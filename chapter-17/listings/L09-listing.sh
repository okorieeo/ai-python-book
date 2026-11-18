python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> from chat import services
>>> from audit.models import AuditEvent
>>> ada = get_user_model().objects.first()
>>> conv = services.create_conversation(user=ada, title="Throwaway")
>>> services.delete_conversation(user=ada, conversation=conv)
>>> event = AuditEvent.objects.first()
>>> event.action, event.target_type
('chat.conversation_deleted', 'conversation')
>>> event.delete()
PermissionError: Audit events cannot be deleted by the application.
