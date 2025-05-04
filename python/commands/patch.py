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

# Importar funciones y constantes desde patch_utils
from .patch_utils import (
    calculate_checksum, 
    get_remote_file_checksum,
    get_remote_file_version,
    get_local_file_version,
    show_file_diff,
    determine_patch_status,
    get_site_specific_lock_file,
    load_lock_file,
    save_lock_file,
    PATCH_STATUS_PENDING,
    PATCH_STATUS_APPLIED,
    PATCH_STATUS_ORPHANED,
    PATCH_STATUS_OBSOLETED,
    PATCH_STATUS_MISMATCHED,
    PATCH_STATUS_STALE,
    PATCH_STATUS_LABELS
)

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
        
        # Cargar configuración siguiendo principio "fail fast"
        try:
            # Obtener valores de SSH requeridos
            if "ssh" not in self.config.config:
                raise ValueError("Falta sección 'ssh' en la configuración")
            
            self.remote_host = self.config.get_strict("ssh", "remote_host")
            self.remote_path = self.config.get_strict("ssh", "remote_path")
            self.local_path = Path(self.config.get_strict("ssh", "local_path"))
            
            # Asegurarse de que las rutas remotas terminen con un solo /
            self.remote_path = self.remote_path.rstrip('/') + '/'
            
            # Cargar configuración de seguridad
            self.production_safety = get_nested(self.config, "security", "production_safety") == "enabled"
            
            # Determinar el sitio actual para el archivo lock específico por sitio
            self.current_site = self.config.current_site
            
            # Generar el nombre del archivo lock usando la función de utility
            self.lock_file = get_site_specific_lock_file(self.current_site)
            
            # Cargar archivo lock
            self.lock_data = load_lock_file(self.lock_file)
            
            # Cargar archivos protegidos
            self.protected_files = self.config.get_protected_files()
            
            # Cargar límite de memoria para WP-CLI - sin valores por defecto (fail fast)
            self.wp_memory_limit = self.config.get_wp_memory_limit()
            
            # Inicializar lista de parches
            self.patches = []
            
        except ValueError as e:
            print(f"❌ Error de configuración: {str(e)}")
            print("   El sistema no puede continuar sin la configuración requerida.")
            raise
        
    def save_lock_file(self):
        """
        Guarda los datos del archivo lock
        """
        save_lock_file(self.lock_file, self.lock_data, self.current_site)
    
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
                print(f"❌ No se pudo acceder al servidor remoto: {self.remote_host}")
                if stderr:
                    print(f"   Error: {stderr}")
                return False
                
            if "NOT_FOUND" in stdout:
                print(f"❌ La ruta remota no existe: {self.remote_path}")
                return False
                
            print(f"✅ Conexión exitosa con el servidor remoto")
            return True
    
    def calculate_checksum(self, file_path: Path) -> str:
        """
        Calcula el checksum MD5 de un archivo
        
        Args:
            file_path: Ruta al archivo
            
        Returns:
            str: Checksum MD5 del archivo
        """
        return calculate_checksum(file_path)
        
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
                original_checksum = info.get("original_checksum", "")
                local_version = info.get("local_version", "Desconocida")
                remote_version = info.get("remote_version", "Desconocida")
                
                # Determinar estado del parche si estamos conectados
                status = "Desconocido"
                status_code = PATCH_STATUS_PENDING  # Por defecto
                
                if connected and ssh:
                    try:
                        status_code, status_details = self.get_patch_status(file_path, ssh)
                        status = PATCH_STATUS_LABELS.get(status_code, "Estado desconocido")
                    except Exception as e:
                        # Capturar errores específicos de memoria PHP
                        if "Fatal error: Allowed memory size" in str(e):
                            if not php_memory_error_shown:
                                print(f"⚠️ Error de memoria PHP al obtener algunos estados. Use WP_CLI_PHP_ARGS para aumentar el límite de memoria.")
                                php_memory_error_shown = True
                            status = "⚠️ Error de memoria"
                        else:
                            status = f"⚠️ Error: {str(e)}"
                elif connected:
                    status = "⚠️ No conectado"
                else:
                    # Si no estamos conectados, usamos la información local
                    if applied_date:
                        status = "✅ Aplicado (sin verificar)"
                    else:
                        status = "⏳ Pendiente (sin verificar)"
                
                # Formatear fecha si existe
                formatted_date = ""
                if applied_date:
                    try:
                        # Intentar parsear la fecha
                        applied_datetime = datetime.datetime.fromisoformat(applied_date)
                        formatted_date = applied_datetime.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        formatted_date = applied_date
                
                # Mostrar información del parche
                print(f"\n📄 {item_type}: {plugin_name}")
                print(f"   • Archivo: {file_path}")
                print(f"   • Descripción: {description}")
                print(f"   • Estado: {status}")
                
                # Verificar si hay diferencias entre checksums que indiquen cambios
                if original_checksum and local_checksum and original_checksum != local_checksum:
                    print(f"   • Cambios: ✅ Detectados (checksums diferentes)")
                elif original_checksum and local_checksum and original_checksum == local_checksum:
                    print(f"   • Cambios: ❌ No detectados (checksums idénticos)")
                
                if verbose:
                    print(f"   • Versión local: {local_version}")
                    if connected:
                        print(f"   • Versión remota: {remote_version}")
                    
                    if original_checksum:
                        print(f"   • MD5 original: {original_checksum}")
                    print(f"   • MD5 local: {local_checksum}")
                    patched_checksum = info.get("patched_checksum", "")
                    if patched_checksum:
                        print(f"   • MD5 parcheado: {patched_checksum}")
                    
                    # Mostrar backups
                    if info.get("local_backup_file", ""):
                        print(f"   • Backup local: {info.get('local_backup_file')}")
                    if info.get("backup_file", ""):
                        print(f"   • Backup remoto: {info.get('backup_file')}")
                    
                    if applied_date:
                        print(f"   • Aplicado: {formatted_date}")
                        
                        # Mostrar usuario que aplicó el parche si está disponible
                        applied_by = info.get("applied_by", "")
                        if applied_by:
                            print(f"   • Aplicado por: {applied_by}")
                
        except Exception as e:
            print(f"⚠️ Error al listar parches: {str(e)}")
        finally:
            # Cerrar la conexión SSH
            if ssh and ssh.client:
                ssh.disconnect()

    def check_safety(self, force_dry_run: bool = False) -> Optional[bool]:
        """
        Verifica las medidas de seguridad para proteger entornos de producción
        
        Args:
            force_dry_run: Si es True, siempre ejecuta en modo simulación
            
        Returns:
            Optional[bool]: True si es seguro proceder, False si se debe abortar, None si forzar dry-run
        """
        if force_dry_run:
            print("\n⚠️ ATENCIÓN: Seguridad forzada. Ejecutando en modo simulación.")
            return None
            
        if self.production_safety:
            print("\n⚠️ ATENCIÓN: Protección de producción activada en la configuración.")
            print("   Esta operación podría afectar un entorno de producción.")
            print("   Para continuar, desactive la protección en config.yaml o confirme para continuar.")
            
            user_input = input("\n¿Está seguro de querer continuar? (s/N): ")
            
            if user_input.lower() not in ["s", "si", "sí", "y", "yes"]:
                print("Operación cancelada por el usuario.")
                return False
                
            print("Protección desactivada temporalmente a petición del usuario.\n")
            
        return True
        
    def get_remote_file_checksum(self, ssh: SSHClient, remote_file: str) -> str:
        """
        Obtiene el checksum de un archivo en el servidor remoto
        
        Args:
            ssh: Cliente SSH conectado
            remote_file: Ruta al archivo en el servidor remoto
            
        Returns:
            str: Checksum MD5 del archivo remoto
        """
        return get_remote_file_checksum(ssh, remote_file)
        
    def get_remote_file_version(self, ssh: SSHClient, file_path: str) -> str:
        """
        Obtiene la versión de un plugin o tema desde un archivo en el servidor remoto
        
        Args:
            ssh: Cliente SSH conectado
            file_path: Ruta al archivo
            
        Returns:
            str: Versión del plugin o tema, o cadena vacía si no se puede determinar
        """
        return get_remote_file_version(ssh, file_path, self.remote_path, self.wp_memory_limit)
        
    def get_local_file_version(self, file_path: str) -> str:
        """
        Obtiene la versión de un plugin o tema desde un archivo local
        
        Args:
            file_path: Ruta relativa al archivo
            
        Returns:
            str: Versión del plugin o tema, o cadena vacía si no se puede determinar
        """
        return get_local_file_version(file_path, self.local_path)
    
    def add_patch(self, file_path: str, description: str = "") -> bool:
        """
        Registra un nuevo parche en el archivo lock
        
        Flujo correcto:
        1. Verifica que el archivo local existe y está modificado
        2. Descarga la versión original desde el servidor remoto
        3. Guarda esa versión como backup local
        4. Calcula checksums de ambas versiones
        5. Registra el parche con toda la información necesaria
        
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
            
        # Calcular checksum del archivo local (ya modificado)
        local_checksum = self.calculate_checksum(local_file)
        if not local_checksum:
            print(f"❌ Error: No se pudo calcular el checksum del archivo local")
            return False
            
        # Verificar conexión con el servidor remoto para descargar el archivo original
        if not self.check_remote_connection():
            print("❌ Error: No se pudo conectar con el servidor remoto para obtener el archivo original")
            return False
            
        # Obtener el archivo original desde el servidor remoto
        remote_file = f"{self.remote_path}{file_path}"
        original_checksum = ""
        backup_path = local_file.with_suffix(f"{local_file.suffix}.original.bak")
        local_backup_file = str(backup_path.relative_to(self.local_path))
        backup_checksum = ""
        remote_file_exists = False
            
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                print("❌ Error: No se pudo establecer conexión SSH")
                return False
                
            # Verificar si el archivo existe en el servidor
            cmd = f"test -f '{remote_file}' && echo 'EXISTS' || echo 'NOT_EXISTS'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if "EXISTS" in stdout:
                remote_file_exists = True
                
                # Obtener checksum del archivo remoto
                original_checksum = self.get_remote_file_checksum(ssh, remote_file)
                
                # Comparar checksums para verificar si hay cambios
                if original_checksum == local_checksum:
                    print("⚠️ Advertencia: El archivo local y el remoto tienen el mismo checksum")
                    print("   No parece haber modificaciones para parchar.")
                    confirm = input("   ¿Deseas continuar de todos modos? (s/n): ")
                    if confirm.lower() != "s":
                        print("   Operación cancelada.")
                        return False
                
                # Descargar el archivo original como backup
                print(f"📥 Descargando archivo original desde el servidor...")
                if not ssh.download_file(remote_file, backup_path):
                    print(f"❌ Error: No se pudo descargar el archivo original desde el servidor")
                    return False
                    
                # Verificar que el backup se creó correctamente
                if not backup_path.exists():
                    print(f"❌ Error: No se pudo crear el backup del archivo original")
                    return False
                    
                # Calcular checksum del backup
                backup_checksum = self.calculate_checksum(backup_path)
                if not backup_checksum:
                    print(f"❌ Error: No se pudo calcular el checksum del backup")
                    return False
                    
                # Verificar que el checksum del backup coincide con el remoto
                if backup_checksum != original_checksum:
                    print(f"⚠️ Advertencia: El checksum del backup no coincide con el remoto")
                    print(f"   Checksum remoto: {original_checksum}")
                    print(f"   Checksum backup: {backup_checksum}")
                    confirm = input("   ¿Deseas continuar de todos modos? (s/n): ")
                    if confirm.lower() != "s":
                        print("   Operación cancelada.")
                        return False
                
                print(f"✅ Archivo original guardado como: {backup_path.name}")
            else:
                print(f"ℹ️ El archivo no existe en el servidor. Se considerará un archivo nuevo.")
                original_checksum = ""
        
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
        
        # Obtener versión remota del plugin/tema si existe
        remote_version = ""
        if remote_file_exists:
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
            except Exception as e:
                print(f"⚠️ No se pudo obtener la versión remota: {str(e)}")
        
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
            "original_checksum": original_checksum,
            "registered_date": datetime.datetime.now().isoformat(),
            "item_type": item_type,
            "item_slug": item_slug,
            "local_version": local_version,
            "remote_version": remote_version,
            "local_backup_file": local_backup_file,
            "local_backup_checksum": backup_checksum
        }
        
        # Guardar archivo lock
        self.save_lock_file()
        
        print(f"✅ Parche registrado: {file_path}")
        if item_type != "other" and local_version:
            print(f"   Detectado {item_type}: {item_slug} (versión local {local_version})")
            if remote_version:
                print(f"   Versión remota: {remote_version}")
        
        if original_checksum and original_checksum != local_checksum:
            print(f"   Se han detectado modificaciones en el archivo")
        
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
        
        # Verificar seguridad solo si production_safety está habilitado
        if self.production_safety and not dry_run:
            safety_check = self.check_safety(force_dry_run=False)
            if safety_check is None:  # Forzar dry-run por seguridad
                print("⚠️ Forzando modo dry-run debido a configuración de seguridad")
                dry_run = True
            elif not safety_check:  # Abortar si no es seguro y no se fuerza dry-run
                return False
        
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
        patch_info = self.lock_data["patches"][file_path]
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
            remote_file = f"{self.remote_path.rstrip('/')}/{file_path}"
            
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
                backup_path = f"{self.remote_path.rstrip('/')}/{file_path}.bak.{timestamp}"
                
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
                    "patched_checksum": local_checksum  # Checksum del archivo modificado que se subió
                })
                
                # Si es un plugin o tema, obtener la versión remota actualizada
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
        Muestra las diferencias entre un archivo local y uno remoto
        
        Args:
            local_file: Ruta al archivo local
            remote_file: Ruta al archivo remoto
            ssh: Cliente SSH conectado (opcional, se crea uno nuevo si no se proporciona)
        """
        show_file_diff(local_file, remote_file, ssh)
    
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
            
        remote_file = f"{self.remote_path.rstrip('/')}/{file_path}"
        
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
        
        # Verificar seguridad solo si production_safety está habilitado
        if self.production_safety and not dry_run:
            safety_check = self.check_safety(force_dry_run=False)
            if safety_check is None:  # Forzar dry-run por seguridad
                print("⚠️ Forzando modo dry-run debido a configuración de seguridad")
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
        Determina el estado de un parche
        
        Args:
            file_path: Ruta relativa al archivo
            ssh: Cliente SSH conectado (opcional)
            
        Returns:
            Tuple[str, Dict]: Código de estado del parche y detalles
        """
        patch_info = self.lock_data.get("patches", {}).get(file_path, {})
        
        if not patch_info:
            return PATCH_STATUS_PENDING, {"error": "Parche no encontrado", "messages": ["Parche no registrado"]}
            
        # Inicializar valores
        details = {
            "remote_exists": False,
            "local_exists": False,
            "remote_checksum": "",
            "current_local_checksum": "",
            "registered_local_checksum": patch_info.get("local_checksum", ""),
            "current_remote_version": "",
            "registered_remote_version": patch_info.get("remote_version", ""),
            "messages": []
        }
            
        # Comprobar archivo local
        local_file = self.local_path / file_path
        local_exists = local_file.exists()
        details["local_exists"] = local_exists
        
        # Obtener checksum local actual
        current_local_checksum = ""
        if local_exists:
            current_local_checksum = self.calculate_checksum(local_file)
        details["current_local_checksum"] = current_local_checksum
            
        # Verificar existencia y checksum del archivo remoto
        remote_exists = False
        remote_checksum = ""
        current_remote_version = ""
        
        if ssh and ssh.client:
            # Construir ruta remota completa
            remote_file = self.remote_path + file_path
            
            # Comprobar si el archivo remoto existe
            cmd = f"test -f '{remote_file}' && echo 'EXISTS' || echo 'NOT_FOUND'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if "EXISTS" in stdout:
                remote_exists = True
                
                # Obtener checksum del archivo remoto
                remote_checksum = self.get_remote_file_checksum(ssh, remote_file)
                
                # Obtener versión del plugin/tema remoto
                current_remote_version = self.get_remote_file_version(ssh, file_path)
                
        details["remote_exists"] = remote_exists
        details["remote_checksum"] = remote_checksum
        details["current_remote_version"] = current_remote_version
                
        # Determinar estado del parche
        return determine_patch_status(
            patch_info,
            remote_exists,
            remote_checksum,
            local_exists,
            current_local_checksum,
            current_remote_version,
            patch_info.get("local_checksum", "")
        )

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

    def _load_patched_files(self) -> List[Tuple[str, str]]:
        """
        Carga la lista de archivos con parches registrados y sus backups desde el archivo lock
        
        Returns:
            List[Tuple[str, str]]: Lista de tuplas con (archivo parcheado, backup local)
        """
        patched_files = []
        
        # Verificar si existe el archivo lock
        if self.lock_data and "patches" in self.lock_data:
            # Extraer rutas de archivos con parches y sus backups
            for file_path, patch_info in self.lock_data["patches"].items():
                # Agregar el archivo parcheado
                local_backup = patch_info.get("local_backup_file", "")
                
                if local_backup:
                    patched_files.append((file_path, local_backup))
                    print(f"🔧 Excluyendo parche: {file_path} y su backup local: {local_backup}")
                else:
                    patched_files.append((file_path, None))
                    print(f"🔧 Excluyendo parche: {file_path} (sin backup local)")
                
                # Agregar backup remoto si existe
                remote_backup = patch_info.get("backup_file", "")
                if remote_backup and remote_backup.startswith(self.remote_path):
                    # Convertir la ruta remota completa a una ruta relativa
                    relative_backup = remote_backup[len(self.remote_path):]
                    patched_files.append((file_path, relative_backup))
                
            if patched_files:
                print(f"🔧 Se encontraron {len(patched_files)} parches y backups para excluir")
                
        return patched_files

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
    
    for file_path, info in manager.lock_data.get("patches", {}).items():
        if info.get("applied_date"):
            patched_files.append(file_path)
            
    return patched_files 