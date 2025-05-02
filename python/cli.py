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
from wp_deploy.config_yaml import get_yaml_config, create_default_config, generate_template_config
from wp_deploy.commands.sync import sync_files
from wp_deploy.commands.diff import show_diff
from wp_deploy.commands.database import sync_database
from wp_deploy.commands.patch import list_patches, apply_patch, rollback_patch, add_patch, remove_patch

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
def diff_command(all, verbose, patches):
    """
    Muestra las diferencias entre el servidor remoto y el entorno local.
    Este comando siempre es de solo lectura y nunca realiza cambios.
    """
    success = show_diff(show_all=all, verbose=verbose, only_patches=patches)
    if not success:
        sys.exit(1)
    
@cli.command("sync-files")
@click.option("--dry-run", is_flag=True, help="Simular operación sin hacer cambios")
@click.option("--direction", type=click.Choice(['from-remote', 'to-remote']), 
              default='from-remote', help="Dirección de la sincronización")
@click.option("--clean/--no-clean", default=True, help="Limpiar archivos excluidos después de sincronizar")
def sync_files_command(dry_run, direction, clean):
    """
    Sincroniza archivos entre el servidor remoto y el entorno local.
    """
    success = sync_files(direction=direction, dry_run=dry_run, clean=clean)
    if not success:
        sys.exit(1)
    
@cli.command("sync-db")
@click.option("--dry-run", is_flag=True, help="Simular operación sin hacer cambios")
@click.option("--direction", type=click.Choice(['from-remote', 'to-remote']), 
              default='from-remote', help="Dirección de la sincronización")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
def sync_db_command(dry_run, direction, verbose):
    """
    Sincroniza la base de datos entre el servidor remoto y el entorno local.
    """
    success = sync_database(direction=direction, dry_run=dry_run, verbose=verbose)
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
def patch_command(file_path, list, add, remove, info, dry_run, description, verbose):
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
    """
    # Opción de listar parches
    if list:
        from wp_deploy.commands.patch import PatchManager
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
def patch_commit_command(file_path, dry_run, force, verbose):
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
    from wp_deploy.config_yaml import get_yaml_config
    from wp_deploy.commands.patch import PatchManager

    # Verificar protección de producción
    config = get_yaml_config()
    production_safety = config.get("security", "production_safety") == "enabled"
    
    if production_safety and not dry_run:
        print("⛔ ERROR: No se pueden aplicar parches con la protección de producción activada.")
        print("   Esta operación modificará archivos en el servidor de PRODUCCIÓN.")
        print("   Si estás seguro de lo que haces, puedes:")
        print("   1. Usar --dry-run para ver qué cambios se harían sin aplicarlos")
        print("   2. Desactivar temporalmente 'production_safety' en la configuración")
        sys.exit(1)
    
    # Solicitar confirmación explícita para aplicar parches
    if not dry_run:
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
def rollback_command(file_path, dry_run):
    """
    Revierte un parche aplicado anteriormente a un plugin o tema.
    
    FILE_PATH es la ruta relativa al archivo que se va a restaurar desde el backup.
    Funciona sólo con parches que se hayan aplicado previamente y estén registrados
    en el archivo patches.lock.json.
    """
    success = rollback_patch(file_path=file_path, dry_run=dry_run)
    if not success:
        sys.exit(1)
    
@cli.command("config")
@click.option("--show", is_flag=True, help="Mostrar configuración actual")
@click.option("--init", is_flag=True, help="Crear archivo de configuración YAML predeterminado")
@click.option("--template", is_flag=True, help="Generar plantilla de configuración con comentarios")
@click.option("--repair", is_flag=True, help="Reparar la configuración si hay problemas de estructura")
@click.option("--output", type=str, default="wp-deploy.yaml", help="Ruta de salida para el archivo de configuración")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
def config_command(show, init, template, repair, output, verbose):
    """
    Gestiona la configuración de las herramientas.
    """
    output_path = Path(output)
    
    if show:
        # Mostrar la configuración actual
        config = get_yaml_config(verbose=verbose)
        config.display()
    elif init:
        # Crear archivo de configuración predeterminado
        config = get_yaml_config(verbose=verbose)
        config.save_default_config(output_path)
        click.echo(f"Configuración guardada en {output_path}")
    elif template:
        # Generar plantilla de configuración
        config = get_yaml_config(verbose=verbose)
        config.generate_template(output_path)
        click.echo(f"Plantilla de configuración generada en {output_path}")
    elif repair:
        # Reparar la configuración
        import shutil
        
        # Hacer una copia de seguridad si el archivo existe
        if output_path.exists():
            backup_path = output_path.with_suffix(".yaml.bak")
            shutil.copy2(output_path, backup_path)
            click.echo(f"✅ Copia de seguridad creada: {backup_path}")
            
        # Generar una plantilla de configuración
        config = get_yaml_config(verbose=verbose)
        
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
        click.echo("Uso: wp-deploy config [--show|--init|--template|--repair] [--output ARCHIVO]")

@cli.command("check")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada durante la ejecución")
def check_command(verbose):
    """
    Verifica los requisitos y configuración del sistema.
    """
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
    config = get_yaml_config(verbose=verbose)
    
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
        click.echo("⚠️ Algunas secciones de la configuración están faltando. Ejecute 'config --template' para generar una plantilla completa.")
    
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
def debug_config_command(verbose):
    """
    Muestra información de depuración sobre la configuración
    """
    config = get_yaml_config(verbose=True)  # Forzar verbose para este comando
    
    # Mostrar rutas de configuración
    print("\n🔍 Información de depuración de configuración:")
    print(f"  - Directorio raíz detectado: {config.project_root}")
    print(f"  - Directorio de deploy-tools: {config.deploy_tools_dir}")
    
    # Verificar archivos de configuración
    global_config_file = config.deploy_tools_dir / "python" / "config.yaml"
    project_config_file = config.project_root / "wp-deploy.yaml"
    
    print("\n📂 Archivos de configuración:")
    if global_config_file.exists():
        print(f"  ✅ Archivo global: {global_config_file} (EXISTE)")
    else:
        print(f"  ❌ Archivo global: {global_config_file} (NO EXISTE)")
        
    if project_config_file.exists():
        print(f"  ✅ Archivo de proyecto: {project_config_file} (EXISTE)")
    else:
        print(f"  ❌ Archivo de proyecto: {project_config_file} (NO EXISTE)")
        
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