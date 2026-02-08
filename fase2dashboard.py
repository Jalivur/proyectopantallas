import tkinter as tk
import psutil
import subprocess
from collections import deque
import json
import os
import socket
import logging
import threading
import re
from functools import partial


# -----------------------------
# ---------- Archivos ----------
# -----------------------------
STATE_FILE = "/home/jalivur/Documents/proyectopantallas/fan_state.json"
CURVE_FILE = "/home/jalivur/Documents/proyectopantallas/fan_curve.json"

# -----------------------------
# ---------- DSI display config ----------
# -----------------------------
DSI_WIDTH = 800
DSI_HEIGHT = 480
DSI_X = 1920 - DSI_WIDTH
DSI_Y = 1080 - DSI_HEIGHT

# -----------------------------
# ---------- Config ----------
# -----------------------------
UPDATE_MS = 2000
HISTORY = 60
WIDTH = 800
HEIGHT = 20

CPU_WARN  = 60
CPU_CRIT  = 85
TEMP_WARN = 60
TEMP_CRIT = 75
RAM_WARN  = 65
RAM_CRIT  = 85
NET_WARN  = 2.0   # MB/s
NET_CRIT  = 6.0
NET_INTERFACE = None   # None = auto | "eth0" | "wlan0"
NET_MAX_MB = 10.0   # eje fijo en MB/s
NET_MIN_SCALE = 0.5
NET_MAX_SCALE = 200.0   # límite de seguridad
NET_IDLE_THRESHOLD = 0.2
NET_IDLE_RESET_TIME = 15   # segundos

# -----------------------------
# ---------- Helper style ----------
# -----------------------------
def style_radiobutton(rb, fg="#00ffff", bg="#111111", hover_fg="#1ae313"):
    rb.config(fg=fg, bg=bg, selectcolor=bg, activeforeground=fg, activebackground=bg,
              font=("FiraFiraMono Nerd Font", 14, "bold"), indicatoron=True)
    def on_enter(e): rb.config(fg=hover_fg)
    def on_leave(e): rb.config(fg=fg)
    rb.bind("<Enter>", on_enter)
    rb.bind("<Leave>", on_leave)

def make_futuristic_button(parent, text, command=None, width=12, height=2):
    btn = tk.Button(parent, text=text, command=command,
                    fg="#00ffff", bg="#111111",
                    activebackground="#222222", activeforeground="#00ffff",
                    borderwidth=2, relief="ridge", width=width, height=height,
                    font=("FiraFiraMono Nerd Font", 14, "bold"))
    def on_enter(e): btn.config(fg="#00ffff", bg="#222222")
    def on_leave(e): btn.config(fg="#00ffff", bg="#111111")
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn

def style_slider(slider, color="#00ffff"):
    slider.config(troughcolor="#14611E", sliderrelief="flat", bd=0,
                  highlightthickness=0, fg=color, bg="#111111", activebackground=color)

def style_scrollbar(sb, color="#111111"):
    sb.config(troughcolor="#14611E", bg=color, activebackground=color,
              highlightthickness=0, relief="flat")

def custom_msgbox(parent, text, title="Info"):
    popup = tk.Toplevel(parent)
    popup.overrideredirect(True)
    popup.configure(bg="#111111")

    # --- Contenedor ---
    frame = tk.Frame(popup, bg="#111111", padx=20, pady=20)
    frame.pack(fill="both", expand=True)

    title_lbl = tk.Label(
        frame, text=title,
        fg="#00ffff", bg="#111111",
        font=("FiraFiraMono Nerd Font", 16, "bold")
    )
    title_lbl.pack(anchor="center", pady=(0, 10))

    text_lbl = tk.Label(
        frame, text=text,
        fg="white", bg="#111111",
        font=("FiraFiraMono Nerd Font", 14),
        justify="left",
        wraplength=800   # límite lógico, no tamaño final
    )
    text_lbl.pack(anchor="center", pady=(0, 15))

    btn = tk.Button(
        frame, text="OK",
        fg="#00ffff", bg="#111111",
        command=popup.destroy,
        width=10, height=1
    )
    btn.pack()

    # --- Forzar cálculo de tamaño ---
    popup.update_idletasks()

    # --- Tamaño requerido ---
    w = popup.winfo_reqwidth()
    h = popup.winfo_reqheight()

    # --- Tamaño máximo de pantalla ---
    max_w = parent.winfo_screenwidth() - 40
    max_h = parent.winfo_screenheight() - 40

    w = min(w, max_w)
    h = min(h, max_h)

    # --- Centrar sobre la ventana padre ---
    x = parent.winfo_x() + (parent.winfo_width() // 2) - (w // 2)
    y = parent.winfo_y() + (parent.winfo_height() // 2) - (h // 2)

    popup.geometry(f"{w}x{h}+{x}+{y}")

    popup.lift()
    popup.focus_force()
    popup.grab_set()


# -----------------------------
# ---------- Utils ----------
# -----------------------------
def write_state(data):
    tmp = STATE_FILE + ".tmp"
    with open(tmp,"w") as f: json.dump(data,f)
    os.replace(tmp,STATE_FILE)

def load_state():
    try:
        with open(STATE_FILE) as f:
            data=json.load(f)
            if not isinstance(data,dict): return {"mode":"auto","target_pwm":None}
            return {"mode":data.get("mode","auto"), "target_pwm":data.get("target_pwm")}
    except: return {"mode":"auto","target_pwm":None}

def load_curve():
    try:
        with open(CURVE_FILE) as f:
            data=json.load(f)
            pts=data.get("points",[])
            if not isinstance(pts,list): pts=[]
            sanitized=[]
            for p in pts:
                try: t=int(p.get("temp",0))
                except: t=0
                try: pwm=int(p.get("pwm",0))
                except: pwm=0
                pwm=max(0,min(255,pwm))
                sanitized.append({"temp":t,"pwm":pwm})
            if not sanitized:
                sanitized=[{"temp":40,"pwm":100},{"temp":50,"pwm":100},{"temp":60,"pwm":100},{"temp":70,"pwm":63},{"temp":80,"pwm":81}]
            return sorted(sanitized,key=lambda x:x["temp"])
    except:
        return [{"temp":40,"pwm":100},{"temp":50,"pwm":100},{"temp":60,"pwm":100},{"temp":70,"pwm":63},{"temp":80,"pwm":81}]

def compute_pwm_from_curve(temp):
    curve=sorted(load_curve(),key=lambda p:p["temp"])
    if not curve: return 0
    if temp<=curve[0]["temp"]: return int(curve[0]["pwm"])
    if temp>=curve[-1]["temp"]: return int(curve[-1]["pwm"])
    for i in range(len(curve)-1):
        t1,p1=curve[i]["temp"],curve[i]["pwm"]
        t2,p2=curve[i+1]["temp"],curve[i+1]["pwm"]
        if t1<=temp<=t2:
            if t2==t1: return int(p1)
            r=(temp-t1)/(t2-t1)
            return int(p1+r*(p2-p1))
    return int(curve[-1]["pwm"])

# -----------------------------
# ---------- Sensors ----------
# -----------------------------
def get_cpu_temp():
    try:
        out=subprocess.check_output(["vcgencmd","measure_temp"]).decode()
        return float(out.replace("temp=","").replace("'C\n",""))
    except:
        return 0.0

# -----------------------------
# ---------- Graph helpers ----------
# -----------------------------
def draw_graph(canvas, data, max_val, color, y_offset=0):
    step = WIDTH / (len(data) - 1)
    pts = []
    for i, v in enumerate(data):
        x = i * step
        y = HEIGHT - (v / max_val) * HEIGHT + y_offset
        pts.append((x, y))
    for i in range(len(pts) - 1):
        canvas.create_line(
            *pts[i], *pts[i+1],
            fill=color,
            width=2
        )

def init_graph_lines(canvas, history_len, color, width=2):
    lines = []
    for _ in range(history_len - 1):
        lid = canvas.create_line(0, 0, 0, 0, fill=color, width=width)
        lines.append(lid)
    return lines

def update_graph_lines(canvas, lines, data, max_val, y_offset=0):
    if not lines:
        return
    step = WIDTH / (len(data) - 1)
    for i in range(len(lines)):
        v1 = data[i]
        v2 = data[i + 1]

        x1 = i * step
        x2 = (i + 1) * step

        y1 = HEIGHT - (v1 / max_val) * HEIGHT + y_offset
        y2 = HEIGHT - (v2 / max_val) * HEIGHT + y_offset

        canvas.coords(lines[i], x1, y1, x2, y2)
        
def recolor_lines(canvas, lines, color):
    for lid in lines:
        canvas.itemconfig(lid, fill=color)

def level_color(v,w,c):
    if v<w: return "#00ff00"
    if v<c: return "#ffaa00"
    return "#ff3333"

def net_color(v):
    if v < NET_WARN:
        return "#ec0909"
    if v < NET_CRIT:
        return "#ffaa00"
    return "#52f828"

def smooth(data, n=5):
    if len(data) < n:
        return data
    out = []
    for i in range(len(data)):
        start = max(0, i - n + 1)
        out.append(sum(data[start:i+1]) / (i - start + 1))
    return out

def make_block(parent,title):
    lbl=tk.Label(parent,text=title,fg="white",bg="black",font=("FiraFiraMono Nerd Font",16))
    lbl.pack(anchor="w")
    val=tk.Label(parent,fg="white",bg="black",font=("FiraFiraMono Nerd Font",22,"bold"))
    val.pack(anchor="e")
    cvs=tk.Canvas(parent,width=WIDTH,height=HEIGHT,bg="black",highlightthickness=0)
    cvs.pack()
    return lbl,val,cvs

# -----------------------------
# ---------- Network helpers ----------
# -----------------------------
def get_net_io(interface=None):
    """
    Retorna la interfaz usada y sus stats.
    Evita picos absurdos y mantiene el historial correcto.
    """
    global last_net_pernic

    stats = psutil.net_io_counters(pernic=True)

    if interface and interface in stats:
        last_net_pernic = stats
        return interface, stats[interface]

    best_name = None
    best_speed = -1

    for name in stats:
        if name not in last_net_pernic:
            continue

        curr = stats[name]
        prev = last_net_pernic[name]

        speed = (
            (curr.bytes_recv - prev.bytes_recv) +
            (curr.bytes_sent - prev.bytes_sent)
        )

        # --- Evitar picos absurdos ---
        if speed < 0 or speed > 500*1024*1024:  # 500 MB en intervalo
            continue

        if speed > best_speed:
            best_speed = speed
            best_name = name

    last_net_pernic = stats

    if best_name:
        return best_name, stats[best_name]

    # fallback
    name = next(iter(stats))
    return name, stats[name]

def safe_net_speed(curr, prev):
    if not prev:
        return 0.0, 0.0

    dl = curr.bytes_recv - prev.bytes_recv
    ul = curr.bytes_sent - prev.bytes_sent

    # --- Si el contador bajó → reset ---
    if dl < 0 or ul < 0:
        return 0.0, 0.0

    # convertir a MB/s
    dl = dl / 1024 / 1024
    ul = ul / 1024 / 1024

    # --- Filtro de picos absurdos ---
    if dl > 500 or ul > 500:
        return 0.0, 0.0

    return dl, ul

def adaptive_scale(current_max, data):
    """
    Ajusta escala dinámica, sube rápido con tráfico real,
    baja progresivamente y se reinicia si hay inactividad.
    """
    global net_idle_counter

    if not data:
        return current_max * 0.5

    peak = max(data)

    # --- Subir rápido si hay tráfico real ---
    if peak > current_max:
        net_idle_counter = 0
        return min(peak * 1.2, NET_MAX_SCALE)

    # --- Detectar tráfico bajo ---
    if peak < NET_IDLE_THRESHOLD:
        net_idle_counter += 1
    else:
        net_idle_counter = 0

    # --- Reset si lleva tiempo sin tráfico ---
    if net_idle_counter > NET_IDLE_RESET_TIME:
        return NET_MIN_SCALE

    # --- Decaimiento progresivo ---
    new_val = current_max * 0.90
    return max(new_val, NET_MIN_SCALE)


def get_interfaces_ips():
    """
    Retorna un diccionario: { "eth0": "192.168.1.5", "wlan0": "192.168.1.10", ... }
    """
    result = {}
    addrs = psutil.net_if_addrs()
    for iface, addr_list in addrs.items():
        for addr in addr_list:
            # AF_INET = IPv4
            if addr.family == socket.AF_INET:
                result[iface] = addr.address
    return result

def run_speedtest():
    global speedtest_running

    speedtest_running = True

    speedtest_result["status"] = "running"
    speedtest_result["ping"] = None
    speedtest_result["download"] = None
    speedtest_result["upload"] = None

    try:
        proc = subprocess.run(
            ["speedtest-cli", "--simple"],
            capture_output=True,
            text=True,
            timeout=60
        )

        out = proc.stdout

        ping = re.search(r"Ping:\s+([\d.]+)", out)
        down = re.search(r"Download:\s+([\d.]+)", out)
        up   = re.search(r"Upload:\s+([\d.]+)", out)

        speedtest_result["ping"] = float(ping.group(1)) if ping else None
        speedtest_result["download"] = float(down.group(1))/8 if down else None
        speedtest_result["upload"] = float(up.group(1))/8 if up else None

        speedtest_result["status"] = "done"

    except subprocess.TimeoutExpired:
        speedtest_result["status"] = "timeout"
    except Exception:
        speedtest_result["status"] = "error"

    speedtest_running = False

def start_speedtest():
    if speedtest_running:
        return
    t = threading.Thread(target=run_speedtest, daemon=True)
    t.start()

def list_all_usb_devices():
    """
    Retorna dos listas de dispositivos USB:
    1. almacenamiento: discos/particiones USB con mountpoint
    2. otros: cualquier otro USB (teclados, ratones, cámaras, hubs, etc.)
    Cada dispositivo es un dict con keys: 'name', 'type', 'mount', 'dev', 'size'
    """
    storage_devices = []
    other_devices = []

    # --- Discos USB ---
    try:
        out = subprocess.check_output(
            ["lsblk", "-o", "NAME,MODEL,TRAN,MOUNTPOINT,SIZE,TYPE", "-J"], text=True
        )
        blk = json.loads(out)
        for block in blk.get("blockdevices", []):
            if block.get("tran") == "usb":
                # Guardar disco padre
                dev = {
                    "name": block.get("model", "USB Disk"),
                    "type": block.get("type", "disk"),
                    "mount": block.get("mountpoint"),
                    "dev": "/dev/" + block.get("name"),
                    "size": block.get("size"),
                    "children": []
                }

                # Guardar particiones como hijos
                for child in block.get("children", []):
                    child_dev = {
                        "name": child.get("model") or child.get("name"),
                        "type": child.get("type"),
                        "mount": child.get("mountpoint"),
                        "dev": "/dev/" + child.get("name"),
                        "size": child.get("size")
                    }
                    dev["children"].append(child_dev)

                storage_devices.append(dev)

    except Exception:
        pass

    # --- Otros dispositivos USB ---
    try:
        out = subprocess.check_output(["lsusb"], text=True)
        
        for line in out.strip().split("\n"):
            if line:
                other_devices.append({"name": line, "type": "usb", "mount": None, "dev": None, "size": None})
    except Exception:
        other_devices.append({"name": "Error listando USBs", "type": "error", "mount": None, "dev": None, "size": None})

    return storage_devices, other_devices

def parse_lsusb_line(line):
    """
    Convierte una línea de lsusb en algo más legible:
    'Bus 004 Device 002: ID 0b05:17eb ASUSTek Computer, Inc. USB-AC55 ...'
    → 'Bus 004 - ASUSTek Computer, Inc.: USB-AC55 ...'
    """
    parts = line.split()
    try:
        # Extraer número de bus
        bus_index = parts.index("Bus") + 1
        bus = parts[bus_index]

        # Buscar el primer elemento después del ID XXXX:YYYY
        id_index = parts.index("ID") + 2
        manufacturer = parts[id_index]
        model = " ".join(parts[id_index+1:])

        return f"Bus {bus} - {manufacturer}: {model}"
    except Exception:
        return line  # fallback si no se puede parsear


last_storage_devices = set()  # global

def refresh_usb_devices():
    """
    Refresca los dispositivos USB en la ventana actual.
    """
    global usb_inner_frame, usb_devices_labels, usb_devices_buttons

    if not usb_win or not usb_win.winfo_exists():
        return

    storage, others = list_all_usb_devices()

    # Limpiar widgets antiguos (excepto botón refrescar)
    for key, lbl in list(usb_devices_labels.items()):
        if key != "refresh_btn": lbl.destroy()
        usb_devices_labels.pop(key, None)
    for btn in usb_devices_buttons.values():
        btn.destroy()
    usb_devices_buttons.clear()

    # --- Almacenamiento USB ---
    if storage:
        lbl_title = tk.Label(usb_inner_frame, text="Almacenamiento USB:", fg="#14611E", bg="black",
                            font=("FiraFiraMono Nerd Font", 20, "bold"))
        lbl_title.pack(anchor="w", pady=(10, 5))
        usb_devices_labels["storage_title"] = lbl_title
        for idx, dev in enumerate(storage):
            name = dev.get("model") or dev.get("name")
            size = dev.get("size")
            info_text = f"{name} ({dev['type']}) - {size}"
            lbl = tk.Label(usb_inner_frame, text=info_text, fg="#00ffff", bg="black",
                        font=("FiraFiraMono Nerd Font", 18), wraplength=DSI_WIDTH-60)
            lbl.pack(anchor="w", pady=2)
            usb_devices_labels[f"storage_{idx}"] = lbl

            # --- Botón de expulsar para el disco padre siempre ---
            btn = tk.Button(
                usb_inner_frame,
                text="Expulsar",
                fg="#00ffff", bg="#111111",
                command=lambda d=dev: eject_usb_device_with_popup(d),
                font=("FiraFiraMono Nerd Font", 14, "bold"),
                width=12, height=1
            )
            btn.pack(anchor="w", padx=20, pady=(0,4))
            usb_devices_buttons[f"storage_{idx}"] = btn

                # --- Mostrar particiones montadas ---
            children = dev.get("children") or []
            for c_idx, part in enumerate(children):
                mount = part.get("mount")
                name = part.get("name")
                part_text = f"Partición: {name}"
                if mount:
                    part_text += f" | Montado en: {mount}"  # <-- aquí añadimos el punto de montaje

                # Creamos la etiqueta
                part_lbl = tk.Label(
                    usb_inner_frame,
                    text=part_text,
                    fg="#00ffff",
                    bg="black",
                    font=("FiraFiraMono Nerd Font", 16),
                    wraplength=DSI_WIDTH-60
                )
                part_lbl.pack(anchor="w", padx=40, pady=1)
                usb_devices_labels[f"storage_{idx}_part_{c_idx}"] = part_lbl



    # --- Otros dispositivos USB ---
    if others:
        lbl_title = tk.Label(usb_inner_frame, text="Otros dispositivos USB:", fg="#14611E", bg="black",
                             font=("FiraFiraMono Nerd Font", 20, "bold"))
        lbl_title.pack(anchor="w", pady=(10, 5))
        usb_devices_labels["others_title"] = lbl_title

        for idx, dev in enumerate(others):
            text = parse_lsusb_line(dev['name'])
            lbl = tk.Label(usb_inner_frame, text=text, fg="#00ffff", bg="black",
                        font=("FiraFiraMono Nerd Font", 16), anchor="w", justify="left", wraplength=DSI_WIDTH-60)
            lbl.pack(anchor="w", pady=1)
            usb_devices_labels[f"other_{idx}"] = lbl


def eject_usb_device_with_popup(dev):
    try:
        # Desmontar todas las particiones del disco
        if dev['type'] == 'disk':
            out = subprocess.check_output(
                ["lsblk", "-ln", "-o", "NAME,MOUNTPOINT", dev['dev']], text=True
            )
            for line in out.strip().split("\n"):
                parts = line.split()
                if len(parts) == 2 and parts[1]:  # tiene mountpoint
                    part_dev = "/dev/" + parts[0]
                    subprocess.run(["udisksctl", "unmount", "-b", part_dev], check=True)
        elif dev['mount']:  # si es solo una partición
            subprocess.run(["udisksctl", "unmount", "-b", dev['dev']], check=True)

        # Expulsar el disco
        subprocess.run(["udisksctl", "power-off", "-b", dev['dev']], check=True)
        custom_msgbox(usb_win, f"{dev['name']} expulsado correctamente")
    except subprocess.CalledProcessError as e:
        custom_msgbox(usb_win, f"No se pudo expulsar {dev['name']}.\n{e}", title="Error")


# -----------------------------
# ---------- Variables globales ----------
# -----------------------------
root = tk.Tk()
root.title("Fan Control")
root.configure(bg="black")
root.overrideredirect(True)

# Variables de control
mode_var = tk.StringVar(value="auto")
manual_pwm = tk.IntVar(value=128)
curve_vars=[]
last_state=None
monitor_win = None
# Históricos y líneas gráficas
cpu_hist=deque([0]*HISTORY,maxlen=HISTORY)
ram_hist=deque([0]*HISTORY,maxlen=HISTORY)
temp_hist=deque([0]*HISTORY,maxlen=HISTORY)
cpu_lines  = []
ram_lines  = []
temp_lines = []

disk_lbl = None
disk_val = None
disk_cvs = None
disk_hist = deque([0]*HISTORY, maxlen=HISTORY)
disk_lines = []
disk_read_hist = deque([0]*HISTORY, maxlen=HISTORY)
disk_write_hist = deque([0]*HISTORY, maxlen=HISTORY)
last_disk_io = psutil.disk_io_counters()
disk_write_lvl = None
disk_write_val = None
disk_read_lvl = None
disk_read_val = None
disk_write_lines = []
disk_read_lines = []
disk_write_cvs = None
disk_read_cvs = None

# Red
net_download_hist = deque([0]*HISTORY, maxlen=HISTORY) 
net_upload_hist = deque([0]*HISTORY, maxlen=HISTORY) 
last_used_iface = None
last_net_io = {}
last_net_pernic = psutil.net_io_counters(pernic=True)
net_win = None
net_dynamic_max = 1.0
net_idle_counter = 0
net_dl_lbl = net_dl_val = net_dl_cvs = None
net_ul_lbl = net_ul_val = net_ul_cvs = None
net_dl_lines = []
net_ul_lines = []
net_iface_labels = {}  # diccionario: iface -> Label widget
ips_frame = None       # frame donde estarán las IPs
speedtest_running = False
speedtest_result = {
    "ping": None,
    "download": None,
    "upload": None,
    "status": "idle"
}
net_speed_test_lbl = None
net_speed_test_val = None
# ---------- Ventana monitor USB ----------
usb_win = None
usb_inner_frame = None  # Frame interno donde estarán los dispositivos
usb_scroll_canvas = None
usb_scroll_lines = []   # opcional, si quieres animar algún gráfico futuro
usb_devices_labels = {} # Diccionario: id -> Label widget
usb_devices_buttons = {}     # idx -> botón de expulsar
usb_devices_info = []        # lista de dicts con info de cada USB

# -----------------------------
# ---------- Posicionamiento DSI para root ----------
# -----------------------------
def detect_dsi_geometry():
    """
    Detecta la posición del DSI conectado y devuelve (x, y).
    Si no encuentra, devuelve None.
    """
    try:
        out = subprocess.check_output(["xrandr","--query"], stderr=subprocess.DEVNULL).decode()
        for line in out.splitlines():
            if " connected " in line:
                parts = line.split()
                for tok in parts:
                    if "+" in tok and "x" in tok:
                        try:
                            res,pos = tok.split("+",1)
                            w,h = map(int,res.split("x"))
                            x,y = map(int,pos.split("+"))
                            if w==DSI_WIDTH and h==DSI_HEIGHT:
                                return x,y
                        except: pass
        return None
    except:
        return None

pos = detect_dsi_geometry()
if pos:
    DSI_X, DSI_Y = pos
else:
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    DSI_X = max(0, screen_w - DSI_WIDTH)
    DSI_Y = max(0, screen_h - DSI_HEIGHT)

CTRL_W, CTRL_H = 800, 480
root.geometry(f"{CTRL_W}x{CTRL_H}+{DSI_X}+{DSI_Y}")
root.resizable(False, False)

# -----------------------------
# ---------- Layout principal ----------
# -----------------------------
main = tk.Frame(root, bg="black"); main.pack(fill="both", expand=True)
top = tk.Frame(main, bg="black"); top.pack(fill="both", expand=True, padx=6, pady=(6,2))
bottom = tk.Frame(main, bg="black"); bottom.pack(fill="x", padx=8, pady=(0,4))

# -----------------------------
# ---------- Modo ----------
# -----------------------------
mode_frame = tk.LabelFrame(top, text="Modo", fg="white", bg="black", labelanchor="nw", padx=10, pady=8)
mode_frame.pack(fill="x", pady=4)
modes_row = tk.Frame(mode_frame, bg="black"); modes_row.pack(anchor="w")

def set_mode(mode):
    """Actualiza modo y guarda en estado"""
    mode_var.set(mode)
    write_state({"mode":mode,"target_pwm":None})

for m in ("auto","silent","normal","performance","manual"):
    rb = tk.Radiobutton(modes_row, text=m.upper(), variable=mode_var, value=m,
                        command=lambda m=m: set_mode(m), bg="black", fg="white", selectcolor="black")
    rb.pack(side="left", padx=6)
    style_radiobutton(rb)

# -----------------------------
# ---------- PWM Manual ----------
# -----------------------------
manual_frame = tk.LabelFrame(top, text="Control manual PWM", fg="white", bg="black", labelanchor="nw", padx=10, pady=8)
manual_frame.pack(fill="x", pady=4)
manual_row = tk.Frame(manual_frame, bg="black"); manual_row.pack(fill="x")

manual_scale = tk.Scale(manual_row, from_=0, to=255, orient="horizontal", variable=manual_pwm,
                        bg="black", fg="white", highlightthickness=0, length=560, sliderlength=36, width=30)
manual_scale.pack(side="left", fill="x", expand=True)
style_slider(manual_scale)

manual_lbl = tk.Label(manual_row, textvariable=manual_pwm, fg="white", bg="black", width=4,
                      font=("FiraFiraMono Nerd Font", 20, "bold"))
manual_lbl.pack(side="left", padx=12)

# Al mover el slider, si estamos en manual, actualizamos el estado
manual_scale.configure(command=lambda val: write_state({"mode":"manual","target_pwm":max(0,min(255,int(float(val))))}) if mode_var.get()=="manual" else None)

# -----------------------------
# ---------- Curva ----------
# -----------------------------
curve_frame = tk.LabelFrame(top, text="Curva térmica", fg="white", bg="black", labelanchor="nw", padx=10, pady=8)
curve_frame.pack(fill="both", expand=True, pady=4)

canvas = tk.Canvas(curve_frame, bg="black", highlightthickness=0, height=180)
canvas.pack(side="left", fill="both", expand=True)

scrollbar = tk.Scrollbar(curve_frame, orient="vertical", command=canvas.yview, width=30)
scrollbar.pack(side="right", fill="y")
canvas.configure(yscrollcommand=scrollbar.set)
style_scrollbar(scrollbar)

curve_inner = tk.Frame(canvas, bg="black")
canvas.create_window((0,0), window=curve_inner, anchor="nw")

curve_inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

curve_vars.clear()
for p in load_curve():
    row = tk.Frame(curve_inner, bg="black"); row.pack(fill="x", pady=6)
    tk.Label(row, text=f'{p["temp"]}°C', fg="white", bg="black", width=6).pack(side="left")
    var = tk.IntVar(value=p["pwm"])
    tk.Label(row, textvariable=var, fg="white", bg="black", width=4).pack(side="right")
    scale = tk.Scale(row, from_=0, to=255, orient="horizontal", variable=var,
                     bg="black", fg="white", highlightthickness=0, length=520, sliderlength=28, width=30)
    scale.pack(side="left", fill="x", expand=True, padx=6)
    style_slider(scale)
    curve_vars.append((p["temp"], var))

# -----------------------------
# ---------- Actions ----------
# -----------------------------
actions = tk.Frame(bottom, bg="black"); actions.pack(fill="x", pady=4)

def save_curve():
    """Guarda los sliders actuales en el archivo JSON"""
    data = {"points":[{"temp":t,"pwm":v.get()} for t,v in curve_vars]}
    with open(CURVE_FILE, "w") as f: json.dump(data, f, indent=2)
    custom_msgbox(root, "Curva guardada correctamente", "Guardado")

def restore_default():
    """Restaura la curva por defecto y actualiza sliders"""
    default = [{"temp":40,"pwm":100},{"temp":50,"pwm":130},{"temp":60,"pwm":160},{"temp":70,"pwm":180},{"temp":80,"pwm":255}]
    with open(CURVE_FILE, "w") as f: json.dump({"points":default}, f, indent=2)
    # --- Actualizamos los sliders para reflejar la curva por defecto ---
    for t_var, (t, var) in zip(default, curve_vars):
        var.set(t_var["pwm"])
    custom_msgbox(root, "Curva restaurada por defecto", "Restaurado")

make_futuristic_button(actions,"Guardar curva", save_curve, width=16, height=2).pack(side="left", padx=10)
make_futuristic_button(actions,"Restaurar por defecto", restore_default, width=18, height=2).pack(side="left", padx=10)

# ---------- Ventana monitor placa ----------
monitor_win = None
cpu_lbl = cpu_val = cpu_cvs = None
ram_lbl = ram_val = ram_cvs = None
temp_lbl = temp_val = temp_cvs = None

def open_monitor_window():
    global monitor_win, cpu_lbl, cpu_val, cpu_cvs, ram_lbl, ram_val, ram_cvs, temp_lbl, temp_val, temp_cvs
    global cpu_lines, ram_lines, temp_lines
    global disk_lbl, disk_val, disk_cvs, disk_lines
    global disk_write_lvl, disk_write_val, disk_read_lvl, disk_read_val, disk_write_lines, disk_read_lines, disk_write_cvs, disk_read_cvs

    if monitor_win and monitor_win.winfo_exists():
        monitor_win.lift()
        return

    monitor_win = tk.Toplevel(root)
    monitor_win.title("System Monitor")
    monitor_win.configure(bg="black")
    monitor_win.overrideredirect(True)
    monitor_win.geometry(f"{DSI_WIDTH}x{DSI_HEIGHT}+{DSI_X}+{DSI_Y}")
    monitor_win.resizable(False, False)

    main_frame = tk.Frame(monitor_win, bg="black")
    main_frame.pack(fill="both", expand=True)

    # --- Sección hardware ---
    section_hw = tk.Frame(main_frame, bg="black")
    section_hw.pack(fill="both", expand=True, pady=(0,10))

    hw_canvas = tk.Canvas(section_hw, bg="black", highlightthickness=0)
    hw_canvas.pack(side="left", fill="both", expand=True)
    hw_scrollbar = tk.Scrollbar(section_hw, orient="vertical", command=hw_canvas.yview, width=30)
    hw_scrollbar.pack(side="right", fill="y")
    style_scrollbar(hw_scrollbar)
    hw_canvas.configure(yscrollcommand=hw_scrollbar.set)

    hw_inner = tk.Frame(hw_canvas, bg="black")
    hw_canvas.create_window((0,0), window=hw_inner, anchor="nw", width=DSI_WIDTH-35)

    hw_inner.bind("<Configure>", lambda e: hw_canvas.configure(scrollregion=hw_canvas.bbox("all")))

    # --- Bloques CPU, RAM, TEMP ---
    cpu_lbl, cpu_val, cpu_cvs = make_block(hw_inner, "CPU %")
    ram_lbl, ram_val, ram_cvs = make_block(hw_inner, "RAM %")
    temp_lbl, temp_val, temp_cvs = make_block(hw_inner, "TEMP °C")

    cpu_lines  = init_graph_lines(cpu_cvs, HISTORY, cpu_lbl.cget("fg"))
    ram_lines  = init_graph_lines(ram_cvs, HISTORY, ram_lbl.cget("fg"))
    temp_lines = init_graph_lines(temp_cvs, HISTORY, temp_lbl.cget("fg"))

    # --- Bloques disco ---
    disk_lbl, disk_val, disk_cvs = make_block(hw_inner, "DISK %")
    disk_lines = init_graph_lines(disk_cvs, HISTORY, disk_lbl.cget("fg"))

    disk_write_lvl, disk_write_val, disk_write_cvs = make_block(hw_inner, "DISK WRITE MB/s")
    disk_read_lvl, disk_read_val, disk_read_cvs = make_block(hw_inner, "DISK READ MB/s")
    disk_write_lines = init_graph_lines(disk_write_cvs, HISTORY, disk_write_lvl.cget("fg"))
    disk_read_lines = init_graph_lines(disk_read_cvs, HISTORY, disk_read_lvl.cget("fg"))

    # --- Sección inferior ---
    section_bottom = tk.Frame(main_frame, bg="black")
    section_bottom.pack(fill="x")
    bottom_frame = tk.Frame(section_bottom, bg="black"); bottom_frame.pack(fill="x", padx=8, pady=6)

    make_futuristic_button(bottom_frame, "Red", open_net_window, width=12, height=2).pack(side="left", padx=10)
    make_futuristic_button(bottom_frame, "USB", open_usb_window, width=12, height=2).pack(side="left", padx=10)
    make_futuristic_button(bottom_frame, "Cerrar", lambda: monitor_win.destroy(), width=12, height=2).pack(side="right", padx=10)

# ---------- Botones principales ----------
make_futuristic_button(actions, "Mostrar gráficas", open_monitor_window, width=14, height=2).pack(side="left", padx=10)
make_futuristic_button(actions, "Salir", root.destroy, width=12, height=2).pack(side="right", padx=10)

# -----------------------------
# ---------- Ventana monitor de red ----------
# -----------------------------
def open_net_window():
    global net_win
    global net_dl_lbl, net_dl_val, net_dl_cvs
    global net_ul_lbl, net_ul_val, net_ul_cvs
    global net_dl_lines, net_ul_lines
    global ips_frame, net_iface_labels, last_used_iface, last_net_io
    global net_speed_test_lbl, net_speed_test_val
    if net_win and net_win.winfo_exists():
        net_win.lift()
        return

    net_win = tk.Toplevel(root)
    net_win.title("Red")
    net_win.configure(bg="black")
    net_win.overrideredirect(True)
    net_win.geometry(f"{DSI_WIDTH}x{DSI_HEIGHT}+{DSI_X}+{DSI_Y}")
    net_win.resizable(False, False)

    main_frame = tk.Frame(net_win, bg="black")
    main_frame.pack(fill="both", expand=True)

    net_section = tk.Frame(main_frame, bg="black")
    net_section.pack(fill="both", expand=True, pady=(0, 10))

    net_canvas = tk.Canvas(net_section, bg="black", highlightthickness=0)
    net_canvas.pack(side="left", fill="both", expand=True)
    net_scrollbar = tk.Scrollbar(net_section, orient="vertical", command=net_canvas.yview, width=30)
    net_scrollbar.pack(side="right", fill="y")
    style_scrollbar(net_scrollbar)
    net_canvas.configure(yscrollcommand=net_scrollbar.set)

    net_inner = tk.Frame(net_canvas, bg="black")
    net_canvas.create_window((0,0), window=net_inner, anchor="nw", width=DSI_WIDTH-35)
    net_inner.bind("<Configure>", lambda e: net_canvas.configure(scrollregion=net_canvas.bbox("all")))

    # --- Bloques descarga/subida ---
    net_dl_lbl, net_dl_val, net_dl_cvs = make_block(net_inner, "DESCARGA MB/s")
    net_dl_lines = init_graph_lines(net_dl_cvs, HISTORY, "#00ffff")
    net_ul_lbl, net_ul_val, net_ul_cvs = make_block(net_inner, "SUBIDA MB/s")
    net_ul_lines = init_graph_lines(net_ul_cvs, HISTORY, "#ffaa00")
    # --- Bloque speedtest ---
    net_speed_test_lbl = tk.Label(
        net_inner,
        text="TEST DE VELOCIDAD",
        fg="#14611E",
        bg="black",
        font=("FiraFiraMono Nerd Font", 20, "bold")
    )
    net_speed_test_lbl.pack(anchor="w", pady=(10, 0))

    net_speed_test_val = tk.Label(
        net_inner,
        text="Esperando test...",
        fg="#00ffff",
        bg="black",
        font=("FiraFiraMono Nerd Font", 18)
    )
    net_speed_test_val.pack(anchor="w", pady=(0, 10))
    # --- Bloque de IPs ---
    ips_frame = tk.Frame(net_inner, bg="black")
    ips_frame.pack(fill="x", pady=(0, 10))
    tk.Label(ips_frame, text="Interfaces y IPs:", fg="#14611E", bg="black",
            font=("FiraFiraMono Nerd Font", 20, "bold")).pack(anchor="w")

    iface_ips = get_interfaces_ips()
    for iface, ip in iface_ips.items():
        lbl = tk.Label(ips_frame, text=f"{iface}: {ip}", fg="#00ffff", bg="black",
                       font=("FiraFiraMono Nerd Font", 18))
        lbl.pack(anchor="w")
        net_iface_labels[iface] = lbl

    # --- Sección inferior ---

    bottom = tk.Frame(net_win, bg="black")
    bottom.pack(fill="x", pady=6)
    make_futuristic_button(
        bottom,
        "Test velocidad",
        start_speedtest,
        width=16,
        height=2
    ).pack(side="left", padx=10)

    make_futuristic_button(bottom, "Cerrar", lambda: net_win.destroy(), width=12, height=2).pack(side="right", padx=10)

def open_usb_window():
    """
    Abre la ventana de dispositivos USB.
    """
    global usb_win, usb_inner_frame, usb_scroll_canvas
    global usb_devices_labels, usb_devices_buttons

    if usb_win and usb_win.winfo_exists():
        usb_win.lift()
        return

    usb_win = tk.Toplevel(root)
    usb_win.title("Dispositivos USB")
    usb_win.configure(bg="black")
    usb_win.overrideredirect(True)
    usb_win.geometry(f"{DSI_WIDTH}x{DSI_HEIGHT}+{DSI_X}+{DSI_Y}")
    usb_win.resizable(False, False)

    main_frame = tk.Frame(usb_win, bg="black")
    main_frame.pack(fill="both", expand=True)
    usb_section = tk.Frame(main_frame, bg="black")
    usb_section.pack(fill="both", expand=True, pady=(0, 10))
    # Scrollable frame
    usb_scroll_canvas = tk.Canvas(usb_section, bg="black", highlightthickness=0)
    usb_scroll_canvas.pack(side="left", fill="both", expand=True)
    usb_scrollbar = tk.Scrollbar(usb_section, orient="vertical", command=usb_scroll_canvas.yview, width=30)
    usb_scrollbar.pack(side="right", fill="y")
    style_scrollbar(usb_scrollbar)
    usb_scroll_canvas.configure(yscrollcommand=usb_scrollbar.set)

    usb_inner_frame = tk.Frame(usb_scroll_canvas, bg="black")
    usb_scroll_canvas.create_window((0,0), window=usb_inner_frame, anchor="nw", width=DSI_WIDTH-35)
    usb_inner_frame.bind("<Configure>", lambda e: usb_scroll_canvas.configure(scrollregion=usb_scroll_canvas.bbox("all")))


    # Limpiar contenedores
    usb_devices_labels.clear()
    usb_devices_buttons.clear()

    # Botón cerrar siempre abajo
    bottom_frame = tk.Frame(main_frame, bg="black")
    bottom_frame.pack(fill="x", pady=6)
    make_futuristic_button(bottom_frame, "Cerrar", usb_win.destroy, width=12, height=2).pack(side="right", padx=10)
    refresh_btn = make_futuristic_button(
        bottom_frame, "Refrescar USB", refresh_usb_devices, width=16, height=2
    )
    refresh_btn.pack(anchor="w", pady=(10, 10))

    # Carga inicial
    refresh_usb_devices()


# -----------------------------
# ---------- Update loop ----------
# -----------------------------
def update():
    global last_state, last_disk_io, last_net_io, last_used_iface, net_dynamic_max, net_idle_counter

    # --- Cargar estado ---
    try:
        st = load_state()
        if st != last_state:
            last_state = st
            mode_var.set(st.get("mode","auto"))
            tp = st.get("target_pwm")
            if isinstance(tp,int): manual_pwm.set(tp)
    except: pass

    # --- Lecturas del sistema ---
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    temp = get_cpu_temp()
    disk_io = psutil.disk_io_counters()
    disk_read = (disk_io.read_bytes - last_disk_io.read_bytes)
    disk_write = (disk_io.write_bytes - last_disk_io.write_bytes)
    last_disk_io = disk_io

    # --- Gestión PWM ---
    try:
        st = load_state()
        mode = st.get("mode","auto"); current_target = st.get("target_pwm")
        if mode=="manual":
            desired = int(current_target) if isinstance(current_target,int) else int(manual_pwm.get())
        elif mode=="auto":
            desired = compute_pwm_from_curve(temp)
        elif mode=="silent": desired=30
        elif mode=="normal": desired=128
        elif mode=="performance": desired=255
        else: desired = compute_pwm_from_curve(temp)
        desired = max(0, min(255, int(desired)))
        if desired != current_target:
            write_state({"mode":mode,"target_pwm":desired})
    except: pass

    # --- Actualizar ventana monitor si existe ---
    if monitor_win and monitor_win.winfo_exists():
        cpu_hist.append(cpu); ram_hist.append(ram); temp_hist.append(temp)
        cpu_c = level_color(cpu, CPU_WARN, CPU_CRIT)
        ram_c = level_color(ram, RAM_WARN, RAM_CRIT)
        tmp_c = level_color(temp, TEMP_WARN, TEMP_CRIT)
        recolor_lines(cpu_cvs, cpu_lines, cpu_c)
        recolor_lines(ram_cvs, ram_lines, ram_c)
        recolor_lines(temp_cvs, temp_lines, tmp_c)
        update_graph_lines(cpu_cvs, cpu_lines, cpu_hist, 100)
        update_graph_lines(ram_cvs, ram_lines, ram_hist, 100)
        update_graph_lines(temp_cvs, temp_lines, temp_hist, 85)
        cpu_lbl.config(fg=cpu_c); cpu_val.config(text=f"{cpu:4.0f} %", fg=cpu_c)
        ram_lbl.config(fg=ram_c); ram_val.config(text=f"{ram:4.0f} %", fg=ram_c)
        temp_lbl.config(fg=tmp_c); temp_val.config(text=f"{temp:4.1f} °C", fg=tmp_c)

        # --- Disco ---
        disk = psutil.disk_usage('/').percent
        disk_hist.append(disk)
        disk_c = level_color(disk, 60, 80)
        recolor_lines(disk_cvs, disk_lines, disk_c)
        update_graph_lines(disk_cvs, disk_lines, disk_hist, 100)
        disk_lbl.config(fg=disk_c)
        disk_val.config(text=f"{disk:.0f} %", fg=disk_c)

        disk_write_mb = disk_write / 1024 / 1024
        disk_read_mb = disk_read / 1024 / 1024
        disk_write_hist.append(disk_write_mb)
        disk_read_hist.append(disk_read_mb)
        write_c = level_color(disk_write_mb, 10, 50)
        read_c = level_color(disk_read_mb, 10, 50)
        recolor_lines(disk_write_cvs, disk_write_lines, write_c)
        recolor_lines(disk_read_cvs, disk_read_lines, read_c)
        update_graph_lines(disk_write_cvs, disk_write_lines, disk_write_hist, 50)
        update_graph_lines(disk_read_cvs, disk_read_lines, disk_read_hist, 50)
        disk_write_lvl.config(fg=write_c)
        disk_read_lvl.config(fg=read_c)
        disk_write_val.config(text=f"{disk_write_mb:.1f} MB/s", fg=write_c)
        disk_read_val.config(text=f"{disk_read_mb:.1f} MB/s", fg=read_c)

    if net_win and net_win.winfo_exists():
        iface, stats = get_net_io(NET_INTERFACE)

        prev = last_net_io.get(iface)
        dl, ul = safe_net_speed(stats, prev)

        last_net_io[iface] = stats
        last_used_iface = iface

        net_download_hist.append(dl)
        net_upload_hist.append(ul)

        net_dynamic_max = adaptive_scale(
            net_dynamic_max,
            list(net_download_hist) + list(net_upload_hist)
        )

        recolor_lines(net_dl_cvs, net_dl_lines, net_color(dl))
        recolor_lines(net_ul_cvs, net_ul_lines, net_color(ul))
        update_graph_lines(net_dl_cvs, net_dl_lines, net_download_hist, net_dynamic_max)
        update_graph_lines(net_ul_cvs, net_ul_lines, net_upload_hist, net_dynamic_max)

        net_dl_lbl.config(text=f"DESCARGA MB/s ({iface})", fg=net_color(dl))
        net_ul_lbl.config(text=f"SUBIDA MB/s ({iface})", fg=net_color(ul))
        net_dl_val.config(text=f"{dl:.2f} MB/s | Escala: {net_dynamic_max:.2f}", fg=net_color(dl))
        net_ul_val.config(text=f"{ul:.2f} MB/s | Escala: {net_dynamic_max:.2f}", fg=net_color(ul))
        if (
            net_win and net_win.winfo_exists()
            and net_speed_test_val is not None
        ):
            st = speedtest_result["status"]

            if st == "idle":
                net_speed_test_val.config(
                    text="Esperando test...",
                    fg="#00ffff"
                )

            elif st == "running":
                net_speed_test_val.config(
                    text="Ejecutando test...",
                    fg="#ffaa00"
                )

            elif st == "done":
                net_speed_test_val.config(
                    text=(
                        f"Ping: {speedtest_result['ping']} ms\n"
                        f"↓ {speedtest_result['download']} MB/s\n"
                        f"↑ {speedtest_result['upload']} MB/s"
                    ),
                    fg="#00ffff"
                )

            elif st == "timeout":
                net_speed_test_val.config(
                    text="Timeout en el test",
                    fg="#ff3333"
                )

            elif st == "error":
                net_speed_test_val.config(
                    text="Error ejecutando test",
                    fg="#ff3333"
                )


    root.after(UPDATE_MS, update)

# -----------------------------
# ---------- Inicio ----------
# -----------------------------
update()
root.mainloop()
