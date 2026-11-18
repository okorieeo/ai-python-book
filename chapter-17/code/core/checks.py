"""Registers our configuration checks, so `manage.py check --deploy` runs them."""
from django.conf import settings
from django.core.checks import Error, Tags, register

from .security.config_checks import find_config_problems


@register(Tags.security, deploy=True)
def project_security_checks(app_configs, **kwargs):
    problems = find_config_problems(settings)
    return [Error(problem, id="core.E001") for problem in problems]
