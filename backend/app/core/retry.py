"""Retry / timeout / circuit-breaker utilities for external calls.

Used by the Agent loop, MCP client and LLM client so that a flaky
dependency degrades gracefully instead of taking the whole request down.

Design notes:
- ``retry_async`` retries only on explicitly retryable exception types.
- Every external call can be bounded by a timeout via ``with_timeout``.
- ``CircuitBreaker`` stops hammering a dependency that is fully down,
  and lets a single probe through after ``recovery_timeout``.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

from app.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

#: Exceptions that are considered transient and therefore worth retrying.
DEFAULT_RETRYABLE: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    OSError,
)


class CircuitState(str, Enum):
    """State of a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RetryPolicy:
    """Exponential backoff retry policy.

    ``delay_for(attempt) = min(base_delay * backoff ** (attempt - 1), max_delay)``
    plus optional random jitter in ``[0, jitter]``.
    """

    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    backoff: float = 2.0
    jitter: float = 0.0
    retryable: tuple[type[BaseException], ...] = DEFAULT_RETRYABLE

    def delay_for(self, attempt: int) -> float:
        """Delay before the next attempt. ``attempt`` is 1-based."""
        if attempt <= 0:
            return 0.0
        delay = min(self.base_delay * (self.backoff ** (attempt - 1)), self.max_delay)
        if self.jitter:
            delay += random.uniform(0.0, self.jitter)
        return delay


async def with_timeout(coro: Awaitable[T], timeout: float) -> T:
    """Await ``coro`` but give up after ``timeout`` seconds."""
    return await asyncio.wait_for(asyncio.ensure_future(coro), timeout)


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    policy: RetryPolicy | None = None,
    timeout: float | None = None,
    *,
    sleeper: Callable[[float], Awaitable[None]] | None = None,
    operation: str = "call",
) -> T:
    """Call ``fn()`` retrying transient failures with exponential backoff.

    ``fn`` must be a zero-argument callable returning a coroutine, so each
    attempt builds a fresh coroutine (a coroutine object cannot be awaited twice).

    Raises the last retryable exception once ``policy.max_attempts`` is exhausted.
    """
    policy = policy or RetryPolicy()
    sleep = sleeper or asyncio.sleep
    last_exc: BaseException | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            if timeout is not None:
                return await with_timeout(fn(), timeout)
            return await fn()
        except policy.retryable as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt >= policy.max_attempts:
                break
            delay = policy.delay_for(attempt)
            logger.warning(
                "retry_scheduled",
                operation=operation,
                attempt=attempt,
                max_attempts=policy.max_attempts,
                delay=round(delay, 3),
                error=str(exc),
            )
            await sleep(delay)

    if last_exc is None:  # pragma: no cover - defensive
        raise RuntimeError(f"retry_async failed without an exception: {operation}")
    raise last_exc


@dataclass
class CircuitBreaker:
    """Simple circuit breaker with open / half-open / closed states.

    CLOSED    - normal operation, failures are counted.
    OPEN      - dependency considered down; every call fails fast.
    HALF_OPEN - after ``recovery_timeout`` a limited number of probe calls pass.
    """

    name: str = "default"
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    opened_at: float = 0.0
    _half_open_calls: int = field(default=0, repr=False)

    # ---------- state transitions ----------

    def trip(self) -> None:
        """Move to OPEN immediately."""
        if self.state is not CircuitState.OPEN:
            logger.warning(
                "circuit_open",
                name=self.name,
                failures=self.failure_count,
            )
        self.state = CircuitState.OPEN
        self.opened_at = time.time()
        self._half_open_calls = 0

    def reset(self) -> None:
        """Back to normal operation."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self._half_open_calls = 0
        self.opened_at = 0.0

    def record_success(self) -> None:
        if self.state is CircuitState.HALF_OPEN:
            logger.info("circuit_closed_after_probe", name=self.name)
        self.reset()

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.state is CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            self.trip()

    # ---------- query ----------

    def is_open(self) -> bool:
        """True when calls must fail fast. May transition OPEN -> HALF_OPEN."""
        if self.state is CircuitState.OPEN:
            if time.time() - self.opened_at >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("circuit_half_open", name=self.name)
            else:
                return True
        if self.state is CircuitState.HALF_OPEN:
            return self._half_open_calls >= self.half_open_max_calls
        return False

    # ---------- call ----------

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Run ``fn()`` under the breaker. Raises ``CircuitOpenError`` when open."""
        if self.is_open():
            raise CircuitOpenError(f"circuit is open: {self.name}")

        if self.state is CircuitState.HALF_OPEN:
            self._half_open_calls += 1

        try:
            result = await fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit is open."""
