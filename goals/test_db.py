from unittest import mock

import psycopg
import pytest
from django.conf import settings
from django.db.backends.postgresql.base import DatabaseWrapper as PostgresDatabaseWrapper

from goals.db.postgresql.base import RETRY_DELAYS, DatabaseWrapper

REFUSED = psycopg.OperationalError('connection to server at "127.0.0.1", port 5432 failed: Connection refused')


@pytest.fixture
def wrapper():
    # The parent's get_new_connection is mocked, so nothing needs the settings a real wrapper gets
    return DatabaseWrapper.__new__(DatabaseWrapper)


@pytest.fixture
def sleep():
    with mock.patch("goals.db.postgresql.base.time.sleep") as sleep:
        yield sleep


def parent_connect(*side_effect):
    return mock.patch.object(PostgresDatabaseWrapper, "get_new_connection", side_effect=side_effect)


def test_retries_while_postgres_restarts(wrapper, sleep):
    connection = object()
    with parent_connect(REFUSED, REFUSED, connection) as connect:
        assert wrapper.get_new_connection({"dbname": "goals"}) is connection
    assert connect.call_count == 3
    assert sleep.call_args_list == [mock.call(0.5), mock.call(1)]


def test_gives_up_after_the_last_delay(wrapper, sleep):
    with parent_connect(*[REFUSED] * (len(RETRY_DELAYS) + 1)) as connect, pytest.raises(psycopg.OperationalError):
        wrapper.get_new_connection({"dbname": "goals"})
    assert connect.call_count == len(RETRY_DELAYS) + 1
    assert [c.args[0] for c in sleep.call_args_list] == list(RETRY_DELAYS)


def test_does_not_retry_other_errors(wrapper, sleep):
    error = psycopg.OperationalError('connection to server at "127.0.0.1", port 5432 failed: password authentication failed')
    with parent_connect(error) as connect, pytest.raises(psycopg.OperationalError, match="password authentication failed"):
        wrapper.get_new_connection({"dbname": "goals"})
    assert connect.call_count == 1
    sleep.assert_not_called()


def test_connections_are_health_checked():
    assert settings.DATABASES["default"]["CONN_HEALTH_CHECKS"] is True
