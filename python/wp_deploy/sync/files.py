"""
Módulo para sincronización de archivos entre entornos

Este módulo proporciona funciones para sincronizar archivos entre
un servidor remoto y el entorno local mediante rsync.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from wp_deploy.config_yaml import get_yaml_config
from wp_deploy.utils.ssh import SSHClient, run_rsync
from wp_deploy.utils.filesystem import ensure_dir_exists, create_backup, get_default_exclusions

class FileSynchronizer:
    """
    Clase para sincronizar archivos entre entornos
    """
    
    def __init__(self):
        """
        Inicializa el sincronizador de archivos
        """
        self.config = get_yaml_config()
        
        # Cargar configuración
        self.remote_host = self.config.get("ssh", "remote_host")
        self.remote_path = self.config.get("ssh", "remote_path")
        self.local_path = Path(self.config.get("ssh", "local_path"))
        
        # Asegurarse de que las rutas remotas terminen con /
        if not self.remote_path.endswith("/"):
            self.remote_path += "/"
            
        # Cargar exclusiones
        self.exclusions = self.config.get_exclusions()
        
        # Cargar archivos protegidos
        self.protected_files = self.config.get_protected_files()
        
    def _prepare_paths(self, direction: str) -> Tuple[str, str]:
        """
        Prepara las rutas de origen y destino según la dirección
        
        Args:
            direction: Dirección de la sincronización ("from-remote" o "to-remote")
            
        Returns:
            Tuple[str, str]: Rutas de origen y destino
        """
        if direction == "from-remote":
            # Desde remoto a local
            source = f"{self.remote_host}:{self.remote_path}"
            dest = str(self.local_path)
        else:
            # Desde local a remoto
            source = str(self.local_path)
            dest = f"{self.remote_host}:{self.remote_path}"
            
        return source, dest
        
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
            
    def diff(self, dry_run: bool = True) -> bool:
        """
        Muestra las diferencias entre el servidor remoto y el entorno local
        
        Args:
            dry_run: Si es True, no realiza cambios reales
            
        Returns:
            bool: True si la sincronización fue exitosa, False en caso contrario
        """
        print(f"🔍 Comparando archivos entre el servidor remoto y el entorno local...")
        
        # Verificar conexión
        if not self.check_remote_connection():
            return False
            
        # Preparar rutas (siempre desde remoto para diff)
        source, dest = self._prepare_paths("from-remote")
        
        # Obtener las exclusiones y verificar que sean un diccionario válido
        exclusions = self.exclusions
        if not exclusions:
            print("ℹ️ No hay exclusiones configuradas. Usando exclusiones predeterminadas.")
            exclusions = get_default_exclusions()
            
        # Mostrar número de exclusiones
        print(f"ℹ️ Se aplicarán {len(exclusions)} patrones de exclusión")
        
        # Opciones de rsync para mostrar diferencias
        options = [
            "-avzhnc",  # archivo, verbose, compresión, human-readable, dry-run, checksum
            "--itemize-changes",  # mostrar cambios detallados
            "--delete",  # eliminar archivos que no existen en origen
        ]
        
        # Ejecutar rsync en modo de comparación
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=exclusions,
            dry_run=True  # Siempre en modo simulación para diff
        )
        
        return success
        
    def sync(self, direction: str = "from-remote", dry_run: bool = False) -> bool:
        """
        Sincroniza archivos entre el servidor remoto y el entorno local
        
        Args:
            direction: Dirección de la sincronización ("from-remote" o "to-remote")
            dry_run: Si es True, no realiza cambios reales
            
        Returns:
            bool: True si la sincronización fue exitosa, False en caso contrario
        """
        if direction == "from-remote":
            print(f"📥 Sincronizando archivos desde el servidor remoto al entorno local...")
        else:
            print(f"📤 Sincronizando archivos desde el entorno local al servidor remoto...")
            
            # Verificar si hay protección de producción activada
            if self.config.get("security", "production_safety") == "enabled":
                print("⚠️ ADVERTENCIA: Protección de producción está activada.")
                print("   Esta operación modificaría archivos en PRODUCCIÓN.")
                
                # Solicitar confirmación explícita
                confirm = input("   ¿Estás COMPLETAMENTE SEGURO de continuar? (escriba 'si' para confirmar): ")
                
                if confirm.lower() != "si":
                    print("❌ Operación cancelada por seguridad.")
                    return False
                    
                print("⚡ Confirmación recibida. Procediendo con la operación...")
                print("")
        
        # Verificar conexión
        if not self.check_remote_connection():
            return False
            
        # Preparar rutas
        source, dest = self._prepare_paths(direction)
        
        # Opciones de rsync
        options = [
            "-avzh",  # archivo, verbose, compresión, human-readable
            "--progress",  # mostrar progreso
            "--delete",  # eliminar archivos que no existen en origen
        ]
        
        # Si es simulación, agregar opción
        if dry_run:
            print("🔄 Ejecutando en modo simulación (no se realizarán cambios)")
            
        # Ejecutar rsync
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=self.exclusions,
            dry_run=dry_run
        )
        
        # Si la sincronización fue desde remoto a local, arreglar configuración local si es necesario
        if success and direction == "from-remote" and not dry_run:
            self._fix_local_config()
            
        return success
        
    def _fix_local_config(self):
        """
        Arregla configuración local después de sincronizar desde remoto
        """
        # Ajustar wp-config.php para DDEV si es necesario
        wp_config_path = self.local_path / "wp-config.php"
        wp_config_ddev_path = self.local_path / "wp-config-ddev.php"
        
        if wp_config_path.exists() and wp_config_ddev_path.exists():
            print("🔍 Verificando que wp-config.php incluya la configuración DDEV...")
            
            # Leer el archivo
            with open(wp_config_path, 'r') as f:
                content = f.read()
                
            # Verificar si ya incluye la configuración DDEV
            if "wp-config-ddev.php" not in content:
                print("⚙️ Corrigiendo wp-config.php para incluir configuración DDEV...")
                
                # Hacer una copia de seguridad
                create_backup(wp_config_path)
                
                # Código para incluir DDEV
                ddev_config = (
                    "<?php\n"
                    "// DDEV configuration\n"
                    "$ddev_settings = dirname(__FILE__) . '/wp-config-ddev.php';\n"
                    "if (is_readable($ddev_settings) && !defined('DB_USER')) {\n"
                    "  require_once($ddev_settings);\n"
                    "}\n\n"
                )
                
                # Añadir el código al principio del archivo
                with open(wp_config_path, 'w') as f:
                    f.write(ddev_config + content)
                    
                print("✅ wp-config.php actualizado para DDEV.")
            else:
                print("✅ wp-config.php ya incluye la configuración DDEV.")
                
# Clase para comandos de diferencias (más específicos que la sincronización general)
class DiffCommand:
    """
    Clase para comandos específicos de diferencias
    """
    
    def __init__(self):
        """
        Inicializa el objeto de diferencias
        """
        self.synchronizer = FileSynchronizer()
        
    def show_diff(self):
        """
        Muestra las diferencias entre el servidor remoto y el entorno local
        """
        return self.synchronizer.diff(dry_run=True)
        
# Funciones de nivel módulo para facilitar su uso desde otros módulos
def sync_files(direction: str = "from-remote", dry_run: bool = False) -> bool:
    """
    Sincroniza archivos entre entornos
    
    Args:
        direction: Dirección de la sincronización ("from-remote" o "to-remote")
        dry_run: Si es True, no realiza cambios reales
        
    Returns:
        bool: True si la sincronización fue exitosa, False en caso contrario
    """
    synchronizer = FileSynchronizer()
    return synchronizer.sync(direction=direction, dry_run=dry_run)
    
def show_diff() -> bool:
    """
    Muestra las diferencias entre el servidor remoto y el entorno local
    
    Returns:
        bool: True si la operación fue exitosa, False en caso contrario
    """
    diff_cmd = DiffCommand()
    return diff_cmd.show_diff() 