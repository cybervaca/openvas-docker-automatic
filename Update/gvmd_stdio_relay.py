#!/usr/bin/env python3
"""
Puente STDIO <-> Unix socket gvmd (se ejecuta DENTRO del contenedor vía docker exec -i).

Uso interno:
  docker exec -i openvas python3 /opt/gvm/Update/gvmd_stdio_relay.py /run/gvmd/gvmd.sock
"""
from __future__ import annotations

import select
import socket
import sys


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("uso: gvmd_stdio_relay.py /ruta/gvmd.sock\n")
        return 2
    path = sys.argv[1]
    upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        upstream.connect(path)
    except OSError as e:
        sys.stderr.write(f"no conecta a {path}: {e}\n")
        return 1

    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    up_fd = upstream.fileno()
    in_fd = stdin.fileno()

    try:
        while True:
            readable, _, _ = select.select([in_fd, up_fd], [], [], 60.0)
            if not readable:
                continue
            if in_fd in readable:
                data = stdin.read1(65536) if hasattr(stdin, "read1") else stdin.read(65536)
                if not data:
                    break
                upstream.sendall(data)
            if up_fd in readable:
                data = upstream.recv(65536)
                if not data:
                    break
                stdout.write(data)
                stdout.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        try:
            upstream.close()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
