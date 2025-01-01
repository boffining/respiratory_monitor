import time

class BreathingAlarm:
    def __init__(self, thresholds):
        self.alarm_armed = False
        self.alarm_active = False
        self.validation_count = 0
        self.thresholds = thresholds
        self.pending_state = "Initializing"
        self.active_state = "Initializing"
        self.no_movement = False

    def update_alarm_state(self):
        """
        Updates the alarm state based on current states and thresholds.
        """
        alarm_count_limit = (self.thresholds["pending"] 
                             if self.active_state != "NoMovement"
                             else self.thresholds["pending"] + self.thresholds["active"])

        if self.pending_state == "NoMovement":
            if self.validation_count < alarm_count_limit:
                self.validation_count += 1
        else:
            if self.validation_count > 0:
                self.validation_count -= 1

        # Validate alarm activation
        if self.validation_count >= self.thresholds["validation"]:
            self.activate_alarm()

    def activate_alarm(self):
        """
        Activates the alarm.
        """
        self.alarm_active = True
        self.alarm_armed = False  # Disarm after activation
        print("Alarm Activated")

    def reset_alarm(self, disarm=False):
        """
        Resets the alarm state.
        """
        if disarm:
            self.alarm_armed = False
        self.validation_count = 0
        if self.alarm_active:
            self.alarm_active = False
            print("Alarm Reset")

    def arm_alarm(self):
        """
        Arms the alarm for activation.
        """
        self.alarm_armed = True

    def set_states(self, pending, active):
        """
        Set the pending and active states for the algorithm.
        """
        self.pending_state = pending
        self.active_state = active

    def is_active(self):
        return self.alarm_active

    def is_armed(self):
        return self.alarm_armed


if __name__ == "__main__":
    thresholds = {
        "pending": 200,
        "active": 30,
        "validation": 230  # Pending + Active thresholds
    }

    alarm = BreathingAlarm(thresholds)

    # Example sequence
    alarm.arm_alarm()
    for _ in range(250):
        alarm.set_states("NoMovement", "Breathing")
        alarm.update_alarm_state()
        time.sleep(0.01)  # Simulate processing delay
