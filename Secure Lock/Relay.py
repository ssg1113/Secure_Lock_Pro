import RPi.GPIO as GPIO
import time

# === Setup ===
RELAY_PIN = 27  # GPIO27 (physical pin 13)

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)

print("Relay test started. Press Ctrl+C to stop.")

try:
    while True:
        # Turn relay ON (active LOW)
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        print("Relay ON")
        time.sleep(6)

        # Turn relay OFF
        GPIO.output(RELAY_PIN, GPIO.LOW)
        print("Relay OFF")
        time.sleep(6)

except KeyboardInterrupt:
    print("Program stopped by user.")

finally:
    GPIO.cleanup()
    print("GPIO cleaned up.")
