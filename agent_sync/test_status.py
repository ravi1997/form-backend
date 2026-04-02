import requests
import json

login_url = "http://localhost:8051/form/api/v1/auth/login"
resp = requests.post(login_url, json={"username": "testuser_frontend", "password": "TestPass123!"})
data = resp.json()
token = data['data']['access_token']

status_url = "http://localhost:8051/form/api/v1/user/status"
resp2 = requests.get(status_url, headers={"Authorization": f"Bearer {token}"})
print(json.dumps(resp2.json(), indent=2))
