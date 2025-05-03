# WordPress Deploy Tools

Herramientas para sincronización, despliegue y gestión de parches en sitios WordPress, implementadas en Python para un flujo de trabajo de desarrollo eficiente.

## Filosofía y propósito

Este proyecto nace de la necesidad de democratizar el desarrollo y mantenimiento de sitios web basados en WordPress, especialmente para pequeños negocios y desarrolladores independientes, bajo tres principios fundamentales:

### Autonomía digital

En un mundo donde la dependencia de plataformas SaaS y proveedores de servicios multinacionales crece exponencialmente, estas herramientas ayudan a mantener la soberanía sobre la infraestructura digital. La capacidad de migrar fácilmente entre proveedores de hosting, gestionar entornos eficientemente y mantener el control completo de los datos se vuelve crítica para la supervivencia digital sostenible.

### Accesibilidad económica

Los modelos de precios de muchas soluciones comerciales están diseñados para economías de primer mundo, dejando fuera a pequeños emprendedores y negocios de economías emergentes. Este proyecto permite implementar flujos de trabajo profesionales y seguros sin la necesidad de costosas suscripciones, haciendo posible que pequeños negocios compitan digitalmente sin comprometer sus finanzas.

### Eficiencia operativa

La gestión manual de entornos WordPress consume tiempo valioso que podría invertirse en crear valor real para clientes. Estas herramientas automatizan tareas repetitivas de sincronización, configuración y mantenimiento, permitiendo a desarrolladores y propietarios de negocios enfocarse en lo que realmente importa: crear y hacer crecer sus proyectos.

En esencia, este proyecto pertenece a una nueva generación de herramientas open source que, potenciadas por avances tecnológicos como la IA, buscan devolver el control tecnológico a las personas y negocios independientes, siguiendo la tradición del movimiento de software libre y su visión de un internet más abierto y accesible para todos.

## Filosofía de configuración y flujo de trabajo

### Configuración única e idempotencia

Este proyecto se fundamenta en dos principios de ingeniería fundamentales:

1. **Sistema de configuración dividido**: El proyecto opera con dos archivos de configuración complementarios:
   - `config.yaml`: Contiene configuración global aplicable a todos los sitios
   - `sites.yaml`: Define la configuración específica de cada sitio individual

   Este enfoque permite gestionar múltiples sitios WordPress desde una única instalación de las herramientas, eliminando inconsistencias y facilitando la adaptación a diferentes proyectos.

2. **Idempotencia**: Los comandos están diseñados para producir el mismo resultado final independientemente de cuántas veces se ejecuten. Esto permite automatizar operaciones sin preocuparse por efectos secundarios o estados intermedios.

### Gestión de múltiples sitios

El sistema permite operar con múltiples sitios WordPress desde una única instalación de las herramientas, lo que:

1. **Centraliza las actualizaciones**: Mantener una sola copia de las herramientas permite actualizarlas fácilmente
2. **Evita duplicación**: No es necesario clonar el proyecto en cada sitio de WordPress
3. **Flexibilidad de ubicación**: El proyecto puede estar en cualquier ubicación de tu sistema, no necesariamente dentro del directorio DDEV de cada sitio

Cada sitio puede tener su propia configuración completa e independiente, y se accede mediante un alias único:

```bash
# Inicializar el sistema de sitios
python deploy-tools/python/cli.py site --init

# Añadir un sitio con la configuración actual
python deploy-tools/python/cli.py site --add mitienda --from-current 

# Añadir otro sitio (se creará con configuración por defecto que deberás editar)
python deploy-tools/python/cli.py site --add otrasitio

# Establecer un sitio como predeterminado
python deploy-tools/python/cli.py site --set-default mitienda

# Listar sitios disponibles
python deploy-tools/python/cli.py site --list
```

Para ejecutar cualquier comando en un sitio específico, simplemente añade la opción `--site`:

```bash
# Sincronizar archivos de un sitio específico
python deploy-tools/python/cli.py sync-files --site mitienda

# Ver información del sistema para un sitio
python deploy-tools/python/cli.py check --site otrasitio
```

### Flujo de trabajo recomendado

El típico flujo de trabajo para empezar a desarrollar en un sitio WordPress existente es:

#### 1. Preparación inicial (una sola vez)

```bash
# Clonar las herramientas
git clone https://github.com/aficiomaquinas/wp-deploy-tools.git deploy-tools

# Crear un sitio y configurarlo
cd deploy-tools/python
python cli.py site --init
python cli.py site --add mitienda
```

Editar el archivo de configuración del sitio (`sites.yaml`) con:
- Datos de conexión SSH del servidor remoto
- Rutas locales y remotas del proyecto
- Configuración de base de datos
- Patrones de exclusión para sincronización (especialmente `wp-content/uploads/*`)
- URL de medios para evitar sincronizarlos localmente

#### 2. Replicación del entorno (desarrollo diario)

Todo el proceso puede realizarse con un solo comando:

```bash
# Inicializar entorno completo (archivos, BD y configuración de medios)
python cli.py init --with-db --with-media --site mitienda
```

O paso a paso:

```bash
# 1. Sincronizar archivos (excluyendo medios y nuestro código personalizado)
python cli.py sync-files --site mitienda

# 2. Sincronizar base de datos
python cli.py sync-db --site mitienda

# 3. Configurar rutas de medios para usar los de producción
python cli.py media-path --site mitienda

# 4. Verificar diferencias
python cli.py diff --site mitienda
```

En este punto, se tiene un entorno local completamente funcional que:
- Contiene todos los archivos de WordPress, plugins y temas de producción
- Tiene la misma configuración y contenido de la base de datos
- Utiliza los medios directamente desde el servidor de producción
- Está listo para desarrollo sin haber descargado gigabytes de archivos de medios

#### 3. Desarrollo y parches

A partir de aquí, se pueden:
- Desarrollar plugins y temas propios que residirán en sus propios repositorios
- Aplicar parches a plugins de terceros según sea necesario
- Probar las modificaciones localmente antes de aplicarlas en producción

```bash
# Registrar un parche para un plugin que necesita modificación
python cli.py patch --add wp-content/plugins/woocommerce/archivo-a-modificar.php --site mitienda

# Editar el archivo localmente

# Cuando esté listo, aplicar el parche en producción
python cli.py patch-commit --site mitienda
```

### Automatización completa

Todo este proceso podría automatizarse en un solo comando gracias a la idempotencia del sistema. El comando `init` permite configurar un entorno de desarrollo completo con un solo click, ahorrando tiempo valioso y eliminando errores humanos en el proceso de configuración.

> 🔍 **Nota**: El principio de idempotencia es clave en este flujo. Incluso si un paso falla o se interrumpe, simplemente se puede volver a ejecutar el mismo comando y continuará desde donde se quedó, sin efectos secundarios no deseados.

### Beneficios de este enfoque

Este flujo de trabajo resuelve uno de los mayores desafíos en el desarrollo de WordPress: el tiempo entre decidir trabajar en un sitio y tener un entorno local funcional. Con este método:

- Se reduce drásticamente el tiempo de configuración (de horas a minutos)
- No es necesario descargar gigas de archivos multimedia que no son parte del desarrollo
- La base de datos y archivos reflejan exactamente la producción, eliminando sorpresas
- Los cambios y parches se aplican de forma controlada y rastreable
- Las modificaciones necesarias en producción se pueden realizar de forma segura y consistente
- Se puede trabajar con múltiples sitios desde una única instalación de las herramientas

En esencia, estas herramientas permiten que los desarrolladores se enfoquen en crear valor real para sus clientes en lugar de lidiar con tareas repetitivas de configuración y sincronización.

## Características principales

- **Sincronización bidireccional** de archivos entre entorno local y remoto
- **Sincronización de base de datos** con ajuste automático de URLs y configuraciones
- **Sistema avanzado de gestión de parches** para modificar plugins de terceros
- **Gestión de rutas de medios** para trabajar con CDNs o servidores de medios externos
- **Protecciones de seguridad** para prevenir cambios accidentales en producción
- **Configuración centralizada** mediante archivos YAML con soporte para entornos
- **Interfaz de línea de comandos** intuitiva con comandos y subcomandos

## Requisitos

- Python 3.6 o superior
- SSH configurado con acceso al servidor remoto
- MySQL/MariaDB (local si se usa sincronización de base de datos)
- Para desarrollo local: DDEV sobre UNIX based OS (único soportado por el momento)

## Instalación

1. Clona este repositorio en tu proyecto WordPress:
```bash
   git clone https://github.com/aficiomaquinas/wp-deploy-tools.git deploy-tools
   ```

2. Instala las dependencias:
   ```bash
   cd deploy-tools/python
   pip install -r requirements.txt
   ```

3. Crea tu archivo de configuración:
   ```bash
   python cli.py config --init
   ```

## Estructura del proyecto

```
deploy-tools/python/
├── wp_deploy/                    # Paquete principal
│   ├── __init__.py
│   ├── config_yaml.py            # Gestión de configuración YAML
│   ├── commands/                 # Comandos disponibles
│   │   ├── __init__.py
│   │   ├── diff.py               # Mostrar diferencias
│   │   ├── sync.py               # Sincronización de archivos
│   │   ├── database.py           # Sincronización de base de datos
│   │   ├── patch.py              # Aplicación de parches
│   │   ├── site.py               # Gestión de múltiples sitios
│   │   └── media.py              # Gestión de rutas de medios
│   ├── utils/                    # Utilidades compartidas
│   │   ├── __init__.py
│   │   ├── ssh.py                # Operaciones SSH
│   │   ├── wp_cli.py             # Operaciones con WP-CLI
│   │   └── filesystem.py         # Operaciones de sistema de archivos
├── cli.py                        # Punto de entrada CLI
├── config.yaml                   # Configuración global para todos los sitios
├── sites.yaml                    # Configuración específica de cada sitio
├── patches.lock.json             # Registro de parches aplicados
├── setup.py                      # Configuración de instalación
└── requirements.txt              # Dependencias
```

## Configuración

El sistema utiliza archivos de configuración YAML para gestionar todos los parámetros necesarios.

### Gestión de configuración

La configuración se puede personalizar mediante los siguientes comandos:

```bash
# Mostrar la configuración actual (global + sitio predeterminado)
python cli.py config --show

# Mostrar la configuración de un sitio específico
python cli.py config --show --site mitienda

# Crear archivos de configuración predeterminados
python cli.py config --init

# Generar una plantilla de configuración con comentarios explicativos
python cli.py config --template

# Verificar la configuración y los requisitos del sistema
python cli.py check

# Verificar un sitio específico
python cli.py check --site mitienda
```

### Gestión de sitios

El sistema multi-sitio permite administrar varios sitios WordPress:

```bash
# Inicializar el sistema de sitios
python cli.py site --init

# Añadir un sitio con la configuración actual
python cli.py site --add mitienda --from-current

# Añadir un nuevo sitio (con configuración por defecto)
python cli.py site --add otrositio

# Establecer un sitio como predeterminado
python cli.py site --set-default mitienda

# Listar todos los sitios configurados
python cli.py site --list

# Eliminar un sitio de la configuración (no elimina archivos)
python cli.py site --remove otrositio
```

### Ejemplo de archivos de configuración

#### Configuración global (config.yaml)

```yaml
# Configuración global para WordPress Deploy Tools
# Este archivo contiene configuración común para todos los sitios

# Ajustes WP-CLI globales
wp_cli:
  memory_limit: "512M"  # Límite de memoria para PHP en WP-CLI

# Parámetros de seguridad por defecto
security:
  production_safety: "enabled"  # Protección contra sobrescritura en producción
  backups: "enabled"  # Crear backups automáticos antes de operaciones peligrosas

# Exclusiones por defecto (se pueden sobrescribir por sitio)
exclusions:
  # Directorios de caché y optimización
  cache: "wp-content/cache/"
  litespeed: "wp-content/litespeed/"
  
  # Media (por defecto no sincronizar uploads)
  default-themes: "wp-content/themes/twenty*"
  uploads-by-year: "wp-content/uploads/[0-9][0-9][0-9][0-9]/"

# Archivos protegidos por defecto
protected_files:
  - "wp-config.php"
  - "wp-config-ddev.php"
  - ".gitignore"
  - ".ddev/" 

#### Configuración de sitios (sites.yaml)

```yaml
# Configuración de múltiples sitios para WordPress Deploy Tools

# Sitio predeterminado (si hay varios configurados)
default: "mitienda"

# Configuración de sitios individuales
sites:
  mitienda:
    ssh:
      remote_host: "mi-servidor"  # Alias SSH en ~/.ssh/config
      remote_path: "/ruta/al/wordpress/en/servidor/"
      local_path: "/ruta/local/al/proyecto/app/public/"

    security:
      production_safety: "enabled"  # Protección contra sobrescritura

    urls:
      remote: "https://mi-sitio.com"
      local: "https://mi-sitio.ddev.site"

    database:
      remote:
        name: "nombre_db"
        user: "usuario_db"
        password: "contraseña_segura"
        host: "localhost"

    media:
      url: "https://mi-sitio.com/wp-content/uploads/"
      expert_mode: false
      path: "../media"

    # Configuración DDEV
    ddev:
      webroot: "/var/www/html/app/public"

    # Exclusiones específicas para este sitio
    exclusions:
      # Plugins personalizados que no deben sincronizarse
      my-plugin: "wp-content/plugins/mi-plugin-personalizado/"
      
  otrosito:
    ssh:
      remote_host: "otro-servidor"
      remote_path: "/var/www/html/otrosito/"
      local_path: "/ruta/local/otrosito/app/public/"
    
    # ... configuración similar para cada sitio
```

## Comandos disponibles

### Verificación y diferencias

```bash
# Verificar configuración y requisitos para el sitio predeterminado
python cli.py check

# Verificar un sitio específico
python cli.py check --site mitienda

# Mostrar diferencias entre servidor remoto y local (sitio predeterminado)
python cli.py diff

# Mostrar diferencias para un sitio específico
python cli.py diff --site mitienda

# Mostrar sólo diferencias de archivos parcheados
python cli.py diff --patches

# Mostrar diferencias de parches para un sitio específico
python cli.py diff --patches --site mitienda
```

### Sincronización de archivos

```bash
# Sincronizar archivos desde el servidor remoto al entorno local (sitio predeterminado)
python cli.py sync-files

# Sincronizar archivos para un sitio específico
python cli.py sync-files --site mitienda

# Sincronizar archivos desde el entorno local al servidor remoto
python cli.py sync-files --direction to-remote

# Sincronizar archivos locales a remoto para un sitio específico
python cli.py sync-files --direction to-remote --site mitienda

# Simular sincronización sin hacer cambios
python cli.py sync-files --dry-run --site mitienda
```

### Sincronización de base de datos

```bash
# Sincronizar base de datos desde el servidor remoto al entorno local (sitio predeterminado)
python cli.py sync-db

# Sincronizar base de datos para un sitio específico
python cli.py sync-db --site mitienda

# Sincronizar base de datos desde el entorno local al servidor remoto (PELIGROSO)
python cli.py sync-db --direction to-remote

# Simular sincronización sin hacer cambios
python cli.py sync-db --dry-run --site mitienda
```

### Gestión de parches

```bash
# Listar parches registrados (sitio predeterminado)
python cli.py patch --list

# Listar parches para un sitio específico
python cli.py patch --list --site mitienda

# Registrar un nuevo parche
python cli.py patch --add wp-content/plugins/woocommerce/woocommerce.php --site mitienda

# Registrar un parche con descripción
python cli.py patch --add --description "Corrección de error" wp-content/plugins/woocommerce/woocommerce.php --site mitienda

# Ver información detallada de un parche
python cli.py patch --info wp-content/plugins/woocommerce/woocommerce.php --site mitienda

# Eliminar un parche del registro
python cli.py patch --remove wp-content/plugins/woocommerce/woocommerce.php --site mitienda
```

### Aplicación de parches

```bash
# Aplicar un parche específico
python cli.py patch-commit wp-content/plugins/woocommerce/woocommerce.php --site mitienda

# Aplicar todos los parches registrados
python cli.py patch-commit --site mitienda

# Simular aplicación de parches sin hacer cambios
python cli.py patch-commit --dry-run --site mitienda

# Forzar aplicación incluso con archivos modificados
python cli.py patch-commit --force --site mitienda
```

### Rollback de parches

```bash
# Revertir un parche aplicado
python cli.py rollback wp-content/plugins/woocommerce/woocommerce.php --site mitienda

# Simular rollback sin hacer cambios
python cli.py rollback wp-content/plugins/woocommerce/woocommerce.php --dry-run --site mitienda
```

### Gestión de rutas de medios

```bash
# Configurar rutas de medios según config.yaml (sitio predeterminado)
python cli.py media-path

# Configurar rutas de medios para un sitio específico
python cli.py media-path --site mitienda

# Aplicar configuración en el servidor remoto
python cli.py media-path --remote --site mitienda

# Mostrar información detallada durante la configuración
python cli.py media-path --verbose --site mitienda
```

La gestión de rutas de medios permite configurar URLs personalizadas para los archivos multimedia de WordPress, facilitando:

- Usado en combinacion con exclusiones (por ejemplo de wp-content/uploads/{year}) permite reducir el tiempo que toma hacer que el entorno de desarrollo local funcione.
- Usar CDNs o servidores de medios externos para mejorar rendimiento y reducir el tiempo de puesta en marcha del ambiente de desarrollo local, evitando tener que sincronizar los medios que pueden ser directorios muy pesados y que generalmente son estaticos y no suelen estar involucrados con el funcionamiento del sitio (generalmente no tienen scripts).
- Mantener archivos multimedia en ubicaciones independientes del código
- Configurar entornos de desarrollo para trabajar con media desde producción
- Implementar estrategias de almacenamiento óptimas según presupuesto y necesidades

El comando instala y configura automáticamente el plugin "WP Original Media Path" utilizando los valores definidos en la sección `media` del archivo de configuración:

```yaml
media:
  url: "https://media.midominio.com/wp-content/uploads/"  # URL para archivos multimedia
  expert_mode: false  # Activar modo experto para rutas físicas personalizadas
  path: "/ruta/absoluta/a/uploads"  # Ruta física (solo con expert_mode: true)
```

## Sistema de parches

El sistema de parches permite mantener modificaciones a plugins y temas de terceros de manera organizada y rastreable:

### Funcionamiento

1. **Registro de parches**: Los parches se registran en un archivo `patches.lock.json`
2. **Verificación de checksums**: Se comparan checksums para detectar cambios en archivos
3. **Backup automático**: Se crean copias de seguridad antes de aplicar parches
4. **Trazabilidad**: Se registra quién aplicó cada parche y cuándo

### Estados de parches

El sistema puede mostrar diferentes estados para cada parche:

- **⏳ Pendiente**: Registrado pero no aplicado
- **✅ Aplicado**: Aplicado correctamente y vigente
- **⚠️ Huérfano**: El archivo local ha cambiado desde que se registró
- **🔄 Obsoleto**: Parche aplicado pero el archivo local modificado después
- **❌ Desajustado**: Aplicado pero el archivo remoto ha sido modificado
- **📅 Caduco**: Parche obsoleto porque la versión remota ha cambiado

### Filosofía del sistema de parches

El sistema de parches aborda un problema fundamental en el ecosistema WordPress: la necesidad de modificar código de terceros manteniendo la integridad del ciclo de actualizaciones.

#### ¿Por qué parches en lugar de forks completos?

Mientras que algunas soluciones comerciales costosas ofrecen entornos "atómicos" con repositorios completos versionados (como Pantheon o RunCloud Enterprise), este enfoque:

1. **Respeta el versionamiento original**: El código ya está versionado por sus autores en Wordpress.org. Crear un sistema paralelo de versionamiento completo es redundante e ineficiente.

2. **Mantiene la responsabilidad compartida**: Un parche por definición reconoce que estamos modificando algo que no es nuestro, pero asumiendo la responsabilidad por esa modificación.

3. **Facilita las actualizaciones**: Al mantener un registro claro de las modificaciones puntuales, es más fácil determinar si un parche sigue siendo necesario después de una actualización.

4. **Reduce la complejidad operativa**: Gestionar un repositorio separado para cada plugin modificado genera una complejidad innecesaria en el flujo de trabajo.

Este enfoque simple pero efectivo ayuda a mantener WordPress seguro y funcional sin sacrificar la capacidad de personalización ni incurrir en costos elevados por soluciones comerciales que esencialmente hacen lo mismo de forma más compleja.

> 💡 **Nota:** En el futuro, podría integrarse con sistemas de verificación de integridad (Malcare, Wordfence, Jetpack) de plugins populares para manejar excepciones específicas a versiones parchadas, sin afectar la verificación en versiones futuras cuando el autor actualice el código.

## Características de seguridad

1. **Protección de entorno de producción**
   - Si `production_safety` está habilitado, se ejecuta en modo simulación
   - Requiere confirmación explícita para operaciones críticas

2. **Protección de archivos**
   - Sistema para identificar y proteger archivos críticos
   - Solicita confirmación antes de sobrescribir archivos importantes

3. **Copias de seguridad automáticas**
   - Creación de backups antes de operaciones destructivas
   - Backups con nombres únicos basados en timestamps

4. **Verificación por checksums**
   - Detección de cambios mediante checksums MD5
   - Evita aplicar parches sobre archivos modificados

## Próximos pasos

El proyecto se enfoca ahora en:

1. **Mejorar la integración con DDEV** para una experiencia aún más fluida
2. **Sistema de actualización automática** para facilitar el seguimiento de mejoras
3. **Pruebas de integración** para validar el funcionamiento completo
4. **Optimización de rendimiento** en proyectos con mucho contenido
5. **Detección y gestión automática de plugins parcheados** en sistemas de verificación de integridad
6. **Capacidades avanzadas de migración** para simplificar cambios entre proveedores de hosting

## Licencia

Este proyecto es software libre bajo licencia [MIT](LICENSE). 