---
name: migration-checker
description: Checks Django model changes against migrations for missing, destructive or slow migrations. Use after editing any models.py.
tools: Read, Grep, Glob, Bash
model: haiku
---
Compare the models with the migrations in the same app.

1. Run `python manage.py makemigrations --check --dry-run`. If it reports changes, a migration is missing: say so.
2. Read any new migration and flag operations that lose data (RemoveField, DeleteModel, AlterField that narrows a type), take long locks on a large table (adding a non-null column with a default, adding an index without CONCURRENTLY on PostgreSQL), or cannot be reversed.
3. Report findings only. Never edit a migration and never run migrate.
