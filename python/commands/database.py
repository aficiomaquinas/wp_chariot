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
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from config_yaml import get_yaml_config
from utils.ssh import SSHClient
from utils.filesystem import ensure_dir_exists, create_backup
from utils.wp_cli import run_wp_cli

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
        
        # Cargar la configuración usando el sistema de sitios
        config_obj = get_yaml_config(verbose=self.verbose)
        
        # Valores predeterminados por si no se puede cargar la configuración
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
        
        # Cargar valores de la configuración
        if config_obj:
            # Obtener la configuración como diccionario
            config = config_obj.config
            
            # Cargar configuración SSH
            if 'ssh' in config:
                ssh_config = config['ssh']
                self.remote_host = ssh_config.get('remote_host', self.remote_host)
                self.remote_path = ssh_config.get('remote_path', self.remote_path)
                self.local_path = Path(ssh_config.get('local_path', str(self.local_path)))
            
            # Cargar configuración de seguridad
            if 'security' in config:
                security_config = config['security']
                self.production_safety = security_config.get('production_safety', 'enabled') == 'enabled'
            
            # Cargar configuración de URLs
            if 'urls' in config:
                urls_config = config['urls']
                self.remote_url = urls_config.get('remote', self.remote_url)
                self.local_url = urls_config.get('local', self.local_url)
            
            # Cargar configuración de base de datos remota
            if 'database' in config and 'remote' in config['database']:
                db_config = config['database']['remote']
                self.remote_db_name = db_config.get('name', self.remote_db_name)
                self.remote_db_user = db_config.get('user', self.remote_db_user)
                self.remote_db_pass = db_config.get('password', self.remote_db_pass)
                self.remote_db_host = db_config.get('host', self.remote_db_host)
        
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
        if config_obj and hasattr(config_obj, 'config'):
            self.config = config_obj.config
            
            # Verificar si tenemos configuración de DDEV y mostrarla si estamos en modo detallado
            if self.verbose and 'ddev' in self.config:
                ddev_webroot = self.config.get('ddev', {}).get('webroot', 'No configurada')
                print(f"   - DDEV webroot: {ddev_webroot}")
        
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
                
                # Evitar el doble slash cuando remote_path ya termina con /
                if self.remote_path.endswith('/'):
                    remote_temp_dir = f"{self.remote_path}wp-content"
                else:
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
                code, stdout, stderr = run_wp_cli(
                    ["db", "check"],
                    path=".",  # No importa aquí, se usa remote_path
                    remote=True,
                    remote_host=self.remote_host,
                    remote_path=self.remote_path
                )
                
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
        
        # Evitar doble slash en rutas remotas
        if self.remote_path.endswith('/'):
            remote_sql_file = f"{self.remote_path}wp-content/db-export-{timestamp}.sql"
        else:
            remote_sql_file = f"{self.remote_path}/wp-content/db-export-{timestamp}.sql"
        
        local_sql_file = temp_dir / f"db-export-{timestamp}.sql"
        
        # Obtener información sobre el charset de la base de datos
        with SSHClient(self.remote_host) as ssh:
            print("🔍 Obteniendo información sobre el charset de la base de datos...")
            charset_cmd = (
                f"cd {self.remote_path} && "
                f"wp db query 'SHOW VARIABLES LIKE \"%character%\";' --skip-column-names"
            )
            try:
                code, stdout, stderr = ssh.execute(charset_cmd)
                if code == 0 and stdout:
                    charset_info = stdout.strip().split('\n')
                    for line in charset_info:
                        if 'character_set_database' in line:
                            db_charset = line.split()[1]
                            print(f"   - Charset de la base de datos: {db_charset}")
                        elif 'character_set_connection' in line:
                            conn_charset = line.split()[1]
                            print(f"   - Charset de conexión: {conn_charset}")
            except Exception as e:
                print(f"   ⚠️ No se pudo obtener información del charset: {str(e)}")
        
        # Crear comando de exportación con opciones explícitas de charset
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
                print(f"   El archivo permanece en el servidor: {remote_sql_file}")
                return None
                
            # Solo eliminamos el archivo si la descarga fue exitosa
            print(f"🧹 Limpiando archivo temporal en el servidor...")
            ssh.execute(f"rm {remote_sql_file}")
            
        print(f"✅ Base de datos exportada exitosamente a {local_sql_file}")
        
        # Mostrar información sobre el archivo descargado
        file_size_mb = os.path.getsize(local_sql_file) / (1024*1024)
        print(f"   - Tamaño del archivo: {file_size_mb:.2f} MB")
        
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
        Reemplaza URLs en el archivo SQL exportado
        
        Args:
            sql_file: Ruta al archivo SQL
            reverse: Si es True, reemplaza local->remoto en lugar de remoto->local
            
        Returns:
            Optional[str]: Ruta al archivo procesado, None si hubo error
        """
        if not sql_file or not os.path.exists(sql_file):
            print(f"❌ Archivo SQL no encontrado: {sql_file}")
            return None
            
        # Ya no modificamos el archivo SQL, el reemplazo se hará después de importar
        if reverse:
            print(f"ℹ️ Las URLs se reemplazarán después de importar: {self.local_url} -> {self.remote_url}")
        else:
            print(f"ℹ️ Las URLs se reemplazarán después de importar: {self.remote_url} -> {self.local_url}")
            
        # Solo informar el tamaño del archivo
        file_size = os.path.getsize(sql_file)
        print(f"   - Tamaño del archivo: {file_size / (1024*1024):.2f} MB")
        
        return sql_file  # Devolvemos el mismo archivo sin procesar
            
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
        if not sql_file.endswith('.sql'):
            new_sql_file = f"{sql_file.split('.')[0]}.sql"
            try:
                os.rename(sql_file, new_sql_file)
                sql_file = new_sql_file
                print(f"✅ Archivo renombrado para asegurar compatibilidad: {sql_file}")
            except Exception as e:
                print(f"⚠️ No se pudo renombrar el archivo: {str(e)}")
        
        # Verificar el inicio del archivo SQL para detectar posibles problemas
        try:
            with open(sql_file, 'rb') as f:
                header = f.read(4096)  # Leer los primeros 4KB
                
                # Verificar si parece un archivo SQL válido
                if not header.startswith(b"-- ") and not header.startswith(b"/*") and b"CREATE TABLE" not in header and b"INSERT INTO" not in header:
                    print("⚠️ El archivo SQL podría no ser válido o tener un formato inesperado")
                    print("   Se intentará importar de todos modos pero podría fallar")
        except Exception as e:
            print(f"⚠️ No se pudo verificar el contenido del archivo SQL: {str(e)}")
            
        # Importar el SQL a DDEV
        try:
            print(f"⚙️ Importando archivo SQL a DDEV...")
            print(f"   Archivo: {sql_file}")
            print(f"   Tamaño: {os.path.getsize(sql_file) / (1024*1024):.2f} MB")
            
            # Obtener la ruta de WordPress dentro del contenedor desde la configuración (sites.yaml)
            ddev_wp_path = None
            if hasattr(self, 'config') and isinstance(self.config, dict) and 'ddev' in self.config:
                ddev_config = self.config.get('ddev', {})
                # Exigir explícitamente ambos parámetros (fail fast)
                if 'base_path' not in ddev_config or 'docroot' not in ddev_config:
                    print("❌ Error: Configuración DDEV incompleta en sites.yaml")
                    print("   Se requieren ambos parámetros:")
                    print("   - ddev.base_path: Ruta base dentro del contenedor (ej: \"/var/www/html\")")
                    print("   - ddev.docroot: Directorio del docroot (ej: \"app/public\")")
                    return False
                
                # Construir la ruta WP completa
                base_path = ddev_config.get('base_path')
                docroot = ddev_config.get('docroot')
                ddev_wp_path = f"{base_path}/{docroot}"
                print(f"ℹ️ Usando ruta WordPress: {ddev_wp_path}")
            else:
                print("❌ Error: No se encontró configuración DDEV en sites.yaml")
                print("   Se requiere la sección 'ddev' con 'base_path' y 'docroot'")
                return False
            
            # Usar un comando más explícito con todas las opciones completas
            # para diagnosticar mejor cualquier error
            result = subprocess.run(
                ["ddev", "import-db", "--file", sql_file, "--database", "db"],
                cwd=self.local_path.parent,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"❌ Error al importar base de datos:")
                print(f"   - Código de error: {result.returncode}")
                if result.stderr:
                    print(f"   - Error: {result.stderr}")
                if result.stdout:
                    print(f"   - Salida: {result.stdout}")
                    
                # Verificar errores comunes
                error_output = result.stderr + result.stdout
                if "ERROR 1180" in error_output or "Operation not permitted" in error_output:
                    print("\n⚠️ Se detectó un error de operación no permitida durante la importación.")
                    print("   Este error suele ocurrir por problemas de permisos o restricciones en el sistema de archivos.")
                    print("   Recomendaciones:")
                    print("   1. Asegúrate de que el usuario tiene permisos de escritura en el directorio")
                    print("   2. Verifica que no hay bloqueos en la base de datos")
                    print("   3. Intenta reimportar con un archivo más pequeño o fragmentado")
                
                elif "Unknown character set" in error_output:
                    print("\n⚠️ Se detectó un error de conjunto de caracteres desconocido.")
                    print("   Esto puede ocurrir cuando el SQL contiene declaraciones de charset que MySQL/MariaDB no reconoce.")
                    print("   Recomendaciones:")
                    print("   1. Edita el archivo SQL para cambiar las declaraciones de charset")
                    print("   2. Usa una herramienta como 'sed' para corregir estos problemas")
                    
                # Intentar un enfoque alternativo de importación directa por MySQL
                print("\n🔄 Intentando método alternativo de importación...")
                try:
                    alt_result = subprocess.run(
                        ["ddev", "mysql", "db", "<", sql_file],
                        cwd=self.local_path.parent,
                        shell=True,  # Necesario para la redirección
                        capture_output=True,
                        text=True
                    )
                    
                    if alt_result.returncode == 0:
                        print("✅ Importación alternativa exitosa usando MySQL directo")
                        # Continuar con el flujo de éxito
                    else:
                        print(f"❌ También falló el método alternativo: {alt_result.stderr}")
                        return False
                            
                except Exception as alt_e:
                    print(f"❌ Error en método alternativo: {str(alt_e)}")
                    return False
                    
                # Si llegamos aquí es porque el método alternativo tuvo éxito
                    
            print("✅ Base de datos importada exitosamente")
            
            # Ejecutar WP CLI para asegurarse de que todo funciona
            print("⚙️ Verificando instalación de WordPress...")
            
            if ddev_wp_path:
                print(f"   Usando ruta WordPress: {ddev_wp_path}")
            else:
                print("   ⚠️ No se encontró ruta WordPress en la configuración")
            
            # Usar la función run_wp_cli para verificar la instalación con la ruta correcta
            code, stdout, stderr = run_wp_cli(
                ["core", "is-installed"],
                self.local_path.parent,
                remote=False,
                use_ddev=True,
                wp_path=ddev_wp_path  # Pasar la ruta obtenida de la configuración
            )
            
            if code != 0:
                print("❌ WordPress no está instalado o no se pudo detectar")
                print("   La base de datos se importó correctamente, pero la verificación de WordPress falló")
                if stderr:
                    print(f"   Error: {stderr}")
            else:
                print("✅ WordPress verificado correctamente")
                
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
        
        # Evitar doble slash en rutas remotas
        if self.remote_path.endswith('/'):
            remote_sql_file = f"{self.remote_path}wp-content/db-import-{timestamp}.sql"
        else:
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
                print(f"   - Se importaría a DDEV (entorno local)")
                print(f"   - Se reemplazaría URL: {self.remote_url} -> {self.local_url} usando wp-cli")
                return True
                
            # Proceso real
            # 1. Exportar base de datos remota
            sql_file = self.export_remote_db()
            if not sql_file:
                return False
                
            # 2. Importar a local (sin modificar el archivo)
            success = self.import_to_local(sql_file)
            if not success:
                return False
                
            # 3. Reemplazar URLs usando wp-cli (después de importar)
            print(f"🔄 Reemplazando URLs en la base de datos...")
            
            # Obtener dominios sin protocolo
            remote_domain = self.remote_url.replace("https://", "").replace("http://", "")
            local_domain = self.local_url.replace("https://", "").replace("http://", "")
            
            print(f"   - Cambiando: {self.remote_url} -> {self.local_url}")
            
            # Lista completa de patrones a reemplazar para cubrir todos los casos posibles
            replacements = [
                # URLs con protocolo completo
                (self.remote_url, self.local_url),
                
                # URLs sin protocolo (//example.com)
                (f"//{remote_domain}", f"//{local_domain}"),
            ]
            
            # Si la URL remota usa HTTPS, añadir variante HTTP para asegurar que todas las URLs se reemplazan
            if self.remote_url.startswith("https://"):
                http_remote = self.remote_url.replace("https://", "http://")
                replacements.append((http_remote, self.local_url))
            
            # Variantes con www y sin www
            # Añadir variantes con www si no están presentes
            if not remote_domain.startswith("www."):
                www_remote_domain = f"www.{remote_domain}"
                # Con protocolo
                if "://" in self.remote_url:
                    protocol = self.remote_url.split("://")[0]
                    www_remote_url = f"{protocol}://{www_remote_domain}"
                    replacements.append((www_remote_url, self.local_url))
                # Sin protocolo
                replacements.append((f"//{www_remote_domain}", f"//{local_domain}"))
            # O variantes sin www si están presentes
            elif remote_domain.startswith("www."):
                non_www_remote_domain = remote_domain.replace("www.", "")
                # Con protocolo
                if "://" in self.remote_url:
                    protocol = self.remote_url.split("://")[0]
                    non_www_remote_url = f"{protocol}://{non_www_remote_domain}"
                    replacements.append((non_www_remote_url, self.local_url))
                # Sin protocolo
                replacements.append((f"//{non_www_remote_domain}", f"//{local_domain}"))
            
            # Ejecutar cada reemplazo
            for source, target in replacements:
                print(f"   - Reemplazando: {source} -> {target}")
                code, stdout, stderr = run_wp_cli(
                    ["search-replace", source, target, "--all-tables", "--precise", "--skip-columns=guid"],
                    self.local_path.parent,
                    remote=False,
                    use_ddev=True
                )
                
                if code != 0 and self.verbose:
                    print(f"   - Advertencia: {stderr}")
            
            # Limpiar transients después de reemplazar URLs
            print("🧹 Limpiando transients para evitar referencias antiguas...")
            code, stdout, stderr = run_wp_cli(
                ["transient", "delete", "--all"],
                self.local_path.parent,
                remote=False,
                use_ddev=True
            )
            
            if code != 0 and self.verbose:
                print(f"   - Advertencia al limpiar transients: {stderr}")
            else:
                print("   - Transients eliminados correctamente")
            
            print("✅ Todos los patrones de URL han sido reemplazados")
            
            # 4. Limpiar archivos temporales
            try:
                os.unlink(sql_file)
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
                print(f"   - Se reemplazaría URL: {self.local_url} -> {self.remote_url} usando wp-cli")
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
            
            # 1. Reemplazar URLs en la base de datos local antes de exportar
            print(f"🔄 Reemplazando URLs en la base de datos local...")
            
            # Obtener dominios sin protocolo
            remote_domain = self.remote_url.replace("https://", "").replace("http://", "")
            local_domain = self.local_url.replace("https://", "").replace("http://", "")
            
            print(f"   - Cambiando: {self.local_url} -> {self.remote_url}")
            
            # Lista completa de patrones a reemplazar para cubrir todos los casos posibles
            replacements = [
                # URLs con protocolo completo
                (self.local_url, self.remote_url),
                
                # URLs sin protocolo (//example.com)
                (f"//{local_domain}", f"//{remote_domain}"),
            ]
            
            # Si la URL local usa HTTPS, añadir variante HTTP para asegurar que todas las URLs se reemplazan
            if self.local_url.startswith("https://"):
                http_local = self.local_url.replace("https://", "http://")
                replacements.append((http_local, self.remote_url))
            
            # Variantes con www y sin www
            # Añadir variantes con www si no están presentes
            if not local_domain.startswith("www."):
                www_local_domain = f"www.{local_domain}"
                # Con protocolo
                if "://" in self.local_url:
                    protocol = self.local_url.split("://")[0]
                    www_local_url = f"{protocol}://{www_local_domain}"
                    replacements.append((www_local_url, self.remote_url))
                # Sin protocolo
                replacements.append((f"//{www_local_domain}", f"//{remote_domain}"))
            # O variantes sin www si están presentes
            elif local_domain.startswith("www."):
                non_www_local_domain = local_domain.replace("www.", "")
                # Con protocolo
                if "://" in self.local_url:
                    protocol = self.local_url.split("://")[0]
                    non_www_local_url = f"{protocol}://{non_www_local_domain}"
                    replacements.append((non_www_local_url, self.remote_url))
                # Sin protocolo
                replacements.append((f"//{non_www_local_domain}", f"//{remote_domain}"))
            
            try:
                # Ejecutar cada reemplazo
                for source, target in replacements:
                    print(f"   - Reemplazando: {source} -> {target}")
                    code, stdout, stderr = run_wp_cli(
                        ["search-replace", source, target, "--all-tables", "--precise", "--skip-columns=guid"],
                        self.local_path.parent,
                        remote=False,
                        use_ddev=True
                    )
                    
                    if code != 0 and self.verbose:
                        print(f"   - Advertencia: {stderr}")
                
                print("✅ Reemplazo de URLs completado")
            except Exception as e:
                print(f"⚠️ Error al reemplazar URLs: {str(e)}")
                print("   Continuando de todos modos...")
            
            # 2. Exportar base de datos local
            sql_file = self.export_local_db()
            if not sql_file:
                # Revertir los cambios de URL antes de salir
                print("🔄 Revirtiendo cambios de URL...")
                try:
                    # Restablecer cada patrón que reemplazamos
                    for target, source in replacements:  # Invertir el orden aquí
                        run_wp_cli(
                            ["search-replace", source, target, "--all-tables", "--precise", "--skip-columns=guid"],
                            self.local_path.parent,
                            remote=False,
                            use_ddev=True
                        )
                except:
                    print("⚠️ No se pudieron revertir los cambios de URL")
                return False
                
            # 3. Importar a remoto
            success = self.import_to_remote(sql_file)
            
            # 4. Revertir los cambios de URL en la base de datos local
            print("🔄 Restaurando URLs en la base de datos local...")
            try:
                # Restablecer cada patrón que reemplazamos
                for target, source in replacements:  # Invertir el orden aquí
                    run_wp_cli(
                        ["search-replace", source, target, "--all-tables", "--precise", "--skip-columns=guid"],
                        self.local_path.parent,
                        remote=False,
                        use_ddev=True
                    )
                print("✅ URLs locales restauradas")
            except:
                print("⚠️ No se pudieron restaurar las URLs locales")
            
            # 5. Limpiar archivos temporales
            try:
                os.unlink(sql_file)
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