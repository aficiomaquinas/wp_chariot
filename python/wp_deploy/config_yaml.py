"""
Módulo de configuración basado en YAML para wp_deploy

Este módulo se encarga de cargar y gestionar la configuración
desde archivos YAML, con soporte para estructuras de datos complejas.
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
import copy
import re

from wp_deploy.utils.filesystem import get_default_exclusions, get_protected_files

class YAMLConfig:
    """
    Clase para manejar la configuración del sistema usando YAML.
    Carga variables desde archivos YAML y proporciona acceso a ellas.
    """
    
    def __init__(self, project_root: Optional[Path] = None, verbose: bool = False):
        """
        Inicializa el objeto de configuración.
        
        Args:
            project_root: Ruta raíz del proyecto. Si es None, se detecta automáticamente.
            verbose: Si es True, muestra mensajes de depuración detallados
        """
        # Definir el directorio raíz del proyecto
        if project_root is None:
            # Intentar detectar la raíz del proyecto
            self.project_root = self._detect_project_root()
        else:
            self.project_root = project_root
            
        # Guarda el nivel de verbosidad
        self.verbose = verbose
            
        # Directorio de herramientas de despliegue
        self.deploy_tools_dir = self.project_root / "deploy-tools"
        
        # Valores predeterminados para la configuración
        self.config: Dict[str, Any] = {
            # Configuración SSH
            "ssh": {
                "remote_host": "example-server",
                "remote_path": "/home/user/webapps/example/",
                "local_path": str(self.project_root / "app" / "public"),
            },
            
            # Configuración de seguridad
            "security": {
                "production_safety": "enabled",
            },
            
            # Configuración de base de datos
            "database": {
                "remote": {
                    "name": "",
                    "user": "",
                    "password": "",
                    "host": "localhost",
                }
            },
            
            # URLs
            "urls": {
                "remote": "https://example.com",
                "local": "https://example.ddev.site",
            },
            
            # Configuración de medios
            "media": {
                "url": "",
                "expert_mode": False,
                "path": "../media",
            },
            
            # Exclusiones para sincronización
            "exclusions": get_default_exclusions(),
            
            # Archivos protegidos
            "protected_files": get_protected_files()
        }
        
        # Cargar configuración desde archivos YAML
        self._load_config()
        
    def _detect_project_root(self) -> Path:
        """
        Detecta la raíz del proyecto WordPress.
        Busca hacia arriba en el árbol de directorios hasta encontrar 
        un directorio que contenga una carpeta deploy-tools.
        
        Returns:
            Path: Ruta a la raíz del proyecto
        """
        current_dir = Path.cwd()
        
        # Buscar hacia arriba en el árbol de directorios
        while current_dir != current_dir.parent:
            # Verificar si el directorio actual contiene deploy-tools
            if (current_dir / "deploy-tools").exists():
                return current_dir
                
            # Subir un nivel
            current_dir = current_dir.parent
            
        # Si no se encuentra, usar el directorio actual
        print("⚠️ No se pudo detectar la raíz del proyecto. Usando directorio actual.")
        return Path.cwd()
        
    def _load_config(self):
        """
        Carga la configuración desde archivos YAML.
        Primero carga la configuración global, luego la configuración del proyecto.
        """
        # Variable para rastrear si se cargó algún archivo de configuración
        config_loaded = False
        
        # Cargar configuración global
        global_config_file = self.deploy_tools_dir / "python" / "config.yaml"
        if global_config_file.exists():
            if self.verbose:
                print(f"📝 Cargando configuración desde {global_config_file}")
            self._load_yaml_file(global_config_file)
            config_loaded = True
            
        # Cargar configuración del proyecto
        project_config_file = self.project_root / "wp-deploy.yaml"
        if project_config_file.exists():
            if self.verbose:
                print(f"📝 Cargando configuración desde {project_config_file}")
            self._load_yaml_file(project_config_file)
            config_loaded = True
        
        # Si no se cargó ninguna configuración, mostrar advertencia
        if not config_loaded:
            # Esto no es un error crítico porque tenemos valores predeterminados
            print("⚠️ No se encontró ningún archivo de configuración válido.")
            print(f"   Buscando en:")
            print(f"   - {global_config_file}")
            print(f"   - {project_config_file}")
            print(f"   Se usarán valores predeterminados.")
            
        # Cargar variables de entorno para compatibilidad con el sistema anterior
        self._load_env_vars()
        
    def _load_yaml_file(self, file_path: Path):
        """
        Carga un archivo YAML y actualiza la configuración
        
        Args:
            file_path: Ruta al archivo YAML
        """
        try:
            with open(file_path, 'r') as file:
                if self.verbose:
                    print(f"📝 Leyendo archivo YAML: {file_path}")
                yaml_data = yaml.safe_load(file)
                
            if yaml_data and isinstance(yaml_data, dict):
                # Mostrar claves principales para depuración
                if self.verbose:
                    print(f"📝 Claves encontradas en {file_path}: {', '.join(yaml_data.keys())}")
                
                # Si hay una sección de database, mostrar su contenido
                if 'database' in yaml_data and self.verbose:
                    db_config = yaml_data['database']
                    print(f"📝 Configuración de base de datos encontrada:")
                    if 'remote' in db_config:
                        remote_db = db_config['remote']
                        print(f"   - DB Host: {remote_db.get('host', 'no configurado')}")
                        print(f"   - DB Name: {remote_db.get('name', 'no configurado')}")
                        print(f"   - DB User: {remote_db.get('user', 'no configurado')}")
                        print(f"   - DB Pass: {'*'*len(remote_db.get('password', '')) if 'password' in remote_db else 'no configurado'}")
                
                # Actualizar la configuración de forma recursiva
                self._update_dict_recursive(self.config, yaml_data)
                
                # Verificar que se actualizaron los valores
                if 'database' in yaml_data and 'remote' in yaml_data['database'] and self.verbose:
                    print(f"📝 Valores de base de datos después de actualizar:")
                    remote_db = self.config['database']['remote']
                    print(f"   - DB Host: {remote_db.get('host', 'no configurado')}")
                    print(f"   - DB Name: {remote_db.get('name', 'no configurado')}")
                    print(f"   - DB User: {remote_db.get('user', 'no configurado')}")
                    print(f"   - DB Pass: {'*'*len(remote_db.get('password', '')) if 'password' in remote_db else 'no configurado'}")
        except Exception as e:
            print(f"❌ Error al cargar archivo YAML {file_path}: {str(e)}")
            import traceback
            traceback.print_exc()
            
    def _update_dict_recursive(self, target: Dict, source: Dict):
        """
        Actualiza un diccionario de forma recursiva
        
        Args:
            target: Diccionario destino
            source: Diccionario origen con nuevos valores
        """
        for key, value in source.items():
            # Si ambos valores son diccionarios, actualizar recursivamente
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._update_dict_recursive(target[key], value)
            else:
                # En caso contrario, sobrescribir el valor
                target[key] = copy.deepcopy(value)
                
    def _load_env_vars(self):
        """
        Carga variables de entorno para mantener compatibilidad con el sistema anterior
        """
        # Mapeo de variables de entorno a la nueva estructura
        env_mapping = {
            "REMOTE_SSH": ("ssh", "remote_host"),
            "REMOTE_SSH_ALIAS": ("ssh", "remote_host"),  # Alias alternativo
            "REMOTE_PATH": ("ssh", "remote_path"),
            "LOCAL_PATH": ("ssh", "local_path"),
            "PRODUCTION_SAFETY": ("security", "production_safety"),
            "REMOTE_DB_NAME": ("database", "remote", "name"),
            "REMOTE_DB_USER": ("database", "remote", "user"),
            "REMOTE_DB_PASS": ("database", "remote", "password"),
            "REMOTE_DB_HOST": ("database", "remote", "host"),
            "REMOTE_URL": ("urls", "remote"),
            "LOCAL_URL": ("urls", "local"),
            "WP_MEDIA_URL": ("media", "url"),
            "WP_MEDIA_EXPERT": ("media", "expert_mode"),
            "WP_MEDIA_PATH": ("media", "path"),
        }
        
        # Intentar cargar .env en la raíz del proyecto
        env_file = self.project_root / ".env"
        if env_file.exists():
            if self.verbose:
                print(f"📝 Cargando variables de entorno desde {env_file} (compatibilidad)")
            env_vars = self._parse_env_file(env_file)
            
            # Aplicar las variables de entorno según el mapeo
            for env_name, config_path in env_mapping.items():
                if env_name in env_vars:
                    value = env_vars[env_name]
                    
                    # Convertir valores booleanos
                    if env_name == "WP_MEDIA_EXPERT":
                        if value in ("1", "true", "yes", "on"):
                            value = True
                        elif value in ("0", "false", "no", "off"):
                            value = False
                    
                    self._set_nested_value(self.config, config_path, value)
                    
    def _parse_env_file(self, file_path: Path) -> Dict[str, str]:
        """
        Parsea un archivo .env y devuelve un diccionario con las variables
        
        Args:
            file_path: Ruta al archivo .env
            
        Returns:
            Dict[str, str]: Diccionario con las variables de entorno
        """
        env_vars = {}
        
        try:
            with open(file_path, 'r') as file:
                for line in file:
                    line = line.strip()
                    # Ignorar líneas vacías y comentarios
                    if not line or line.startswith('#'):
                        continue
                        
                    # Dividir en clave y valor
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Eliminar comillas si existen
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                            
                        env_vars[key] = value
                        
        except Exception as e:
            if self.verbose:
                print(f"❌ Error al parsear archivo .env {file_path}: {str(e)}")
            
        return env_vars
        
    def _set_nested_value(self, target: Dict, path: tuple, value: Any):
        """
        Establece un valor en un diccionario anidado según una ruta
        
        Args:
            target: Diccionario destino
            path: Tupla con la ruta de claves para acceder al valor
            value: Valor a establecer
        """
        current = target
        for i, key in enumerate(path):
            if i == len(path) - 1:
                # Último elemento: establecer el valor
                current[key] = value
            else:
                # Elemento intermedio: asegurarse de que existe el diccionario
                if key not in current or not isinstance(current[key], dict):
                    current[key] = {}
                current = current[key]
                
    def get(self, *path: str, default: Any = None) -> Any:
        """
        Obtiene un valor de configuración según una ruta de claves
        
        Args:
            *path: Ruta de claves para acceder al valor
            default: Valor predeterminado si no se encuentra la ruta
            
        Returns:
            El valor de configuración o el valor predeterminado
        """
        current = self.config
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current
        
    def get_exclusions(self) -> Dict[str, str]:
        """
        Obtiene el diccionario de exclusiones para rsync
        
        Returns:
            Dict[str, str]: Diccionario de exclusiones (clave -> patrón)
        """
        # Obtener exclusiones y asegurarse de que sea un diccionario
        raw_exclusions = self.config.get("exclusions", {}) or {}
        
        if not isinstance(raw_exclusions, dict):
            print(f"⚠️ Advertencia: Las exclusiones no son un diccionario válido. Usando exclusiones predeterminadas.")
            return get_default_exclusions()
            
        # Si no hay exclusiones configuradas, usar las predeterminadas
        if not raw_exclusions:
            print(f"ℹ️ No hay exclusiones configuradas. Usando exclusiones predeterminadas.")
            return get_default_exclusions()
        
        # Procesar exclusiones, eliminando las desactivadas (False)
        exclusions = {}
        for key, value in raw_exclusions.items():
            if value is not False:  # Permitir desactivar exclusiones estableciéndolas a False
                exclusions[key] = value
                
        # Si todas las exclusiones fueron desactivadas, usar las predeterminadas
        if not exclusions:
            print(f"⚠️ Todas las exclusiones fueron desactivadas. Usando exclusiones predeterminadas.")
            return get_default_exclusions()
                
        return exclusions
        
    def get_protected_files(self) -> List[str]:
        """
        Obtiene la lista de archivos protegidos
        
        Returns:
            List[str]: Lista de patrones de archivos protegidos
        """
        return self.config.get("protected_files", [])
        
    def get_media_config(self) -> Dict[str, Any]:
        """
        Obtiene la configuración de medios
        
        Returns:
            Dict[str, Any]: Configuración de medios
        """
        return self.config.get("media", {})
        
    def display(self):
        """
        Muestra la configuración actual de forma estructurada
        """
        print("\n🔧 Configuración cargada:")
        self._display_dict(self.config)
        print()
        
    def _display_dict(self, data: Dict, indent: int = 1):
        """
        Muestra un diccionario de forma estructurada
        
        Args:
            data: Diccionario a mostrar
            indent: Nivel de indentación
        """
        for key, value in data.items():
            # Ocultar contraseñas y valores sensibles (los valores reales se usan internamente)
            # NOTA IMPORTANTE: Por seguridad, se muestran valores de ejemplo en lugar de las credenciales reales
            if "password" in key.lower() or "pass" in key.lower():
                display_value = "********"
            # Ocultar credenciales de base de datos para mayor seguridad
            elif key == "name" and isinstance(data.get("password"), str):
                display_value = "nombre_db_remota"
            elif key == "user" and isinstance(data.get("password"), str):
                display_value = "usuario_db_remota"
            elif key == "host" and isinstance(data.get("password"), str):
                # Mantener el host visible ya que no es sensible
                display_value = value
            elif isinstance(value, dict):
                print(f"{'   ' * indent}- {key}:")
                self._display_dict(value, indent + 1)
                continue
            else:
                display_value = value
                
            print(f"{'   ' * indent}- {key}: {display_value}")
            
    def save_default_config(self, output_path: Path):
        """
        Guarda la configuración predeterminada en un archivo YAML
        
        Args:
            output_path: Ruta donde guardar el archivo
        """
        try:
            with open(output_path, 'w') as file:
                yaml.dump(self.config, file, default_flow_style=False, sort_keys=False)
            print(f"✅ Configuración predeterminada guardada en {output_path}")
        except Exception as e:
            print(f"❌ Error al guardar configuración: {str(e)}")
            
    def generate_template(self, output_path: Path):
        """
        Genera un archivo de plantilla con comentarios explicativos
        
        Args:
            output_path: Ruta donde guardar el archivo
        """
        # Copiar la plantilla desde el directorio de templates
        template_path = self.deploy_tools_dir / "python" / "templates" / "ejemplo.yaml"
        if template_path.exists():
            try:
                import shutil
                shutil.copy2(template_path, output_path)
                print(f"✅ Plantilla de configuración generada en {output_path}")
            except Exception as e:
                print(f"❌ Error al generar plantilla: {str(e)}")
        else:
            if self.verbose:
                print(f"❌ No se encontró el archivo de plantilla: {template_path}")
            self.save_default_config(output_path)

# Instancia global de configuración
_config: Optional[YAMLConfig] = None

def get_yaml_config(verbose: bool = False) -> YAMLConfig:
    """
    Obtiene la instancia global de configuración YAML.
    Si aún no existe, la crea.
    
    Args:
        verbose: Si es True, muestra mensajes de depuración detallados
    
    Returns:
        YAMLConfig: Instancia de configuración
    """
    global _config
    if _config is None:
        _config = YAMLConfig(verbose=verbose)
    return _config

def create_default_config(verbose: bool = False):
    """
    Crea un archivo de configuración YAML predeterminado
    
    Args:
        verbose: Si es True, muestra mensajes de depuración detallados
    """
    config = YAMLConfig(verbose=verbose)
    output_path = Path.cwd() / "wp-deploy.yaml"
    config.save_default_config(output_path)
    
def generate_template_config(verbose: bool = False):
    """
    Genera un archivo de plantilla YAML con comentarios explicativos
    
    Args:
        verbose: Si es True, muestra mensajes de depuración detallados
    """
    config = YAMLConfig(verbose=verbose)
    output_path = Path.cwd() / "wp-deploy.yaml"
    config.generate_template(output_path)

def get_nested(config_or_dict: Any, section: str, key: str, default: Any = None) -> Any:
    """
    Accede a un valor en una configuración anidada
    
    Args:
        config_or_dict: Configuración (YAMLConfig o Dict)
        section: Sección principal
        key: Clave dentro de la sección
        default: Valor por defecto
        
    Returns:
        Any: Valor encontrado o valor por defecto
    """
    # Si es un objeto YAMLConfig, usar su método get()
    if isinstance(config_or_dict, YAMLConfig):
        return config_or_dict.get(section, key, default=default)
        
    # Si es un diccionario, acceder directamente
    if not isinstance(config_or_dict, dict) or section not in config_or_dict:
        return default
        
    section_dict = config_or_dict[section]
    if not isinstance(section_dict, dict) or key not in section_dict:
        return default
        
    return section_dict[key] 