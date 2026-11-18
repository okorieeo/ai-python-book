numbers = [1, 2, 3, 4, 5, 6]

squares = [n * n for n in numbers]                 # [1, 4, 9, 16, 25, 36]
evens = [n for n in numbers if n % 2 == 0]         # [2, 4, 6]
lookup = {n: n * n for n in numbers}               # {1: 1, 2: 4, ...}

users = [{"name": "Ada", "active": True}, {"name": "Bo", "active": False}]
active_names = [u["name"] for u in users if u["active"]]   # ['Ada']
