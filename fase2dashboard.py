import tkinter as tk
import psutil
import subprocess
from collections import deque

# ---------- Config ----------
UPDATE_MS = 500
HISTORY = 120   # ~60 segundos
WIDTH =800
HEIGHT = 20
CPU_WARN  = 60
CPU_CRIT  = 85
TEMP_WARN = 60
TEMP_CRIT = 75
RPM_WARN  = 1200
RAM_WARN  = 65
RAM_CRIT  = 85


# ---------- Lecturas ----------
def get_cpu_temp():
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
        return float(out.replace("temp=", "").replace("'C\n", ""))
    except:
        return 0.0

def get_fan_rpm():
    try:
        with open("/sys/class/hwmon/hwmon2/fan1_input") as f:
            return int(f.read().strip())
    except:
        return 0

# ---------- UI ----------
root = tk.Tk()

# quitar bordes
#root.overrideredirect(True)

# tamaño de la pantalla DSI (ajústalo a tu pantalla)
dsi_width = 800
dsi_height = 480

# posición en la pantalla secundaria (ajusta según tu setup)
# si la DSI es secundaria a la izquierda de HDMI grande:
x_offset = 1920 - dsi_width
y_offset = 1080

root.geometry(f"{dsi_width}x{dsi_height}+{x_offset}+{y_offset}")
# Forzar la ventana sobre todas (evita marcos de gestor de ventanas)
root.attributes("-topmost", True)
root.attributes("-fullscreen", True)  # esto ayuda en algunos drivers

# Salir con ESC
def cerrar(event=None):
    root.destroy()

root.bind("<Escape>", cerrar)
root.bind("<Control-q>", cerrar)  # opción alternativa para salir

# Ejemplo de fondo negro para asegurarse que no haya marco
root.configure(bg="black")

scale_factor = dsi_height / 480  # ejemplo basado en altura
font = ("FiraFiraMono Nerd Font", int(16*scale_factor))
font_value = ("FiraFiraMono Nerd Font", int(22*scale_factor), "bold")


# ---------- Historias ----------
cpu_hist  = deque([0]*HISTORY, maxlen=HISTORY)
temp_hist = deque([0]*HISTORY, maxlen=HISTORY)
rpm_hist  = deque([0]*HISTORY, maxlen=HISTORY)
ram_hist = deque([0]*HISTORY, maxlen=HISTORY)

# ---------- Helpers ----------
def draw_graph(canvas, data, max_val, color):
    canvas.delete("all")
    step = WIDTH / (len(data)-1)

    points = []
    for i, val in enumerate(data):
        x = i * step
        y = HEIGHT - (val / max_val) * HEIGHT
        points.append((x, y))

    for i in range(len(points)-1):
        canvas.create_line(
            points[i][0], points[i][1],
            points[i+1][0], points[i+1][1],
            fill=color, width=2
        )
        
def level_color(value, warn, crit):
    if value < warn:
        return "#00ff00"   # verde
    elif value < crit:
        return "#ffaa00"   # naranja
    else:
        return "#ff3333"   # rojo


# ---------- Layout ----------
frame = tk.Frame(root, bg="black")
frame.pack(padx=10, pady=10)

cpu_lbl = tk.Label(frame, text="CPU %", fg="white", bg="black", font=font)
cpu_lbl.pack(anchor="w")
cpu_value = tk.Label(frame, fg="white", bg="black", font=font_value)
cpu_value.pack(anchor="e")
cpu_canvas = tk.Canvas(frame, width=WIDTH, height=HEIGHT, bg="black", highlightthickness=0)
cpu_canvas.pack()

ram_lbl = tk.Label(frame, text="RAM %", fg="white", bg="black", font=font)
ram_lbl.pack(anchor="w", pady=(10,0))
ram_value = tk.Label(frame, fg="white", bg="black", font=font_value)
ram_value.pack(anchor="e")
ram_canvas = tk.Canvas(frame, width=WIDTH, height=HEIGHT, bg="black", highlightthickness=0)
ram_canvas.pack()

temp_lbl = tk.Label(frame, text="TEMP °C", fg="white", bg="black", font=font)
temp_lbl.pack(anchor="w", pady=(10,0))
temp_value = tk.Label(frame, fg="white", bg="black", font=font_value)
temp_value.pack(anchor="e")
temp_canvas = tk.Canvas(frame, width=WIDTH, height=HEIGHT, bg="black", highlightthickness=0)
temp_canvas.pack()

rpm_lbl = tk.Label(frame, text="FAN RPM", fg="white", bg="black", font=font)
rpm_lbl.pack(anchor="w", pady=(10,0))
rpm_value = tk.Label(frame, fg="white", bg="black", font=font_value)
rpm_value.pack(anchor="e")
rpm_canvas = tk.Canvas(frame, width=WIDTH, height=HEIGHT, bg="black", highlightthickness=0)
rpm_canvas.pack()



# ---------- Update ----------
def update():
    cpu  = psutil.cpu_percent()
    ram  = psutil.virtual_memory().percent
    temp = get_cpu_temp()
    rpm  = get_fan_rpm()

    cpu_hist.append(cpu)
    ram_hist.append(ram)
    temp_hist.append(temp)
    rpm_hist.append(rpm)

    cpu_col  = level_color(cpu,  CPU_WARN,  CPU_CRIT)
    ram_col  = level_color(ram,  RAM_WARN,  RAM_CRIT)
    temp_col = level_color(temp, TEMP_WARN, TEMP_CRIT)
    rpm_col  = "#00aaff" if rpm > RPM_WARN else "#ff3333"

    draw_graph(cpu_canvas,  cpu_hist, 100,  cpu_col)
    draw_graph(ram_canvas,  ram_hist, 100,  ram_col)
    draw_graph(temp_canvas, temp_hist, 85,   temp_col)
    draw_graph(rpm_canvas,  rpm_hist, 4000, rpm_col)

    cpu_lbl.config(fg=cpu_col)
    ram_lbl.config(fg=ram_col)
    temp_lbl.config(fg=temp_col)
    rpm_lbl.config(fg=rpm_col)
    cpu_value.config(text=f"{cpu:4.0f} %", fg=cpu_col)
    ram_value.config(text=f"{ram:4.0f} %", fg=ram_col)
    temp_value.config(text=f"{temp:4.1f} °C", fg=temp_col)
    rpm_value.config(text=f"{rpm:4d}", fg=rpm_col)

    root.after(UPDATE_MS, update)


update()
root.mainloop()
