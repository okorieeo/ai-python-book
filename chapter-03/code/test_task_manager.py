import pytest
from task_manager import TaskNotFoundError, TaskStore

def test_add_and_persist(tmp_path):
    path = tmp_path / "tasks.json"
    store = TaskStore(path)
    task = store.add("Write chapter", "high")
    assert task.id == 1

    reloaded = TaskStore(path)               # new object reads the saved file
    assert reloaded.tasks[0].title == "Write chapter"

def test_complete_task(tmp_path):
    store = TaskStore(tmp_path / "tasks.json")
    task = store.add("Test me")
    store.complete(task.id)
    assert store.get(task.id).done is True

def test_invalid_priority(tmp_path):
    store = TaskStore(tmp_path / "tasks.json")
    with pytest.raises(ValueError):
        store.add("Bad", "urgent")

def test_missing_task(tmp_path):
    store = TaskStore(tmp_path / "tasks.json")
    with pytest.raises(TaskNotFoundError):
        store.get(999)
