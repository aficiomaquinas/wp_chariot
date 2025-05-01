#!/bin/bash

# Script para mostrar diferencias entre servidor remoto y entorno local

# Importar configuración compartida
DEPLOY_TOOLS_DIR="$(dirname "$(dirname "$0")")"
source "$DEPLOY_TOOLS_DIR/scripts/sync_config.sh"

# Verificar requisitos
check_requirements

# Función para generar el diff detallado
generate_diff() {
  # Crear un archivo temporal para las reglas de exclusión e inclusión
  local exclude_file=$(create_rules_file)
  
  # Construir el comando rsync con dry-run para ver qué cambiaría sin hacer cambios
  local cmd=("rsync" "-avzn" "--itemize-changes" "--delete" "-e" "ssh" "--filter=merge ${exclude_file}")
  cmd+=("$SOURCE" "$DEST")
  
  # Crear archivo temporal para la salida del diff
  local diff_output=$(mktemp)
  
  # Ejecutar el comando y guardar la salida
  echo "Generando diff entre servidor remoto y local..."
  echo "Usando el siguiente archivo de reglas:"
  cat "$exclude_file"
  echo ""
  echo "Ejecutando: ${cmd[*]}"
  "${cmd[@]}" | tee "$diff_output"
  
  # Analizar y formatear la salida del diff
  echo ""
  echo "===================== RESUMEN DEL DIFF ====================="
  echo ""
  
  # Contar archivos nuevos, modificados y eliminados
  local new_files=$(grep -c "^>" "$diff_output" || echo "0")
  local del_files=$(grep -c "^<" "$diff_output" || echo "0")
  local changed_files=$(grep -c "^.s" "$diff_output" || echo "0")
  
  echo "Archivos nuevos en el servidor: $new_files"
  echo "Archivos modificados: $changed_files"
  echo "Archivos eliminados en el servidor: $del_files"
  
  # Mostrar ejemplos de archivos cambiados
  echo ""
  echo "Ejemplos de archivos modificados:"
  grep "^.s" "$diff_output" | head -50 | awk '{print $2}'
  
  # Mostrar ejemplos de archivos nuevos
  echo ""
  echo "Ejemplos de archivos nuevos en el servidor:"
  grep "^>" "$diff_output" | head -50 | awk '{print $2}'
  
  # Limpiar archivos temporales
  rm -f "$exclude_file" "$diff_output"
}

# Función para generar lista de archivos modificados localmente
generate_local_changes() {
  echo ""
  echo "===================== CAMBIOS LOCALES ====================="
  echo ""
  echo "Archivos que han sido modificados localmente:"
  
  # Crear un archivo temporal para las reglas
  local exclude_file=$(create_rules_file)
  
  # Generar lista de archivos modificados (dirección opuesta)
  local cmd=("rsync" "-avzn" "--itemize-changes" "-e" "ssh" "--filter=merge ${exclude_file}")
  cmd+=("$DEST" "$SOURCE")
  
  # Ejecutar y filtrar solo los archivos modificados
  "${cmd[@]}" | grep "^.s" | awk '{print $2}'
  
  # Limpiar
  rm -f "$exclude_file"
}

# Menú principal
echo "🔍 Diff entre servidor remoto y local"
echo "------------------------------------"
echo "1) Ver qué cambiaría al sincronizar desde el servidor (diff detallado)"
echo "2) Ver archivos modificados localmente"
echo "3) Ambos"
echo "0) Salir"
echo ""
read -p "Seleccione una opción [1-3]: " option

case $option in
  1)
    generate_diff
    ;;
  2)
    generate_local_changes
    ;;
  3)
    generate_diff
    generate_local_changes
    ;;
  0)
    echo "Saliendo..."
    exit 0
    ;;
  *)
    echo "Opción inválida. Saliendo..."
    exit 1
    ;;
esac

echo "🎉 Proceso completado exitosamente!" 