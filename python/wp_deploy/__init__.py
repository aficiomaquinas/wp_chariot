"""
Herramientas de despliegue para WordPress
"""

__version__ = "1.0.0"

# Estos imports solo están disponibles cuando el paquete está instalado
# Se manejan en cada módulo individual para permitir importaciones relativas
try:
    from wp_deploy.config_yaml import get_yaml_config
    from wp_deploy.commands import sync, db, patch
    from wp_deploy.utils import filesystem, ssh, wp_cli
except ImportError:
    # En modo de desarrollo, estos imports pueden fallar
    pass

__all__ = ["config_yaml", "commands", "utils"]

__author__ = "Victor Gonzalez" 