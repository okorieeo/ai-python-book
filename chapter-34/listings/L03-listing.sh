python manage.py makemigrations privacy
python manage.py migrate
python manage.py shell -c "
import hashlib
from django.utils import timezone
from privacy.models import LegalDocument
for kind, path in (('terms', 'legal/terms_template.md'), ('privacy', 'legal/privacy_template.md')):
    text = open(path, 'rb').read()
    LegalDocument.objects.get_or_create(kind=kind, version='2026-11-05', defaults=dict(
        effective_at=timezone.now(), sha256=hashlib.sha256(text).hexdigest(),
        url=f'https://example.com/{kind}'))
"
