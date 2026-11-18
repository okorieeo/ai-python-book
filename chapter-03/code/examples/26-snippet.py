import json

data = {"name": "Ada", "skills": ["python", "django"], "active": True, "manager": None}

text = json.dumps(data, indent=2)     # Python -> JSON string
print(text)

parsed = json.loads(text)             # JSON string -> Python
print(parsed["skills"][0])            # python

# Save and load JSON files
with open("user.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

with open("user.json", "r", encoding="utf-8") as f:
    loaded = json.load(f)
