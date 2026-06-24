import requests

BLYNK_TOKEN = "r_TQaT4713CU331lau-06BZyfZNOgQas"

result = "TEST_FROM_FLASK"

url = f"https://blynk.cloud/external/api/update?token={BLYNK_TOKEN}&v1={result}"

r = requests.get(url)

print("Status:", r.status_code)
print("Response:", r.text)