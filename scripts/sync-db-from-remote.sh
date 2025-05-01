#!/bin/bash

# Script para sincronizar la base de datos desde un servidor remoto a entorno local
# Incluye exportación, transferencia, búsqueda y reemplazo, e importación

# Verificar requisitos
if ! command -v ddev &> /dev/null; then
    echo "❌ Error: DDEV no está instalado. Por favor, instálalo primero."
    exit 1
fi

# Verificar que estamos en un proyecto DDEV
if [ ! -f .ddev/config.yaml ]; then
    echo "❌ Error: No se detectó configuración de DDEV (.ddev/config.yaml)."
    echo "   Este script debe ejecutarse desde la raíz de un proyecto DDEV."
    exit 1
fi

# Verificar si existe el archivo .env
if [ ! -f .env ]; then
    echo "❌ Error: No se encontró el archivo .env en el directorio actual."
    echo "   Este archivo es necesario para obtener la configuración."
    echo ""
    echo "   Crea un archivo .env con al menos estas variables:"
    echo "   REMOTE_SSH_ALIAS=remoto           # Alias del servidor SSH en ~/.ssh/config"
    echo "   REMOTE_DB_NAME=nombre_db          # Nombre de la base de datos remota"
    echo "   REMOTE_DB_USER=usuario_db         # Usuario de la base de datos remota"
    echo "   REMOTE_DB_PASS=contraseña_db      # Contraseña de la base de datos remota"
    echo "   REMOTE_DB_HOST=localhost          # Host de la base de datos remota"
    echo "   REMOTE_PATH=/ruta/wordpress       # Ruta al WordPress remoto"
    echo "   REMOTE_URL=https://sitio.com      # URL del sitio remoto"
    echo "   LOCAL_URL=https://sitio.ddev.site # URL local del sitio"
    exit 1
fi

# Cargar variables desde .env
echo "📝 Cargando configuración desde .env..."
DEPLOY_TOOLS_DIR="$(dirname "$(dirname "$0")")"
source "$DEPLOY_TOOLS_DIR/scripts/sync_config.sh"

# Verificar variables esenciales
for VAR in REMOTE_SSH_ALIAS REMOTE_DB_NAME REMOTE_DB_USER REMOTE_DB_PASS REMOTE_DB_HOST REMOTE_PATH REMOTE_URL LOCAL_URL; do
    if [ -z "${!VAR}" ]; then
        echo "❌ Error: La variable $VAR no está definida en .env"
        exit 1
    fi
done

# Crear directorio temporal si no existe
TEMP_DIR="./tmp"
mkdir -p "$TEMP_DIR"

# Generar nombre aleatorio para directorio temporal remoto
RANDOM_SUFFIX=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 10 | head -n 1)
REMOTE_TEMP_DIR="${REMOTE_PATH}/tmp_dump_${RANDOM_SUFFIX}"
DUMP_FILE="${REMOTE_DB_NAME}_$(date +"%Y%m%d_%H%M%S").sql"
REMOTE_DUMP_PATH="${REMOTE_TEMP_DIR}/${DUMP_FILE}"
LOCAL_DUMP_PATH="${TEMP_DIR}/${DUMP_FILE}"

echo "🔄 Iniciando sincronización de base de datos desde servidor remoto..."
echo "   - Servidor: $REMOTE_SSH_ALIAS (alias SSH)"
echo "   - Base de datos: $REMOTE_DB_NAME"
echo "   - URL remota: $REMOTE_URL"
echo "   - URL local: $LOCAL_URL"
echo ""

# Paso 1: Crear directorio temporal en el servidor remoto
echo "📁 Creando directorio temporal en el servidor remoto..."
ssh "$REMOTE_SSH_ALIAS" "mkdir -p \"$REMOTE_TEMP_DIR\""

if [ $? -ne 0 ]; then
    echo "❌ Error al crear directorio temporal en el servidor remoto."
    exit 1
fi

# Paso 2: Exportar base de datos en el servidor remoto
echo "📤 Exportando base de datos en el servidor remoto..."
ssh "$REMOTE_SSH_ALIAS" "mysqldump --default-character-set=utf8mb4 --no-tablespaces \
    -h \"$REMOTE_DB_HOST\" -u \"$REMOTE_DB_USER\" -p\"$REMOTE_DB_PASS\" \
    \"$REMOTE_DB_NAME\" > \"$REMOTE_DUMP_PATH\""

if [ $? -ne 0 ]; then
    echo "❌ Error al exportar la base de datos remota."
    # Limpiar directorio temporal remoto
    ssh "$REMOTE_SSH_ALIAS" "rm -rf \"$REMOTE_TEMP_DIR\""
    exit 1
fi

echo "✅ Base de datos exportada correctamente en el servidor remoto."

# Paso 3: Transferir el archivo dump a local
echo "📥 Descargando archivo dump del servidor remoto..."
scp "$REMOTE_SSH_ALIAS:$REMOTE_DUMP_PATH" "$LOCAL_DUMP_PATH"

if [ $? -ne 0 ]; then
    echo "❌ Error al transferir el archivo dump."
    # Limpiar directorio temporal remoto
    ssh "$REMOTE_SSH_ALIAS" "rm -rf \"$REMOTE_TEMP_DIR\""
    exit 1
fi

echo "✅ Archivo dump descargado correctamente: $LOCAL_DUMP_PATH"

# Paso 4: Eliminar el directorio temporal del servidor remoto
echo "🧹 Eliminando directorio temporal del servidor remoto..."
ssh "$REMOTE_SSH_ALIAS" "rm -rf \"$REMOTE_TEMP_DIR\""

# Paso 5: Búsqueda y reemplazo en el archivo dump
echo "🔍 Realizando búsqueda y reemplazo en el archivo dump..."
echo "   Reemplazando '$REMOTE_URL' por '$LOCAL_URL'"

# Crear un archivo temporal para el reemplazo
PROCESSED_DUMP="${LOCAL_DUMP_PATH%.sql}_processed.sql"

# Realizar el reemplazo con sed
sed "s#$REMOTE_URL#$LOCAL_URL#g" "$LOCAL_DUMP_PATH" > "$PROCESSED_DUMP"

if [ $? -ne 0 ]; then
    echo "❌ Error en la búsqueda y reemplazo."
    exit 1
fi

echo "✅ Búsqueda y reemplazo completado."

# Verificar si debemos realizar un reemplazo adicional para las URLs de medios
if [ -n "$WP_MEDIA_URL" ] && [ "$WP_MEDIA_URL" != "$LOCAL_URL/wp-content/uploads" ]; then
    echo "🔍 Detectada URL personalizada para medios: $WP_MEDIA_URL"
    echo "   Realizando reemplazo adicional para URLs de medios..."
    
    # Crear un segundo archivo procesado
    FINAL_DUMP="${PROCESSED_DUMP%.sql}_media.sql"
    
    # Reemplazar la ruta estándar de medios por la personalizada
    sed "s#$REMOTE_URL/wp-content/uploads#$WP_MEDIA_URL#g" "$PROCESSED_DUMP" > "$FINAL_DUMP"
    
    # Actualizar la referencia al archivo procesado
    PROCESSED_DUMP="$FINAL_DUMP"
    
    echo "✅ Reemplazo de URLs de medios completado."
fi

# Paso 6: Verificar estado de DDEV
DDEV_STATUS=$(ddev status | grep "running" | wc -l)
if [ "$DDEV_STATUS" -eq 0 ]; then
    echo "🚀 DDEV no está en ejecución. Iniciando DDEV..."
    ddev start
fi

# Paso 7: Importar el dump a la base de datos local
echo "📥 Importando base de datos a DDEV..."
cat "$PROCESSED_DUMP" | ddev mysql

if [ $? -ne 0 ]; then
    echo "❌ Error al importar la base de datos."
    exit 1
fi

echo "✅ Base de datos importada correctamente."

# Paso 8: Limpieza y finalización
echo "🧹 Limpiando archivos temporales locales..."
rm -f "$LOCAL_DUMP_PATH" "$PROCESSED_DUMP"
# Si existe el archivo de medios adicional, también lo eliminamos
if [ -f "${PROCESSED_DUMP%.sql}_media.sql" ]; then
    rm -f "${PROCESSED_DUMP%.sql}_media.sql"
fi

echo ""
echo "🎉 Sincronización de base de datos completada con éxito!"
echo "   - URL reemplazada: $REMOTE_URL → $LOCAL_URL"
if [ -n "$WP_MEDIA_URL" ] && [ "$WP_MEDIA_URL" != "$LOCAL_URL/wp-content/uploads" ]; then
    echo "   - URL de medios configurada: $WP_MEDIA_URL"
fi
echo ""
echo "   Recuerda ejecutar install-media-path.sh para configurar correctamente"
echo "   las rutas de medios si aún no lo has hecho."
echo ""
echo "   Para acceder a tu sitio local: ddev launch" 