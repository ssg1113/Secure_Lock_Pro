import os
import sys
import time
import json
import uuid
import serial
import threading
from datetime import datetime, timezone, timedelta

import RPi.GPIO as GPIO

sys.path.append('/home/techsharks/MFRC522-python')
from mfrc522 import MFRC522

from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont

sys.path.append('/home/techsharks/firebase_lib')
import firebase_admin
from firebase_admin import credentials, firestore

import boto3
from botocore.exceptions import ClientError
from picamera2 import Picamera2

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

# ---------------------------
# ========== CONFIG =========
# ---------------------------

CRED_FILE = "/home/techsharks/credentials.json"
FIREBASE_SA_PATH = "/home/techsharks/dlp-0712-firebase-adminsdk-fbsvc-39b92e3a37.json"

RELAY_PIN = 27
BUZZER_PIN = 17
BUTTON_PIN = 23
VIBRATION_PIN = 22

ROW_PINS = [26, 16, 20, 21]
COL_PINS = [5, 6, 13, 19]

KEYPAD = [
    ["1", "2", "3", "A"],
    ["4", "5", "6", "B"],
    ["7", "8", "9", "C"],
    ["*", "0", "#", "D"]
]

I2C_ADDR = 0x3C
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY", "AKIAZ5OCCZAZF7X62QYT")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY", "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")
AWS_REGION = "ap-south-1"
COLLECTION_ID = "dlpbucketfaces"
SIMILARITY_THRESHOLD = 75

OTP_MAX_MINUTES = 10

VIBRATION_HIT_THRESHOLD = 3
VIBRATION_WINDOW_SECONDS = 5

# ---------------------------
# ========== SETUP ==========
# ---------------------------

GPIO.setwarnings(False)
GPIO.cleanup()
GPIO.setmode(GPIO.BCM)  # Pin numbering mode

# Setup keypad pins
for row_pin in ROW_PINS:
    GPIO.setup(row_pin, GPIO.OUT)
    GPIO.output(row_pin, GPIO.HIGH)  # rows idle high

for col_pin in COL_PINS:
    GPIO.setup(col_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Setup relay, buzzer, button, vibration sensor pins
GPIO.setup(RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)  # Relay off
GPIO.setup(BUZZER_PIN, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(VIBRATION_PIN, GPIO.IN)

# Setup buzzer PWM 1kHz
buzzer_pwm = GPIO.PWM(BUZZER_PIN, 1000)
buzzer_pwm.start(0)  # off initially

reader = MFRC522()
# ? List of authorized card IDs
AUTHORIZED_IDS = [3555744237,3279957986]
AUTHORIZED_CARDS = {
    3555744237: "SSG",
    3279957986: "Ashen",
}

i2c_serial = i2c(port=1, address=I2C_ADDR)
oled = ssd1306(i2c_serial)
font_default = FONT_PATH

if not os.path.exists(FIREBASE_SA_PATH):
    raise FileNotFoundError(f"Firebase service account JSON not found at {FIREBASE_SA_PATH}")
cred = credentials.Certificate(FIREBASE_SA_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()

rekognition = boto3.client(
    'rekognition',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

# ---------------------------
# ========== STATE ==========
# ---------------------------

mode = "normal"
input_buffer = ""
pw1_verified = False
new_password_stage = 0
new_password_temp = ""

hit_count = 0
start_time_vib = time.time()

def ensure_credentials_file():
    default = {"users": [{"username": "Admin", "password": "1234"}], "count": 1}
    if not os.path.exists(CRED_FILE):
        with open(CRED_FILE, "w") as f:
            json.dump(default, f)

ensure_credentials_file()

# ---------------------------
# ========== UTIL ===========
# ---------------------------

def update_display(message):
    try:
        img = Image.new("1", oled.size)
        draw = ImageDraw.Draw(img)
        lines = message.split("\n") if message else [""]
        for size in range(24, 6, -1):
            try:
                font = ImageFont.truetype(font_default, size)
            except Exception:
                font = ImageFont.load_default()
            max_w = max(draw.textlength(line, font=font) for line in lines)
            total_h = sum(font.getbbox(line)[3] for line in lines) + (len(lines)-1)*2
            if max_w <= oled.width and total_h <= oled.height:
                break
        y = (oled.height - total_h) // 2
        draw.rectangle((0, 0, oled.width, oled.height), fill=0)
        for line in lines:
            w = draw.textlength(line, font=font)
            draw.text(((oled.width - w) // 2, y), line, font=font, fill=255)
            y += font.getbbox(line)[3] + 2
        oled.display(img)
    except Exception as e:
        print("OLED update error:", e)

def relay_on(duration=5):
    print("Relay ON")
    GPIO.output(RELAY_PIN, GPIO.HIGH)  # Relay ON
    time.sleep(duration)
    GPIO.output(RELAY_PIN, GPIO.LOW)  # Relay OFF
    print("Relay OFF")

def buzzer_beep(duration=0.12):
    try:
        buzzer_pwm.ChangeDutyCycle(50)  # 50% duty cycle ON
        time.sleep(duration)
        buzzer_pwm.ChangeDutyCycle(0)   # OFF
    except Exception:
        pass

# ---------------------------
# ========== CREDENTIALS ==========
# ---------------------------

def load_credentials():
    global credentials
    try:
        with open(CRED_FILE, "r") as f:
            credentials = json.load(f)
    except Exception:
        credentials = {"users":[{"username":"Admin","password":"1234"}], "count":1}
        save_credentials()
    return credentials

def save_credentials():
    with open(CRED_FILE, "w") as f:
        json.dump(credentials, f, indent=2)

# ---------------------------
# ========== FIRESTORE OTP ==========
# ---------------------------

def get_latest_otp(db_client):
    try:
        otps_ref = db_client.collection("otps")
        query = otps_ref.order_by("createdAt", direction=firestore.Query.DESCENDING).limit(1)
        docs = list(query.stream())
        if not docs:
            return None, None
        data = docs[0].to_dict()
        return data.get("code"), data.get("createdAt")
    except Exception as e:
        print("get_latest_otp error:", e)
        return None, None

def is_otp_valid(otp_created_at, max_minutes=OTP_MAX_MINUTES):
    if not otp_created_at:
        return False
    try:
        if hasattr(otp_created_at, "to_datetime"):
            dt = otp_created_at.to_datetime()
        else:
            dt = otp_created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) <= timedelta(minutes=max_minutes)
    except Exception as e:
        print("is_otp_valid error:", e)
        return False

# ---------------------------
# ========== REKOGNITION ==========
# ---------------------------

def capture_live_image(filename='live.jpg'):
    try:
        picam2 = Picamera2()
        config = picam2.create_still_configuration()
        picam2.configure(config)
        picam2.start()
        time.sleep(1.2)
        picam2.capture_file(filename)
        picam2.close()
        return filename
    except Exception as e:
        print("Camera capture error:", e)
        return None

def identify_person(image_path):
    if not image_path or not os.path.exists(image_path):
        update_display("Image\nFailed")
        return
    try:
        with open(image_path, 'rb') as f:
            response = rekognition.search_faces_by_image(
                CollectionId=COLLECTION_ID,
                Image={'Bytes': f.read()},
                MaxFaces=1,
                FaceMatchThreshold=SIMILARITY_THRESHOLD
            )
        matches = response.get('FaceMatches', [])
        if matches:
            m = matches[0]
            name = m.get('Face', {}).get('ExternalImageId', 'Unknown')
            sim = m.get('Similarity', 0.0)
            update_display(f"Hello\n{name}")
            buzzer_beep()
            relay_on(5)
            update_display("Hello..")
        else:
            update_display("No match")
    except ClientError as e:
        print("AWS ClientError:", e)
        update_display("AWS Error")
    except Exception as e:
        print("Recognition error:", e)
        update_display("Recog Error")

# ---------------------------
# ========== KEYPAD HANDLING ==========
# ---------------------------

def scan_keypad():
    for row_num, row_pin in enumerate(ROW_PINS):
        GPIO.output(row_pin, GPIO.LOW)
        for col_num, col_pin in enumerate(COL_PINS):
            if GPIO.input(col_pin) == 0:
                time.sleep(0.02)  # debounce
                if GPIO.input(col_pin) == 0:
                    GPIO.output(row_pin, GPIO.HIGH)
                    return KEYPAD[row_num][col_num]
        GPIO.output(row_pin, GPIO.HIGH)
    return None

def handle_submit():
    global input_buffer, mode, pw1_verified, new_password_stage, new_password_temp, credentials

    if mode == "normal":
        creds = load_credentials()
        match = next((u for u in creds["users"] if u["password"] == input_buffer), None)
        if match:
            update_display(f"Welcome\n{match['username']}")
            buzzer_beep()
            relay_on(5)
            input_buffer = ""
            update_display("Hello..")
            return

        otp_code, otp_time = get_latest_otp(db)
        if otp_code and input_buffer == str(otp_code):
            if is_otp_valid(otp_time):
                update_display("Welcome\nOTP user")
                buzzer_beep()
                relay_on(5)
                update_display("Hello..")
            else:
                update_display("OTP Expired")
                time.sleep(2)
                update_display("Hello..")
            input_buffer = ""
            return

        update_display("Incorrect")
        buzzer_beep(0.2)
        time.sleep(1.5)
        update_display("Hello..")
        input_buffer = ""

    elif mode == "add":
        creds = load_credentials()
        if not pw1_verified:
            if creds["users"] and input_buffer == creds["users"][0]["password"]:
                pw1_verified = True
                input_buffer = ""
                update_display("Enter New\nPassword:")
                return
            else:
                update_display("Need Admin\nPassword")
                time.sleep(2)
                input_buffer = ""
                mode = "normal"
                update_display("Hello..")
                return

        if new_password_stage == 0:
            new_password_temp = input_buffer
            new_password_stage = 1
            input_buffer = ""
            update_display("Confirm New\nPassword:")
            return
        elif new_password_stage == 1:
            if input_buffer == new_password_temp:
                if any(u["password"] == input_buffer for u in creds["users"]):
                    update_display("Already exists")
                    time.sleep(2)
                    mode = "normal"
                    pw1_verified = False
                    new_password_stage = 0
                    input_buffer = ""
                    update_display("Hello..")
                    return
                creds["count"] = creds.get("count", len(creds["users"]))
                creds["count"] += 1
                new_user = {"username": f"PW{creds['count']}", "password": input_buffer}
                creds["users"].append(new_user)
                with open(CRED_FILE, "w") as f:
                    json.dump(creds, f, indent=2)
                update_display(f"Saved as\n{new_user['username']}")
                buzzer_beep(0.2)
                time.sleep(2)
            else:
                update_display("Mismatch\nTry again")
                buzzer_beep(0.2)
                time.sleep(2)
            mode = "normal"
            pw1_verified = False
            new_password_stage = 0
            input_buffer = ""
            update_display("Hello..")
            return

def print_key(key):
    global input_buffer, mode
    if key == "*":
        input_buffer = input_buffer[:-1]
        update_display("*" * len(input_buffer))
    elif key == "D":
        handle_submit()
    elif key == "A":
        mode = "add"
        input_buffer = ""
        update_display("Enter Admin\nPassword to add")
    elif key == "B":
        update_display("Capturing\nImage...")
        fname = capture_live_image()
        update_display("Identifying...")
        identify_person(fname)
    elif key in ["C", "#"]:
        pass
    else:
        input_buffer += key
        update_display("*" * len(input_buffer))

# ---------------------------
# ========== RFID THREAD ==========
# ---------------------------

def rfid_read_loop():
    print("RFID reader started")
    while True:
        status, TagType = reader.MFRC522_Request(reader.PICC_REQIDL)
        if status == reader.MI_OK:
            print("Card detected")
            status, uid = reader.MFRC522_Anticoll()
            if status == reader.MI_OK:
                uid_str = "".join(f"{i:02X}" for i in uid)
                print(f"Card UID: {uid_str}")
                buzzer_beep()
                relay_on(5)
                time.sleep(1)  # Prevent repeated reads
        time.sleep(0.1)

# ---------------------------
# ========== BUTTON CALLBACK ==========
# ---------------------------

def button_pressed_callback():
    print("Button pressed - manual unlock")
    update_display("Manually\nUnlocked")
    buzzer_beep(0.08)
    relay_on(5)
    update_display("Hello..")
    
# Remove any existing event detect on BUTTON_PIN before adding
try:
    GPIO.remove_event_detect(BUTTON_PIN)
except RuntimeError:
    pass  # no event detect previously

#GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=button_pressed_callback, bouncetime=300)

# ---------------------------
# ========== VIBRATION MONITOR ==========
# ---------------------------

def send_alert_to_firestore(alert_message="Hard vibration detected"):
    try:
        alert_data = {"alert": alert_message, "timestamp": firestore.SERVER_TIMESTAMP}
        ts = datetime.now(timezone.utc).strftime("%Y_%m_%d_%H_%M_%S_%f")
        docid = f"alert_{ts}_{uuid.uuid4().hex[:6]}"
        db.collection("door_alerts").document(docid).set(alert_data)
        print("Sent alert", docid)
    except Exception as e:
        print("Failed to send alert:", e)

def vibration_monitor():
    global hit_count, start_time_vib
    hit_count = 0
    start_time_vib = time.time()
    while True:
        if GPIO.input(VIBRATION_PIN) == 1:
            now = time.time()
            if now - start_time_vib > VIBRATION_WINDOW_SECONDS:
                hit_count = 0
                start_time_vib = now
            hit_count += 1
            print("Vibration:", hit_count)
            if hit_count >= VIBRATION_HIT_THRESHOLD:
                send_alert_to_firestore()
                hit_count = 0
            time.sleep(0.5)
        else:
            time.sleep(0.12)

# ---------------------------
# ========== FIRESTORE RELAY CONTROL ==========
# ---------------------------

def firestore_relay_control_loop():
    while True:
        try:
            docs = db.collection('lockEvents') \
                 .order_by('timestamp', direction=firestore.Query.DESCENDING) \
                 .limit(1) \
                 .stream()

            locked_value = None
            for doc in docs:
                data = doc.to_dict()
                locked_value = data.get('locked')

            if locked_value is False:
                GPIO.output(RELAY_PIN, GPIO.HIGH)  # Relay ON
                print("Locked is False, Relay ON")
            else:
                GPIO.output(RELAY_PIN, GPIO.LOW)   # Relay OFF
        except Exception as e:
            print("firestore_relay_control_loop error:", e)
        time.sleep(1)

# ---------------------------
# ========== IDLE DISPLAY LOOP ==========
# ---------------------------

def idle_display_loop():
    idle_msg = "Hello.."
    idle_interval = 8
    while True:
        update_display(idle_msg)
        time.sleep(idle_interval)

# ---------------------------
# ========== MAIN ==========
# ---------------------------

def main():
    global credentials
    credentials = load_credentials()
    update_display("Hello..")

    threading.Thread(target=rfid_read_loop, daemon=True).start()
    threading.Thread(target=vibration_monitor, daemon=True).start()
    threading.Thread(target=idle_display_loop, daemon=True).start()
    threading.Thread(target=firestore_relay_control_loop, daemon=True).start()

    print("System ready. Waiting for keypad / events.")

    last_key = None
    last_button_state = GPIO.input(BUTTON_PIN)

    try:
        while True:
            # Keypad scanning
            key = scan_keypad()
            if key and key != last_key:
                print_key(key)
                last_key = key
            elif key is None:
                last_key = None

            # Button polling (detect falling edge)
            current_button_state = GPIO.input(BUTTON_PIN)
            if last_button_state == GPIO.HIGH and current_button_state == GPIO.LOW:
                # Button pressed detected (falling edge)
                button_pressed_callback()
            last_button_state = current_button_state

            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("Exiting, cleaning up...")
    finally:
        buzzer_pwm.stop()
        GPIO.cleanup()
        sys.exit(0)

if __name__ == "__main__":
    main()
