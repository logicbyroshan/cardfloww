import requests

s = requests.Session()

r1 = s.get('http://127.0.0.1:8008/api/health/')
print("Health:", r1.status_code, r1.json())

r2 = s.get('http://127.0.0.1:8008/api/banners/')
print("Banners:", r2.status_code, r2.json()['banners'][0]['title'])

r3 = s.post('http://127.0.0.1:8008/api/auth/login/', json={'email': 'admin', 'password': 'admin123', 'remember_me': True})
print("Login:", r3.status_code, r3.json())

r4 = s.get('http://127.0.0.1:8008/api/auth/me/')
print("Auth/me:", r4.status_code, r4.json())
