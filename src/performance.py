import logging
import os
import time
from contextlib import contextmanager

from gi.repository import GLib

logger = logging.getLogger("chelsea")

CHECK_INTERVAL_MS = 50
SLOW_LOOP_MS = 100


class LoopWatcher:
    def __init__(self):
        self.last_check = time.monotonic()
        GLib.timeout_add(CHECK_INTERVAL_MS, self.check)

    def check(self):
        now = time.monotonic()
        blocked_ms = (now - self.last_check) * 1000 - CHECK_INTERVAL_MS
        if blocked_ms > SLOW_LOOP_MS:
            logger.warning("the interface was blocked for %d ms", blocked_ms)
        self.last_check = now
        return GLib.SOURCE_CONTINUE


def setup_logging():
    debug = bool(os.environ.get("CHELSEA_DEBUG"))
    logging.basicConfig(level=logging.DEBUG if debug else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    if debug:
        LoopWatcher()


@contextmanager
def timed(name: str):
    start = time.monotonic()
    try:
        yield
    finally:
        logger.debug("%s took %d ms", name, (time.monotonic() - start) * 1000)
