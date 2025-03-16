import time

class Timer:
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.running = False

    def start(self):
        """Start the timer."""
        self.start_time = time.monotonic()
        self.end_time = None
        self.running = True

    def stop(self):
        """Stop the timer."""
        if self.running:
            self.end_time = time.monotonic()
            self.running = False

    def elapsed(self):
        """Return the elapsed time since the timer started."""
        if self.running:
            return time.monotonic() - self.start_time
        elif self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def reset(self):
        """Reset the timer to its initial state."""
        self.start_time = None
        self.end_time = None
        self.running = False
