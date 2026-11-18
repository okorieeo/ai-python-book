class Product:
    def __init__(self, price_cents: int) -> None:
        self.price_cents = price_cents

    @property
    def price(self) -> float:
        return self.price_cents / 100

p1 = Product(1999)
print(p1.price)                # 19.99 (used like an attribute, no parentheses)
