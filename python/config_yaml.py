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

class YAMLConfig:
    """
    Clase para gestionar configuración basada en YAML, con soporte para múltiples sitios
    """
    
    def __init__(self, verbose=False):
        """
        Inicializa configuración desde archivo YAML
        
        Args:
            verbose (bool): Activar modo detallado
        """
        self.verbose = verbose
        self.config = {}
        self.sites = {}
        self.current_site = None
        self.default_site = None
        
        # Detectar directorio del proyecto y de deploy-tools
        self.detect_project_roots()
        
        # Cargar configuración
        self.load_config()
        
        # Detectar y cargar configuración multi-sitio
        self.load_sites_config()
        
        # Seleccionar automáticamente el sitio por defecto si existe
        if self.default_site and self.default_site in self.sites:
            self.set_current_site(self.default_site)
            if self.verbose:
                print(f"✅ Sitio por defecto seleccionado automáticamente: {self.default_site}")
        
    def detect_project_roots(self):
        """
        Detecta la estructura de directorios del proyecto y de deploy-tools
        """
        # Detectar deploy-tools
        current_file = Path(__file__).resolve()
        # config_yaml.py -> python -> deploy-tools
        self.deploy_tools_dir = current_file.parent.parent
        
        # Si estamos ejecutando desde dentro de deploy-tools
        if "deploy-tools" in str(self.deploy_tools_dir):
            # El directorio del proyecto es el padre de deploy-tools
            self.project_root = self.deploy_tools_dir.parent
        else:
            # En caso de que el paquete se instale como biblioteca y no esté en la estructura deploy-tools
            # Usar el directorio actual como raíz del proyecto
            self.project_root = Path.cwd()
        
        if self.verbose:
            print(f"Detectado directorio de proyecto: {self.project_root}")
            print(f"Detectado directorio de deploy-tools: {self.deploy_tools_dir}")

    def load_config(self):
        """
        Carga la configuración desde archivos YAML
        """
        # Configuración global (dentro de deploy-tools)
        global_config_file = self.deploy_tools_dir / "python" / "config.yaml"
        
        # Configuración de proyecto (en la raíz del proyecto)
        project_config_file = self.project_root / "wp-deploy.yaml"
        
        # Inicializar configuración vacía
        self.config = {}
        
        # Cargar configuración global si existe
        if global_config_file.exists():
            try:
                with open(global_config_file, 'r') as f:
                    global_config = yaml.safe_load(f) or {}
                    # Establecer la configuración global
                    self.config = global_config
                if self.verbose:
                    print(f"Configuración global cargada desde: {global_config_file}")
            except Exception as e:
                print(f"Error al cargar configuración global: {str(e)}")
                
        # Cargar configuración del proyecto si existe
        if project_config_file.exists():
            try:
                with open(project_config_file, 'r') as f:
                    project_config = yaml.safe_load(f) or {}
                    # Fusionar con la configuración existente
                    self.merge_config(project_config)
                if self.verbose:
                    print(f"Configuración de proyecto cargada desde: {project_config_file}")
            except Exception as e:
                print(f"Error al cargar configuración de proyecto: {str(e)}")
    
    def load_sites_config(self):
        """
        Carga la configuración de múltiples sitios
        """
        sites_config_file = self.deploy_tools_dir / "python" / "sites.yaml"
        
        if sites_config_file.exists():
            try:
                with open(sites_config_file, 'r') as f:
                    sites_config = yaml.safe_load(f) or {}
                    
                # Extraer listado de sitios
                self.sites = sites_config.get("sites", {})
                self.default_site = sites_config.get("default", None)
                
                if self.verbose:
                    print(f"Configuración de sitios cargada: {len(self.sites)} sitios encontrados")
                    if self.default_site:
                        print(f"Sitio por defecto: {self.default_site}")
            except Exception as e:
                print(f"Error al cargar configuración de sitios: {str(e)}")
    
    def set_current_site(self, site_alias):
        """
        Establece el sitio actual a usar
        
        Args:
            site_alias: Alias del sitio a usar
            
        Returns:
            bool: True si el sitio existe y se estableció correctamente
        """
        if site_alias not in self.sites:
            print(f"❌ Error: Sitio '{site_alias}' no encontrado en la configuración")
            return False
        
        # Guardar el nombre del sitio actual
        self.current_site = site_alias
        
        # Cargar la configuración del sitio
        site_config = self.sites[site_alias]
        
        # Resetear la configuración actual a un diccionario vacío
        self.config = {}
        
        # Cargar configuración global
        global_config_file = self.deploy_tools_dir / "python" / "config.yaml"
        if global_config_file.exists():
            try:
                with open(global_config_file, 'r') as f:
                    global_config = yaml.safe_load(f) or {}
                    self.config = global_config
            except Exception:
                pass
        
        # Aplicar la configuración específica del sitio
        self.merge_config(site_config)
        
        if self.verbose:
            print(f"✅ Sitio actual establecido a: {site_alias}")
        
        return True
    
    def get_available_sites(self):
        """
        Obtiene la lista de sitios disponibles
        
        Returns:
            dict: Diccionario con los sitios disponibles
        """
        return self.sites
    
    def get_default_site(self):
        """
        Obtiene el sitio por defecto
        
        Returns:
            str: Alias del sitio por defecto o None si no hay
        """
        return self.default_site
    
    def select_site(self, site_alias=None):
        """
        Selecciona un sitio para usar
        
        Args:
            site_alias: Alias del sitio a usar (opcional)
            
        Returns:
            bool: True si el sitio se seleccionó correctamente
        """
        # Si no se especifica un sitio, intentar determinar automáticamente
        if not site_alias:
            # Si solo hay un sitio, usarlo
            if len(self.sites) == 1:
                site_alias = list(self.sites.keys())[0]
                if self.verbose:
                    print(f"ℹ️ Sitio único seleccionado automáticamente: {site_alias}")
            # Si hay más de uno y hay uno por defecto, usar ese
            elif self.default_site and self.default_site in self.sites:
                site_alias = self.default_site
                if self.verbose:
                    print(f"ℹ️ Sitio por defecto seleccionado: {site_alias}")
            # Si no hay un sitio por defecto y hay múltiples sitios, error
            elif len(self.sites) > 1:
                print("❌ Error: Múltiples sitios disponibles. Especifica uno con --site ALIAS")
                print("   Sitios disponibles:")
                for alias in self.sites.keys():
                    default_mark = " (por defecto)" if alias == self.default_site else ""
                    print(f"   - {alias}{default_mark}")
                return False
            # Si no hay sitios configurados, continuar con la configuración actual
            else:
                if self.verbose:
                    print("ℹ️ No hay sitios configurados. Usando configuración actual.")
                return True
        
        # Intentar establecer el sitio seleccionado
        if site_alias:
            return self.set_current_site(site_alias)
        
        return True
    
    def create_sites_config(self, default_site=None):
        """
        Crea un archivo de configuración de sitios vacío
        
        Args:
            default_site: Sitio por defecto (opcional)
            
        Returns:
            bool: True si se creó correctamente
        """
        sites_config_file = self.deploy_tools_dir / "python" / "sites.yaml"
        
        # Plantilla inicial
        template = {
            "default": default_site,
            "sites": {}
        }
        
        # Si ya hay sitios configurados, mantenerlos
        if hasattr(self, 'sites') and self.sites:
            template["sites"] = self.sites
        
        # Escribir configuración
        try:
            with open(sites_config_file, 'w') as f:
                yaml.dump(template, f, default_flow_style=False, sort_keys=False)
            print(f"✅ Archivo de configuración de sitios creado: {sites_config_file}")
            return True
        except Exception as e:
            print(f"❌ Error al crear archivo de configuración de sitios: {str(e)}")
            return False
    
    def add_site(self, alias, config=None, is_default=False):
        """
        Añade un nuevo sitio a la configuración
        
        Args:
            alias: Alias del sitio
            config: Configuración del sitio (opcional)
            is_default: Si es el sitio por defecto
            
        Returns:
            bool: True si se añadió correctamente
        """
        sites_config_file = self.deploy_tools_dir / "python" / "sites.yaml"
        
        # Cargar configuración actual
        self.load_sites_config()
        
        # Si no se proporciona una configuración, usar la actual
        if not config:
            config = self.config
        
        # Añadir/actualizar el sitio
        self.sites[alias] = config
        
        # Actualizar sitio por defecto si es necesario
        if is_default:
            self.default_site = alias
        
        # Guardar configuración
        template = {
            "default": self.default_site,
            "sites": self.sites
        }
        
        try:
            with open(sites_config_file, 'w') as f:
                yaml.dump(template, f, default_flow_style=False, sort_keys=False)
            print(f"✅ Sitio '{alias}' añadido/actualizado correctamente")
            
            if is_default:
                print(f"✅ '{alias}' establecido como sitio por defecto")
                
            return True
        except Exception as e:
            print(f"❌ Error al guardar configuración de sitios: {str(e)}")
            return False
    
    def remove_site(self, alias):
        """
        Elimina un sitio de la configuración
        
        Args:
            alias: Alias del sitio a eliminar
            
        Returns:
            bool: True si se eliminó correctamente
        """
        sites_config_file = self.deploy_tools_dir / "python" / "sites.yaml"
        
        # Cargar configuración actual
        self.load_sites_config()
        
        # Verificar si el sitio existe
        if alias not in self.sites:
            print(f"❌ Error: Sitio '{alias}' no encontrado")
            return False
        
        # Eliminar el sitio
        del self.sites[alias]
        
        # Si era el sitio por defecto, quitar esa configuración
        if self.default_site == alias:
            self.default_site = None
            print(f"ℹ️ El sitio eliminado era el sitio por defecto. Ya no hay sitio por defecto.")
        
        # Guardar configuración
        template = {
            "default": self.default_site,
            "sites": self.sites
        }
        
        try:
            with open(sites_config_file, 'w') as f:
                yaml.dump(template, f, default_flow_style=False, sort_keys=False)
            print(f"✅ Sitio '{alias}' eliminado correctamente")
            return True
        except Exception as e:
            print(f"❌ Error al guardar configuración de sitios: {str(e)}")
            return False

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
                # Caso especial para la sección de seguridad, asegurando que la configuración del sitio tenga precedencia
                if key == 'security' and 'production_safety' in value:
                    # Preservar valor de production_safety directamente del sitio antes de hacer merge recursivo
                    production_safety_value = value.get('production_safety')
                    
                    # Hacer merge recursivo normal
                    self._update_dict_recursive(target[key], value)
                    
                    # Aplicar el valor del sitio con precedencia
                    target[key]['production_safety'] = production_safety_value
                    
                    if self.verbose:
                        print(f"Configuración de seguridad actualizada: production_safety={production_safety_value}")
                else:
                    # Para otras secciones, hacer merge recursivo normal
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
        
    def get_strict(self, *path: str) -> Any:
        """
        Obtiene un valor de configuración siguiendo el principio fail-fast
        
        A diferencia de get(), esta función lanza una excepción si la ruta no existe,
        en lugar de retornar un valor por defecto.
        
        Args:
            *path: Ruta de claves para acceder al valor
            
        Returns:
            Any: El valor de configuración
            
        Raises:
            ValueError: Si la ruta no existe en la configuración
        """
        current = self.config
        for i, key in enumerate(path):
            if not isinstance(current, dict):
                path_str = ' -> '.join(path[:i])
                raise ValueError(f"La ruta de configuración '{path_str}' no es un diccionario")
            
            if key not in current:
                path_str = ' -> '.join(path[:i+1])
                raise ValueError(f"La clave '{key}' no existe en la ruta '{path_str}'")
            
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
            print(f"⚠️ Advertencia: Las exclusiones no son un diccionario válido.")
            return {}
            
        # Si no hay exclusiones configuradas, usar un diccionario vacío
        if not raw_exclusions:
            print(f"ℹ️ No hay exclusiones configuradas.")
            return {}
        
        # Procesar exclusiones, eliminando las desactivadas (False)
        exclusions = {}
        for key, value in raw_exclusions.items():
            if value is not False:  # Permitir desactivar exclusiones estableciéndolas a False
                exclusions[key] = value
                
        return exclusions
        
    def get_protected_files(self) -> List[str]:
        """
        Obtiene la lista de archivos protegidos que no deben eliminarse
        
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
            if "password" in key.lower() or "pass" in key.lower():
                display_value = "***********"
            # Ocultar credenciales de base de datos para mayor seguridad
            elif key == "name" and isinstance(data.get("password"), str):
                display_value = "***********"
            elif key == "user" and isinstance(data.get("password"), str):
                display_value = "***********"
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
            
    def get_wp_memory_limit(self) -> str:
        """
        Obtiene el límite de memoria para PHP de WP-CLI
        
        Siguiendo el principio "fail fast", esta función retorna exactamente
        lo que hay en la configuración sin intentar arreglar valores inválidos.
        Si el valor no existe en la configuración, se falla explícitamente.
        
        Returns:
            str: Límite de memoria para PHP
            
        Raises:
            ValueError: Si el valor no existe en la configuración
        """
        # Verificar si existe la sección wp_cli
        if "wp_cli" not in self.config:
            raise ValueError("La sección 'wp_cli' no está definida en la configuración")
        
        # Verificar si existe la clave memory_limit
        if "memory_limit" not in self.config["wp_cli"]:
            raise ValueError("La clave 'memory_limit' no está definida en la sección 'wp_cli'")
        
        # Retornar exactamente lo que hay en la configuración, sin intentar arreglarlo
        return self.config["wp_cli"]["memory_limit"]

    def merge_config(self, config):
        """
        Fusiona la configuración proporcionada con la configuración actual
        
        Args:
            config: Diccionario con la configuración a fusionar
        """
        if not config:
            return
            
        self._update_dict_recursive(self.config, config)

# Función global para obtener la configuración
_config_instance = None

def get_yaml_config(verbose=False):
    """
    Obtiene la instancia única de la configuración
    
    Args:
        verbose: Si es True, muestra información adicional
        
    Returns:
        YAMLConfig: Instancia de la configuración
    """
    global _config_instance
    
    if not _config_instance:
        _config_instance = YAMLConfig(verbose=verbose)
        
    return _config_instance

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