#!/bin/bash

# Script para instalar y configurar wp-original-media-path
# para URLs personalizadas de medios en WordPress

# Importar configuración compartida (solo para las funciones de verificación)
DEPLOY_TOOLS_DIR="$(dirname "$(dirname "$0")")"
source "$DEPLOY_TOOLS_DIR/scripts/sync_config.sh"

# Verificar requisitos
check_requirements "ddev"

# Cargar variables desde .env
load_env

# Verificar variables necesarias
if [ -z "$WP_MEDIA_URL" ]; then
    echo "❌ Error: La variable WP_MEDIA_URL no está definida en .env"
    echo "   Ejemplo: WP_MEDIA_URL=https://media.tudominio.com"
    exit 1
fi

# Definir ruta a WordPress (usar valor predeterminado si no está definido en .env)
WP_PATH="${WP_PATH:-app/public}"
echo "🌐 Usando ruta WordPress: $WP_PATH"

# Verificar estado de DDEV
DDEV_STATUS=$(ddev status | grep "running" | wc -l)
if [ "$DDEV_STATUS" -eq 0 ]; then
    echo "🚀 DDEV no está en ejecución. Iniciando DDEV..."
    ddev start
fi

# Verificar la estructura de archivos primero
echo "🔍 Verificando instalación de WordPress en DDEV..."

# En DDEV, la ruta dentro del contenedor siempre es relativa a /var/www/html
CONTAINER_PATH="/var/www/html/$WP_PATH"

echo "   - Ruta local: $WP_PATH"
echo "   - Ruta en contenedor: $CONTAINER_PATH"

# Verificar si los archivos principales de WordPress existen
if ! ddev exec "test -f $CONTAINER_PATH/wp-config.php" || ! ddev exec "test -d $CONTAINER_PATH/wp-includes"; then
    echo "⚠️ No se encontraron archivos básicos de WordPress en la ruta especificada."
    echo "   - wp-config.php o wp-includes no existen en $CONTAINER_PATH"
    
    # Verificar si existen en la raíz del proyecto
    if ddev exec "test -f /var/www/html/wp-config.php" && ddev exec "test -d /var/www/html/wp-includes"; then
        echo "🔎 Se encontró WordPress en la raíz del proyecto (/var/www/html)."
        echo "   Actualizando WP_PATH a la raíz..."
        WP_PATH=""
        CONTAINER_PATH="/var/www/html"
    else
        read -p "¿Quieres continuar de todos modos? (s/n): " CONTINUE_ANYWAY
        if [[ "$CONTINUE_ANYWAY" != "s" && "$CONTINUE_ANYWAY" != "S" ]]; then
            echo "❌ Operación cancelada."
            exit 1
        fi
    fi
fi

# Intentar verificar si WordPress está instalado correctamente
if ! ddev exec "cd $CONTAINER_PATH && wp core is-installed --allow-root" &> /dev/null; then
    echo "⚠️ WordPress parece estar presente pero no está correctamente instalado o configurado."
    echo "   Esto puede deberse a una base de datos no configurada o a problemas de permisos."
    
    read -p "¿Quieres intentar instalar/configurar WordPress ahora? (s/n): " INSTALL_WP
    if [[ "$INSTALL_WP" == "s" || "$INSTALL_WP" == "S" ]]; then
        echo "🔧 Este proceso está fuera del alcance de este script."
        echo "   Por favor, complete la instalación de WordPress primero usando:"
        echo "   ddev start"
        echo "   ddev launch"
        echo "   Y complete el asistente de instalación web de WordPress."
        exit 1
    fi
    
    read -p "¿Quieres continuar de todos modos e intentar instalar el plugin? (s/n): " CONTINUE_ANYWAY
    if [[ "$CONTINUE_ANYWAY" != "s" && "$CONTINUE_ANYWAY" != "S" ]]; then
        echo "❌ Operación cancelada."
        exit 1
    fi
fi

echo "🔌 Instalando plugin wp-original-media-path..."

# Verificar si el plugin ya está instalado
if ddev exec "cd $CONTAINER_PATH && wp plugin is-installed wp-original-media-path --allow-root" &> /dev/null; then
    echo "📦 El plugin ya está instalado. Verificando si necesita actualizarse..."
    ddev exec "cd $CONTAINER_PATH && wp plugin update wp-original-media-path --allow-root"
else
    echo "📥 Instalando el plugin wp-original-media-path..."
    ddev exec "cd $CONTAINER_PATH && wp plugin install wp-original-media-path --allow-root"
fi

# Activar el plugin si no está activado
if ! ddev exec "cd $CONTAINER_PATH && wp plugin is-active wp-original-media-path --allow-root" &> /dev/null; then
    echo "✨ Activando plugin..."
    ddev exec "cd $CONTAINER_PATH && wp plugin activate wp-original-media-path --allow-root"
    echo "✅ Plugin activado correctamente."
else
    echo "✅ El plugin ya está activo."
fi

# Mostrar información sobre el plugin
echo ""
echo "ℹ️  Información del Plugin:"
echo "-------------------"
echo "Este plugin permite modificar la ubicación de los archivos de medios en WordPress."
echo "- Puedes cambiar la URL donde se acceden los medios (útil para subdominios o CDN)"
echo "- También puedes cambiar la ruta donde se guardan físicamente"
echo "- No es retroactivo para imágenes ya subidas (ver migración)"
echo "- No compatible con WordPress Multisite"
echo ""

# Configurar el plugin con valores del .env
echo "⚙️ Configurando plugin con valores del archivo .env:"
echo "  - URL de medios: $WP_MEDIA_URL"

# Configurar la URL de medios
ddev exec "cd $CONTAINER_PATH && wp option update upload_url_path '$WP_MEDIA_URL' --allow-root"
echo "✅ URL de medios actualizada correctamente."

# Verificar si debemos configurar el modo experto
if [ "${WP_MEDIA_EXPERT:-0}" == "1" ] && [ -n "${WP_MEDIA_PATH}" ]; then
    echo "  - Ruta física: $WP_MEDIA_PATH (Modo Experto)"
    ddev exec "cd $CONTAINER_PATH && wp option update owmp_path '$WP_MEDIA_PATH' --allow-root"
    ddev exec "cd $CONTAINER_PATH && wp option update owmp_expert_bool '1' --allow-root"
    echo "✅ Ruta física y modo experto configurados correctamente."
else
    echo "  - Modo básico (sin ruta personalizada)"
    ddev exec "cd $CONTAINER_PATH && wp option update owmp_expert_bool '0' --allow-root"
fi

# Verificar configuración final
echo ""
echo "📊 Verificando configuración aplicada:"
FINAL_URL=$(ddev exec "cd $CONTAINER_PATH && wp option get upload_url_path --allow-root" 2>/dev/null)
FINAL_PATH=$(ddev exec "cd $CONTAINER_PATH && wp option get owmp_path --allow-root" 2>/dev/null)
FINAL_EXPERT=$(ddev exec "cd $CONTAINER_PATH && wp option get owmp_expert_bool --allow-root" 2>/dev/null)

echo "  - URL de medios: ${FINAL_URL:-[Vacío - usando valor predeterminado de WordPress]}"
echo "  - Ruta personalizada: ${FINAL_PATH:-[Vacío - usando valor predeterminado de WordPress]}"
echo "  - Modo experto: ${FINAL_EXPERT:-desactivado}"

echo ""
echo "🎉 ¡Proceso completado! El plugin wp-original-media-path está instalado y configurado."
echo "   Recuerda que debes sincronizar la base de datos y ejecutar búsqueda y reemplazo para"
echo "   las URLs de los medios existentes."
echo ""
echo "   La ruta WordPress utilizada fue: ${WP_PATH:-raíz}"
echo "   Contenedor: $CONTAINER_PATH" 