from time import monotonic
from threading import Lock
from uuid import uuid4

from app.security import fail


class TestLoginLimiter:
    """Disposable limiter for business-flow tests; shared limits use real Redis in integration tests."""
    __test__ = False

    def __init__(self):
        self.attempts = {}
        self.lock = Lock()

    def reserve(self, source):
        with self.lock:
            stamp = monotonic()
            active = self.attempts.setdefault(source, {})
            for ticket in [ticket for ticket, at in active.items() if at <= stamp - 300]:
                del active[ticket]
            if len(active) >= 10:
                fail('RATE_LIMIT', '登录过于频繁', 429)
            ticket = uuid4().hex
            active[ticket] = stamp
            return source, ticket

    def refund(self, ticket):
        source, attempt = ticket
        with self.lock:
            active = self.attempts[source]
            active.pop(attempt, None)
            if not active:
                del self.attempts[source]
