from gpiozero import LED
import threading
import time

class LEDController:
    def __init__(self, pin_in=19, pin_out=26):
        self.led_in = LED(pin_in)
        self.led_out = LED(pin_out)

    def flash_in(self, duration=0.2):
        self._flash(self.led_in, duration)

    def flash_out(self, duration=0.2):
        self._flash(self.led_out, duration)

    def _flash(self, led, duration):
        def do_flash():
            led.on()
            time.sleep(duration)
            led.off()
        threading.Thread(target=do_flash).start()
