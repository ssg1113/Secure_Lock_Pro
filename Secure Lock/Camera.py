import boto3
import time
from picamera2 import Picamera2
from botocore.exceptions import ClientError

AWS_ACCESS_KEY = ''
AWS_SECRET_KEY = ''
AWS_REGION = 'ap-south-1'  # Change if necessary
COLLECTION_ID = 'dlpbucketfaces'  # Name of your Rekognition collection
SIMILARITY_THRESHOLD = 75   # Minimum similarity for a positive ID

rekognition = boto3.client(
    'rekognition',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

def capture_live_image(filename='live.jpg'):
    picam2 = Picamera2()
    config = picam2.create_still_configuration()
    picam2.configure(config)
    picam2.start()
    time.sleep(2)  # wait for camera to adjust
    picam2.capture_file(filename)
    picam2.close()
    print(f"Live image captured: {filename}")
    return filename

def identify_person(image_path):
    try:
        with open(image_path, 'rb') as image_file:
            response = rekognition.search_faces_by_image(
                CollectionId=COLLECTION_ID,
                Image={'Bytes': image_file.read()},
                MaxFaces=1,
                FaceMatchThreshold=SIMILARITY_THRESHOLD
            )
        print("Rekognition response:", response)

        matches = response.get('FaceMatches', [])
        if matches:
            match = matches[0]
            name = match.get('Face', {}).get('ExternalImageId', 'name')
            similarity = match.get('Similarity', 0)
            print(f"Person Identified: {name} (Similarity: {similarity:.2f}%)")
        else:
            print("Face not recorganized")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'InvalidParameterException':
            # This means no faces found in the image
            print("No faces detected in the image. Continuing without interruption.")
        else:
            # Re-raise unexpected exceptions
            raise e

if __name__ == '__main__':
    image = capture_live_image()
    identify_person(image)
