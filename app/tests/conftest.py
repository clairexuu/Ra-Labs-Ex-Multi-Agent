"""Shared test fixtures."""

import logging

import pytest

import app.observability as obs


@pytest.fixture(autouse=True, scope="session")
def _redirect_test_logs(tmp_path_factory):
    """Redirect log file output to a temp directory for the entire test session.

    Without this, ``setup_logging()`` creates a ``FileHandler`` that writes to
    the real ``logs/events.jsonl``, polluting it with test artifacts.
    """
    tmp_logs = tmp_path_factory.mktemp("logs")
    original_logs_dir = obs.LOGS_DIR
    obs.LOGS_DIR = tmp_logs

    # Clear any pre-existing handlers so the next setup_logging() call
    # recreates them with the redirected LOGS_DIR.
    logger = logging.getLogger("investment_team")
    logger.handlers.clear()
    logger.filters.clear()

    yield

    # Restore original state
    obs.LOGS_DIR = original_logs_dir
    logger.handlers.clear()
    logger.filters.clear()
