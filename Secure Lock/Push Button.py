import RPi.GPIO as GPIO
import time

BUTTON_PIN = 23     # GPIO23 - Push Button
RELAY_PIN = 27     # GPIO27 - Relay

GPIO.setmode(GPIO.BCM)

# Setup
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(RELAY_PIN, GPIO.OUT)

# Start with relay ON (locked)
GPIO.output(RELAY_PIN, GPIO.LOW)

try:
    while True:
        if GPIO.input(BUTTON_PIN) == GPIO.LOW:
            print("Button pressed ? Unlocking for 5 seconds")
            GPIO.output(RELAY_PIN, GPIO.HIGH)  # Unlock (relay OFF)
            time.sleep(5)  # Keep unlocked
            print("Locking again")
            GPIO.output(RELAY_PIN, GPIO.LOW)   # Lock again (relay ON)
        
        time.sleep(0.1)  # Polling delay
except KeyboardInterrupt:
    GPIO.cleanup()
