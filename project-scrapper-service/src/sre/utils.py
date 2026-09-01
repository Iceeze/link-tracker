import httpx
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.config import load_config
from src.sre.circuit_breaker import CircuitBreaker

config = load_config()

limiter: Limiter = Limiter(key_func=get_remote_address)
timeout = httpx.Timeout(config.request_timeout, connect=config.request_timeout_connect)
breaker = CircuitBreaker(
    window_size=config.circuit_breaker_window_size,
    failure_rate_threshold=config.circuit_breaker_failure_rate_threshold,
    recovery_timeout=config.circuit_breaker_recovery_timeout,
    expected_exceptions=config.circuit_breaker_expected_exceptions,
)


def is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in config.retryable_statuses
    if isinstance(exc, httpx.RequestError):
        return True
    return False
