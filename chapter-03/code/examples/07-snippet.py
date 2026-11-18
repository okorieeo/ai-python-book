def calculate_cost(tokens: int, price_per_1k: float = 0.003) -> float:
    """Return the cost of a number of tokens."""
    return (tokens / 1000) * price_per_1k

print(calculate_cost(2500))                       # uses default price
print(calculate_cost(2500, price_per_1k=0.01))    # keyword argument
