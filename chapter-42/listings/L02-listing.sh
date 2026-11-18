$ python manage.py makemigrations --check --dry-run
No changes detected
$ echo $?
0

# now add a field to a model and forget the migration:
$ python manage.py makemigrations --check --dry-run
Migrations for 'attachments':
  attachments/migrations/0002_attachment_language.py
    + Add field language to attachment
$ echo $?
1
