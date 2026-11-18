def divide(a: float, b: float) -> float:
    return a / b

try:
    result = divide(10, 0)
except ZeroDivisionError:
    print("You cannot divide by zero")
except (TypeError, ValueError) as error:
    print(f"Bad input: {error}")
else:
    print("Result:", result)          # runs only if no exception happened
finally:
    print("Always runs (cleanup)")    # runs no matter what
