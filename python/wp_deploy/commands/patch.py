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
from typing import Dict, List, Any, Optional, Tuple, Union

from wp_deploy.config_yaml import get_yaml_config, get_nested
from wp_deploy.utils.ssh import SSHClient
from wp_deploy.utils.filesystem import ensure_dir_exists, create_backup, get_default_exclusions
from wp_deploy.utils.wp_cli import get_item_version_from_path

class PatchManager:
    """
    Clase para gestionar la aplicación de parches
    """
    
    def __init__(self):
        """
        Inicializa el gestor de parches
        """
        self.config = get_yaml_config()
        
        # Cargar configuración
        self.remote_host = get_nested(self.config, "ssh", "remote_host")
        self.remote_path = get_nested(self.config, "ssh", "remote_path", "").rstrip('/')
        self.local_path = Path(get_nested(self.config, "ssh", "local_path"))
        
        # Cargar configuración de seguridad
        self.production_safety = get_nested(self.config, "security", "production_safety") == "enabled"
        
        # Cargar archivo lock
        self.lock_file = Path(__file__).resolve().parent.parent.parent / "patches.lock.json"
        self.lock_data = self.load_lock_file()
        
    def load_lock_file(self) -> Dict:
        """
        Carga el archivo lock con información de parches
        
        Returns:
            Dict: Datos del archivo lock
        """
        if not self.lock_file.exists():
            # Crear estructura inicial del archivo lock
            lock_data = {
                "patches": {},
                "last_updated": datetime.datetime.now().isoformat()
            }
            return lock_data
            
        try:
            with open(self.lock_file, 'r') as f:
                lock_data = json.load(f)
                
            print(f"✅ Archivo lock cargado: {len(lock_data.get('patches', {}))} parches registrados")
            return lock_data
            
        except Exception as e:
            print(f"⚠️ Error al cargar archivo lock: {str(e)}")
            print("   Se creará un nuevo archivo lock.")
            return {
                "patches": {},
                "last_updated": datetime.datetime.now().isoformat()
            }
    
    def save_lock_file(self):
        """
        Guarda los datos del archivo lock
        """
        try:
            # Actualizar fecha de modificación
            self.lock_data["last_updated"] = datetime.datetime.now().isoformat()
            
            with open(self.lock_file, 'w') as f:
                json.dump(self.lock_data, f, indent=2)
                
            print(f"✅ Archivo lock actualizado: {self.lock_file}")
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
            
    def list_patches(self) -> None:
        """
        Muestra la lista de parches registrados
        """
        if not self.lock_data.get("patches", {}):
            print("ℹ️ No hay parches registrados.")
            print("   Puedes agregar parches con el comando 'patch --add ruta/al/archivo'")
            return
            
        print("🔍 Parches registrados:")
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
            applied_date = info.get("applied_date", "No aplicado")
            local_checksum = info.get("local_checksum", "Desconocido")
            local_version = info.get("local_version", "Desconocida")
            remote_version = info.get("remote_version", "Desconocida")
            
            print(f"  - {file_path}")
            print(f"    • {item_type}: {plugin_name}")
            print(f"    • Descripción: {description}")
            print(f"    • Estado: {'✅ Aplicado' if info.get('applied_date') else '⏳ Registrado'} ({applied_date})")
            print(f"    • Versión local: {local_version}")
            if info.get("applied_date"):
                print(f"    • Versión remota: {remote_version}")
            print(f"    • Checksum local: {local_checksum}")
            print()
            
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
            remote_file: Ruta al archivo remoto
            
        Returns:
            str: Checksum MD5 del archivo remoto
        """
        # Comprobar si el archivo existe
        cmd_check = f"test -f \"{remote_file}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
        _, stdout, _ = ssh.execute(cmd_check)
        
        if "NOT_EXISTS" in stdout:
            return ""
            
        # Calcular checksum
        cmd_md5 = f"md5sum \"{remote_file}\" | cut -d' ' -f1"
        code, stdout, stderr = ssh.execute(cmd_md5)
        
        if code != 0 or not stdout.strip():
            print(f"⚠️ Error al obtener checksum remoto: {stderr}")
            return ""
            
        return stdout.strip()
    
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
        
    def apply_patch(self, file_path: str, dry_run: bool = False, show_details: bool = False, force: bool = False) -> bool:
        """
        Aplica un parche específico
        
        Args:
            file_path: Ruta relativa al archivo
            dry_run: Si es True, solo muestra qué se haría
            show_details: Si es True, muestra detalles adicionales del parche
            force: Si es True, aplica el parche incluso si las versiones no coinciden
            
        Returns:
            bool: True si el parche se aplicó correctamente, False en caso contrario
        """
        if "patches" not in self.lock_data or file_path not in self.lock_data["patches"]:
            print(f"❌ El parche '{file_path}' no está registrado.")
            print("   Usa 'patch --add {file_path}' para registrarlo primero.")
            return False
            
        patch_info = self.lock_data["patches"][file_path]
        description = patch_info.get("description", f"Parche para {file_path}")
        local_checksum = patch_info.get("local_checksum", "")
        
        print(f"🔄 Procesando: {file_path}")
        print(f"   Descripción: {description}")
        
        local_file = self.local_path / file_path
        remote_file = f"{self.remote_path}/{file_path}"
        
        # Verificar si el archivo local existe
        if not local_file.exists():
            print(f"   ❌ Error: El archivo local no existe: {local_file}")
            return False
            
        # Verificar que el checksum local coincide con el registrado
        current_local_checksum = self.calculate_checksum(local_file)
        if current_local_checksum != local_checksum:
            print(f"⚠️ ADVERTENCIA: El archivo local ha cambiado desde que se registró el parche.")
            print(f"   Checksum registrado: {local_checksum}")
            print(f"   Checksum actual: {current_local_checksum}")
            
            confirm = input("   ¿Deseas actualizar el registro y continuar? (s/n): ")
            if confirm.lower() != "s":
                print("   ⏭️ Operación cancelada.")
                return False
                
            # Actualizar el checksum en el registro
            patch_info["local_checksum"] = current_local_checksum
            self.lock_data["patches"][file_path] = patch_info
            self.save_lock_file()
            print("   ✅ Registro actualizado con el nuevo checksum.")
            
            # Actualizar variable local para uso posterior
            local_checksum = current_local_checksum
            
        # Verificar seguridad y posiblemente forzar dry-run
        safety_check = self.check_safety(force_dry_run=True)
        if safety_check is None:  # Forzar dry-run por seguridad
            dry_run = True
        elif not safety_check:  # Abortar si no es seguro y no se fuerza dry-run
            return False
            
        # Verificar conexión
        if not self.check_remote_connection():
            return False
            
        # Si es modo simulación o detalles, mostrar información
        if dry_run or show_details:
            print("   🔍 Modo informativo:")
            print(f"   - Archivo local: {local_file}")
            print(f"   - Checksum local: {local_checksum}")
            print(f"   - Destino remoto: {self.remote_host}:{remote_file}")
            
            item_type = patch_info.get("item_type", "other")
            item_slug = patch_info.get("item_slug", "")
            local_version = patch_info.get("local_version", "")
            
            if item_type != "other" and local_version:
                print(f"   - Tipo: {item_type}")
                print(f"   - Slug: {item_slug}")
                print(f"   - Versión local: {local_version}")
            
            if dry_run:
                print("   - Se crearía un backup del archivo en el servidor")
                print("   - Se subiría el archivo local al servidor")
                print("   - Se registraría el checksum en el archivo lock")
                
            # En modo de detalles, mostrar diferencias
            if show_details:
                self._show_file_diff(local_file, remote_file)
                
            if dry_run:
                return True
            
        # Crear un backup remoto antes de aplicar el parche
        with SSHClient(self.remote_host) as ssh:
            print("   📂 Verificando estado actual...")
            
            # Obtener checksum del archivo remoto actual
            remote_checksum = self.get_remote_file_checksum(ssh, remote_file)
            
            # Obtener información de versión remota para plugins/temas
            item_type = patch_info.get("item_type", "other")
            item_slug = patch_info.get("item_slug", "")
            local_version = patch_info.get("local_version", "")
            
            remote_version = ""
            if item_type in ["plugin", "theme"] and item_slug:
                _, _, remote_version = get_item_version_from_path(
                    file_path, 
                    self.remote_path,
                    remote=True,
                    remote_host=self.remote_host,
                    remote_path=self.remote_path,
                    use_ddev=False
                )
                
                # Verificar si las versiones coinciden
                if local_version and remote_version and local_version != remote_version and not force:
                    print(f"⚠️ ADVERTENCIA: Las versiones del {item_type} no coinciden")
                    print(f"   Versión local: {local_version}")
                    print(f"   Versión remota: {remote_version}")
                    print(f"   Este parche fue creado para la versión {local_version} y podría no ser compatible")
                    print(f"   con la versión {remote_version} instalada en el servidor.")
                    print("")
                    print(f"   Usa --force para aplicar el parche de todos modos.")
                    return False
                elif local_version and remote_version and local_version != remote_version and force:
                    print(f"⚠️ ADVERTENCIA: Forzando aplicación del parche a pesar de que las versiones no coinciden")
                    print(f"   Versión local: {local_version}")
                    print(f"   Versión remota: {remote_version}")
            
            # Verificar si ya se aplicó este parche
            if patch_info.get("patched_checksum"):
                # Comparar checksums para ver si el archivo remoto ha cambiado
                recorded_remote_checksum = patch_info.get("patched_checksum", "")
                
                if remote_checksum and remote_checksum == recorded_remote_checksum:
                    print("   ℹ️ Este parche ya se aplicó anteriormente y el archivo remoto no ha cambiado.")
                    confirm = input("   ¿Desea aplicar el parche de nuevo? (s/n): ")
                    if confirm.lower() != "s":
                        print("   ⏭️ Omitiendo este parche.")
                        return True  # Retornamos True porque el parche ya está aplicado
                elif remote_checksum:
                    print("   ⚠️ El archivo remoto ha cambiado desde la última aplicación del parche.")
                    print(f"   Checksum registrado: {recorded_remote_checksum}")
                    print(f"   Checksum actual: {remote_checksum}")
                    
                    confirm = input("   ¿Deseas continuar y sobrescribir los cambios remotos? (s/n): ")
                    if confirm.lower() != "s":
                        print("   ⏭️ Operación cancelada.")
                        return False
            
            # Verificar si el archivo remoto existe
            cmd_check = f"test -f \"{remote_file}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
            _, stdout, _ = ssh.execute(cmd_check)
            
            # Preparar nombre para backup
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_file = f"{remote_file}.bak.{timestamp}"
            
            if "EXISTS" in stdout:
                # Crear backup
                cmd_backup = f"cp \"{remote_file}\" \"{backup_file}\""
                ssh.execute(cmd_backup)
                print(f"   ✅ Backup creado: {backup_file}")
            else:
                print(f"   ⚠️ El archivo remoto no existe. Se creará un nuevo archivo.")
                # Crear directorio si es necesario
                dir_name = os.path.dirname(remote_file)
                ssh.execute(f"mkdir -p \"{dir_name}\"")
                backup_file = ""
                
            # Comparar archivos para mostrar diferencias, siempre es útil
            self._show_file_diff(local_file, remote_file, ssh)
            
            # Preguntar si se desea aplicar el parche
            apply_patch = input("   ¿Desea aplicar este parche en el servidor? (s/n): ")
            
            if apply_patch.lower() != "s":
                print("   ⏭️ Omitiendo este parche.")
                return False
                
            # Subir el archivo al servidor
            print("   📤 Subiendo archivo al servidor...")
            if not ssh.upload_file(local_file, remote_file):
                print("   ❌ Error al subir el archivo al servidor.")
                return False
                
            # Obtener checksum del archivo remoto después de parcharlo
            new_remote_checksum = self.get_remote_file_checksum(ssh, remote_file)
            
            # Actualizar información en el archivo lock
            self.lock_data["patches"][file_path].update({
                "original_checksum": remote_checksum,
                "patched_checksum": new_remote_checksum,
                "backup_file": backup_file,
                "applied_date": datetime.datetime.now().isoformat(),
                "remote_version": remote_version
            })
            
            # Guardar archivo lock
            self.save_lock_file()
            
            print("   ✅ Parche aplicado correctamente en el servidor.")
            
            # Información sobre el parche aplicado
            if '/plugins/' in file_path:
                plugin_name = file_path.split('/')[2]
                item_type = "Plugin"
            elif '/themes/' in file_path:
                plugin_name = file_path.split('/')[2]
                item_type = "Tema"
            else:
                plugin_name = os.path.basename(file_path)
                item_type = "Archivo"
                
            print("   ℹ️ Información del parche:")
            print(f"   - {item_type}: {plugin_name}")
            print(f"   - Archivo: {file_path}")
            if local_version and remote_version:
                print(f"   - Versión: {remote_version}")
            print(f"   - Checksum original: {remote_checksum or 'N/A (nuevo archivo)'}")
            print(f"   - Checksum después del parche: {new_remote_checksum}")
            if backup_file:
                print(f"   - Backup: {backup_file}")
            
            return True
    
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
            close_ssh = True
            
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
            
        success_count = 0
        total_count = len(self.lock_data["patches"])
        
        for file_path in self.lock_data["patches"]:
            success = self.apply_patch(file_path, dry_run, force=force)
            if success:
                success_count += 1
                
        print("")
        print(f"🎉 Proceso de aplicación de parches completado.")
        print(f"   ✅ {success_count}/{total_count} parches aplicados correctamente.")
        print(f"   📋 La información de los parches aplicados se ha guardado en {self.lock_file}")
        
        return success_count == total_count
        
def list_patches():
    """
    Muestra la lista de parches disponibles
    """
    manager = PatchManager()
    manager.list_patches()
    
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
        force: Si es True, aplica parches incluso si las versiones no coinciden
        
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
    
    # Si no hay parches registrados, devolver lista vacía
    if not manager.lock_data.get("patches"):
        return patched_files
        
    # Recopilar la lista de archivos parcheados
    for file_path, info in manager.lock_data.get("patches", {}).items():
        # Solo incluir archivos que tengan parche aplicado
        if info.get("applied_date"):
            patched_files.append(file_path)
            
    return patched_files 