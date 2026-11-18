from django.db import migrations


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.get_or_create(code="free", defaults=dict(
        name="Free", daily_message_limit=10, price_usd_cents=0, sort_order=0))
    Plan.objects.get_or_create(code="pro", defaults=dict(
        name="Pro", daily_message_limit=500, price_usd_cents=1200, sort_order=1))


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
