"""
Utilidades para operaciones de sistema de archivos
"""

import os
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
import time

def ensure_dir_exists(directory: Path) -> None:
    """
    Asegura que un directorio exista, creándolo si es necesario
    
    Args:
        directory: Ruta del directorio
    """
    directory.mkdir(parents=True, exist_ok=True)
    
def create_backup(file_path: Path, backup_suffix: str = ".bak", config=None) -> Optional[Path]:
    """
    Crea una copia de seguridad de un archivo o directorio
    
    Args:
        file_path: Ruta del archivo o directorio a respaldar
        backup_suffix: Sufijo para el archivo/directorio de respaldo
        config: Objeto de configuración que contiene las definiciones de archivos protegidos
        
    Returns:
        Path: Ruta del archivo/directorio de respaldo o None si no se pudo crear
    """
    if not file_path.exists():
        return None
    
    # Generar un nombre único para la copia de seguridad
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    
    if file_path.is_file():
        # Para archivos, usar el sufijo
        backup_path = file_path.with_suffix(file_path.suffix + backup_suffix)
        try:
            shutil.copy2(file_path, backup_path)
            print(f"✅ Copia de seguridad creada: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"❌ Error al crear copia de seguridad: {str(e)}")
            return None
    elif file_path.is_dir():
        # Para directorios, crear un directorio con timestamp en la misma ruta
        parent_dir = file_path.parent
        dir_name = file_path.name
        backup_dir = parent_dir / f"{dir_name}_backup_{timestamp}"
        
        try:
            # Obtener la lista de archivos protegidos desde la configuración
            protected_files = []
            
            if config:
                # Intentar obtener los archivos protegidos de la configuración
                if hasattr(config, 'get_protected_files'):
                    protected_files = config.get_protected_files()
                elif hasattr(config, 'config') and isinstance(config.config, dict):
                    # Intenta obtener la lista de archivos protegidos desde el diccionario de configuración
                    protected_files = config.config.get('protected_files', [])
            
            # Si no hay configuración o no se encuentran archivos protegidos, fail fast
            if not protected_files:
                print("❌ Error: No se encontró configuración de archivos protegidos")
                print("   No se puede crear una copia de seguridad sin saber qué archivos proteger")
                print("   Asegúrese de que la sección 'protected_files' esté definida en config.yaml")
                return None
                
            # Crear el directorio de backup
            if not backup_dir.exists():
                backup_dir.mkdir(parents=True)
            
            # Copiar solo los archivos protegidos especificados en la configuración
            files_copied = 0
            for file_pattern in protected_files:
                # Manejar patrones con comodines
                if '*' in file_pattern:
                    matches = list(file_path.glob(file_pattern))
                    for source_file in matches:
                        if source_file.is_file():
                            # Mantener la estructura relativa de subdirectorios para archivos con comodines
                            rel_path = source_file.relative_to(file_path)
                            dest_file = backup_dir / rel_path
                            # Crear directorios padres si es necesario
                            dest_file.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source_file, dest_file)
                            files_copied += 1
                else:
                    # Archivos específicos (sin comodines)
                    source_file = file_path / file_pattern
                    if source_file.exists() and source_file.is_file():
                        dest_file = backup_dir / file_pattern
                        # Crear directorios padres si es necesario
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_file, dest_file)
                        files_copied += 1
            
            if files_copied > 0:
                print(f"✅ Copia de seguridad creada en {backup_dir} ({files_copied} archivos)")
                return backup_dir
            else:
                # No se copió ningún archivo
                print("⚠️ No se encontraron archivos importantes para respaldar en la ruta especificada")
                # Eliminar el directorio vacío
                backup_dir.rmdir()
                return None
        except Exception as e:
            print(f"❌ Error al crear copia de seguridad del directorio: {str(e)}")
            return None
    else:
        # No es ni archivo ni directorio (symlink u otro)
        print(f"⚠️ No se puede crear copia de seguridad: el tipo de {file_path} no es compatible")
        return None
