"""Sample code for the mutation demo: coupon pricing for the billing screen."""

FREE_SHIPPING_FROM = 5000          # cents


def apply_coupon(cents, percent):
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    return cents - cents * percent // 100


def shipping(cents):
    if cents >= FREE_SHIPPING_FROM:
        return 0
    return 499


def order_total(cents, percent):
    discounted = apply_coupon(cents, percent)
    return discounted + shipping(discounted)
