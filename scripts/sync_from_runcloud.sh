#!/bin/bash

# Script para sincronizar archivos desde el servidor de producción al entorno local

# Importar configuración compartida
DEPLOY_TOOLS_DIR="$(dirname "$(dirname "$0")")"
source "$DEPLOY_TOOLS_DIR/scripts/sync_config.sh"

# Verificar requisitos
check_requirements

# Ejecutar sincronización
echo "🔄 Iniciando sincronización..."
run_rsync "-avz --progress --delete"
echo "✅ Sincronización completa!"

# Limpieza local de elementos excluidos
clean_excluded_paths

# Arreglar configuración DDEV
fix_wp_config_for_ddev

echo "🎉 Proceso completado exitosamente!"
