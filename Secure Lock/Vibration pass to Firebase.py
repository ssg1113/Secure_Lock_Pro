import sys
sys.path.append('/home/techsharks/firebase_lib')

import time
import RPi.GPIO as GPIO
import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# GPIO setup
VIBRATION_PIN = 22
GPIO.setmode(GPIO.BCM)
GPIO.setup(VIBRATION_PIN, GPIO.IN)

# Firebase setup
cred = credentials.Certificate('/home/techsharks/dlp-0712-firebase-adminsdk-fbsvc-39b92e3a37.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

hit_count = 0
time_window = 5  # seconds
start_time = time.time()

def send_alert_to_firestore():
    alert_data = {
        "alert": "Hard vibration detected 3 times",
        "timestamp": firestore.SERVER_TIMESTAMP
    }
    timestamp_str = datetime.datetime.now().strftime("%Y_%m_%d_%H:%M:%S")
    doc_id = f"alert_{timestamp_str}"

    db.collection("door_alerts").document(doc_id).set(alert_data)  # adds a new alert document each time
    print("Alert sent to Firestore")

try:
    while True:
        if GPIO.input(VIBRATION_PIN) == GPIO.HIGH:
            current_time = time.time()
            if current_time - start_time > time_window:
                hit_count = 0
                start_time = current_time
            
            hit_count += 1
            print(f"Hit detected: {hit_count}")
            
            if hit_count >= 3:
                send_alert_to_firestore()
                hit_count = 0  # reset after alert
            
            time.sleep(0.5)  # debounce delay
        else:
            time.sleep(0.1)
except KeyboardInterrupt:
    GPIO.cleanup()
