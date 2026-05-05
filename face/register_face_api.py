import requests
import base64
import os

def register_face(mobile_number, image_path):
    url = "http://localhost:8000/api/face/register/"
    
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    
    payload = {
        "mobile_number": mobile_number,
        "face_image_base64": encoded_string
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 201:
            print(f"✅ Successfully registered face for {mobile_number}")
        else:
            print(f"❌ Failed to register face: {response.json()}")
    except Exception as e:
        print(f"❌ Error connecting to server: {str(e)}")

if __name__ == "__main__":
    mobile = input("Enter mobile number: ")
    img = "captured.jpg" # Default from face.py
    if os.path.exists(img):
        register_face(mobile, img)
    else:
        print(f"❌ {img} not found. Please run face.py first to capture an image.")
