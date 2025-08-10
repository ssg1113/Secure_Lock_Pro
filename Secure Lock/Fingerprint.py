import serial
import threading
import time
import os

ser = serial.Serial('/dev/serial0', baudrate=57600, timeout=1)
serial_lock = threading.Lock()
DB_FILE = "finger_db.txt"

def packet_header(packet_type, payload):
    header = b'\xEF\x01\xFF\xFF\xFF\xFF'
    length = len(payload) + 2
    packet = (
        header +
        bytes([packet_type]) +
        length.to_bytes(2, 'big') +
        payload
    )
    checksum = sum(packet[6:])
    packet += checksum.to_bytes(2, 'big')
    return packet

def send_cmd(payload, response_len=12):
    with serial_lock:
        packet = packet_header(0x01, payload)
        ser.write(packet)
        response = ser.read(response_len)
    return response

def set_led(mode=0x01, speed=0x03, color=0x01, count=0x00):
    # mode: 0x00=off, 0x01=on, 0x02=breathing, 0x03=flashing
    # color: 0x01=blue, 0x02=red, 0x03=purple, 0x04=green (try 0x04; fallback to 0x03 if not supported)
    payload = b'\x35' + bytes([mode, speed, color, count])
    send_cmd(payload)

def load_database():
    db = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            for line in f:
                if ':' in line:
                    name, id_str = line.strip().split(":")
                    db[int(id_str)] = name
    return db

def save_to_database(name, fid):
    with open(DB_FILE, "a") as f:
        f.write(f"{name}:{fid}\n")

def write_full_database(db):
    with open(DB_FILE, "w") as f:
        for fid in sorted(db):
            f.write(f"{db[fid]}:{fid}\n")

def get_next_available_id():
    db = load_database()
    for i in range(1, 256):
        if i not in db:
            return i
    return -1

def enroll_fingerprint():
    name = input("Enter user name to enroll: ").strip()
    if not name:
        print("Name cannot be empty.")
        return

    db = load_database()
    if name in db.values():
        print("Name already exists.")
        return

    fid = get_next_available_id()
    if fid == -1:
        print("No available fingerprint slots.")
        return

    print(f"Enrolling '{name}' at ID {fid}")
    set_led(mode=0x02, speed=0x03, color=0x01, count=0x00)  # Blue breathing LED
    print("Place your finger...")

    while True:
        resp = send_cmd(b'\x01')
        if resp and len(resp) > 9 and resp[9] == 0x00:
            break
        time.sleep(0.3)

    resp = send_cmd(b'\x02\x01')
    if not resp or len(resp) <= 9 or resp[9] != 0x00:
        print("Failed to convert image.")
        set_led(mode=0x03, speed=0x03, color=0x02, count=0x02)  # Red flash LED
        time.sleep(1)
        set_led(mode=0x00)
        return

    print("Remove finger...")
    time.sleep(2)
    print("Place the same finger again...")

    while True:
        resp = send_cmd(b'\x01')
        if resp and len(resp) > 9 and resp[9] == 0x00:
            break
        time.sleep(0.3)

    resp = send_cmd(b'\x02\x02')
    if not resp or len(resp) <= 9 or resp[9] != 0x00:
        print("Failed to convert second image.")
        set_led(mode=0x03, speed=0x03, color=0x02, count=0x02)
        time.sleep(1)
        set_led(mode=0x00)
        return

    resp = send_cmd(b'\x05')
    if not resp or len(resp) <= 9 or resp[9] != 0x00:
        print("Failed to create model.")
        set_led(mode=0x03, speed=0x03, color=0x02, count=0x02)
        time.sleep(1)
        set_led(mode=0x00)
        return

    fid_bytes = fid.to_bytes(2, 'big')
    store_cmd = b'\x06\x01' + fid_bytes
    resp = send_cmd(store_cmd)
    if resp and len(resp) > 9 and resp[9] == 0x00:
        save_to_database(name, fid)
        print(f"'{name}' enrolled successfully with ID {fid}")
        set_led(mode=0x01, speed=0x01, color=0x04, count=0x00)  # Green LED success
        time.sleep(2)
        set_led(mode=0x00)
    else:
        print("Failed to store fingerprint.")
        set_led(mode=0x03, speed=0x03, color=0x02, count=0x02)
        time.sleep(1)
        set_led(mode=0x00)

def list_database():
    db = load_database()
    print("\nEnrolled Users:")
    if db:
        for fid in sorted(db):
            print(f"  ID {fid:03d} : {db[fid]}")
    else:
        print("  (No users enrolled yet)")
    print()

def remove_fingerprint_with_confirmation():
    db = load_database()
    if not db:
        print("No fingerprints to remove.")
        return
    list_database()
    val = input("Enter the ID or Name to remove: ").strip()
    fid = None
    name = None
    try:
        fid = int(val)
        name = db.get(fid, None)
    except ValueError:
        for k, v in db.items():
            if v.lower() == val.lower():
                fid = k
                name = v
                break

    if fid is None or fid not in db:
        print("Not found in database.")
        return

    print("For confirmation, please scan the finger you wish to delete (must match record).")
    set_led(mode=0x02, speed=0x03, color=0x01, count=0x00)  # Blue breathing LED
    confirmed = False
    while not confirmed:
        # Wait for finger
        while True:
            resp = send_cmd(b'\x01')
            if resp and len(resp) > 9 and resp[9] == 0x00:
                break
            time.sleep(0.2)
        # Convert and search
        resp = send_cmd(b'\x02\x01')
        if resp and len(resp) > 9 and resp[9] == 0x00:
            search_cmd = b'\x04\x01\x00\x00\x01\x00'
            resp2 = send_cmd(search_cmd, response_len=16)
            if resp2 and len(resp2) > 13 and resp2[9] == 0x00:
                confirmed_id = (resp2[10] << 8) | resp2[11]
                if confirmed_id == fid:
                    confirmed = True
                    print("Finger confirmed for deletion. Deleting...")
                    set_led(mode=0x01, speed=0x01, color=0x04)
                    time.sleep(1)
                    set_led(mode=0x00)
                    page_id_bytes = fid.to_bytes(2, "big")
                    del_cmd = b'\x0C' + page_id_bytes + b'\x00\x01'
                    resp3 = send_cmd(del_cmd)
                    if resp3 and len(resp3)>9 and resp3[9] == 0x00:
                        print("Fingerprint deleted.")
                        db.pop(fid)
                        write_full_database(db)
                    else:
                        print(f"Error deleting from sensor: code {resp3[9] if resp3 and len(resp3)>9 else 'unknown'}")
                else:
                    print("Scanned finger does not match the record to be deleted. Try again.")
                    set_led(mode=0x03, speed=0x03, color=0x02, count=0x02)
                    time.sleep(1)
                    set_led(mode=0x00)
            else:
                print("Scanned finger not recognized. Try again.")
                set_led(mode=0x03, speed=0x03, color=0x02, count=0x02)
                time.sleep(1)
                set_led(mode=0x00)
        else:
            print("Could not process finger. Try again.")
            set_led(mode=0x03, speed=0x03, color=0x02, count=0x02)
            time.sleep(1)
            set_led(mode=0x00)

        # Wait for finger removal before retrying
        while True:
            resp = send_cmd(b'\x01')
            if resp and len(resp) > 9 and resp[9] == 0x02:
                break
            time.sleep(0.2)

def background_search_loop():
    while True:
        try:
            set_led(mode=0x02, speed=0x03, color=0x01, count=0x00)  # Blue waiting LED
            # Wait for finger
            while True:
                resp = send_cmd(b'\x01')
                if resp and len(resp) > 9 and resp[9] == 0x00:
                    break
                time.sleep(0.2)

            # Convert image to template
            resp = send_cmd(b'\x02\x01')
            if not (resp and len(resp) > 9 and resp[9] == 0x00):
                # Fail converting image
                set_led(mode=0x03, speed=0x03, color=0x02, count=0x02)
                time.sleep(1)
                set_led(mode=0x00)
                continue

            # Search fingerprint
            search_cmd = b'\x04\x01\x00\x00\x01\x00'
            resp2 = send_cmd(search_cmd, response_len=16)
            if resp2 and len(resp2) > 13 and resp2[9] == 0x00:
                matched_id = (resp2[10] << 8) | resp2[11]
                db = load_database()
                name = db.get(matched_id, "Unknown User")
                print(f"\nDetected: {name} (ID {matched_id})")
                set_led(mode=0x01, speed=0x01, color=0x04)
                time.sleep(1)
                set_led(mode=0x00)
            else:
                print("\nFingerprint not recognized.")
                set_led(mode=0x03, speed=0x03, color=0x02, count=0x02)
                time.sleep(1)
                set_led(mode=0x00)

            # Wait for finger removal before next
            while True:
                resp = send_cmd(b'\x01')
                if resp and len(resp) > 9 and resp[9] == 0x02:
                    break
                time.sleep(0.2)

        except serial.serialutil.SerialException as e:
            print(f"Serial error in background thread: {e}")
            time.sleep(2)

def menu_loop():
    while True:
        print("\nMenu:")
        print("1. Enroll Fingerprint")
        print("2. Show Enrolled Users")
        print("3. Remove Fingerprint")
        print("Q. Quit")
        choice = input("Select option: ").strip().lower()
        if choice == '1':
            enroll_fingerprint()
        elif choice == '2':
            list_database()
        elif choice == '3':
            remove_fingerprint_with_confirmation()
        elif choice == 'q':
            print("Goodbye!")
            ser.close()
            os._exit(0)
        else:
            print("Invalid option.")

if __name__ == "__main__":
    print("=== R503 Fingerprint System ===")
    search_thread = threading.Thread(target=background_search_loop, daemon=True)
    search_thread.start()
    menu_loop()
