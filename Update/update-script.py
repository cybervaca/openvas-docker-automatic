#!/usr/bin/env python3
"""
Actualiza /opt/gvm al commit exacto de origin/main.

Usa fetch + reset --hard (no git pull) para evitar el error de Git:
  "Necesita especificar cómo reconciliar las ramas divergentes"

Config/config.json y demás ficheros en .gitignore NO se tocan.
Cualquier commit o cambio local en ficheros rastreados se descarta
(comportamiento deseado en flota de servidores).
"""
import argparse
import subprocess
import sys


def run_git(args, repo_path, check=True):
    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"git {' '.join(args)} falló: {err}")
    return result


def sync_to_origin_main(repo_path="/opt/gvm/", branch="main", remote="origin"):
    """
    Alinea el repo local con remote/branch de forma determinista.
    """
    print(f"Sincronizando {repo_path} → {remote}/{branch}...")

    run_git(["remote", "get-url", remote], repo_path)

    print(f"→ git fetch {remote}")
    run_git(["fetch", remote], repo_path)

    target = f"{remote}/{branch}"
    before = run_git(["rev-parse", "--short", "HEAD"], repo_path).stdout.strip()
    remote_sha = run_git(["rev-parse", "--short", target], repo_path).stdout.strip()

    if before == remote_sha:
        print(f"✓ Ya actualizado en {before} (= {target})")
        return True

    behind = run_git(
        ["rev-list", "--count", f"HEAD..{target}"], repo_path
    ).stdout.strip()
    ahead = run_git(
        ["rev-list", "--count", f"{target}..HEAD"], repo_path
    ).stdout.strip()
    print(f"  Local:  {before} (ahead={ahead}, behind={behind})")
    print(f"  Remoto: {remote_sha}")

    # Evitar estar en detached HEAD o en otra rama
    print(f"→ git checkout {branch}")
    co = run_git(["checkout", branch], repo_path, check=False)
    if co.returncode != 0:
        # Crear rama local siguiendo al remoto si no existe
        print(f"→ git checkout -B {branch} {target}")
        run_git(["checkout", "-B", branch, target], repo_path)

    print(f"→ git reset --hard {target}")
    run_git(["reset", "--hard", target], repo_path)

    after = run_git(["rev-parse", "--short", "HEAD"], repo_path).stdout.strip()
    print(f"✓ Actualizado {before} → {after}")
    log = run_git(["log", "-1", "--oneline"], repo_path).stdout.strip()
    print(f"  HEAD: {log}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Sincroniza el repo OpenVAS con origin/main (reset --hard)"
    )
    parser.add_argument(
        "-p",
        "--path",
        default="/opt/gvm/",
        help="Ruta del repositorio (default: /opt/gvm/)",
    )
    parser.add_argument(
        "-b",
        "--branch",
        default="main",
        help="Rama remota a seguir (default: main)",
    )
    parser.add_argument(
        "-r",
        "--remote",
        default="origin",
        help="Remoto git (default: origin)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Actualización OpenVAS → origin/main (fetch + reset --hard)")
    print("=" * 60)

    try:
        sync_to_origin_main(args.path, args.branch, args.remote)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n✓ Proceso completado")
    print("  Nota: Config/config.json y ficheros ignorados se conservan.")
    sys.exit(0)


if __name__ == "__main__":
    main()
