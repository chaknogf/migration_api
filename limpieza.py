#!/usr/bin/env python3
"""
Script para:
1. Eliminar consultas con nombres, apellidos o nacimiento NULL
2. Generar reporte CSV de consultas no migradas

IMPORTANTE: Este script modifica MySQL - hacer backup antes de ejecutar
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import csv
from datetime import datetime
import sys

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

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

MYSQL_URL = construir_url_mysql()
POSTGRES_URL = construir_url_postgres()

print("=" * 80)
print("🧹 LIMPIEZA Y REPORTE DE CONSULTAS NO MIGRADAS")
print("=" * 80)

# Conexiones
mysql_engine = create_engine(MYSQL_URL, echo=False)
postgres_engine = create_engine(POSTGRES_URL, echo=False)

MySQLSession = sessionmaker(bind=mysql_engine)
PostgresSession = sessionmaker(bind=postgres_engine)

mysql_db = MySQLSession()
postgres_db = PostgresSession()

# ============================================================================
# PASO 1: OBTENER IDs MIGRADOS DESDE POSTGRESQL
# ============================================================================

def obtener_ids_migrados():
    """Obtiene los IDs de consultas ya migradas a PostgreSQL"""
    
    print("\n" + "=" * 80)
    print("📍 PASO 1: OBTENER IDs MIGRADOS")
    print("=" * 80)
    
    print("\n🔄 Obteniendo IDs de consultas migradas desde PostgreSQL...")
    
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
    
    return ids_migrados

# ============================================================================
# PASO 2: ELIMINAR REGISTROS CON DATOS NULL
# ============================================================================

def eliminar_registros_null():
    """
    Elimina consultas donde nombres Y apellidos son NULL o vacíos ('')
    (No se puede identificar al paciente sin nombres y apellidos)
    """
    
    print("\n" + "=" * 80)
    print("📍 PASO 2: ELIMINAR REGISTROS SIN NOMBRES Y APELLIDOS")
    print("=" * 80)
    
    print("\n📋 Condiciones de eliminación:")
    print("   (nombres IS NULL OR TRIM(nombres) = '') AND")
    print("   (apellidos IS NULL OR TRIM(apellidos) = '')")
    
    # Contar antes de eliminar
    print("\n🔍 Contando registros sin nombres Y apellidos...")
    count_null = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE (nombres IS NULL OR TRIM(nombres) = '')
          AND (apellidos IS NULL OR TRIM(apellidos) = '')
    """)).scalar()
    
    print(f"⚠️  Registros sin nombres Y apellidos: {count_null:,}")
    
    if count_null == 0:
        print("✅ No hay registros sin nombres Y apellidos")
        return 0
    
    # Desglose
    count_ambos_null = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE nombres IS NULL AND apellidos IS NULL
    """)).scalar()
    
    count_ambos_vacios = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE TRIM(nombres) = '' AND TRIM(apellidos) = ''
          AND nombres IS NOT NULL AND apellidos IS NOT NULL
    """)).scalar()
    
    count_mixtos = count_null - count_ambos_null - count_ambos_vacios
    
    print(f"\n   Desglose:")
    print(f"   - Ambos NULL:           {count_ambos_null:,}")
    print(f"   - Ambos vacíos (''):    {count_ambos_vacios:,}")
    print(f"   - Mixtos (NULL/vacío):  {count_mixtos:,}")
    
    # Mostrar muestra
    print("\n📋 Muestra de registros a eliminar:")
    muestra = mysql_db.execute(text("""
        SELECT 
            id,
            tipo_consulta,
            expediente,
            nombres,
            apellidos,
            hoja_emergencia,
            fecha_consulta,
            dpi
        FROM consultas
        WHERE (nombres IS NULL OR TRIM(nombres) = '')
          AND (apellidos IS NULL OR TRIM(apellidos) = '')
        LIMIT 20
    """))
    
    print("\n{:8} | {:4} | {:10} | {:15} | {:15} | {:15} | {:12}".format(
        "ID", "Tipo", "Expediente", "Nombres", "Apellidos", "Hoja Emerg", "Fecha"
    ))
    print("-" * 100)
    
    for row in muestra:
        nombres_display = "NULL" if row[3] is None else ("''" if str(row[3]).strip() == "" else str(row[3])[:15])
        apellidos_display = "NULL" if row[4] is None else ("''" if str(row[4]).strip() == "" else str(row[4])[:15])
        
        print("{:8} | {:4} | {:10} | {:15} | {:15} | {:15} | {:12}".format(
            row[0] or 0,
            str(row[1] or "NULL")[:4],
            str(row[2] or "NULL")[:10],
            nombres_display,
            apellidos_display,
            str(row[5] or "NULL")[:15],
            str(row[6] or "NULL")[:12]
        ))
    
    # Confirmar eliminación
    print(f"\n⚠️  ¿Desea eliminar {count_null:,} registros sin nombres Y apellidos?")
    print("   Razón: No se puede identificar al paciente sin nombres y apellidos")
    print("   Se eliminarán registros donde:")
    print("   - nombres es NULL o vacío ('')")
    print("   - Y apellidos es NULL o vacío ('')")
    respuesta = input("\n   Escriba 'ELIMINAR' para confirmar: ")
    
    if respuesta != "ELIMINAR":
        print("❌ Eliminación cancelada")
        return 0
    
    # Eliminar
    print("\n🗑️  Eliminando registros...")
    resultado = mysql_db.execute(text("""
        DELETE FROM consultas
        WHERE (nombres IS NULL OR TRIM(nombres) = '')
          AND (apellidos IS NULL OR TRIM(apellidos) = '')
    """))
    mysql_db.commit()
    
    eliminados = resultado.rowcount
    print(f"✅ Eliminados {eliminados:,} registros")
    
    return eliminados

# ============================================================================
# PASO 3: GENERAR REPORTE DE NO MIGRADOS
# ============================================================================

def generar_reporte_no_migrados(ids_migrados):
    """Genera CSV con consultas no migradas"""
    
    print("\n" + "=" * 80)
    print("📍 PASO 3: GENERAR REPORTE DE NO MIGRADOS")
    print("=" * 80)
    
    # Nombre del archivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"consultas_no_migradas_{timestamp}.csv"
    
    print(f"\n📄 Generando reporte: {filename}")
    
    # Obtener consultas no migradas
    print("\n🔍 Buscando consultas no migradas en MySQL...")
    resultado = mysql_db.execute(text("""
        SELECT 
            id,
            tipo_consulta,
            hoja_emergencia,
            expediente,
            nombres,
            apellidos,
            nacimiento,
            dpi,
            fecha_consulta,
            hora,
            dx
        FROM consultas
        ORDER BY id
    """))
    
    # Filtrar no migrados y escribir CSV
    count_no_migrados = 0
    count_total = 0
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Encabezados
        writer.writerow([
            'ID',
            'Tipo Consulta',
            'Hoja Emergencia',
            'Expediente',
            'Nombres',
            'Apellidos',
            'Nacimiento',
            'DPI',
            'Fecha Consulta',
            'Hora',
            'Diagnóstico'
        ])
        
        for row in resultado:
            count_total += 1
            id_consulta = row[0]
            
            # Si NO está migrado
            if id_consulta not in ids_migrados:
                writer.writerow([
                    row[0],  # id
                    row[1],  # tipo_consulta
                    row[2],  # hoja_emergencia
                    row[3],  # expediente
                    row[4],  # nombres
                    row[5],  # apellidos
                    row[6],  # nacimiento
                    row[7],  # dpi
                    row[8],  # fecha_consulta
                    row[9],  # hora
                    row[10]  # dx
                ])
                count_no_migrados += 1
            
            if count_total % 10000 == 0:
                print(f"   Procesadas {count_total:,} consultas...")
    
    print(f"\n✅ Reporte generado: {filename}")
    print(f"   Total consultas MySQL: {count_total:,}")
    print(f"   Consultas no migradas: {count_no_migrados:,}")
    print(f"   Consultas migradas:    {count_total - count_no_migrados:,}")
    
    # Mostrar muestra del reporte
    print("\n📋 Primeras 10 consultas no migradas:")
    print("-" * 80)
    
    with open(filename, 'r', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Skip header
        
        for i, row in enumerate(reader):
            if i >= 10:
                break
            print(f"ID: {row[0]:8} | Tipo: {row[1]:1} | Exp: {row[3]:10} | {row[4]:20} {row[5]:20}")
    
    return filename, count_no_migrados

# ============================================================================
# PASO 4: ANÁLISIS DE NO MIGRADOS
# ============================================================================

def analizar_no_migrados(ids_migrados):
    """Analiza las consultas no migradas por categoría"""
    
    print("\n" + "=" * 80)
    print("📍 PASO 4: ANÁLISIS DE NO MIGRADOS")
    print("=" * 80)
    
    # Obtener todas las consultas
    resultado = mysql_db.execute(text("""
        SELECT 
            id,
            tipo_consulta,
            expediente,
            fecha_consulta,
            nombres,
            apellidos,
            hoja_emergencia
        FROM consultas
    """))
    
    stats = {
        "total": 0,
        "migrados": 0,
        "no_migrados": 0,
        "sin_tipo": 0,
        "sin_fecha": 0,
        "sin_nombres_apellidos": 0,
        "tipo_1_sin_exp": 0,
        "tipo_2_sin_exp": 0,
        "tipo_3_sin_exp": 0,
        "con_datos_completos": 0
    }
    
    for row in resultado:
        id_consulta = row[0]
        tipo = row[1]
        expediente = row[2]
        fecha = row[3]
        nombres = row[4]
        apellidos = row[5]
        hoja_emergencia = row[6]
        
        stats["total"] += 1
        
        if id_consulta in ids_migrados:
            stats["migrados"] += 1
        else:
            stats["no_migrados"] += 1
            
            # Categorizar por qué no se migró
            if (nombres is None or str(nombres).strip() == '') and (apellidos is None or str(apellidos).strip() == ''):
                stats["sin_nombres_apellidos"] += 1
            elif tipo is None:
                stats["sin_tipo"] += 1
            elif fecha is None:
                stats["sin_fecha"] += 1
            elif tipo == 1 and (expediente is None or expediente == 0):
                stats["tipo_1_sin_exp"] += 1
            elif tipo == 2 and (expediente is None or expediente == 0):
                stats["tipo_2_sin_exp"] += 1
            elif tipo == 3 and (expediente is None or expediente == 0):
                stats["tipo_3_sin_exp"] += 1
            
            # Contar los que tienen todos los datos
            if nombres and apellidos and fecha and tipo:
                stats["con_datos_completos"] += 1
    
    print(f"\n📊 Estadísticas:")
    print(f"   Total consultas MySQL:     {stats['total']:,}")
    print(f"   ✅ Migradas:                {stats['migrados']:,} ({stats['migrados']/stats['total']*100:.2f}%)")
    print(f"   ❌ No migradas:             {stats['no_migrados']:,} ({stats['no_migrados']/stats['total']*100:.2f}%)")
    
    print(f"\n🔍 Causas de no migración:")
    print(f"   Sin nombres Y apellidos:              {stats['sin_nombres_apellidos']:,}")
    print(f"   Sin tipo_consulta:                    {stats['sin_tipo']:,}")
    print(f"   Sin fecha_consulta:                   {stats['sin_fecha']:,}")
    print(f"   Tipo 1 sin expediente:                {stats['tipo_1_sin_exp']:,}")
    print(f"   Tipo 2 sin expediente:                {stats['tipo_2_sin_exp']:,}")
    print(f"   Tipo 3 sin expediente:                {stats['tipo_3_sin_exp']:,}")
    print(f"   Con datos completos:                  {stats['con_datos_completos']:,}")
    
    return stats

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n💡 Este script:")
    print("   1. Elimina consultas con nombres/apellidos/nacimiento NULL")
    print("   2. Genera reporte CSV de consultas no migradas")
    print("   3. Analiza causas de no migración")
    print()
    
    respuesta = input("¿Desea continuar? (s/n): ")
    if respuesta.lower() != 's':
        print("❌ Proceso cancelado")
        return
    
    inicio = datetime.now()
    
    try:
        # PASO 1: Obtener IDs migrados
        ids_migrados = obtener_ids_migrados()
        
        # PASO 2: Eliminar registros NULL
        eliminados = eliminar_registros_null()
        
        # PASO 3: Generar reporte
        filename, count_no_migrados = generar_reporte_no_migrados(ids_migrados)
        
        # PASO 4: Análisis
        stats = analizar_no_migrados(ids_migrados)
        
        tiempo_total = (datetime.now() - inicio).total_seconds()
        
        # RESUMEN FINAL
        print("\n" + "=" * 80)
        print("📊 RESUMEN FINAL")
        print("=" * 80)
        
        print(f"\nRegistros eliminados (NULL):  {eliminados:,}")
        print(f"Archivo generado:             {filename}")
        print(f"Consultas no migradas:        {count_no_migrados:,}")
        print(f"Tiempo total:                 {tiempo_total:.2f} segundos")
        
        print("\n💡 PRÓXIMOS PASOS:")
        print(f"   1. Revisar archivo: {filename}")
        print("   2. Analizar causas de no migración")
        print("   3. Decidir si crear script especial para casos particulares")
        
        if eliminados > 0:
            print(f"\n⚠️  Se eliminaron {eliminados:,} registros de MySQL")
            print("   Si necesita restaurarlos, use el backup de MySQL")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        mysql_db.rollback()
    
    finally:
        mysql_db.close()
        postgres_db.close()
        mysql_engine.dispose()
        postgres_engine.dispose()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Proceso cancelado por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)