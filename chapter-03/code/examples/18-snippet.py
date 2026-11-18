# project layout
# app/
#   __init__.py
#   billing.py
#   main.py

# billing.py
def calculate_cost(tokens: int) -> float:
    return tokens / 1000 * 0.003

# main.py
from billing import calculate_cost
print(calculate_cost(5000))
