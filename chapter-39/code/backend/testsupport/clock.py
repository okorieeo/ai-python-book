class FakeClock:
    """Time you control. Pass it where the code takes `now`; never sleep in a test."""

    def __init__(self, start: float = 1_700_000_000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds
