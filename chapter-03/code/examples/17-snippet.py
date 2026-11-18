import requests

response = requests.get("https://api.github.com")
print(response.status_code)       # 200 means success
print(response.json())            # parsed JSON as a dict
