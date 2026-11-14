"""PostgreSQL backend that waits for the server when opening a connection.

unattended-upgrades restarts Postgres, which is down for a few seconds. Without this, every
request (and potatoq task) that needs a new connection in that window fails with a 500.
Only opening a connection is retried, never a query; errors a restart can't explain
(bad password, missing database, ...) are raised right away.
"""

import logging
import time

import psycopg
from django.db.backends.postgresql.base import DatabaseWrapper as PostgresDatabaseWrapper

logger = logging.getLogger(__name__)

# ~15s in total, well under gunicorn's 30s worker timeout
RETRY_DELAYS = (0.5, 1, 2, 4, 8)

TRANSIENT_ERRORS = (
    "Connection refused",
    "the database system is shutting down",
    "the database system is starting up",
    "not yet accepting connections",
    "No such file or directory",  # the unix socket is gone while the server restarts
)


def is_transient(error: psycopg.OperationalError) -> bool:
    message = str(error)
    return any(text in message for text in TRANSIENT_ERRORS)


class DatabaseWrapper(PostgresDatabaseWrapper):
    def get_new_connection(self, conn_params):
        for delay in RETRY_DELAYS:
            try:
                return super().get_new_connection(conn_params)
            except psycopg.OperationalError as error:
                if not is_transient(error):
                    raise
                logger.warning("Postgres is unavailable, retrying the connection in %ss: %s", delay, error)
                time.sleep(delay)
        return super().get_new_connection(conn_params)
