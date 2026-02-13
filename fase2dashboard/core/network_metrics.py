import time
from config.settings import (
    NET_MIN_SCALE,
    NET_MAX_SCALE,
    NET_IDLE_THRESHOLD,
    NET_IDLE_RESET_TIME
)

class NetworkMetrics:

    def __init__(self):
        self.dynamic_max = NET_MIN_SCALE
        self.last_activity = time.time()

    def compute_speed(self, bytes_amount, delta_time):
        mb_per_sec = (bytes_amount / 1024 / 1024) / delta_time
        return mb_per_sec

    def update_dynamic_scale(self, current_speed):
        now = time.time()

        if current_speed > self.dynamic_max:
            self.dynamic_max = min(current_speed, NET_MAX_SCALE)
            self.last_activity = now

        elif current_speed > NET_IDLE_THRESHOLD:
            self.last_activity = now

        if now - self.last_activity > NET_IDLE_RESET_TIME:
            self.dynamic_max = NET_MIN_SCALE

        return self.dynamic_max
