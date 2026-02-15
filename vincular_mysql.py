#!/usr/bin/env python3
"""
Script para vincular consultas huérfanas por nombre + apellido + nacimiento
Solo actualiza MySQL - NO migra a PostgreSQL

OBJETIVO:
- Tipo 1 y 2: Buscar expediente en pacientes por nombre+apellido+nacimiento
- Tipo 3: Buscar expediente en pacientes por nombre+apellido+nacimiento

Este script actualiza el campo 'expediente' en consultas MySQL
para que puedan ser migradas correctamente en la siguiente ejecución.
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import sys
from datetime import datetime

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

MYSQL_URL = construir_url_mysql()

print("=" * 80)
print("🔗 VINCULACIÓN DE CONSULTAS POR NOMBRE + APELLIDO + NACIMIENTO")
print("=" * 80)
print("\n⚠️  Este script SOLO actualiza MySQL")
print("   NO migra a PostgreSQL")
print("=" * 80)

# ============================================================================
# CONEXIÓN
# ============================================================================

print("\n🔌 Conectando a MySQL...")
try:
    mysql_engine = create_engine(MYSQL_URL, echo=False)
    MySQLSession = sessionmaker(bind=mysql_engine)
    mysql_db = MySQLSession()
    
    # Probar conexión
    mysql_db.execute(text("SELECT 1"))
    print("✅ Conexión establecida\n")
except Exception as e:
    print(f"❌ Error al conectar: {e}")
    sys.exit(1)

# ============================================================================
# FUNCIONES DE NORMALIZACIÓN
# ============================================================================

def normalizar_nombre(nombre):
    """Normaliza nombre para comparación"""
    if not nombre:
        return None
    # Convertir a minúsculas, eliminar espacios extra, quitar acentos básicos
    nombre = str(nombre).lower().strip()
    nombre = ' '.join(nombre.split())
    
    # Reemplazos básicos de acentos
    reemplazos = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ä': 'a', 'ë': 'e', 'ï': 'i', 'ö': 'o', 'ü': 'u',
        'ñ': 'n'
    }
    for viejo, nuevo in reemplazos.items():
        nombre = nombre.replace(viejo, nuevo)
    
    return nombre

# ============================================================================
# PASO 1: VINCULAR CONSULTAS TIPO 1 Y 2
# ============================================================================

def vincular_tipo_1_y_2():
    """
    Vincula consultas tipo 1 y 2 sin expediente
    buscando coincidencias en pacientes por nombre+apellido+nacimiento
    """
    
    print("=" * 80)
    print("📍 PASO 1: VINCULAR CONSULTAS TIPO 1 Y 2")
    print("=" * 80)
    
    stats = {
        "analizadas": 0,
        "vinculadas": 0,
        "sin_coincidencia": 0,
        "multiples_coincidencias": 0,
        "errores": 0
    }
    
    try:
        # Obtener consultas tipo 1 y 2 sin expediente
        print("\n📋 Buscando consultas tipo 1 y 2 sin expediente...")
        resultado = mysql_db.execute(text("""
            SELECT 
                id,
                tipo_consulta,
                nombres,
                apellidos,
                nacimiento
            FROM consultas
            WHERE tipo_consulta IN (1, 2)
            AND (expediente IS NULL OR expediente = 0)
            AND nombres IS NOT NULL
            AND apellidos IS NOT NULL
            AND nacimiento IS NOT NULL
            ORDER BY id
        """))
        
        consultas_huerfanas = resultado.fetchall()
        total = len(consultas_huerfanas)
        
        if total == 0:
            print("✅ No hay consultas tipo 1 y 2 sin expediente")
            return stats
        
        print(f"✅ Encontradas {total:,} consultas sin expediente")
        print("\n🔍 Buscando coincidencias en tabla pacientes...")
        
        for consulta in consultas_huerfanas:
            id_consulta = consulta[0]
            tipo = consulta[1]
            nombres = consulta[2]
            apellidos = consulta[3]
            nacimiento = consulta[4]
            
            stats["analizadas"] += 1
            
            try:
                # Normalizar datos
                nombres_norm = normalizar_nombre(nombres)
                apellidos_norm = normalizar_nombre(apellidos)
                
                if not nombres_norm or not apellidos_norm or not nacimiento:
                    stats["sin_coincidencia"] += 1
                    continue
                
                # Buscar en pacientes por nombre + apellido + nacimiento
                resultado_pac = mysql_db.execute(text("""
                    SELECT expediente
                    FROM pacientes
                    WHERE LOWER(TRIM(nombre)) = :nombres
                    AND LOWER(TRIM(apellido)) = :apellidos
                    AND nacimiento = :nacimiento
                    AND expediente IS NOT NULL
                    AND expediente != 0
                    LIMIT 2
                """), {
                    "nombres": nombres_norm,
                    "apellidos": apellidos_norm,
                    "nacimiento": nacimiento
                })
                
                pacientes = resultado_pac.fetchall()
                
                if len(pacientes) == 0:
                    stats["sin_coincidencia"] += 1
                    
                elif len(pacientes) == 1:
                    # Una coincidencia única - actualizar
                    expediente_encontrado = pacientes[0][0]
                    
                    mysql_db.execute(text("""
                        UPDATE consultas
                        SET expediente = :expediente
                        WHERE id = :id_consulta
                    """), {
                        "expediente": expediente_encontrado,
                        "id_consulta": id_consulta
                    })
                    mysql_db.commit()
                    
                    stats["vinculadas"] += 1
                    
                else:
                    # Múltiples coincidencias - no actualizar por seguridad
                    stats["multiples_coincidencias"] += 1
                
                if stats["analizadas"] % 100 == 0:
                    print(f"   Analizadas: {stats['analizadas']:,} | Vinculadas: {stats['vinculadas']:,}")
                    
            except Exception as e:
                mysql_db.rollback()
                stats["errores"] += 1
                if stats["errores"] <= 5:
                    print(f"   ❌ Error en consulta ID {id_consulta}: {e}")
        
        print(f"\n✅ Proceso completado:")
        print(f"   Total analizadas:          {stats['analizadas']:,}")
        print(f"   ✅ Vinculadas (actualizadas): {stats['vinculadas']:,}")
        print(f"   ⚠️  Sin coincidencia:         {stats['sin_coincidencia']:,}")
        print(f"   ⚠️  Múltiples coincidencias:  {stats['multiples_coincidencias']:,}")
        print(f"   ❌ Errores:                  {stats['errores']:,}")
        
    except Exception as e:
        print(f"❌ Error en proceso: {e}")
        mysql_db.rollback()
    
    return stats

# ============================================================================
# PASO 2: VINCULAR CONSULTAS TIPO 3
# ============================================================================

def vincular_tipo_3():
    """
    Vincula consultas tipo 3 sin expediente
    buscando coincidencias en pacientes por nombre+apellido+nacimiento
    """
    
    print("\n" + "=" * 80)
    print("📍 PASO 2: VINCULAR CONSULTAS TIPO 3 (URGENCIAS)")
    print("=" * 80)
    
    stats = {
        "analizadas": 0,
        "vinculadas": 0,
        "sin_coincidencia": 0,
        "multiples_coincidencias": 0,
        "errores": 0
    }
    
    try:
        # Obtener consultas tipo 3 sin expediente
        print("\n📋 Buscando consultas tipo 3 sin expediente...")
        resultado = mysql_db.execute(text("""
            SELECT 
                id,
                tipo_consulta,
                nombres,
                apellidos,
                nacimiento
            FROM consultas
            WHERE tipo_consulta = 3
            AND (expediente IS NULL OR expediente = 0)
            AND nombres IS NOT NULL
            AND apellidos IS NOT NULL
            AND nacimiento IS NOT NULL
            ORDER BY id
        """))
        
        consultas_huerfanas = resultado.fetchall()
        total = len(consultas_huerfanas)
        
        if total == 0:
            print("✅ No hay consultas tipo 3 sin expediente")
            return stats
        
        print(f"✅ Encontradas {total:,} consultas sin expediente")
        print("\n🔍 Buscando coincidencias en tabla pacientes...")
        
        for consulta in consultas_huerfanas:
            id_consulta = consulta[0]
            tipo = consulta[1]
            nombres = consulta[2]
            apellidos = consulta[3]
            nacimiento = consulta[4]
            
            stats["analizadas"] += 1
            
            try:
                # Normalizar datos
                nombres_norm = normalizar_nombre(nombres)
                apellidos_norm = normalizar_nombre(apellidos)
                
                if not nombres_norm or not apellidos_norm or not nacimiento:
                    stats["sin_coincidencia"] += 1
                    continue
                
                # Buscar en pacientes por nombre + apellido + nacimiento
                resultado_pac = mysql_db.execute(text("""
                    SELECT expediente
                    FROM pacientes
                    WHERE LOWER(TRIM(nombre)) = :nombres
                    AND LOWER(TRIM(apellido)) = :apellidos
                    AND nacimiento = :nacimiento
                    AND expediente IS NOT NULL
                    AND expediente != 0
                    LIMIT 2
                """), {
                    "nombres": nombres_norm,
                    "apellidos": apellidos_norm,
                    "nacimiento": nacimiento
                })
                
                pacientes = resultado_pac.fetchall()
                
                if len(pacientes) == 0:
                    stats["sin_coincidencia"] += 1
                    
                elif len(pacientes) == 1:
                    # Una coincidencia única - actualizar
                    expediente_encontrado = pacientes[0][0]
                    
                    mysql_db.execute(text("""
                        UPDATE consultas
                        SET expediente = :expediente
                        WHERE id = :id_consulta
                    """), {
                        "expediente": expediente_encontrado,
                        "id_consulta": id_consulta
                    })
                    mysql_db.commit()
                    
                    stats["vinculadas"] += 1
                    
                else:
                    # Múltiples coincidencias - no actualizar por seguridad
                    stats["multiples_coincidencias"] += 1
                
                if stats["analizadas"] % 100 == 0:
                    print(f"   Analizadas: {stats['analizadas']:,} | Vinculadas: {stats['vinculadas']:,}")
                    
            except Exception as e:
                mysql_db.rollback()
                stats["errores"] += 1
                if stats["errores"] <= 5:
                    print(f"   ❌ Error en consulta ID {id_consulta}: {e}")
        
        print(f"\n✅ Proceso completado:")
        print(f"   Total analizadas:          {stats['analizadas']:,}")
        print(f"   ✅ Vinculadas (actualizadas): {stats['vinculadas']:,}")
        print(f"   ⚠️  Sin coincidencia:         {stats['sin_coincidencia']:,}")
        print(f"   ⚠️  Múltiples coincidencias:  {stats['multiples_coincidencias']:,}")
        print(f"   ❌ Errores:                  {stats['errores']:,}")
        
    except Exception as e:
        print(f"❌ Error en proceso: {e}")
        mysql_db.rollback()
    
    return stats

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n💡 Este script vinculará consultas sin expediente")
    print("   buscando coincidencias por nombre + apellido + nacimiento")
    print()
    
    respuesta = input("¿Desea continuar? (s/n): ")
    if respuesta.lower() != 's':
        print("❌ Proceso cancelado")
        return
    
    inicio = datetime.now()
    
    # PASO 1: Tipo 1 y 2
    stats_tipo_12 = vincular_tipo_1_y_2()
    
    # PASO 2: Tipo 3
    stats_tipo_3 = vincular_tipo_3()
    
    tiempo_total = (datetime.now() - inicio).total_seconds()
    
    # RESUMEN FINAL
    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL")
    print("=" * 80)
    
    total_vinculadas = stats_tipo_12["vinculadas"] + stats_tipo_3["vinculadas"]
    total_analizadas = stats_tipo_12["analizadas"] + stats_tipo_3["analizadas"]
    
    print(f"\nTipo 1 y 2:")
    print(f"  Analizadas:  {stats_tipo_12['analizadas']:,}")
    print(f"  ✅ Vinculadas: {stats_tipo_12['vinculadas']:,}")
    
    print(f"\nTipo 3:")
    print(f"  Analizadas:  {stats_tipo_3['analizadas']:,}")
    print(f"  ✅ Vinculadas: {stats_tipo_3['vinculadas']:,}")
    
    print(f"\n" + "=" * 80)
    print(f"TOTALES:")
    print(f"  Analizadas:  {total_analizadas:,}")
    print(f"  Vinculadas:  {total_vinculadas:,}")
    print(f"  Tiempo:      {tiempo_total:.2f} segundos")
    print("=" * 80)
    
    if total_vinculadas > 0:
        print("\n💡 PRÓXIMOS PASOS:")
        print(f"   Se vincularon {total_vinculadas:,} consultas en MySQL")
        print("   Ahora puedes re-ejecutar la migración:")
        print("   python migrate_por_tipo_consulta.py")
        print()
        print("   Estas consultas ahora tendrán expediente y se migrarán correctamente")
    else:
        print("\n⚠️  No se vinculó ninguna consulta")
        print("   Posibles razones:")
        print("   - No hay coincidencias exactas en tabla pacientes")
        print("   - Nombres/apellidos no coinciden exactamente")
        print("   - Fechas de nacimiento diferentes")

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
    finally:
        mysql_db.close()
        mysql_engine.dispose()