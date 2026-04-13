# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Port availability utilities — no app imports so tests can import safely."""
from __future__ import annotations

import socket as _socket

_DEFAULT_PORT = 7070


def find_free_port(start: int = _DEFAULT_PORT, max_scan: int = 20) -> int:
    """Scan upward from `start` and return the first unbound port."""
    for port in range(start, start + max_scan):
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start + max_scan  # last resort — caller will discover conflict at serve time
