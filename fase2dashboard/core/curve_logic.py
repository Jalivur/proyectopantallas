import json
from config.settings import CURVE_FILE

class CurveLogic:

    def load_curve(self):
        try:
            with open(CURVE_FILE) as f:
                data = json.load(f)
                pts = data.get("points", [])
                if not isinstance(pts, list):
                    pts = []
                sanitized = []
                for p in pts:
                    try:
                        t = int(p.get("temp", 0))
                        pwm = int(p.get("pwm", 0))
                        pwm = max(0, min(255, pwm))
                        sanitized.append({"temp": t, "pwm": pwm})
                    except:
                        continue
                if not sanitized:
                    sanitized = [
                        {"temp": 40, "pwm": 100},
                        {"temp": 50, "pwm": 130},
                        {"temp": 60, "pwm": 160},
                        {"temp": 70, "pwm": 180},
                        {"temp": 80, "pwm": 200}
                    ]
                return sorted(sanitized, key=lambda x: x["temp"])
        except:
            return [
                {"temp": 40, "pwm": 100},
                {"temp": 50, "pwm": 130},
                {"temp": 60, "pwm": 160},
                {"temp": 70, "pwm": 180},
                {"temp": 80, "pwm": 200}
            ]

    def compute_pwm(self, temp):
        curve = self.load_curve()
        if not curve:
            return 0

        if temp <= curve[0]["temp"]:
            return curve[0]["pwm"]

        if temp >= curve[-1]["temp"]:
            return curve[-1]["pwm"]

        for i in range(len(curve) - 1):
            t1 = curve[i]
            t2 = curve[i + 1]
            if t1["temp"] <= temp <= t2["temp"]:
                ratio = (temp - t1["temp"]) / (t2["temp"] - t1["temp"])
                return int(t1["pwm"] + ratio * (t2["pwm"] - t1["pwm"]))

        return curve[-1]["pwm"]
