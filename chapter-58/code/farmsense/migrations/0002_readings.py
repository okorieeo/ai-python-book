from django.db import migrations

from farmsense_core.partitions import CREATE_PARENT_SQL, partitions_to_create
from datetime import date


def forward_sql():
    return CREATE_PARENT_SQL + ";\n".join(partitions_to_create(date.today(), ahead=2)) + ";"


class Migration(migrations.Migration):
    """Creates the partitioned readings table, a default partition, and this month plus two more.
    Run `ensure_partitions` (a Celery beat task) afterwards so that new months keep appearing."""
    dependencies = [("farmsense", "0001_initial")]
    operations = [migrations.RunSQL(forward_sql(), reverse_sql="DROP TABLE IF EXISTS farmsense_reading CASCADE")]
