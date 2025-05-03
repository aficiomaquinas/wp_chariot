#!/usr/bin/env python3
"""
Herramienta de línea de comandos para gestionar parches

Permite gestionar parches para plugins y temas de WordPress, 
guardando un registro de los parches aplicados.
"""

import argparse
import sys
from typing import List, Optional

from commands.patch import (
    add_patch, remove_patch, apply_patch, list_patches, rollback_patch
)

def parse_args(args: Optional[List[str]] = None):
    """
    Parsea los argumentos de línea de comandos
    
    Args:
        args: Lista de argumentos (si es None, usa sys.argv)
        
    Returns:
        argparse.Namespace: Argumentos parseados
    """
    parser = argparse.ArgumentParser(
        description="Gestiona parches para plugins y temas de WordPress"
    )
    
    # Argumentos específicos para acciones
    parser.add_argument("--add", metavar="FILE_PATH", help="Registra un nuevo parche")
    parser.add_argument("--remove", metavar="FILE_PATH", help="Elimina un parche del registro")
    parser.add_argument("--list", action="store_true", help="Lista los parches registrados")
    parser.add_argument("--rollback", metavar="FILE_PATH", help="Revierte un parche aplicado anteriormente")
    parser.add_argument("--info", action="store_true", help="Muestra información detallada al aplicar parches")
    parser.add_argument("--dry-run", action="store_true", help="Muestra qué se haría sin realizar cambios reales")
    parser.add_argument("--description", metavar="DESC", help="Descripción del parche (para usar con --add)")
    parser.add_argument("--force", action="store_true", help="Forzar aplicación del parche incluso si las versiones no coinciden")
    
    # Argumento posicional para el archivo a parchar
    parser.add_argument("file_path", nargs="?", help="Ruta relativa al archivo a parchar")
    
    return parser.parse_args(args)

def main(args: Optional[List[str]] = None) -> int:
    """
    Punto de entrada principal para el CLI
    
    Args:
        args: Lista de argumentos (si es None, usa sys.argv)
        
    Returns:
        int: Código de salida (0 si éxito, no cero en caso de error)
    """
    args = parse_args(args)
    
    # Procesar comandos
    if args.list:
        # Listar parches
        list_patches()
        return 0
        
    elif args.add:
        # Agregar parche
        description = args.description or ""
        success = add_patch(args.add, description)
        return 0 if success else 1
        
    elif args.remove:
        # Eliminar parche
        success = remove_patch(args.remove)
        return 0 if success else 1
        
    elif args.rollback:
        # Revertir parche
        success = rollback_patch(args.rollback, args.dry_run)
        return 0 if success else 1
        
    elif args.file_path:
        # Aplicar parche específico
        success = apply_patch(
            args.file_path, 
            args.dry_run, 
            args.info,
            args.force
        )
        return 0 if success else 1
        
    else:
        # Aplicar todos los parches
        success = apply_patch(
            None,  # None indica aplicar todos los parches
            args.dry_run,
            args.info,
            args.force
        )
        return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 