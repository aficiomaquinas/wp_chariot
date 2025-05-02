#!/usr/bin/env python3
"""
Script para configurar la ruta de uploads en WordPress

Este script instala y configura el plugin 'WP Original Media Path' y establece
la ruta de subidas de WordPress para trabajar con medios externos.
"""

import os
import sys
import argparse
import time
from pathlib import Path
import subprocess

# Añadir directorio padre al path para poder importar wp_deploy
script_dir = Path(__file__).resolve().parent
project_dir = script_dir.parent
sys.path.insert(0, str(project_dir))

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

def main():
    """
    Función principal del script
    """
    parser = argparse.ArgumentParser(
        description="Instala y configura wp-original-media-path para URLs personalizadas de medios"
    )
    
    parser.add_argument(
        "--url", 
        help="URL del directorio de uploads (ej: https://media.tudominio.com)"
    )
    
    parser.add_argument(
        "--expert", action="store_true",
        help="Activar modo experto para configurar ruta física personalizada"
    )
    
    parser.add_argument(
        "--path", 
        help="Ruta física para uploads (solo con --expert)"
    )
    
    parser.add_argument(
        "--remote", action="store_true",
        help="Aplicar en el servidor remoto en lugar de localmente"
    )
    
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Mostrar información detallada"
    )
    
    args = parser.parse_args()
    
    # Cargar configuración
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    
    # Obtener ruta dentro del contenedor DDEV (valor obligatorio desde config.yaml)
    ddev_wp_path = get_nested(config, "ddev", "webroot")
    if not ddev_wp_path and not args.remote:
        print("⚠️ Error: No se ha configurado ddev.webroot en config.yaml")
        print("   Esta configuración es obligatoria para usar DDEV.")
        print("   Ejemplo: webroot: \"/var/www/html/app/public\"")
        return 1
    
    # Obtener URL de medios desde configuración si no se especificó
    media_url = args.url
    if not media_url:
        media_url = get_nested(config, "media", "url", "")
        if not media_url:
            print("⚠️ No se especificó URL de medios y no se encontró en configuración")
            print("   Ejemplo: --url=https://media.tudominio.com")
            print("   Sin URL de medios, se usará la URL predeterminada de WordPress")
    
    # Ruta física personalizada para modo experto
    media_path = args.path
    if not media_path and args.expert:
        media_path = get_nested(config, "media", "path", "")
    
    if not media_path and args.expert:
        print("⚠️ Advertencia: Modo experto solicitado pero no se proporcionó ruta física")
        print("   Ejemplo: --path=/ruta/absoluta/a/uploads")
    
    # Si estamos en entorno local, verificar y asegurar que DDEV esté en ejecución
    if not args.remote:
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
    if args.verbose:
        print(f"   Ruta local: {local_path}")
        print(f"   Ruta en contenedor DDEV: {ddev_wp_path}")
    
    if not is_wordpress_installed(local_path, args.remote, remote_host, remote_path, True, ddev_wp_path):
        print("⚠️ No se pudo verificar una instalación funcional de WordPress")
        print("   Verifique que WordPress está correctamente instalado y configurado")
        print("   Continuando de todos modos, pero pueden ocurrir errores...")
    
    print(f"🔍 Configurando WordPress para usar rutas de medios personalizadas")
    if media_url:
        print(f"   URL de medios: {media_url}")
    if args.expert and media_path:
        print(f"   Ruta física: {media_path} (Modo Experto)")
    
    # 1. Verificar si el plugin ya está instalado
    print(f"📋 Verificando plugin '{MEDIA_PLUGIN}'...")
    
    if is_plugin_installed(MEDIA_PLUGIN, local_path, args.remote, remote_host, remote_path, True, ddev_wp_path):
        print(f"✅ Plugin '{MEDIA_PLUGIN}' ya está instalado")
        
        # Actualizar el plugin si ya está instalado
        print(f"🔄 Actualizando plugin '{MEDIA_PLUGIN}'...")
        update_result = install_plugin(
            MEDIA_PLUGIN, 
            local_path, 
            args.remote, 
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
        if not args.remote:
            debug_cmd = f"ddev wp plugin install {MEDIA_PLUGIN}"
        else:
            debug_cmd = f"ssh {remote_host} 'cd {remote_path} && wp plugin install {MEDIA_PLUGIN}'"
        print(f"🔍 Comando a ejecutar: {debug_cmd}")
        
        install_result = install_plugin(
            MEDIA_PLUGIN, 
            local_path, 
            args.remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path
        )
        
        if not install_result:
            print(f"❌ Error al instalar el plugin '{MEDIA_PLUGIN}'")
            print(f"🔄 Intentando instalar desde URL: {MEDIA_PLUGIN_URL}")
            
            # Mostrar comando que se ejecutaría para depuración
            if not args.remote:
                debug_cmd = f"ddev wp plugin install {MEDIA_PLUGIN_URL}"
            else:
                debug_cmd = f"ssh {remote_host} 'cd {remote_path} && wp plugin install {MEDIA_PLUGIN_URL}'"
            print(f"🔍 Comando a ejecutar: {debug_cmd}")
            
            # Intentar instalar desde URL
            install_result = install_plugin(
                MEDIA_PLUGIN_URL, 
                local_path, 
                args.remote, 
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
                if not args.remote:
                    print(f"      $ ddev wp plugin install {MEDIA_PLUGIN_URL}")
                else:
                    print(f"      $ ssh {remote_host} 'cd {remote_path} && wp plugin install {MEDIA_PLUGIN_URL}'")
                
                print("⚠️ Continuando sin el plugin. La configuración de medios puede no funcionar correctamente.")
            else:
                print(f"✅ Plugin '{MEDIA_PLUGIN}' instalado correctamente")
        else:
            print(f"✅ Plugin '{MEDIA_PLUGIN}' instalado correctamente")
    
    # 2. Activar el plugin
    print(f"🔌 Activando plugin '{MEDIA_PLUGIN}'...")
    activate_result = activate_plugin(
        MEDIA_PLUGIN, 
        local_path, 
        args.remote, 
        remote_host, 
        remote_path,
        True,
        ddev_wp_path
    )
    
    if not activate_result:
        print(f"⚠️ No se pudo activar el plugin '{MEDIA_PLUGIN}'. Continuando de todos modos...")
    else:
        print(f"✅ Plugin '{MEDIA_PLUGIN}' activado correctamente")
    
    # 3. Obtener configuración actual
    if args.verbose:
        print("🔍 Configuración actual:")
        cmd = ["option", "get", "upload_url_path"]
        code, stdout, stderr = run_wp_cli(cmd, local_path, args.remote, remote_host, remote_path, True, ddev_wp_path)
        current_url = stdout.strip() if code == 0 and stdout.strip() else "No configurado"
        
        cmd = ["option", "get", "owmp_path"]
        code, stdout, stderr = run_wp_cli(cmd, local_path, args.remote, remote_host, remote_path, True, ddev_wp_path)
        current_path = stdout.strip() if code == 0 and stdout.strip() else "No configurado"
        
        cmd = ["option", "get", "owmp_expert_bool"]
        code, stdout, stderr = run_wp_cli(cmd, local_path, args.remote, remote_host, remote_path, True, ddev_wp_path)
        current_expert = stdout.strip() if code == 0 and stdout.strip() else "0"
        
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
            args.remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path
        )
    
    # 5. Configurar modo experto si se solicitó
    if args.expert:
        print("⚙️ Activando modo experto para ruta personalizada")
        update_option(
            "owmp_expert_bool", 
            "1", 
            local_path, 
            args.remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path
        )
        
        if media_path:
            print(f"🔧 Configurando ruta física a: {media_path}")
            update_option(
                "owmp_path", 
                media_path, 
                local_path, 
                args.remote, 
                remote_host, 
                remote_path,
                True,
                ddev_wp_path
            )
    else:
        # Asegurar que el modo experto esté desactivado
        update_option(
            "owmp_expert_bool", 
            "0", 
            local_path, 
            args.remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path
        )
    
    # 6. Limpiar caché
    print("🧹 Limpiando caché de WordPress...")
    flush_cache(
        local_path, 
        args.remote, 
        remote_host, 
        remote_path,
        True,
        ddev_wp_path
    )
    
    # 7. Verificar configuración final
    print("\n📊 Configuración final:")
    
    # URL de medios
    cmd = ["option", "get", "upload_url_path"]
    code, stdout, stderr = run_wp_cli(cmd, local_path, args.remote, remote_host, remote_path, True, ddev_wp_path)
    final_url = stdout.strip() if code == 0 and stdout.strip() else "No configurado (usando valor predeterminado)"
    
    # Ruta física
    cmd = ["option", "get", "owmp_path"]
    code, stdout, stderr = run_wp_cli(cmd, local_path, args.remote, remote_host, remote_path, True, ddev_wp_path)
    final_path = stdout.strip() if code == 0 and stdout.strip() else "No configurado (usando valor predeterminado)"
    
    # Modo experto
    cmd = ["option", "get", "owmp_expert_bool"]
    code, stdout, stderr = run_wp_cli(cmd, local_path, args.remote, remote_host, remote_path, True, ddev_wp_path)
    final_expert = "Activado" if code == 0 and stdout.strip() == "1" else "Desactivado"
    
    print(f"   URL de medios: {final_url}")
    print(f"   Ruta física: {final_path}")
    print(f"   Modo experto: {final_expert}")
    
    print("\n✅ Configuración completada correctamente")
    print("🔍 Los archivos de medios se buscarán ahora en la ruta configurada")
    if not args.remote:
        print("\n💡 Recordatorio: Después de sincronizar la base de datos de producción")
        print("   a desarrollo, ejecute este script para configurar las rutas de medios")
        print("   y asegúrese de que los archivos de medios estén disponibles localmente.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 