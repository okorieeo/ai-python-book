def apply_discount(price_minor, percent):
    discount = price_minor * percent / 100
    return price_minor - discount


def total(items):
    result = 0
    for item in items:
        result += apply_discount(item["price"], item["discount"])
    return result


if __name__ == "__main__":
    print(total([{"price": 1999, "discount": 10}, {"price": 500, "discount": 0}]))
