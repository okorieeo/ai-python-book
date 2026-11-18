WEBHOOKS_DEV=1 python manage.py shell -c "
from accounts.models import User
from notifications.outbound import queue_event
user = User.objects.get(email='ada@example.com')
print(len(queue_event(user, 'document.ready', {'document_id': '942c5fc3'})), 'delivery queued')"

WEBHOOKS_DEV=1 python manage.py deliver_webhooks
 example output
1 delivery queued
1 webhook(s) delivered
