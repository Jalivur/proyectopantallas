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
DSI_X = None
DSI_Y = None

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

# ---------- Layout (graphs only) ----------
frame = tk.Frame(root, bg="black")
frame.pack(padx=10, pady=10)

def make_block(title):
    lbl = tk.Label(frame, text=title, fg="white", bg="black", font=font)
    lbl.pack(anchor="w")
    val = tk.Label(frame, fg="white", bg="black", font=font_value)
    val.pack(anchor="e")
    cvs = tk.Canvas(frame, width=WIDTH, height=HEIGHT, bg="black", highlightthickness=0)
    cvs.pack()
    return lbl, val, cvs

cpu_lbl, cpu_val, cpu_cvs = make_block("CPU %")
ram_lbl, ram_val, ram_cvs = make_block("RAM %")
temp_lbl, temp_val, temp_cvs = make_block("TEMP °C")

cpu_hist = deque([0]*HISTORY, maxlen=HISTORY)
ram_hist = deque([0]*HISTORY, maxlen=HISTORY)
temp_hist = deque([0]*HISTORY, maxlen=HISTORY)

# ---------- CONTROL WINDOW ----------
control_win = None
mode_var = tk.StringVar(value="auto")
manual_pwm = tk.IntVar(value=128)
curve_vars = []
last_state = None
# Allow forcing compact layout from UI
compact_var = tk.BooleanVar(value=False)

def toggle_compact_mode():
    """Toggle compact mode and rebuild the control window to apply layout."""
    try:
        new = compact_var.get()
        logging.info(f"toggle_compact_mode -> {new}")
        if control_win and control_win.winfo_exists():
            control_win.destroy()
            # reopen with new compact setting
            open_control_window()
    except Exception:
        logging.exception("Failed toggling compact mode")

def open_control_window():
    global control_win, curve_vars

    try:
        logging.info("Opening control window")

        if control_win and control_win.winfo_exists():
            control_win.lift()
            control_win.focus_force()
            return

        control_win = tk.Toplevel(root)
        control_win.title("Fan Control")
        control_win.configure(bg="black")
        # Position control window inside the DSI screen with margins (robust)
        cw_w, cw_h = 600, 400
        cw_x, cw_y = 100, 100
        try:
            if DSI_X is not None and DSI_Y is not None:
                cw_w = min(780, max(300, DSI_WIDTH - 20))
                cw_h = min(460, max(200, DSI_HEIGHT - 20))
                cw_x = DSI_X + 10
                cw_y = DSI_Y + 10
            else:
                # fallback to centering on primary screen
                screen_w = root.winfo_screenwidth()
                screen_h = root.winfo_screenheight()
                cw_w = min(780, max(300, screen_w - 300))
                cw_h = min(460, max(200, screen_h - 200))
                cw_x = max(0, (screen_w - cw_w) // 2)
                cw_y = max(0, (screen_h - cw_h) // 2)
            control_win.geometry(f"{cw_w}x{cw_h}+{cw_x}+{cw_y}")
            control_win.minsize(300,200)
            # Keep the control window fixed to avoid content overflow on small displays
            try:
                control_win.resizable(False, False)
            except Exception:
                pass
            logging.info(f"Control window geometry set to {cw_w}x{cw_h}+{cw_x}+{cw_y}")
        except Exception:
            control_win.geometry("600x500")
            cw_w, cw_h = 600, 500

        # Use transient/topmost and focus rather than grab_set (modal grabs can interfere with some input devices)
        control_win.transient(root)
        try:
            control_win.attributes("-topmost", True)
        except Exception:
            pass
        control_win.focus_set()
        control_win.protocol("WM_DELETE_WINDOW", on_control_close)
        # allow Esc to close the control window
        control_win.bind("<Escape>", lambda e: on_control_close())

        # Log focus events to help diagnose responsiveness on different displays
        control_win.bind("<FocusIn>", lambda e: logging.info("Control window FocusIn"))
        control_win.bind("<FocusOut>", lambda e: logging.info("Control window FocusOut"))
        control_win.bind("<Map>", lambda e: logging.info(f"Control window mapped at {control_win.winfo_x()},{control_win.winfo_y()} size {control_win.winfo_width()}x{control_win.winfo_height()}"))

        # Resize handling: debounce configure events and adjust slider lengths
        def _adjust_scales_to_width():
            try:
                w = max(200, control_win.winfo_width())
                # compute new scale length
                new_len = max(120, w - 220)
                try:
                    manual_scale.config(length=new_len)
                except Exception:
                    pass
                # iterate content children to find scales and update them
                try:
                    for child in content.winfo_children():
                        # if direct Scale
                        if isinstance(child, tk.Scale):
                            child.config(length=new_len)
                        else:
                            for c2 in child.winfo_children():
                                if isinstance(c2, tk.Scale):
                                    c2.config(length=new_len)
                except Exception:
                    pass
                logging.info(f"Adjusted scales to length {new_len} on resize ({w}px)")
            except Exception:
                logging.exception("Failed adjusting scales on resize")

        def _on_control_configure(event):
            try:
                if hasattr(control_win, '_resize_after'):
                    control_win.after_cancel(control_win._resize_after)
                control_win._resize_after = control_win.after(250, _adjust_scales_to_width)
            except Exception:
                pass

        control_win.bind('<Configure>', _on_control_configure)

        # Pointer event logging for widgets on this Toplevel (helps detect input not reaching controls)
        def _pointer_event(e):
            try:
                if e.widget.winfo_toplevel() == control_win:
                    logging.info(f"Pointer event on control window: widget={e.widget}, x={e.x_root}, y={e.y_root}")
            except Exception:
                pass
        control_win.bind_all("<Button-1>", _pointer_event)

        # Create a scrollable area for the controls
        content_container = tk.Frame(control_win, bg="black")
        content_container.pack(fill="both", expand=True)
        # Configure canvas to fit within computed control window size
        canvas_w = max(200, cw_w - 24)
        canvas_h = max(200, cw_h - 120)
        canvas = tk.Canvas(content_container, bg="black", highlightthickness=0, width=canvas_w, height=canvas_h)
        vsb = tk.Scrollbar(content_container, orient="vertical", command=canvas.yview, width=16)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=vsb.set)
        inner = tk.Frame(canvas, bg="black", width=canvas_w)
        canvas.create_window((0,0), window=inner, anchor="nw", width=canvas_w)
        def _on_inner_config(event):
            # ensure scrollregion matches current contents
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner_config)
        content = inner
        # Dynamic scale length for sliders to avoid overflow
        scale_len = max(200, cw_w - 180)

        # update the manual scale later to use scale_len
        # (we will configure its length when creating it below)

        # Mouse wheel support for scrolling (Linux, Windows, macOS)
        def _on_mousewheel(event):
            try:
                # X11: Button-4 (up), Button-5 (down)
                if hasattr(event, 'num') and event.num == 4:
                    canvas.yview_scroll(-1, "units")
                    return
                if hasattr(event, 'num') and event.num == 5:
                    canvas.yview_scroll(1, "units")
                    return
                # Windows / macOS: event.delta
                delta = getattr(event, 'delta', 0)
                if delta:
                    canvas.yview_scroll(-int(delta / 120), "units")
            except Exception:
                logging.exception("Error handling mousewheel")

        # Bind mousewheel only while pointer is over the canvas to avoid global grabbing
        def _bind_mousewheel(event):
            canvas.bind("<Button-4>", _on_mousewheel)
            canvas.bind("<Button-5>", _on_mousewheel)
            canvas.bind("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(event):
            canvas.unbind("<Button-4>")
            canvas.unbind("<Button-5>")
            canvas.unbind("<MouseWheel>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        # Top fixed area with mode/manual/actions (always visible)
        top_area = tk.Frame(control_win, bg="black")
        top_area.pack(fill="x", padx=6, pady=6)

        # ---------- MODE (fixed) ----------
        tk.Label(top_area, text="Modo", fg="white", bg="black").grid(row=0, column=0, sticky="w")
        modes_frame = tk.Frame(top_area, bg="black")
        modes_frame.grid(row=0, column=1, sticky="w", padx=(8,0))

        def set_mode(mode):
            logging.info(f"set_mode -> {mode}")
            mode_var.set(mode)
            write_state({"mode": mode, "target_pwm": None})

        for i, m in enumerate(("auto", "silent", "normal", "performance", "manual")):
            tk.Radiobutton(
                modes_frame,
                text=m.upper(),
                variable=mode_var,
                value=m,
                command=lambda m=m: set_mode(m),
                bg="black", fg="white",
                selectcolor="black",
                indicatoron=1
            ).pack(side="left", padx=(0,6))
        # Compact mode toggle (forces compact layout when checked)
        tk.Checkbutton(modes_frame, text="Compacto", variable=compact_var, command=toggle_compact_mode, bg="black", fg="white", selectcolor="black").pack(side="left", padx=(6,0))
        # allow user to resize control window
        try:
            control_win.resizable(True, True)
        except Exception:
            pass

        # ---------- MANUAL (fixed) ----------
        tk.Label(top_area, text="PWM Manual (0-255)", fg="white", bg="black").grid(row=1, column=0, sticky="w", pady=(6,0))
        manual_frame = tk.Frame(top_area, bg="black")
        manual_frame.grid(row=1, column=1, sticky="we", pady=(6,0))
        manual_scale = tk.Scale(
            manual_frame,
            from_=0, to=255,
            orient="horizontal",
            variable=manual_pwm,
            bg="black", fg="white",
            highlightthickness=0,
            length=scale_len,
            sliderlength=20,
            width=20
        )
        manual_scale.pack(side="left", fill="x", expand=True)
        manual_lbl = tk.Label(manual_frame, text=str(manual_pwm.get()), fg="white", bg="black", width=5)
        manual_lbl.pack(side="left", padx=(6,0))

        def on_manual_pwm(val):
            logging.info(f"on_manual_pwm -> {val} (mode={mode_var.get()})")
            if mode_var.get() != "manual":
                return
            try:
                val_int = int(float(val))
            except Exception:
                val_int = manual_pwm.get()
            val_int = max(0, min(255, val_int))
            manual_pwm.set(val_int)
            logging.info(f"manual PWM set to {val_int}")
            write_state({"mode": "manual", "target_pwm": val_int})

        # update label on change and call on_manual_pwm
        manual_scale.configure(command=lambda v: (on_manual_pwm(v), manual_lbl.config(text=str(int(float(v))))) )

        # Define save_curve before creating its button to avoid UnboundLocalError
        def save_curve():
            if not curve_vars:
                logging.warning("save_curve called but no curve_vars present")
                messagebox.showerror("Error", "No hay puntos de curva para guardar")
                return
            data = {
                "points": sorted(
                    [{"temp": t, "pwm": max(0, min(255, int(v.get())))} for t, v in curve_vars],
                    key=lambda p: p["temp"]
                )
            }
            logging.info(f"Saving curve data: {data}")
            try:
                with open(CURVE_FILE, "w") as f:
                    json.dump(data, f, indent=2)
                logging.info("Curva guardada correctamente")
                messagebox.showinfo("Guardado", "Curva guardada correctamente")
            except Exception as e:
                logging.exception("Failed to save curve")
                messagebox.showerror("Error", f"No se pudo guardar la curva: {e}")

        # Action buttons fixed
        actions_frame = tk.Frame(top_area, bg="black")
        actions_frame.grid(row=0, column=2, rowspan=2, padx=(12,0))
        tk.Button(actions_frame, text="Guardar curva", command=save_curve).pack(pady=(0,6))
        def restore_default():
            default = [
                {"temp": 40, "pwm": 100},
                {"temp": 50, "pwm": 130},
                {"temp": 60, "pwm": 160},
                {"temp": 70, "pwm": 180},
                {"temp": 80, "pwm": 255}
            ]
            try:
                with open(CURVE_FILE, "w") as f:
                    json.dump({"points": default}, f, indent=2)
                messagebox.showinfo("Restaurado", "Curva por defecto restaurada")
                logging.info("Curva restaurada a valores por defecto")
                # recreate the control window to refresh sliders
                control_win.destroy()
                open_control_window()
            except Exception:
                logging.exception("Failed to restore default curve")
                messagebox.showerror("Error", "No se pudo restaurar la curva por defecto")
        tk.Button(actions_frame, text="Restaurar por defecto", command=restore_default).pack()
        # Close button to properly shut the control window and cleanup
        tk.Button(actions_frame, text="Cerrar", command=on_control_close).pack(pady=(6,0))

        # Quick scroll buttons (helpful if mouse wheel not working)
        btn_frame = tk.Frame(content, bg="black")
        btn_frame.pack(fill="x", pady=(6,0))
        tk.Button(btn_frame, text="↑", command=lambda: canvas.yview_scroll(-1, "pages"), width=3).pack(side="left", padx=(0,6))
        tk.Button(btn_frame, text="↓", command=lambda: canvas.yview_scroll(1, "pages"), width=3).pack(side="left")

        # ---------- CURVE ----------
        tk.Label(content, text="Curva térmica", fg="white", bg="black").pack(anchor="w", pady=(10,0))

        curve_vars.clear()

        status_lbl = tk.Label(content, text="", fg="white", bg="black")
        status_lbl.pack(anchor="w")

        try:
            pts = load_curve()
            n_pts = len(pts)
            logging.info(f"Loaded curve with {n_pts} points")

            # Determine if content fits; if not, enable compact modes to shrink vertical footprint
            top_fixed_est = 140  # estimated vertical space taken by fixed top area
            actions_est = 80     # estimated space for action buttons and margins
            avail_height = cw_h - 24  # available inner height for content
            per_row_default = 48
            needed = top_fixed_est + actions_est + n_pts * per_row_default
            compact = False
            super_compact = False
            small_slider_length = 18
            small_scale_width = 16
            small_label_font = (font[0], max(10, font[1]-4))

            # If user forces compact mode, honor it and try to fit
            if compact_var.get():
                compact = True
                scale_len = max(120, int(cw_w * 0.45))
                status_lbl.config(text=f"Puntos: {n_pts} (compacto - forzado)")
                try:
                    manual_scale.config(length=scale_len, sliderlength=small_slider_length, width=small_scale_width)
                    manual_lbl.config(font=small_label_font)
                except Exception:
                    pass
                # If after forcing compact it still doesn't fit, escalate to super compact
                if needed > avail_height and n_pts > 0:
                    super_compact = True
            elif needed > avail_height and n_pts > 0:
                compact = True
                # compute a per-row height that fits
                per_row = max(18, (avail_height - top_fixed_est - actions_est) // n_pts)
                scale_len = max(120, int(cw_w * 0.45))
                logging.info(f"Switching to compact layout: per_row={per_row}, scale_len={scale_len}")
                status_lbl.config(text=f"Puntos: {n_pts} (compacto)")
                # shrink manual scale to match new size
                try:
                    manual_scale.config(length=scale_len, sliderlength=small_slider_length, width=small_scale_width)
                    manual_lbl.config(font=small_label_font)
                except Exception:
                    pass
                # If still not enough vertical room, escalate to super compact
                if needed > avail_height and n_pts > 0:
                    super_compact = True

            # Super compact further reduces fonts, paddings and slider thickness
            if super_compact:
                logging.info("Enabling super compact layout")
                per_row = max(16, (avail_height - top_fixed_est - actions_est) // max(1, n_pts))
                scale_len = max(100, int(cw_w * 0.35))
                small_slider_length = 16
                small_scale_width = 12
                small_label_font = (font[0], max(8, font[1]-6))
                status_lbl.config(text=f"Puntos: {n_pts} (super compacto)")
                try:
                    manual_scale.config(length=scale_len, sliderlength=small_slider_length, width=small_scale_width)
                    manual_lbl.config(font=small_label_font)
                except Exception:
                    pass

            if not compact and not super_compact:
                status_lbl.config(text=f"Puntos: {n_pts}")

            for p in pts:
                row = tk.Frame(content, bg="black")
                # reduce vertical spacing in compact mode
                row.pack(fill="x", pady=(2,2) if compact else (6,6))

                lbl_temp = tk.Label(row, text=f'{p["temp"]}°C', fg="white", bg="black", width=6)
                if compact:
                    lbl_temp.config(font=small_label_font)
                lbl_temp.pack(side="left")

                var = tk.IntVar(value=max(0, min(255, int(p.get("pwm", 0)))))
                lbl_val = tk.Label(row, text=str(var.get()), fg="white", bg="black", width=5)
                if compact:
                    lbl_val.config(font=small_label_font)
                lbl_val.pack(side="right")

                def make_cmd(lbl, temp):
                    def cmd(v):
                        try:
                            val = int(float(v))
                        except Exception:
                            val = int(lbl.cget("text"))
                        lbl.config(text=str(val))
                        logging.info(f"curve slider {temp}°C -> {val}")
                    return cmd

                tk.Scale(
                    row,
                    from_=0, to=255,
                    orient="horizontal",
                    variable=var,
                    command=make_cmd(lbl_val, p["temp"]),
                    bg="black", fg="white",
                    highlightthickness=0,
                    length=scale_len,
                    sliderlength=(small_slider_length if compact else 25),
                    width=(small_scale_width if compact else 20)
                ).pack(fill="x", expand=True)

                curve_vars.append((p["temp"], var))

        except Exception:
            logging.exception("Failed to create curve sliders")
            messagebox.showerror("Error", "No se pudieron crear sliders de curva. Revisa el log.")

        # Initialize controls from saved state
        try:
            st = load_state()
            logging.info(f"Initializing control window with state: {st}")
            mode_var.set(st.get("mode", "auto"))
            tp = st.get("target_pwm")
            if isinstance(tp, int):
                manual_pwm.set(tp)
        except Exception:
            logging.exception("Failed to initialize control window state")


    except Exception as e:
        logging.exception("Failed to open control window")
        messagebox.showerror("Error", f"Error al abrir ventana de control: {e}")

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
    



# ---------- Menu ----------
menu = tk.Menu(root)
root.config(menu=menu)
fan_menu = tk.Menu(menu, tearoff=0)
menu.add_cascade(label="Ventiladores", menu=fan_menu)
fan_menu.add_command(label="Control", command=open_control_window)
fan_menu.add_command(label="Salir", command=root.destroy)

# ---------- Toolbar ----------
toolbar = tk.Frame(root, bg="black", pady=4)
toolbar.pack(side="top", fill="x")

# botón grande
tk.Button(toolbar, text="Control", command=open_control_window, width=12, height=2).pack(side="left", padx=6)
tk.Button(toolbar, text="Salir", command=root.destroy, width=8, height=2).pack(side="left", padx=6)

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

