import json
import os
from config.settings import STATE_FILE

class StateService:

    def write_state(self, data):
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, STATE_FILE)

    def load_state(self):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {"mode": "auto", "target_pwm": None}
                return {
                    "mode": data.get("mode", "auto"),
                    "target_pwm": data.get("target_pwm")
                }
        except:
            return {"mode": "auto", "target_pwm": None}

