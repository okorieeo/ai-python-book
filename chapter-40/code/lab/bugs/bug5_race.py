"""Symptom: two quick requests both spend the last credits and the balance goes negative."""
from typing import Callable


class Wallet:
    def __init__(self, balance: int, pause: Callable[[], None] = lambda: None):
        self.balance = balance
        self._pause = pause          # a test hook that widens the gap between the check and the update

    def spend(self, amount: int) -> bool:
        if self.balance >= amount:
            self._pause()
            self.balance -= amount
            return True
        return False
