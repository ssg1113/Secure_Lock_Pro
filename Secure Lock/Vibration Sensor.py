import RPi.GPIO as GPIO
import time

SENSOR_PIN = 22  # GPIO 22 (Pin 15)

GPIO.setmode(GPIO.BCM)
GPIO.setup(SENSOR_PIN, GPIO.IN)

print("Monitoring vibration on GPIO 22...")

try:
    while True:
        if GPIO.input(SENSOR_PIN) == GPIO.HIGH:
            for i in range(100):
                print("Vibration detected!")
                print(i)
        time.sleep(0.5)
except KeyboardInterrupt:
    print("Stopped by user")
finally:
    GPIO.cleanup()
