import requests

url = "https://smart-farming-ai-9ps1.onrender.com/analyze"

with open("test.jpg", "rb") as f:
    r = requests.post(url, data=f.read())

print(r.status_code)
print(r.text)