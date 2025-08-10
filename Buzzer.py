import RPi.GPIO as GPIO
import time

buzzer_pin = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(buzzer_pin, GPIO.OUT)

pwm = GPIO.PWM(buzzer_pin, 700)  # 440 Hz = A4 note
pwm.start(50)  # 50% duty cycle
time.sleep(0.1)
pwm.stop()
GPIO.cleanup()
