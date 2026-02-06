import tkinter as tk
import psutil
import subprocess
from collections import deque
import json
import os
import logging

# ---------- Archivos ----------
STATE_FILE = "/home/jalivur/Documents/proyectyopantallas/fan_state.json"
CURVE_FILE = "/home/jalivur/Documents/proyectyopantallas/fan_curve.json"

# ---------- DSI display config ----------
DSI_WIDTH = 800
DSI_HEIGHT = 480
DSI_X = 1920 - DSI_WIDTH
DSI_Y = 1080 - DSI_HEIGHT

# ---------- Config ----------
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
# ---------- Helper style ----------
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
    popup.geometry("300x150+{}+{}".format(parent.winfo_x()+250, parent.winfo_y()+180))
    tk.Label(popup, text=title, fg="#00ffff", bg="#111111", font=("FiraFiraMono Nerd Font",16,"bold")).pack(pady=(10,0))
    tk.Label(popup, text=text, fg="white", bg="#111111", font=("FiraFiraMono Nerd Font",14)).pack(pady=(10,10))
    tk.Button(popup, text="OK", fg="#00ffff", bg="#111111", command=popup.destroy, width=10,height=10).pack(pady=(0,10))
    popup.lift(); popup.focus_force(); popup.grab_set()

# ---------- Utils ----------
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

# ---------- Sensors ----------
def get_cpu_temp():
    try:
        out=subprocess.check_output(["vcgencmd","measure_temp"]).decode()
        return float(out.replace("temp=","").replace("'C\n",""))
    except:
        return 0.0

# ---------- Graph helpers ----------
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

def get_net_io(interface=None):
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
    global net_idle_counter

    if not data:
        return current_max * 0.5

    peak = max(data)

    # --- Subir rápido ---
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
    new_val = current_max * 0.97
    return max(new_val, NET_MIN_SCALE)


# ---------- Variables globales ----------
root = tk.Tk()
root.title("Fan Control")
root.configure(bg="black")
root.overrideredirect(True)

# ---------- Posicionamiento DSI para root ----------
def detect_dsi_geometry():
    try:
        out=subprocess.check_output(["xrandr","--query"],stderr=subprocess.DEVNULL).decode()
        for line in out.splitlines():
            if " connected " in line:
                parts=line.split()
                for tok in parts:
                    if "+" in tok and "x" in tok:
                        try:
                            res,pos=tok.split("+",1)
                            w,h=map(int,res.split("x"))
                            x,y=map(int,pos.split("+"))
                            if w==DSI_WIDTH and h==DSI_HEIGHT:
                                return x,y
                        except: pass
        return None
    except: return None

pos = detect_dsi_geometry()
if pos:
    DSI_X,DSI_Y=pos
else:
    screen_w=root.winfo_screenwidth()
    screen_h=root.winfo_screenheight()
    DSI_X = max(0, screen_w - DSI_WIDTH)
    DSI_Y = max(0, screen_h - DSI_HEIGHT)

CTRL_W, CTRL_H = 800,480
root.geometry(f"{CTRL_W}x{CTRL_H}+{DSI_X}+{DSI_Y}")
root.resizable(False,False)

mode_var = tk.StringVar(value="auto")
manual_pwm = tk.IntVar(value=128)
curve_vars=[]
last_state=None
monitor_win=None
cpu_hist=deque([0]*HISTORY,maxlen=HISTORY)
ram_hist=deque([0]*HISTORY,maxlen=HISTORY)
temp_hist=deque([0]*HISTORY,maxlen=HISTORY)
cpu_lines  = []
ram_lines  = []
temp_lines = []
#----Variables para ventana monitor de red----
net_download_hist = deque([0]*HISTORY, maxlen=HISTORY) 
net_upload_hist = deque([0]*HISTORY, maxlen=HISTORY) 
last_used_iface = None

last_net_io = psutil.net_io_counters()
last_net_pernic = psutil.net_io_counters(pernic=True)
net_win = None
net_dynamic_max = 1.0
net_idle_counter = 0

net_dl_lbl = net_dl_val = net_dl_cvs = None
net_ul_lbl = net_ul_val = net_ul_cvs = None
net_dl_lines = []
net_ul_lines = []



# ---------- Layout principal ----------
main = tk.Frame(root,bg="black"); main.pack(fill="both",expand=True)
top = tk.Frame(main,bg="black"); top.pack(fill="both",expand=True,padx=6,pady=(6,2))
bottom = tk.Frame(main,bg="black"); bottom.pack(fill="x",padx=8,pady=(0,4))

# ---------- Modo ----------
mode_frame = tk.LabelFrame(top,text="Modo",fg="white",bg="black",labelanchor="nw",padx=10,pady=8)
mode_frame.pack(fill="x",pady=4)
modes_row = tk.Frame(mode_frame,bg="black"); modes_row.pack(anchor="w")

def set_mode(mode):
    mode_var.set(mode)
    write_state({"mode":mode,"target_pwm":None})

for m in ("auto","silent","normal","performance","manual"):
    rb=tk.Radiobutton(modes_row,text=m.upper(),variable=mode_var,value=m,command=lambda m=m:set_mode(m),bg="black",fg="white",selectcolor="black")
    rb.pack(side="left",padx=6)
    style_radiobutton(rb)

# ---------- PWM Manual ----------
manual_frame = tk.LabelFrame(top,text="Control manual PWM",fg="white",bg="black",labelanchor="nw",padx=10,pady=8)
manual_frame.pack(fill="x",pady=4)
manual_row=tk.Frame(manual_frame,bg="black"); manual_row.pack(fill="x")
manual_scale=tk.Scale(manual_row,from_=0,to=255,orient="horizontal",variable=manual_pwm,bg="black",fg="white",highlightthickness=0,length=560,sliderlength=36,width=30)
manual_scale.pack(side="left",fill="x",expand=True)
style_slider(manual_scale)
manual_lbl=tk.Label(manual_row,textvariable=manual_pwm,fg="white",bg="black",width=4,font=("FiraFiraMono Nerd Font",20,"bold"))
manual_lbl.pack(side="left",padx=12)
manual_scale.configure(command=lambda val: write_state({"mode":"manual","target_pwm":max(0,min(255,int(float(val))))}) if mode_var.get()=="manual" else None)

# ---------- Curva ----------
curve_frame = tk.LabelFrame(top,text="Curva térmica",fg="white",bg="black",labelanchor="nw",padx=10,pady=8)
curve_frame.pack(fill="both",expand=True,pady=4)
canvas=tk.Canvas(curve_frame,bg="black",highlightthickness=0,height=180); canvas.pack(side="left",fill="both",expand=True)
scrollbar=tk.Scrollbar(curve_frame,orient="vertical",command=canvas.yview,width=30); scrollbar.pack(side="right",fill="y")
canvas.configure(yscrollcommand=scrollbar.set)
style_scrollbar(scrollbar)
curve_inner=tk.Frame(canvas,bg="black"); canvas.create_window((0,0),window=curve_inner,anchor="nw")
curve_inner.bind("<Configure>",lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
curve_vars.clear()
for p in load_curve():
    row=tk.Frame(curve_inner,bg="black"); row.pack(fill="x",pady=6)
    tk.Label(row,text=f'{p["temp"]}°C',fg="white",bg="black",width=6).pack(side="left")
    var=tk.IntVar(value=p["pwm"])
    tk.Label(row,textvariable=var,fg="white",bg="black",width=4).pack(side="right")
    scale=tk.Scale(row,from_=0,to=255,orient="horizontal",variable=var,bg="black",fg="white",highlightthickness=0,length=520,sliderlength=28,width=30)
    scale.pack(side="left",fill="x",expand=True,padx=6)
    style_slider(scale)
    curve_vars.append((p["temp"],var))

# ---------- Actions ----------
actions = tk.Frame(bottom,bg="black"); actions.pack(fill="x",pady=4)
def save_curve():
    data={"points":[{"temp":t,"pwm":v.get()} for t,v in curve_vars]}
    with open(CURVE_FILE,"w") as f: json.dump(data,f,indent=2)
    custom_msgbox(root,"Curva guardada correctamente","Guardado")
def restore_default():
    default=[{"temp":40,"pwm":100},{"temp":50,"pwm":130},{"temp":60,"pwm":160},{"temp":70,"pwm":180},{"temp":80,"pwm":255}]
    with open(CURVE_FILE,"w") as f: json.dump({"points":default},f,indent=2)
    custom_msgbox(root,"Curva restaurada por defecto","Restaurado")

make_futuristic_button(actions,"Guardar curva",save_curve,width=16,height=2).pack(side="left",padx=10)
make_futuristic_button(actions,"Restaurar por defecto",restore_default,width=18,height=2).pack(side="left",padx=10)

# ---------- Ventana monitor placa ----------
def open_monitor_window():
    global monitor_win,cpu_lbl,cpu_val,cpu_cvs,ram_lbl,ram_val,ram_cvs,temp_lbl,temp_val,temp_cvs
    if monitor_win and monitor_win.winfo_exists(): monitor_win.lift(); return
    monitor_win=tk.Toplevel(root)
    monitor_win.title("System Monitor")
    monitor_win.configure(bg="black")
    monitor_win.overrideredirect(True)
    monitor_win.geometry(f"{DSI_WIDTH}x{DSI_HEIGHT}+{DSI_X}+{DSI_Y}")
    monitor_win.resizable(False,False)
    main_frame=tk.Frame(monitor_win,bg="black"); main_frame.pack(fill="both",expand=True)
    cpu_lbl,cpu_val,cpu_cvs=make_block(main_frame,"CPU %")
    ram_lbl,ram_val,ram_cvs=make_block(main_frame,"RAM %")
    temp_lbl,temp_val,temp_cvs=make_block(main_frame,"TEMP °C")
    global cpu_lines, ram_lines, temp_lines
    cpu_lines  = init_graph_lines(cpu_cvs, HISTORY, cpu_lbl.cget("fg"))
    ram_lines  = init_graph_lines(ram_cvs, HISTORY, ram_lbl.cget("fg"))
    temp_lines = init_graph_lines(temp_cvs, HISTORY, temp_lbl.cget("fg"))



    bottom_frame=tk.Frame(monitor_win,bg="black"); bottom_frame.pack(fill="x",padx=8,pady=6)
    make_futuristic_button(
        bottom_frame, "Red", open_net_window, width=12, height=2
    ).pack(side="left", padx=10)
    make_futuristic_button(bottom_frame,"Cerrar",lambda: monitor_win.destroy(),width=12,height=2).pack(side="right",padx=10)

make_futuristic_button(actions,"Mostrar gráficas",open_monitor_window,width=14,height=2).pack(side="left",padx=10)
make_futuristic_button(actions,"Salir",root.destroy,width=12,height=2).pack(side="right",padx=10)

#---------- Ventana monitor de red ----------
def open_net_window():
    global net_win
    global net_dl_lbl, net_dl_val, net_dl_cvs
    global net_ul_lbl, net_ul_val, net_ul_cvs
    global net_dl_lines, net_ul_lines

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
    main_frame.pack(fill="both", expand=True, padx=8, pady=8)

    # Descarga
    net_dl_lbl, net_dl_val, net_dl_cvs = make_block(main_frame, "DESCARGA MB/s")
    net_dl_lines = init_graph_lines(net_dl_cvs, HISTORY, "#00ffff")

    # Subida
    net_ul_lbl, net_ul_val, net_ul_cvs = make_block(main_frame, "SUBIDA MB/s")
    net_ul_lines = init_graph_lines(net_ul_cvs, HISTORY, "#ffaa00")

    bottom = tk.Frame(net_win, bg="black")
    bottom.pack(fill="x", pady=6)

    make_futuristic_button(
        bottom, "Cerrar", lambda: net_win.destroy(), width=12, height=2
    ).pack(side="right", padx=10)


# ---------- Update loop ----------
def update():
    global last_state
    try:
        st=load_state()
        if st!=last_state:
            last_state=st
            mode_var.set(st.get("mode","auto"))
            tp=st.get("target_pwm")
            if isinstance(tp,int): manual_pwm.set(tp)
    except: pass

    cpu=psutil.cpu_percent(); ram=psutil.virtual_memory().percent; temp=get_cpu_temp()

    try:
        st=load_state()
        mode=st.get("mode","auto"); current_target=st.get("target_pwm")
        if mode=="manual": desired=int(current_target) if isinstance(current_target,int) else int(manual_pwm.get())
        elif mode=="auto": desired=compute_pwm_from_curve(temp)
        elif mode=="silent": desired=30
        elif mode=="normal": desired=128
        elif mode=="performance": desired=255
        else: desired=compute_pwm_from_curve(temp)
        desired=max(0,min(255,int(desired)))
        if desired!=current_target:
            write_state({"mode":mode,"target_pwm":desired})
    except: pass

    if monitor_win and monitor_win.winfo_exists():
        cpu_hist.append(cpu); ram_hist.append(ram); temp_hist.append(temp)
        cpu_c=level_color(cpu,CPU_WARN,CPU_CRIT)
        ram_c=level_color(ram,RAM_WARN,RAM_CRIT)
        tmp_c=level_color(temp,TEMP_WARN,TEMP_CRIT)
        recolor_lines(cpu_cvs, cpu_lines, cpu_c)
        recolor_lines(ram_cvs, ram_lines, ram_c)
        recolor_lines(temp_cvs, temp_lines, tmp_c)
        update_graph_lines(cpu_cvs, cpu_lines, cpu_hist, 100)
        update_graph_lines(ram_cvs, ram_lines, ram_hist, 100)
        update_graph_lines(temp_cvs, temp_lines, temp_hist, 85)
        cpu_lbl.config(fg=cpu_c); cpu_val.config(text=f"{cpu:4.0f} %",fg=cpu_c)
        ram_lbl.config(fg=ram_c); ram_val.config(text=f"{ram:4.0f} %",fg=ram_c)
        temp_lbl.config(fg=tmp_c); temp_val.config(text=f"{temp:4.1f} °C",fg=tmp_c)
    if net_win and net_win.winfo_exists():
        global last_net_io, last_used_iface

        used_iface, net_io = get_net_io(NET_INTERFACE)

        # --- Detectar cambio de interfaz ---
        if used_iface != last_used_iface:
            last_used_iface = used_iface
            last_net_io = net_io
            download = 0.0
            upload = 0.0
        else:
            download, upload = safe_net_speed(net_io, last_net_io)
            last_net_io = net_io


        net_download_hist.append(download)
        net_upload_hist.append(upload)
        
        global net_dynamic_max

        combined = list(net_download_hist) + list(net_upload_hist)
        net_dynamic_max = adaptive_scale(net_dynamic_max, combined)


        smooth_dl = smooth(list(net_download_hist), 6)
        smooth_ul = smooth(list(net_upload_hist), 6)


        update_graph_lines(
            net_dl_cvs,
            net_dl_lines,
            smooth_dl,
            net_dynamic_max
        )

        update_graph_lines(
            net_ul_cvs,
            net_ul_lines,
            smooth_ul,
            net_dynamic_max
        )


        dl_c = net_color(download)
        ul_c = net_color(upload)

        recolor_lines(net_dl_cvs, net_dl_lines, dl_c)
        recolor_lines(net_ul_cvs, net_ul_lines, ul_c)

        net_dl_lbl.config(fg=dl_c, text=f"DESCARGA MB/s ({used_iface})")
        net_dl_val.config(fg=dl_c, text=f"{download:5.2f} MB/s |  Escala {net_dynamic_max:.1f}")
        net_ul_lbl.config(fg=ul_c, text=f"SUBIDA MB/s ({used_iface})")
        net_ul_val.config(fg=ul_c, text=f"{upload:5.2f} MB/s |  Escala {net_dynamic_max:.1f}")



    root.after(UPDATE_MS,update)

update()
root.mainloop()

