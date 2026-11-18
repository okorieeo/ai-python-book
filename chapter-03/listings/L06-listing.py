user = {"id": 1, "name": "Ada", "plan": "free"}

print(user["name"])                  # Ada
print(user.get("email"))             # None (no error if the key is missing)
print(user.get("email", "unknown"))  # unknown (custom default)

user["plan"] = "pro"                 # update
user["email"] = "ada@example.com"    # add new key
del user["id"]                       # remove key

for key, value in user.items():
    print(key, "->", value)
