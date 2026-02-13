import psutil
import time
from config.settings import NET_INTERFACE

class NetworkService:

    def __init__(self):
        self._last_io = psutil.net_io_counters(pernic=True)
        self._last_time = time.time()

    def get_network_delta(self):
        current_io = psutil.net_io_counters(pernic=True)
        current_time = time.time()

        # -----------------------------
        # Selección automática interfaz
        # -----------------------------
        iface = None

        if NET_INTERFACE and NET_INTERFACE in current_io:
            iface = NET_INTERFACE
        else:
            # Buscar interfaz con tráfico
            max_bytes = 0
            for name, stats in current_io.items():
                if name == "lo":
                    continue  # ignorar loopback

                total = stats.bytes_sent + stats.bytes_recv
                if total > max_bytes:
                    max_bytes = total
                    iface = name

        if iface is None:
            return {
                "iface": "N/A",
                "upload_bytes": 0,
                "download_bytes": 0,
                "delta_time": 1
            }

        prev = self._last_io.get(iface)
        curr = current_io.get(iface)

        delta_time = current_time - self._last_time
        delta_time = max(delta_time, 0.0001)

        upload = curr.bytes_sent - prev.bytes_sent if prev else 0
        download = curr.bytes_recv - prev.bytes_recv if prev else 0

        self._last_io = current_io
        self._last_time = current_time

        return {
            "iface": iface,
            "upload_bytes": max(0, upload),
            "download_bytes": max(0, download),
            "delta_time": delta_time
        }
