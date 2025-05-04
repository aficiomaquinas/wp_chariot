"""
Utilidades para el sistema de parches

Este módulo contiene funciones auxiliares para trabajar con parches,
calculando checksums, detectando estados y manejando versiones de archivos.
Sigue el principio "fail fast" para garantizar comportamientos predecibles.
"""

import os
import hashlib
import json
import difflib
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, Set

from config_yaml import get_yaml_config, get_nested
from utils.ssh import SSHClient
from utils.wp_cli import get_item_version_from_path

# Estados de parches
PATCH_STATUS_PENDING = "PENDING"        # Registrado, no aplicado, checksum vigente
PATCH_STATUS_APPLIED = "APPLIED"        # Aplicado y vigente
PATCH_STATUS_ORPHANED = "ORPHANED"      # Checksum local no coincide, parche huérfano
PATCH_STATUS_OBSOLETED = "OBSOLETED"    # Parche aplicado pero local modificado después
PATCH_STATUS_MISMATCHED = "MISMATCHED"  # Aplicado pero versión remota diferente
PATCH_STATUS_STALE = "STALE"            # Parche antiguo, ya no relevante

# Estado legible para el usuario
PATCH_STATUS_LABELS = {
    PATCH_STATUS_PENDING: "⏳ Pendiente",
    PATCH_STATUS_APPLIED: "✅ Aplicado",
    PATCH_STATUS_ORPHANED: "⚠️ Huérfano",
    PATCH_STATUS_OBSOLETED: "🔄 Obsoleto",
    PATCH_STATUS_MISMATCHED: "❌ Desajustado",
    PATCH_STATUS_STALE: "📅 Caduco"
}

def calculate_checksum(file_path: Path) -> str:
    """
    Calcula el checksum MD5 de un archivo
    
    Args:
        file_path: Ruta al archivo
        
    Returns:
        str: Checksum MD5 del archivo
    """
    if not file_path.exists():
        return ""
        
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"⚠️ Error al calcular checksum: {str(e)}")
        return ""

def get_remote_file_checksum(ssh: SSHClient, remote_file: str) -> str:
    """
    Obtiene el checksum de un archivo en el servidor remoto
    
    Args:
        ssh: Cliente SSH conectado
        remote_file: Ruta al archivo en el servidor remoto
        
    Returns:
        str: Checksum MD5 del archivo remoto
    """
    if not ssh or not ssh.client:
        return ""
    
    # Verificar si el archivo existe
    cmd = f"test -f '{remote_file}' && echo 'EXISTS' || echo 'NOT_FOUND'"
    code, stdout, stderr = ssh.execute(cmd)
    
    if "NOT_FOUND" in stdout:
        return ""
    
    # Calcular checksum MD5
    cmd = f"md5sum '{remote_file}' | awk '{{print $1}}'"
    code, stdout, stderr = ssh.execute(cmd)
    
    if code != 0:
        return ""
        
    return stdout.strip()

def get_remote_file_version(ssh: SSHClient, file_path: str, wp_path: str, wp_memory_limit: str) -> str:
    """
    Obtiene la versión de un plugin o tema desde un archivo en el servidor remoto
    
    Args:
        ssh: Cliente SSH conectado
        file_path: Ruta al archivo
        wp_path: Ruta a WordPress en el servidor remoto
        wp_memory_limit: Límite de memoria para PHP
        
    Returns:
        str: Versión del plugin o tema, o cadena vacía si no se puede determinar
    """
    if not ssh or not ssh.client:
        return ""
        
    try:
        # Usar directamente wp_path como base sin intentar obtener ABSPATH
        wp_base_path = wp_path
        
        # Normalizar rutas
        if not wp_base_path.endswith("/"):
            wp_base_path += "/"
            
        # Eliminar cualquier prefijo de ruta absoluta
        if file_path.startswith("/"):
            file_path = file_path.lstrip("/")
            
        # Detectar tipo y versión usando WP-CLI
        if "/plugins/" in file_path or "/themes/" in file_path:
            cmd = f"cd {wp_path} && php -d memory_limit={wp_memory_limit} $(which wp) plugin list --format=json || echo 'ERROR'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0 or "ERROR" in stdout:
                return ""
                
            # Analizar la ruta para determinar si es un plugin o tema
            item_type = "other"
            item_slug = ""
            
            if '/plugins/' in file_path:
                item_type = "plugin"
                parts = file_path.split('/')
                for i, part in enumerate(parts):
                    if part == "plugins" and i + 1 < len(parts):
                        item_slug = parts[i + 1]
                        break
            elif '/themes/' in file_path:
                item_type = "theme"
                parts = file_path.split('/')
                for i, part in enumerate(parts):
                    if part == "themes" and i + 1 < len(parts):
                        item_slug = parts[i + 1]
                        break
                
            # Si no se ha podido determinar el tipo o el slug, no se puede obtener versión
            if item_type == "other" or not item_slug:
                return ""
            
            # Obtener la versión usando WP-CLI
            if item_type == "plugin":
                cmd = f"cd {wp_path} && php -d memory_limit={wp_memory_limit} $(which wp) plugin get {item_slug} --format=json"
            else:  # theme
                cmd = f"cd {wp_path} && php -d memory_limit={wp_memory_limit} $(which wp) theme get {item_slug} --format=json"
                
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0 or not stdout.strip():
                return ""
                
            try:
                data = json.loads(stdout)
                return data.get("version", "")
            except:
                return ""
        
        return ""
    except Exception as e:
        print(f"⚠️ Error al obtener versión remota: {str(e)}")
        return ""

def get_local_file_version(file_path: str, local_base_path: Path) -> str:
    """
    Obtiene la versión de un plugin o tema desde un archivo local
    
    Args:
        file_path: Ruta relativa al archivo
        local_base_path: Ruta base local a WordPress
        
    Returns:
        str: Versión del plugin o tema, o cadena vacía si no se puede determinar
    """
    try:
        # Convertir a ruta relativa si es necesario
        if file_path.startswith("/"):
            file_path = file_path.lstrip("/")
            
        # Obtener versión
        item_type, item_slug, version = get_item_version_from_path(
            file_path,
            local_base_path,
            remote=False,
            use_ddev=True
        )
        
        return version
    except Exception as e:
        print(f"⚠️ Error al obtener versión local: {str(e)}")
        return ""

def show_file_diff(local_file: Path, remote_file: str, ssh: Optional[SSHClient] = None) -> None:
    """
    Muestra las diferencias entre un archivo local y uno remoto
    
    Args:
        local_file: Ruta al archivo local
        remote_file: Ruta al archivo remoto
        ssh: Cliente SSH conectado (opcional, se crea uno nuevo si no se proporciona)
    """
    needs_disconnect = False
    
    try:
        # Verificar si local_file existe
        if not local_file.exists():
            print(f"❌ El archivo local no existe: {local_file}")
            return
            
        # Verificar SSH
        if not ssh or not ssh.client:
            print(f"⚠️ No hay conexión SSH, no se pueden mostrar diferencias")
            return
            
        # Obtener contenido del archivo remoto
        cmd = f"cat '{remote_file}'"
        code, remote_content, stderr = ssh.execute(cmd)
        
        if code != 0:
            print(f"❌ No se pudo leer el archivo remoto: {remote_file}")
            if stderr:
                print(f"   Error: {stderr}")
            return
            
        # Leer contenido del archivo local
        with open(local_file, 'r', encoding='utf-8', errors='replace') as f:
            local_content = f.read()
            
        # Dividir en líneas
        local_lines = local_content.splitlines()
        remote_lines = remote_content.splitlines()
        
        # Generar diflist
        diff = list(difflib.unified_diff(
            remote_lines, local_lines,
            fromfile=f"{remote_file} (remoto)",
            tofile=f"{local_file} (local)",
            lineterm="",
            n=3
        ))
        
        # Mostrar el diff
        if diff:
            print(f"\n📊 Diferencias entre los archivos:")
            for line in diff:
                # Colorear las líneas según el tipo
                if line.startswith('+'):
                    print(f"\033[92m{line}\033[0m")  # Verde para adiciones
                elif line.startswith('-'):
                    print(f"\033[91m{line}\033[0m")  # Rojo para eliminaciones
                elif line.startswith('@@'):
                    print(f"\033[96m{line}\033[0m")  # Cian para marcadores
                else:
                    print(line)
            print("")
        else:
            print(f"✅ No hay diferencias entre los archivos\n")
    except Exception as e:
        print(f"⚠️ Error al mostrar diferencias: {str(e)}")
    finally:
        # Cerrar conexión SSH si la creamos aquí
        if needs_disconnect and ssh and ssh.client:
            ssh.disconnect()

def determine_patch_status(patch_info: Dict[str, Any], 
                          remote_exists: bool, 
                          remote_checksum: str, 
                          local_exists: bool,
                          current_local_checksum: str,
                          current_remote_version: str,
                          registered_local_checksum: str) -> Tuple[str, Dict]:
    """
    Determina el estado de un parche basado en checksums y versiones
    
    Args:
        patch_info: Información del parche desde el archivo lock
        remote_exists: True si el archivo remoto existe
        remote_checksum: Checksum del archivo remoto
        local_exists: True si el archivo local existe
        current_local_checksum: Checksum actual del archivo local
        current_remote_version: Versión del plugin remoto
        registered_local_checksum: Checksum registrado del archivo local
        
    Returns:
        Tuple[str, Dict]: Código de estado del parche y detalles
    """
    details = {
        "remote_exists": remote_exists,
        "remote_checksum": remote_checksum,
        "local_exists": local_exists,
        "current_local_checksum": current_local_checksum,
        "registered_local_checksum": registered_local_checksum,
        "current_remote_version": current_remote_version,
        "registered_remote_version": patch_info.get("remote_version", ""),
        "messages": []
    }
    
    if remote_exists:
        if patch_info.get("applied_date"):
            # Parche está marcado como aplicado
            patched_checksum = patch_info.get("patched_checksum", "")
            
            if remote_checksum == patched_checksum:
                # El checksum remoto coincide con el del parche aplicado
                if local_exists and current_local_checksum == registered_local_checksum:
                    return PATCH_STATUS_APPLIED, details
                else:
                    # El archivo local ha cambiado, parche obsoleto
                    return PATCH_STATUS_OBSOLETED, details
            else:
                # El checksum remoto no coincide, parche desajustado
                if details.get("current_remote_version") != patch_info.get("remote_version"):
                    # La versión remota cambió, parche caduco
                    return PATCH_STATUS_STALE, details
                else:
                    # Mismo plugin pero archivo modificado en el servidor
                    return PATCH_STATUS_MISMATCHED, details
        else:
            # Parche no está aplicado
            if local_exists and current_local_checksum == registered_local_checksum:
                # El archivo local coincide con el registrado, parche pendiente
                return PATCH_STATUS_PENDING, details
            else:
                # El archivo local ha cambiado, parche huérfano
                return PATCH_STATUS_ORPHANED, details
    else:
        # El archivo remoto no existe
        details["messages"].append(f"El archivo remoto no existe")
        
        if patch_info.get("applied_date"):
            # Parche está marcado como aplicado pero el archivo no existe
            return PATCH_STATUS_MISMATCHED, details
        else:
            # Parche no aplicado y archivo remoto no existe
            if local_exists and current_local_checksum == registered_local_checksum:
                # Archivo local correcto, pendiente (será un archivo nuevo)
                return PATCH_STATUS_PENDING, details
            else:
                # Archivo local modificado, huérfano
                return PATCH_STATUS_ORPHANED, details
    
    # Estado por defecto
    return PATCH_STATUS_PENDING, details

def get_site_specific_lock_file(site_name: Optional[str] = None) -> Path:
    """
    Obtiene la ruta al archivo lock específico para un sitio
    
    Args:
        site_name: Nombre del sitio, None para el sitio predeterminado
        
    Returns:
        Path: Ruta al archivo lock específico para el sitio
    """
    # Si no hay sitio específico, usar el archivo genérico
    if not site_name:
        return Path(__file__).resolve().parent.parent / "patches.lock.json"
    
    # Si hay sitio, usar archivo específico
    return Path(__file__).resolve().parent.parent / f"patches-{site_name}.lock.json"

def load_lock_file(lock_file: Path) -> Dict:
    """
    Carga el archivo lock con información de parches
    
    Args:
        lock_file: Ruta al archivo lock
        
    Returns:
        Dict: Datos del archivo lock
    """
    # Crear estructura inicial del archivo lock
    lock_data = {
        "patches": {},
        "last_updated": datetime.datetime.now().isoformat()
    }
    
    # Verificar si existe el archivo
    if lock_file.exists():
        try:
            with open(lock_file, 'r') as f:
                lock_data = json.load(f)
                
            print(f"✅ Archivo lock '{lock_file.name}' cargado: {len(lock_data.get('patches', {}))} parches registrados")
            return lock_data
        except Exception as e:
            print(f"⚠️ Error al cargar archivo lock: {str(e)}")
            print("   Se creará un nuevo archivo lock.")
    else:
        print(f"ℹ️ No se encontró archivo lock. Se creará uno nuevo.")
        
    return lock_data

def save_lock_file(lock_file: Path, lock_data: Dict, site_name: Optional[str] = None) -> bool:
    """
    Guarda los datos del archivo lock
    
    Args:
        lock_file: Ruta al archivo lock
        lock_data: Datos a guardar
        site_name: Nombre del sitio (para mensajes informativos)
        
    Returns:
        bool: True si se guardó correctamente, False en caso contrario
    """
    try:
        # Actualizar fecha de modificación
        lock_data["last_updated"] = datetime.datetime.now().isoformat()
        
        # Asegurarnos de que el directorio padre existe
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(lock_file, 'w') as f:
            json.dump(lock_data, f, indent=2)
            
        # Mostrar información sobre el sitio si es un archivo específico
        if site_name:
            print(f"✅ Archivo lock para el sitio '{site_name}' actualizado: {lock_file}")
        else:
            print(f"✅ Archivo lock general actualizado: {lock_file}")
            
        return True
    except Exception as e:
        print(f"⚠️ Error al guardar archivo lock: {str(e)}")
        return False 