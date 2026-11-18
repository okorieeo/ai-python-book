# audit/services.py: add these members to the Action enum from Chapter 17.
class Action(enum.StrEnum):
    # ... the ones you already have ...
    TASK_DELETED = "tasks.task_deleted"
    EVENT_DELETED = "schedule.event_deleted"
    ASSISTANT_ACTION_CONFIRMED = "assistant.action_confirmed"
    ASSISTANT_ACTION_DECLINED = "assistant.action_declined"
