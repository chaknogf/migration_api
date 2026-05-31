#!/usr/bin/env bash

set -euo pipefail

trap 'echo ""; echo "❌ Error en la línea $LINENO"; exit 1' ERR

PROJECT_DIR="/Users/macbookairm2/Project/hosprojects/migration_api"

echo "======================================================"
echo "     MIGRACIÓN COMPLETA MYSQL → POSTGRESQL"
echo "======================================================"

echo ""
echo "📂 Entrando al proyecto..."
cd "$PROJECT_DIR"

echo ""
echo "[1/7] Restaurando MySQL..."
./restaurar_mysql.sh

echo ""
echo "[2/7] Activando entorno virtual..."
source .venv/bin/activate

echo ""
echo "[3/7] Preparando datos MySQL..."
python3 preparar_mysql_optimizado.py

echo ""
echo "[4/7] Migrando médicos..."
python3 migrate_medicos.py

echo ""
echo "[5/7] Migrando pacientes y consultas..."
python3 migrar_postgres.py

echo ""
echo "[6/7] Migrando citas..."
python3 migrate_citas.py

echo ""
echo "[7/7] Generando y enviando backup PostgreSQL..."
python3 backup_postgres.py

echo ""
echo "======================================================"
echo "✓ PROCESO COMPLETADO CORRECTAMENTE"
echo "======================================================"