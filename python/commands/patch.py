"""
Módulo para aplicar parches a plugins de terceros

Este módulo proporciona funciones para aplicar parches de plugins locales
al servidor remoto, con seguimiento mediante un archivo lock.
"""

import os
import sys
import tempfile
import shutil
import difflib
import json
import hashlib
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, Set

from config_yaml import get_yaml_config, get_nested
from utils.ssh import SSHClient
from utils.filesystem import ensure_dir_exists, create_backup
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

class PatchManager:
    """
    Clase para gestionar la aplicación de parches
    
    Notas:
    - Los parches se gestionan por sitio, con un archivo de bloqueo específico para cada sitio.
    - Si existe un archivo `patches.lock.json` general, se usará como punto de partida
      para los sitios que no tengan un archivo específico.
    - Los archivos de bloqueo de sitios se nombran como `patches-{sitename}.lock.json`.
    """
    
    def __init__(self):
        """
        Inicializa el gestor de parches
        """
        self.config = get_yaml_config(verbose=False)
        
        # Cargar configuración
        self.remote_host = self.config.get("ssh", "remote_host")
        self.remote_path = self.config.get("ssh", "remote_path")
        self.local_path = Path(self.config.get("ssh", "local_path"))
        
        # Asegurarse de que las rutas remotas terminen con /
        if not self.remote_path.endswith("/"):
            self.remote_path += "/"
        
        # Cargar configuración de seguridad
        self.production_safety = get_nested(self.config, "security", "production_safety") == "enabled"
        
        # Determinar el sitio actual para el archivo lock específico por sitio
        self.current_site = self.config.current_site
        
        # Generar el nombre del archivo lock: patches-sitename.lock.json si hay un sitio actual,
        # o patches.lock.json si no hay sitio o es el predeterminado
        lock_filename = "patches.lock.json"
        if self.current_site:
            lock_filename = f"patches-{self.current_site}.lock.json"
        
        # Crear la ruta al archivo lock (ahora solo dos niveles arriba con la estructura aplanada)
        self.lock_file = Path(__file__).resolve().parent.parent / lock_filename
        
        # Cargar archivo lock
        self.lock_data = self.load_lock_file()
        
        # Cargar archivos protegidos
        self.protected_files = self.config.get_protected_files()
        
        # Cargar límite de memoria para WP-CLI
        self.wp_memory_limit = self.config.get_wp_memory_limit()
        
        # Inicializar lista de parches
        self.patches = []
        
    def load_lock_file(self) -> Dict:
        """
        Carga el archivo lock con información de parches
        
        Returns:
            Dict: Datos del archivo lock
        """
        # Crear estructura inicial del archivo lock
        lock_data = {
            "patches": {},
            "last_updated": datetime.datetime.now().isoformat()
        }
        
        # Verificar si existe el archivo específico del sitio
        if self.lock_file.exists():
            try:
                with open(self.lock_file, 'r') as f:
                    lock_data = json.load(f)
                    
                print(f"✅ Archivo lock '{self.lock_file.name}' cargado: {len(lock_data.get('patches', {}))} parches registrados")
                return lock_data
            except Exception as e:
                print(f"⚠️ Error al cargar archivo lock específico del sitio: {str(e)}")
                print("   Se creará un nuevo archivo lock para este sitio.")
        elif self.current_site:
            # Si no existe el archivo específico del sitio pero sí el genérico,
            # intentar cargar el archivo genérico y usarlo como base
            generic_lock_file = Path(__file__).resolve().parent.parent / "patches.lock.json"
            if generic_lock_file.exists():
                try:
                    with open(generic_lock_file, 'r') as f:
                        lock_data = json.load(f)
                        
                    print(f"ℹ️ Usando archivo lock genérico como base: {len(lock_data.get('patches', {}))} parches encontrados")
                    print(f"   Se guardará como '{self.lock_file.name}' para este sitio.")
                    # No guardamos inmediatamente el archivo específico para evitar duplicar datos innecesariamente
                except Exception as e:
                    print(f"⚠️ Error al cargar archivo lock genérico: {str(e)}")
        else:
            print(f"ℹ️ No se encontró archivo lock. Se creará uno nuevo.")
            
        return lock_data
    
    def save_lock_file(self):
        """
        Guarda los datos del archivo lock
        """
        try:
            # Actualizar fecha de modificación
            self.lock_data["last_updated"] = datetime.datetime.now().isoformat()
            
            # Asegurarnos de que el directorio padre existe
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.lock_file, 'w') as f:
                json.dump(self.lock_data, f, indent=2)
                
            # Mostrar información sobre el sitio si es un archivo específico
            if self.current_site:
                print(f"✅ Archivo lock para el sitio '{self.current_site}' actualizado: {self.lock_file}")
            else:
                print(f"✅ Archivo lock general actualizado: {self.lock_file}")
        except Exception as e:
            print(f"⚠️ Error al guardar archivo lock: {str(e)}")
    
    def calculate_checksum(self, file_path: Path) -> str:
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
        
    def check_remote_connection(self) -> bool:
        """
        Verifica la conexión con el servidor remoto
        
        Returns:
            bool: True si la conexión es exitosa, False en caso contrario
        """
        print(f"🔄 Verificando conexión con el servidor remoto: {self.remote_host}")
        
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                return False
                
            # Verificar acceso a la ruta remota
            cmd = f"test -d {self.remote_path} && echo 'OK' || echo 'NOT_FOUND'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error al verificar ruta remota: {stderr}")
                return False
                
            if "OK" not in stdout:
                print(f"❌ La ruta remota no existe: {self.remote_path}")
                return False
                
            print(f"✅ Conexión verificada con éxito")
            return True
            
    def list_patches(self, verbose: bool = False) -> None:
        """
        Muestra la lista de parches registrados con estado detallado
        
        Args:
            verbose: Si es True, muestra información adicional
        """
        if not self.lock_data.get("patches", {}):
            print("ℹ️ No hay parches registrados.")
            print("   Puedes agregar parches con el comando 'patch --add ruta/al/archivo'")
            return
            
        print("🔍 Parches registrados:")
        
        # Verificar conexión SSH para estados más precisos
        ssh = None
        connected = False
        try:
            connected = self.check_remote_connection()
            if connected:
                ssh = SSHClient(self.remote_host)
                ssh.connect()
                print() # Línea en blanco para separar la conexión de los resultados
        except Exception as e:
            print(f"⚠️ Error de conexión: {str(e)}")
            connected = False
            
        try:
            # Procesar cada parche registrado
            php_memory_error_shown = False
            
            for file_path, info in self.lock_data.get("patches", {}).items():
                # Determinar el nombre del plugin o tema
                if '/plugins/' in file_path:
                    plugin_name = file_path.split('/')[2]
                    item_type = "Plugin"
                elif '/themes/' in file_path:
                    plugin_name = file_path.split('/')[2]
                    item_type = "Tema"
                elif '/mu-plugins/' in file_path:
                    plugin_name = os.path.basename(file_path)
                    item_type = "MU Plugin"
                else:
                    plugin_name = os.path.basename(file_path)
                    item_type = "Archivo"
                
                description = info.get("description", "Sin descripción")
                applied_date = info.get("applied_date", "")
                local_checksum = info.get("local_checksum", "Desconocido")
                local_version = info.get("local_version", "Desconocida")
                remote_version = info.get("remote_version", "Desconocida")
                
                # Obtener estado detallado si hay conexión SSH
                status_details = {"messages": []}
                if connected and ssh and ssh.client:
                    try:
                        status_code, status_details = self.get_patch_status(file_path, ssh)
                        status_label = PATCH_STATUS_LABELS.get(status_code, "⏳ Registrado")
                        
                        # Capturar errores de memoria PHP solo una vez
                        error_msg = status_details.get("error", "")
                        if "memory size" in error_msg and not php_memory_error_shown:
                            print(f"⚠️ Error de memoria PHP al consultar información. Algunos detalles pueden no mostrarse.")
                            php_memory_error_shown = True
                    except Exception as e:
                        status_code = PATCH_STATUS_APPLIED if applied_date else PATCH_STATUS_PENDING
                        status_label = PATCH_STATUS_LABELS.get(status_code, "⏳ Registrado")
                        status_details["messages"].append(f"Error al obtener estado: {str(e)}")
                else:
                    # Estado básico si no hay conexión
                    status_code = PATCH_STATUS_APPLIED if applied_date else PATCH_STATUS_PENDING
                    status_label = PATCH_STATUS_LABELS.get(status_code, "⏳ Registrado")
                
                # Mostrar información del parche de forma compacta
                print(f"  - {file_path}")
                print(f"    • {item_type}: {plugin_name}")
                print(f"    • Descripción: {description}")
                print(f"    • Estado: {status_label} {applied_date and f'({applied_date})' or '(No aplicado)'}")
                
                # Mostrar versiones en la misma línea para ser más compacto
                version_info = f"Versión local: {local_version}"
                if applied_date and remote_version != "Desconocida":
                    version_info += f" | Versión remota: {remote_version}"
                print(f"    • {version_info}")
                print(f"    • Checksum local: {local_checksum}")
                
                # Mostrar mensajes de estado importantes si hay
                for message in status_details.get("messages", []):
                    if "Error" in message or "error" in message:
                        print(f"    • ⚠️ {message}")
                
                # En modo verbose, mostrar más detalles
                if verbose and status_details:
                    if status_details.get("current_local_checksum") and status_details.get("current_local_checksum") != local_checksum:
                        print(f"    • Checksum local actual: {status_details.get('current_local_checksum')}")
                    if status_details.get("current_remote_checksum"):
                        print(f"    • Checksum remoto actual: {status_details.get('current_remote_checksum')}")
                    if status_details.get("remote_backups"):
                        print(f"    • Backups encontrados: {len(status_details.get('remote_backups'))}")
                        for i, backup in enumerate(status_details.get("remote_backups")[:3]):
                            print(f"      - {os.path.basename(backup)}")
                        if len(status_details.get("remote_backups")) > 3:
                            print(f"      ... y {len(status_details.get('remote_backups')) - 3} más")
                
                print()
        finally:
            # Cerrar la conexión SSH si está abierta
            if ssh and ssh.client:
                ssh.disconnect()
        
    def check_safety(self, force_dry_run: bool = False) -> bool:
        """
        Verifica si se pueden aplicar parches según la configuración de seguridad
        
        Args:
            force_dry_run: Si es True, fuerza modo dry-run en entorno protegido en vez de abortar
            
        Returns:
            bool: True si es seguro continuar, False si no se debe permitir, None si se debe forzar dry-run
        """
        if self.production_safety:
            if force_dry_run:
                print("⚠️ ADVERTENCIA: Protección de producción está activada.")
                print("   Se ejecutará en modo simulación (dry-run) para mostrar qué cambios se harían.")
                print("   Para aplicar cambios reales, debes desactivar 'production_safety' en la configuración.")
                return None  # Indica que se debe forzar dry-run
            else:
                print("⛔ ERROR: No se pueden aplicar parches con la protección de producción activada.")
                print("   Esta operación podría sobrescribir código en el servidor de producción.")
                print("   Para continuar, debes desactivar 'production_safety' en la configuración YAML:")
                print("   security:")
                print("     production_safety: disabled")
                print("")
                print("   ⚠️ ADVERTENCIA: Solo desactiva esta protección si estás completamente seguro de lo que haces.")
                print("")
                print("   Puedes usar --info para ver qué cambios se harían sin aplicarlos.")
                return False
            
        return True
    
    def get_remote_file_checksum(self, ssh: SSHClient, remote_file: str) -> str:
        """
        Obtiene el checksum MD5 de un archivo remoto
        
        Args:
            ssh: Conexión SSH activa
            remote_file: Ruta absoluta al archivo remoto
            
        Returns:
            str: Checksum MD5 del archivo o cadena vacía si hay error
        """
        cmd = f"md5sum \"{remote_file}\" | cut -d' ' -f1"
        code, stdout, stderr = ssh.execute(cmd)
        
        if code != 0 or not stdout.strip():
            return ""
            
        return stdout.strip()
        
    def get_remote_file_version(self, ssh: SSHClient, file_path: str) -> str:
        """
        Obtiene la versión del plugin o tema en el servidor remoto
        
        Args:
            ssh: Conexión SSH activa
            file_path: Ruta relativa al archivo
            
        Returns:
            str: Versión del plugin/tema o cadena vacía si no se puede determinar
        """
        try:
            item_type, slug, _ = get_item_version_from_path(
                file_path, 
                self.local_path, 
                remote=True,
                remote_host=self.remote_host,
                remote_path=self.remote_path,
                memory_limit=self.wp_memory_limit
            )
            
            if not slug:
                return ""
                
            # Usar el WP-CLI remoto para obtener la versión
            if item_type == "plugin":
                cmd = f"php -d memory_limit={self.wp_memory_limit} $(which wp) plugin get {slug} --format=json --path={self.remote_path}"
                code, stdout, stderr = ssh.execute(cmd)
                
                if code != 0 or not stdout.strip():
                    # Si hay error, puede ser por falta de memoria
                    if "Fatal error: Allowed memory size" in stderr:
                        print(f"⚠️ Error de memoria al obtener información del plugin: {slug}")
                        print(f"   Intentando con límite de memoria aumentado...")
                        
                        # Intentar con más memoria
                        cmd = f"php -d memory_limit=1024M $(which wp) plugin get {slug} --format=json --path={self.remote_path}"
                        code, stdout, stderr = ssh.execute(cmd)
                        
                        if code != 0 or not stdout.strip():
                            return ""
                    else:
                        return ""
                    
                try:
                    data = json.loads(stdout)
                    return data.get("version", "")
                except:
                    return ""
            elif item_type == "theme":
                cmd = f"php -d memory_limit={self.wp_memory_limit} $(which wp) theme get {slug} --format=json --path={self.remote_path}"
                code, stdout, stderr = ssh.execute(cmd)
                
                if code != 0 or not stdout.strip():
                    # Si hay error, puede ser por falta de memoria
                    if "Fatal error: Allowed memory size" in stderr:
                        print(f"⚠️ Error de memoria al obtener información del tema: {slug}")
                        print(f"   Intentando con límite de memoria aumentado...")
                        
                        # Intentar con más memoria
                        cmd = f"php -d memory_limit=1024M $(which wp) theme get {slug} --format=json --path={self.remote_path}"
                        code, stdout, stderr = ssh.execute(cmd)
                        
                        if code != 0 or not stdout.strip():
                            return ""
                    else:
                        return ""
                    
                try:
                    data = json.loads(stdout)
                    return data.get("version", "")
                except:
                    return ""
        except Exception as e:
            if isinstance(e, Exception) and str(e):
                print(f"⚠️ Error al obtener versión remota: {str(e)}")
            return ""
            
        return ""
        
    def get_local_file_version(self, file_path: str) -> str:
        """
        Obtiene la versión del plugin o tema local
        
        Args:
            file_path: Ruta relativa al archivo
            
        Returns:
            str: Versión del plugin/tema o cadena vacía si no se puede determinar
        """
        try:
            _, _, version = get_item_version_from_path(
                file_path, 
                self.local_path,
                memory_limit=self.wp_memory_limit
            )
            return version
        except Exception as e:
            if isinstance(e, Exception) and str(e):
                print(f"⚠️ Error al obtener versión local: {str(e)}")
            return ""
    
    def add_patch(self, file_path: str, description: str = "") -> bool:
        """
        Registra un nuevo parche en el archivo lock
        
        Args:
            file_path: Ruta relativa al archivo
            description: Descripción del parche
            
        Returns:
            bool: True si se registró correctamente, False en caso contrario
        """
        print(f"🔄 Registrando parche: {file_path}")
        
        # Verificar que el archivo local existe
        local_file = self.local_path / file_path
        if not local_file.exists():
            print(f"❌ Error: El archivo local no existe: {local_file}")
            print("   Debes proporcionar una ruta relativa válida desde la raíz del proyecto.")
            return False
            
        # Calcular checksum del archivo local
        local_checksum = self.calculate_checksum(local_file)
        if not local_checksum:
            print(f"❌ Error: No se pudo calcular el checksum del archivo local")
            return False
            
        # Obtener configuración DDEV
        ddev_wp_path = get_nested(self.config, "ddev", "webroot")

        # Obtener información de versión del plugin/tema
        item_type, item_slug, local_version = get_item_version_from_path(
            file_path, 
            self.local_path,
            remote=False,
            use_ddev=True,
            wp_path=ddev_wp_path
        )
        
        # Crear o actualizar entrada en el archivo lock
        if "patches" not in self.lock_data:
            self.lock_data["patches"] = {}
            
        # Si ya existe una entrada para este archivo, actualízala
        if file_path in self.lock_data["patches"]:
            print(f"ℹ️ El parche para '{file_path}' ya existe. Actualizando...")
            
        # Si no se proporcionó una descripción, usar la existente o una genérica
        if not description:
            if file_path in self.lock_data["patches"] and self.lock_data["patches"][file_path].get("description"):
                description = self.lock_data["patches"][file_path]["description"]
            else:
                description = f"Parche para {os.path.basename(file_path)}"
                
        # Registrar el parche
        self.lock_data["patches"][file_path] = {
            "description": description,
            "local_checksum": local_checksum,
            "registered_date": datetime.datetime.now().isoformat(),
            "item_type": item_type,
            "item_slug": item_slug,
            "local_version": local_version
        }
        
        # Guardar archivo lock
        self.save_lock_file()
        
        print(f"✅ Parche registrado: {file_path}")
        if item_type != "other" and local_version:
            print(f"   Detectado {item_type}: {item_slug} (versión {local_version})")
        print(f"   Para aplicar el parche, ejecuta: patch {file_path}")
        
        return True
    
    def remove_patch(self, file_path: str) -> bool:
        """
        Elimina un parche del archivo lock
        
        Args:
            file_path: Ruta relativa al archivo
            
        Returns:
            bool: True si se eliminó correctamente, False en caso contrario
        """
        if "patches" not in self.lock_data or file_path not in self.lock_data["patches"]:
            print(f"❌ El parche '{file_path}' no está registrado.")
            return False
            
        # Comprobar si el parche ya fue aplicado
        if self.lock_data["patches"][file_path].get("applied_date"):
            print("⚠️ Este parche ya fue aplicado al servidor.")
            confirm = input("   ¿Deseas eliminarlo del registro de todos modos? (s/n): ")
            if confirm.lower() != "s":
                print("   ⏭️ Operación cancelada.")
                return False
                
        # Eliminar el parche
        del self.lock_data["patches"][file_path]
        
        # Guardar archivo lock
        self.save_lock_file()
        
        print(f"✅ Parche eliminado del registro: {file_path}")
        return True
        
    def apply_patch(self, file_path: str, dry_run: bool = False, show_details: bool = False, force: bool = False, ssh_client: Optional[SSHClient] = None) -> bool:
        """
        Aplica un parche a un archivo remoto
        
        Args:
            file_path: Ruta relativa al archivo
            dry_run: Si es True, solo muestra qué se haría
            show_details: Si es True, muestra más detalles
            force: Si es True, aplica el parche incluso si las versiones no coinciden
            ssh_client: Cliente SSH ya inicializado (opcional)
            
        Returns:
            bool: True si el parche se aplicó correctamente, False en caso contrario
        """
        # Verificar que el parche existe en el registro
        if "patches" not in self.lock_data or file_path not in self.lock_data["patches"]:
            print(f"❌ Error: El parche para '{file_path}' no está registrado")
            print("   Puedes registrarlo con el comando 'patch --add'")
            return False
        
        # Verificar seguridad y posiblemente forzar dry-run
        safety_check = self.check_safety(force_dry_run=True)
        if safety_check is None:  # Forzar dry-run por seguridad
            if not dry_run:
                print("⚠️ Forzando modo dry-run debido a configuración de seguridad")
            dry_run = True
        elif not safety_check:  # Abortar si no es seguro y no se fuerza dry-run
            return False
            
        # Obtener información del parche
        patch_info = self.lock_data["patches"][file_path]
        
        # Verificar archivo local
        local_file = self.local_path / file_path
        if not local_file.exists():
            print(f"❌ Error: El archivo local no existe: {local_file}")
            return False
            
        # Calcular checksum del archivo local
        local_checksum = self.calculate_checksum(local_file)
        if not local_checksum:
            print(f"❌ Error: No se pudo calcular el checksum del archivo local")
            return False
            
        # Verificar si el archivo local ha cambiado desde que se registró el parche
        registered_checksum = patch_info.get("local_checksum", "")
        if local_checksum != registered_checksum and not force:
            print(f"❌ Error: El archivo local ha cambiado desde que se registró el parche")
            print(f"   Checksum registrado: {registered_checksum}")
            print(f"   Checksum actual: {local_checksum}")
            print("   La aplicación del parche podría no ser correcta.")
            print("   Utiliza --force para aplicar el parche de todos modos.")
            return False
        
        # Verificar conexión SSH
        ssh = None
        ssh_provided = ssh_client is not None
        try:
            if ssh_client is not None:
                ssh = ssh_client
            else:
                # Verificar conexión al servidor
                if not self.check_remote_connection():
                    return False
                
                # Establecer conexión SSH
                ssh = SSHClient(self.remote_host)
                ssh.connect()
            
            # Verificar si la aplicación del parche es segura
            remote_file = f"{self.remote_path}/{file_path}"
            
            # Comprobar si el archivo existe en el servidor
            cmd = f"test -f \"{remote_file}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error al verificar el archivo remoto: {stderr}")
                return False
                
            remote_exists = "EXISTS" in stdout
            
            # Si está marcado como aplicado, verificar si realmente está aplicado
            if patch_info.get("applied_date"):
                if not remote_exists:
                    print(f"⚠️ El archivo está marcado como parcheado pero no existe en el servidor")
                    if not force:
                        print("   Utiliza --force para aplicar el parche de todos modos.")
                        return False
                else:
                    # Verificar si el checksum coincide con el guardado
                    remote_checksum = self.get_remote_file_checksum(ssh, remote_file)
                    patched_checksum = patch_info.get("patched_checksum", "")
                    
                    if remote_checksum == patched_checksum:
                        if not show_details:
                            print(f"✅ El parche ya está aplicado correctamente")
                            return True
                        else:
                            print(f"✅ El parche está aplicado correctamente con checksum {patched_checksum}")
                    else:
                        print(f"⚠️ El archivo remoto ha sido modificado desde que se aplicó el parche")
                        print(f"   Checksum guardado: {patched_checksum}")
                        print(f"   Checksum actual: {remote_checksum}")
                        
                        if not force:
                            print("   Utiliza --force para aplicar el parche de todos modos.")
                            return False
            
            # Si el archivo existe en el servidor, crear backup
            backup_file = ""
            if remote_exists and not dry_run:
                # Generar nombre de archivo de backup con timestamp
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{remote_file}.bak.{timestamp}"
                
                # Crear backup
                cmd = f"cp -f \"{remote_file}\" \"{backup_path}\""
                code, stdout, stderr = ssh.execute(cmd)
                
                if code != 0:
                    print(f"❌ Error al crear backup: {stderr}")
                    return False
                    
                backup_file = backup_path
                print(f"✅ Backup creado: {os.path.basename(backup_path)}")
                
                # Verificar que el backup se creó correctamente
                cmd = f"test -f \"{backup_path}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
                code, stdout, stderr = ssh.execute(cmd)
                
                if code != 0 or "EXISTS" not in stdout:
                    print(f"❌ Error: No se pudo verificar el backup")
                    return False
            
            # Mostrar diferencias si se solicita
            if show_details:
                print("\n📋 Diferencias entre archivos:")
                self._show_file_diff(local_file, remote_file, ssh)
                print("")
            
            # En modo dry-run, no hacer cambios
            if dry_run:
                print("ℹ️ Modo simulación: No se realizaron cambios")
                return True
            
            # Transferir el archivo
            remote_dir = os.path.dirname(remote_file)
            
            # Asegurarse de que el directorio remoto existe
            cmd = f"mkdir -p \"{remote_dir}\""
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error al crear directorio remoto: {stderr}")
                return False
            
            # Usar SCP para transferir el archivo
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = tmp.name
                
            try:
                # Copiar archivo local al temporal
                shutil.copy2(local_file, tmp_path)
                
                # Transferir el archivo al servidor
                if not ssh.upload_file(tmp_path, remote_file):
                    print(f"❌ Error al transferir el archivo al servidor")
                    return False
                    
                # Verificar permisos del archivo original para mantenerlos
                if remote_exists:
                    cmd = f"stat -c '%a' \"{backup_path}\""
                    code, stdout, stderr = ssh.execute(cmd)
                    
                    if code == 0 and stdout.strip():
                        permissions = stdout.strip()
                        # Aplicar los mismos permisos
                        cmd = f"chmod {permissions} \"{remote_file}\""
                        ssh.execute(cmd)
                
                # Actualizar información del parche en el lock
                patch_info.update({
                    "applied_date": datetime.datetime.now().isoformat(),
                    "backup_file": backup_file,
                    "patched_checksum": local_checksum
                })
                
                # Si es un plugin o tema, obtener la versión remota
                if patch_info.get("item_type") in ["plugin", "theme"] and patch_info.get("item_slug"):
                    try:
                        _, _, remote_version = get_item_version_from_path(
                            file_path, 
                            self.remote_path,
                            remote=True,
                            remote_host=self.remote_host,
                            remote_path=self.remote_path,
                            memory_limit=self.wp_memory_limit,
                            use_ddev=False
                        )
                        
                        if remote_version:
                            patch_info["remote_version"] = remote_version
                    except Exception as e:
                        print(f"⚠️ No se pudo obtener la versión remota: {str(e)}")
                
                # Guardar cambios
                self.save_lock_file()
                
                print(f"✅ Parche aplicado correctamente: {file_path}")
                return True
                
            finally:
                # Eliminar archivo temporal
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            print(f"❌ Error al aplicar el parche: {str(e)}")
            return False
            
        finally:
            # Cerrar la conexión SSH si se creó en este método
            if ssh and ssh.client and not ssh_provided:
                ssh.disconnect()
    
    def _show_file_diff(self, local_file: Path, remote_file: str, ssh: Optional[SSHClient] = None) -> None:
        """
        Muestra las diferencias entre el archivo local y el remoto
        
        Args:
            local_file: Ruta al archivo local
            remote_file: Ruta al archivo remoto
            ssh: Conexión SSH activa (opcional)
        """
        print("   🔍 Verificando diferencias con el servidor...")
        
        # Crear un SSH client si no se proporcionó uno
        close_ssh = False
        if ssh is None:
            ssh = SSHClient(self.remote_host)
            ssh.connect()
            
        if not ssh.client:
            print("   ❌ No se pudo establecer conexión SSH para mostrar diferencias")
            return
            
        # Verificar si el archivo remoto existe
        cmd_check = f"test -f \"{remote_file}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
        _, stdout, _ = ssh.execute(cmd_check)
        
        # Crear directorio temporal
        temp_dir = tempfile.mkdtemp()
        remote_temp = Path(temp_dir) / os.path.basename(remote_file)
        
        try:
            # Descargar archivo remoto si existe
            if "EXISTS" in stdout:
                if not ssh.download_file(remote_file, remote_temp):
                    print("   ⚠️ No se pudo descargar el archivo remoto para comparar.")
                    return
                    
                # Comparar archivos
                with open(local_file, 'r') as local_f, open(remote_temp, 'r') as remote_f:
                    local_content = local_f.readlines()
                    remote_content = remote_f.readlines()
                    
                diff = list(difflib.unified_diff(
                    remote_content, local_content, 
                    fromfile='servidor', tofile='local',
                    lineterm=''
                ))
                
                if not diff:
                    print("   ℹ️ No hay diferencias entre versión local y remota.")
                else:
                    # Mostrar las diferencias (limitadas)
                    print("   📊 Diferencias encontradas:")
                    for line in diff[:30]:
                        print(f"   {line}")
                    if len(diff) > 30:
                        print("   ... (más diferencias)")
            else:
                print("   ℹ️ El archivo no existe en el servidor o no se puede leer.")
        finally:
            # Limpiar directorio temporal
            shutil.rmtree(temp_dir)
            
            # Ya no intentamos cerrar SSH aquí, ya que la conexión se maneja
            # automáticamente con el context manager (with) en los métodos que llaman
            # a esta función, o dentro de SSHClient mismo
    
    def rollback_patch(self, file_path: str, dry_run: bool = False) -> bool:
        """
        Revierte un parche aplicado anteriormente
        
        Args:
            file_path: Ruta relativa al archivo
            dry_run: Si es True, solo muestra qué se haría
            
        Returns:
            bool: True si el rollback fue exitoso, False en caso contrario
        """
        print(f"🔄 Intentando revertir parche: {file_path}")
        
        # Verificar si el parche existe en el archivo lock
        if "patches" not in self.lock_data or file_path not in self.lock_data["patches"]:
            print(f"❌ El parche '{file_path}' no se encuentra en el registro.")
            print("   Use --list para ver los parches disponibles.")
            return False
            
        # Obtener información del parche
        patch_info = self.lock_data["patches"][file_path]
        backup_file = patch_info.get("backup_file", "")
        
        if not backup_file:
            print("❌ No se encontró copia de seguridad para este parche.")
            print("   No se puede realizar el rollback automático.")
            return False
            
        # Verificar seguridad y posiblemente forzar dry-run
        safety_check = self.check_safety(force_dry_run=True)
        if safety_check is None:  # Forzar dry-run por seguridad
            dry_run = True
        elif not safety_check:  # Abortar si no es seguro y no se fuerza dry-run
            return False
            
        # Verificar conexión
        if not self.check_remote_connection():
            return False
            
        remote_file = f"{self.remote_path}/{file_path}"
        
        # Si es modo simulación, solo mostrar qué se haría
        if dry_run:
            print("   🔄 Modo simulación: No se realizarán cambios reales")
            print(f"   - Se restauraría {backup_file} a {remote_file}")
            print(f"   - Se actualizaría el archivo lock: {self.lock_file}")
            return True
            
        # Restaurar backup
        with SSHClient(self.remote_host) as ssh:
            # Verificar si el backup existe
            cmd_check = f"test -f \"{backup_file}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
            _, stdout, _ = ssh.execute(cmd_check)
            
            if "NOT_EXISTS" in stdout:
                print(f"❌ El archivo de backup no existe en el servidor: {backup_file}")
                return False
                
            # Mostrar diferencias entre el backup y el archivo actual
            print("   🔍 Mostrando diferencias entre archivo actual y backup...")
            
            # Crear directorio temporal
            temp_dir = tempfile.mkdtemp()
            backup_temp = Path(temp_dir) / f"backup_{os.path.basename(file_path)}"
            current_temp = Path(temp_dir) / f"current_{os.path.basename(file_path)}"
            
            try:
                # Descargar archivos para comparar
                ssh.download_file(backup_file, backup_temp)
                ssh.download_file(remote_file, current_temp)
                
                # Comparar archivos
                with open(backup_temp, 'r') as backup_f, open(current_temp, 'r') as current_f:
                    backup_content = backup_f.readlines()
                    current_content = current_f.readlines()
                    
                diff = list(difflib.unified_diff(
                    current_content, backup_content, 
                    fromfile='actual', tofile='backup',
                    lineterm=''
                ))
                
                if not diff:
                    print("   ℹ️ No hay diferencias entre el archivo actual y el backup.")
                else:
                    # Mostrar las diferencias (limitadas)
                    print("   📊 Diferencias encontradas:")
                    for line in diff[:30]:
                        print(f"   {line}")
                    if len(diff) > 30:
                        print("   ... (más diferencias)")
            finally:
                # Limpiar directorio temporal
                shutil.rmtree(temp_dir)
                
            # Preguntar si se desea restaurar
            restore = input("   ¿Desea restaurar a la versión anterior? (s/n): ")
            if restore.lower() != "s":
                print("   ⏭️ Operación cancelada.")
                return False
                
            # Restaurar el backup
            cmd_restore = f"cp \"{backup_file}\" \"{remote_file}\""
            code, stdout, stderr = ssh.execute(cmd_restore)
            
            if code != 0:
                print(f"❌ Error al restaurar el backup: {stderr}")
                return False
                
            print(f"✅ Archivo restaurado desde backup: {backup_file}")
            
            # Actualizar el archivo lock
            # Eliminamos flags de aplicación pero mantenemos el registro
            self.lock_data["patches"][file_path].update({
                "patched_checksum": "",
                "backup_file": "",
                "rollback_date": datetime.datetime.now().isoformat(),
                "applied_date": "",
                "remote_version": ""
            })
            
            self.save_lock_file()
            print(f"✅ Registro actualizado: parche marcado como revertido.")
                
            return True
            
    def apply_all_patches(self, dry_run: bool = False, force: bool = False) -> bool:
        """
        Aplica todos los parches registrados
        
        Args:
            dry_run: Si es True, solo muestra qué se haría
            force: Si es True, aplica parches incluso si las versiones no coinciden
            
        Returns:
            bool: True si todos los parches se aplicaron correctamente, False en caso contrario
        """
        if not self.lock_data.get("patches", {}):
            print("ℹ️ No hay parches registrados para aplicar.")
            print("   Puedes registrar parches con 'patch --add ruta/al/archivo'")
            return False
            
        print("🔧 Iniciando aplicación de parches de local a servidor...")
        print(f"   Origen: {self.local_path}")
        print(f"   Destino: {self.remote_host}:{self.remote_path}")
        print("")
        
        # Verificar seguridad y posiblemente forzar dry-run
        safety_check = self.check_safety(force_dry_run=True)
        if safety_check is None:  # Forzar dry-run por seguridad
            dry_run = True
        elif not safety_check:  # Abortar si no es seguro y no se fuerza dry-run
            return False
        
        # Verificar conexión
        if not self.check_remote_connection():
            return False

        # Configuramos una única conexión SSH para todas las operaciones
        php_memory_error_shown = False
        
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                print("❌ Error al establecer conexión SSH")
                return False
                
            success_count = 0
            total_count = len(self.lock_data["patches"])
            
            print(f"Aplicando {total_count} parches:")
            
            for i, file_path in enumerate(self.lock_data["patches"]):
                # Obtener información básica del parche actual
                patch_info = self.lock_data["patches"][file_path]
                description = patch_info.get("description", "Sin descripción")
                
                print(f"\n[{i+1}/{total_count}] {file_path} - {description}")
                
                try:
                    # Verificar estado del parche
                    status_code, status_details = self.get_patch_status(file_path, ssh)
                    
                    # Verificar si hay errores de memoria PHP
                    error_msg = status_details.get("error", "")
                    if "memory size" in error_msg.lower() and not php_memory_error_shown:
                        print("⚠️ Advertencia: Errores de memoria PHP detectados. Aumentando límite si es posible.")
                        php_memory_error_shown = True
                    
                    # Verificar si podemos aplicar el parche
                    if status_code == PATCH_STATUS_ORPHANED and not force:
                        print(f"⚠️ El parche está huérfano (ORPHANED): El archivo local ha cambiado")
                        print("   Omitiendo (use --force para aplicar de todos modos)")
                        continue
                    
                    if status_code == PATCH_STATUS_OBSOLETED and not force:
                        print(f"⚠️ El parche está obsoleto (OBSOLETED): Archivo local modificado después de aplicar")
                        print("   Omitiendo (use --force para aplicar de todos modos)")
                        continue
                        
                    if status_code == PATCH_STATUS_APPLIED:
                        print(f"✅ El parche ya está aplicado correctamente.")
                        success_count += 1
                        continue
                        
                    # Aplicar el parche
                    success = self.apply_patch(file_path, dry_run, False, force, ssh)
                    if success:
                        success_count += 1
                
                except Exception as e:
                    print(f"❌ Error al procesar el parche: {str(e)}")
                    
        print("")
        print(f"🎉 Proceso de aplicación de parches completado.")
        print(f"   ✅ {success_count}/{total_count} parches aplicados correctamente.")
        
        return success_count == total_count
        
    def get_patch_status(self, file_path: str, ssh: Optional[SSHClient] = None) -> Tuple[str, Dict]:
        """
        Verifica el estado detallado de un parche
        
        Args:
            file_path: Ruta relativa al archivo
            ssh: Conexión SSH activa (opcional)
            
        Returns:
            Tuple[str, Dict]: Estado del parche y detalles adicionales
        """
        # Verificar si el parche existe en el registro
        if "patches" not in self.lock_data or file_path not in self.lock_data["patches"]:
            return None, {}
            
        patch_info = self.lock_data["patches"][file_path]
        details = {
            "description": patch_info.get("description", ""),
            "local_path": str(self.local_path / file_path),
            "remote_path": f"{self.remote_path}/{file_path}",
            "registered_date": patch_info.get("registered_date", ""),
            "applied_date": patch_info.get("applied_date", ""),
            "item_type": patch_info.get("item_type", "other"),
            "item_slug": patch_info.get("item_slug", ""),
            "local_version": patch_info.get("local_version", ""),
            "remote_version": patch_info.get("remote_version", ""),
            "original_checksum": patch_info.get("original_checksum", ""),
            "patched_checksum": patch_info.get("patched_checksum", ""),
            "backup_file": patch_info.get("backup_file", ""),
            "messages": [],
            "error": ""
        }
        
        # Verificar archivo local
        local_file = self.local_path / file_path
        local_exists = local_file.exists()
        details["local_exists"] = local_exists
        
        if local_exists:
            current_local_checksum = self.calculate_checksum(local_file)
            registered_local_checksum = patch_info.get("local_checksum", "")
            details["current_local_checksum"] = current_local_checksum
            details["registered_local_checksum"] = registered_local_checksum
            
            # Verificar si el archivo local ha cambiado desde que se registró
            if current_local_checksum != registered_local_checksum:
                details["messages"].append(f"El archivo local ha cambiado desde que se registró el parche")
        else:
            details["messages"].append(f"El archivo local no existe: {local_file}")
            
        # Verificar archivo remoto si es posible
        if ssh is None or not ssh.client:
            # No hay conexión SSH disponible
            # Si el parche está marcado como aplicado
            if patch_info.get("applied_date"):
                # Si coincide el checksum local con el registrado
                if local_exists and current_local_checksum == registered_local_checksum:
                    return PATCH_STATUS_APPLIED, details
                else:
                    # El archivo local ha cambiado, parche obsoleto
                    return PATCH_STATUS_OBSOLETED, details
            else:
                # Si coincide el checksum local con el registrado
                if local_exists and current_local_checksum == registered_local_checksum:
                    return PATCH_STATUS_PENDING, details
                else:
                    # El archivo local ha cambiado, parche huérfano
                    return PATCH_STATUS_ORPHANED, details
        
        # Si hay conexión SSH, verificar archivo remoto
        remote_file = f"{self.remote_path}/{file_path}"
        cmd_check = f"test -f \"{remote_file}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
        _, stdout, _ = ssh.execute(cmd_check)
        remote_exists = "EXISTS" in stdout
        details["remote_exists"] = remote_exists
        
        # Si el archivo remoto existe, verificar checksum
        if remote_exists:
            remote_checksum = self.get_remote_file_checksum(ssh, remote_file)
            details["current_remote_checksum"] = remote_checksum
            
            # Verificar si hay archivos de backup en el servidor
            backup_pattern = f"{remote_file}.bak.*"
            cmd_find_backups = f"find $(dirname \"{remote_file}\") -name \"$(basename \"{backup_pattern}\")\" -type f | sort"
            _, stdout, _ = ssh.execute(cmd_find_backups)
            remote_backups = [line.strip() for line in stdout.split('\n') if line.strip()]
            details["remote_backups"] = remote_backups
            
            # Verificar versión remota si es plugin o tema
            if patch_info.get("item_type") in ["plugin", "theme"] and patch_info.get("item_slug"):
                try:
                    _, _, remote_version = get_item_version_from_path(
                        file_path, 
                        self.remote_path,
                        remote=True,
                        remote_host=self.remote_host,
                        remote_path=self.remote_path,
                        memory_limit=self.wp_memory_limit,
                        use_ddev=False
                    )
                    details["current_remote_version"] = remote_version
                    
                    # Comparar versiones
                    if remote_version and patch_info.get("remote_version") and remote_version != patch_info.get("remote_version"):
                        details["messages"].append(f"La versión remota ha cambiado: {patch_info.get('remote_version')} → {remote_version}")
                except Exception as e:
                    error_msg = str(e)
                    details["error"] = error_msg
                    if "memory size" in error_msg.lower():
                        details["messages"].append("No se pudo obtener la versión remota (error de memoria PHP)")
                    else:
                        details["messages"].append(f"Error al obtener la versión remota: {error_msg}")
            
            # Determinar estado del parche
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
            details["messages"].append(f"El archivo remoto no existe: {remote_file}")
            
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

    def show_config_info(self, verbose: bool = False) -> None:
        """
        Muestra información de configuración del gestor de parches
        
        Args:
            verbose: Si es True, muestra información adicional
        """
        print("\n🛠️ Configuración del gestor de parches:")
        
        # Información sobre el sitio
        if self.current_site:
            print(f"   • Sitio actual: {self.current_site}")
        else:
            print(f"   • Usando configuración general (sin sitio específico)")
            
        # Información sobre el archivo lock
        print(f"   • Archivo de parches: {self.lock_file.name}")
        if self.lock_file.exists():
            print(f"     - Estado: Existe ({len(self.lock_data.get('patches', {}))} parches registrados)")
            last_updated = self.lock_data.get("last_updated", "Desconocida")
            print(f"     - Última actualización: {last_updated}")
        else:
            # Verificar si existe el archivo genérico
            generic_lock_file = Path(__file__).resolve().parent.parent / "patches.lock.json"
            if generic_lock_file.exists():
                print(f"     - Estado: No existe (se usará el genérico: patches.lock.json)")
            else:
                print(f"     - Estado: No existe (se creará cuando sea necesario)")
                
        # Rutas relevantes
        if verbose:
            print(f"\n📂 Rutas:")
            print(f"   • Ruta del archivo lock: {self.lock_file}")
            print(f"   • Ruta local del sitio: {self.local_path}")
            print(f"   • Servidor remoto: {self.remote_host}:{self.remote_path}")
            
        print("")

def list_patches(verbose: bool = False):
    """
    Muestra la lista de parches disponibles con información detallada
    
    Args:
        verbose: Si es True, muestra información adicional
    """
    manager = PatchManager()
    
    # En modo verbose, mostrar información de configuración
    if verbose:
        manager.show_config_info(verbose=True)
    
    manager.list_patches(verbose=verbose)
    
def add_patch(file_path: str, description: str = "") -> bool:
    """
    Registra un nuevo parche en el archivo lock
    
    Args:
        file_path: Ruta relativa al archivo a parchar
        description: Descripción del parche
        
    Returns:
        bool: True si se registró correctamente, False en caso contrario
    """
    manager = PatchManager()
    return manager.add_patch(file_path, description)
    
def remove_patch(file_path: str) -> bool:
    """
    Elimina un parche del archivo lock
    
    Args:
        file_path: Ruta relativa al archivo a eliminar
        
    Returns:
        bool: True si se eliminó correctamente, False en caso contrario
    """
    manager = PatchManager()
    return manager.remove_patch(file_path)
    
def apply_patch(file_path: str = None, dry_run: bool = False, show_details: bool = False, force: bool = False) -> bool:
    """
    Aplica uno o todos los parches
    
    Args:
        file_path: Ruta relativa al archivo a parchar, o None para todos
        dry_run: Si es True, solo muestra qué se haría
        show_details: Si es True, muestra detalles adicionales del parche
        force: Si es True, aplica parches incluso si las versiones no coinciden o el archivo ha cambiado
        
    Returns:
        bool: True si el parche se aplicó correctamente, False en caso contrario
    """
    manager = PatchManager()
    
    if file_path:
        # Obtener el estado actual del parche
        ssh = None
        try:
            if manager.check_remote_connection():
                ssh = SSHClient(manager.remote_host)
                ssh.connect()
                
                status_code, status_details = manager.get_patch_status(file_path, ssh)
                
                # Si el parche está huérfano y no se fuerza, mostrar error
                if status_code == PATCH_STATUS_ORPHANED and not force:
                    print(f"❌ Error: El parche para '{file_path}' está huérfano (ORPHANED)")
                    print("   El archivo local ha cambiado y no coincide con el registrado.")
                    print("   Usa --force para aplicar el parche de todos modos.")
                    return False
                
                # Si el parche está obsoleto y no se fuerza, mostrar error
                if status_code == PATCH_STATUS_OBSOLETED and not force:
                    print(f"❌ Error: El parche para '{file_path}' está obsoleto (OBSOLETED)")
                    print("   El archivo local ha cambiado después de haber aplicado el parche.")
                    print("   Usa --force para aplicar el parche de todos modos.")
                    return False
        except Exception as e:
            print(f"⚠️ Error al verificar estado del parche: {str(e)}")
        finally:
            # Cerrar la conexión SSH
            if ssh and ssh.client:
                ssh.disconnect()
                
        # Aplicar un solo parche
        return manager.apply_patch(file_path, dry_run, show_details, force)
    else:
        # Aplicar todos los parches
        return manager.apply_all_patches(dry_run, force)
        
def rollback_patch(file_path: str, dry_run: bool = False) -> bool:
    """
    Revierte un parche aplicado anteriormente
    
    Args:
        file_path: Ruta relativa al archivo a revertir
        dry_run: Si es True, solo muestra qué se haría
        
    Returns:
        bool: True si el rollback fue exitoso, False en caso contrario
    """
    manager = PatchManager()
    return manager.rollback_patch(file_path, dry_run)

def get_patched_files() -> List[str]:
    """
    Devuelve la lista de archivos que tienen parches aplicados
    
    Returns:
        List[str]: Lista de rutas de archivos parcheados
    """
    manager = PatchManager()
    patched_files = []
    
    # Si no hay parches registrados, devolver lista vacía
    if not manager.lock_data.get("patches"):
        return patched_files
        
    # Recopilar la lista de archivos parcheados
    for file_path, info in manager.lock_data.get("patches", {}).items():
        # Solo incluir archivos que tengan parche aplicado
        if info.get("applied_date"):
            patched_files.append(file_path)
            
    return patched_files 