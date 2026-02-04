import tkinter as tk
import psutil
import subprocess
from collections import deque
import json
import os
import logging
from tkinter import messagebox

# Logging to file for diagnostics
#logging.basicConfig(filename='/home/jalivur/Documents/proyectyopantallas/fase2dashboard.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

STATE_FILE = "/home/jalivur/Documents/proyectyopantallas/fan_state.json"
CURVE_FILE = "/home/jalivur/Documents/proyectyopantallas/fan_curve.json"

# DSI display configuration (800x480) placed at bottom-right of a 1920x1080 HDMI
DSI_WIDTH = 800
DSI_HEIGHT = 480
# DSI_X/DSI_Y are computed at startup based on current screen resolution
DSI_X = 1920 - DSI_WIDTH
DSI_Y = 1080 - DSI_HEIGHT

# ---------- Config ----------
UPDATE_MS = 1000   
HISTORY = 120
WIDTH = 800
HEIGHT = 20

CPU_WARN  = 60
CPU_CRIT  = 85
TEMP_WARN = 60
TEMP_CRIT = 75
RAM_WARN  = 65
RAM_CRIT  = 85

# --- FUNCIONES HELPER PARA ESTILO FUTURISTA ---
def style_radiobutton(rb, fg="#00ffff", bg="#111111", hover_fg="#ffffff"):
    rb.config(
        fg=fg,
        bg=bg,
        selectcolor=bg,  # quitar el color por defecto
        activeforeground=fg,
        activebackground=bg,
        font=("FiraFiraMono Nerd Font", 14, "bold"),
        indicatoron=True  # mantiene el circulito
    )
    
    # Hover glow
    def on_enter(e): rb.config(fg=hover_fg)
    def on_leave(e): rb.config(fg=fg)
    rb.bind("<Enter>", on_enter)
    rb.bind("<Leave>", on_leave)

def make_futuristic_button(parent, text, command=None, width=12, height=2):
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        fg="#00ffff",
        bg="#111111",
        activebackground="#222222",
        activeforeground="#00ffff",
        borderwidth=2,
        relief="ridge",
        width=width,
        height=height,
        font=("FiraFiraMono Nerd Font", 14, "bold")
    )
    def on_enter(e): btn.config(fg="#00ffff", bg="#222222")
    def on_leave(e): btn.config(fg="#00ffff", bg="#111111")
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn

def style_slider(slider, color="#00ffff"):
    slider.config(
        troughcolor="#222222",
        sliderrelief="flat",
        bd=0,
        highlightthickness=0,
        fg=color,
        bg="#111111",
        activebackground=color
    )

def style_scrollbar(sb, color="#00ffff"):
    sb.config(
        troughcolor="#111111",
        bg=color,
        activebackground=color,
        highlightthickness=0,
        relief="flat"
    )

def add_hover_glow(slider, normal="#00ffff", hover="#ffffff"):
    def enter(e): slider.config(fg=hover, activebackground=hover)
    def leave(e): slider.config(fg=normal, activebackground=normal)
    slider.bind("<Enter>", enter)
    slider.bind("<Leave>", leave)

# ---------- Utils ----------
def write_state(data):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, STATE_FILE)

def load_state():
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"mode": "auto", "target_pwm": None}
            return {
                "mode": data.get("mode", "auto"),
                "target_pwm": data.get("target_pwm")
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"mode": "auto", "target_pwm": None}


def load_curve():
    try:
        with open(CURVE_FILE) as f:
            data = json.load(f)
            pts = data.get("points", [])
            if not isinstance(pts, list):
                return [
                    {"temp": 40, "pwm": 100},
                    {"temp": 50, "pwm": 100},
                    {"temp": 60, "pwm": 100},
                    {"temp": 70, "pwm": 63},
                    {"temp": 80, "pwm": 81}
                ]
            sanitized = []
            for p in pts:
                try:
                    t = int(p.get("temp", 0))
                except Exception:
                    t = 0
                try:
                    pwm = int(p.get("pwm", 0))
                except Exception:
                    pwm = 0
                pwm = max(0, min(255, pwm))
                sanitized.append({"temp": t, "pwm": pwm})
            if not sanitized:
                return [
                    {"temp": 40, "pwm": 100},
                    {"temp": 50, "pwm": 100},
                    {"temp": 60, "pwm": 100},
                    {"temp": 70, "pwm": 63},
                    {"temp": 80, "pwm": 81}
                ]
            return sorted(sanitized, key=lambda x: x["temp"])
    except (FileNotFoundError, json.JSONDecodeError):
        # Return a sensible default curve to avoid crashes
        return [
            {"temp": 40, "pwm": 100},
            {"temp": 50, "pwm": 100},
            {"temp": 60, "pwm": 100},
            {"temp": 70, "pwm": 63},
            {"temp": 80, "pwm": 81}
        ]

def compute_pwm_from_curve(temp):
    curve = sorted(load_curve(), key=lambda p: p["temp"])
    if not curve:
        return 0
    # Below lowest point -> use lowest pwm
    if temp <= curve[0]["temp"]:
        return int(curve[0]["pwm"])
    # Above highest point -> use highest pwm
    if temp >= curve[-1]["temp"]:
        return int(curve[-1]["pwm"])
    for i in range(len(curve)-1):
        t1, p1 = curve[i]["temp"], curve[i]["pwm"]
        t2, p2 = curve[i+1]["temp"], curve[i+1]["pwm"]
        if t1 <= temp <= t2:
            # guard against identical temperatures
            if t2 == t1:
                return int(p1)
            r = (temp - t1) / (t2 - t1)
            return int(p1 + r * (p2 - p1))
    # Fallback
    return int(curve[-1]["pwm"])

# ---------- Sensors ----------
def get_cpu_temp():
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
        return float(out.replace("temp=", "").replace("'C\n", ""))
    except:
        return 0.0

# ---------- UI root ----------
root = tk.Tk()
root.title("System Monitor")
root.configure(bg="black")

# QUITAR MARCO Y BARRA DE TÍTULO
root.overrideredirect(True)

# ======================================================
# MAIN LAYOUT (800x480 friendly)
# ======================================================
main = tk.Frame(root, bg="black")
main.pack(fill="both", expand=True)

top = tk.Frame(main, bg="black")
top.pack(fill="both", expand=True, padx=10, pady=(10, 6))

bottom = tk.Frame(main, bg="black")
bottom.pack(fill="x", padx=10, pady=(0, 8))

# Attempt to detect the actual DSI monitor geometry via xrandr (if available) and fall back to simple bottom-right placement

def detect_dsi_geometry():
    try:
        out = subprocess.check_output(["xrandr", "--query"], stderr=subprocess.DEVNULL).decode()
        for line in out.splitlines():
            if " connected " in line:
                parts = line.split()
                for tok in parts:
                    if "+" in tok and "x" in tok:
                        # tok looks like '800x480+1120+600'
                        try:
                            res, pos = tok.split("+", 1)
                            w, h = res.split("x")
                            x, y = pos.split("+")
                            w = int(w); h = int(h); x = int(x); y = int(y)
                            if w == DSI_WIDTH and h == DSI_HEIGHT:
                                logging.info(f"Detected DSI geometry via xrandr: {w}x{h}+{x}+{y}")
                                return x, y
                        except Exception:
                            pass
        return None
    except Exception:
        return None

# Position the window on the DSI display (bottom-right of the main screen)
try:
    pos = detect_dsi_geometry()
    if pos:
        DSI_X, DSI_Y = pos
    else:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        DSI_X = max(0, screen_w - DSI_WIDTH)
        DSI_Y = max(0, screen_h - DSI_HEIGHT)
    root.geometry(f"{DSI_WIDTH}x{DSI_HEIGHT}+{DSI_X}+{DSI_Y}")
    root.resizable(False, False)
    logging.info(f"Placing window at {DSI_X},{DSI_Y} (DSI size {DSI_WIDTH}x{DSI_HEIGHT})")
except Exception:
    logging.exception("Failed to position window on DSI display")

font = ("FiraFiraMono Nerd Font", 16)
font_value = ("FiraFiraMono Nerd Font", 22, "bold")

# ---------- Graph helpers ----------
def draw_graph(canvas, data, max_val, color):
    canvas.delete("all")
    step = WIDTH / (len(data)-1)
    pts = []
    for i, v in enumerate(data):
        x = i * step
        y = HEIGHT - (v / max_val) * HEIGHT
        pts.append((x, y))
    for i in range(len(pts)-1):
        canvas.create_line(*pts[i], *pts[i+1], fill=color, width=2)

def level_color(v, w, c):
    if v < w: return "#00ff00"
    if v < c: return "#ffaa00"
    return "#ff3333"


def make_block(parent, title):
    lbl = tk.Label(parent, text=title, fg="white", bg="black", font=font)
    lbl.pack(anchor="w")
    val = tk.Label(parent, fg="white", bg="black", font=font_value)
    val.pack(anchor="e")
    cvs = tk.Canvas(parent, width=WIDTH, height=HEIGHT, bg="black", highlightthickness=0)
    cvs.pack()
    return lbl, val, cvs
# ---------- SECCION SISTEMA ----------
system_frame = tk.LabelFrame(
    top,
    text="Sistema",
    fg="white",
    bg="black",
    labelanchor="nw",
    padx=10,
    pady=8
)
system_frame.pack(fill="both", expand=True)

cpu_lbl, cpu_val, cpu_cvs = make_block(system_frame, "CPU %")
ram_lbl, ram_val, ram_cvs = make_block(system_frame, "RAM %")
temp_lbl, temp_val, temp_cvs = make_block(system_frame, "TEMP °C")

cpu_hist = deque([0]*HISTORY, maxlen=HISTORY)
ram_hist = deque([0]*HISTORY, maxlen=HISTORY)
temp_hist = deque([0]*HISTORY, maxlen=HISTORY)



# ---------- CONTROL WINDOW ----------
control_win = None
mode_var = tk.StringVar(value="auto")
manual_pwm = tk.IntVar(value=128)
curve_vars = []
last_state = None



def open_control_window():
    global control_win, curve_vars

    if control_win and control_win.winfo_exists():
        control_win.lift()
        return

    control_win = tk.Toplevel(root)
    control_win.title("Fan Control")
    control_win.configure(bg="black")

    # QUITAR MARCO Y BARRA DE TÍTULO
    control_win.overrideredirect(True)

    # Tamaño fijo
    CTRL_W = 800
    CTRL_H = 480
    control_win.geometry(f"{CTRL_W}x{CTRL_H}")

    # MUY IMPORTANTE: no transient, no topmost todavía
    control_win.update_idletasks()

    def place_control():
        x = root.winfo_x()
        y = root.winfo_y()
        control_win.geometry(f"{CTRL_W}x{CTRL_H}+{x}+{y}")

        # AHORA sí
        control_win.transient(root)
        control_win.lift()
        control_win.focus_force()

    # Ejecutar DESPUÉS de que el WM haya hecho lo suyo
    control_win.after_idle(place_control)


    control_win.resizable(False, False)

    # ======================================================
    # CONTENEDOR PRINCIPAL
    # ======================================================
    main = tk.Frame(control_win, bg="black")
    main.pack(fill="both", expand=True)

    top = tk.Frame(main, bg="black")
    top.pack(fill="both", expand=True, padx=6, pady=(6, 2))
    
    bottom = tk.Frame(main, bg="black")
    bottom.pack(fill="x", padx=8, pady=(0, 4))

    # ======================================================
    # SECCIÓN MODO
    # ======================================================
    mode_frame = tk.LabelFrame(
        top, text="Modo",
        fg="white", bg="black",
        labelanchor="nw", padx=10, pady=8
    )
    mode_frame.pack(fill="x", pady=4)

    modes_row = tk.Frame(mode_frame, bg="black")
    modes_row.pack(anchor="w")

    def set_mode(mode):
        mode_var.set(mode)
        write_state({"mode": mode, "target_pwm": None})

    for m in ("auto", "silent", "normal", "performance", "manual"):
        Radiobutton = tk.Radiobutton(
            modes_row,
            text=m.upper(),
            variable=mode_var,
            value=m,
            command=lambda m=m: set_mode(m),
            bg="black",
            fg="white",
            selectcolor="black"
        )
        Radiobutton.pack(side="left", padx=6)
        style_radiobutton(Radiobutton)

    # ======================================================
    # SECCIÓN MANUAL PWM
    # ======================================================
    manual_frame = tk.LabelFrame(
        top, text="Control manual PWM",
        fg="white", bg="black",
        labelanchor="nw", padx=10, pady=8
    )
    manual_frame.pack(fill="x", pady=4)

    manual_row = tk.Frame(manual_frame, bg="black")
    manual_row.pack(fill="x")

    manual_scale = tk.Scale(
        manual_row,
        from_=0, to=255,
        orient="horizontal",
        variable=manual_pwm,
        bg="black",
        fg="white",
        highlightthickness=0,
        length=560,
        sliderlength=36,
        width=30
    )
    manual_scale.pack(side="left", fill="x", expand=True)
    style_slider(manual_scale)
    manual_lbl = tk.Label(
        manual_row,
        textvariable=manual_pwm,
        fg="white",
        bg="black",
        width=4,
        font=("FiraFiraMono Nerd Font", 20, "bold")
    )
    manual_lbl.pack(side="left", padx=12)

    def on_manual_pwm(val):
        if mode_var.get() != "manual":
            return
        v = max(0, min(255, int(float(val))))
        manual_pwm.set(v)
        write_state({"mode": "manual", "target_pwm": v})

    manual_scale.configure(command=on_manual_pwm)

    # ======================================================
    # SECCIÓN CURVA (SCROLL)
    # ======================================================
    curve_frame = tk.LabelFrame(
        top, text="Curva térmica",
        fg="white", bg="black",
        labelanchor="nw", padx=10, pady=8
    )
    curve_frame.pack(fill="both", expand=True, pady=4)

    canvas = tk.Canvas(curve_frame, bg="black", highlightthickness=0, height=180)
    canvas.pack(side="left", fill="both", expand=True)

    scrollbar = tk.Scrollbar(curve_frame, orient="vertical", command=canvas.yview, width=30)
    scrollbar.pack(side="right", fill="y")
    canvas.configure(yscrollcommand=scrollbar.set)
    style_scrollbar(scrollbar)
    
    curve_inner = tk.Frame(canvas, bg="black")
    canvas.create_window((0, 0), window=curve_inner, anchor="nw")

    curve_inner.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    curve_vars.clear()

    for p in load_curve():
        row = tk.Frame(curve_inner, bg="black")
        row.pack(fill="x", pady=6)

        tk.Label(
            row,
            text=f'{p["temp"]}°C',
            fg="white",
            bg="black",
            width=6
        ).pack(side="left")

        var = tk.IntVar(value=p["pwm"])

        val_lbl = tk.Label(
            row,
            textvariable=var,
            fg="white",
            bg="black",
            width=4
        )
        val_lbl.pack(side="right")

        scale = tk.Scale(
            row,
            from_=0, to=255,
            orient="horizontal",
            variable=var,
            bg="black",
            fg="white",
            highlightthickness=0,
            length=520,
            sliderlength=28,
            width=30
        )
        scale.pack(side="left", fill="x", expand=True, padx=6)
        style_slider(scale)
        curve_vars.append((p["temp"], var))

    # ======================================================
    # SECCIÓN ACCIONES
    # ======================================================
    actions = tk.Frame(bottom, bg="black")
    actions.pack(fill="x", pady=4)

    def save_curve():
        data = {
            "points": [
                {"temp": t, "pwm": v.get()}
                for t, v in curve_vars
            ]
        }
        with open(CURVE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        messagebox.showinfo("Guardado", "Curva guardada correctamente")

    def restore_default():
        default = [
            {"temp": 40, "pwm": 100},
            {"temp": 50, "pwm": 130},
            {"temp": 60, "pwm": 160},
            {"temp": 70, "pwm": 180},
            {"temp": 80, "pwm": 255}
        ]
        with open(CURVE_FILE, "w") as f:
            json.dump({"points": default}, f, indent=2)
        control_win.destroy()
        open_control_window()


    make_futuristic_button(actions, "Guardar curva", save_curve, width=16, height=2).pack(side="left", padx=10)
    make_futuristic_button(actions, "Restaurar por defecto", restore_default, width=16, height=2).pack(side="left", padx=10)
    make_futuristic_button(actions, "Cerrar", on_control_close, width=12, height=2).pack(side="right", padx=10)

def on_control_close():
    # Remove any global pointer logging and topmost attribute before closing
    try:
        control_win.unbind_all("<Button-1>")
    except Exception:
        pass
    try:
        control_win.attributes("-topmost", False)
    except Exception:
        pass
    try:
        control_win.destroy()
    except Exception:
        pass
    # Reapply DSI positioning in case window moved
    try:
        root.geometry(f"{DSI_WIDTH}x{DSI_HEIGHT}+{DSI_X}+{DSI_Y}")
    except Exception:
        pass
    





# ---------- Toolbar ----------
actions = tk.LabelFrame(
    bottom,
    text="Acciones",
    fg="white",
    bg="black",
    labelanchor="nw",
    padx=10,
    pady=6
)
actions.pack(fill="x")
"""
tk.Button(
    actions,
    text="Control ventiladores",
    command=open_control_window,
    width=20,
    height=2
).pack(side="left", padx=10)

tk.Button(
    actions,
    text="Salir",
    command=root.destroy,
    width=12,
    height=2
).pack(side="right", padx=10)
"""
# Ahora:
make_futuristic_button(actions, "Control ventiladores", open_control_window, width=20, height=2).pack(side="left", padx=10)
make_futuristic_button(actions, "Salir", root.destroy, width=12, height=2).pack(side="right", padx=10)



# ---------- Update ----------
def update():
    global last_state

    # Sync state from file and apply to UI if changed
    try:
        st = load_state()
        if st != last_state:
            logging.info(f"State changed: {st}")
            last_state = st
            mode_var.set(st.get("mode", "auto"))
            tp = st.get("target_pwm")
            if isinstance(tp, int):
                manual_pwm.set(tp)
    except Exception:
        logging.exception("Failed to sync state")

    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    temp = get_cpu_temp()

    # Determine desired PWM according to mode and temp
    try:
        st = load_state()
        mode = st.get("mode", "auto")
        current_target = st.get("target_pwm")
        if mode == "manual":
            desired = int(current_target) if isinstance(current_target, int) else int(manual_pwm.get())
        elif mode == "auto":
            desired = compute_pwm_from_curve(temp)
        elif mode == "silent":
            desired = 30
        elif mode == "normal":
            desired = 128
        elif mode == "performance":
            desired = 255
        else:
            desired = compute_pwm_from_curve(temp)
        desired = max(0, min(255, int(desired)))
        if desired != current_target:
            logging.info(f"Applying desired PWM {desired} for mode {mode} (temp {temp})")
            write_state({"mode": mode, "target_pwm": desired})
    except Exception:
        logging.exception("Failed to compute/apply desired PWM")

    cpu_hist.append(cpu)
    ram_hist.append(ram)
    temp_hist.append(temp)

    cpu_c = level_color(cpu, CPU_WARN, CPU_CRIT)
    ram_c = level_color(ram, RAM_WARN, RAM_CRIT)
    tmp_c = level_color(temp, TEMP_WARN, TEMP_CRIT)

    draw_graph(cpu_cvs, cpu_hist, 100, cpu_c)
    draw_graph(ram_cvs, ram_hist, 100, ram_c)
    draw_graph(temp_cvs, temp_hist, 85, tmp_c)

    cpu_lbl.config(fg=cpu_c); cpu_val.config(text=f"{cpu:4.0f} %", fg=cpu_c)
    ram_lbl.config(fg=ram_c); ram_val.config(text=f"{ram:4.0f} %", fg=ram_c)
    temp_lbl.config(fg=tmp_c); temp_val.config(text=f"{temp:4.1f} °C", fg=tmp_c)


    root.after(UPDATE_MS, update)

update()
root.mainloop()

