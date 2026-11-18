import logging

from celery.signals import before_task_publish, task_failure, task_postrun, task_prerun

logger = logging.getLogger("celery.trace")

@before_task_publish.connect
def attach_request_id(headers=None, **kwargs):
    from core.logging_context import current_request_id          # Chapter 17's contextvar
    headers["request_id"] = current_request_id()

@task_prerun.connect
def task_started(task_id=None, task=None, **kwargs):
    rid = getattr(task.request, "request_id", None) or (task.request.headers or {}).get("request_id")
    logger.info("task start", extra={"event": "task_start", "request_id": rid,
                                     "fields": {"task": task.name, "task_id": task_id}})

@task_postrun.connect
def task_finished(task_id=None, task=None, state=None, **kwargs):
    logger.info("task end", extra={"event": "task_end", "fields": {"task": task.name, "task_id": task_id, "state": state}})

@task_failure.connect
def task_failed(task_id=None, exception=None, sender=None, **kwargs):
    logger.error("task failed", extra={"event": "task_failed",
                 "fields": {"task": sender.name, "task_id": task_id, "error": type(exception).__name__}})
