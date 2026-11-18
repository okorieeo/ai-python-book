age_text = "28"
age_number = int(age_text)       # str -> int
print(age_number + 1)            # 29

print(str(99) + " problems")     # int -> str
print(float("3.5") * 2)          # 7.0

answer = input("What is your name? ")   # input() ALWAYS returns a string
print(f"Welcome, {answer}!")
