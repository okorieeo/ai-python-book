from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    """Must run BEFORE the migration that creates Chunk (it needs the "vector" type).
    Creating an extension needs a database user that is allowed to (the default superuser in the pgvector Docker image is)."""
    dependencies = []
    operations = [VectorExtension()]
