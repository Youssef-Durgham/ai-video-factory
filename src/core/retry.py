"""
Retry decorator — simple retry with exponential backoff.
Used for wrapping individual function calls.

For comprehensive per-service retry with recovery actions,
see retry_engine.py (RetryEngine class).

This module provides a lightweight @retry decorator for quick use.
"""

import functools
import logging
import time
from typing import Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


def retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
):
    """
    Retry decorator with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        initial_delay: Initial delay in seconds between retries.
        backoff_multiplier: Multiplier for exponential backoff.
        max_delay: Maximum delay in seconds.
        exceptions: Tuple of exception types to catch and retry.
        on_retry: Optional callback(attempt, exception) called before each retry.

    Usage:
        @retry(max_retries=3, exceptions=(ConnectionError, TimeoutError))
        def call_api():
            ...

        @retry(max_retries=5, initial_delay=2.0)
        async def async_call():
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f"[retry] {func.__name__} failed after {max_retries} attempts: {e}"
                        )
                        raise

                    delay = min(
                        initial_delay * (backoff_multiplier ** (attempt - 1)),
                        max_delay,
                    )

                    logger.warning(
                        f"[retry] {func.__name__} attempt {attempt}/{max_retries} "
                        f"failed: {e} — retrying in {delay:.1f}s"
                    )

                    if on_retry:
                        on_retry(attempt, e)

                    time.sleep(delay)

            raise last_exception

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            import asyncio

            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f"[retry] {func.__name__} failed after {max_retries} attempts: {e}"
                        )
                        raise

                    delay = min(
                        initial_delay * (backoff_multiplier ** (attempt - 1)),
                        max_delay,
                    )

                    logger.warning(
                        f"[retry] {func.__name__} attempt {attempt}/{max_retries} "
                        f"failed: {e} — retrying in {delay:.1f}s"
                    )

                    if on_retry:
                        on_retry(attempt, e)

                    await asyncio.sleep(delay)

            raise last_exception

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
