"""
Comandos para crear backups completos sin aplicar exclusiones
"""

import os
import shutil
import time
from pathlib import Path
import zipfile
from typing import Optional
from tqdm import tqdm


from config_yaml import get_yaml_config

def create_full_backup(site_alias: Optional[str] = None, output_dir: Optional[str] = None) -> str:
    """
    Crea un backup completo del directorio de la aplicación en formato ZIP
    sin aplicar ninguna exclusión.
    
    Args:
        site_alias: Alias del sitio a respaldar
        output_dir: Directorio donde guardar el backup (opcional)
        
    Returns:
        str: Ruta del archivo ZIP creado
    """
    config = get_yaml_config()
    
    # Seleccionar el sitio si se proporciona un alias
    if site_alias:
        config.select_site(site_alias)
        print(f"🔍 Sitio seleccionado: {site_alias}")
    
    # Obtener la ruta local del sitio
    local_path = Path(config.get("ssh", "local_path"))
    
    if not local_path.exists():
        raise ValueError(f"La ruta local no existe: {local_path}")
    
    # Generar nombre de archivo con timestamp
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    site_name = site_alias or config.get_default_site() or "wordpress"
    backup_filename = f"{site_name}_backup_{timestamp}.zip"
    
    # Determinar directorio de salida
    if output_dir:
        backup_dir = Path(output_dir)
    else:
        backup_dir = local_path.parent / "backups"
    
    # Crear el directorio si no existe
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Ruta completa del archivo ZIP
    backup_path = backup_dir / backup_filename
    
    print(f"📦 Creando backup completo sin exclusiones...")
    print(f"   Origen: {local_path}")
    print(f"   Destino: {backup_path}")
    
    # Primero contar archivos totales para la barra de progreso
    total_files = 0
    for _, _, files in os.walk(local_path):
        total_files += len(files)
    
    print(f"🔄 Procesando {total_files} archivos...")
    
    # Crear el archivo ZIP
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Obtener la ruta base para almacenar rutas relativas en el ZIP
        base_path = local_path
        
        # Contador de archivos
        file_count = 0
        
        progress_bar = tqdm(total=total_files, unit='files', desc="Comprimiendo")
        
        # Recorrer todos los archivos y directorios
        for root, _, files in os.walk(local_path):
            # Añadir archivos al ZIP
            for file in files:
                file_path = Path(root) / file
                # Ruta relativa para el archivo en el ZIP
                rel_path = file_path.relative_to(base_path)
                
                # Añadir archivo al ZIP
                zipf.write(file_path, rel_path)
                file_count += 1
                
                # Actualizar barra de progreso
                progress_bar.update(1)
        
        # Cerrar la barra de progreso
        progress_bar.close()
    
    print(f"✅ Backup completado: {file_count} archivos")
    print(f"📦 Archivo ZIP creado: {backup_path}")
    
    # Devolver la ruta del backup
    return str(backup_path) 