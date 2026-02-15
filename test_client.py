
import requests
import os

url = 'http://localhost:8000/upload-video'
video_path = 'IMG_5720.MOV'
files = {'video': open(video_path, 'rb')}
data = {'emotion': 'General'}

print(f"Sending request to {url}...")
try:
    response = requests.post(url, files=files, data=data, timeout=120)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
