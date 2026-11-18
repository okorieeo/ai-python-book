"""Verification helper (not part of the book code): load the Django-dependent toolset with stub modules."""
import sys, types, unittest
from unittest import mock

for name in ["django", "django.db", "django.utils", "django.conf", "audit.services", "audit",
             "schedule.services", "schedule.models", "tasks.services", "tasks.models"]:
    sys.modules.setdefault(name, mock.MagicMock())
# the real pure helpers the toolset imports must stay real
import schedule.availability, tasks.planning  # noqa
sys.modules["tasks.models"].Task = type("Task", (), {"DoesNotExist": type("DoesNotExist", (Exception,), {})})
sys.modules["schedule.services"].Event = type("Event", (), {"DoesNotExist": type("DoesNotExist", (Exception,), {})})
sys.modules["schedule.services"].EventValidationError = type("EVE", (ValueError,), {})
sys.modules["tasks.services"].TaskValidationError = type("TVE", (ValueError,), {})
sys.modules["schedule.services"].working_hours = lambda p: None
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(not result.wasSuccessful())
