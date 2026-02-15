#!/usr/bin/env python3
"""
Script para identificar las 9,879 consultas no migradas
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
print("🔍 ANÁLISIS DE CONSULTAS NO MIGRADAS")
print("=" * 80)

mysql_engine = create_engine(construir_url_mysql(), echo=False)
postgres_engine = create_engine(construir_url_postgres(), echo=False)

MySQLSession = sessionmaker(bind=mysql_engine)
PostgresSession = sessionmaker(bind=postgres_engine)

mysql_db = MySQLSession()
postgres_db = PostgresSession()

try:
    # Total en MySQL
    total_mysql = mysql_db.execute(text("SELECT COUNT(*) FROM consultas")).scalar()
    print(f"\n📊 Total consultas MySQL: {total_mysql:,}")
    
    # Total en PostgreSQL
    total_postgres = postgres_db.execute(text("SELECT COUNT(*) FROM consultas")).scalar()
    print(f"📊 Total consultas PostgreSQL: {total_postgres:,}")
    
    # Diferencia
    diferencia = total_mysql - total_postgres
    print(f"\n⚠️  Consultas faltantes: {diferencia:,} ({diferencia/total_mysql*100:.2f}%)")
    
    # Obtener IDs migrados
    print("\n🔄 Obteniendo IDs migrados de PostgreSQL...")
    resultado = postgres_db.execute(text("""
        SELECT ciclo->>'id_mysql' as id_mysql 
        FROM consultas 
        WHERE ciclo->>'id_mysql' IS NOT NULL
    """))
    
    ids_migrados = set()
    for row in resultado:
        try:
            id_mysql = int(row[0])
            ids_migrados.add(id_mysql)
        except (ValueError, TypeError):
            continue
    
    print(f"✅ Obtenidos {len(ids_migrados):,} IDs migrados")
    
    # Análisis de consultas NO migradas
    print("\n" + "=" * 80)
    print("📋 ANÁLISIS DE CONSULTAS NO MIGRADAS")
    print("=" * 80)
    
    # Por tipo de consulta
    print("\n1️⃣  Por tipo de consulta:")
    resultado = mysql_db.execute(text("""
        SELECT 
            tipo_consulta,
            COUNT(*) as total
        FROM consultas
        GROUP BY tipo_consulta
        ORDER BY tipo_consulta
    """))
    
    for tipo, total in resultado:
        print(f"   Tipo {tipo if tipo else 'NULL':4}: {total:8,} consultas")
    
    # Sin fecha
    print("\n2️⃣  Sin fecha válida:")
    sin_fecha = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas 
        WHERE fecha_consulta IS NULL
    """)).scalar()
    print(f"   Sin fecha_consulta: {sin_fecha:,}")
    
    # Fechas futuras (asumiendo hoy es 2026-02-14)
    fechas_futuras = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas 
        WHERE fecha_consulta > '2026-02-14'
    """)).scalar()
    print(f"   Fechas futuras: {fechas_futuras:,}")
    
    # Fechas muy antiguas
    fechas_antiguas = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas 
        WHERE fecha_consulta < '1900-01-01'
    """)).scalar()
    print(f"   Fechas < 1900: {fechas_antiguas:,}")
    
    # Sin hora
    print("\n3️⃣  Sin hora:")
    sin_hora = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas 
        WHERE hora IS NULL
    """)).scalar()
    print(f"   Sin hora: {sin_hora:,}")
    
    # Sin expediente ni DPI
    print("\n4️⃣  Sin forma de vincular (tipo 1 y 2):")
    sin_vinculo_12 = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas 
        WHERE tipo_consulta IN (1, 2)
        AND (expediente IS NULL OR expediente = 0)
    """)).scalar()
    print(f"   Tipo 1 y 2 sin expediente: {sin_vinculo_12:,}")
    
    # Muestra de consultas no migradas
    print("\n" + "=" * 80)
    print("📝 MUESTRA DE CONSULTAS NO MIGRADAS (primeras 20)")
    print("=" * 80)
    
    resultado = mysql_db.execute(text("""
        SELECT 
            id,
            tipo_consulta,
            expediente,
            fecha_consulta,
            hora,
            dpi,
            nombres,
            apellidos
        FROM consultas
        ORDER BY id
        LIMIT 1000
    """))
    
    count = 0
    for row in resultado:
        id_consulta = row[0]
        if id_consulta not in ids_migrados:
            tipo = row[1] if row[1] else 'NULL'
            exp = row[2] if row[2] else 'NULL'
            fecha = row[3] if row[3] else 'NULL'
            hora = row[4] if row[4] else 'NULL'
            dpi = row[5] if row[5] else 'NULL'
            nombres = row[6] if row[6] else 'NULL'
            apellidos = row[7] if row[7] else 'NULL'
            
            print(f"\nID: {id_consulta}")
            print(f"  Tipo: {tipo}")
            print(f"  Expediente: {exp}")
            print(f"  Fecha: {fecha}")
            print(f"  Hora: {hora}")
            print(f"  DPI: {dpi}")
            print(f"  Nombre: {nombres} {apellidos}")
            
            count += 1
            if count >= 20:
                break
    
    # Resumen de causas probables
    print("\n" + "=" * 80)
    print("📊 RESUMEN DE CAUSAS PROBABLES")
    print("=" * 80)
    
    total_invalidas = sin_fecha + fechas_futuras + fechas_antiguas
    
    print(f"\nFecha inválida:              ~{total_invalidas:,}")
    print(f"Tipo 1/2 sin expediente:     ~{sin_vinculo_12:,}")
    print(f"Otros (errores de batch):    ~{diferencia - total_invalidas - sin_vinculo_12:,}")
    print(f"                             ─────────")
    print(f"Total no migradas:            {diferencia:,}")
    
    # Recomendaciones
    print("\n" + "=" * 80)
    print("💡 RECOMENDACIONES")
    print("=" * 80)
    
    if sin_fecha > 0:
        print(f"\n⚠️  Hay {sin_fecha:,} consultas sin fecha")
        print("   Acción: Corregir fechas en MySQL y re-migrar")
    
    if sin_vinculo_12 > 0:
        print(f"\n⚠️  Hay {sin_vinculo_12:,} consultas tipo 1/2 sin expediente")
        print("   Acción: Estas consultas no se pueden vincular")
        print("   Revisar si deben ser tipo 3 (urgencias)")
    
    if diferencia > 0:
        print(f"\n✅ {total_postgres:,} consultas migradas ({total_postgres/total_mysql*100:.1f}%)")
        print(f"⚠️  {diferencia:,} consultas no migradas ({diferencia/total_mysql*100:.1f}%)")

finally:
    mysql_db.close()
    postgres_db.close()
    mysql_engine.dispose()
    postgres_engine.dispose()

print("\n" + "=" * 80)
print("✅ Análisis completado")
print("=" * 80)