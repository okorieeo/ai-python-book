class Notifier:
    def send(self, message: str) -> None:
        raise NotImplementedError("Subclasses must implement send()")

class EmailNotifier(Notifier):
    def send(self, message: str) -> None:
        print(f"Sending EMAIL: {message}")

class SmsNotifier(Notifier):
    def send(self, message: str) -> None:
        print(f"Sending SMS: {message}")

for notifier in [EmailNotifier(), SmsNotifier()]:
    notifier.send("Your report is ready")     # same call, different behavior
