"""Tests for scheduler timing helpers.

The scheduler module imports freely; the helpers under test are pure
functions so they can be verified without starting a scheduler.
"""
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.scheduler import tasks


def test_first_ai_time_is_immediate():
    before = datetime.now()
    run = tasks._first_ai_time()
    after = datetime.now()
    assert before <= run <= after


def test_next_ai_time_with_backlog_is_quick():
    run = tasks._next_ai_time(has_remaining=True)
    assert run <= datetime.now() + timedelta(seconds=tasks.AI_RETRY_SECONDS + 1)


def test_next_ai_time_without_backlog_uses_interval():
    settings = get_settings()
    run = tasks._next_ai_time(has_remaining=False)
    delta = run - datetime.now()
    assert timedelta(minutes=settings.AI_PROCESS_INTERVAL_MINUTES - 1) <= delta
    assert delta <= timedelta(minutes=settings.AI_PROCESS_INTERVAL_MINUTES + 1)


def test_cleanup_cutoff_uses_retention_days():
    settings = get_settings()
    cutoff = tasks._cleanup_cutoff()
    delta = datetime.now() - cutoff
    assert timedelta(days=settings.CLEANUP_RETENTION_DAYS - 1) < delta
    assert delta <= timedelta(days=settings.CLEANUP_RETENTION_DAYS, seconds=1)