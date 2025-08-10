import sys
import time
import RPi.GPIO as GPIO

sys.path.append('/home/techsharks/firebase_lib')
from firebase_admin import credentials, firestore
import firebase_admin

cred = credentials.Certificate('/home/techsharks/dlp-0712-firebase-adminsdk-fbsvc-39b92e3a37.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

RELAY_PIN = 27
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)

print("Starting relay control based on Firestore 'locked' value. Press Ctrl+C to stop.")

try:
    while True:
        docs = db.collection('lockEvents') \
                 .order_by('timestamp', direction=firestore.Query.DESCENDING) \
                 .limit(1) \
                 .stream()

        locked_value = None
        for doc in docs:
            data = doc.to_dict()
            locked_value = data.get('locked')

        if locked_value is False:
            GPIO.output(RELAY_PIN, GPIO.HIGH)  # Relay ON (active LOW)
            print("Locked is False, Relay ON")
        else:
            GPIO.output(RELAY_PIN, GPIO.LOW)  # Relay OFF (active HIGH)
            # no print here

        time.sleep(6)

except KeyboardInterrupt:
    print("Program stopped by user.")

finally:
    GPIO.cleanup()
    print("GPIO cleaned up.")
