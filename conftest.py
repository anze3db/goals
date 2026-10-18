import pytest
from potatoq import current_app


@pytest.fixture(autouse=True)
def eager_tasks():
    """Run potatoq tasks in-process at .delay(), so views that enqueue a sync can be tested end to end."""
    app = current_app()
    app.conf.task_always_eager = True
    yield
    app.conf.task_always_eager = False
