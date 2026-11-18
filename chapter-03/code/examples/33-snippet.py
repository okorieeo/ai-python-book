def calculate_total(prices):
    total = 0
    for price in prices:
        print("DEBUG price:", price, "total so far:", total)
        total += price
    return total
