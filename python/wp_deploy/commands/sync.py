"""
Módulo para sincronización de archivos entre entornos

Este módulo proporciona funciones para sincronizar archivos entre
un servidor remoto y el entorno local mediante rsync.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, Set

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
            
    def diff(self, dry_run: bool = True, show_all: bool = False, verbose: bool = False, only_patches: bool = False) -> bool:
        """
        Muestra las diferencias entre el servidor remoto y el entorno local.
        Este método siempre es de solo lectura y nunca realiza cambios,
        independientemente del valor del parámetro dry_run.
        
        Args:
            dry_run: Este parámetro se mantiene por compatibilidad pero siempre se ignora
            show_all: Si es True, muestra todos los archivos sin límite
            verbose: Si es True, muestra información detallada
            only_patches: Si es True, muestra solo información relacionada con parches
            
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        if not only_patches:
            print(f"🔍 Comparando archivos entre el servidor remoto y el entorno local...")
        
        # Verificar conexión
        if not self.check_remote_connection():
            return False
            
        # Preparar rutas (siempre desde remoto para diff)
        source, dest = self._prepare_paths("from-remote")
        
        # Obtener las exclusiones y verificar que sean un diccionario válido
        exclusions = self.exclusions.copy() if self.exclusions else {}
        if not exclusions:
            if not only_patches:
                print("ℹ️ No hay exclusiones configuradas. Usando exclusiones predeterminadas.")
            exclusions = get_default_exclusions()
        
        # Añadir archivos protegidos a las exclusiones para que no aparezcan en el diff
        if self.protected_files:
            if not only_patches:
                print(f"🛡️ Protegiendo {len(self.protected_files)} archivos durante la comparación")
            for i, file_pattern in enumerate(self.protected_files):
                exclusions[f"protected_{i}"] = file_pattern
            
        # Mostrar número de exclusiones
        if not only_patches:
            print(f"ℹ️ Se aplicarán {len(exclusions)} patrones de exclusión")
            
            # En modo verbose, mostrar los patrones de exclusión
            if verbose:
                print("📋 Aplicando patrones de exclusión:")
                for key, pattern in sorted(exclusions.items()):
                    print(f"   - {key}: {pattern}")
        
        # Opciones de rsync para mostrar diferencias
        options = [
            "-avzhnc",  # archivo, verbose, compresión, human-readable, dry-run, checksum
            "--itemize-changes",  # mostrar cambios detallados
            "--delete",  # eliminar archivos que no existen en origen
        ]
        
        # Ejecutar rsync en modo de comparación
        # Siempre usamos dry_run=True porque este método es solo para mostrar diferencias
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=exclusions,
            dry_run=True,  # Siempre en modo simulación para diff
            capture_output=True,  # Capturar la salida para procesarla nosotros
            verbose=verbose  # Solo mostrar la salida cruda en modo verbose
        )
        
        if not success:
            print("❌ Error al mostrar diferencias")
            return False
            
        # Si solo queremos información de parches, no necesitamos continuar con el análisis normal
        if only_patches:
            return self._analyze_patches(output, show_all, verbose)
        
        # Parsear la salida de rsync
        files_new = []       # Archivos nuevos en el servidor (>f....)
        files_modified = []  # Archivos modificados (.s....)
        files_deleted = []   # Archivos que serían eliminados (*deleting)
        files_directories = [] # Directorios (.d....)
        
        # Límite de archivos a mostrar por categoría
        limit = 0 if show_all else 100
        
        # Analizar cada línea de la salida
        for line in output.split('\n'):
            line = line.strip()
            
            # Ignorar líneas vacías o sin información de archivo
            if not line or line.startswith('sent ') or line.startswith('receiving ') or line.startswith('total size'):
                continue
                
            # Extraer el patrón de cambio y el nombre del archivo
            if line.startswith('>'):
                # Archivo nuevo en el servidor
                pattern = line[:10]
                file = line[10:].strip()
                files_new.append((pattern, file))
            elif line.startswith('*deleting'):
                # Archivo presente localmente pero no en el servidor
                file = line[10:].strip()
                files_deleted.append(('*deleting', file))
            elif line.startswith('.d'):
                # Directorio
                pattern = line[:10]
                file = line[10:].strip()
                files_directories.append((pattern, file))
            elif '.s' in line[:5]:
                # Archivo modificado
                pattern = line[:10]
                file = line[10:].strip()
                files_modified.append((pattern, file))
        
        # Crear función para imprimir archivos con límite
        def print_files(files, title, symbol, limit_count=limit):
            if not files:
                return
                
            count = len(files)
            print(f"\n{symbol} {title} ({count} elementos):")
            
            # Verificar si se debe limitar la salida
            if limit_count > 0 and count > limit_count:
                print_list = files[:limit_count]
                remainder = count - limit_count
            else:
                print_list = files
                remainder = 0
                
            # Imprimir archivos
            for pattern, file in print_list:
                if verbose:
                    print(f"   {pattern} {file}")
                else:
                    print(f"   {file}")
                    
            # Si hay más archivos que no se mostraron
            if remainder > 0:
                print(f"   ... y {remainder} más (usa --all para ver todos)")
        
        # Mostrar el resumen
        print("\n====== RESUMEN DE DIFERENCIAS ======")
        print(f"Total de archivos a comparar: {len(files_new) + len(files_modified) + len(files_deleted) + len(files_directories)}")
        
        # Mostrar archivos por categoría si hay alguno
        print_files(files_new, "Archivos nuevos en el servidor", "🆕")
        print_files(files_modified, "Archivos modificados en el servidor", "📝")
        print_files(files_deleted, "Archivos nuevos locales (no están en el servidor)", "🏠")
        
        # Directorios sólo si hay verbose
        if verbose:
            print_files(files_directories, "Directorios", "📁")
        
        # Analizar y mostrar información de parches
        self._analyze_patches(output, show_all, verbose, files_modified, files_deleted)
        
        return True
        
    def _analyze_patches(self, output: str = "", show_all: bool = False, verbose: bool = False, files_modified: list = None, files_deleted: list = None) -> bool:
        """
        Analiza la información de parches y muestra un resumen.
        
        Args:
            output: Salida de rsync para analizar (si no se proporciona files_modified y files_deleted)
            show_all: Si es True, muestra todos los archivos sin límite
            verbose: Si es True, muestra información detallada
            files_modified: Lista de archivos modificados ya procesada (opcional)
            files_deleted: Lista de archivos eliminados ya procesada (opcional)
            
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        # Si no se proporcionaron listas de archivos, procesamos la salida de rsync
        if files_modified is None or files_deleted is None:
            files_modified = []
            files_deleted = []
            
            # Analizar cada línea de la salida para extraer archivos
            for line in output.split('\n'):
                line = line.strip()
                
                # Ignorar líneas vacías o sin información de archivo
                if not line or line.startswith('sent ') or line.startswith('receiving ') or line.startswith('total size'):
                    continue
                    
                # Extraer el patrón de cambio y el nombre del archivo
                if line.startswith('*deleting'):
                    # Archivo presente localmente pero no en el servidor
                    file = line[10:].strip()
                    files_deleted.append(('*deleting', file))
                elif '.s' in line[:5]:
                    # Archivo modificado
                    pattern = line[:10]
                    file = line[10:].strip()
                    files_modified.append((pattern, file))
        
        # Obtener la lista de archivos parcheados
        try:
            from wp_deploy.commands.patch import get_patched_files, PatchManager
            
            # Primero mostramos un mensaje para confirmar que esta parte se ejecuta
            print("\n🔧 ANÁLISIS DE PARCHES")
            
            # Crear instancia del PatchManager para obtener más detalles
            patch_manager = PatchManager()
            
            # Extraer archivos nuevos locales (presentes en "files_deleted")
            local_files = [file for _, file in files_deleted]
            
            # En lugar de usar get_patched_files(), que solo muestra los parches aplicados,
            # obtendremos todos los parches registrados directamente desde lock_data
            patched_files = list(patch_manager.lock_data.get("patches", {}).keys())
            
            # Mostrar todos los parches registrados (incluso si no están afectados por cambios)
            if patched_files:
                print(f"   Se encontraron {len(patched_files)} archivos con parches registrados")
                
                # 1. Archivos con parches registrados
                print("\n📋 Archivos con parches registrados:")
                for patched_file in patched_files:
                    patch_info = patch_manager.lock_data["patches"].get(patched_file, {})
                    applied_date = patch_info.get("applied_date", "")
                    status = "✅ Aplicado" if applied_date else "❌ No aplicado"
                    print(f"   - {patched_file} [{status}]")
                    
                    # Si el parche está aplicado, verificar el estado actual del archivo remoto
                    if applied_date:
                        with SSHClient(self.remote_host) as ssh:
                            if ssh.client:
                                remote_file = f"{self.remote_path}/{patched_file}"
                                
                                # Verificar si el archivo existe en el servidor
                                cmd_check = f"test -f \"{remote_file}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
                                _, stdout, _ = ssh.execute(cmd_check)
                                
                                if "EXISTS" in stdout:
                                    # Obtener checksums
                                    current_remote_checksum = patch_manager.get_remote_file_checksum(ssh, remote_file)
                                    patched_checksum = patch_info.get("patched_checksum", "")
                                    
                                    if patched_checksum and current_remote_checksum:
                                        if current_remote_checksum == patched_checksum:
                                            print(f"      • Checksum remoto: ✅ Coincide con el parche")
                                        else:
                                            print(f"      • Checksum remoto: ⚠️ No coincide con el parche (modificado)")
                                            print(f"        El archivo remoto ha cambiado desde que se aplicó el parche")
                                    elif verbose:
                                        print(f"      • Checksum remoto: ⚠️ No se pudo verificar")
                                else:
                                    print(f"      • Archivo remoto: ⚠️ No existe en el servidor")
                                    
                    # Mostrar más detalles en modo verbose
                    if verbose:
                        print(f"      • Descripción: {patch_info.get('description', 'No hay descripción')}")
                        if applied_date:
                            print(f"      • Fecha de aplicación: {applied_date}")
                    
                # 2. Archivos nuevos locales con parches asociados
                local_patched = [file for file in local_files if file in patched_files]
                
                if local_patched:
                    print("\n📦 Archivos nuevos locales con parches asociados:")
                    for file in local_patched:
                        patch_info = patch_manager.lock_data["patches"].get(file, {})
                        applied_date = patch_info.get("applied_date", "")
                        status = "✅ Aplicado" if applied_date else "❌ No aplicado"
                        print(f"   - {file} [{status}]")
                        
                        if verbose:
                            print(f"      • Descripción: {patch_info.get('description', 'No hay descripción')}")
                else:
                    print("\n📦 No hay archivos nuevos locales con parches asociados")
                    
                # 3. Archivos modificados en el servidor con parches asociados
                modified_patched = [file for _, file in files_modified if file in patched_files]
                
                if modified_patched:
                    print("\n⚠️ Archivos parcheados con cambios en el servidor:")
                    for file in modified_patched:
                        patch_info = patch_manager.lock_data["patches"].get(file, {})
                        applied_date = patch_info.get("applied_date", "")
                        status = "✅ Aplicado" if applied_date else "❌ No aplicado"
                        print(f"   - {file} [{status}]")
                        print("      • Este archivo tiene cambios en el servidor que podrían sobrescribir el parche")
                        if applied_date:
                            print("      • Considera verificar los cambios antes de sincronizar")
                else:
                    print("\n✅ No hay archivos parcheados que hayan sido modificados en el servidor")
            else:
                print("   ✅ No se encontraron archivos parcheados registrados")
                
            # Mostrar sugerencias para la gestión de parches
            print("\n💡 SUGERENCIAS:")
            print("   • Usa 'python deploy-tools/python/cli.py patch --list' para ver todos los parches")
            print("   • Para aplicar todos los parches, ejecuta 'python deploy-tools/python/cli.py patch'")
            print("   • Para aplicar un parche específico: 'python deploy-tools/python/cli.py patch [ruta-archivo]'") 
            
            return True
                
        except Exception as e:
            # Si hay algún error en el análisis de parches, mostrarlo
            print(f"\n⚠️ Error al analizar parches: {str(e)}")
            if verbose:
                import traceback
                traceback.print_exc()
            return False
        
    def _check_protected_files(self, direction: str) -> bool:
        """
        Verifica si hay archivos protegidos que podrían ser sobrescritos
        
        Args:
            direction: Dirección de la sincronización ("from-remote" o "to-remote")
            
        Returns:
            bool: True si es seguro continuar, False en caso contrario
        """
        if not self.protected_files:
            return True
            
        protected_at_risk = []
        
        if direction == "from-remote":
            # Comprobando archivos locales protegidos que podrían ser sobrescritos
            for file_pattern in self.protected_files:
                full_path = self.local_path / file_pattern
                
                # Si es un patrón con comodín, usar glob
                if "*" in file_pattern:
                    matches = list(self.local_path.glob(file_pattern))
                    for match in matches:
                        if match.is_file():
                            rel_path = match.relative_to(self.local_path)
                            protected_at_risk.append(str(rel_path))
                elif Path(full_path).is_file():
                    protected_at_risk.append(file_pattern)
                    
        else:  # to-remote
            # Para subir archivos, simplemente advertir sobre todos los archivos protegidos
            protected_at_risk = self.protected_files
            
        if protected_at_risk:
            print("\n⚠️ ADVERTENCIA: Se han detectado archivos protegidos que podrían ser sobrescritos:")
            for file in protected_at_risk:
                print(f"  - {file}")
                
            # Solicitar confirmación explícita
            confirm = input("\n¿Deseas continuar a pesar de los archivos protegidos? (escriba 'si' para confirmar): ")
            
            if confirm.lower() != "si":
                print("❌ Operación cancelada para proteger archivos.")
                return False
                
            print("⚡ Confirmación recibida. Procediendo con la operación...")
            
        return True
        
    def _clean_excluded_files(self, direction: str) -> bool:
        """
        Limpia archivos excluidos en el destino después de la sincronización
        
        Args:
            direction: Dirección de la sincronización ("from-remote" o "to-remote")
            
        Returns:
            bool: True si la limpieza fue exitosa, False en caso contrario
        """
        # Esta función solo tiene sentido cuando se sincroniza desde remoto a local
        if direction != "from-remote":
            return True
            
        print("\n🧹 Limpiando archivos excluidos en el entorno local...")
        
        # Obtener exclusiones
        exclusions = self.exclusions
        if not exclusions:
            print("ℹ️ No hay exclusiones configuradas. Saltando limpieza.")
            return True
            
        # Contar archivos eliminados
        cleaned_count = 0
        
        # Procesar cada patrón de exclusión
        for category, pattern in exclusions.items():
            # Convertir a Path y comprobar si existe
            if pattern.endswith('/'):
                # Es un directorio
                dir_path = self.local_path / pattern.rstrip('/')
                if dir_path.exists() and dir_path.is_dir():
                    try:
                        # Eliminar el directorio completo
                        shutil.rmtree(dir_path)
                        print(f"✅ Directorio eliminado: {pattern}")
                        cleaned_count += 1
                    except Exception as e:
                        print(f"❌ Error al eliminar directorio {pattern}: {str(e)}")
            else:
                # Es un archivo o patrón
                if "*" in pattern:
                    # Patrón con comodín
                    matches = list(self.local_path.glob(pattern))
                    for match in matches:
                        try:
                            if match.is_file():
                                match.unlink()
                                print(f"✅ Archivo eliminado: {match.relative_to(self.local_path)}")
                                cleaned_count += 1
                            elif match.is_dir():
                                shutil.rmtree(match)
                                print(f"✅ Directorio eliminado: {match.relative_to(self.local_path)}")
                                cleaned_count += 1
                        except Exception as e:
                            print(f"❌ Error al eliminar {match}: {str(e)}")
                else:
                    # Archivo específico
                    file_path = self.local_path / pattern
                    if file_path.exists():
                        try:
                            if file_path.is_file():
                                file_path.unlink()
                                print(f"✅ Archivo eliminado: {pattern}")
                                cleaned_count += 1
                            elif file_path.is_dir():
                                shutil.rmtree(file_path)
                                print(f"✅ Directorio eliminado: {pattern}")
                                cleaned_count += 1
                        except Exception as e:
                            print(f"❌ Error al eliminar {pattern}: {str(e)}")
                            
        print(f"✅ Limpieza completa. {cleaned_count} elementos eliminados.")
        return True
        
    def sync(self, direction: str = "from-remote", dry_run: bool = False, clean: bool = True) -> bool:
        """
        Sincroniza archivos entre el servidor remoto y el entorno local
        
        Args:
            direction: Dirección de la sincronización ("from-remote" o "to-remote")
            dry_run: Si es True, no realiza cambios reales
            clean: Si es True, limpia archivos excluidos después de la sincronización
            
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
        
        # Verificar archivos protegidos
        if not dry_run and not self._check_protected_files(direction):
            return False
        
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
        
        # Preparar exclusiones con archivos protegidos
        exclusions = self.exclusions.copy() if self.exclusions else {}
        
        # Añadir archivos protegidos a las exclusiones
        if self.protected_files:
            print(f"🛡️ Protegiendo {len(self.protected_files)} archivos durante la sincronización")
            for i, file_pattern in enumerate(self.protected_files):
                exclusions[f"protected_{i}"] = file_pattern
        
        # Crear copia de seguridad del destino si no es modo simulación
        if not dry_run and direction == "from-remote":
            # Asegurarnos de que el directorio de destino existe
            ensure_dir_exists(self.local_path)
            
            # Opcionalmente, crear una copia de seguridad
            if self.config.get("security", "backups") == "enabled":
                print("📦 Creando copia de seguridad del entorno local...")
                backup_path = create_backup(self.local_path)
                if backup_path:
                    print(f"✅ Copia de seguridad creada en {backup_path}")
                else:
                    print("⚠️ No se pudo crear copia de seguridad")
            
        # Ejecutar rsync
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=exclusions,
            dry_run=dry_run
        )
        
        if not success:
            print("❌ Error durante la sincronización")
            return False
            
        # Si la sincronización fue exitosa y no es simulación
        if success and not dry_run:
            # Si fue desde remoto a local, arreglar configuración
            if direction == "from-remote":
                self._fix_local_config()
                
                # Limpieza de archivos excluidos si se solicitó
                if clean:
                    self._clean_excluded_files(direction)
                    
            print("✅ Sincronización completada con éxito")
            
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
                
def sync_files(direction: str = "from-remote", dry_run: bool = False, clean: bool = True) -> bool:
    """
    Sincroniza archivos entre entornos
    
    Args:
        direction: Dirección de la sincronización ("from-remote" o "to-remote")
        dry_run: Si es True, no realiza cambios reales
        clean: Si es True, limpia archivos excluidos después de la sincronización
        
    Returns:
        bool: True si la sincronización fue exitosa, False en caso contrario
    """
    synchronizer = FileSynchronizer()
    return synchronizer.sync(direction=direction, dry_run=dry_run, clean=clean) 