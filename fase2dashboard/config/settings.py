# config/settings.py

# -----------------------------
# ---------- Archivos ----------
# -----------------------------
STATE_FILE = "/home/jalivur/Documents/proyectopantallas/fan_state.json"
CURVE_FILE = "/home/jalivur/Documents/proyectopantallas/fan_curve.json"

# -----------------------------
# ---------- Display ----------
# -----------------------------
DSI_WIDTH = 800
DSI_HEIGHT = 480

# -----------------------------
# ---------- Config ----------
# -----------------------------
UPDATE_MS = 2000
HISTORY = 60

CPU_WARN  = 60
CPU_CRIT  = 85
TEMP_WARN = 60
TEMP_CRIT = 75
RAM_WARN  = 65
RAM_CRIT  = 85

NET_WARN  = 2.0
NET_CRIT  = 6.0


DISK_MIN_SCALE = 0.1
DISK_MAX_SCALE = 10000 # MB/s límite superior
DISK_IDLE_THRESHOLD = 0.5  # MB/s mínimo para considerar inactivo
DISK_IDLE_RESET_TIME = 15  # segundos

LAUNCHERS = [
    {
        "label": "Montar NAS",
        "script": "/home/jalivur/Documents/montarnas.sh"
    },
    {
        "label": "Desmontar NAS",
        "script": "/home/jalivur/Documents/desmontarnas.sh"
    },
    {
        "label": "Update System",
        "script": "/home/jalivur/Documents/update.sh"
    },
    {
        "label": "Shutdown",
        "script": "/home/jalivur/Documents/apagado.sh"
    },
    {
        "label": "Conectar VPN",
        "script":"/home/jalivur/Documents/conectar_vpn.sh"
    },
    {
        "label":"Desconectar VPN",
        "script":"/home/jalivur/Documents/desconectar_vpn.sh"
    }
]
