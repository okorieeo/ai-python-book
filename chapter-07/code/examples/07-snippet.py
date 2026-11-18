from django.db import migrations

def fill_default_titles(apps, schema_editor):
    Conversation = apps.get_model("chat", "Conversation")      # historical model, not the live one
    Conversation.objects.filter(title="").update(title="New conversation")

class Migration(migrations.Migration):
    dependencies = [("chat", "0002_conversation_title")]
    operations = [migrations.RunPython(fill_default_titles, migrations.RunPython.noop)]
