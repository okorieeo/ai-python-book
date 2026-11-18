from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    """Runs CREATE EXTENSION IF NOT EXISTS vector. It must come before the model migration."""

    initial = True
    dependencies = []
    operations = [VectorExtension()]
