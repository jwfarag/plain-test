"""A tiny shopping cart: the code under test in the plaintest example."""


class CartError(Exception):
    pass


class Cart:
    def __init__(self):
        self.items: list[tuple[str, float]] = []
        self.discount = 0.0

    def add(self, name: str, price: float) -> None:
        self.items.append((name, price))

    def subtotal(self) -> float:
        return sum(price for _, price in self.items)

    def apply_discount(self, amount: float) -> None:
        """Apply a fixed-amount discount code."""
        self.discount = amount

    def total(self) -> float:
        return max(0.0, self.subtotal() - self.discount)

    def checkout(self) -> float:
        if not self.items:
            raise CartError("Cannot check out: the cart is empty.")
        return self.total()
