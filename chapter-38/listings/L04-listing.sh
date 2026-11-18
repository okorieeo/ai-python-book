python manage.py shell -c "
from django.contrib.auth import get_user_model
from payments.models import Payment
from payments.services import refund_payment
from core.payments.money import Money
staff = get_user_model().objects.get(email='you@example.com')
p = Payment.objects.get(reference='pay_...')
print(refund_payment(staff_user=staff, payment=p, amount=Money(100000, p.currency), reason='test refund'))
"
