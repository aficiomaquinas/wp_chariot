"""
Utilidades para operaciones de sistema de archivos
"""

import os
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional

def ensure_dir_exists(directory: Path) -> None:
    """
    Asegura que un directorio exista, creándolo si es necesario
    
    Args:
        directory: Ruta del directorio
    """
    directory.mkdir(parents=True, exist_ok=True)
    
def create_backup(file_path: Path, backup_suffix: str = ".bak") -> Optional[Path]:
    """
    Crea una copia de seguridad de un archivo
    
    Args:
        file_path: Ruta del archivo a respaldar
        backup_suffix: Sufijo para el archivo de respaldo
        
    Returns:
        Path: Ruta del archivo de respaldo o None si no se pudo crear
    """
    if not file_path.exists():
        return None
        
    backup_path = file_path.with_suffix(file_path.suffix + backup_suffix)
    try:
        shutil.copy2(file_path, backup_path)
        print(f"✅ Copia de seguridad creada: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"❌ Error al crear copia de seguridad: {str(e)}")
        return None
