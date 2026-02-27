import time
import psutil
import subprocess
from PIL import Image, ImageDraw, ImageFont
import os
import sys
sys.path.append("/home/jalivur/Documents/proyectopantallas")
from Code.expansion import Expansion
from Code.oled import OLED
import json
import signal

# ── Rutas de estado ──────────────────────────────────────────────────────────
STATE_FILE    = "/home/jalivur/Documents/system_dashboard/data/fan_state.json"
LED_FILE      = "/home/jalivur/Documents/system_dashboard/data/led_state.json"      # NUEVO
HW_FILE       = "/home/jalivur/Documents/system_dashboard/data/hardware_state.json" # NUEVO

# ── Señales ───────────────────────────────────────────────────────────────────
stop_flag = False

def handle_exit(signum, frame):
    global stop_flag
    print(f"Señal {signum} recibida, saliendo...")
    stop_flag = True

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

# ── Inicialización ────────────────────────────────────────────────────────────
board = Expansion()
oled  = OLED()
oled.clear()
font  = ImageFont.load_default()

# ── Funciones de lectura de JSON ─────────────────────────────────────────────
def read_fan_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return None

def read_led_state():                          # NUEVO
    """Lee led_state.json. Devuelve None si no existe."""
    if not os.path.exists(LED_FILE):
        return None
    try:
        with open(LED_FILE) as f:
            return json.load(f)
    except:
        return None

def write_hardware_state(chassis_temp, fan0_pct, fan1_pct):  # NUEVO
    """Escribe en hardware_state.json para que el dashboard lo lea."""
    data = {
        "chassis_temp": chassis_temp,
        "fan0_pct":     fan0_pct,
        "fan1_pct":     fan1_pct,
        "ts":           time.time()
    }
    try:
        tmp = HW_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, HW_FILE)   # escritura atómica
    except Exception as e:
        print(f"[fase1] Error escribiendo hardware_state: {e}")

# ── Funciones de hardware ─────────────────────────────────────────────────────
def get_cpu_temp():
    temp = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
    return float(temp.replace("temp=", "").replace("'C\n", ""))

def fan_curve(temp):
    if temp < 40:   return 40
    elif temp > 75: return 255
    else:           return int((temp - 40) * (215 / 35) + 40)

def temp_to_color(temp):
    if temp < 40:   return (0, 255, 0)
    elif temp > 75: return (255, 0, 0)
    else:
        ratio = (temp - 40) / 35
        return (int(255 * ratio), int(255 * (1 - ratio)), 0)

def smooth(prev, target, step=10):
    return tuple(
        prev[i] + max(-step, min(step, target[i] - prev[i]))
        for i in range(3)
    )

def get_ip():
    for _ in range(10):
        ip_output = subprocess.getoutput("hostname -I").split()
        if ip_output:
            return ip_output[0]
        time.sleep(1)
    return "No IP"

def get_ip_of_interface(iface_name="tun0"):
    addrs = psutil.net_if_addrs()
    if iface_name in addrs:
        for addr in addrs[iface_name]:
            if addr.family.name == "AF_INET":
                return addr.address
    return "No IP"

# ── Lógica de LEDs ────────────────────────────────────────────────────────────
# Modos LED del GPIO Board:
#   0 = Off  1 = RGB fijo  2 = Secuencial  3 = Respiración  4 = Arcoíris
_LED_MODE_MAP = {
    "off":       0,
    "static":    1,
    "follow":    2,
    "breathing": 3,
    "rainbow":   4,
}
# ── Estado LED aplicado por última vez ─────────────────────────────────────
# Se compara con el estado deseado para solo escribir I2C cuando cambia algo.
_last_led_applied = {
    "mode": None,   # modo aplicado (None = nunca aplicado)
    "r":    None,
    "g":    None,
    "b":    None,
}

def apply_led_state(led_state, cpu_temp, current_color):
    """
    Aplica el estado de LEDs solo si algo ha cambiado desde la última vez.
    Esto evita resetear las animaciones del firmware (follow, breathing)
    en cada iteración del bucle.

    Devuelve current_color actualizado.
    """
    global _last_led_applied

    # ── Determinar modo y color deseados ─────────────────────────────────────
    if led_state is None or led_state.get("mode", "auto") == "auto":
        # Modo auto: smooth del color hacia temp_to_color
        target_color  = temp_to_color(cpu_temp)
        new_color     = smooth(current_color, target_color)
        desired_mode  = "auto"
        desired_r, desired_g, desired_b = new_color
    else:
        mode_str = led_state.get("mode", "auto")
        if mode_str == "off":
            desired_mode  = "off"
            desired_r, desired_g, desired_b = 0, 0, 0
        elif mode_str == "rainbow":
            desired_mode  = "rainbow"
            desired_r, desired_g, desired_b = 0, 0, 0   # el color no importa en rainbow
        else:
            # static / follow / breathing
            desired_mode  = mode_str
            desired_r = int(led_state.get("r", 0))
            desired_g = int(led_state.get("g", 255))
            desired_b = int(led_state.get("b", 0))
        new_color = (desired_r, desired_g, desired_b)

    # ── Detectar si algo ha cambiado ──────────────────────────────────────────
    # Para modo auto el color cambia en pequeños pasos (smooth), así que solo
    # escribimos si el cambio es mayor que un umbral (evita escrituras I2C constantes
    # mientras el color está prácticamente estable).
    if desired_mode == "auto":
        last_r = _last_led_applied["r"] or 0
        last_g = _last_led_applied["g"] or 0
        last_b = _last_led_applied["b"] or 0
        color_delta = (
            abs(desired_r - last_r) +
            abs(desired_g - last_g) +
            abs(desired_b - last_b)
        )
        mode_changed  = (_last_led_applied["mode"] != "auto")
        color_changed = (color_delta >= 8)   # umbral: ignorar cambios menores de 8 puntos RGB
    else:
        mode_changed  = (_last_led_applied["mode"] != desired_mode)
        color_changed = (
            _last_led_applied["r"] != desired_r or
            _last_led_applied["g"] != desired_g or
            _last_led_applied["b"] != desired_b
        )

    if not mode_changed and not color_changed:
        # Nada que hacer — el firmware gestiona la animación sin interferencia
        return new_color

    # ── Aplicar solo si hay cambio ────────────────────────────────────────────
    if desired_mode == "off":
        board.set_led_mode(0)
        board.set_all_led_color(0, 0, 0)

    elif desired_mode == "rainbow":
        if mode_changed:
            board.set_led_mode(4)
        # No llamar set_all_led_color en rainbow — el firmware gestiona los colores

    elif desired_mode == "breathing":
        if mode_changed:
            board.set_led_mode(3)
        if color_changed:
            board.set_all_led_color(desired_r, desired_g, desired_b)
        # Nota: set_all_led_color en breathing solo fija el COLOR BASE de la respiración,
        # no reinicia la animación si el modo ya estaba en 3. Pero si mode_changed=True
        # (acabamos de activar el modo) es correcto enviarlo una sola vez.

    elif desired_mode == "follow":
        if mode_changed:
            board.set_led_mode(2)
        if color_changed:
            board.set_all_led_color(desired_r, desired_g, desired_b)
        # Mismo principio que breathing

    else:
        # "auto" o "static" → modo 1 RGB fijo
        if mode_changed:
            board.set_led_mode(1)
        board.set_all_led_color(desired_r, desired_g, desired_b)

    # ── Actualizar estado aplicado ────────────────────────────────────────────
    _last_led_applied["mode"] = desired_mode
    _last_led_applied["r"]    = desired_r
    _last_led_applied["g"]    = desired_g
    _last_led_applied["b"]    = desired_b

    return new_color

# ── OLED ──────────────────────────────────────────────────────────────────────
last_oled_state = {
    "cpu": None, "ram": None, "temp": None,
    "ip": None, "tun_ip": None,
    "fan0_duty": None, "fan1_duty": None
}

def draw_oled_smart(cpu, ram, temp, ip, tun_ip, fan0_duty, fan1_duty):
    changed = (
        round(cpu, 1)  != last_oled_state["cpu"]      or
        round(ram, 1)  != last_oled_state["ram"]      or
        int(temp)      != last_oled_state["temp"]     or
        ip             != last_oled_state["ip"]       or
        tun_ip         != last_oled_state["tun_ip"]   or
        fan0_duty      != last_oled_state["fan0_duty"] or
        fan1_duty      != last_oled_state["fan1_duty"]
    )
    if not changed:
        return

    oled.clear()
    oled.draw_text(f"CPU: {cpu:>5.1f} %",   (0, 0))
    oled.draw_text(f"RAM: {ram:>5.1f} %",   (0, 12))
    oled.draw_text(f"TEMP:{temp:>5.1f} C",  (0, 24))
    oled.draw_text(f"IP: {ip}",              (0, 36))
    if tun_ip != "No IP":
        oled.draw_text(f"IP Tun: {tun_ip}",               (0, 48))
    else:
        oled.draw_text(f"Fan1:{fan0_duty}%/ Fan2:{fan1_duty}%", (0, 48))
    oled.show()

    last_oled_state.update({
        "cpu": round(cpu, 1), "ram": round(ram, 1),
        "temp": int(temp), "ip": ip, "tun_ip": tun_ip,
        "fan0_duty": fan0_duty, "fan1_duty": fan1_duty
    })

# ── Bucle principal ───────────────────────────────────────────────────────────
try:
    board.set_fan_mode(1)   # Manual
    board.set_led_mode(1)   # RGB fijo (modo inicial, luego apply_led_state lo gestiona)
    current_color = (0, 255, 0)

    last_pwm         = None
    last_ip          = None
    last_tun_ip      = "No IP"
    last_ip_time     = 0
    last_state_file  = None
    last_state_time  = 0
    last_temp        = None
    last_temp_time   = 0
    last_led_file    = None
    last_led_time    = 0
    last_hw_time     = 0    # NUEVO: cuándo escribimos hardware_state por última vez

    while not stop_flag:
        now = time.time()
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent

        # ── Temperatura CPU (cada 1s) ──
        if now - last_temp_time > 1:
            last_temp      = get_cpu_temp()
            last_temp_time = now
        temp = last_temp

        # ── IPs (cada 20s) ──
        if now - last_ip_time > 20:
            last_ip     = get_ip()
            last_tun_ip = get_ip_of_interface("tun0")
            last_ip_time = now
        ip     = last_ip
        tun_ip = last_tun_ip

        # ── fan_state.json (cada 1s) ──
        if now - last_state_time > 1:
            last_state_file  = read_fan_state()
            last_state_time  = now
        state = last_state_file

        # ── led_state.json (cada 1s) ── NUEVO
        if now - last_led_time > 1:
            last_led_file = read_led_state()
            last_led_time = now

        # ── Fans ──
        fan_pwm = None
        if state:
            mode = state.get("mode")
            if mode in ("manual", "auto", "silent", "normal", "performance"):
                fan_pwm = state.get("target_pwm")
        if fan_pwm is None:
            fan_pwm = fan_curve(temp)
        if fan_pwm != last_pwm:
            board.set_fan_duty(fan_pwm, fan_pwm)
            last_pwm = fan_pwm

        fan_percent = int(last_pwm * 100 / 255)
        fan0_duty   = fan_percent
        fan1_duty   = fan_percent

        # ── LEDs ── NUEVO: delegar a apply_led_state
        current_color = apply_led_state(last_led_file, temp, current_color)

        # ── hardware_state.json (cada 5s) ── NUEVO
        if now - last_hw_time > 5:
            try:
                chassis_temp = board.get_temp()
                real_fan0    = int(board.get_fan0_duty() * 100 / 255)
                real_fan1    = int(board.get_fan1_duty() * 100 / 255)
            except Exception:
                chassis_temp = 0
                real_fan0    = fan0_duty
                real_fan1    = fan1_duty
            write_hardware_state(chassis_temp, real_fan0, real_fan1)
            last_hw_time = now

        # ── OLED ──
        draw_oled_smart(cpu, ram, temp, ip, tun_ip, fan0_duty, fan1_duty)

        time.sleep(0.5)

except KeyboardInterrupt:
    print("Salida limpia")
except Exception as e:
    print(f"Unexpected error: {e}")
finally:
    oled.clear()
    board.set_all_led_color(0, 0, 0)
    board.set_fan_duty(0, 0)