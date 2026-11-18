# Before
def f(a, b):
    if a == "pro":
        return b * 0.003
    else:
        return b * 0.005

# After
PRICE_PER_1K_TOKENS = {"pro": 0.003, "free": 0.005}

def calculate_cost(plan: str, tokens: int) -> float:
    """Return the cost in USD for a number of tokens on a given plan."""
    return tokens / 1000 * PRICE_PER_1K_TOKENS[plan]
