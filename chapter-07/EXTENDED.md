# Chapter 7 — Database Design and Data Modeling: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## From Schema to Django Models › Reading the mapping

| **Design decision** | **In Django** |
|---|---|
| Foreign key + delete rule | `ForeignKey(..., on_delete=models.CASCADE / PROTECT / SET_NULL)` |
| Reverse access | `related_name="messages"` lets you write `conversation.messages.all()` |
| Fixed set of values | `TextChoices` plus the `choices=` argument; add a `CheckConstraint` if you also want the database to enforce it |
| Composite index | `Meta.indexes = [models.Index(fields=[...])]` |
| Unique rule / partial unique | `Meta.constraints = [UniqueConstraint(...)]` |
| JSONB column | `JSONField` |
| Created/updated timestamps | `auto_now_add=True`, `auto_now=True` |
| Surrogate primary key | Automatic `id` (BigAutoField by default in new projects) |


## Migrations: Evolving the Schema Safely › Data migrations

Sometimes you must transform existing data, such as filling a new column from old ones. Use a `RunPython` migration with a reversible function and keep it fast and idempotent:

**python**

```python
from django.db import migrations

def fill_default_titles(apps, schema_editor):
    Conversation = apps.get_model("chat", "Conversation")      # historical model, not the live one
    Conversation.objects.filter(title="").update(title="New conversation")

class Migration(migrations.Migration):
    dependencies = [("chat", "0002_conversation_title")]
    operations = [migrations.RunPython(fill_default_titles, migrations.RunPython.noop)]
```


## Indexes and Query Performance › Other everyday performance habits

- **Select only what you need:**  `.only("id", "title")` or `.values_list(...)` for large rows (messages hold big text).
- **Always paginate** lists. Never return unbounded results.
- **Batch writes:**  `bulk_create(list_of_objects)` instead of saving 1,000 rows one by one.
- **Aggregate in the database,** not in Python: use `Sum`, `Count`, `Avg` rather than loading rows and looping.
- **Avoid `COUNT(*)` on huge tables for every request;** cache it or keep an approximate counter.

## Indexes and Query Performance › Pagination: offset vs. keyset

`LIMIT 50 OFFSET 100000` forces the database to walk past 100,000 rows before returning 50, so deep pages get slower and slower, and rows inserted meanwhile cause duplicates or gaps. **Keyset (cursor) pagination** remembers the last row seen and continues after it, which stays fast at any depth:

**SQL**

```sql
-- Page 1
SELECT id, created_at, content FROM messages
WHERE conversation_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 50;

-- Next page: pass the created_at and id of the last row you received
SELECT id, created_at, content FROM messages
WHERE conversation_id = 7
  AND (created_at, id) < ('2026-11-01 09:30:00+00', 1234)
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Django REST Framework provides `CursorPagination` for exactly this; use it for chat history, feeds and any list that keeps growing.
