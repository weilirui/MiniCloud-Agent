"""Unit tests for retry / timeout / circuit-breaker."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.core.retry import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RetryPolicy,
    retry_async,
    with_timeout,
)


async def _no_sleep(_: float) -> None:
    """Stand-in for asyncio.sleep so tests don't actually wait."""


def test_delay_for_is_exponential_and_capped():
    policy = RetryPolicy(base_delay=1.0, max_delay=5.0)
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(2) == 2.0
    assert policy.delay_for(3) == 4.0
    assert policy.delay_for(10) == 5.0  # capped


def test_delay_for_zero_attempt():
    assert RetryPolicy().delay_for(0) == 0.0


async def test_retry_succeeds_without_retrying():
    calls = {"n": 0}

    async def ok():
        calls["n"] += 1
        return "done"

    assert await retry_async(ok) == "done"
    assert calls["n"] == 1


async def test_retry_recovers_after_transient_failure():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "recovered"

    result = await retry_async(flaky, RetryPolicy(max_attempts=4), sleeper=_no_sleep)
    assert result == "recovered"
    assert calls["n"] == 3


async def test_retry_gives_up_and_reraises():
    calls = {"n": 0}

    async def always_fail():
        calls["n"] += 1
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        await retry_async(always_fail, RetryPolicy(max_attempts=3), sleeper=_no_sleep)
    assert calls["n"] == 3


async def test_retry_does_not_swallow_programming_errors():
    async def bad_args():
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        await retry_async(bad_args, RetryPolicy(max_attempts=3), sleeper=_no_sleep)


async def test_retry_applies_timeout():
    async def slow():
        await asyncio.sleep(5)

    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        await retry_async(slow, RetryPolicy(max_attempts=1), timeout=0.01, sleeper=_no_sleep)


async def test_with_timeout_returns_value_when_fast():
    async def fast():
        return 42

    assert await with_timeout(fast(), 1.0) == 42


def test_circuit_starts_closed():
    breaker = CircuitBreaker()
    assert breaker.state is CircuitState.CLOSED
    assert breaker.is_open() is False


def test_circuit_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    assert breaker.is_open() is True


async def test_open_circuit_fails_fast():
    breaker = CircuitBreaker(failure_threshold=1)
    breaker.record_failure()

    async def never_called():
        raise AssertionError("should not be invoked")

    with pytest.raises(CircuitOpenError):
        await breaker.call(never_called)


def test_circuit_moves_to_half_open_after_recovery():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10)
    breaker.record_failure()
    assert breaker.is_open() is True

    # simulate time passing
    breaker.opened_at = time.time() - 20
    assert breaker.is_open() is False
    assert breaker.state is CircuitState.HALF_OPEN


async def test_probe_success_closes_the_circuit():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10)
    breaker.record_failure()
    breaker.opened_at = time.time() - 20
    breaker.is_open()  # triggers OPEN -> HALF_OPEN

    async def ok():
        return "ok"

    assert await breaker.call(ok) == "ok"
    assert breaker.state is CircuitState.CLOSED
    assert breaker.failure_count == 0


async def test_probe_failure_reopens_the_circuit():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10)
    breaker.record_failure()
    breaker.opened_at = time.time() - 20
    breaker.is_open()

    async def nope():
        raise ConnectionError("still down")

    with pytest.raises(ConnectionError):
        await breaker.call(nope)
    assert breaker.state is CircuitState.OPEN


def test_half_open_blocks_extra_probes():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10, half_open_max_calls=1)
    breaker.record_failure()
    breaker.opened_at = time.time() - 20

    assert breaker.is_open() is False      # first probe slot is free
    breaker._half_open_calls = 1
    assert breaker.is_open() is True       # second probe is blocked


async def test_half_open_probe_slot_is_consumed_by_a_call():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10, half_open_max_calls=1)
    breaker.record_failure()
    breaker.opened_at = time.time() - 20

    async def ok():
        return 1

    await breaker.call(ok)          # consumes the single probe slot
    assert breaker.state is CircuitState.CLOSED  # success resets the breaker
