#!/bin/bash

# Script para análisis avanzado de cambios locales

# Importar configuración compartida
DEPLOY_TOOLS_DIR="$(dirname "$(dirname "$0")")"
source "$DEPLOY_TOOLS_DIR/scripts/sync_config.sh"

# Función para obtener archivos modificados usando git
get_modified_files_git() {
  echo "Detectando cambios usando Git..."
  echo ""
  
  # Cambiar al directorio de destino
  cd "$DEST" || return 1
  
  # Verificar si hay cambios sin confirmar
  if git status --porcelain | grep -q "^.M"; then
    echo "Archivos modificados según Git:"
    echo "------------------------------"
    git status --porcelain | grep "^.M" | awk '{print $2}'
    
    echo ""
    echo "Mostrando diferencias de los archivos modificados:"
    echo "------------------------------------------------"
    
    # Recorrer cada archivo modificado y mostrar el diff
    git status --porcelain | grep "^.M" | awk '{print $2}' | while read -r file; do
      echo ""
      echo "📄 $file:"
      echo "----------------"
      git diff -- "$file" | head -n 30  # Mostrar solo las primeras 30 líneas del diff
      echo ""
      echo "(Mostrados solo los primeros cambios, usa 'git diff -- $file' para ver completo)"
      echo "----------------"
    done
  else
    echo "No se detectaron archivos modificados en el repositorio Git."
  fi
}

# Función para obtener archivos modificados basándose en timestamps
get_modified_files_timestamp() {
  echo "Detectando cambios usando timestamps (esto puede ser menos preciso)..."
  echo ""
  
  # Crear un archivo temporal para las reglas
  local exclude_file=$(create_rules_file)
  
  # Buscar archivos modificados en las últimas 24 horas
  echo "Archivos modificados en las últimas 24 horas:"
  echo "-------------------------------------------"
  find "$DEST" -type f -mtime -1 | while read -r file; do
    # Verificar si el archivo debe ser excluido
    exclude=false
    rel_path="${file#$DEST}"
    
    for key in "${!EXCLUSIONS[@]}"; do
      pattern=${EXCLUSIONS[$key]}
      if [[ "$rel_path" == $pattern ]] || [[ "$rel_path" == */$pattern ]] || [[ "$rel_path" == */$pattern/* ]]; then
        exclude=true
        break
      fi
    done
    
    if [ "$exclude" = false ]; then
      echo "$rel_path"
    fi
  done
  
  # Limpiar
  rm -f "$exclude_file"
}

# Función para buscar específicamente archivos de código PHP modificados
find_code_files() {
  echo ""
  echo "Buscando archivos de código significativos modificados..."
  echo ""
  
  # Patrones de archivos importantes
  local important_patterns=(
    "wp-content/plugins/avalon-ttamayo/**/*.php"
    "wp-content/themes/avalon/**/*.php"
    "wp-content/plugins/avalon-ttamayo/**/*.js"
    "wp-content/themes/avalon/**/*.js"
    "wp-content/mu-plugins/**/*.php"
    "wp-config*.php"
  )
  
  if is_git_repo; then
    # Usar git para encontrar archivos importantes
    cd "$DEST" || return 1
    
    for pattern in "${important_patterns[@]}"; do
      echo "📁 Buscando archivos modificados que coincidan con: $pattern"
      git status --porcelain | grep "^.M" | awk '{print $2}' | grep -E "$pattern" || echo "  Ninguno encontrado"
      echo ""
    done
  else
    # Usar find para encontrar archivos importantes
    for pattern in "${important_patterns[@]}"; do
      echo "📁 Buscando archivos modificados en las últimas 72 horas que coincidan con: $pattern"
      find "$DEST" -path "$DEST/$pattern" -type f -mtime -3 || echo "  Ninguno encontrado"
      echo ""
    done
  fi
}

# Función para encontrar elementos personalizados específicos de interés 
find_custom_elements() {
  echo ""
  echo "Buscando elementos personalizados de interés..."
  echo ""
  
  # Lista de directorios/archivos personalizados a revisar
  local custom_elements=(
    "wp-content/plugins/avalon-ttamayo"
    "wp-content/mu-plugins"
    "wp-content/themes/avalon-child"
  )
  
  for element in "${custom_elements[@]}"; do
    if [ -e "$DEST/$element" ]; then
      echo "📂 Elemento personalizado encontrado: $element"
      
      # Si es un directorio, mostrar archivo más reciente
      if [ -d "$DEST/$element" ]; then
        echo "   Archivos modificados recientemente:"
        find "$DEST/$element" -type f -mtime -7 | sort -r | head -5 
      fi
      echo ""
    fi
  done
}

# Menú principal
echo "🔍 Análisis de cambios locales"
echo "-----------------------------"
echo "1) Analizar cambios usando Git (si está disponible)"
echo "2) Analizar cambios usando timestamps de archivos"
echo "3) Buscar archivos de código importantes modificados"
echo "4) Buscar elementos personalizados de interés"
echo "5) Realizar todos los análisis"
echo "0) Salir"
echo ""
read -p "Seleccione una opción [0-5]: " option

case $option in
  1)
    if is_git_repo; then
      get_modified_files_git
    else
      echo "❌ No se detectó un repositorio Git en $DEST"
      echo "   Usando método alternativo basado en timestamps..."
      get_modified_files_timestamp
    fi
    ;;
  2)
    get_modified_files_timestamp
    ;;
  3)
    find_code_files
    ;;
  4)
    find_custom_elements
    ;;
  5)
    if is_git_repo; then
      get_modified_files_git
    else
      get_modified_files_timestamp
    fi
    find_code_files
    find_custom_elements
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