import requests

r1 = requests.get('http://127.0.0.1:8000/api/health/')
print("Health:", r1.status_code, r1.text[:200])

r2 = requests.get('http://127.0.0.1:8000/api/banners/')
print("Banners:", r2.status_code, r2.text[:200])
