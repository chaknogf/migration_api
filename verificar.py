#!/usr/bin/env python3
"""
Script de verificación PRE-MIGRACIÓN
Ejecutar ANTES de migrate_por_fases.py para conocer el estado actual
de MySQL y PostgreSQL, y estimar qué ocurrirá en cada fase de migración.

Genera un reporte CSV con toda la información recolectada.
NO modifica ningún dato.
"""

import os
import csv
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

def construir_url_mysql():
    user     = os.getenv("MYSQL_USER",     "root")
    password = os.getenv("MYSQL_PASSWORD", "Prometeus.0")
    host     = os.getenv("MYSQL_HOST",     "localhost")
    port     = os.getenv("MYSQL_PORT",     "3306")
    database = os.getenv("MYSQL_DATABASE", "test_api")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

def construir_url_postgres():
    user     = os.getenv("POSTGRES_USER",     "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "secreto123")
    host     = os.getenv("POSTGRES_HOST",     "localhost")
    port     = os.getenv("POSTGRES_PORT",     "5432")
    database = os.getenv("POSTGRES_DB",       "hospital")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

TIMESTAMP                   = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_REPORTE                 = f"reporte_pre_migracion_{TIMESTAMP}.csv"
CSV_SIN_COINCIDENCIA        = f"diagnostico_sin_coincidencia_{TIMESTAMP}.csv"
CSV_MULTIPLES_COINCIDENCIAS = f"diagnostico_multiples_coincidencias_{TIMESTAMP}.csv"

# Acumuladores
filas_csv           = []
registros_sin       = []
registros_multiples = []

def registrar(seccion, metrica, valor, detalle=""):
    """Agrega una fila al reporte resumen CSV."""
    filas_csv.append({
        "seccion":  seccion,
        "metrica":  metrica,
        "valor":    valor,
        "detalle":  detalle,
    })

def normalizar_texto(texto):
    """Normaliza texto para comparación (minúsculas, sin espacios extra, sin acentos)."""
    if not texto:
        return None
    t = str(texto).lower().strip()
    t = ' '.join(t.split())
    for viejo, nuevo in {
        'á':'a','é':'e','í':'i','ó':'o','ú':'u',
        'ä':'a','ë':'e','ï':'i','ö':'o','ü':'u',
        'à':'a','è':'e','ì':'i','ò':'o','ù':'u','ñ':'n'
    }.items():
        t = t.replace(viejo, nuevo)
    return t

# ============================================================================
# ENCABEZADO
# ============================================================================

print("=" * 80)
print("🔍 VERIFICACIÓN PRE-MIGRACIÓN")
print("=" * 80)
print("\n📌 Este script SOLO lee datos — no modifica nada en MySQL ni PostgreSQL.")
print(f"   Al finalizar se generará el archivo: {CSV_REPORTE}")
print("=" * 80)

# ============================================================================
# MYSQL
# ============================================================================

print("\n" + "─" * 80)
print("📦 MYSQL — Estado actual de la base de datos origen")
print("─" * 80)

mysql_engine = create_engine(construir_url_mysql(), echo=False)
MySQLSession  = sessionmaker(bind=mysql_engine)
mysql_db      = MySQLSession()

tiene_exp_ref = False
con_exp_ref   = 0
grupos_unicos = 0

try:
    # ── Pacientes ──────────────────────────────────────────────────────────
    total_pacientes = mysql_db.execute(text("SELECT COUNT(*) FROM pacientes")).scalar()
    print(f"\n  👥 Pacientes registrados:          {total_pacientes:>10,}")
    registrar("MySQL - Pacientes", "Total pacientes", total_pacientes)

    # ── Consultas ──────────────────────────────────────────────────────────
    total_consultas = mysql_db.execute(text("SELECT COUNT(*) FROM consultas")).scalar()
    print(f"\n  📋 Consultas registradas:          {total_consultas:>10,}")
    registrar("MySQL - Consultas", "Total consultas", total_consultas)

    cons_con_exp = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE expediente IS NOT NULL AND expediente != 0
    """)).scalar()
    pct_exp = cons_con_exp / total_consultas * 100 if total_consultas else 0
    print(f"     ✅ Con expediente asignado:      {cons_con_exp:>10,}  ({pct_exp:.1f}%)")
    registrar("MySQL - Consultas", "Con expediente asignado", cons_con_exp, f"{pct_exp:.1f}% del total")

    cons_con_dpi = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE dpi IS NOT NULL AND CHAR_LENGTH(TRIM(dpi)) = 13
    """)).scalar()
    pct_dpi = cons_con_dpi / total_consultas * 100 if total_consultas else 0
    print(f"     🪪 Con DPI válido (13 dígitos):  {cons_con_dpi:>10,}  ({pct_dpi:.1f}%)")
    registrar("MySQL - Consultas", "Con DPI válido (13 dígitos)", cons_con_dpi, f"{pct_dpi:.1f}% del total")

    cons_sin_id = total_consultas - cons_con_exp
    pct_sin = cons_sin_id / total_consultas * 100 if total_consultas else 0
    print(f"     ❌ Sin expediente:               {cons_sin_id:>10,}  ({pct_sin:.1f}%)")
    registrar("MySQL - Consultas", "Sin expediente", cons_sin_id, f"{pct_sin:.1f}% del total")

    # ── Campo exp_ref ──────────────────────────────────────────────────────
    print(f"\n  🔎 Verificando campo 'exp_ref' en tabla pacientes...")

    existe_col = mysql_db.execute(text("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name   = 'pacientes'
          AND column_name  = 'exp_ref'
    """)).scalar()
    tiene_exp_ref = existe_col > 0

    if tiene_exp_ref:
        con_exp_ref = mysql_db.execute(text("""
            SELECT COUNT(*) FROM pacientes
            WHERE exp_ref IS NOT NULL
              AND exp_ref != 0
              AND exp_ref != expediente
        """)).scalar()
        impacto = "FASE 2 recuperará consultas antiguas vinculadas a este campo" if con_exp_ref > 0 else "No hay pacientes con exp_ref distinto — FASE 2 no aportará datos nuevos"
        print(f"     ✅ Campo 'exp_ref' existe en la tabla")
        print(f"        Pacientes con exp_ref diferente al expediente: {con_exp_ref:,}")
        print(f"        → {impacto}")
        registrar("MySQL - exp_ref", "Campo exp_ref existe", "Sí")
        registrar("MySQL - exp_ref", "Pacientes con exp_ref distinto", con_exp_ref, impacto)
    else:
        print(f"     ⚠️  Campo 'exp_ref' NO existe en la tabla pacientes")
        print(f"        → FASE 2 se omitirá durante la migración")
        registrar("MySQL - exp_ref", "Campo exp_ref existe", "No", "FASE 2 se omitirá")

    # ── Grupos únicos sin expediente (para FASE 4) ─────────────────────────
    if cons_sin_id > 0:
        grupos_unicos = mysql_db.execute(text("""
            SELECT COUNT(DISTINCT CONCAT(
                IFNULL(nombres, ''), '|',
                IFNULL(apellidos, ''), '|',
                IFNULL(nacimiento, '')
            ))
            FROM consultas
            WHERE (expediente IS NULL OR expediente = 0)
              AND nombres   IS NOT NULL
              AND apellidos IS NOT NULL
        """)).scalar()
        print(f"\n  👤 Grupos únicos sin expediente:   {grupos_unicos:>10,}")
        print(f"     (identificados por nombre + apellido + fecha de nacimiento)")
        print(f"     → FASE 4 creará ~{grupos_unicos:,} pacientes sintéticos para estas consultas")
        registrar("MySQL - Sin expediente", "Grupos únicos (nombre+apellido+nacimiento)", grupos_unicos,
                  f"FASE 4 creará ~{grupos_unicos} pacientes sintéticos")
        registrar("MySQL - Sin expediente", "Consultas sin expediente a migrar", cons_sin_id)

finally:
    mysql_db.close()
    mysql_engine.dispose()

# ============================================================================
# POSTGRESQL
# ============================================================================

print("\n" + "─" * 80)
print("🐘 POSTGRESQL — Estado actual de la base de datos destino")
print("─" * 80)

postgres_engine = create_engine(construir_url_postgres(), echo=False)
PostgresSession  = sessionmaker(bind=postgres_engine)
postgres_db      = PostgresSession()

try:
    pac_actuales = postgres_db.execute(text("SELECT COUNT(*) FROM pacientes")).scalar()
    print(f"\n  👥 Pacientes ya en PostgreSQL:     {pac_actuales:>10,}")
    registrar("PostgreSQL - Estado actual", "Pacientes existentes", pac_actuales)

    if pac_actuales > 0:
        cui_unicos = postgres_db.execute(text("""
            SELECT COUNT(DISTINCT cui) FROM pacientes WHERE cui IS NOT NULL
        """)).scalar()
        print(f"     ⚠️  La base NO está vacía — la migración manejará duplicados automáticamente")
        print(f"        CUI únicos registrados: {cui_unicos:,}")
        registrar("PostgreSQL - Estado actual", "CUI únicos existentes", cui_unicos,
                  "Base no vacía — se manejarán duplicados automáticamente")
    else:
        print(f"     ✅ Base vacía — la migración será limpia, sin riesgo de duplicados")
        registrar("PostgreSQL - Estado actual", "Estado", "Vacía", "Migración limpia sin duplicados")

    cons_actuales = postgres_db.execute(text("SELECT COUNT(*) FROM consultas")).scalar()
    print(f"\n  📋 Consultas ya en PostgreSQL:     {cons_actuales:>10,}")
    registrar("PostgreSQL - Estado actual", "Consultas existentes", cons_actuales)

finally:
    postgres_db.close()
    postgres_engine.dispose()

# ============================================================================
# PREDICCIÓN POR FASES
# ============================================================================

print("\n" + "=" * 80)
print("📈 PREDICCIÓN DE MIGRACIÓN — Qué se espera en cada fase")
print("=" * 80)

estimado_pacientes  = total_pacientes + grupos_unicos
estimado_consultas  = total_consultas

fase2_consultas = con_exp_ref * 2 if tiene_exp_ref and con_exp_ref > 0 else 0
fase3_consultas = max(cons_con_dpi - cons_con_exp, 0)

print(f"""
  FASE 1 — Pacientes + Consultas con expediente exacto
  ─────────────────────────────────────────────────────
    Pacientes a migrar:                  {total_pacientes:>10,}
    Consultas a migrar:                  {cons_con_exp:>10,}  ({pct_exp:.1f}% del total)
    Método: relación directa expediente → paciente
""")
registrar("Predicción FASE 1", "Pacientes a migrar", total_pacientes)
registrar("Predicción FASE 1", "Consultas a migrar", cons_con_exp, f"{pct_exp:.1f}% del total")

if tiene_exp_ref and con_exp_ref > 0:
    print(f"  FASE 2 — Consultas vinculadas por exp_ref (expediente de referencia)")
    print(f"  ─────────────────────────────────────────────────────")
    print(f"    Consultas a recuperar (estimado):    {fase2_consultas:>10,}")
    print(f"    Método: busca consultas del expediente antiguo (exp_ref) y las asocia al nuevo\n")
    registrar("Predicción FASE 2", "Consultas a recuperar (estimado)", fase2_consultas,
              "Consultas vinculadas por expediente de referencia")
else:
    print(f"  FASE 2 — Omitida (campo exp_ref no existe o no hay datos)\n")
    registrar("Predicción FASE 2", "Estado", "Omitida", "Campo exp_ref no existe o sin datos relevantes")

print(f"  FASE 3 — Consultas vinculadas por DPI")
print(f"  ─────────────────────────────────────────────────────")
print(f"    Consultas a vincular (estimado):     {fase3_consultas:>10,}")
print(f"    Método: cruza el DPI de la consulta con el DPI del paciente en la tabla pacientes\n")
registrar("Predicción FASE 3", "Consultas a vincular (estimado)", fase3_consultas,
          "Cruce por DPI entre consultas y pacientes")

if cons_sin_id > 0:
    print(f"  FASE 4 — Consultas sin expediente ni DPI")
    print(f"  ─────────────────────────────────────────────────────")
    print(f"    Pacientes sintéticos a crear:        {grupos_unicos:>10,}")
    print(f"    Consultas a migrar:                  {cons_sin_id:>10,}")
    print(f"    Método: agrupa por nombre + apellido + nacimiento y crea un paciente temporal\n")
    registrar("Predicción FASE 4", "Pacientes sintéticos a crear", grupos_unicos)
    registrar("Predicción FASE 4", "Consultas a migrar", cons_sin_id,
              "Agrupadas por nombre + apellido + fecha de nacimiento")
else:
    print(f"  FASE 4 — No aplica (todas las consultas tienen expediente)\n")
    registrar("Predicción FASE 4", "Estado", "No aplica", "Todas las consultas tienen expediente")

print("─" * 80)
print(f"  TOTAL ESTIMADO AL FINALIZAR LA MIGRACIÓN")
print("─" * 80)
print(f"    Pacientes en PostgreSQL:             {estimado_pacientes:>10,}")
print(f"    Consultas en PostgreSQL:             {estimado_consultas:>10,}")
print("─" * 80)

registrar("Totales estimados", "Pacientes totales en PostgreSQL", estimado_pacientes)
registrar("Totales estimados", "Consultas totales en PostgreSQL", estimado_consultas)

# ============================================================================
# EXPORTAR CSV
# ============================================================================

print(f"\n📁 Generando reporte CSV...")

with open(CSV_REPORTE, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["seccion", "metrica", "valor", "detalle"])
    writer.writeheader()
    writer.writerows(filas_csv)

print(f"   ✅ Reporte guardado: {CSV_REPORTE}")

# ============================================================================
# CIERRE
# ============================================================================

print("\n" + "=" * 80)
print("✅ Verificación completada — no se modificó ningún dato")
print("=" * 80)
print("\n💡 PRÓXIMO PASO:")
print("   Revisa el CSV generado y luego ejecuta la migración:")
print("   python migrate_por_fases.py")
print()