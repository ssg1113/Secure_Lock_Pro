import sys
sys.path.append('/home/techsharks/firebase_lib')

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone, timedelta

def initialize_firestore():
    cred = credentials.Certificate('/home/techsharks/dlp-0712-firebase-adminsdk-fbsvc-39b92e3a37.json')
    firebase_admin.initialize_app(cred)
    return firestore.client()

def get_latest_otp(db):
    try:
        otps_ref = db.collection("otps")
        query = otps_ref.order_by("createdAt", direction=firestore.Query.DESCENDING).limit(1)
        docs = query.stream()

        for doc in docs:
            data = doc.to_dict()
            otp_code = data.get('code')
            otp_timestamp = data.get('createdAt')
            return otp_code, otp_timestamp
        
        return None, None
    except Exception as e:
        print("Error fetching latest OTP:", e)
        return None, None

def is_otp_valid(otp_created_at, max_minutes=10):
    if otp_created_at is None:
        return False

    # Convert Firestore timestamp to datetime
    if hasattr(otp_created_at, 'to_datetime'):
        created_at_dt = otp_created_at.to_datetime()
    else:
        created_at_dt = otp_created_at

    if created_at_dt.tzinfo is None:
        created_at_dt = created_at_dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = now - created_at_dt
    return delta <= timedelta(minutes=max_minutes)

def main():
    db = initialize_firestore()
    print("Enter 'exit' to quit.")

    while True:
        user_input = input("Enter password (OTP): ").strip()
        if user_input.lower() == 'exit':
            print("Exiting.")
            break

        otp_code, otp_created_at = get_latest_otp(db)
        if otp_code is None:
            print("No OTP code found.")
            continue

        if not is_otp_valid(otp_created_at):
            print(f"OTP expired. It was created at {otp_created_at}. Please use a recent OTP.")
            continue

        if user_input == otp_code:
            print("Password accepted! OTP is correct and within 10 minutes.")
        else:
            print("Incorrect password or OTP.")

if __name__ == "__main__":
    main()