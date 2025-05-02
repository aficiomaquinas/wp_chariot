# WordPress Deploy Tools

Esta carpeta contiene scripts y herramientas para facilitar el desarrollo, sincronización y despliegue de sitios WordPress.

## Estructura de archivos

```
deploy-tools/
├── scripts/             # Scripts de sincronización y despliegue
│   ├── sync_config.sh   # Configuración compartida
│   ├── diff_with_server.sh
│   ├── sync_from_runcloud.sh
│   ├── sync-db-from-remote.sh
│   ├── install-media-path.sh
│   ├── edit_diff.sh
│   └── rollback.sh
├── templates/           # Plantillas de configuración
│   └── ejemplo.env      # Modelo de archivo .env
├── deploy-tools.env     # Configuración para las herramientas
└── README.md            # Este archivo
```

## Instalación

1. Clona este repositorio o cópialo a tu directorio de proyecto WordPress
2. Crea un archivo `.env` en la raíz de tu proyecto, basado en `templates/ejemplo.env`
3. Utiliza los scripts mediante el wrapper `wp-tools.sh` en la raíz del proyecto

## Configuración

### deploy-tools.env
Este archivo configura el comportamiento de las herramientas:

```bash
# Ruta al archivo .env del proyecto (relativo a la ubicación de este archivo)
PROJECT_ENV_PATH="../.env"

# Flag de seguridad para prevenir despliegues accidentales
PRODUCTION_SAFETY="enabled"
```

### .env del proyecto
Contiene la configuración específica de tu proyecto:

```bash
# Host SSH (debe estar configurado en ~/.ssh/config)
REMOTE_SSH="nombre_del_host_ssh"

# Rutas
REMOTE_PATH="/home/usuario/webapps/sitio/"
LOCAL_PATH="/ruta/local/sitio/app/public/"

# Configuración de base de datos, URLs, etc.
REMOTE_DB_NAME="nombre_db"
...
```

## Herramientas disponibles

### Sincronización y diferencias

* **diff_with_server.sh**: Muestra las diferencias entre el servidor y local
* **sync_from_runcloud.sh**: Sincroniza archivos desde el servidor a local
* **sync-db-from-remote.sh**: Sincroniza la base de datos del servidor a local

### Desarrollo y mantenimiento

* **edit_diff.sh**: Herramienta para analizar y editar cambios
* **install-media-path.sh**: Configura rutas personalizadas para medios
* **rollback.sh**: Permite hacer rollback de plugins a versiones anteriores

### Aplicación de parches

**apply-patches.sh** (en la raíz): Aplica parches a plugins de terceros

## Uso

Utiliza el script wrapper en la raíz:

```bash
# Ver diferencias con el servidor
./wp-tools.sh diff

# Sincronizar archivos
./wp-tools.sh sync

# Sincronizar base de datos
./wp-tools.sh db

# Aplicar parches
./wp-tools.sh patch

# Ver todos los comandos
./wp-tools.sh help
```

## Seguridad

### Protección para producción

Para prevenir despliegues accidentales a producción, estas herramientas incluyen un mecanismo de seguridad:

1. La variable `PRODUCTION_SAFETY` puede estar en "enabled" o "disabled"
2. Cuando está habilitada, cualquier operación que modifique el servidor requerirá confirmación explícita
3. Para deshabilitar temporalmente, cambia a "disabled" en tu .env

## Extensión y personalización

### Añadir exclusiones

Las exclusiones para rsync están definidas en `sync_config.sh`. Si necesitas añadir o modificar exclusiones:

1. Edita el array `EXCLUSIONS` en `sync_config.sh`
2. Conserva el formato de clave-valor existente

### Añadir nuevos scripts

Para añadir un nuevo script:

1. Crea tu script en `scripts/`
2. Importa la configuración compartida: `source "$(dirname "$0")/sync_config.sh"`
3. Añade el comando al script wrapper `wp-tools.sh`

## Resolución de problemas

### Problemas comunes

* **Error de conexión SSH**: Asegúrate de que tu configuración SSH funciona correctamente
* **Rutas incorrectas**: Verifica las rutas en tu archivo .env
* **Permisos de archivo**: Asegúrate de que todos los scripts tienen permisos de ejecución

### Logs y depuración

Activa la salida de depuración añadiendo `set -x` al principio de cualquier script.

## Refactorización a Python (En Progreso)

Estamos migrando estas herramientas de Bash a Python para mejorar:

- Manejo de errores y validación de datos
- Configuración más robusta y flexible
- Mejor interfaz de línea de comandos
- Mayor facilidad de mantenimiento y extensibilidad

### Estructura del proyecto Python

```
deploy-tools/
├── python/              # Nueva implementación en Python
│   ├── wp_deploy/       # Paquete principal
│   │   ├── __init__.py
│   │   ├── config.py    # Manejo de configuración 
│   │   ├── sync/        # Módulos de sincronización
│   │   ├── tools/       # Herramientas auxiliares
│   │   └── utils/       # Utilidades comunes
│   ├── cli.py           # Punto de entrada CLI
│   ├── requirements.txt # Dependencias
│   └── setup.py         # Configuración de instalación
├── scripts/             # Scripts originales Bash (legado)
└── ... (resto de la estructura original)
```

### Compatibilidad

La nueva versión en Python es totalmente compatible con:
- Los mismos archivos de configuración (.env)
- El mismo flujo de trabajo e interfaz de comandos
- Las mismas funcionalidades, con mejoras adicionales

## Plan de trabajo

La migración a Python se realizará en las siguientes fases:

1. **Fase 1**: Implementación del sistema de configuración y estructura base
2. **Fase 2**: Migración de funcionalidades de sincronización de archivos
3. **Fase 3**: Migración de sincronización de base de datos
4. **Fase 4**: Migración de herramientas de parches y rollback
5. **Fase 5**: Mejoras de interfaz de línea de comandos y documentación
6. **Fase 6**: Pruebas de integración y optimizaciones

Durante la migración, ambas versiones (Bash y Python) coexistirán para facilitar la transición.

## Próximos pasos 

Este sistema está diseñado para ser una solución de transición. En futuras versiones, se planea:

1. Migrar a Python para mejor manejo de configuración y errores
2. Mejorar la interfaz de línea de comandos
3. Añadir opciones más avanzadas de sincronización y despliegue 