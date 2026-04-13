# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import socket
import pytest
from synthadoc.cli._port import find_free_port as _find_free_port


def test_find_free_port_returns_start_when_available():
    """Returns the start port if it is not bound."""
    # Pick a port above common use range — unlikely to be bound in CI
    port = _find_free_port(start=19700)
    assert port == 19700


def test_find_free_port_skips_bound_port():
    """Skips a port that is already bound and returns the next free one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 19800))
        port = _find_free_port(start=19800)
    assert port == 19801


def test_find_free_port_scans_multiple():
    """Scans past multiple bound ports."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s1, \
         socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
        s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s1.bind(("127.0.0.1", 19900))
        s2.bind(("127.0.0.1", 19901))
        port = _find_free_port(start=19900)
    assert port == 19902
