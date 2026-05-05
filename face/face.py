import cv2
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

# AWS client
client = boto3.client(
    "rekognition",
    region_name=os.getenv("AWS_DEFAULT_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

# Load stored image
with open("face3.jpg", "rb") as f:
    stored_image = f.read()

# Open webcam
cap = cv2.VideoCapture(0)

print("📷 Press SPACE to capture and login")

while True:
    ret, frame = cap.read()
    cv2.imshow("Webcam Login", frame)

    key = cv2.waitKey(1)

    # Press SPACE to capture
    if key == 32:
        cv2.imwrite("captured.jpg", frame)
        print("📸 Image Captured")
        break

    # Press ESC to exit
    if key == 27:
        cap.release()
        cv2.destroyAllWindows()
        exit()

cap.release()
cv2.destroyAllWindows()

# Read captured image
with open("captured.jpg", "rb") as f:
    captured_image = f.read()

# Compare faces
response = client.compare_faces(
    SourceImage={'Bytes': stored_image},
    TargetImage={'Bytes': captured_image},
    SimilarityThreshold=80
)

matches = response.get("FaceMatches", [])

if matches:
    similarity = matches[0]["Similarity"]
    print(f"✅ LOGIN SUCCESS — Similarity: {similarity:.2f}%")
else:
    print("❌ LOGIN FAILED")