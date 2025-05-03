"""
Comandos para interactuar con WordPress a través de wp-cli
"""

import os
import argparse
import sys
from pathlib import Path
from typing import List, Optional

from config_yaml import get_yaml_config, get_nested
from utils.wp_cli import flush_cache, update_option, update_media_path

def flush_wp_cache(args: Optional[List[str]] = None) -> int:
    """
    Limpia la caché de WordPress
    
    Args:
        args: Lista de argumentos de línea de comandos
        
    Returns:
        int: Código de salida (0 si éxito, 1 si error)
    """
    parser = argparse.ArgumentParser(description="Limpia la caché de WordPress")
    
    parser.add_argument("--remote", action="store_true", help="Ejecutar en el servidor remoto")
    
    args = parser.parse_args(args)
    
    # Cargar configuración
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    ddev_wp_path = get_nested(config, "ddev", "webroot")
    
    # Limpiar caché
    success = flush_cache(
        path=local_path,
        remote=args.remote,
        remote_host=remote_host,
        remote_path=remote_path,
        use_ddev=True,
        wp_path=ddev_wp_path
    )
    
    return 0 if success else 1

def update_wp_option(args: Optional[List[str]] = None) -> int:
    """
    Actualiza una opción de WordPress
    
    Args:
        args: Lista de argumentos de línea de comandos
        
    Returns:
        int: Código de salida (0 si éxito, 1 si error)
    """
    parser = argparse.ArgumentParser(description="Actualiza una opción de WordPress")
    
    parser.add_argument("name", help="Nombre de la opción")
    parser.add_argument("value", help="Valor de la opción")
    parser.add_argument("--remote", action="store_true", help="Ejecutar en el servidor remoto")
    
    args = parser.parse_args(args)
    
    # Cargar configuración
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    ddev_wp_path = get_nested(config, "ddev", "webroot")
    
    # Actualizar opción
    success = update_option(
        option_name=args.name,
        option_value=args.value,
        path=local_path,
        remote=args.remote,
        remote_host=remote_host,
        remote_path=remote_path,
        use_ddev=True,
        wp_path=ddev_wp_path
    )
    
    return 0 if success else 1

def update_wp_media_path(args: Optional[List[str]] = None) -> int:
    """
    Actualiza la ruta de los medios en WordPress
    
    Args:
        args: Lista de argumentos de línea de comandos
        
    Returns:
        int: Código de salida (0 si éxito, 1 si error)
    """
    parser = argparse.ArgumentParser(description="Actualiza la ruta de los medios en WordPress")
    
    parser.add_argument("path", help="Nueva ruta para los archivos de medios")
    parser.add_argument("--remote", action="store_true", help="Ejecutar en el servidor remoto")
    
    args = parser.parse_args(args)
    
    # Cargar configuración
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    ddev_wp_path = get_nested(config, "ddev", "webroot")
    
    # Actualizar ruta de medios
    success = update_media_path(
        new_path=args.path,
        path=local_path,
        remote=args.remote,
        remote_host=remote_host,
        remote_path=remote_path,
        use_ddev=True,
        wp_path=ddev_wp_path
    )
    
    return 0 if success else 1

if __name__ == "__main__":
    # Script principal para interactuar con WordPress
    command_map = {
        "cache-flush": flush_wp_cache,
        "update-option": update_wp_option,
        "update-media-path": update_wp_media_path
    }
    
    # Verificar argumentos
    if len(sys.argv) < 2 or sys.argv[1] not in command_map:
        print("Uso: python -m wp_deploy.commands.wp_cli [comando] [opciones]")
        print("Comandos disponibles:")
        for cmd in command_map.keys():
            print(f"  {cmd}")
        sys.exit(1)
        
    # Ejecutar comando
    command = sys.argv[1]
    sys.exit(command_map[command](sys.argv[2:]))