#!/usr/bin/env python3
"""
Script simplificado de actualización de OpenVAS
Solo hace git pull sin forzar ni hacer backups
"""
import subprocess
import sys


def git_pull(repo_path='/opt/gvm/'):
    """
    Hace un git pull simple en el repositorio
    No fuerza cambios, respeta configuración local
    """
    try:
        print(f"Verificando actualizaciones en {repo_path}...")
        
        # Hacer fetch para traer cambios remotos
        result_fetch = subprocess.run(
            ['git', 'fetch', 'origin'],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        if result_fetch.returncode != 0:
            print(f"Error al hacer fetch: {result_fetch.stderr}")
            return False
        
        # Verificar si hay cambios
        result_status = subprocess.run(
            ['git', 'rev-list', '--count', 'HEAD..origin/main'],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        if result_status.returncode == 0 and result_status.stdout.strip():
            commits_remotos = int(result_status.stdout.strip())
            if commits_remotos == 0:
                print("✓ Ya estás actualizado, no hay cambios remotos")
                return True
            else:
                print(f"Se encontraron {commits_remotos} commit(s) remoto(s)")
        
        # Hacer git pull
        print("Actualizando repositorio...")
        result_pull = subprocess.run(
            ['git', 'pull', 'origin', 'main'],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        if result_pull.returncode == 0:
            print("✓ Actualización completada exitosamente")
            print(result_pull.stdout)
            return True
        else:
            print(f"Error al hacer pull: {result_pull.stderr}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"Error en comando git: {e}")
        return False
    except Exception as e:
        print(f"Error inesperado: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Script de actualización de OpenVAS (git pull)")
    print("=" * 60)
    
    success = git_pull()
    
    if success:
        print("\n✓ Proceso completado")
        sys.exit(0)
    else:
        print("\n✗ Proceso falló")
        sys.exit(1)
    
