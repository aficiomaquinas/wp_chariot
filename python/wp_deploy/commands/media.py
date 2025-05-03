#!/usr/bin/env python3
"""
Módulo para la configuración de rutas de medios en WordPress

Este módulo proporciona funciones para configurar la ruta de uploads en WordPress
mediante el plugin 'WP Original Media Path'.
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple, Dict

from wp_deploy.utils.wp_cli import (
    run_wp_cli,
    update_option,
    flush_cache,
    is_plugin_installed,
    install_plugin,
    activate_plugin,
    is_wordpress_installed
)
from wp_deploy.config_yaml import get_yaml_config, get_nested

# Plugin requerido para medios originales
MEDIA_PLUGIN = "wp-original-media-path"
MEDIA_PLUGIN_URL = "https://downloads.wordpress.org/plugin/wp-original-media-path.latest-stable.zip"

# Límite de memoria para WP-CLI
WP_CLI_MEMORY_LIMIT = "256M"

def configure_media_path(
    media_url: Optional[str] = None,
    expert_mode: bool = False,
    media_path: Optional[str] = None,
    remote: bool = False,
    verbose: bool = False
) -> bool:
    """
    Configura la ruta de medios en WordPress
    
    Args:
        media_url: IGNORADO - Se usa el valor de config.yaml
        expert_mode: Indica si se debe activar el modo experto (desde config.yaml)
        media_path: IGNORADO - Se usa el valor de config.yaml
        remote: Aplicar en el servidor remoto en lugar de localmente
        verbose: Mostrar información detallada
        
    Returns:
        bool: True si la configuración se completó correctamente, False en caso contrario
    """
    # Cargar configuración
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    
    # Obtener ruta dentro del contenedor DDEV (valor obligatorio desde config.yaml)
    ddev_wp_path = get_nested(config, "ddev", "webroot")
    if not ddev_wp_path and not remote:
        print("⚠️ Error: No se ha configurado ddev.webroot en config.yaml")
        print("   Esta configuración es obligatoria para usar DDEV.")
        print("   Ejemplo: webroot: \"/var/www/html/app/public\"")
        return False
    
    # SIEMPRE obtener los valores desde la configuración
    media_url = get_nested(config, "media", "url", "")
    if not media_url:
        print("⚠️ No se encontró URL de medios en la configuración")
        print("   Configure 'media.url' en config.yaml")
        print("   Ejemplo: url: \"https://media.tudominio.com\"")
        print("   Sin URL de medios, se usará la URL predeterminada de WordPress")
    
    # Usar el modo experto según la configuración
    expert_mode = get_nested(config, "media", "expert_mode", False)
    media_path = None
    if expert_mode:
        media_path = get_nested(config, "media", "path", "")
        if not media_path:
            print("⚠️ Modo experto activado pero no se configuró ruta física")
            print("   Configure 'media.path' en config.yaml")
            print("   Ejemplo: path: \"/ruta/absoluta/a/uploads\"")
    
    # Si estamos en entorno local, verificar y asegurar que DDEV esté en ejecución
    if not remote:
        try:
            print("🔍 Verificando estado de DDEV...")
            ddev_status = subprocess.run(
                ["ddev", "status"],
                cwd=local_path.parent,
                capture_output=True,
                text=True
            )
            if "running" not in ddev_status.stdout.lower():
                print("⚠️ DDEV no está en ejecución. Iniciando DDEV automáticamente...")
                try:
                    start_process = subprocess.run(
                        ["ddev", "start"],
                        cwd=local_path.parent,
                        capture_output=True,
                        text=True
                    )
                    if start_process.returncode == 0:
                        print("✅ DDEV iniciado correctamente")
                    else:
                        print(f"⚠️ No se pudo iniciar DDEV: {start_process.stderr}")
                        print("   Continuando de todos modos, pero pueden producirse errores...")
                except Exception as e:
                    print(f"⚠️ Error al intentar iniciar DDEV: {str(e)}")
                    print("   Continuando con la instalación...")
        except Exception as e:
            print(f"⚠️ No se pudo verificar el estado de DDEV: {str(e)}")
            print("   Continuando con la instalación...")
    
    # Verificación de WordPress antes de continuar
    print(f"🔍 Verificando instalación de WordPress...")
    if verbose:
        print(f"   Ruta local: {local_path}")
        print(f"   Ruta en contenedor DDEV: {ddev_wp_path}")
    
    if not is_wordpress_installed(local_path, remote, remote_host, remote_path, True, ddev_wp_path):
        print("⚠️ No se pudo verificar una instalación funcional de WordPress")
        print("   Verifique que WordPress está correctamente instalado y configurado")
        print("   Continuando de todos modos, pero pueden ocurrir errores...")
    
    print(f"🔍 Configurando WordPress para usar rutas de medios personalizadas")
    if media_url:
        print(f"   URL de medios: {media_url}")
    if expert_mode and media_path:
        print(f"   Ruta física: {media_path} (Modo Experto)")
    
    # 1. Verificar si el plugin ya está instalado
    print(f"📋 Verificando plugin '{MEDIA_PLUGIN}'...")
    
    if is_plugin_installed(MEDIA_PLUGIN, local_path, remote, remote_host, remote_path, True, ddev_wp_path):
        print(f"✅ Plugin '{MEDIA_PLUGIN}' ya está instalado")
        
        # Actualizar el plugin si ya está instalado
        print(f"🔄 Actualizando plugin '{MEDIA_PLUGIN}'...")
        update_result = install_plugin(
            MEDIA_PLUGIN, 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path
        )
        
        if update_result:
            print(f"✅ Plugin '{MEDIA_PLUGIN}' actualizado correctamente")
        else:
            print(f"ℹ️ No fue necesario actualizar '{MEDIA_PLUGIN}' o ocurrió un error")
    else:
        print(f"📦 Instalando plugin '{MEDIA_PLUGIN}'...")
        
        # Mostrar comando que se ejecutaría para depuración
        if not remote:
            debug_cmd = f"ddev wp plugin install {MEDIA_PLUGIN}"
        else:
            debug_cmd = f"ssh {remote_host} 'cd {remote_path} && wp plugin install {MEDIA_PLUGIN}'"
        print(f"🔍 Comando a ejecutar: {debug_cmd}")
        
        install_result = install_plugin(
            MEDIA_PLUGIN, 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path
        )
        
        if not install_result:
            print(f"❌ Error al instalar el plugin '{MEDIA_PLUGIN}'")
            print(f"🔄 Intentando instalar desde URL: {MEDIA_PLUGIN_URL}")
            
            # Mostrar comando que se ejecutaría para depuración
            if not remote:
                debug_cmd = f"ddev wp plugin install {MEDIA_PLUGIN_URL}"
            else:
                debug_cmd = f"ssh {remote_host} 'cd {remote_path} && wp plugin install {MEDIA_PLUGIN_URL}'"
            print(f"🔍 Comando a ejecutar: {debug_cmd}")
            
            # Intentar instalar desde URL
            install_result = install_plugin(
                MEDIA_PLUGIN_URL, 
                local_path, 
                remote, 
                remote_host, 
                remote_path,
                True,
                ddev_wp_path,
                True  # Usar URL
            )
            
            if not install_result:
                print(f"❌ Error al instalar el plugin '{MEDIA_PLUGIN}'")
                print("ℹ️ Posibles soluciones:")
                print("   1. Verifica que WordPress está correctamente instalado")
                print("   2. Asegúrate de que DDEV está en ejecución (ddev start)")
                print("   3. Comprueba la conectividad a Internet")
                print("   4. Intenta instalar el plugin manualmente:")
                if not remote:
                    print(f"      $ ddev wp plugin install {MEDIA_PLUGIN_URL}")
                else:
                    print(f"      $ ssh {remote_host} 'cd {remote_path} && wp plugin install {MEDIA_PLUGIN_URL}'")
                
                print("⚠️ Continuando sin el plugin. La configuración de medios puede no funcionar correctamente.")
                return False
            else:
                print(f"✅ Plugin '{MEDIA_PLUGIN}' instalado correctamente")
        else:
            print(f"✅ Plugin '{MEDIA_PLUGIN}' instalado correctamente")
    
    # 2. Activar el plugin
    print(f"🔌 Activando plugin '{MEDIA_PLUGIN}'...")
    # Intentar activar hasta 3 veces con pequeñas pausas
    activate_success = False
    for attempt in range(3):
        activate_result = activate_plugin(
            MEDIA_PLUGIN, 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT  # Usar límite de memoria explícito
        )
        
        if activate_result:
            activate_success = True
            print(f"✅ Plugin '{MEDIA_PLUGIN}' activado correctamente")
            break
        else:
            if attempt < 2:  # No mostrar en último intento
                print(f"⚠️ Intento {attempt+1}/3 fallido. Reintentando...")
                time.sleep(2)  # Esperar un poco antes de reintentar
    
    if not activate_success:
        print(f"⚠️ No se pudo activar el plugin '{MEDIA_PLUGIN}'. Continuando de todos modos...")
        print(f"   Es posible que necesites activarlo manualmente desde el panel de WordPress.")
        print(f"   O revisar los errores utilizando 'wp plugin activate {MEDIA_PLUGIN} --debug'")
    
    # 3. Obtener configuración actual
    if verbose:
        print("🔍 Configuración actual:")
        cmd = ["option", "get", "upload_url_path", "--skip-themes", "--skip-plugins"]
        code, stdout, stderr = run_wp_cli(
            cmd, 
            local_path, 
            remote, 
            remote_host, 
            remote_path, 
            True, 
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
        current_url = stdout.strip() if code == 0 and stdout.strip() else "No configurado"
        
        # Limpiar mensajes de error de memoria en la salida
        if "Failed to set memory limit" in current_url:
            current_url = current_url.split("\n")[-1].strip()
        
        cmd = ["option", "get", "owmp_path", "--skip-themes", "--skip-plugins"]
        code, stdout, stderr = run_wp_cli(
            cmd, 
            local_path, 
            remote, 
            remote_host, 
            remote_path, 
            True, 
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
        current_path = stdout.strip() if code == 0 and stdout.strip() else "No configurado"
        
        # Limpiar mensajes de error de memoria en la salida
        if "Failed to set memory limit" in current_path:
            current_path = current_path.split("\n")[-1].strip()
        
        cmd = ["option", "get", "owmp_expert_bool", "--skip-themes", "--skip-plugins"]
        code, stdout, stderr = run_wp_cli(
            cmd, 
            local_path, 
            remote, 
            remote_host, 
            remote_path, 
            True, 
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
        current_expert = stdout.strip() if code == 0 and stdout.strip() else "0"
        
        # Limpiar mensajes de error de memoria en la salida
        if "Failed to set memory limit" in current_expert:
            current_expert = current_expert.split("\n")[-1].strip()
            
        print(f"   URL actual: {current_url}")
        print(f"   Ruta física: {current_path}")
        print(f"   Modo experto: {'Activado' if current_expert == '1' else 'Desactivado'}")
    
    # 4. Configurar URL de medios
    if media_url:
        print(f"🔧 Configurando URL de medios a: {media_url}")
        update_option(
            "upload_url_path", 
            media_url, 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
    
    # 5. Configurar modo experto si se solicitó
    if expert_mode:
        print("⚙️ Activando modo experto para ruta personalizada")
        update_option(
            "owmp_expert_bool", 
            "1", 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
        
        if media_path:
            print(f"🔧 Configurando ruta física a: {media_path}")
            update_option(
                "owmp_path", 
                media_path, 
                local_path, 
                remote, 
                remote_host, 
                remote_path,
                True,
                ddev_wp_path,
                memory_limit=WP_CLI_MEMORY_LIMIT
            )
    else:
        # Asegurar que el modo experto esté desactivado
        update_option(
            "owmp_expert_bool", 
            "0", 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
    
    # 6. Limpiar caché
    print("🧹 Limpiando caché de WordPress...")
    flush_cache(
        local_path, 
        remote, 
        remote_host, 
        remote_path,
        True,
        ddev_wp_path,
        memory_limit=WP_CLI_MEMORY_LIMIT
    )
    
    # 7. Verificar configuración final
    print("\n📊 Configuración final:")
    
    # URL de medios
    cmd = ["option", "get", "upload_url_path", "--skip-themes", "--skip-plugins"]
    code, stdout, stderr = run_wp_cli(
        cmd, 
        local_path, 
        remote, 
        remote_host, 
        remote_path, 
        True, 
        ddev_wp_path,
        memory_limit=WP_CLI_MEMORY_LIMIT
    )
    final_url = stdout.strip() if code == 0 and stdout.strip() else "No configurado (usando valor predeterminado)"
    
    # Limpiar mensajes de error de memoria en la salida
    if "Failed to set memory limit" in final_url:
        final_url = final_url.split("\n")[-1].strip()
    
    # Ruta física
    cmd = ["option", "get", "owmp_path", "--skip-themes", "--skip-plugins"]
    code, stdout, stderr = run_wp_cli(
        cmd, 
        local_path, 
        remote, 
        remote_host, 
        remote_path, 
        True, 
        ddev_wp_path,
        memory_limit=WP_CLI_MEMORY_LIMIT
    )
    final_path = stdout.strip() if code == 0 and stdout.strip() else "No configurado (usando valor predeterminado)"
    
    # Limpiar mensajes de error de memoria en la salida
    if "Failed to set memory limit" in final_path:
        final_path = final_path.split("\n")[-1].strip()
    
    # Modo experto
    cmd = ["option", "get", "owmp_expert_bool", "--skip-themes", "--skip-plugins"]
    code, stdout, stderr = run_wp_cli(
        cmd, 
        local_path, 
        remote, 
        remote_host, 
        remote_path, 
        True, 
        ddev_wp_path,
        memory_limit=WP_CLI_MEMORY_LIMIT
    )
    final_expert = "Activado" if code == 0 and stdout.strip() == "1" else "Desactivado"
    
    # Limpiar mensajes de error de memoria en la salida
    if "Failed to set memory limit" in stdout:
        final_expert = "Activado" if stdout.split("\n")[-1].strip() == "1" else "Desactivado"
    
    print(f"   URL de medios: {final_url}")
    print(f"   Ruta física: {final_path}")
    print(f"   Modo experto: {final_expert}")
    
    print("\n✅ Configuración completada correctamente")
    print("🔍 Los archivos de medios se buscarán ahora en la ruta configurada")
    if not remote:
        print("\n💡 Recordatorio: Después de sincronizar la base de datos de producción")
        print("   a desarrollo, ejecute este script para configurar las rutas de medios")
        print("   y asegúrese de que los archivos de medios estén disponibles localmente.")
    
    return True 