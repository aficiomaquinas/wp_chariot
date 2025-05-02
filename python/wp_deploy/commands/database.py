"""
Módulo para sincronización de base de datos entre entornos

Este módulo proporciona funciones para sincronizar la base de datos
entre un servidor remoto y el entorno local.
"""

import os
import sys
import tempfile
import time
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from wp_deploy.config_yaml import get_yaml_config
from wp_deploy.utils.ssh import SSHClient
from wp_deploy.utils.filesystem import ensure_dir_exists, create_backup

class DatabaseSynchronizer:
    """
    Clase para sincronizar bases de datos entre entornos
    """
    
    def __init__(self, verbose=False):
        """
        Inicializa el sincronizador de bases de datos
        
        Args:
            verbose: Si es True, muestra mensajes de depuración detallados
        """
        # Guardar nivel de verbosidad
        self.verbose = verbose
        
        # Cargar directamente el archivo config.yaml para evitar problemas de importación
        import yaml
        from pathlib import Path
        
        # Encontrar la ruta del archivo de configuración
        current_script_path = Path(__file__).resolve().parent.parent.parent
        config_file_path = current_script_path / "config.yaml"
        
        if self.verbose:
            print(f"🔍 Cargando configuración directamente desde: {config_file_path}")
        
        # Valores predeterminados por si no se puede cargar el archivo
        self.remote_host = "example-server"
        self.remote_path = ""
        self.local_path = Path(".")
        self.remote_url = ""
        self.local_url = ""
        self.remote_db_name = ""
        self.remote_db_user = ""
        self.remote_db_pass = ""
        self.remote_db_host = "localhost"
        self.production_safety = True
        
        # Cargar el archivo YAML directamente
        try:
            with open(config_file_path, 'r') as f:
                config_data = yaml.safe_load(f)
                
            # Cargar configuración SSH
            if 'ssh' in config_data:
                ssh_config = config_data['ssh']
                self.remote_host = ssh_config.get('remote_host', self.remote_host)
                self.remote_path = ssh_config.get('remote_path', self.remote_path)
                self.local_path = Path(ssh_config.get('local_path', str(self.local_path)))
            
            # Cargar configuración de seguridad
            if 'security' in config_data:
                security_config = config_data['security']
                self.production_safety = security_config.get('production_safety', 'enabled') == 'enabled'
            
            # Cargar configuración de URLs
            if 'urls' in config_data:
                urls_config = config_data['urls']
                self.remote_url = urls_config.get('remote', self.remote_url)
                self.local_url = urls_config.get('local', self.local_url)
            
            # Cargar configuración de base de datos remota
            if 'database' in config_data and 'remote' in config_data['database']:
                db_config = config_data['database']['remote']
                self.remote_db_name = db_config.get('name', self.remote_db_name)
                self.remote_db_user = db_config.get('user', self.remote_db_user)
                self.remote_db_pass = db_config.get('password', self.remote_db_pass)
                self.remote_db_host = db_config.get('host', self.remote_db_host)
        
        except Exception as e:
            import traceback
            print(f"❌ Error al cargar configuración: {str(e)}")
            traceback.print_exc()
        
        # Asegurarse de que las URLs no terminen con /
        if self.remote_url.endswith("/"):
            self.remote_url = self.remote_url[:-1]
            
        if self.local_url.endswith("/"):
            self.local_url = self.local_url[:-1]
        
        # Debug para verificar qué configuración se está cargando (solo si verbose es True)
        if self.verbose:
            print("📋 Configuración cargada:")
            print(f"   - SSH: {self.remote_host}:{self.remote_path}")
            print(f"   - URLs: {self.remote_url} → {self.local_url}")
            print(f"   - DB Host: {self.remote_db_host}")
            print(f"   - DB User: {self.remote_db_user}")
            print(f"   - DB Name: {self.remote_db_name}")
            print(f"   - DB Pass: {'*' * len(self.remote_db_pass) if self.remote_db_pass else 'no configurada'}")
        else:
            # Mostrar información mínima en modo normal
            print(f"📋 Configuración: {self.remote_host} → {self.remote_url} ⟷ {self.local_url}")
        
        # Guardar referencia a config para métodos que la necesitan
        self.config = {'security': {'backups': 'disabled'}}
        
        # Verificar si se están usando valores por defecto
        default_values = ["example-server", "nombre_db_remota", "usuario_db_remota", "contraseña_db_remota"]
        if any(val in default_values for val in [self.remote_host, self.remote_db_name, self.remote_db_user]):
            print("⚠️ ADVERTENCIA: Se están usando valores predeterminados en la configuración.")
            print("   Verifique que el archivo config.yaml está correctamente configurado.")
        
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
            
    def check_remote_database(self) -> bool:
        """
        Verifica la conexión a la base de datos remota
        
        Returns:
            bool: True si la conexión a la base de datos es exitosa, False en caso contrario
        """
        print(f"🔄 Verificando conexión a la base de datos remota...")
        
        # Verificar que las credenciales no son valores predeterminados
        default_credentials = ["nombre_db_remota", "usuario_db_remota", "contraseña_db_remota"]
        if self.remote_db_name in default_credentials or self.remote_db_user in default_credentials:
            print(f"❌ Error: Las credenciales de base de datos parecen ser valores predeterminados")
            print("   Es probable que no se estén cargando correctamente las variables del archivo .env")
            print("   Revise las siguientes claves en el archivo de configuración o .env:")
            print("   - REMOTE_DB_NAME: Base de datos remota")
            print("   - REMOTE_DB_USER: Usuario de base de datos")
            print("   - REMOTE_DB_PASS: Contraseña de la base de datos")
            return False
            
        if not self.remote_db_name or not self.remote_db_user:
            print(f"❌ Error: Faltan credenciales de base de datos remota")
            return False
            
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                return False
                
            # Verificar directamente con las credenciales configuradas
            # Método seguro: crear archivo local y subirlo, sin mostrar la contraseña en el registro
            import hashlib, random, string
            import tempfile
            import os
            
            # Crear un archivo temporal local con la configuración
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
                temp_file_path = temp_file.name
                temp_file.write(f"[client]\n")
                temp_file.write(f"host={self.remote_db_host}\n")
                temp_file.write(f"user={self.remote_db_user}\n")
                temp_file.write(f"password={self.remote_db_pass}\n")
                temp_file.flush()
            
            try:
                # Generar un nombre de archivo temporal único en el servidor
                random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                file_hash = hashlib.md5(f"{self.remote_db_name}_{random_suffix}".encode()).hexdigest()
                remote_temp_dir = f"{self.remote_path}/wp-content"
                remote_temp_pass = f"{remote_temp_dir}/.wp_deploy_tmp_{file_hash}.cnf"
                
                # Subir el archivo al servidor
                if self.verbose:
                    print(f"🔒 Subiendo configuración de conexión segura...")
                
                if not ssh.upload_file(temp_file_path, remote_temp_pass):
                    print("❌ Error al subir configuración de conexión")
                    return False
                
                # Establecer permisos correctos
                ssh.execute(f"chmod 600 {remote_temp_pass}")
                
                # Comando MySQL seguro que usa el archivo de configuración temporal
                mysql_check_cmd = (
                    f"mysql --defaults-extra-file={remote_temp_pass} "
                    f"-e 'SHOW DATABASES LIKE \"{self.remote_db_name}\";'"
                )
                
                # Ejecutar el comando para verificar la conexión
                code, stdout, stderr = ssh.execute(mysql_check_cmd)
                
                # Analizar resultado
                if code != 0:
                    print(f"❌ Error al conectar con MySQL: {stderr}")
                    print("   Verifique las credenciales de base de datos en la configuración:")
                    print(f"   - Host: {self.remote_db_host}")
                    print(f"   - Usuario: {self.remote_db_user}")
                    print(f"   - Base de datos: {self.remote_db_name}")
                    return False
                    
                if self.remote_db_name not in stdout:
                    print(f"❌ La base de datos '{self.remote_db_name}' no existe o no es accesible")
                    print("   Verifique el nombre de la base de datos en la configuración")
                    return False
                
                # Verificar que también podemos conectarnos usando wp-cli
                # (esto verifica que WordPress está correctamente configurado)
                db_check_cmd = f"cd {self.remote_path} && wp db check"
                code, stdout, stderr = ssh.execute(db_check_cmd)
                
                if code != 0:
                    print(f"⚠️ WordPress puede no estar correctamente configurado: {stderr}")
                    if self.verbose:
                        print("   La conexión directa a MySQL funciona, pero wp-cli no puede conectarse.")
                        print("   Esto podría indicar un problema con el archivo wp-config.php")
                    # No fallamos aquí porque la conexión directa a MySQL sí funciona
                    
                print(f"✅ Conexión a la base de datos remota verificada con éxito")
                if self.verbose:
                    print(f"   Base de datos: {self.remote_db_name}@{self.remote_db_host}")
                return True
                
            finally:
                # Eliminar el archivo temporal independientemente del resultado
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                
                # Eliminar el archivo temporal en el servidor
                ssh.execute(f"rm -f {remote_temp_pass}")
            
    def export_remote_db(self) -> Optional[str]:
        """
        Exporta la base de datos remota a un archivo SQL
        
        Returns:
            Optional[str]: Ruta al archivo de exportación o None si falló
        """
        print(f"📤 Exportando base de datos remota '{self.remote_db_name}'...")
        
        # Verificar conexión
        if not self.check_remote_connection():
            return None
            
        # Crear directorio temporal para el archivo SQL
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        temp_dir = Path(tempfile.gettempdir()) / f"wp-deploy-{timestamp}"
        ensure_dir_exists(temp_dir)
        
        remote_sql_file = f"{self.remote_path}/wp-content/db-export-{timestamp}.sql"
        local_sql_file = temp_dir / f"db-export-{timestamp}.sql"
        
        # Crear comando de exportación
        export_cmd = (
            f"cd {self.remote_path} && "
            f"wp db export {remote_sql_file} --add-drop-table"
        )
        
        # Ejecutar comando de exportación en el servidor remoto
        with SSHClient(self.remote_host) as ssh:
            print("⚙️ Ejecutando exportación en el servidor remoto...")
            code, stdout, stderr = ssh.execute(export_cmd)
            
            if code != 0:
                print(f"❌ Error al exportar base de datos remota: {stderr}")
                return None
                
            # Descargar archivo SQL
            print(f"⬇️ Descargando archivo SQL ({remote_sql_file})...")
            success = ssh.download_file(remote_sql_file, local_sql_file)
            
            if not success:
                print("❌ Error al descargar archivo SQL")
                return None
                
            # Eliminar archivo SQL temporal en el servidor remoto
            ssh.execute(f"rm {remote_sql_file}")
            
        print(f"✅ Base de datos exportada exitosamente a {local_sql_file}")
        return str(local_sql_file)

    def export_local_db(self) -> Optional[str]:
        """
        Exporta la base de datos local (DDEV) a un archivo SQL
        
        Returns:
            Optional[str]: Ruta al archivo de exportación o None si falló
        """
        print(f"📤 Exportando base de datos local (DDEV)...")
        
        # Verificar que DDEV está instalado
        try:
            subprocess.run(["ddev", "--version"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            print("❌ DDEV no está instalado o no está en el PATH")
            return None

        # Crear directorio temporal para el archivo SQL
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        temp_dir = Path(tempfile.gettempdir()) / f"wp-deploy-{timestamp}"
        ensure_dir_exists(temp_dir)
        
        local_sql_file = temp_dir / f"db-export-local-{timestamp}.sql"
        
        # Exportar base de datos local usando DDEV
        try:
            print("⚙️ Ejecutando exportación en el entorno local...")
            result = subprocess.run(
                ["ddev", "export-db", "-f", str(local_sql_file)],
                cwd=self.local_path.parent,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"❌ Error al exportar base de datos local: {result.stderr}")
                return None
                
            print(f"✅ Base de datos local exportada exitosamente a {local_sql_file}")
            return str(local_sql_file)
            
        except Exception as e:
            print(f"❌ Error durante la exportación: {str(e)}")
            return None
        
    def search_replace_urls(self, sql_file: str, reverse: bool = False) -> Optional[str]:
        """
        Reemplaza URLs en el archivo SQL
        
        Args:
            sql_file: Ruta al archivo SQL de origen
            reverse: Si es True, reemplaza local -> remoto en lugar de remoto -> local
            
        Returns:
            Optional[str]: Ruta al archivo SQL procesado o None si falló
        """
        if not sql_file or not os.path.exists(sql_file):
            print(f"❌ Archivo SQL no encontrado: {sql_file}")
            return None
        
        if reverse:
            source_url = self.local_url
            target_url = self.remote_url
            print(f"🔄 Procesando URLs en archivo SQL (local -> remoto)...")
        else:
            source_url = self.remote_url
            target_url = self.local_url
            print(f"🔄 Procesando URLs en archivo SQL (remoto -> local)...")
            
        print(f"   - Reemplazando: {source_url} -> {target_url}")
        
        # Crear archivo temporal para el resultado
        output_file = f"{sql_file.split('.')[0]}.sql"
        
        try:
            # Leer el archivo SQL
            with open(sql_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Reemplazar URLs
            content = content.replace(source_url, target_url)
            
            # Reemplazar variantes con www, https, http
            source_variants = [
                source_url.replace('https://', 'http://'),
                source_url.replace('http://', 'https://'),
                source_url.replace('://www.', '://'),
                source_url.replace('://', '://www.')
            ]
            
            for source_var in source_variants:
                if source_var != source_url:
                    content = content.replace(source_var, target_url)
                    
            # Guardar el archivo procesado
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
            print(f"✅ URLs procesadas exitosamente")
            return output_file
            
        except Exception as e:
            print(f"❌ Error al procesar URLs: {str(e)}")
            return None
            
    def import_to_local(self, sql_file: str) -> bool:
        """
        Importa el archivo SQL al entorno local (DDEV)
        
        Args:
            sql_file: Ruta al archivo SQL a importar
            
        Returns:
            bool: True si la importación fue exitosa, False en caso contrario
        """
        if not sql_file or not os.path.exists(sql_file):
            print(f"❌ Archivo SQL no encontrado: {sql_file}")
            return False
            
        print(f"📥 Importando base de datos a entorno local (DDEV)...")
        
        # Verificar que DDEV está instalado
        try:
            subprocess.run(["ddev", "--version"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            print("❌ DDEV no está instalado o no está en el PATH")
            return False
            
        # Crear copia de seguridad de la base de datos local si está configurado
        if self.config.get('security', {}).get('backups', 'disabled') == "enabled":
            print("📦 Creando copia de seguridad de la base de datos local...")
            try:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                backup_dir = Path(self.local_path).parent / "db-backups"
                ensure_dir_exists(backup_dir)
                
                backup_file = backup_dir / f"db-backup-{timestamp}.sql"
                result = subprocess.run(
                    ["ddev", "export-db", "-f", str(backup_file)],
                    cwd=self.local_path.parent,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"✅ Copia de seguridad creada en {backup_file}")
                else:
                    print(f"⚠️ No se pudo crear copia de seguridad: {result.stderr}")
                    
            except Exception as e:
                print(f"⚠️ Error al crear copia de seguridad: {str(e)}")
                
        # Asegurarse de que el archivo tenga la extensión correcta
        if sql_file.endswith('.processed'):
            new_sql_file = sql_file.replace('.processed', '')
            try:
                os.rename(sql_file, new_sql_file)
                sql_file = new_sql_file
                print(f"✅ Archivo renombrado para asegurar compatibilidad: {sql_file}")
            except Exception as e:
                print(f"⚠️ No se pudo renombrar el archivo: {str(e)}")
                
        # Importar el SQL a DDEV
        try:
            print(f"⚙️ Importando archivo SQL a DDEV...")
            result = subprocess.run(
                ["ddev", "import-db", "--file", sql_file],
                cwd=self.local_path.parent,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"❌ Error al importar base de datos: {result.stderr}")
                return False
                
            print("✅ Base de datos importada exitosamente")
            
            # Intentar actualizar la URL del sitio y el home
            try:
                print("⚙️ Actualizando configuración de WordPress...")
                subprocess.run(
                    ["ddev", "wp", "option", "update", "siteurl", self.local_url],
                    cwd=self.local_path.parent,
                    capture_output=True
                )
                subprocess.run(
                    ["ddev", "wp", "option", "update", "home", self.local_url],
                    cwd=self.local_path.parent,
                    capture_output=True
                )
            except Exception as e:
                print(f"⚠️ No se pudo actualizar la URL del sitio: {str(e)}")
            
            # Ejecutar WP CLI para asegurarse de que todo funciona
            print("⚙️ Verificando instalación de WordPress...")
            wp_check = subprocess.run(
                ["ddev", "wp", "core", "is-installed"],
                cwd=self.local_path.parent,
                capture_output=True,
                text=True
            )
            
            if wp_check.returncode != 0:
                print("⚠️ WordPress no está completamente configurado después de la importación")
                print("   Esto puede deberse a diferencias en la configuración entre entornos")
                print("   Pero la base de datos se ha importado correctamente.")
                # No fallamos aquí, ya que la importación funcionó
            else:
                print("✅ WordPress está correctamente instalado y configurado")
                
                # Limpiar cualquier caché existente
                print("🧹 Limpiando caché...")
                subprocess.run(
                    ["ddev", "wp", "cache", "flush"],
                    cwd=self.local_path.parent,
                    capture_output=True
                )
            
            return True
            
        except Exception as e:
            print(f"❌ Error durante la importación: {str(e)}")
            return False

    def import_to_remote(self, sql_file: str) -> bool:
        """
        Importa el archivo SQL al servidor remoto
        
        Args:
            sql_file: Ruta al archivo SQL a importar
            
        Returns:
            bool: True si la importación fue exitosa, False en caso contrario
        """
        if not sql_file or not os.path.exists(sql_file):
            print(f"❌ Archivo SQL no encontrado: {sql_file}")
            return False
            
        print(f"📤 Importando base de datos al servidor remoto...")
        
        # Verificar conexión
        if not self.check_remote_connection():
            return False
            
        # Asegurarse de que el archivo tenga la extensión correcta
        if sql_file.endswith('.processed'):
            new_sql_file = sql_file.replace('.processed', '')
            try:
                os.rename(sql_file, new_sql_file)
                sql_file = new_sql_file
                print(f"✅ Archivo renombrado para asegurar compatibilidad: {sql_file}")
            except Exception as e:
                print(f"⚠️ No se pudo renombrar el archivo: {str(e)}")
                
        # Crear nombre para el archivo SQL temporal en el servidor
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        remote_sql_file = f"{self.remote_path}/wp-content/db-import-{timestamp}.sql"
        
        # Subir archivo SQL al servidor
        with SSHClient(self.remote_host) as ssh:
            print(f"⬆️ Subiendo archivo SQL al servidor...")
            success = ssh.upload_file(sql_file, remote_sql_file)
            
            if not success:
                print("❌ Error al subir archivo SQL")
                return False
                
            # Crear comando para importar
            import_cmd = (
                f"cd {self.remote_path} && "
                f"wp db import {remote_sql_file} --skip-optimization"
            )
            
            # Ejecutar comando de importación
            print("⚙️ Importando base de datos en el servidor remoto...")
            code, stdout, stderr = ssh.execute(import_cmd)
            
            # Eliminar archivo SQL temporal independientemente del resultado
            ssh.execute(f"rm {remote_sql_file}")
            
            if code != 0:
                print(f"❌ Error al importar base de datos: {stderr}")
                return False
                
            # Limpiar caché de WordPress
            print("🧹 Limpiando caché en el servidor remoto...")
            ssh.execute(f"cd {self.remote_path} && wp cache flush")
            
            print("✅ Base de datos importada exitosamente al servidor remoto")
            return True
            
    def sync(self, direction: str = "from-remote", dry_run: bool = False) -> bool:
        """
        Sincroniza la base de datos entre entornos
        
        Args:
            direction: Dirección de la sincronización ("from-remote" o "to-remote")
            dry_run: Si es True, solo muestra qué se haría
            
        Returns:
            bool: True si la sincronización fue exitosa, False en caso contrario
        """
        if direction == "from-remote":
            print(f"📥 Sincronizando base de datos desde el servidor remoto al entorno local...")
            
            # Verificar conexión incluso en modo dry-run
            if not self.check_remote_connection():
                print("❌ No se puede continuar sin una conexión remota válida")
                return False
            
            # Verificar información de base de datos remota
            if not self.remote_db_name:
                print("❌ Error: No se ha configurado el nombre de la base de datos remota")
                print("   Por favor, establezca database.remote.name en el archivo de configuración.")
                return False
                
            # Verificar conexión a la base de datos remota
            if not self.check_remote_database():
                print("❌ No se puede continuar sin una conexión a la base de datos remota válida")
                return False
                
            # Verificar que DDEV está instalado
            try:
                subprocess.run(["ddev", "--version"], capture_output=True, check=True)
            except (subprocess.SubprocessError, FileNotFoundError):
                print("❌ DDEV no está instalado o no está en el PATH")
                print("   Se requiere DDEV para la sincronización con el entorno local")
                return False
                
            if dry_run:
                print("🔄 Modo simulación: No se realizarán cambios reales")
                print(f"   - Se exportaría la base de datos remota '{self.remote_db_name}'")
                print(f"   - Se reemplazaría URL: {self.remote_url} -> {self.local_url}")
                print(f"   - Se importaría a DDEV (entorno local)")
                return True
                
            # Proceso real
            # 1. Exportar base de datos remota
            sql_file = self.export_remote_db()
            if not sql_file:
                return False
                
            # 2. Reemplazar URLs
            processed_file = self.search_replace_urls(sql_file)
            if not processed_file:
                return False
                
            # 3. Importar a local
            success = self.import_to_local(processed_file)
            
            # 4. Limpiar archivos temporales
            try:
                os.unlink(sql_file)
                os.unlink(processed_file)
            except:
                pass
                
            return success
            
        else:  # to-remote
            print(f"📤 Sincronizando base de datos desde el entorno local al servidor remoto...")
            
            # Comprobar si la protección de producción está activada
            if self.production_safety:
                print("⛔ ERROR: No se puede subir la base de datos a producción con la protección activada.")
                print("   Esta operación podría sobrescribir datos críticos en el servidor.")
                print("   Para continuar, debes desactivar 'production_safety' en la configuración YAML:")
                print("   security:")
                print("     production_safety: disabled")
                print("")
                print("   ⚠️ ADVERTENCIA: Solo desactiva esta protección si estás completamente seguro de lo que haces.")
                return False
                
            # Verificar conexión incluso en modo dry-run
            if not self.check_remote_connection():
                print("❌ No se puede continuar sin una conexión remota válida")
                return False
                
            # Verificar conexión a la base de datos remota
            if not self.check_remote_database():
                print("❌ No se puede continuar sin una conexión a la base de datos remota válida")
                return False
                
            # Verificar que DDEV está instalado
            try:
                subprocess.run(["ddev", "--version"], capture_output=True, check=True)
            except (subprocess.SubprocessError, FileNotFoundError):
                print("❌ DDEV no está instalado o no está en el PATH")
                print("   Se requiere DDEV para exportar la base de datos local")
                return False
                
            if dry_run:
                print("🔄 Modo simulación: No se realizarán cambios reales")
                print("   - Se exportaría la base de datos local")
                print(f"   - Se reemplazaría URL: {self.local_url} -> {self.remote_url}")
                print(f"   - Se importaría al servidor remoto")
                return True
                
            # Solicitar confirmación explícita
            print("⚠️ ADVERTENCIA: Estás a punto de sobrescribir la base de datos de PRODUCCIÓN.")
            print("   Esta operación NO SE PUEDE DESHACER y podría causar pérdida de datos.")
            confirm = input("   ¿Estás COMPLETAMENTE SEGURO de continuar? (escriba 'SI CONFIRMO' para continuar): ")
            
            if confirm != "SI CONFIRMO":
                print("❌ Operación cancelada por el usuario.")
                return False
                
            print("⚡ Confirmación recibida. Procediendo con la operación...")
            
            # 1. Exportar base de datos local
            sql_file = self.export_local_db()
            if not sql_file:
                return False
                
            # 2. Reemplazar URLs (de local a remoto)
            processed_file = self.search_replace_urls(sql_file, reverse=True)
            if not processed_file:
                return False
                
            # 3. Importar a remoto
            success = self.import_to_remote(processed_file)
            
            # 4. Limpiar archivos temporales
            try:
                os.unlink(sql_file)
                os.unlink(processed_file)
            except:
                pass
                
            return success
            
def sync_database(direction: str = "from-remote", dry_run: bool = False, verbose: bool = False) -> bool:
    """
    Sincroniza la base de datos entre entornos
    
    Args:
        direction: Dirección de la sincronización ("from-remote" o "to-remote")
        dry_run: Si es True, solo muestra qué se haría
        verbose: Si es True, muestra mensajes de depuración detallados
        
    Returns:
        bool: True si la sincronización fue exitosa, False en caso contrario
    """
    synchronizer = DatabaseSynchronizer(verbose=verbose)
    return synchronizer.sync(direction=direction, dry_run=dry_run) 