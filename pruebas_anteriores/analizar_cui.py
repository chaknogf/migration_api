#!/usr/bin/env python3
"""
Script para analizar y resolver CUI duplicados
Ejecutar ANTES de migrate_enriquecido.py para decidir estrategia
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import sys

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

def construir_url_postgres():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "secreto123")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "hospital")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

POSTGRES_URL = construir_url_postgres()

print("=" * 80)
print("🔍 ANÁLISIS DE CUI DUPLICADOS EN POSTGRESQL")
print("=" * 80)

# ============================================================================
# ANÁLISIS
# ============================================================================

def analizar_cui_duplicados():
    """Analiza CUI duplicados existentes en PostgreSQL"""
    
    engine = create_engine(POSTGRES_URL, echo=False)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # 1. Contar pacientes actuales
        total_pacientes = db.execute(text(
            "SELECT COUNT(*) FROM pacientes"
        )).scalar()
        
        print(f"\n📊 Pacientes actuales en PostgreSQL: {total_pacientes:,}")
        
        # 2. Contar CUI únicos
        cui_unicos = db.execute(text(
            "SELECT COUNT(DISTINCT cui) FROM pacientes WHERE cui IS NOT NULL"
        )).scalar()
        
        cui_nulos = db.execute(text(
            "SELECT COUNT(*) FROM pacientes WHERE cui IS NULL"
        )).scalar()
        
        print(f"   CUI únicos: {cui_unicos:,}")
        print(f"   Sin CUI: {cui_nulos:,}")
        
        # 3. Detectar si hay CUI duplicados en la base actual
        duplicados_actuales = db.execute(text("""
            SELECT cui, COUNT(*) as cantidad
            FROM pacientes
            WHERE cui IS NOT NULL
            GROUP BY cui
            HAVING COUNT(*) > 1
        """)).fetchall()
        
        if duplicados_actuales:
            print(f"\n⚠️  ADVERTENCIA: Ya hay {len(duplicados_actuales)} CUI duplicados en PostgreSQL:")
            for cui, cantidad in duplicados_actuales[:10]:
                print(f"   CUI {cui}: {cantidad} registros")
            if len(duplicados_actuales) > 10:
                print(f"   ... y {len(duplicados_actuales) - 10} más")
        else:
            print(f"\n✅ No hay CUI duplicados en la base actual")
        
        # 4. Verificar restricción de unicidad
        tiene_constraint = db.execute(text("""
            SELECT COUNT(*)
            FROM pg_constraint
            WHERE conname = 'pacientes_cui_key'
        """)).scalar()
        
        if tiene_constraint:
            print(f"\n🔒 Restricción de unicidad 'pacientes_cui_key' está ACTIVA")
            print(f"   Esto impedirá insertar CUI duplicados")
        else:
            print(f"\n⚠️  Restricción de unicidad NO está activa")
        
    finally:
        db.close()
        engine.dispose()

def listar_opciones():
    """Muestra opciones de resolución"""
    
    print("\n" + "=" * 80)
    print("💡 OPCIONES DE RESOLUCIÓN")
    print("=" * 80)
    
    print("\n📌 OPCIÓN 1: Limpiar base PostgreSQL (RECOMENDADO si es migración inicial)")
    print("   • Elimina todos los pacientes y consultas")
    print("   • Permite migración limpia sin conflictos")
    print("   • Comando:")
    print("     TRUNCATE TABLE consultas, pacientes RESTART IDENTITY CASCADE;")
    
    print("\n📌 OPCIÓN 2: Usar script actualizado (RECOMENDADO si hay datos previos)")
    print("   • migrate_enriquecido.py ahora maneja CUI duplicados")
    print("   • Pacientes con CUI duplicado se insertan SIN CUI")
    print("   • El CUI original se guarda en metadatos")
    print("   • Puedes ejecutar la migración directamente")
    
    print("\n📌 OPCIÓN 3: Remover restricción de unicidad (NO RECOMENDADO)")
    print("   • Permite CUI duplicados en la base")
    print("   • Puede causar problemas de integridad")
    print("   • Comando:")
    print("     ALTER TABLE pacientes DROP CONSTRAINT IF EXISTS pacientes_cui_key;")
    
    print("\n📌 OPCIÓN 4: Mergear pacientes duplicados (AVANZADO)")
    print("   • Requiere análisis manual")
    print("   • Decide qué registro mantener para cada CUI")
    print("   • Actualiza referencias en consultas")

def generar_script_limpieza():
    """Genera script SQL para limpiar la base"""
    
    print("\n" + "=" * 80)
    print("🗑️  SCRIPT DE LIMPIEZA")
    print("=" * 80)
    
    script = """
-- ⚠️  CUIDADO: Este script elimina TODOS los datos
-- Ejecutar solo si quieres empezar desde cero

-- 1. Desactivar restricciones temporalmente
SET session_replication_role = 'replica';

-- 2. Limpiar tablas
TRUNCATE TABLE consultas RESTART IDENTITY CASCADE;
TRUNCATE TABLE pacientes RESTART IDENTITY CASCADE;

-- 3. Reactivar restricciones
SET session_replication_role = 'origin';

-- 4. Verificar
SELECT 'pacientes: ' || COUNT(*) FROM pacientes;
SELECT 'consultas: ' || COUNT(*) FROM consultas;

-- Si todo OK, verás:
-- Pacientes: 0
-- Consultas: 0
"""
    
    print(script)
    
    with open("/mnt/user-data/outputs/limpieza_postgres.sql", "w") as f:
        f.write(script)
    
    print("✅ Script guardado en: /mnt/user-data/outputs/limpieza_postgres.sql")

def main():
    print("\nEste script analiza la situación de CUI duplicados y ofrece soluciones.\n")
    
    # Análisis
    analizar_cui_duplicados()
    
    # Opciones
    listar_opciones()
    
    # Script de limpieza
    generar_script_limpieza()
    
    print("\n" + "=" * 80)
    print("📋 RECOMENDACIÓN")
    print("=" * 80)
    
    engine = create_engine(POSTGRES_URL, echo=False)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        total = db.execute(text("SELECT COUNT(*) FROM pacientes")).scalar()
        
        if total == 0:
            print("\n✅ Base vacía - puedes migrar directamente")
            print("   Ejecuta: python migrate_enriquecido.py")
        elif total < 1000:
            print("\n⚠️  Base con pocos registros")
            print("   OPCIÓN A: Limpiar y migrar todo desde cero")
            print("   OPCIÓN B: Usar migrate_enriquecido.py actualizado")
        else:
            print(f"\n⚠️  Base con {total:,} pacientes existentes")
            print("   RECOMENDADO: Usar migrate_enriquecido.py actualizado")
            print("   El script manejará CUI duplicados automáticamente")
    finally:
        db.close()
        engine.dispose()
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)