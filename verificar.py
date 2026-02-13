#!/usr/bin/env python3
"""
Script de verificación PRE-MIGRACIÓN
Ejecutar ANTES de migrate_por_fases.py para conocer el estado
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

def construir_url_mysql():
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "Prometeus.0")
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DATABASE", "test_api")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

def construir_url_postgres():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "secreto123")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "hospital")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

print("=" * 80)
print("🔍 VERIFICACIÓN PRE-MIGRACIÓN")
print("=" * 80)

# ============================================================================
# MYSQL
# ============================================================================

print("\n📊 ANÁLISIS DE MYSQL")
print("-" * 80)

mysql_engine = create_engine(construir_url_mysql(), echo=False)
MySQLSession = sessionmaker(bind=mysql_engine)
mysql_db = MySQLSession()

try:
    # Pacientes
    total_pacientes = mysql_db.execute(text("SELECT COUNT(*) FROM pacientes")).scalar()
    print(f"Pacientes:                {total_pacientes:,}")
    
    # Consultas
    total_consultas = mysql_db.execute(text("SELECT COUNT(*) FROM consultas")).scalar()
    print(f"Consultas:                {total_consultas:,}")
    
    # Consultas con expediente válido
    cons_con_exp = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas 
        WHERE expediente IS NOT NULL AND expediente != 0
    """)).scalar()
    print(f"  └─ Con expediente:      {cons_con_exp:,} ({cons_con_exp/total_consultas*100:.1f}%)")
    
    # Consultas con DPI válido
    cons_con_dpi = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas 
        WHERE dpi IS NOT NULL AND CHAR_LENGTH(TRIM(dpi)) = 13
    """)).scalar()
    print(f"  └─ Con DPI válido:      {cons_con_dpi:,} ({cons_con_dpi/total_consultas*100:.1f}%)")
    
    # Consultas sin expediente ni DPI
    cons_sin_id = total_consultas - cons_con_exp
    print(f"  └─ Sin expediente/DPI:  {cons_sin_id:,} ({cons_sin_id/total_consultas*100:.1f}%)")
    
    # Verificar campo exp_ref
    print("\n🔍 Verificando campo exp_ref...")
    try:
        resultado = mysql_db.execute(text("""
            SELECT COUNT(*) 
            FROM information_schema.columns 
            WHERE table_schema = DATABASE()
            AND table_name = 'pacientes' 
            AND column_name = 'exp_ref'
        """))
        tiene_exp_ref = resultado.scalar() > 0
        
        if tiene_exp_ref:
            # Contar cuántos tienen exp_ref diferente
            con_exp_ref = mysql_db.execute(text("""
                SELECT COUNT(*) FROM pacientes 
                WHERE exp_ref IS NOT NULL 
                AND exp_ref != 0
                AND exp_ref != expediente
            """)).scalar()
            print(f"✅ Campo exp_ref existe")
            print(f"   Pacientes con exp_ref: {con_exp_ref:,}")
            if con_exp_ref > 0:
                print(f"   → FASE 2 recuperará consultas antiguas")
        else:
            print(f"⚠️  Campo exp_ref NO existe")
            print(f"   → FASE 2 se omitirá")
    except Exception as e:
        print(f"⚠️  Error verificando exp_ref: {e}")

finally:
    mysql_db.close()
    mysql_engine.dispose()

# ============================================================================
# POSTGRESQL
# ============================================================================

print("\n📊 ANÁLISIS DE POSTGRESQL")
print("-" * 80)

postgres_engine = create_engine(construir_url_postgres(), echo=False)
PostgresSession = sessionmaker(bind=postgres_engine)
postgres_db = PostgresSession()

try:
    # Pacientes actuales
    pac_actuales = postgres_db.execute(text("SELECT COUNT(*) FROM pacientes")).scalar()
    print(f"Pacientes actuales:       {pac_actuales:,}")
    
    if pac_actuales > 0:
        print("⚠️  Ya hay pacientes en PostgreSQL")
        print("   El script manejará duplicados automáticamente")
        
        # CUI únicos
        cui_unicos = postgres_db.execute(text("""
            SELECT COUNT(DISTINCT cui) FROM pacientes WHERE cui IS NOT NULL
        """)).scalar()
        print(f"   CUI únicos:            {cui_unicos:,}")
    else:
        print("✅ Base PostgreSQL vacía - migración limpia")
    
    # Consultas actuales
    cons_actuales = postgres_db.execute(text("SELECT COUNT(*) FROM consultas")).scalar()
    print(f"Consultas actuales:       {cons_actuales:,}")

finally:
    postgres_db.close()
    postgres_engine.dispose()

# ============================================================================
# PREDICCIONES
# ============================================================================

print("\n" + "=" * 80)
print("📈 PREDICCIÓN DE MIGRACIÓN")
print("=" * 80)

print(f"\nFASE 1: Pacientes + Consultas exactas")
print(f"  Pacientes a migrar:     {total_pacientes:,}")
print(f"  Consultas a migrar:     ~{cons_con_exp:,} ({cons_con_exp/total_consultas*100:.1f}%)")

if tiene_exp_ref and con_exp_ref > 0:
    print(f"\nFASE 2: Consultas con exp_ref")
    print(f"  Consultas a recuperar:  ~{con_exp_ref * 2:,} (estimado)")

print(f"\nFASE 3: Consultas por DPI")
print(f"  Consultas a vincular:   ~{cons_con_dpi - cons_con_exp:,} (estimado)")

if cons_sin_id > 0:
    # Estimar grupos únicos
    grupos_unicos = mysql_db.execute(text("""
        SELECT COUNT(DISTINCT CONCAT(IFNULL(nombres, ''), IFNULL(apellidos, ''), IFNULL(nacimiento, '')))
        FROM consultas
        WHERE (expediente IS NULL OR expediente = 0)
        AND nombres IS NOT NULL
        AND apellidos IS NOT NULL
    """)).scalar()
    
    print(f"\nFASE 4: Sin expediente")
    print(f"  Pacientes sintéticos:   ~{grupos_unicos:,}")
    print(f"  Consultas a migrar:     ~{cons_sin_id:,}")

print(f"\n" + "=" * 80)
print("TOTAL ESTIMADO:")
print(f"  Pacientes:  {total_pacientes + (grupos_unicos if cons_sin_id > 0 else 0):,}")
print(f"  Consultas:  {total_consultas:,}")
print("=" * 80)

print("\n✅ Verificación completada")
print("\n💡 Siguiente paso:")
print("   python migrate_por_fases.py")