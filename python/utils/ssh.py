"""
Utilidades para operaciones SSH con servidores remotos
"""

import os
import paramiko
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import subprocess
import shlex

class SSHClient:
    """
    Cliente SSH para ejecutar comandos en servidores remotos
    """
    
    def __init__(self, host: str):
        """
        Inicializa el cliente SSH
        
        Args:
            host: Alias del host SSH (debe estar configurado en ~/.ssh/config)
        """
        self.host = host
        self.client = None
        
    def connect(self) -> bool:
        """
        Establece la conexión SSH con el servidor remoto
        
        Returns:
            bool: True si la conexión fue exitosa, False en caso contrario
        """
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Usar el archivo de configuración SSH del usuario
            ssh_config = paramiko.SSHConfig()
            user_config_file = os.path.expanduser("~/.ssh/config")
            
            if os.path.exists(user_config_file):
                with open(user_config_file) as f:
                    ssh_config.parse(f)
                    
                # Obtener la configuración para el host específico
                host_config = ssh_config.lookup(self.host)
                
                # Extraer parámetros de conexión
                hostname = host_config.get('hostname', self.host)
                port = int(host_config.get('port', 22))
                username = host_config.get('user', os.getenv('USER', 'root'))
                identity_file = host_config.get('identityfile', [None])[0]
                
                # Expandir la ruta del archivo de identidad
                if identity_file:
                    identity_file = os.path.expanduser(identity_file)
                
                # Conectar usando la configuración
                if identity_file:
                    self.client.connect(
                        hostname=hostname,
                        port=port,
                        username=username,
                        key_filename=identity_file
                    )
                else:
                    # Sin archivo de identidad, usar autenticación por contraseña o agente SSH
                    self.client.connect(
                        hostname=hostname,
                        port=port,
                        username=username
                    )
                
                print(f"✅ Conexión SSH establecida con {self.host} ({hostname})")
                return True
            else:
                print(f"❌ No se encontró el archivo de configuración SSH: {user_config_file}")
                return False
                
        except Exception as e:
            print(f"❌ Error al conectar con {self.host}: {str(e)}")
            return False
            
    def disconnect(self):
        """
        Cierra la conexión SSH
        """
        if self.client:
            self.client.close()
            print(f"✅ Conexión SSH cerrada con {self.host}")
            
    def __enter__(self):
        """
        Soporte para el patrón with
        """
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Cierra la conexión al salir del bloque with
        """
        self.disconnect()
        
    def execute(self, command: str) -> Tuple[int, str, str]:
        """
        Ejecuta un comando en el servidor remoto
        
        Args:
            command: Comando a ejecutar
            
        Returns:
            Tuple[int, str, str]: Código de salida, salida estándar, salida de error
        """
        if not self.client:
            print("❌ No hay conexión SSH establecida")
            return (1, "", "No hay conexión SSH establecida")
            
        try:
            print(f"🔄 Ejecutando comando remoto: {command}")
            stdin, stdout, stderr = self.client.exec_command(command)
            
            # Leer la salida
            stdout_str = stdout.read().decode('utf-8')
            stderr_str = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
            
            if exit_code != 0:
                print(f"⚠️ El comando devolvió código de salida {exit_code}")
                if stderr_str:
                    print(f"Error: {stderr_str}")
            
            return (exit_code, stdout_str, stderr_str)
            
        except Exception as e:
            print(f"❌ Error al ejecutar comando remoto: {str(e)}")
            return (1, "", str(e))
            
    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """
        Sube un archivo al servidor remoto
        
        Args:
            local_path: Ruta local del archivo
            remote_path: Ruta remota donde guardar el archivo
            
        Returns:
            bool: True si la transferencia fue exitosa, False en caso contrario
        """
        if not self.client:
            print("❌ No hay conexión SSH establecida")
            return False
            
        try:
            # Crear un cliente SFTP
            sftp = self.client.open_sftp()
            
            # Asegurarse de que el directorio remoto existe
            remote_dir = os.path.dirname(remote_path)
            self.execute(f"mkdir -p {shlex.quote(remote_dir)}")
            
            # Transferir el archivo
            print(f"📤 Subiendo archivo {local_path} -> {remote_path}")
            sftp.put(str(local_path), remote_path)
            sftp.close()
            
            print(f"✅ Archivo subido correctamente")
            return True
            
        except Exception as e:
            print(f"❌ Error al subir archivo: {str(e)}")
            return False
            
    def download_file(self, remote_path: str, local_path: Path) -> bool:
        """
        Descarga un archivo del servidor remoto
        
        Args:
            remote_path: Ruta remota del archivo
            local_path: Ruta local donde guardar el archivo
            
        Returns:
            bool: True si la transferencia fue exitosa, False en caso contrario
        """
        if not self.client:
            print("❌ No hay conexión SSH establecida")
            return False
            
        try:
            # Crear un cliente SFTP
            sftp = self.client.open_sftp()
            
            # Asegurarse de que el directorio local existe
            local_dir = local_path.parent
            local_dir.mkdir(parents=True, exist_ok=True)
            
            # Transferir el archivo
            print(f"📥 Descargando archivo {remote_path} -> {local_path}")
            sftp.get(remote_path, str(local_path))
            sftp.close()
            
            print(f"✅ Archivo descargado correctamente")
            return True
            
        except Exception as e:
            print(f"❌ Error al descargar archivo: {str(e)}")
            return False


def run_rsync(
    source: str,
    dest: str,
    options: List[str] = None,
    exclusions: Dict[str, str] = None,
    dry_run: bool = False,
    ssh_options: str = None,
    capture_output: bool = False,
    verbose: bool = False
) -> Tuple[bool, str]:
    """
    Ejecuta rsync para sincronizar archivos
    
    Args:
        source: Origen de la sincronización (puede ser local o remoto)
        dest: Destino de la sincronización (puede ser local o remoto)
        options: Opciones adicionales para rsync
        exclusions: Diccionario de patrones a excluir (clave -> patrón)
        dry_run: Si es True, no realiza cambios reales (simulación)
        ssh_options: Opciones adicionales para SSH
        capture_output: Si es True, captura la salida en lugar de mostrarla
        verbose: Si es True, muestra la salida detallada en tiempo real
        
    Returns:
        Tuple[bool, str]: True si la sincronización fue exitosa, False en caso contrario,
                          y la salida del comando
    """
    # Opciones predeterminadas
    if options is None:
        options = ["-avzh", "--delete"]
        
    # Añadir opción de simulación si es necesario
    if dry_run:
        options.append("--dry-run")
        
    # Configurar SSH
    ssh_cmd = "ssh"
    if ssh_options:
        ssh_cmd = f"ssh {ssh_options}"
        
    # Construir comando base
    cmd = ["rsync", "-e", ssh_cmd]
    
    # Añadir opciones
    cmd.extend(options)
    
    # Verificar exclusiones
    if exclusions is None:
        print("⚠️ No se proporcionaron exclusiones")
        exclusions = {}
    elif not isinstance(exclusions, dict):
        print("⚠️ El formato de exclusiones no es válido, se ignorarán")
        exclusions = {}
    
    # Crear archivo temporal de exclusiones si es necesario
    exclude_file = None
    exclusion_count = 0
    
    if exclusions and len(exclusions) > 0:
        import tempfile
        exclude_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
        
        # Solo mostrar los patrones si estamos en modo verbose
        if verbose:
            print(f"📋 Aplicando {len(exclusions)} patrones de exclusión:")
        
        try:
            # Asegurarse de que exclusions es un diccionario
            if isinstance(exclusions, dict):
                for key, pattern in exclusions.items():
                    if pattern:  # Solo añadir si el patrón no es None o vacío
                        if verbose:
                            print(f"   - {key}: {pattern}")
                        exclude_file.write(f"- {pattern}\n")
                        exclusion_count += 1
        except Exception as e:
            print(f"⚠️ Error al procesar exclusiones: {str(e)}")
            print("Continuando sin exclusiones...")
            
            # Cerrar y eliminar el archivo temporal
            try:
                exclude_file.close()
                os.unlink(exclude_file.name)
            except:
                pass
            
            exclude_file = None
            
        if exclude_file:
            exclude_file.close()
            cmd.extend(["--filter", f"merge {exclude_file.name}"])
            if verbose:
                print(f"✅ Se aplicaron {exclusion_count} patrones de exclusión")
    elif verbose:
        print("⚠️ No hay exclusiones definidas, se sincronizarán todos los archivos")
    
    # Añadir origen y destino
    cmd.append(source)
    cmd.append(dest)
    
    # Ejecutar comando
    cmd_str = " ".join([shlex.quote(str(arg)) for arg in cmd])
    print(f"🔄 Ejecutando: {cmd_str}")
    
    try:
        output = []
        
        if capture_output and not verbose:
            # Capturar la salida sin mostrarla en tiempo real
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False
            )
            
            output_text = process.stdout
            output = output_text.splitlines()
            return_code = process.returncode
            
        else:
            # Ejecutar con salida en tiempo real
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in process.stdout:
                line = line.rstrip()
                if verbose or not capture_output:
                    print(line)
                output.append(line)
                
            process.wait()
            return_code = process.returncode
        
        # Limpiar archivo temporal
        if exclude_file:
            try:
                os.unlink(exclude_file.name)
            except:
                pass
            
        if return_code == 0:
            print("✅ Sincronización completada con éxito")
            return True, "\n".join(output)
        else:
            print(f"❌ Error en la sincronización (código {return_code})")
            return False, "\n".join(output)
            
    except Exception as e:
        # Limpiar archivo temporal en caso de error
        if exclude_file:
            try:
                os.unlink(exclude_file.name)
            except:
                pass
        
        print(f"❌ Error al ejecutar rsync: {str(e)}")
        return False, str(e) 