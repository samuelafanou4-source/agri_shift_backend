"""Server clock for sync cursors: strictly increasing within the process.

Every `server_updated_at` and every pull `server_time` comes from `server_now()`. Because two
calls never return the same value, a row written before a pull is always `< server_time` and a
row written after it is always `> server_time`, even when the wall clock is coarse (≈15 ms steps
on Windows) or steps backwards. Valid for a single API instance (DECISIONS D-42 / D-53).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

_ONE_US = timedelta(microseconds=1)
_lock = threading.Lock()
_last = datetime.min.replace(tzinfo=UTC)


def _wall() -> datetime:
    return datetime.now(UTC)


def server_now() -> datetime:
    global _last
    with _lock:
        now = _wall()
        if now <= _last:
            now = _last + _ONE_US
        _last = now
        return now
