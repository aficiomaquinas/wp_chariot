"""
Módulo de configuración para wp_deploy

Este módulo se encarga de cargar y gestionar la configuración
desde archivos .env y variables de entorno.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

class Config:
    """
    Clase para manejar la configuración del sistema.
    Carga variables desde archivos .env y proporciona acceso a ellas.
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Inicializa el objeto de configuración.
        
        Args:
            project_root: Ruta raíz del proyecto. Si es None, se detecta automáticamente.
        """
        # Definir el directorio raíz del proyecto
        if project_root is None:
            # Intentar detectar la raíz del proyecto
            self.project_root = self._detect_project_root()
        else:
            self.project_root = project_root
            
        # Directorio de herramientas de despliegue
        self.deploy_tools_dir = self.project_root / "deploy-tools"
        
        # Configuración predeterminada
        self.config: Dict[str, Any] = {
            # Configuración SSH
            "REMOTE_SSH": "server",
            "REMOTE_PATH": "/home/user/webapps/wordpress/",
            "LOCAL_PATH": str(self.project_root / "app" / "public"),
            
            # Configuración de seguridad
            "PRODUCTION_SAFETY": "enabled",
            
            # Configuración de base de datos
            "REMOTE_DB_NAME": "",
            "REMOTE_DB_USER": "",
            "REMOTE_DB_PASS": "",
            "REMOTE_DB_HOST": "localhost",
            
            # URLs
            "REMOTE_URL": "https://example.com",
            "LOCAL_URL": "https://example.ddev.site",
        }
        
        # Cargar la configuración
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
        Carga la configuración desde los archivos .env
        """
        # Cargar deploy-tools.env primero
        deploy_tools_env = self.deploy_tools_dir / "deploy-tools.env"
        if deploy_tools_env.exists():
            print(f"📝 Cargando configuración desde {deploy_tools_env}")
            load_dotenv(deploy_tools_env)
            
            # Verificar si se especifica una ruta personalizada para el archivo .env
            project_env_path = os.getenv("PROJECT_ENV_PATH")
            if project_env_path:
                env_path = self.deploy_tools_dir / project_env_path
                if env_path.exists():
                    print(f"📝 Cargando configuración desde {env_path}")
                    load_dotenv(env_path)
                else:
                    print(f"⚠️ No se encontró el archivo .env especificado: {env_path}")
        
        # Intentar cargar .env en la raíz del proyecto
        project_env = self.project_root / ".env"
        if project_env.exists():
            print(f"📝 Cargando configuración desde {project_env}")
            load_dotenv(project_env)
            
        # Actualizar la configuración con las variables de entorno cargadas
        for key in self.config.keys():
            env_value = os.getenv(key)
            if env_value is not None:
                self.config[key] = env_value
                
    def get(self, key: str, default: Any = None) -> Any:
        """
        Obtiene un valor de configuración.
        
        Args:
            key: Clave de configuración
            default: Valor predeterminado si no se encuentra la clave
            
        Returns:
            El valor de configuración o el valor predeterminado
        """
        return self.config.get(key, default)
        
    def __getitem__(self, key: str) -> Any:
        """
        Permite acceder a la configuración mediante la sintaxis de índice:
        config["REMOTE_SSH"]
        
        Args:
            key: Clave de configuración
            
        Returns:
            El valor de configuración
            
        Raises:
            KeyError: Si la clave no existe
        """
        if key in self.config:
            return self.config[key]
        raise KeyError(f"Clave de configuración no encontrada: {key}")
        
    def display(self):
        """
        Muestra la configuración actual
        """
        print("\n🔧 Configuración cargada:")
        for key, value in self.config.items():
            # Ocultar contraseñas
            if "PASS" in key or "PASSWORD" in key:
                display_value = "********"
            else:
                display_value = value
            print(f"   - {key}: {display_value}")
        print()
        
# Instancia global de configuración
_config: Optional[Config] = None

def get_config() -> Config:
    """
    Obtiene la instancia global de configuración.
    Si aún no existe, la crea.
    
    Returns:
        Config: Instancia de configuración
    """
    global _config
    if _config is None:
        _config = Config()
    return _config 