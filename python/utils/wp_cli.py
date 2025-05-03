"""
Utilidades para interactuar con WP-CLI desde Python
"""

import os
import subprocess
import json
import shlex
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, Literal

from config_yaml import get_yaml_config, get_nested

def run_wp_cli(command: List[str], path: Union[str, Path], remote: bool = False, 
              remote_host: Optional[str] = None, remote_path: Optional[str] = None,
              use_ddev: bool = True, wp_path: Optional[str] = None,
              memory_limit: Optional[str] = None) -> Tuple[int, str, str]:
    """
    Ejecuta un comando de WP-CLI
    
    Args:
        command: Lista con el comando y sus argumentos
        path: Ruta al directorio de WordPress
        remote: Si es True, ejecuta el comando en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (si es None, se usa el valor de configuración)
        
    Returns:
        Tuple[int, str, str]: Código de salida, salida estándar, error estándar
    """
    # Obtener configuración y valor de memoria
    config = get_yaml_config()
    
    # Si no se especifica límite de memoria, usar el valor de configuración
    if memory_limit is None:
        memory_limit = config.get_wp_memory_limit()
    
    if not remote:
        # Comando local
        if use_ddev:
            # Usar ddev para ejecutar wp-cli
            wp_cmd_str = " ".join([f"'{arg}'" if ' ' in arg else arg for arg in command])
            
            # Obtener la ruta de WordPress dentro de DDEV desde la configuración
            ddev_wp_path = wp_path
            
            if not ddev_wp_path:
                # Intentar obtener la ruta del contenedor DDEV desde la configuración
                ddev_wp_path = get_nested(config, "ddev", "webroot")
                # Si no está en la configuración, usar la parte final de local_path
                if not ddev_wp_path:
                    local_path = get_nested(config, "ssh", "local_path", "")
                    # La ruta local típicamente termina en /app/public/ o similar
                    # Vamos a extraer solo la parte final para usarla en DDEV
                    if "/app/public" in local_path:
                        ddev_wp_path = "/var/www/html/app/public"
                    else:
                        # Si no podemos inferir la ruta, usar el valor predeterminado
                        ddev_wp_path = "/var/www/html"
            
            # Añadir límite de memoria al comando
            cmd = ["ddev", "exec", f"cd {ddev_wp_path} && php -d memory_limit={memory_limit} $(which wp) {wp_cmd_str}"]
            
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(path),
                    capture_output=True,
                    text=True,
                    check=False
                )
                return result.returncode, result.stdout, result.stderr
            except Exception as e:
                return 1, "", str(e)
        else:
            # Ejecutar wp-cli directamente
            wp_cmd = ["wp"] + command
            
            try:
                # Intentar configurar el entorno con el límite de memoria
                env = os.environ.copy()
                env["PHP_MEMORY_LIMIT"] = memory_limit
                
                result = subprocess.run(
                    wp_cmd,
                    cwd=str(path),
                    capture_output=True,
                    text=True,
                    check=False,
                    env=env
                )
                return result.returncode, result.stdout, result.stderr
            except Exception as e:
                return 1, "", str(e)
    else:
        # Comando remoto
        if not remote_host or not remote_path:
            return 1, "", "Se requiere host y ruta remotos para ejecutar WP-CLI en el servidor"
            
        # Construir comando SSH con aumento de límite de memoria para PHP
        wp_cmd = ["wp"] + command
        wp_cmd_str = " ".join([f"'{arg}'" if ' ' in arg else arg for arg in wp_cmd])
        
        # Añadir el límite de memoria a los comandos PHP
        php_memory_cmd = f"php -d memory_limit={memory_limit}"
        ssh_cmd = ["ssh", remote_host, f"cd {remote_path} && {php_memory_cmd} $(which wp) {' '.join(command)}"]
        
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return 1, "", str(e)

def is_plugin_installed(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                       remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                       use_ddev: bool = True, wp_path: Optional[str] = None,
                       memory_limit: Optional[str] = None) -> bool:
    """
    Verifica si un plugin está instalado
    
    Args:
        plugin_slug: Slug del plugin
        path: Ruta al directorio de WordPress
        remote: Si es True, verifica en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        bool: True si el plugin está instalado, False en caso contrario
    """
    cmd = ["plugin", "list", "--status=inactive,active", "--format=json"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        return False
        
    try:
        plugins = json.loads(stdout)
        for plugin in plugins:
            if plugin.get("name", "").lower() == plugin_slug.lower():
                return True
        return False
    except Exception as e:
        return False

def get_plugin_status(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                     remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                     use_ddev: bool = True, wp_path: Optional[str] = None,
                     memory_limit: Optional[str] = None) -> Optional[str]:
    """
    Obtiene el estado de un plugin (active, inactive, not installed)
    
    Args:
        plugin_slug: Slug del plugin
        path: Ruta al directorio de WordPress
        remote: Si es True, verifica en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        Optional[str]: Estado del plugin ("active", "inactive", None si no está instalado)
    """
    cmd = ["plugin", "list", "--format=json"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        return None
        
    try:
        plugins = json.loads(stdout)
        for plugin in plugins:
            if plugin.get("name", "").lower() == plugin_slug.lower():
                return plugin.get("status", "")
        return None
    except Exception as e:
        return None

def install_plugin(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                  remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                  use_ddev: bool = True, wp_path: Optional[str] = None, 
                  use_url: bool = False, memory_limit: Optional[str] = None) -> bool:
    """
    Instala un plugin de WordPress
    
    Args:
        plugin_slug: Slug del plugin o URL si use_url=True
        path: Ruta al directorio de WordPress
        remote: Si es True, instala en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        use_url: Si es True, plugin_slug se interpreta como una URL
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        bool: True si el plugin se instaló correctamente, False en caso contrario
    """
    cmd = ["plugin", "install", plugin_slug]
    
    if use_url:
        cmd.append("--force")
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"Error al instalar el plugin: {stderr}")
        return False
        
    # Verificar que el plugin se instaló correctamente
    if "successfully installed the plugin" in stdout or "Plugin already installed" in stdout:
        return True
    
    return False

def activate_plugin(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                   remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                   use_ddev: bool = True, wp_path: Optional[str] = None,
                   memory_limit: Optional[str] = None) -> bool:
    """
    Activa un plugin de WordPress
    
    Args:
        plugin_slug: Slug del plugin
        path: Ruta al directorio de WordPress
        remote: Si es True, activa en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        bool: True si el plugin se activó correctamente, False en caso contrario
    """
    # Verificar el estado actual del plugin
    status = get_plugin_status(plugin_slug, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    # Si ya está activo, no hacer nada
    if status == "active":
        return True
    
    # Si no está instalado, no podemos activarlo
    if status is None:
        return False
        
    # Activar el plugin
    cmd = ["plugin", "activate", plugin_slug]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"Error al activar el plugin: {stderr}")
        return False
        
    # Verificar que el plugin se activó correctamente
    if "Plugin 'wp-original-media-path' activated" in stdout or "Success:" in stdout or "Plugin '" in stdout:
        return True
    
    return False

def deactivate_plugin(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                     remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                     use_ddev: bool = True, wp_path: Optional[str] = None,
                     memory_limit: Optional[str] = None) -> bool:
    """
    Desactiva un plugin de WordPress
    
    Args:
        plugin_slug: Slug del plugin
        path: Ruta al directorio de WordPress
        remote: Si es True, desactiva en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        bool: True si el plugin se desactivó correctamente, False en caso contrario
    """
    # Verificar el estado actual del plugin
    status = get_plugin_status(plugin_slug, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    # Si ya está inactivo o no está instalado, no hacer nada
    if status != "active":
        return True
        
    # Desactivar el plugin
    cmd = ["plugin", "deactivate", plugin_slug]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"Error al desactivar el plugin: {stderr}")
        return False
        
    return True

def get_plugin_info(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                   remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                   use_ddev: bool = True, wp_path: Optional[str] = None,
                   memory_limit: Optional[str] = None) -> Dict[str, Any]:
    """
    Obtiene información sobre un plugin
    
    Args:
        plugin_slug: Slug del plugin
        path: Ruta al directorio de WordPress
        remote: Si es True, obtiene información del servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        Dict[str, Any]: Información del plugin
    """
    cmd = ["plugin", "get", plugin_slug, "--format=json"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"⚠️ Error al obtener información del plugin: {stderr}")
        return {}
        
    try:
        plugin_info = json.loads(stdout)
        return plugin_info
    except json.JSONDecodeError:
        print(f"⚠️ Error al parsear la información del plugin")
        return {}

def get_theme_info(theme_slug: str, path: Union[str, Path], remote: bool = False,
                  remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                  use_ddev: bool = True, wp_path: Optional[str] = None,
                  memory_limit: Optional[str] = None) -> Dict[str, Any]:
    """
    Obtiene información sobre un tema
    
    Args:
        theme_slug: Slug del tema
        path: Ruta al directorio de WordPress
        remote: Si es True, obtiene información del servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        Dict[str, Any]: Información del tema
    """
    cmd = ["theme", "get", theme_slug, "--format=json"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"⚠️ Error al obtener información del tema: {stderr}")
        return {}
        
    try:
        theme_info = json.loads(stdout)
        return theme_info
    except json.JSONDecodeError:
        print(f"⚠️ Error al parsear la información del tema")
        return {}
        
def get_item_version_from_path(file_path: str, path: Union[str, Path], remote: bool = False,
                             remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                             use_ddev: bool = True, wp_path: Optional[str] = None, 
                             memory_limit: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Obtiene información sobre el tipo de elemento (plugin/tema) y versión desde una ruta de archivo
    
    Args:
        file_path: Ruta relativa al archivo (desde la raíz del sitio)
        path: Ruta base al directorio de WordPress
        remote: Si es True, verifica en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        Tuple[str, str, str]: Tipo de elemento ("plugin", "theme"), slug, versión
    """
    # Analizar la ruta para determinar si es un plugin o tema
    item_type = "other"
    item_slug = ""
    
    if '/plugins/' in file_path:
        item_type = "plugin"
        # El slug del plugin es el directorio principal dentro de plugins/
        parts = file_path.split('/')
        for i, part in enumerate(parts):
            if part == "plugins" and i + 1 < len(parts):
                item_slug = parts[i + 1]
                break
    elif '/themes/' in file_path:
        item_type = "theme"
        # El slug del tema es el directorio principal dentro de themes/
        parts = file_path.split('/')
        for i, part in enumerate(parts):
            if part == "themes" and i + 1 < len(parts):
                item_slug = parts[i + 1]
                break
                
    # Si no se ha podido determinar el tipo o el slug, no se puede obtener versión
    if item_type == "other" or not item_slug:
        return item_type, item_slug, ""
    
    # Obtener versión usando WP-CLI
    try:
        if item_type == "plugin":
            cmd = ["plugin", "get", item_slug, "--format=json"]
            code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
            
            if code != 0 or not stdout.strip():
                # Si hay error, mucha información en el log
                if "Fatal error: Allowed memory size" in stderr:
                    # Aumentar memoria disponible
                    enlarged_memory = "1024M"
                    if memory_limit:
                        try:
                            # Intentar aumentar el límite especificado
                            current_limit = int(memory_limit.replace("M", "").replace("G", "000").replace("K", ""))
                            enlarged_memory = str(current_limit * 2) + "M"
                        except:
                            enlarged_memory = "1024M"
                            
                    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, enlarged_memory)
                    
                    if code != 0 or not stdout.strip():
                        if "Fatal error: Allowed memory size" in stderr:
                            raise Exception(f"Error de memoria al obtener información del plugin: {stderr}")
                        else:
                            return item_type, item_slug, ""
                else:
                    return item_type, item_slug, ""
                
            try:
                data = json.loads(stdout)
                return item_type, item_slug, data.get("version", "")
            except:
                return item_type, item_slug, ""
                
        elif item_type == "theme":
            cmd = ["theme", "get", item_slug, "--format=json"]
            code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
            
            if code != 0 or not stdout.strip():
                # Si hay error, mucha información en el log
                if "Fatal error: Allowed memory size" in stderr:
                    # Aumentar memoria disponible
                    enlarged_memory = "1024M"
                    if memory_limit:
                        try:
                            # Intentar aumentar el límite especificado
                            current_limit = int(memory_limit.replace("M", "").replace("G", "000").replace("K", ""))
                            enlarged_memory = str(current_limit * 2) + "M"
                        except:
                            enlarged_memory = "1024M"
                            
                    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, enlarged_memory)
                    
                    if code != 0 or not stdout.strip():
                        if "Fatal error: Allowed memory size" in stderr:
                            raise Exception(f"Error de memoria al obtener información del tema: {stderr}")
                        else:
                            return item_type, item_slug, ""
                else:
                    return item_type, item_slug, ""
                
            try:
                data = json.loads(stdout)
                return item_type, item_slug, data.get("version", "")
            except:
                return item_type, item_slug, ""
                
    except Exception as e:
        if isinstance(e, Exception):
            raise e
        return item_type, item_slug, ""
        
    return item_type, item_slug, ""

def flush_cache(path: Union[str, Path], remote: bool = False,
               remote_host: Optional[str] = None, remote_path: Optional[str] = None,
               use_ddev: bool = True, wp_path: Optional[str] = None,
               memory_limit: Optional[str] = None) -> bool:
    """
    Limpia la caché de WordPress
    
    Args:
        path: Ruta al directorio de WordPress
        remote: Si es True, ejecuta el comando en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        bool: True si se limpió correctamente, False en caso contrario
    """
    cmd = ["cache", "flush"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"⚠️ Error al limpiar la caché: {stderr}")
        return False
        
    print("✅ Caché de WordPress limpiada correctamente")
    return True

def update_option(option_name: str, option_value: str, path: Union[str, Path], 
                 remote: bool = False, remote_host: Optional[str] = None, 
                 remote_path: Optional[str] = None, use_ddev: bool = True, 
                 wp_path: Optional[str] = None, memory_limit: Optional[str] = None) -> bool:
    """
    Actualiza una opción de WordPress
    
    Args:
        option_name: Nombre de la opción
        option_value: Valor de la opción
        path: Ruta al directorio de WordPress
        remote: Si es True, ejecuta el comando en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        bool: True si se actualizó correctamente, False en caso contrario
    """
    cmd = ["option", "update", option_name, option_value]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"⚠️ Error al actualizar la opción {option_name}: {stderr}")
        return False
        
    print(f"✅ Opción {option_name} actualizada correctamente")
    return True

def update_media_path(new_path: str, path: Union[str, Path], 
                     remote: bool = False, remote_host: Optional[str] = None, 
                     remote_path: Optional[str] = None, use_ddev: bool = True,
                     wp_path: Optional[str] = None, memory_limit: Optional[str] = None) -> bool:
    """
    Actualiza la ruta de los medios en WordPress
    
    Args:
        new_path: Nueva ruta para los archivos de medios
        path: Ruta al directorio de WordPress
        remote: Si es True, ejecuta el comando en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        bool: True si se actualizó correctamente, False en caso contrario
    """
    # Actualizar la opción upload_path
    upload_success = update_option("upload_path", new_path, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if not upload_success:
        return False
        
    # Limpiar la caché para que los cambios surtan efecto
    cache_success = flush_cache(path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    return upload_success and cache_success 

def is_wordpress_installed(path: Union[str, Path], remote: bool = False,
                         remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                         use_ddev: bool = True, wp_path: Optional[str] = None,
                         memory_limit: Optional[str] = None) -> bool:
    """
    Verifica si WordPress está correctamente instalado
    
    Args:
        path: Ruta al directorio de WordPress
        remote: Si es True, verifica en el servidor remoto
        remote_host: Host remoto (solo si remote=True)
        remote_path: Ruta remota (solo si remote=True)
        use_ddev: Si es True (predeterminado), utiliza ddev en entorno local
        wp_path: Ruta específica de WordPress dentro del contenedor (opcional)
        memory_limit: Límite de memoria para PHP (opcional)
        
    Returns:
        bool: True si WordPress está instalado, False en caso contrario
    """
    # Verificar existencia de archivos básicos
    cmd = ["core", "is-installed"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    return code == 0 