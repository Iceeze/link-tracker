from enum import Enum
import time
import structlog
from collections import deque
from functools import wraps

logger = structlog.get_logger(__name__)


class CircuitBreakerOpenException(Exception):
    pass


class StatesCircuitBreaker(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Собственная реализация паттерна Circuit Breaker для асинхронных функций.

    Args:
        window_size: Кол-во последних вызовов для оценки failure rate.
        failure_rate_threshold: Процент неудачных вызовов для открытия цепи.
        recovery_timeout: Время в секундах, после которого пробуем восстановить соединение.
        expected_exceptions: Кортеж типов исключений, которые считаются "неудачными" вызовами.
    """

    def __init__(
        self,
        window_size: int,
        failure_rate_threshold: float,
        recovery_timeout: int,
        expected_exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        self.window_size = window_size
        self.failure_rate_threshold = failure_rate_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions

        self.history: deque[bool] = deque(maxlen=window_size)
        self.state = StatesCircuitBreaker.CLOSED
        self.opened_at = 0.0

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == StatesCircuitBreaker.OPEN:
                if time.time() - self.opened_at > self.recovery_timeout:
                    self.state = StatesCircuitBreaker.HALF_OPEN
                    logger.info("CircuitBreaker: переход в HALF_OPEN (пробный запрос)")
                else:
                    raise CircuitBreakerOpenException("CircuitBreaker is OPEN")
            elif self.state == StatesCircuitBreaker.HALF_OPEN:
                raise CircuitBreakerOpenException(
                    "CircuitBreaker is HALF_OPEN (testing)"
                )

            try:
                result = await func(*args, **kwargs)
                self._record_success()
                return result
            except self.expected_exceptions as e:
                self._record_failure()
                raise e

        return wrapper

    def _record_success(self):
        if self.state == StatesCircuitBreaker.HALF_OPEN:
            self.state = StatesCircuitBreaker.CLOSED
            self.history.clear()
            logger.info("CircuitBreaker: соединение восстановлено, состояние CLOSED")
        elif self.state == StatesCircuitBreaker.CLOSED:
            self.history.append(True)

    def _record_failure(self):
        if self.state == StatesCircuitBreaker.HALF_OPEN:
            self.state = StatesCircuitBreaker.OPEN
            self.opened_at = time.time()
            logger.warning("CircuitBreaker: пробный запрос упал, возврат в OPEN")

        elif self.state == StatesCircuitBreaker.CLOSED:
            self.history.append(False)

            if len(self.history) == self.window_size:
                failure_rate = self.history.count(False) / self.window_size
                if failure_rate >= self.failure_rate_threshold:
                    self.state = StatesCircuitBreaker.OPEN
                    self.opened_at = time.time()
                    self.history.clear()
                    logger.error(
                        f"CircuitBreaker: порог {failure_rate*100:.0f}% превышен -> OPEN"
                    )
