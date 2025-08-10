import sys
sys.path.append('/home/techsharks/MFRC522-python')

import RPi.GPIO as GPIO
from mfrc522 import MFRC522
import time
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timezone, timedelta
import serial
import threading

ser = serial.Serial('/dev/serial0', baudrate=57600, timeout=1)
serial_lock = threading.Lock()

def set_led(mode=0x02, speed=0x00, color=0x02, count=0x00):
    """
    Controls LED ring on R503.
    mode: 0=off, 1=breathing, 2=on, 3=flashing
    color: 1=red, 2=blue, 3=purple, 4=green
    speed: 0-15 (higher slower)
    count: times to flash (0=continuous)
    """
    payload = b'\x35' + bytes([mode, speed, color, count])
    send_cmd(payload)
    
def packet_header(packet_type, payload):
    header = b'\xEF\x01\xFF\xFF\xFF\xFF'
    length = len(payload) + 2
    packet = header + bytes([packet_type]) + length.to_bytes(2, 'big') + payload
    checksum = sum(packet[6:])
    packet += checksum.to_bytes(2, 'big')
    return packet
    
def send_cmd(payload, response_len=12):
    with serial_lock:  # thread-safe serial access
        packet = packet_header(0x01, payload)
        ser.write(packet)
        response = ser.read(response_len)
    return response

RELAY_PIN = 27  # GPIO27 (physical pin 13)

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, GPIO.LOW)

buzzer_pin = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(buzzer_pin, GPIO.OUT)
pwm = GPIO.PWM(buzzer_pin, 1000)  # 440 Hz = A4 note

reader = MFRC522()

# ? List of authorized card IDs
AUTHORIZED_IDS = [3555744237,3279957986]
AUTHORIZED_CARDS = {
    3555744237: "SSG",
    3279957986: "Ashen",
}

# -------------- OLED Display ------------------
serial = i2c(port=1, address=0x3C)
device = ssd1306(serial)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def update_display(message):
    image = Image.new("1", device.size)
    draw = ImageDraw.Draw(image)
    lines = message.split('\n')
    for size in range(20, 7, -1):
        font = ImageFont.truetype(FONT_PATH, size)
        max_w = max(draw.textlength(line, font=font) for line in lines)
        total_h = sum(font.getbbox(line)[3] for line in lines) + (len(lines) - 1) * 2
        if max_w <= device.width and total_h <= device.height:
            break
    y = (device.height - total_h) // 2
    draw.rectangle((0, 0, device.width, device.height), fill=0)
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((device.width - w) // 2, y), line, font=font, fill=255)
        y += font.getbbox(line)[3] + 2
    device.display(image)
    
print("Place your card near the reader...")

try:
    while True:
        set_led(mode=0x02, speed=0x00, color=0x02, count=0x00)  # Blue LED - waiting
        (status, TagType) = reader.MFRC522_Request(reader.PICC_REQIDL)

        if status == reader.MI_OK:
            (status, uid) = reader.MFRC522_Anticoll()

            if status == reader.MI_OK:
                card_id = (uid[0] << 24) | (uid[1] << 16) | (uid[2] << 8) | uid[3]

                if card_id in AUTHORIZED_CARDS:
                    print(f"Hello {AUTHORIZED_CARDS[card_id]}, Welcome !")
                    update_display(f"Hello {AUTHORIZED_CARDS[card_id]}\nWelcome !")
                    pwm.start(50)  # 50% duty cycle
                    time.sleep(0.1)
                    pwm.stop()
                    GPIO.output(RELAY_PIN, GPIO.HIGH)
                    print("Relay ON")
                    time.sleep(5)
                    GPIO.output(RELAY_PIN, GPIO.LOW)
                  
                else:
                    print("Unauthorized card")
                    update_display("Unauthorized")

                # Wait a moment so it doesn't print multiple times for the same card
                time.sleep(2)
    time.sleep(0.1)


finally:
    GPIO.cleanup()