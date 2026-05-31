#!/bin/bash

# =========================================================
# Script: restaurar_mysql.sh
# Descripción:
#   Elimina, crea e importa una base MySQL desde un .sql
# =========================================================

# -------- CONFIGURACIÓN --------
DB_NAME="test_api"
DB_USER="root"
SQL_FILE="/Users/macbookairm2/base.sql"

# -------- VALIDACIONES --------

if [ ! -f "$SQL_FILE" ]; then
    echo "❌ Error: No existe el archivo $SQL_FILE"
    exit 1
fi

echo "======================================"
echo " RESTAURACIÓN COMPLETA MYSQL"
echo "======================================"
echo " Base de datos : $DB_NAME"
echo " Archivo SQL   : $SQL_FILE"
echo "======================================"

# -------- ELIMINAR Y CREAR BASE --------
echo "🗑️  Eliminando base de datos existente..."

mysql -u "$DB_USER" -p -e "
DROP DATABASE IF EXISTS \`$DB_NAME\`;
CREATE DATABASE \`$DB_NAME\`
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
"

if [ $? -ne 0 ]; then
    echo "❌ Error al crear la base de datos."
    exit 1
fi

echo "✅ Base de datos creada correctamente."

# -------- IMPORTAR RESPALDO --------
echo "📥 Importando respaldo SQL..."

mysql -u "$DB_USER" -p "$DB_NAME" < "$SQL_FILE"

# -------- RESULTADO FINAL --------
if [ $? -eq 0 ]; then
    echo "======================================"
    echo "✅ Restauración completada correctamente."
    echo "======================================"
else
    echo "======================================"
    echo "❌ Error durante la importación."
    echo "======================================"
fi