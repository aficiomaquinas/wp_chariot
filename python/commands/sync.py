"""
File synchronization module between environments

This module provides functions to synchronize files between
a remote server and the local environment using rsync.
"""

import os
import sys
import tempfile
import shutil
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, Set
import fnmatch

from config_yaml import get_yaml_config
from utils.ssh import SSHClient, run_rsync
from utils.filesystem import ensure_dir_exists, create_backup
from commands.backup import create_full_backup

class FileSynchronizer:
    """
    Class for synchronizing files between environments
    """
    
    def __init__(self):
        """
        Initializes the file synchronizer
        """
        self.config = get_yaml_config()
        
        # Load configuration
        self.remote_host = self.config.get("ssh", "remote_host")
        self.remote_path = self.config.get("ssh", "remote_path")
        self.local_path = Path(self.config.get("ssh", "local_path"))
        
        # Ensure remote paths end with a single /
        # IMPORTANTE: Para rsync, la barra al final significa "copiar el contenido" no "crear el directorio"
        if not self.remote_path.endswith('/'):
            self.remote_path += '/'
        
        # Asegurar que la ruta local sea absoluta
        if not self.local_path.is_absolute():
            print(f"⚠️ La ruta local '{self.local_path}' no es absoluta. Se recomienda usar rutas absolutas.")
            
        # Load exclusions
        self.exclusions = self.config.get_exclusions()
        
        # Load protected files
        self.protected_files = self.config.get_protected_files()
        
        # Load memory limit for WP-CLI
        self.wp_memory_limit = self.config.get_wp_memory_limit()
        
    def _load_patched_files(self) -> List[str]:
        """
        Loads the list of patched files and their backups from the lock file
        
        Returns:
            List[str]: List of patched files and their backups
        """
        try:
            from commands.patch import PatchManager
            
            # Create PatchManager instance to access its methods
            patch_manager = PatchManager()
            
            # Use the _load_patched_files method from PatchManager that returns tuples (file, backup)
            patched_tuples = patch_manager._load_patched_files()
            
            # Convert tuples to a flat list of files for exclusion
            patched_files = []
            for file_path, backup_path in patched_tuples:
                if file_path:
                    patched_files.append(file_path)
                if backup_path and backup_path not in patched_files:  # Evitar duplicados
                    patched_files.append(backup_path)
            
            return patched_files
            
        except Exception as e:
            print(f"⚠️ Error loading patch file: {str(e)}")
            return []
        
    def _prepare_paths(self, direction: str) -> Tuple[str, str]:
        """
        Prepares the source and destination paths according to the direction
        
        Args:
            direction: Direction of synchronization ("from-remote" or "to-remote")
            
        Returns:
            Tuple[str, str]: Source and destination paths
        """
        # IMPORTANTE: Para rsync, mantener siempre la barra al final
        # Si termina con /, significa "copiar el contenido" no "crear el directorio"
        remote_path = self.remote_path
        
        # Asegurarse de que remote_path siempre termine con /
        if not remote_path.endswith('/'):
            remote_path += '/'
        
        if direction == "from-remote":
            # From remote to local
            source = f"{self.remote_host}:{remote_path}"
            # Asegurarse de que local_path termine con /
            dest = str(self.local_path) + '/' if not str(self.local_path).endswith('/') else str(self.local_path)
        else:
            # From local to remote
            # Asegurarse de que local_path termine con /
            source = str(self.local_path) + '/' if not str(self.local_path).endswith('/') else str(self.local_path)
            dest = f"{self.remote_host}:{remote_path}"
            
        return source, dest
        
    def check_remote_connection(self) -> bool:
        """
        Verifies the connection with the remote server
        
        Returns:
            bool: True if the connection is successful, False otherwise
        """
        print(f"🔄 Checking connection with remote server: {self.remote_host}")
        
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                return False
                
            # Verify access to remote path
            cmd = f"test -d {self.remote_path} && echo 'OK' || echo 'NOT_FOUND'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error checking remote path: {stderr}")
                return False
                
            if "OK" not in stdout:
                print(f"❌ Remote path does not exist: {self.remote_path}")
                return False
                
            print(f"✅ Connection verified successfully")
            return True
            
    def diff(self, dry_run: bool = True, show_all: bool = False, verbose: bool = False, only_patches: bool = False) -> bool:
        """
        Shows the differences between the remote server and the local environment.
        This method is always read-only and never makes changes,
        regardless of the value of the dry_run parameter.
        
        Args:
            dry_run: This parameter is kept for compatibility but is always ignored
            show_all: If True, shows all files without limit
            verbose: If True, shows detailed information
            only_patches: If True, shows only information related to patches
            
        Returns:
            bool: True if the operation was successful, False otherwise
        """
        if not only_patches:
            print(f"🔍 Comparing files between remote server and local environment...")
        
        # Verify connection
        if not self.check_remote_connection():
            return False
            
        # Prepare paths (always from remote for diff)
        source, dest = self._prepare_paths("from-remote")
        
        # DEPURACIÓN - Mostrar rutas exactas que se usarán
        print(f"DEBUG: Source path: {source}")
        print(f"DEBUG: Destination path: {dest}")
        
        # Get exclusions and verify they are a valid dictionary
        exclusions = self.exclusions.copy() if self.exclusions else {}
        if not exclusions:
            if not only_patches:
                print("ℹ️ No exclusions configured.")
        
        # Procesar exclusiones de parches (como en el método sync)
        try:
            # Verificar si necesitamos excluir archivos con parches según la configuración
            exclusions_mode = self.config.get("patches", "exclusions_mode", default="local-only")
            
            if exclusions_mode in ["local-only", "both-ways"]:
                # Cargar archivos con parches
                patched_files = self._load_patched_files()
                
                # Agregar cada archivo con parche a las exclusiones
                for i, patched_file in enumerate(patched_files):
                    if patched_file:
                        # Crear clave única y descriptiva para ver mejor en los logs
                        key = f"patched_{i}_{os.path.basename(patched_file)}"
                        exclusions[key] = patched_file
                
                if patched_files and not only_patches:
                    print(f"🔒 Protegiendo {len(patched_files)} archivos con parches durante la comparación")
        except Exception as e:
            if not only_patches:
                print(f"⚠️ Error procesando exclusiones de parches: {str(e)}")
                print("   Continuando sin exclusiones de parches")
        
        # Add protected files to exclusions so they don't appear in the diff
        if self.protected_files:
            if not only_patches:
                print(f"🛡️ Protecting {len(self.protected_files)} files during comparison")
            for i, file_pattern in enumerate(self.protected_files):
                exclusions[f"protected_{i}"] = file_pattern
        
        # Show number of exclusions
        if not only_patches:
            print(f"ℹ️ {len(exclusions)} exclusion patterns will be applied")
            
            # In verbose mode, show exclusion patterns
            if verbose:
                print("📋 Applying exclusion patterns:")
                for key, pattern in sorted(exclusions.items()):
                    print(f"   - {key}: {pattern}")
        
        # Rsync options to show differences
        options = [
            "-avzhnc",  # archive, verbose, compression, human-readable, dry-run, checksum
            "--itemize-changes",  # show detailed changes
            "--delete",  # delete files that don't exist in source
        ]
        
        # Add verbose for better error diagnosis
        if verbose:
            options.append("--verbose")
        
        # Run rsync in comparison mode
        # Always use dry_run=True because this method is only to show differences
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=exclusions,
            dry_run=True,  # Always in simulation mode for diff
            capture_output=True,  # Capture output to process it ourselves
            verbose=verbose  # Only show raw output in verbose mode
        )
        
        if not success:
            print("❌ Error showing differences")
            return False
            
        # If we only want patch information, we don't need to continue with normal analysis
        if only_patches:
            return self._analyze_patches(output, show_all, verbose)
        
        # Parse rsync output
        files_new = []       # New files in the server (>f....)
        files_modified = []  # Modified files (.s....)
        files_deleted = []   # Files that would be deleted (*deleting)
        files_directories = [] # Directories (.d....)
        
        # File limit to show per category
        limit = 0 if show_all else 100
        
        # Analyze each line of output
        for line in output.split('\n'):
            line = line.strip()
            
            # Ignore empty lines or without file information
            if not line or line.startswith('sent ') or line.startswith('receiving ') or line.startswith('total size'):
                continue
                
            # Extract change pattern and file name
            if line.startswith('>'):
                # New file in server
                pattern = line[:10]
                file = line[10:].strip()
                files_new.append((pattern, file))
            elif line.startswith('*deleting'):
                # File present locally but not in server
                file = line[10:].strip()
                files_deleted.append(('*deleting', file))
            elif line.startswith('.d'):
                # Directory
                pattern = line[:10]
                file = line[10:].strip()
                files_directories.append((pattern, file))
            elif '.s' in line[:5]:
                # Modified file
                pattern = line[:10]
                file = line[10:].strip()
                files_modified.append((pattern, file))
        
        # Create function to print files with limit
        def print_files(files, title, symbol, limit_count=limit):
            if not files:
                return
                
            count = len(files)
            print(f"\n{symbol} {title} ({count} items):")
            
            # Sort files by name
            files_sorted = sorted(files, key=lambda x: x[1].lower())
            
            # Show files up to limit or all if no limit
            for i, (pattern, file) in enumerate(files_sorted):
                if limit_count > 0 and i >= limit_count:
                    print(f"... and {count - limit_count} more files")
                    break
                
                # Process rsync pattern to determine file type
                file_type = "?"
                if pattern[1] == 'f':
                    file_type = "📄"  # Regular file
                elif pattern[1] == 'd':
                    file_type = "📁"  # Directory
                elif pattern[1] == 'L':
                    file_type = "🔗"  # Symlink
                    
                print(f"  {file_type} {file}")
        
        # Print different categories of changes
        print_files(files_new, "New files in server (would be downloaded)", "📥")
        print_files(files_modified, "Modified files (would be updated)", "🔄")
        print_files(files_deleted, "Files to delete (exists locally but not in server)", "🗑️")
        
        # Analyze if there are patches affected by the synchronization
        return self._analyze_patches(output, show_all, verbose, files_modified, files_deleted)
        
    def _analyze_patches(self, output: str = "", show_all: bool = False, verbose: bool = False, files_modified: list = None, files_deleted: list = None) -> bool:
        """
        Analyzes if the synchronization would affect registered patches
        
        Args:
            output: Rsync command output
            show_all: If True, shows all affected files
            verbose: If True, shows additional information
            files_modified: List of modified files
            files_deleted: List of files that would be deleted
            
        Returns:
            bool: True if operation can continue safely, False otherwise
        """
        # Try to load patched files from patch manager
        try:
            from commands.patch import PatchManager
            
            # Create patch manager instance to load patches
            patch_manager = PatchManager()
            
            # Check if there are patches
            if not patch_manager.lock_data.get("patches", {}):
                return True  # No patches to analyze
            
            # First collect all patched files
            patched_files = []
            patched_applied = []
            
            for file_path, info in patch_manager.lock_data.get("patches", {}).items():
                patched_files.append(file_path)
                if info.get("applied_date"):
                    patched_applied.append(file_path)
            
            # Check if we got a complete file list
            if files_modified is None or files_deleted is None:
                # We need to analyze the rsync output to find affected files
                files_modified = []
                files_deleted = []
                
                # Parse rsync output to get modified and deleted files
                for line in output.split('\n'):
                    line = line.strip()
                    
                    # Skip lines without file info
                    if not line or line.startswith('sent ') or line.startswith('receiving ') or line.startswith('total size'):
                        continue
                    
                    # Find modified files
                    if '.s' in line[:5]:
                        pattern = line[:10]
                        file = line[10:].strip()
                        files_modified.append((pattern, file))
                    
                    # Find deleted files
                    elif line.startswith('*deleting'):
                        file = line[10:].strip()
                        files_deleted.append(('*deleting', file))
            
            # Format files modified and deleted as plain list if needed
            if files_modified and isinstance(files_modified[0], tuple):
                files_modified_list = [file for _, file in files_modified]
            else:
                files_modified_list = files_modified
                
            if files_deleted and isinstance(files_deleted[0], tuple):
                files_deleted_list = [file for _, file in files_deleted]
            else:
                files_deleted_list = files_deleted
            
            # Find patched files affected by sync
            affected_modified = []
            affected_deleted = []
            
            for patch_file in patched_files:
                # Check if in modified files
                for mod_file in files_modified_list:
                    if patch_file == mod_file:
                        affected_modified.append(patch_file)
                
                # Check if in deleted files
                for del_file in files_deleted_list:
                    if patch_file == del_file:
                        affected_deleted.append(patch_file)
            
            # If we found no affected files
            if not affected_modified and not affected_deleted:
                # Only show message in verbose mode
                if verbose:
                    print("\n✅ No patched files would be affected by synchronization")
                return True
            
            # Show alert about affected patches
            print("\n⚠️ WARNING: This synchronization would affect patches:")
            
            # Show affected files
            if affected_modified:
                print(f"\n🔄 Modified patched files ({len(affected_modified)}):")
                for file in affected_modified:
                    # Get patch info
                    info = patch_manager.lock_data.get("patches", {}).get(file, {})
                    description = info.get("description", "No description")
                    status = "Applied" if file in patched_applied else "Registered"
                    print(f"  📄 {file}")
                    print(f"     • Description: {description}")
                    print(f"     • Status: {status}")
            
            if affected_deleted:
                print(f"\n🗑️ Deleted patched files ({len(affected_deleted)}):")
                for file in affected_deleted:
                    # Get patch info
                    info = patch_manager.lock_data.get("patches", {}).get(file, {})
                    description = info.get("description", "No description")
                    status = "Applied" if file in patched_applied else "Registered"
                    print(f"  📄 {file}")
                    print(f"     • Description: {description}")
                    print(f"     • Status: {status}")
            
            # Show recommendations
            print("\n⚠️ RECOMMENDATIONS:")
            print("   - If continuing with synchronization, patches would be overwritten")
            print("   - Use 'patch --list' to view details of all patches")
            print("   - After synchronization, apply patches again with 'patch-commit'")
            
            return True
            
        except Exception as e:
            if verbose:
                print(f"\n⚠️ Error analyzing patches: {str(e)}")
            return True
        
    def _check_protected_files(self, direction: str) -> bool:
        """
        Verifies if protected files would be affected by synchronization
        
        Args:
            direction: Direction of synchronization ("from-remote" or "to-remote")
            
        Returns:
            bool: True if it's safe to continue, False otherwise
        """
        # Get protected files list
        if not self.protected_files:
            return True
            
        print(f"🛡️ Checking {len(self.protected_files)} protected files...")
        
        # Prepare command to check file existence
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                print("❌ Error establishing SSH connection")
                return False
                
            # Build command to check all files
            check_script = []
            for pattern in self.protected_files:
                if pattern.startswith('/'):
                    # Absolute path, check directly
                    check_script.append(f"if [ -e \"{pattern}\" ]; then echo \"EXISTS {pattern}\"; fi")
                else:
                    # Relative path, build full path
                    check_script.append(f"if [ -e \"{self.remote_path}{pattern}\" ]; then echo \"EXISTS {pattern}\"; fi")
            
            # Execute remote check
            cmd = "; ".join(check_script)
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error checking protected files: {stderr}")
                return False
            
            # Process results
            existing_files = []
            for line in stdout.split('\n'):
                if line.startswith('EXISTS '):
                    file_path = line[7:]
                    existing_files.append(file_path)
            
            # Show results
            if existing_files:
                if direction == "from-remote":
                    print(f"🛡️ Found {len(existing_files)} protected files on the server that will be ignored:")
                else:  # to-remote
                    print(f"🛡️ Found {len(existing_files)} protected files on the server that will not be overwritten:")
                
                for file in existing_files:
                    print(f"   - {file}")
            else:
                print("✅ No protected files found in the destination")
            
            return True
        
    def _clean_excluded_files(self, direction: str) -> bool:
        """
        Limpia archivos que deberían haberse eliminado durante la sincronización
        pero que no se eliminaron debido al filtrado de rsync.
        NOTA: Esta función NO debe eliminar archivos excluidos intencionalmente.
        
        Args:
            direction: Direction of synchronization ("from-remote" or "to-remote")
            
        Returns:
            bool: True if the cleaning was successful, False otherwise
        """
        # Solo limpiar cuando la dirección es from-remote
        if direction != "from-remote":
            return True
            
        print("🔄 Verificando archivos a limpiar...")
        
        # Obtener la lista de archivos con parches para NUNCA eliminarlos
        patched_files = self._load_patched_files()
        patched_files_normalized = [os.path.normpath(pf) for pf in patched_files if pf]
        
        # CORRECCIÓN: No debemos eliminar archivos excluidos intencionalmente.
        # Los archivos excluidos son aquellos que queremos preservar localmente,
        # no los que queremos eliminar.
        
        # En lugar de eso, buscamos archivos que deberían eliminarse según
        # la sincronización y que no estén en las exclusiones
        
        # Crear una lista de patrones de exclusión para verificación más fácil
        exclusion_patterns = []
        for key, pattern in self.exclusions.items():
            if pattern:
                exclusion_patterns.append(pattern)
                
        # Crear una lista combinada de protecciones
        protected_patterns = exclusion_patterns + self.protected_files
        
        print("✅ Archivos excluidos y protegidos preservados")
        print("ℹ️ Lock file not found. A new one will be created.")
        return True
        
        # IMPORTANTE: Se ha desactivado la lógica anterior que eliminaba
        # los archivos excluidos, ya que esa lógica era incorrecta.
        # Los archivos excluidos deben preservarse, no eliminarse.
        
        # ------------------- CÓDIGO DESACTIVADO -------------------
        """
        # Para cada exclusión buscar archivos/directorios correspondientes para eliminar
        for key, pattern in self.exclusions.items():
            if not pattern:
                continue
                
            # Omitir patrones con comodines (necesitan manejo especial)
            if "*" in pattern or "?" in pattern or "[" in pattern:
                continue
                
            # Convertir patrón a ruta de directorio
            directory = os.path.normpath(os.path.join(self.local_path, pattern))
            
            # Verificar si este directorio existe
            if os.path.exists(directory):
                # PROTECCIÓN: Verificar que no sea un archivo con parche
                normalized_dir = os.path.normpath(directory)
                if normalized_dir in patched_files_normalized:
                    print(f"🛡️ No eliminando archivo con parche: {directory}")
                    continue
                    
                # No eliminar directorios protegidos
                is_protected = False
                for protected_pattern in self.protected_files:
                    if fnmatch.fnmatch(directory, protected_pattern):
                        is_protected = True
                        break
                        
                if is_protected:
                    print(f"🛡️ No eliminando directorio protegido: {directory}")
                    continue
                
                # Eliminar el directorio/archivo
                print(f"🗑️ Cleaning excluded: {directory}")
                
                try:
                    if os.path.isfile(directory):
                        os.unlink(directory)
                    elif os.path.isdir(directory):
                        shutil.rmtree(directory)
                except Exception as e:
                    print(f"   ⚠️ Error deleting {directory}: {str(e)}")
        """
        # --------------------------------------------------------
        
        print("✅ Finished cleaning excluded files")
        return True
        
    def sync(self, direction: str = "from-remote", dry_run: bool = False, clean: bool = True) -> bool:
        """
        Synchronizes files between environments
        
        Args:
            direction: Direction of synchronization ("from-remote" or "to-remote")
            dry_run: If True, only simulates synchronization without making changes
            clean: If True, verifies excluded files after synchronization
            
        Returns:
            bool: True if the synchronization was successful, False otherwise
        """
        if direction == "from-remote":
            print(f"🔄 Sincronizando archivos desde servidor remoto al entorno local...")
            print(f"   Origen: {self.remote_host}:{self.remote_path}")
            print(f"   Destino: {self.local_path}")
        else:
            print(f"🔄 Sincronizando archivos desde entorno local al servidor remoto...")
            print(f"   Origen: {self.local_path}")
            print(f"   Destino: {self.remote_host}:{self.remote_path}")
        
        # Verificar conexión
        if not self.check_remote_connection():
            return False
        
        # Preparar rutas de origen y destino
        source, dest = self._prepare_paths(direction)
        
        # Obtener exclusiones y verificar que sean un diccionario válido
        exclusions = self.exclusions.copy() if self.exclusions else {}
        if not exclusions:
            print("ℹ️ No hay exclusiones configuradas. Todos los archivos en el origen serán sincronizados.")
        else:
            print(f"🛡️ Se aplicarán {len(exclusions)} patrones de exclusión")
            print("   Los archivos excluidos NO serán sincronizados para preservar sus versiones locales")
        
        # Procesar exclusiones de parches
        try:
            # Verificar si necesitamos excluir archivos con parches según la configuración
            exclusions_mode = self.config.get("patches", "exclusions_mode", default="local-only")
            
            if (direction == "from-remote" and exclusions_mode in ["local-only", "both-ways"]) or \
               (direction == "to-remote" and exclusions_mode in ["remote-only", "both-ways"]):
                # Cargar archivos con parches
                patched_files = self._load_patched_files()
                
                # Agregar cada archivo con parche a las exclusiones
                for i, patched_file in enumerate(patched_files):
                    if patched_file:
                        # Crear clave única y descriptiva para ver mejor en los logs
                        key = f"patched_{i}_{os.path.basename(patched_file)}"
                        exclusions[key] = patched_file
                
                if patched_files:
                    print(f"🔒 Protegiendo {len(patched_files)} archivos con parches como configurado")
                    print("   Estos archivos NO se sincronizarán para evitar perder cambios")
        except Exception as e:
            print(f"⚠️ Error procesando exclusiones de parches: {str(e)}")
            print("   Continuando sin exclusiones de parches")
            
        # Agregar archivos protegidos a las exclusiones
        if self.protected_files:
            print(f"🛡️ Agregando {len(self.protected_files)} archivos protegidos a exclusiones")
            for i, file_pattern in enumerate(self.protected_files):
                exclusions[f"protected_{i}"] = file_pattern
            
            print("   Estos archivos NO se sincronizarán y se conservarán intactos")
                
            # Verificar archivos protegidos en destino si no es dry-run
            if not dry_run:
                self._check_protected_files(direction)
        
        # Mostrar número total de exclusiones
        print(f"ℹ️ Se aplicarán un total de {len(exclusions)} patrones de exclusión")
        
        # Opciones para rsync
        options = [
            "-avzh",  # archive, verbose, compression, human-readable
            "--delete",  # delete files that don't exist in source
        ]
        
        # Agregar --dry-run si estamos simulando
        if dry_run:
            options.append("--dry-run")
            print("🔍 Modo dry-run: No se realizarán cambios reales")
        
        # Ejecutar rsync
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=exclusions,
            dry_run=dry_run,
            capture_output=False  # Let it print directly to the console
        )
        
        if not success:
            print("❌ Error durante la sincronización")
            return False
        
        # Verificar exclusiones si es necesario
        if clean and not dry_run and direction == "from-remote":
            self._clean_excluded_files(direction)
            
        # Corregir configuración local si es necesario después de sincronización desde remoto
        if not dry_run and direction == "from-remote":
            self._fix_local_config()
            
        if dry_run:
            print("🔍 Prueba completada. No se realizaron cambios.")
        else:
            print("✅ Sincronización completada exitosamente.")
            
        return True
    
    def _fix_local_config(self):
        """
        Fixes local configuration after synchronization from remote
        
        This is needed when configuration elements in remote environment
        differ from local and need to be adjusted after syncing.
        Solo hace limpieza de caché, la configuración de media path debe hacerse
        explícitamente con el comando media-path.
        """
        print("🔧 Checking if local configuration needs adjustments...")
        
        # Check media URL
        media_config = self.config.config.get("media", {})
        if media_config:
            # Get URLs
            remote_url = self.config.get("urls", "remote", default="")
            local_url = self.config.get("urls", "local", default="")
            
            if remote_url and local_url and remote_url != local_url:
                print("ℹ️ URLs are different, media configuration might need update")
                print("💡 Use 'media-path' command to configure media URLs")
                print("   Example: python cli.py media-path")
        else:
            print("ℹ️ No media configuration found, skipping")
            
        # Clean cache
        try:
            from utils.wp_cli import flush_cache
            
            print("🧹 Cleaning local cache...")
            flush_cache(
                path=self.local_path,
                remote=False,
                use_ddev=True
            )
        except Exception as e:
            print(f"⚠️ Error cleaning cache: {str(e)}")
            print("   You may need to run 'wp cache flush' manually")
            
        print("✅ Local configuration adjustments completed")

def sync_files(direction: str = "from-remote", dry_run: bool = False, clean: bool = True, skip_full_backup: bool = False) -> bool:
    """
    Synchronizes files between environments
    
    Args:
        direction: Direction of synchronization ("from-remote" or "to-remote")
        dry_run: If True, only simulates synchronization without making changes
        clean: If True, cleans excluded files after synchronization
        skip_full_backup: If True, skips creating a full backup before synchronizing from remote
        
    Returns:
        bool: True if the synchronization was successful, False otherwise
    """
    # Crear sincronizador
    try:
        synchronizer = FileSynchronizer()
        
        # Crear backup completo si se sincroniza desde remoto (y no es dry-run o explícitamente omitido)
        if direction == "from-remote" and not dry_run and not skip_full_backup:
            print("📦 Creando backup completo antes de sincronizar archivos...")
            
            try:
                backup_path = create_full_backup()
                print(f"✅ Backup creado exitosamente: {backup_path}")
            except Exception as e:
                print(f"❌ ERROR: No se pudo crear el backup completo: {str(e)}")
                print("⚠️ ADVERTENCIA: Sincronizar sin backup puede causar pérdida de datos.")
                confirm = input("¿Desea continuar SIN backup? (escriba 'SI' para confirmar): ")
                if confirm.upper() != "SI":
                    print("Operación cancelada por el usuario.")
                    return False
                print("Continuando sincronización sin backup bajo su responsabilidad.")
        
        # Ejecutar sincronización
        return synchronizer.sync(direction=direction, dry_run=dry_run, clean=clean)
        
    except Exception as e:
        print(f"❌ Error durante la sincronización: {str(e)}")
        import traceback
        traceback.print_exc()
        return False 