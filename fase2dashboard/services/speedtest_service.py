import subprocess
import threading
import re


class SpeedtestService:

    def __init__(self):
        self._running = False
        self._result = {
            "ping": None,
            "download": None,
            "upload": None,
            "status": "idle"
        }

    def get_result(self):
        return self._result

    def is_running(self):
        return self._running

    def start(self):
        if self._running:
            return

        thread = threading.Thread(
            target=self._run_speedtest,
            daemon=True
        )
        thread.start()

    def _run_speedtest(self):
        self._running = True

        self._result["status"] = "running"
        self._result["ping"] = None
        self._result["download"] = None
        self._result["upload"] = None

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

            self._result["ping"] = float(ping.group(1)) if ping else None
            self._result["download"] = float(down.group(1)) / 8 if down else None
            self._result["upload"] = float(up.group(1)) / 8 if up else None

            self._result["status"] = "done"

        except subprocess.TimeoutExpired:
            self._result["status"] = "timeout"

        except Exception:
            self._result["status"] = "error"

        self._running = False
