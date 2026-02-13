import psutil
import subprocess
import re

class SystemMetrics:

    def __init__(self):
        self._last_disk_io = psutil.disk_io_counters()

    def get_cpu_usage(self):
        return psutil.cpu_percent()

    def get_ram_usage(self):
        return psutil.virtual_memory().percent

    def get_cpu_temp(self):
        try:
            out = subprocess.check_output(
                ["vcgencmd", "measure_temp"]
            ).decode()
            return float(out.replace("temp=", "").replace("'C\n", ""))
        except:
            return 0.0

    def get_disk_usage(self):
        return psutil.disk_usage('/').percent

    def get_disk_io(self):
        current = psutil.disk_io_counters()

        read_bytes = current.read_bytes - self._last_disk_io.read_bytes
        write_bytes = current.write_bytes - self._last_disk_io.write_bytes

        self._last_disk_io = current

        # Evitar valores negativos
        read_bytes = max(0, read_bytes)
        write_bytes = max(0, write_bytes)

        return {
            "read_mb": read_bytes / 1024 / 1024,
            "write_mb": write_bytes / 1024 / 1024
        }


    def get_disk_temp(self, device="/dev/nvme0n1"):
        try:
            out = subprocess.check_output(
                ["sudo", "nvme", "smart-log", device],
                stderr=subprocess.DEVNULL
            ).decode()

            # Buscar temperatura en formato "33°C"
            match = re.search(r"temperature\s*:\s*(\d+)\s*°C", out, re.IGNORECASE)
            if match:
                return int(match.group(1))
            return 0.0
        except:
            return 0.0
