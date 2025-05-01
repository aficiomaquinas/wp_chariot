#!/bin/bash

# Archivo de configuración compartido para scripts de sincronización y despliegue
# Este archivo debe ser incluido por otros scripts: source sync_config.sh

# Obtener ruta absoluta al directorio deploy-tools
if [ -z "$DEPLOY_TOOLS_DIR" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  DEPLOY_TOOLS_DIR="$(dirname "$SCRIPT_DIR")"
fi

# Cargar variables de entorno desde .env antes de cualquier otra operación
load_env() {
  if [ -f "$DEPLOY_TOOLS_DIR/deploy-tools.env" ]; then
    source "$DEPLOY_TOOLS_DIR/deploy-tools.env"
  fi
  
  if [ -n "$PROJECT_ENV_PATH" ] && [ -f "$DEPLOY_TOOLS_DIR/$PROJECT_ENV_PATH" ]; then
    ENV_FILE="$DEPLOY_TOOLS_DIR/$PROJECT_ENV_PATH"
  else
    ENV_FILE=".env"
  fi
  
  if [ -f "$ENV_FILE" ]; then
    echo "📋 Cargando configuración desde archivo $ENV_FILE..."
    # Leer línea por línea para evitar problemas con comentarios y líneas vacías
    while IFS= read -r line || [ -n "$line" ]; do
      # Ignorar líneas vacías y comentarios
      if [[ ! -z "$line" && ! "$line" =~ ^[[:space:]]*# ]]; then
        # Extraer la clave y el valor
        key=$(echo "$line" | cut -d= -f1)
        value=$(echo "$line" | cut -d= -f2-)
        
        # Eliminar espacios al inicio y final de la clave
        key=$(echo "$key" | xargs)
        
        # Verificar si la clave es válida
        if [[ "$key" =~ ^[a-zA-Z0-9_]+$ ]]; then
          # Eliminar comentarios al final de la línea si existen
          value=$(echo "$value" | sed 's/[[:space:]]*#.*$//')
          
          # Exportar la variable
          export "$key=$value"
        fi
      fi
    done < "$ENV_FILE"
  else
    echo "📝 No se encontró archivo $ENV_FILE. Usando valores predeterminados."
    echo "   Para personalizar, crea un archivo .env basado en templates/ejemplo.env."
  fi
}

# Cargar variables desde .env al inicio
load_env

# ======== CONFIGURACIÓN PRINCIPAL ========
# Usar valores del .env o establecer valores predeterminados
: ${REMOTE_SSH:=${REMOTE_SSH_ALIAS:-"ttContaboUsWest"}}
: ${REMOTE_PATH:="/home/runcloud/webapps/tiendattamayocom/"}
: ${LOCAL_PATH:="/home/aficio/Documents/DevelopmentV2/tiendattamayocom/app/public/"}

# Mostrar configuración cargada
echo "🔧 Configuración cargada:"
echo "   - SSH Remoto: $REMOTE_SSH"
echo "   - Ruta Remota: $REMOTE_PATH"
echo "   - Ruta Local: $LOCAL_PATH"

# Rutas completas
SOURCE="${REMOTE_SSH}:${REMOTE_PATH}"
DEST="${LOCAL_PATH}"

# ======== EXCLUSIONES ========
# Lista unificada de exclusiones (se usará tanto para rsync como para limpieza local)
declare -A EXCLUSIONS=(
  # Directorios de caché y optimización
  ["cache"]="wp-content/cache/"
  ["litespeed"]="wp-content/litespeed/"
  ["jetpack-waf"]="wp-content/jetpack-waf/"
  ["wflogs"]="wp-content/wflogs/"
  ["rabbitloader"]="wp-content/rabbitloader/"
  
  # Archivos de caché y configuración
  ["object-cache"]="wp-content/object-cache.php"
  ["litespeed_conf"]="wp-content/.litespeed_conf.dat"
  ["patchstack-mu"]="wp-content/mu-plugins/_patchstack.php"
  
  # Plugins de caché y optimización
  ["akismet"]="wp-content/plugins/akismet/"
  ["patchstack"]="wp-content/plugins/patchstack/"
  ["autoptimize"]="wp-content/plugins/autoptimize/"
  ["bj-lazy-load"]="wp-content/plugins/bj-lazy-load/"
  ["cdn-enabler"]="wp-content/plugins/cdn-enabler/"
  ["critical-css"]="wp-content/plugins/critical-css-for-wp/"
  ["elasticpress"]="wp-content/plugins/elasticpress/"
  ["jetpack"]="wp-content/plugins/jetpack/"
  ["jetpack-search"]="wp-content/plugins/jetpack-search/"
  ["lazy-load-comments"]="wp-content/plugins/lazy-load-for-comments/"
  ["malcare-security"]="wp-content/plugins/malcare-security/"
  ["migrate-guru"]="wp-content/plugins/migrate-guru/"
  ["object-cache-pro"]="wp-content/plugins/object-cache-pro/"
  ["rabbitloader-plugin"]="wp-content/plugins/rabbit-loader/"
  ["cloudflare-turnstile"]="wp-content/plugins/simple-cloudflare-turnstile/"
  ["wp-ses"]="wp-content/plugins/wp-ses/"
  ["litespeed-cache"]="wp-content/plugins/litespeed-cache/"
  ["wordfence"]="wp-content/plugins/wordfence/"
  ["wp-maintenance-mode"]="wp-content/plugins/wp-maintenance-mode/"
  
  # Temas predeterminados
  ["default-themes"]="wp-content/themes/twenty*"
  
  # Directorios de uploads por año
  ["uploads-by-year"]="wp-content/uploads/[0-9][0-9][0-9][0-9]/"
)

# Archivos protegidos (no se borrarán en destino)
PROTECTED_FILES=(
  'wp-config.php'
  'wp-config-ddev.php'
  '.gitignore'
  '.ddev/'
)

# ======== FUNCIONES REUTILIZABLES ========

# Crear archivo temporal de reglas para rsync
create_rules_file() {
  local exclude_file=$(mktemp)
  
  # Añadir las reglas al archivo (el orden es importante)
  # Primero incluir los archivos protegidos
  for file in "${PROTECTED_FILES[@]}"; do
    echo "protect $file" >> "$exclude_file"
  done
  
  # Luego excluir los patrones definidos
  for key in "${!EXCLUSIONS[@]}"; do
    echo "- ${EXCLUSIONS[$key]}" >> "$exclude_file"
  done
  
  echo "$exclude_file"
}

# Ejecutar rsync con las reglas configuradas
# $1: opciones adicionales, $2: origen, $3: destino
run_rsync() {
  local options="$1"
  local src="${2:-$SOURCE}"
  local dst="${3:-$DEST}"
  
  # Crear archivo de reglas
  local rules_file=$(create_rules_file)
  
  # Mostrar configuración
  echo "Usando el siguiente archivo de reglas:"
  cat "$rules_file"
  echo ""
  
  # Construir comando base de rsync
  local base_cmd=("rsync" "-e" "ssh" "--filter=merge ${rules_file}")
  
  # Agregar opciones
  for opt in $options; do
    base_cmd+=("$opt")
  done
  
  # Agregar origen y destino
  base_cmd+=("$src" "$dst")
  
  # Ejecutar comando
  echo "Ejecutando: ${base_cmd[*]}"
  "${base_cmd[@]}"
  
  # Limpiar archivo temporal
  rm -f "$rules_file"
}

# Función para limpiar directorios excluidos localmente
clean_excluded_paths() {
  echo "🧹 Limpiando directorios y archivos locales excluidos..."
  for key in "${!EXCLUSIONS[@]}"; do
    # Eliminar el slash final si existe para hacer la comprobación de archivos más confiable
    clean_path="${EXCLUSIONS[$key]%/}"
    target="${DEST%/}/$clean_path"
    
    # Verificar si el elemento existe (como archivo o directorio)
    if [ -e "$target" ]; then
      echo "   Eliminando: $key (${EXCLUSIONS[$key]})..."
      rm -rf "$target"
    fi
  done
}

# Verificar y arreglar wp-config.php para DDEV
fix_wp_config_for_ddev() {
  WP_CONFIG_PATH="${DEST%/}/wp-config.php"
  WP_CONFIG_DDEV_PATH="${DEST%/}/wp-config-ddev.php"

  if [ -f "$WP_CONFIG_PATH" ] && [ -f "$WP_CONFIG_DDEV_PATH" ]; then
    echo "🔍 Verificando que wp-config.php incluya la configuración DDEV..."
    
    if ! grep -q "wp-config-ddev.php" "$WP_CONFIG_PATH"; then
      echo "⚙️ Corrigiendo wp-config.php para incluir configuración DDEV..."
      
      # Hacer una copia de seguridad del wp-config.php original
      cp "$WP_CONFIG_PATH" "${WP_CONFIG_PATH}.bak"
      
      # Añadir el código para incluir wp-config-ddev.php al principio del archivo
      DDEV_CONFIG_CODE="<?php\n// DDEV configuration\n\$ddev_settings = dirname(__FILE__) . '/wp-config-ddev.php';\nif (is_readable(\$ddev_settings) && !defined('DB_USER')) {\n  require_once(\$ddev_settings);\n}\n\n"
      
      # Insertar el código al principio del archivo
      sed -i "1s|^|$DDEV_CONFIG_CODE|" "$WP_CONFIG_PATH"
      
      echo "✅ wp-config.php actualizado para DDEV."
    else
      echo "✅ wp-config.php ya incluye la configuración DDEV."
    fi
  else
    if [ ! -f "$WP_CONFIG_DDEV_PATH" ]; then
      echo "⚠️ No se encontró wp-config-ddev.php. DDEV podría no funcionar correctamente."
    fi
    
    if [ ! -f "$WP_CONFIG_PATH" ]; then
      echo "⚠️ No se encontró wp-config.php después de la sincronización."
    fi
  fi
}

# Verificar si estamos en un repositorio git
is_git_repo() {
  if [ -d "$DEST/.git" ] || git -C "$DEST" rev-parse --is-inside-work-tree &>/dev/null; then
    return 0  # Es un repositorio git
  else
    return 1  # No es un repositorio git
  fi
}

# Verificar requisitos comunes
check_requirements() {
  # Verificar DDEV si es necesario
  if [ "$1" = "ddev" ]; then
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
  fi
  
  # Verificar SSH
  if ! command -v ssh &> /dev/null; then
    echo "❌ Error: SSH no está instalado. Por favor, instálalo primero."
    exit 1
  fi
  
  # Verificar que el host SSH está configurado
  if ! grep -q "^Host $REMOTE_SSH$" ~/.ssh/config &> /dev/null; then
    echo "⚠️ Advertencia: El host SSH '$REMOTE_SSH' no parece estar configurado en ~/.ssh/config."
    echo "   Asegúrate de que puedes conectarte usando: ssh $REMOTE_SSH"
  fi
}

# Verificar flag de seguridad de producción
check_production_safety() {
  local operation="$1"
  
  # Cargar variables de entorno si aún no se han cargado
  if [ -z "$PRODUCTION_SAFETY" ]; then
    load_env
  fi
  
  # Verificar si el flag de seguridad está activo
  if [ "$PRODUCTION_SAFETY" = "enabled" ]; then
    echo "⚠️ ADVERTENCIA: Protección de producción está activada."
    echo "   Esta operación ($operation) modificaría datos en PRODUCCIÓN."
    
    # Solicitar confirmación explícita
    read -p "   ¿Estás COMPLETAMENTE SEGURO de continuar? (escriba 'si' para confirmar): " confirm
    
    if [ "$confirm" != "si" ]; then
      echo "❌ Operación cancelada por seguridad."
      exit 1
    fi
    
    echo "⚡ Confirmación recibida. Procediendo con la operación..."
    echo ""
  fi
}

# Función para comprobar si una operación afecta a producción
is_production_operation() {
  local operation="$1"
  
  case "$operation" in
    "apply-patches"|"rollback"|"deploy"|"push")
      return 0  # Es una operación que afecta a producción
      ;;
    *)
      return 1  # No es una operación que afecta a producción
      ;;
  esac
}
