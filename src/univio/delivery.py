"""Send one reply per event, with bounded process-local retry suppression."""

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable

from pywa_async import WhatsApp
from pywa_async.types import Button

from univio.conversation import Screen, choose_screen
from univio.events import Event


class DeliveryBusy(Exception):
    """Retry later: an event is in progress or local capacity is exhausted."""


class ReplyService:
    """Coordinate retries without a database or conversation sessions.

    Record an ID only after send_message succeeds. Concurrent duplicates get a
    retryable failure rather than a premature success. The lock protects cache
    operations only; it is never held across a network call.
    """

    def __init__(
        self,
        wa: WhatsApp,
        *,
        clock: Callable[[], float] = time.monotonic,
        capacity: int = 10_000,
        ttl: float = 86_400,
    ):
        self.wa = wa
        self.clock = clock
        self.capacity = capacity
        self.ttl = ttl
        self.completed: OrderedDict[str, float] = OrderedDict()
        self.in_flight: set[str] = set()
        self.lock = asyncio.Lock()

    async def reply(self, event: Event, *, screen: Screen | None = None) -> None:
        """Send a single catalog response, or skip an already completed event."""
        async with self.lock:
            now = self.clock()
            while self.completed and next(iter(self.completed.values())) <= now:
                self.completed.popitem(last=False)
            if event.id in self.completed:
                return
            if event.id in self.in_flight or len(self.in_flight) >= 20:
                raise DeliveryBusy
            self.in_flight.add(event.id)
        try:
            screen = screen or choose_screen(event.command, event.kind)
            await self.wa.send_message(
                to=event.sender,
                text=screen.render(),
                buttons=[
                    Button(title=option.label, callback_data=option.command)
                    for option in screen.options
                ],
            )
            async with self.lock:
                self.completed[event.id] = self.clock() + self.ttl
                while len(self.completed) > self.capacity:
                    self.completed.popitem(last=False)
        finally:
            # Release failed/cancelled sends too, so a later Meta retry can run.
            async with self.lock:
                self.in_flight.discard(event.id)
