# for loop over a range of numbers (0 to 4)
for i in range(5):
    print(i)

# for loop over a list
models = ["fast", "balanced", "smart"]
for model in models:
    print(f"Testing {model}")

# enumerate gives index and value
for index, model in enumerate(models, start=1):
    print(index, model)

# while loop
attempts = 0
while attempts < 3:
    print(f"Attempt {attempts + 1}")
    attempts += 1          # same as attempts = attempts + 1
 break and continue
for number in range(1, 11):
    if number % 2 == 0:
        continue           # skip even numbers
    if number > 7:
        break              # stop the loop entirely
    print(number)          # prints 1, 3, 5, 7
