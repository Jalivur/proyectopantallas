import time
import psutil
import subprocess
from PIL import Image, ImageDraw, ImageFont
import os
import sys
sys.path.append("/home/jalivur/Documents/proyectyopantallas")
from Code.expansion import Expansion
from Code.oled import OLED
import json
import os

STATE_FILE = "/home/jalivur/Documents/proyectyopantallas/fan_state.json"

def read_fan_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return None


import signal
import sys

stop_flag = False

def handle_exit(signum, frame):
    global stop_flag
    print(f"Señal {signum} recibida, saliendo...")
    stop_flag = True

# Capturar SIGTERM (pkill normal) y SIGINT (Ctrl+C)
signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

# ---------- Inicialización ----------
board = Expansion()

# OLED
oled = OLED()
oled.clear()

font = ImageFont.load_default()


# ---------- Funciones ----------
def get_cpu_temp():
    temp = subprocess.check_output(
        ["vcgencmd", "measure_temp"]
    ).decode()
    return float(temp.replace("temp=", "").replace("'C\n", ""))

def fan_curve(temp):
    if temp < 40:
        return 40
    elif temp > 75:
        return 255
    else:
        return int((temp - 40) * (215 / 35) + 40)

def temp_to_color(temp):
    if temp < 40:
        return (0, 255, 0)
    elif temp > 75:
        return (255, 0, 0)
    else:
        ratio = (temp - 40) / 35
        r = int(255 * ratio)
        g = int(255 * (1 - ratio))
        return (r, g, 0)
def smooth(prev, target, step=10):
    return tuple(
        prev[i] + max(-step, min(step, target[i] - prev[i]))
        for i in range(3)
    )
def get_ip():
    for _ in range(10):  # hasta 10 intentos
        ip_output = subprocess.getoutput("hostname -I").split()
        if ip_output:
            return ip_output[0]
        time.sleep(1)
    return "No IP"


last_state = {
    "cpu": None,
    "ram": None,
    "temp": None,
    "ip": None,
    "fan0_duty": None,
    "fan1_duty": None
    
}


def draw_oled_smart(cpu, ram, temp, ip):
    changed = (
        round(cpu, 1) != last_state["cpu"] or
        round(ram, 1) != last_state["ram"] or
        int(temp) != last_state["temp"] or
        ip != last_state["ip"] or
        fan0_duty != last_state["fan0_duty"] or
        fan1_duty != last_state["fan1_duty"]
    )

    if not changed:
        return

    oled.clear()
    oled.draw_text(f"CPU: {cpu:>5.1f} %", (0, 0))
    oled.draw_text(f"RAM: {ram:>5.1f} %", (0, 12))
    oled.draw_text(f"TEMP:{temp:>5.1f} C", (0, 24))
    oled.draw_text(f"IP: {ip}", (0, 36))
    oled.draw_text(f"Fan1:{fan0_duty}%/ Fan2:{fan1_duty}%", (0, 48))
    oled.show()

    last_state["cpu"] = round(cpu, 1)
    last_state["ram"] = round(ram, 1)
    last_state["temp"] = int(temp)
    last_state["ip"] = ip
    last_state["fan0_duty"] = fan0_duty
    last_state["fan1_duty"] = fan1_duty


# ---------- Bucle principal ----------
try:
    board.set_fan_mode(1)  # Manual
    board.set_led_mode(1)  # RGB fijo
    current_color = (0, 255, 0)
    last_pwm = None
    last_ip = None
    last_ip_time = 0
    last_state_file = None
    last_state_time = 0
    last_temp = None
    last_temp_time = 0
    while not stop_flag:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        
        now = time.time()
        if now - last_temp_time > 1:
            last_temp = get_cpu_temp()
            last_temp_time = now

        temp = last_temp
        
        now = time.time()

        if now - last_ip_time > 30:   # cada 30 segundos
            last_ip = get_ip()
            last_ip_time = now

        ip = last_ip


        now = time.time()
        if now - last_state_time > 1:
            state = read_fan_state()
            last_state_file = state
            last_state_time = now
        else:
            state = last_state_file


        fan_pwm = None

        if state:
            mode = state.get("mode")

            if mode == "manual":
                fan_pwm = state.get("target_pwm")

            elif mode in ("auto", "silent", "normal", "performance"):
                fan_pwm = state.get("target_pwm")

        # fallback de seguridad (si no hay estado)
        if fan_pwm is None:
            fan_pwm = fan_curve(temp)

        # aplicar solo si cambia
        if fan_pwm != last_pwm:
            board.set_fan_duty(fan_pwm, fan_pwm)
            last_pwm = fan_pwm

        def safe_duty(val):
            if val is None:
                return 0
            return int(val * 100) // 255

        fan_percent = int(last_pwm * 100 / 255)

        fan0_duty = fan_percent
        fan1_duty = fan_percent


        target_color = temp_to_color(temp)
        current_color = smooth(current_color, target_color)
        board.set_all_led_color(*current_color)

        draw_oled_smart(cpu, ram, temp, ip)

        time.sleep(0.5)

except KeyboardInterrupt:
    print("Salida limpia")
except Exception as e:
    print(f"Unexpected error: {e}")
finally:
    oled.clear()
    board.set_all_led_color(0, 0, 0)
    board.set_fan_duty(0, 0)
