"""A fake Paystack for tests. It remembers what it was asked and behaves like the documented API."""
import itertools

from .errors import PaystackApiError
from .fixtures import DAY, START, authorization_obj, customer_obj, iso, subscription_obj
from .snapshots import parse_time


class FakeGateway:
    def __init__(self, config=None, now: int = START):
        self.config, self.now = config, now
        self.calls = []
        self._n = itertools.count(1)
        self.transactions = {}       # reference -> what we initialized
        self.results = {}            # reference -> what verify returns once the customer has paid
        self.subscriptions = {}
        self.fail_next = None        # set to an exception to make the next call fail once

    def _maybe_fail(self):
        if self.fail_next:
            error, self.fail_next = self.fail_next, None
            raise error

    def initialize_transaction(self, params):
        self.calls.append(("initialize_transaction", params))
        self._maybe_fail()
        if params["reference"] in self.transactions:
            raise PaystackApiError("Duplicate Transaction Reference", 400)
        self.transactions[params["reference"]] = params
        code = f"ac_{next(self._n):04d}"
        return {"authorization_url": f"https://checkout.paystack.com/{code}", "access_code": code,
                "reference": params["reference"]}

    def pay(self, reference, *, status="success", customer="CUS_001", auth="AUTH_001", reusable=True, amount=None):
        """Simulate the customer finishing (or abandoning) the payment page."""
        params = self.transactions[reference]
        plan = None
        if params.get("plan"):
            plan_cfg = self.config.plan_for_code(params["plan"])
            plan = {"plan_code": params["plan"], "amount": plan_cfg.amount if plan_cfg else params["amount"]}
        data = {"id": next(self._n) + 5000, "domain": "test", "status": status, "reference": reference,
                "amount": params["amount"] if amount is None else amount, "currency": params["currency"],
                "gateway_response": "Successful" if status == "success" else "Declined", "channel": "card",
                "metadata": params["metadata"], "customer": customer_obj(customer, params["email"]),
                "authorization": authorization_obj(auth, reusable), "plan": plan or {}}
        self.results[reference] = data
        if params.get("plan") and status == "success":       # Paystack subscribes the customer after the first payment
            self._new_subscription(customer, params["plan"], auth, START + 30 * DAY, params["email"])
        return data

    def verify_transaction(self, reference):
        self.calls.append(("verify_transaction", reference))
        self._maybe_fail()
        if reference in self.results:
            return self.results[reference]
        if reference in self.transactions:
            return {"status": "abandoned", "reference": reference}
        raise PaystackApiError("Transaction reference not found", 404)

    def _new_subscription(self, customer, plan_code, auth, next_payment, email="ada@example.com"):
        code = f"SUB_{next(self._n):03d}"
        sub = subscription_obj(code=code, token=f"tok_{code}", plan_code=plan_code, customer=customer,
                               next_payment=next_payment, auth=auth)
        sub["customer"]["email"] = email
        self.subscriptions[code] = sub
        return sub

    def fetch_customer(self, email_or_code):
        self.calls.append(("fetch_customer", email_or_code))
        self._maybe_fail()
        subs = [s for s in self.subscriptions.values() if s["customer"]["customer_code"] == email_or_code]
        return {"customer_code": email_or_code, "email": "ada@example.com", "subscriptions": subs}

    def create_subscription(self, params):
        self.calls.append(("create_subscription", params))
        self._maybe_fail()
        start = parse_time(params["start_date"]) if params.get("start_date") else self.now + 30 * DAY
        return self._new_subscription(params["customer"], params["plan"], params["authorization"], start)

    def fetch_subscription(self, code):
        self.calls.append(("fetch_subscription", code))
        self._maybe_fail()
        if code not in self.subscriptions:
            raise PaystackApiError("Subscription not found", 404)
        return self.subscriptions[code]

    def disable_subscription(self, code, token):
        self.calls.append(("disable_subscription", code, token))
        sub = self.fetch_subscription(code)
        if token != sub["email_token"]:
            raise PaystackApiError("Invalid token", 400)
        sub["status"] = "non-renewing"
        return {}

    def enable_subscription(self, code, token):
        self.calls.append(("enable_subscription", code, token))
        sub = self.fetch_subscription(code)
        if token != sub["email_token"]:
            raise PaystackApiError("Invalid token", 400)
        sub["status"] = "active"
        return {}

    def manage_link(self, code):
        self.calls.append(("manage_link", code))
        return f"https://paystack.com/manage/subscriptions/{code}"

    def called(self, name):
        return [c for c in self.calls if c[0] == name]
