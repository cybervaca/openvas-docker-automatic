#!/usr/bin/env python3
"""
Proxy en el HOST: Unix socket local -> docker exec -> gvmd.sock del contenedor.

Permite que scripts en el host (usuario con permiso docker) hablen GMP
aunque no exista volumen /opt/gvm/run/gvmd:/run/gvmd.
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time

DEFAULT_CONTAINER = "openvas"
DEFAULT_HOST_SOCK = "/opt/gvm/run/gvmd/gvmd.sock"
DEFAULT_PID_FILE = "/opt/gvm/run/gvmd/docker-proxy.pid"
RELAY = "/opt/gvm/Update/gvmd_stdio_relay.py"
CANDIDATES_IN_CONTAINER = (
    "/run/gvmd/gvmd.sock",
    "/var/run/gvmd/gvmd.sock",
    "/usr/local/var/run/gvmd.sock",
    "/run/gvm/gvmd.sock",
)


def find_container_socket(container: str) -> str:
    script = (
        "for p in "
        + " ".join(CANDIDATES_IN_CONTAINER)
        + "; do [ -S \"$p\" ] && echo \"$p\" && exit 0; done; "
        "find /run /var/run /tmp /usr/local/var/run -type s -name '*gvmd*.sock' 2>/dev/null | head -1"
    )
    r = subprocess.run(
        ["docker", "exec", container, "sh", "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    path = (r.stdout or "").strip().splitlines()
    if r.returncode != 0 or not path or not path[0].strip():
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(
            f"No se encontró gvmd.sock en contenedor «{container}». "
            f"docker exec falló o no hay socket. {err}"
        )
    return path[0].strip()


def _pipe_conn(conn: socket.socket, container: str, container_sock: str) -> None:
    try:
        proc = subprocess.Popen(
            ["docker", "exec", "-i", container, "python3", RELAY, container_sock],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
    except OSError:
        try:
            conn.close()
        except OSError:
            pass
        return

    def client_to_docker() -> None:
        try:
            assert proc.stdin is not None
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                proc.stdin.write(data)
                proc.stdin.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    def docker_to_client() -> None:
        try:
            assert proc.stdout is not None
            while True:
                data = proc.stdout.read(65536)
                if not data:
                    break
                conn.sendall(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    t1 = threading.Thread(target=client_to_docker, daemon=True)
    t2 = threading.Thread(target=docker_to_client, daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    try:
        proc.kill()
    except OSError:
        pass
    try:
        conn.close()
    except OSError:
        pass


def serve(host_sock: str, container: str, container_sock: str) -> None:
    os.makedirs(os.path.dirname(host_sock), exist_ok=True)
    if os.path.exists(host_sock):
        try:
            os.unlink(host_sock)
        except OSError:
            pass

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(host_sock)
    try:
        os.chmod(host_sock, 0o777)
    except OSError:
        pass
    srv.listen(32)
    print(f"[OK] Proxy GMP: {host_sock} -> docker:{container}:{container_sock}", flush=True)

    while True:
        conn, _ = srv.accept()
        threading.Thread(
            target=_pipe_conn, args=(conn, container, container_sock), daemon=True
        ).start()


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def already_running(pid_file: str, host_sock: str) -> bool:
    if os.path.exists(host_sock) and _socket_accepts(host_sock):
        return True
    if not os.path.isfile(pid_file):
        return False
    try:
        pid = int(open(pid_file).read().strip())
    except (OSError, ValueError):
        return False
    return pid_is_alive(pid)


def _socket_accepts(path: str, timeout: float = 1.0) -> bool:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(path)
        s.close()
        return True
    except OSError:
        return False


def start_daemon(host_sock: str, container: str, pid_file: str) -> None:
    if already_running(pid_file, host_sock):
        print(f"[OK] Proxy ya activo: {host_sock}")
        return

    container_sock = find_container_socket(container)
    print(f"[INFO] Socket en contenedor: {container_sock}")

    # Fork simple a background
    if os.fork() != 0:
        # padre: espera a que el socket exista
        for _ in range(50):
            if os.path.exists(host_sock) and _socket_accepts(host_sock):
                print(f"[OK] Proxy listo en {host_sock}")
                return
            time.sleep(0.1)
        raise RuntimeError("Timeout esperando proxy GMP en " + host_sock)

    # hijo daemon
    os.setsid()
    if os.fork() != 0:
        os._exit(0)

    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    def _cleanup(*_a):
        try:
            if os.path.exists(host_sock):
                os.unlink(host_sock)
        except OSError:
            pass
        try:
            if os.path.exists(pid_file):
                os.unlink(pid_file)
        except OSError:
            pass
        os._exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    try:
        serve(host_sock, container, container_sock)
    except Exception:
        _cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description="Proxy host Unix -> gvmd en Docker")
    parser.add_argument("-c", "--container", default=DEFAULT_CONTAINER)
    parser.add_argument("-s", "--socket", default=DEFAULT_HOST_SOCK)
    parser.add_argument("--pid-file", default=DEFAULT_PID_FILE)
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="No daemonizar (debug)",
    )
    parser.add_argument(
        "--find-only",
        action="store_true",
        help="Solo localizar socket en el contenedor y salir",
    )
    args = parser.parse_args()

    try:
        if args.find_only:
            print(find_container_socket(args.container))
            return 0
        if args.foreground:
            sock = find_container_socket(args.container)
            print(f"[INFO] Socket en contenedor: {sock}")
            serve(args.socket, args.container, sock)
            return 0
        start_daemon(args.socket, args.container, args.pid_file)
        return 0
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
