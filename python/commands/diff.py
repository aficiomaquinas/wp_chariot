"""
Módulo para mostrar diferencias entre entornos

Este módulo proporciona funciones para mostrar las diferencias de archivos
entre un servidor remoto y el entorno local.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from config_yaml import get_yaml_config
from utils.ssh import SSHClient, run_rsync

# Importar la clase FileSynchronizer después para evitar importación circular
import commands.sync as sync_module

class DiffCommand:
    """
    Clase para comandos específicos de diferencias
    """
    
    def __init__(self):
        """
        Inicializa el objeto de diferencias
        """
        self.synchronizer = sync_module.FileSynchronizer()
        
    def show_diff(self, show_all: bool = False, verbose: bool = False, only_patches: bool = False) -> bool:
        """
        Muestra las diferencias entre el servidor remoto y el entorno local.
        Este método siempre es de solo lectura y nunca realiza cambios.
        
        Args:
            show_all: Si es True, muestra todos los archivos sin límite
            verbose: Si es True, muestra información detallada
            only_patches: Si es True, muestra solo información relacionada con parches
            
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        # Siempre usamos dry_run=True porque este comando es solo para mostrar diferencias
        return self.synchronizer.diff(dry_run=True, show_all=show_all, verbose=verbose, only_patches=only_patches)

def show_diff(show_all: bool = False, verbose: bool = False, only_patches: bool = False) -> bool:
    """
    Muestra las diferencias entre el servidor remoto y el entorno local.
    Esta función siempre es de solo lectura y nunca realiza cambios.
    
    Args:
        show_all: Si es True, muestra todos los archivos sin límite
        verbose: Si es True, muestra información detallada
        only_patches: Si es True, muestra solo información relacionada con parches
        
    Returns:
        bool: True si la operación fue exitosa, False en caso contrario
    """
    diff_cmd = DiffCommand()
    return diff_cmd.show_diff(show_all=show_all, verbose=verbose, only_patches=only_patches) 