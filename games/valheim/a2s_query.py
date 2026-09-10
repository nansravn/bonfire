#!/usr/bin/env python3
"""Query Valheim's Steam A2S endpoint.

Prints "<player_count> <max_players>" and exits 0 when the server answers;
exits 1 when nothing is listening (timeout or connection refused);
exits 2 on any other error, including a missing python-a2s.
"""
import socket
import sys

try:
    import a2s
except ImportError:
    sys.exit(2)

host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 2457
try:
    info = a2s.info((host, port), timeout=3.0)
except (socket.timeout, TimeoutError, ConnectionRefusedError):
    sys.exit(1)
except Exception:
    sys.exit(2)
print(info.player_count, info.max_players)
