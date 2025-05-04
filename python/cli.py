#!/usr/bin/env python3
"""
CLI para WordPress Deploy Tools

Este script proporciona una interfaz de línea de comandos para las herramientas de despliegue.
"""

import os
import sys
import click
from pathlib import Path
import yaml

# Asegurar que se puede importar el paquete wp_deploy
script_dir = Path(__file__).resolve().parent
if script_dir not in sys.path:
    sys.path.append(str(script_dir))

# Importar la nueva configuración YAML en lugar de la anterior basada en .env
from config_yaml import get_yaml_config
from commands.sync import sync_files
from commands.diff import show_diff
from commands.database import sync_database
from commands.patch import list_patches, apply_patch, rollback_patch, add_patch, remove_patch
from commands.media import configure_media_path

# Definir una opción común para el sitio
site_option = click.option(
    "--site", 
    help="Alias del sitio a operar (si hay múltiples configurados)"
)

# Grupo de comandos principal
@click.group()
@click.version_option("0.1.0")
def cli():
    """
    Herramientas de despliegue para WordPress.
    
    Este conjunto de comandos facilita el desarrollo, sincronización
    y despliegue de sitios WordPress entre entornos.
    """
    pass

@cli.command("diff")
@click.option("--all", is_flag=True, help="Mostrar todos los archivos sin límite")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
@click.option("--patches", is_flag=True, help="Mostrar solo información relacionada con parches")
@site_option
def diff_command(all, verbose, patches, site):
    """
    Muestra las diferencias entre el servidor remoto y el entorno local.
    Este comando siempre es de solo lectura y nunca realiza cambios.
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
        
    success = show_diff(show_all=all, verbose=verbose, only_patches=patches)
    if not success:
        sys.exit(1)
    
@cli.command("sync-files")
@click.option("--dry-run", is_flag=True, help="Simular operación sin hacer cambios")
@click.option("--direction", type=click.Choice(['from-remote', 'to-remote']), 
              default='from-remote', help="Dirección de la sincronización")
@click.option("--clean/--no-clean", default=True, help="Limpiar archivos excluidos después de sincronizar")
@site_option
def sync_files_command(dry_run, direction, clean, site):
    """
    Sincroniza archivos entre el servidor remoto y el entorno local.
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config()
    if not config.select_site(site):
        sys.exit(1)
        
    success = sync_files(direction=direction, dry_run=dry_run, clean=clean)
    if not success:
        sys.exit(1)
    
@cli.command("sync-db")
@click.option("--dry-run", is_flag=True, help="Simular operación sin hacer cambios")
@click.option("--direction", type=click.Choice(['from-remote', 'to-remote']), 
              default='from-remote', help="Dirección de la sincronización")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
@site_option
def sync_db_command(dry_run, direction, verbose, site):
    """
    Sincroniza la base de datos entre el servidor remoto y el entorno local.
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
        
    success = sync_database(direction=direction, dry_run=dry_run, verbose=verbose)
    if not success:
        sys.exit(1)

@cli.command("media-path")
@click.option("--remote", is_flag=True, help="Aplicar en el servidor remoto en lugar de localmente")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
@site_option
def media_path_command(remote, verbose, site):
    """
    Configura la ruta de medios de WordPress utilizando el plugin WP Original Media Path.
    
    Este comando instala y configura el plugin necesario para gestionar rutas
    de medios personalizadas según los valores definidos en config.yaml.
    Mantiene una única fuente de configuración para asegurar la consistencia.
    
    Ejemplos:
      media-path                 # Configurar en entorno local
      media-path --remote        # Configurar en servidor remoto
      media-path --verbose       # Mostrar información detallada
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
        
    # Obtener la configuración
    media_config = config.config.get("media", {})
    expert_mode = media_config.get("expert_mode", False)
    
    success = configure_media_path(
        media_url=None,  # Forzar a que obtenga el valor de config.yaml
        expert_mode=expert_mode,
        media_path=None,  # Forzar a que obtenga el valor de config.yaml
        remote=remote,
        verbose=verbose
    )
    
    if not success:
        sys.exit(1)
    
@cli.command("patch")
@click.argument("file_path", required=False)
@click.option("--list", is_flag=True, help="Listar parches registrados")
@click.option("--add", is_flag=True, help="Registrar un nuevo parche")
@click.option("--remove", is_flag=True, help="Eliminar un parche del registro")
@click.option("--info", is_flag=True, help="Mostrar información detallada de un parche sin aplicarlo")
@click.option("--dry-run", is_flag=True, help="Simular operación sin hacer cambios")
@click.option("--description", "-d", help="Descripción del parche (al registrar)")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada")
@click.option("--config", is_flag=True, help="Mostrar configuración del sistema de parches")
@site_option
def patch_command(file_path, list, add, remove, info, dry_run, description, verbose, config, site):
    """
    Gestiona y registra parches a plugins de terceros.
    
    FILE_PATH es la ruta relativa al archivo que se va a parchar.
    Este comando NO APLICA los parches, solo los gestiona. Para aplicar
    un parche use el comando 'patch commit'.
    
    Ejemplos:
      patch --list -v                     # Listar parches con información detallada
      patch --add wp-content/plugins/x/y.php  # Registrar un nuevo parche
      patch --add --description "Fix..." x.php # Registrar con descripción
      patch --remove wp-content/plugins/x/y.php # Eliminar un parche del registro
      patch --info wp-content/plugins/x/y.php   # Ver detalles sin aplicar
      patch --config                      # Ver configuración del sistema de parches
    """
    # Seleccionar sitio si es necesario
    config_obj = get_yaml_config(verbose=verbose)
    if not config_obj.select_site(site):
        sys.exit(1)
    
    # Mostrar configuración del sistema de parches si se solicita
    if config:
        from commands.patch import PatchManager
        manager = PatchManager()
        manager.show_config_info(verbose=True)
        return
        
    # Opción de listar parches
    if list:
        from commands.patch import PatchManager
        manager = PatchManager()
        manager.list_patches(verbose=verbose)
        return
    
    # Verificar que se proporcionó una ruta para add/remove/info
    if (add or remove or info) and not file_path:
        click.echo("❌ Debe especificar la ruta del archivo para --add, --remove o --info")
        sys.exit(1)
    
    # Opción de agregar un parche
    if add:
        success = add_patch(file_path, description)
        if not success:
            sys.exit(1)
        return
    
    # Opción de eliminar un parche
    if remove:
        success = remove_patch(file_path)
        if not success:
            sys.exit(1)
        return
    
    # Opción de mostrar info detallada
    if info and file_path:
        # Mostrar info detallada de un parche sin aplicarlo
        success = apply_patch(file_path=file_path, dry_run=True, show_details=True)
        if not success:
            sys.exit(1)
        return
        
    # Si no se especificó ninguna acción pero sí un archivo, mostrar info
    if file_path and not (add or remove or info):
        # Mostrar info simple
        success = apply_patch(file_path=file_path, dry_run=True, show_details=False)
        if not success:
            sys.exit(1)
        return
        
    # Si no se especificó ninguna opción, mostrar ayuda
    click.echo("ℹ️ Para ver la lista de parches registrados: patch --list")
    click.echo("ℹ️ Para aplicar parches: patch-commit [archivo]")
    click.echo("ℹ️ Para más opciones: patch --help")

@cli.command("patch-commit")
@click.argument("file_path", required=False)
@click.option("--dry-run", is_flag=True, help="Simular operación sin hacer cambios")
@click.option("--force", is_flag=True, help="Forzar aplicación incluso con archivos modificados o versiones diferentes")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
@site_option
def patch_commit_command(file_path, dry_run, force, verbose, site):
    """
    Aplica parches registrados al servidor remoto.
    
    FILE_PATH es la ruta relativa al archivo que se va a parchar. Si no se especifica,
    se intentará aplicar todos los parches registrados.
    
    Este comando requiere confirmación explícita y verifica la configuración
    de seguridad de producción antes de aplicar cualquier cambio.
    
    Ejemplos:
      patch-commit wp-content/plugins/x/y.php  # Aplicar un parche específico
      patch-commit                           # Aplicar todos los parches registrados
      patch-commit --dry-run                 # Ver qué cambios se harían sin aplicarlos
      patch-commit --force                   # Forzar aplicación incluso con archivos modificados
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
        
    # Verificar protección de producción
    production_safety = config.get("security", "production_safety") == "enabled"
    
    if production_safety and not dry_run:
        print("⛔ ERROR: No se pueden aplicar parches con la protección de producción activada.")
        print("   Esta operación modificará archivos en el servidor de PRODUCCIÓN.")
        print("   Si estás seguro de lo que haces, puedes:")
        print("   1. Usar --dry-run para ver qué cambios se harían sin aplicarlos")
        print("   2. Desactivar temporalmente 'production_safety' en la configuración")
        sys.exit(1)
    
    # Solicitar confirmación explícita para aplicar parches
    if not dry_run and not force:
        if file_path:
            message = f"⚠️ ¿Estás seguro de aplicar el parche a '{file_path}'? Esta acción modificará archivos en el servidor."
        else:
            message = "⚠️ ¿Estás seguro de aplicar TODOS los parches registrados? Esta acción modificará archivos en el servidor."
        
        confirm = input(f"{message} (s/N): ")
        if confirm.lower() != "s":
            print("❌ Operación cancelada.")
            sys.exit(0)
    
    # Aplicar el parche o parches
    success = apply_patch(file_path=file_path, dry_run=dry_run, show_details=verbose, force=force)
    
    if not success:
        sys.exit(1)

@cli.command("rollback")
@click.argument("file_path")
@click.option("--dry-run", is_flag=True, help="Simular operación sin hacer cambios")
@site_option
def rollback_command(file_path, dry_run, site):
    """
    Revierte un parche aplicado anteriormente a un plugin o tema.
    
    FILE_PATH es la ruta relativa al archivo que se va a restaurar desde el backup.
    Funciona sólo con parches que se hayan aplicado previamente y estén registrados
    en el archivo patches.lock.json.
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config()
    if not config.select_site(site):
        sys.exit(1)
        
    success = rollback_patch(file_path=file_path, dry_run=dry_run)
    if not success:
        sys.exit(1)
    
@cli.command("config")
@click.option("--show", is_flag=True, help="Mostrar configuración actual")
@click.option("--repair", is_flag=True, help="Reparar la configuración si hay problemas de estructura")
@click.option("--output", type=str, default="wp-deploy.yaml", help="Ruta de salida para el archivo de configuración")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
@site_option
def config_command(show, repair, output, verbose, site):
    """
    Gestiona la configuración de las herramientas.
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config(verbose=verbose)
    if site and (show or repair) and not config.select_site(site):
        sys.exit(1)
        
    output_path = Path(output)
    
    if show:
        # Mostrar la configuración actual
        if site:
            print(f"Mostrando configuración para el sitio: {site}")
        config.display()
    elif repair:
        # Reparar la configuración
        import shutil
        
        # Hacer una copia de seguridad si el archivo existe
        if output_path.exists():
            backup_path = output_path.with_suffix(".yaml.bak")
            shutil.copy2(output_path, backup_path)
            click.echo(f"✅ Copia de seguridad creada: {backup_path}")
            
        # Leer la plantilla existente si existe
        existing_config = {}
        if output_path.exists():
            try:
                with open(output_path, 'r') as f:
                    existing_config = yaml.safe_load(f) or {}
            except Exception as e:
                click.echo(f"⚠️ Error al leer la configuración actual: {str(e)}")
                
        # Asegurarse de que todas las secciones principales existen
        sections = ["ssh", "security", "database", "urls", "media", "exclusions", "protected_files"]
        
        for section in sections:
            if section not in existing_config:
                existing_config[section] = config.config.get(section, {})
                
        # Guardar la configuración reparada
        try:
            with open(output_path, 'w') as f:
                yaml.dump(existing_config, f, default_flow_style=False, sort_keys=False)
            click.echo(f"✅ Configuración reparada guardada en {output_path}")
        except Exception as e:
            click.echo(f"❌ Error al guardar la configuración reparada: {str(e)}")
    else:
        click.echo("Uso: wp-deploy config [--show|--repair] [--output ARCHIVO]")

@cli.command("site")
@click.option("--list", is_flag=True, help="Listar sitios configurados")
@click.option("--add", is_flag=True, help="Añadir o actualizar un sitio")
@click.option("--remove", is_flag=True, help="Eliminar un sitio")
@click.option("--set-default", is_flag=True, help="Establecer un sitio como predeterminado")
@click.option("--init", is_flag=True, help="Inicializar archivo de configuración de sitios")
@click.option("--from-current", is_flag=True, help="Usar la configuración actual al añadir un sitio")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada")
@click.argument("site_alias", required=False)
def site_command(list, add, remove, set_default, init, from_current, verbose, site_alias):
    """
    Gestiona configuraciones de múltiples sitios.
    
    Esta función permite mantener una única instalación de las herramientas
    que puede operar con múltiples sitios WordPress independientes.
    
    Ejemplos:
      site --list                  # Listar sitios configurados
      site --add mitienda          # Añadir un sitio con alias 'mitienda'
      site --add mitienda --from-current  # Añadir usando configuración actual
      site --remove mitienda       # Eliminar un sitio
      site --set-default mitienda  # Establecer sitio por defecto
    """
    config = get_yaml_config(verbose=verbose)
    
    # Inicializar archivo de sitios
    if init:
        default = site_alias if set_default else None
        success = config.create_sites_config(default_site=default)
        return
    
    # Listar sitios configurados
    if list:
        sites = config.get_available_sites()
        default_site = config.get_default_site()
        
        if not sites:
            print("ℹ️ No hay sitios configurados")
            print("   Puede añadir sitios con: site --add ALIAS")
            return
        
        print("📋 Sitios configurados:")
        for alias, site_config in sites.items():
            default_mark = " (por defecto)" if alias == default_site else ""
            print(f"  - {alias}{default_mark}")
            
            # Mostrar detalles si verbose
            if verbose:
                ssh_config = site_config.get("ssh", {})
                remote = ssh_config.get("remote_host", "No configurado")
                path = ssh_config.get("remote_path", "No configurado")
                print(f"    Servidor: {remote}")
                print(f"    Ruta: {path}")
                
                if "urls" in site_config:
                    print(f"    URL remota: {site_config['urls'].get('remote', 'No configurado')}")
                    print(f"    URL local: {site_config['urls'].get('local', 'No configurado')}")
                
                print("")
        return
    
    # Verificar que se proporcionó un alias para otras operaciones
    if (add or remove or set_default) and not site_alias:
        print("❌ Debe especificar un alias para añadir, eliminar o establecer como predeterminado")
        print("   Ejemplo: site --add misitio")
        sys.exit(1)
    
    # Añadir o actualizar un sitio
    if add:
        site_config = None
        if from_current:
            site_config = config.config
            print(f"ℹ️ Usando configuración actual para el sitio '{site_alias}'")
        
        success = config.add_site(site_alias, config=site_config, is_default=set_default)
        if not success:
            sys.exit(1)
        return
    
    # Eliminar un sitio
    if remove:
        success = config.remove_site(site_alias)
        if not success:
            sys.exit(1)
        return
    
    # Establecer sitio por defecto
    if set_default and not add:
        # Verificar que el sitio existe
        sites = config.get_available_sites()
        if site_alias not in sites:
            print(f"❌ Error: Sitio '{site_alias}' no encontrado")
            sys.exit(1)
        
        success = config.add_site(site_alias, config=sites[site_alias], is_default=True)
        if not success:
            sys.exit(1)
        return
    
    # Si no se especificó ninguna opción, mostrar ayuda
    print("ℹ️ Uso: site [--list|--add|--remove|--set-default|--init] [ALIAS]")
    print("   Para obtener ayuda detallada: site --help")

@cli.command("check")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
@site_option
def check_command(verbose, site):
    """
    Verifica los requisitos y configuración del sistema.
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config(verbose=verbose)
    if site and not config.select_site(site):
        sys.exit(1)
        
    import shutil
    
    click.echo("🔍 Verificando requisitos del sistema...")
    
    # Verificar que rsync está instalado
    if shutil.which("rsync"):
        click.echo("✅ rsync: Instalado")
    else:
        click.echo("❌ rsync: No encontrado")
        
    # Verificar que ssh está instalado
    if shutil.which("ssh"):
        click.echo("✅ ssh: Instalado")
    else:
        click.echo("❌ ssh: No encontrado")
        
    # Verificar que ddev está instalado (para sync-db)
    if shutil.which("ddev"):
        click.echo("✅ ddev: Instalado")
    else:
        click.echo("⚠️ ddev: No encontrado (requerido para sincronización de base de datos)")
        
    # Verificar la configuración SSH
    ssh_config = os.path.expanduser("~/.ssh/config")
    if os.path.exists(ssh_config):
        click.echo("✅ Archivo de configuración SSH: Encontrado")
    else:
        click.echo("❌ Archivo de configuración SSH: No encontrado")
        
    # Verificar la configuración del proyecto
    click.echo("\n🔍 Verificando estructura de configuración YAML...")
    
    # Verificar estructura de las secciones principales
    sections = ["ssh", "security", "database", "urls", "media", "exclusions", "protected_files"]
    all_good = True
    
    for section in sections:
        if section in config.config:
            click.echo(f"✅ Sección '{section}': Presente")
        else:
            click.echo(f"❌ Sección '{section}': Falta")
            all_good = False
    
    if not all_good:
        click.echo("⚠️ Algunas secciones de la configuración están faltando. Ejecute 'config --repair' para generar una plantilla completa.")
    
    # Verificar que las rutas existen
    click.echo("\n🔍 Verificando rutas y configuración...")
    local_path = Path(config.get("ssh", "local_path"))
    if local_path.exists():
        click.echo(f"✅ Ruta local: Existe ({local_path})")
    else:
        click.echo(f"❌ Ruta local: No existe ({local_path})")
        
    # Verificar variables de configuración críticas
    critical_configs = [
        ("ssh", "remote_host"),
        ("ssh", "remote_path"),
        ("ssh", "local_path"),
    ]
    
    for path in critical_configs:
        if config.get(*path):
            click.echo(f"✅ Configuración {'.'.join(path)}: Configurada")
        else:
            click.echo(f"❌ Configuración {'.'.join(path)}: No configurada")
            
    # Verificar exclusiones
    try:
        exclusions = config.get_exclusions()
        if exclusions:
            click.echo(f"✅ Exclusiones: {len(exclusions)} patrones configurados")
        else:
            click.echo("⚠️ Exclusiones: No hay patrones configurados")
    except Exception as e:
        click.echo(f"❌ Error al verificar exclusiones: {str(e)}")
        
    # Verificar configuración de medios
    try:
        media_config = config.get_media_config()
        if media_config and media_config.get("url"):
            click.echo(f"✅ URL de medios configurada: {media_config.get('url')}")
        else:
            click.echo("ℹ️ URL de medios no configurada (se usará la ruta estándar)")
    except Exception as e:
        click.echo(f"❌ Error al verificar configuración de medios: {str(e)}")

@cli.command("debug-config")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
@site_option
def debug_config_command(verbose, site):
    """
    Muestra información de depuración sobre la configuración
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config(verbose=True)  # Forzar verbose para este comando
    if site and not config.select_site(site):
        sys.exit(1)
        
    # Mostrar rutas de configuración
    print("\n🔍 Información de depuración de configuración:")
    print(f"  - Directorio raíz detectado: {config.project_root}")
    print(f"  - Directorio de deploy-tools: {config.deploy_tools_dir}")
    
    # Verificar archivos de configuración
    global_config_file = config.deploy_tools_dir / "python" / "config.yaml"
    project_config_file = config.project_root / "wp-deploy.yaml"
    sites_config_file = config.deploy_tools_dir / "python" / "sites.yaml"
    
    print("\n📂 Archivos de configuración:")
    if global_config_file.exists():
        print(f"  ✅ Archivo global: {global_config_file} (EXISTE)")
    else:
        print(f"  ❌ Archivo global: {global_config_file} (NO EXISTE)")
        
    if project_config_file.exists():
        print(f"  ✅ Archivo de proyecto: {project_config_file} (EXISTE)")
    else:
        print(f"  ❌ Archivo de proyecto: {project_config_file} (NO EXISTE)")
        
    if sites_config_file.exists():
        print(f"  ✅ Archivo de sitios: {sites_config_file} (EXISTE)")
        
        # Mostrar información de sitios
        available_sites = config.get_available_sites()
        default_site = config.get_default_site()
        
        if available_sites:
            print(f"     Sitios configurados: {len(available_sites)}")
            print(f"     Sitio por defecto: {default_site if default_site else 'Ninguno'}")
            print(f"     Sitio actual: {config.current_site if hasattr(config, 'current_site') and config.current_site else 'Ninguno'}")
        else:
            print(f"     No hay sitios configurados")
    else:
        print(f"  ❌ Archivo de sitios: {sites_config_file} (NO EXISTE)")
        
    # Mostrar valores de configuración críticos
    print("\n🔑 Valores REALES de configuración de base de datos (nunca mostrados en otros comandos):")
    db_config = config.config.get('database', {}).get('remote', {})
    print(f"  - Host: {db_config.get('host', 'No configurado')}")
    print(f"  - Nombre: {db_config.get('name', 'No configurado')}")
    print(f"  - Usuario: {db_config.get('user', 'No configurado')}")
    print(f"  - Contraseña: {'*'*len(db_config.get('password', '')) if 'password' in db_config else 'No configurada'}")
    
    print("\n⚠️  IMPORTANTE: Por seguridad, cuando uses los comandos normales como 'config --show',")
    print("   se mostrarán valores de ejemplo para credenciales sensibles (como se ve a continuación).")
    print("   Los valores reales se usan internamente pero no se muestran para proteger las credenciales.")
    
    # Mostrar la configuración completa con valores enmascarados
    print("\n🔧 Configuración como se muestra normalmente (con credenciales ocultas):")
    config.display()

@cli.command("init")
@click.option("--with-db", is_flag=True, help="Incluir sincronización de base de datos")
@click.option("--with-media", is_flag=True, help="Configurar URLs de medios")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada")
@click.option("--dry-run", is_flag=True, help="Simular operación sin hacer cambios")
@site_option
def init_command(with_db, with_media, verbose, dry_run, site):
    """
    Inicializa un entorno de desarrollo completo en un solo paso.
    
    Este comando realiza las siguientes operaciones en secuencia:
    1. Sincroniza archivos desde el servidor remoto
    2. Opcionalmente sincroniza la base de datos
    3. Opcionalmente configura las rutas de medios
    
    Es equivalente a ejecutar los siguientes comandos en secuencia:
    - sync-files
    - sync-db (si --with-db)
    - media-path (si --with-media)
    """
    # Seleccionar sitio si es necesario
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
    
    print("🚀 Inicializando entorno de desarrollo...")
    
    # 1. Sincronizar archivos
    print("\n📂 Paso 1: Sincronización de archivos")
    success = sync_files(direction="from-remote", dry_run=dry_run, clean=True)
    if not success:
        print("❌ Error en la sincronización de archivos")
        sys.exit(1)
    
    # 2. Sincronizar base de datos (opcional)
    if with_db:
        print("\n🗄️ Paso 2: Sincronización de base de datos")
        success = sync_database(direction="from-remote", dry_run=dry_run, verbose=verbose)
        if not success:
            print("❌ Error en la sincronización de base de datos")
            sys.exit(1)
    
    # 3. Configurar rutas de medios (opcional)
    if with_media:
        print("\n🖼️ Paso 3: Configuración de rutas de medios")
        media_config = config.config.get("media", {})
        expert_mode = media_config.get("expert_mode", False)
        
        success = configure_media_path(
            media_url=None,
            expert_mode=expert_mode,
            media_path=None,
            remote=False,
            verbose=verbose
        )
        if not success:
            print("❌ Error en la configuración de rutas de medios")
            sys.exit(1)
    
    print("\n✅ Entorno de desarrollo inicializado correctamente")
    print("🌟 ¡Listo para comenzar a trabajar!")

@cli.command()
@click.option('--path', '-p', help='Ruta dentro del contenedor DDEV donde buscar WordPress (obsoleto, usar sites.yaml)')
@site_option
def verify_wp(path, site):
    """
    Verifica si WordPress está correctamente instalado.
    
    Este comando ejecuta 'wp core is-installed' directamente 
    utilizando la configuración de sites.yaml, sin depender
    de archivos .ddev.
    """
    from utils.wp_cli import run_wp_cli
    from config_yaml import get_yaml_config
    import os
    
    # Obtener configuración de sitios
    config = get_yaml_config()
    if not config.select_site(site):
        sys.exit(1)
    
    print(f"🔍 Verificando instalación de WordPress...")
    
    # Obtener directorio local del proyecto desde la configuración
    if 'ssh' not in config.config or 'local_path' not in config.config['ssh']:
        print("❌ Error: No se encontró configuración de ruta local en sites.yaml")
        sys.exit(1)
        
    # Obtener la ruta local del proyecto directamente de sites.yaml
    local_path_str = config.config['ssh']['local_path']
    
    # Obtener el directorio base del proyecto
    # Ejemplo: /home/user/proyecto/app/public -> /home/user/proyecto
    local_path = Path(local_path_str)
    project_dir = local_path.parent.parent  # Subir dos niveles desde app/public
    
    print(f"ℹ️ Directorio del proyecto DDEV: {project_dir}")
    
    # Obtener la ruta wp_path desde los parámetros base_path y docroot (exigidos explícitamente)
    if 'ddev' not in config.config:
        print("❌ Error: No se encontró sección 'ddev' en sites.yaml")
        sys.exit(1)
        
    # Exigir ambos parámetros explícitamente (fail fast)
    if 'base_path' not in config.config['ddev'] or 'docroot' not in config.config['ddev']:
        print("❌ Error: Configuración DDEV incompleta en sites.yaml")
        print("   Se requieren ambos parámetros:")
        print("   - ddev.base_path: Ruta base dentro del contenedor (ej: \"/var/www/html\")")
        print("   - ddev.docroot: Directorio del docroot (ej: \"app/public\")")
        sys.exit(1)
    
    # Construir la ruta wp_path con los parámetros configurados
    base_path = config.config['ddev']['base_path']
    docroot = config.config['ddev']['docroot']
    wp_path = f"{base_path}/{docroot}"
    
    # Ignorar cualquier ruta pasada por parámetro (obsoleta)
    if path:
        print("⚠️ Ignorando parámetro --path (obsoleto)")
        print("   La ruta se obtiene automáticamente de sites.yaml (ddev.base_path + ddev.docroot)")
    
    print(f"ℹ️ Usando ruta WordPress dentro del contenedor: {wp_path}")
        
    # Verificar que el directorio existe en el sistema
    if not project_dir.exists():
        print(f"❌ Error: El directorio del proyecto '{project_dir}' no existe")
        sys.exit(1)
    
    # Ejecutar verificación con la ruta especificada
    code, stdout, stderr = run_wp_cli(
        ["core", "is-installed"],
        project_dir,  # Ejecutar en el directorio del proyecto
        remote=False,
        use_ddev=True,
        wp_path=wp_path
    )
    
    # Mostrar resultado
    if code == 0:
        print("✅ WordPress está correctamente instalado y configurado")
        sys.exit(0)
    else:
        print("❌ WordPress no está instalado o no se pudo detectar")
        if stderr:
            print(f"   Error: {stderr}")
        print(f"   Ruta utilizada: {wp_path}")
        sys.exit(1)

@cli.command()
@site_option
def show_ddev_config(site):
    """
    Muestra la configuración WordPress de sites.yaml.
    
    Útil para diagnosticar problemas relacionados con la ruta de WordPress.
    """
    import subprocess
    import os
    from config_yaml import get_yaml_config
    from pathlib import Path
    
    # Obtener configuración de sitios
    config = get_yaml_config()
    if not config.select_site(site):
        sys.exit(1)
    
    print("🔍 Obteniendo configuración desde sites.yaml...")
    
    # Verificar si existe configuración DDEV en sites.yaml
    if 'ddev' not in config.config:
        print("❌ No se encontró configuración DDEV en sites.yaml")
        sys.exit(1)
    
    # Obtener directorio local del proyecto desde la configuración
    if 'ssh' not in config.config or 'local_path' not in config.config['ssh']:
        print("❌ Error: No se encontró configuración de ruta local en sites.yaml")
        sys.exit(1)
        
    # Mostrar información desde sites.yaml
    print("📋 Configuración DDEV encontrada en sites.yaml:")
    
    ddev_config = config.config['ddev']
    
    # Verificar que existen ambos parámetros requeridos
    if 'base_path' not in ddev_config or 'docroot' not in ddev_config:
        print("❌ Error: Configuración DDEV incompleta en sites.yaml")
        print("   Se requieren ambos parámetros:")
        print("   - ddev.base_path: Ruta base dentro del contenedor (ej: \"/var/www/html\")")
        print("   - ddev.docroot: Directorio del docroot (ej: \"app/public\")")
        sys.exit(1)
    
    # Mostrar información de la configuración actual
    base_path = ddev_config['base_path']
    docroot = ddev_config['docroot']
    wp_path = f"{base_path}/{docroot}"
    
    print(f"   - base_path: {base_path}")
    print(f"   - docroot: {docroot}")
    print(f"   - Ruta WP completa: {wp_path}")
    
    # Obtener la ruta local del proyecto directamente de sites.yaml
    local_path_str = config.config['ssh']['local_path']
    local_path = Path(local_path_str)
    
    # Obtener el directorio base del proyecto
    # Ejemplo: /home/user/proyecto/app/public -> /home/user/proyecto
    project_dir = local_path.parent.parent  # Subir dos niveles desde app/public
    
    print(f"   - Directorio local del proyecto: {project_dir}")
    
    # Verificar que el directorio existe
    if not project_dir.exists():
        print(f"   ❌ El directorio del proyecto no existe: {project_dir}")
    else:
        print(f"   ✅ El directorio del proyecto existe")
    
    # Ejecutar ddev describe para mostrar URLs (en el directorio correcto)
    print("\n📡 DDEV describe:")
    
    try:
        result = subprocess.run(
            ["ddev", "describe"], 
            cwd=project_dir,  # Ejecutar en el directorio del proyecto
            capture_output=True, 
            text=True, 
            check=False
        )
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if ":" in line:
                    print(f"   {line.strip()}")
        else:
            print(f"   ❌ Error: {result.stderr}")
    except Exception as e:
        print(f"   ❌ Error al ejecutar ddev describe: {str(e)}")
    
    # Sugerir comando para verificar WordPress
    print(f"\n💡 Para verificar WordPress, ejecuta:")
    print(f"   python cli.py verify-wp --site={config.current_site}")
        
    # Mostrar valores de URL
    if 'urls' in config.config and 'remote' in config.config['urls']:
        print(f"\n🌐 URL remota configurada: {config.config['urls']['remote']}")
    if 'urls' in config.config and 'local' in config.config['urls']:
        print(f"🖥️ URL local configurada: {config.config['urls']['local']}")

def main():
    """
    Punto de entrada principal
    """
    try:
        cli()
    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 