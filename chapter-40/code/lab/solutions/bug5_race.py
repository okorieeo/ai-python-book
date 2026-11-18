import threading
from typing import Callable


class Wallet:
    def __init__(self, balance: int, pause: Callable[[], None] = lambda: None):
        self.balance = balance
        self._pause = pause
        self._lock = threading.Lock()

    def spend(self, amount: int) -> bool:
        with self._lock:             # check and update must happen as one step (in Django: select_for_update or an F() update)
            if self.balance >= amount:
                self._pause()
                self.balance -= amount
                return True
            return False
