#!/bin/bash
# rollback.sh - Script para hacer rollback a una versión anterior del plugin

# Importar configuración compartida
DEPLOY_TOOLS_DIR="$(dirname "$(dirname "$0")")"
source "$DEPLOY_TOOLS_DIR/scripts/sync_config.sh"

# Verificar requisitos
check_requirements

# Directorio del plugin
PLUGIN_DIR="wp-content/plugins/avalon-ttamayo"

# Verificar si se proporcionó una versión
VERSION=$1

if [ -z "$VERSION" ]; then
  echo "ℹ️ No se especificó versión. Listando las 5 últimas versiones disponibles:"
  git tag -l --sort=-v:refname | head -5
  echo ""
  echo "Uso: ./rollback.sh v1.2.3"
  exit 1
fi

# Verificar si el tag existe
if ! git tag -l | grep -q "^$VERSION$"; then
  echo "❌ Error: La versión '$VERSION' no existe."
  echo "Versiones disponibles:"
  git tag -l --sort=-v:refname | head -10
  exit 1
fi

# Crear un directorio temporal
TEMP_DIR=$(mktemp -d)
echo "📦 Creando despliegue de rollback para versión $VERSION..."

# Clonar el repositorio en el directorio temporal
git clone -q . "$TEMP_DIR" || { echo "❌ Error al clonar el repositorio local"; rm -rf "$TEMP_DIR"; exit 1; }

# Cambiar al directorio temporal y verificar la versión
cd "$TEMP_DIR" || { echo "❌ Error al acceder al directorio temporal"; rm -rf "$TEMP_DIR"; exit 1; }
git checkout -q "$VERSION" || { echo "❌ Error al hacer checkout de la versión $VERSION"; cd - > /dev/null; rm -rf "$TEMP_DIR"; exit 1; }

# Verificar que existe el directorio del plugin en la versión
if [ ! -d "$PLUGIN_DIR" ]; then
  echo "❌ Error: El directorio del plugin no existe en la versión $VERSION."
  cd - > /dev/null
  rm -rf "$TEMP_DIR"
  exit 1
fi

# Preguntar confirmación
echo "⚠️ Se realizará un rollback del plugin 'avalon-ttamayo' a la versión $VERSION."
echo "   Esta acción reemplazará la versión actual en el servidor remoto."
read -p "¿Desea continuar? (s/n): " CONFIRM

if [[ "$CONFIRM" != "s" && "$CONFIRM" != "S" ]]; then
  echo "❌ Operación cancelada por el usuario."
  cd - > /dev/null
  rm -rf "$TEMP_DIR"
  exit 1
fi

# Crear un paquete del plugin
echo "📦 Creando paquete del plugin versión $VERSION..."
cd "$PLUGIN_DIR" || { echo "❌ Error al acceder al directorio del plugin"; cd - > /dev/null; rm -rf "$TEMP_DIR"; exit 1; }
zip -r -q "$TEMP_DIR/avalon-ttamayo-$VERSION.zip" .

# Volver al directorio original
cd - > /dev/null

# Subir el paquete al servidor
echo "📤 Subiendo paquete al servidor..."
scp "$TEMP_DIR/avalon-ttamayo-$VERSION.zip" "$REMOTE_SSH:$REMOTE_PATH/" || { echo "❌ Error al subir el paquete al servidor"; rm -rf "$TEMP_DIR"; exit 1; }

# Ejecutar comandos en el servidor remoto
echo "🔄 Aplicando rollback en el servidor remoto..."
ssh "$REMOTE_SSH" "cd $REMOTE_PATH && \
  echo '🔍 Haciendo backup de la versión actual...' && \
  if [ -d '$PLUGIN_DIR' ]; then \
    mv '$PLUGIN_DIR' '${PLUGIN_DIR}_backup_$(date +%Y%m%d_%H%M%S)'; \
  fi && \
  echo '📦 Extrayendo versión $VERSION...' && \
  mkdir -p '$PLUGIN_DIR' && \
  unzip -q avalon-ttamayo-$VERSION.zip -d '$PLUGIN_DIR' && \
  echo '🧹 Limpiando archivos temporales...' && \
  rm avalon-ttamayo-$VERSION.zip && \
  echo '✅ Rollback completado con éxito.'" || { echo "❌ Error al aplicar el rollback en el servidor"; rm -rf "$TEMP_DIR"; exit 1; }

# Limpiar directorio temporal
rm -rf "$TEMP_DIR"

echo "🎉 Rollback a la versión $VERSION completado exitosamente."
echo "   La versión anterior ha sido respaldada en el servidor como ${PLUGIN_DIR}_backup_*" 