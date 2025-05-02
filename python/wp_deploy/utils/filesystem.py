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
        
def get_protected_files() -> List[str]:
    """
    Obtiene la lista de archivos protegidos que no deben eliminarse
    
    Returns:
        List[str]: Lista de patrones de archivos protegidos
    """
    return [
        'wp-config.php',
        'wp-config-ddev.php',
        '.gitignore',
        '.ddev/',
    ]
    
def get_default_exclusions() -> Dict[str, str]:
    """
    Obtiene el diccionario de exclusiones predeterminadas para rsync
    
    Returns:
        Dict[str, str]: Diccionario de exclusiones (clave -> patrón)
    """
    return {
        # Directorios de caché y optimización
        "cache": "wp-content/cache/",
        "litespeed": "wp-content/litespeed/",
        "jetpack-waf": "wp-content/jetpack-waf/",
        "wflogs": "wp-content/wflogs/",
        "rabbitloader": "wp-content/rabbitloader/",
        
        # Archivos de caché y configuración
        "object-cache": "wp-content/object-cache.php",
        "litespeed_conf": "wp-content/.litespeed_conf.dat",
        "patchstack-mu": "wp-content/mu-plugins/_patchstack.php",
        
        # Plugins de caché y optimización
        "akismet": "wp-content/plugins/akismet/",
        "patchstack": "wp-content/plugins/patchstack/",
        "autoptimize": "wp-content/plugins/autoptimize/",
        "bj-lazy-load": "wp-content/plugins/bj-lazy-load/",
        "cdn-enabler": "wp-content/plugins/cdn-enabler/",
        "critical-css": "wp-content/plugins/critical-css-for-wp/",
        "elasticpress": "wp-content/plugins/elasticpress/",
        "jetpack": "wp-content/plugins/jetpack/",
        "jetpack-search": "wp-content/plugins/jetpack-search/",
        "lazy-load-comments": "wp-content/plugins/lazy-load-for-comments/",
        "malcare-security": "wp-content/plugins/malcare-security/",
        "migrate-guru": "wp-content/plugins/migrate-guru/",
        "object-cache-pro": "wp-content/plugins/object-cache-pro/",
        "rabbitloader-plugin": "wp-content/plugins/rabbit-loader/",
        "cloudflare-turnstile": "wp-content/plugins/simple-cloudflare-turnstile/",
        "wp-ses": "wp-content/plugins/wp-ses/",
        "litespeed-cache": "wp-content/plugins/litespeed-cache/",
        "wordfence": "wp-content/plugins/wordfence/",
        "wp-maintenance-mode": "wp-content/plugins/wp-maintenance-mode/",
        
        # Temas predeterminados
        "default-themes": "wp-content/themes/twenty*",
        
        # Directorios de uploads por año
        "uploads-by-year": "wp-content/uploads/[0-9][0-9][0-9][0-9]/",
    } 