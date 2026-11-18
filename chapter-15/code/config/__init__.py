from .celery import app as celery_app

__all__ = ("celery_app",)         # loaded with Django, so @shared_task works
