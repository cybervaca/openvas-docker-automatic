#!/usr/bin/env python3
"""
Conexión GMP a gvmd con compatibilidad dual:

- tls  → TLSConnection a host:port (por defecto 127.0.0.1:9390)
- unix → UnixSocketConnection al socket de gvmd
- auto → prueba TLS primero (no romper hosts que ya usan 9390);
         si falla, prueba sockets Unix habituales y el socket
         dentro del contenedor Docker vía /proc/<pid>/root/...

Claves opcionales en /opt/gvm/Config/config.json:
  "gvm_connection": "auto" | "tls" | "unix"
  "gvm_host": "127.0.0.1"
  "gvm_port": 9390
  "gvm_socket": "/opt/gvm/run/gvmd/gvmd.sock"
  "gvm_docker_container": "openvas"
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from gvm.connections import TLSConnection, UnixSocketConnection
from gvm.protocols.gmp import Gmp

DEFAULT_CONFIG_PATH = "/opt/gvm/Config/config.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9390
DEFAULT_TIMEOUT = 900
DEFAULT_DOCKER_CONTAINER = "openvas"

DEFAULT_SOCKET_CANDIDATES = (
    "/opt/gvm/run/gvmd/gvmd.sock",
    "/run/gvmd/gvmd.sock",
    "/var/run/gvmd/gvmd.sock",
    "/usr/local/var/run/gvmd.sock",
)

MOUNT_HINT = (
    "En docker-compose del contenedor openvas añade el volumen "
    "'/opt/gvm/run/gvmd:/run/gvmd' y recrea el contenedor "
    "(docker compose up -d). Así el socket queda en el host. "
    "Alternativa sin recrear: python3 /opt/gvm/Update/gvmd_docker_proxy.py"
)

DEFAULT_HOST_PROXY_SOCK = "/opt/gvm/run/gvmd/gvmd.sock"
DOCKER_PROXY_SCRIPT = "/opt/gvm/Update/gvmd_docker_proxy.py"

# Cache de transporte que funcionó en este proceso (evita re-probar en cada reconnect)
_resolved: Optional[Dict[str, Any]] = None


def load_gvm_config(config_path: str = DEFAULT_CONFIG_PATH, config: Optional[dict] = None) -> dict:
    if config is not None:
        return config
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _mode(cfg: dict) -> str:
    return str(cfg.get("gvm_connection") or "auto").strip().lower()


def _host(cfg: dict) -> str:
    return str(cfg.get("gvm_host") or DEFAULT_HOST).strip() or DEFAULT_HOST


def _port(cfg: dict) -> int:
    try:
        return int(cfg.get("gvm_port") or DEFAULT_PORT)
    except (TypeError, ValueError):
        return DEFAULT_PORT


def _docker_container_name(cfg: dict) -> str:
    return (
        str(cfg.get("gvm_docker_container") or DEFAULT_DOCKER_CONTAINER).strip()
        or DEFAULT_DOCKER_CONTAINER
    )


def _docker_gvmd_socket_paths(container_name: str) -> List[str]:
    """
    Descubre el socket gvmd sin volumen montado:
    1) bind mount host path si /run/gvmd ya está montado
    2) /proc/<pid>/root/run/gvmd/gvmd.sock (suele requerir root o caps)
    """
    paths: List[str] = []
    try:
        r = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .Mounts}}{{.Destination}} {{.Source}}{{println}}{{end}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) != 2:
                    continue
                dest, source = parts[0], parts[1]
                if dest.rstrip("/") in ("/run/gvmd", "/var/run/gvmd") or dest.endswith(
                    "/gvmd"
                ):
                    candidate = os.path.join(source, "gvmd.sock")
                    if candidate not in paths:
                        paths.append(candidate)
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Pid}}", container_name],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode == 0:
            pid = (r.stdout or "").strip()
            if pid.isdigit() and int(pid) > 0:
                for rel in ("run/gvmd/gvmd.sock", "var/run/gvmd/gvmd.sock"):
                    candidate = f"/proc/{pid}/root/{rel}"
                    if candidate not in paths:
                        paths.append(candidate)
    except (OSError, subprocess.SubprocessError):
        pass

    return paths


def _socket_candidates(cfg: dict) -> List[str]:
    paths: List[str] = []
    custom = cfg.get("gvm_socket")
    if custom and str(custom).strip():
        paths.append(str(custom).strip())
    for p in DEFAULT_SOCKET_CANDIDATES:
        if p not in paths:
            paths.append(p)
    for p in _docker_gvmd_socket_paths(_docker_container_name(cfg)):
        if p not in paths:
            paths.append(p)
    return paths


def _connection_hint(errors: List[str]) -> str:
    return (
        "; ".join(errors)
        + " | "
        + MOUNT_HINT
        + " | Comprueba: docker exec openvas ls -la /run/gvmd/gvmd.sock"
    )


def tcp_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def make_tls_connection(host: str, port: int, timeout: int) -> TLSConnection:
    return TLSConnection(hostname=host, port=port, timeout=timeout)


def make_unix_connection(path: str, timeout: int) -> UnixSocketConnection:
    return UnixSocketConnection(path=path, timeout=timeout)


def probe_connection(connection) -> Tuple[bool, str]:
    """Abre GMP, pide versión y cierra. Devuelve (ok, detalle)."""
    try:
        with Gmp(connection=connection) as gmp:
            resp = gmp.get_version()
        return True, (resp or "")[:200]
    except Exception as e:
        return False, str(e)


def describe_resolved() -> str:
    if not _resolved:
        return "sin resolver aún"
    t = _resolved.get("type")
    if t == "tls":
        return f"tls://{_resolved.get('host')}:{_resolved.get('port')}"
    if t == "unix":
        return f"unix:{_resolved.get('path')}"
    return str(_resolved)


def _build_from_resolved(timeout: int):
    if not _resolved:
        return None
    if _resolved["type"] == "tls":
        return make_tls_connection(_resolved["host"], _resolved["port"], timeout)
    if _resolved["type"] == "unix":
        path = _resolved.get("path")
        # /proc/<pid>/root/... deja de valer si el contenedor reinició
        if not path or not os.path.exists(path):
            return None
        return make_unix_connection(path, timeout)
    return None


def _ensure_docker_proxy(cfg: dict, verbose: bool = False) -> Optional[str]:
    """
    Si no hay socket usable en el host, levanta proxy Unix->docker exec.
    Requiere permiso docker y python3 en el contenedor.
    Devuelve la ruta del socket local o None.
    """
    host_sock = str(cfg.get("gvm_socket") or DEFAULT_HOST_PROXY_SOCK).strip()
    container = _docker_container_name(cfg)

    # ¿Ya hay proxy/socket usable?
    if os.path.exists(host_sock):
        try:
            ok, _ = probe_connection(make_unix_connection(host_sock, 5))
            if ok:
                return host_sock
        except Exception:
            pass

    script = DOCKER_PROXY_SCRIPT
    # En desarrollo: ruta relativa al repo
    if not os.path.isfile(script):
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Update", "gvmd_docker_proxy.py")
        if os.path.isfile(alt):
            script = alt
    if not os.path.isfile(script):
        if verbose:
            print(f"[WARNING] No está {DOCKER_PROXY_SCRIPT}; no se puede crear proxy Docker")
        return None

    if verbose:
        print(f"[INFO] Arrancando proxy GMP Docker → {host_sock} (contenedor {container})...")

    try:
        r = subprocess.run(
            [sys.executable, script, "-c", container, "-s", host_sock],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        if verbose:
            print(f"[WARNING] Proxy Docker no arrancó: {e}")
        return None

    if verbose and (r.stdout or r.stderr):
        for line in ((r.stdout or "") + (r.stderr or "")).splitlines():
            print(f"[INFO] proxy: {line}")

    if r.returncode != 0:
        return None

    # Esperar a que el socket acepte
    for _ in range(30):
        if os.path.exists(host_sock):
            ok, detail = probe_connection(make_unix_connection(host_sock, 5))
            if ok:
                return host_sock
        time.sleep(0.2)
    return None


def _try_unix_paths(paths: List[str], ptimeout: int, timeout: int, verbose: bool, errors: List[str]):
    global _resolved
    for path in paths:
        if not os.path.exists(path):
            errors.append(f"unix:{path}: no existe")
            continue
        if not os.access(path, os.R_OK):
            errors.append(f"unix:{path}: sin permiso (prueba root o monta el volumen)")
            continue
        ok, detail = probe_connection(make_unix_connection(path, ptimeout))
        if ok:
            _resolved = {"type": "unix", "path": path}
            if verbose:
                print(f"[INFO] GVM → Unix socket {path}")
            return make_unix_connection(path, timeout)
        errors.append(f"unix:{path}: {detail}")
    return None


def connect_gvm(
    timeout: int = DEFAULT_TIMEOUT,
    config: Optional[dict] = None,
    config_path: str = DEFAULT_CONFIG_PATH,
    force_probe: bool = False,
    verbose: bool = False,
    probe_timeout: int = 15,
):
    """
    Devuelve un objeto de conexión listo para ``Gmp(connection=...)``.

    En modo ``auto`` prueba TLS (9390) primero y luego sockets Unix
    (rutas fijas + descubrimiento Docker).
    """
    global _resolved
    cfg = load_gvm_config(config_path=config_path, config=config)
    mode = _mode(cfg)
    host = _host(cfg)
    port = _port(cfg)
    errors: List[str] = []
    ptimeout = min(probe_timeout, timeout) if timeout else probe_timeout
    candidates = _socket_candidates(cfg)

    if not force_probe and _resolved is not None:
        conn = _build_from_resolved(timeout)
        if conn is not None:
            if verbose:
                print(f"[INFO] GVM reutiliza conexión: {describe_resolved()}")
            return conn
        _resolved = None

    # --- tls only ---
    if mode == "tls":
        ok, detail = probe_connection(make_tls_connection(host, port, ptimeout))
        if not ok:
            raise ConnectionError(f"GVM TLS falló ({host}:{port}): {detail}")
        _resolved = {"type": "tls", "host": host, "port": port}
        if verbose:
            print(f"[INFO] GVM conectado por TLS: {host}:{port}")
        return make_tls_connection(host, port, timeout)

    # --- unix only ---
    if mode == "unix":
        conn = _try_unix_paths(candidates, ptimeout, timeout, verbose, errors)
        if conn is not None:
            return conn
        proxy_sock = _ensure_docker_proxy(cfg, verbose=verbose)
        if proxy_sock:
            ok, detail = probe_connection(make_unix_connection(proxy_sock, ptimeout))
            if ok:
                _resolved = {"type": "unix", "path": proxy_sock}
                return make_unix_connection(proxy_sock, timeout)
            errors.append(f"unix:{proxy_sock} (proxy): {detail}")
        raise ConnectionError("GVM Unix falló. " + _connection_hint(errors))

    # --- auto: TLS primero (compat hosts 9390), luego Unix ---
    if tcp_port_open(host, port, timeout=2.0):
        ok, detail = probe_connection(make_tls_connection(host, port, ptimeout))
        if ok:
            _resolved = {"type": "tls", "host": host, "port": port}
            if verbose:
                print(f"[INFO] GVM auto → TLS {host}:{port}")
            return make_tls_connection(host, port, timeout)
        errors.append(f"tls://{host}:{port}: {detail}")
        if verbose:
            print(f"[INFO] GVM TLS no disponible ({detail}); probando Unix socket...")
    else:
        errors.append(f"tls://{host}:{port}: puerto cerrado")
        if verbose:
            print(f"[INFO] Puerto {host}:{port} cerrado; probando Unix socket...")

    conn = _try_unix_paths(candidates, ptimeout, timeout, verbose, errors)
    if conn is not None:
        return conn

    # Último recurso: proxy host -> docker exec (usuario con grupo docker)
    proxy_sock = _ensure_docker_proxy(cfg, verbose=verbose)
    if proxy_sock:
        ok, detail = probe_connection(make_unix_connection(proxy_sock, ptimeout))
        if ok:
            _resolved = {"type": "unix", "path": proxy_sock}
            if verbose:
                print(f"[INFO] GVM auto → proxy Docker {proxy_sock}")
            return make_unix_connection(proxy_sock, timeout)
        errors.append(f"unix:{proxy_sock} (proxy): {detail}")
    else:
        errors.append("proxy docker: no disponible")

    raise ConnectionError(
        "No se pudo conectar a GVM (auto: TLS + Unix). " + _connection_hint(errors)
    )


def verificar_transporte_gvm(
    config: Optional[dict] = None,
    config_path: str = DEFAULT_CONFIG_PATH,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Healthcheck para el monitor: prueba TLS y/o Unix según modo.
    Devuelve dict con status ok|error|warning y message.
    """
    global _resolved
    cfg = load_gvm_config(config_path=config_path, config=config)
    mode = _mode(cfg)
    host = _host(cfg)
    port = _port(cfg)
    details: List[str] = []
    candidates = _socket_candidates(cfg)

    def tls_ok() -> Optional[str]:
        if not tcp_port_open(host, port, timeout=2.0):
            details.append(f"TLS {host}:{port}: puerto cerrado")
            return None
        try:
            ok, detail = probe_connection(make_tls_connection(host, port, timeout))
            if ok:
                return f"TLS {host}:{port} OK"
            details.append(f"TLS: {detail}")
            return None
        except Exception as e:
            details.append(f"TLS: {e}")
            return None

    def unix_ok() -> Optional[str]:
        for path in candidates:
            if not os.path.exists(path):
                details.append(f"Unix {path}: no existe")
                continue
            try:
                ok, detail = probe_connection(make_unix_connection(path, timeout))
                if ok:
                    return f"Unix {path} OK"
                details.append(f"Unix {path}: {detail}")
            except Exception as e:
                details.append(f"Unix {path}: {e}")
        return None

    try:
        if mode == "tls":
            msg = tls_ok()
            if msg:
                _resolved = {"type": "tls", "host": host, "port": port}
                return {"status": "ok", "message": f"GVM conectado ({msg})", "transport": "tls"}
            return {"status": "error", "message": f"GVM TLS falló: {'; '.join(details)}", "transport": None}

        if mode == "unix":
            msg = unix_ok()
            if msg:
                for path in candidates:
                    if path in (msg or ""):
                        _resolved = {"type": "unix", "path": path}
                        break
                return {"status": "ok", "message": f"GVM conectado ({msg})", "transport": "unix"}
            return {
                "status": "error",
                "message": f"GVM Unix falló: {'; '.join(details)} | {MOUNT_HINT}",
                "transport": None,
            }

        tmsg = tls_ok()
        if tmsg:
            _resolved = {"type": "tls", "host": host, "port": port}
            return {
                "status": "ok",
                "message": f"GVM conectado ({tmsg})",
                "transport": "tls",
            }

        umsg = unix_ok()
        if umsg:
            for path in candidates:
                if path in umsg:
                    _resolved = {"type": "unix", "path": path}
                    break
            return {
                "status": "ok",
                "message": f"GVM conectado ({umsg}; TLS 9390 no disponible)",
                "transport": "unix",
            }

        return {
            "status": "error",
            "message": "GVM no responde por TLS ni Unix: "
            + "; ".join(details)
            + " | "
            + MOUNT_HINT,
            "transport": None,
        }
    except Exception as e:
        return {"status": "error", "message": f"Error de conexión GVM: {e}", "transport": None}


def reset_resolved_cache() -> None:
    """Útil en tests o si gvmd cambia de transporte en caliente."""
    global _resolved
    _resolved = None
