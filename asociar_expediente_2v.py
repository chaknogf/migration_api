#!/usr/bin/env python3
"""
Script: asociar_expediente.py

Asocia expedientes a consultas tipo 1 y 2 sin expediente
comparando:
- Nombres: coincidencia EXACTA (=)
- Apellidos: coincidencia INICIAL (LIKE 'apellido%')

IMPORTANTE: 
- Solo trabaja en MySQL
- Solo afecta consultas tipo 1 y 2
- Nombres debe coincidir exactamente
- Apellidos solo necesita coincidir al inicio
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
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

MYSQL_URL = construir_url_mysql()

print("=" * 80)
print("🔗 ASOCIAR EXPEDIENTES A CONSULTAS TIPO 1 Y 2")
print("=" * 80)
print("\n⚠️  Este script SOLO actualiza MySQL")
print("   Compara:")
print("   - Nombres: coincidencia EXACTA (=)")
print("   - Apellidos: coincidencia INICIAL (LIKE 'apellido%')")
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

def normalizar_texto(texto):
    """Normaliza texto para comparación (minúsculas, sin espacios extra, sin acentos)"""
    if not texto:
        return None
    
    # Convertir a minúsculas y eliminar espacios extra
    texto_norm = str(texto).lower().strip()
    texto_norm = ' '.join(texto_norm.split())
    
    # Reemplazos básicos de acentos
    reemplazos = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ä': 'a', 'ë': 'e', 'ï': 'i', 'ö': 'o', 'ü': 'u',
        'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u',
        'ñ': 'n'
    }
    for viejo, nuevo in reemplazos.items():
        texto_norm = texto_norm.replace(viejo, nuevo)
    
    return texto_norm

# ============================================================================
# ANÁLISIS INICIAL
# ============================================================================

def analizar_estado_inicial():
    """Analiza el estado inicial de las consultas"""
    
    print("=" * 80)
    print("📊 ANÁLISIS INICIAL")
    print("=" * 80)
    
    # Total consultas tipo 1 y 2
    total_tipo_12 = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE tipo_consulta IN (1, 2)
    """)).scalar()
    
    # Con expediente
    con_expediente = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE tipo_consulta IN (1, 2)
        AND expediente IS NOT NULL
        AND expediente != 0
    """)).scalar()
    
    # Sin expediente
    sin_expediente = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE tipo_consulta IN (1, 2)
        AND (expediente IS NULL OR expediente = 0)
    """)).scalar()
    
    # Sin expediente pero con nombres y apellidos
    asociables = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE tipo_consulta IN (1, 2)
        AND (expediente IS NULL OR expediente = 0)
        AND nombres IS NOT NULL
        AND TRIM(nombres) != ''
        AND apellidos IS NOT NULL
        AND TRIM(apellidos) != ''
    """)).scalar()
    
    print(f"\n📋 Consultas Tipo 1 y 2:")
    print(f"   Total:                    {total_tipo_12:,}")
    print(f"   ✅ Con expediente:         {con_expediente:,} ({con_expediente/total_tipo_12*100:.1f}%)")
    print(f"   ❌ Sin expediente:         {sin_expediente:,} ({sin_expediente/total_tipo_12*100:.1f}%)")
    print(f"   🔍 Asociables:             {asociables:,} ({asociables/total_tipo_12*100:.1f}%)")
    print(f"      (tienen nombres y apellidos)")
    
    return {
        "total": total_tipo_12,
        "con_expediente": con_expediente,
        "sin_expediente": sin_expediente,
        "asociables": asociables
    }

# ============================================================================
# ASOCIAR EXPEDIENTES
# ============================================================================

def asociar_expedientes():
    """
    Asocia expedientes a consultas tipo 1 y 2 sin expediente
    comparando nombres y apellidos con tabla pacientes
    """
    
    print("\n" + "=" * 80)
    print("🔗 ASOCIANDO EXPEDIENTES")
    print("=" * 80)
    
    stats = {
        "procesadas": 0,
        "asociadas": 0,
        "sin_coincidencia": 0,
        "multiples_coincidencias": 0,
        "errores": 0
    }
    
    try:
        # Obtener consultas sin expediente tipo 1 y 2
        print("\n🔍 Buscando consultas sin expediente...")
        resultado = mysql_db.execute(text("""
            SELECT 
                id,
                tipo_consulta,
                nombres,
                apellidos
            FROM consultas
            WHERE tipo_consulta IN (1, 2)
            AND (expediente IS NULL OR expediente = 0)
            AND nombres IS NOT NULL
            AND TRIM(nombres) != ''
            AND apellidos IS NOT NULL
            AND TRIM(apellidos) != ''
            ORDER BY id
        """))
        
        consultas = resultado.fetchall()
        total = len(consultas)
        
        if total == 0:
            print("✅ No hay consultas tipo 1 y 2 sin expediente")
            return stats
        
        print(f"✅ Encontradas {total:,} consultas para asociar")
        print("\n🔄 Procesando consultas...")
        
        for consulta in consultas:
            id_consulta = consulta[0]
            tipo = consulta[1]
            nombres = consulta[2]
            apellidos = consulta[3]
            
            stats["procesadas"] += 1
            
            try:
                # Normalizar nombres y apellidos
                nombres_norm = normalizar_texto(nombres)
                apellidos_norm = normalizar_texto(apellidos)
                
                if not nombres_norm or not apellidos_norm:
                    stats["sin_coincidencia"] += 1
                    continue
                
                # Buscar en pacientes por nombres (exacto) y apellidos (inicio con LIKE)
                resultado_pac = mysql_db.execute(text("""
                    SELECT expediente
                    FROM pacientes
                    WHERE LOWER(TRIM(nombre)) = :nombres
                    AND LOWER(TRIM(apellido)) LIKE :apellidos_like
                    AND expediente IS NOT NULL
                    AND expediente != 0
                    LIMIT 2
                """), {
                    "nombres": nombres_norm,
                    "apellidos_like": f"{apellidos_norm}%"  # LIKE con % al final
                })
                
                pacientes = resultado_pac.fetchall()
                
                if len(pacientes) == 0:
                    # No se encontró paciente
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
                    
                    stats["asociadas"] += 1
                    
                else:
                    # Múltiples coincidencias - no actualizar por seguridad
                    stats["multiples_coincidencias"] += 1
                
                # Mostrar progreso
                if stats["procesadas"] % 100 == 0:
                    print(f"   Procesadas: {stats['procesadas']:,} | Asociadas: {stats['asociadas']:,}")
                    
            except Exception as e:
                mysql_db.rollback()
                stats["errores"] += 1
                if stats["errores"] <= 5:
                    print(f"   ❌ Error en consulta ID {id_consulta}: {e}")
        
        print(f"\n✅ Proceso completado:")
        print(f"   Total procesadas:          {stats['procesadas']:,}")
        print(f"   ✅ Asociadas:               {stats['asociadas']:,}")
        print(f"   ⚠️  Sin coincidencia:        {stats['sin_coincidencia']:,}")
        print(f"   ⚠️  Múltiples coincidencias: {stats['multiples_coincidencias']:,}")
        
        if stats["errores"] > 0:
            print(f"   ❌ Errores:                 {stats['errores']:,}")
        
    except Exception as e:
        print(f"❌ Error en proceso: {e}")
        mysql_db.rollback()
    
    return stats

# ============================================================================
# VERIFICACIÓN FINAL
# ============================================================================

def verificar_resultado():
    """Verifica el resultado después de la asociación"""
    
    print("\n" + "=" * 80)
    print("📊 VERIFICACIÓN FINAL")
    print("=" * 80)
    
    # Consultas tipo 1 y 2 con expediente ahora
    con_expediente = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE tipo_consulta IN (1, 2)
        AND expediente IS NOT NULL
        AND expediente != 0
    """)).scalar()
    
    # Sin expediente
    sin_expediente = mysql_db.execute(text("""
        SELECT COUNT(*) FROM consultas
        WHERE tipo_consulta IN (1, 2)
        AND (expediente IS NULL OR expediente = 0)
    """)).scalar()
    
    total = con_expediente + sin_expediente
    
    print(f"\n📋 Estado Final:")
    print(f"   Total tipo 1 y 2:         {total:,}")
    print(f"   ✅ Con expediente:         {con_expediente:,} ({con_expediente/total*100:.1f}%)")
    print(f"   ❌ Sin expediente:         {sin_expediente:,} ({sin_expediente/total*100:.1f}%)")

# ============================================================================
# MOSTRAR EJEMPLOS
# ============================================================================

def mostrar_ejemplos_asociados():
    """Muestra ejemplos de consultas asociadas"""
    
    print("\n" + "=" * 80)
    print("📝 EJEMPLOS DE CONSULTAS ASOCIADAS")
    print("=" * 80)
    
    # Obtener últimas 10 consultas tipo 1 y 2 con expediente
    resultado = mysql_db.execute(text("""
        SELECT 
            c.id,
            c.tipo_consulta,
            c.expediente,
            c.nombres,
            c.apellidos,
            p.nombre as nombre_paciente,
            p.apellido as apellido_paciente
        FROM consultas c
        LEFT JOIN pacientes p ON c.expediente = p.expediente
        WHERE c.tipo_consulta IN (1, 2)
        AND c.expediente IS NOT NULL
        AND c.expediente != 0
        ORDER BY c.id DESC
        LIMIT 10
    """))
    
    print("\n{:8} | {:4} | {:10} | {:20} | {:20} | {:10}".format(
        "ID", "Tipo", "Expediente", "Nombre Consulta", "Apellido Consulta", "Match"
    ))
    print("-" * 100)
    
    for row in resultado:
        id_c = row[0]
        tipo = row[1]
        exp = row[2]
        nom_c = str(row[3])[:20] if row[3] else "NULL"
        ape_c = str(row[4])[:20] if row[4] else "NULL"
        
        # Verificar si coincide
        nom_p = normalizar_texto(row[5]) if row[5] else None
        ape_p = normalizar_texto(row[6]) if row[6] else None
        nom_c_norm = normalizar_texto(row[3]) if row[3] else None
        ape_c_norm = normalizar_texto(row[4]) if row[4] else None
        
        match = "✅" if (nom_p == nom_c_norm and ape_p == ape_c_norm) else "❓"
        
        print("{:8} | {:4} | {:10} | {:20} | {:20} | {:10}".format(
            id_c, tipo, exp, nom_c, ape_c, match
        ))

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n💡 Este script asocia expedientes a consultas tipo 1 y 2")
    print("   Compara con tabla pacientes:")
    print("   - Nombres: coincidencia EXACTA")
    print("   - Apellidos: coincidencia INICIAL (comienza con...)")
    print("   Solo actualiza MySQL (NO afecta PostgreSQL)")
    print()
    
    respuesta = input("¿Desea continuar? (s/n): ")
    if respuesta.lower() != 's':
        print("❌ Proceso cancelado")
        return
    
    inicio = datetime.now()
    
    try:
        # Análisis inicial
        stats_inicial = analizar_estado_inicial()
        
        # Confirmar si hay consultas para asociar
        if stats_inicial["asociables"] == 0:
            print("\n⚠️  No hay consultas para asociar")
            return
        
        print(f"\n💡 Se intentarán asociar {stats_inicial['asociables']:,} consultas")
        respuesta2 = input("   ¿Continuar con la asociación? (s/n): ")
        if respuesta2.lower() != 's':
            print("❌ Asociación cancelada")
            return
        
        # Asociar expedientes
        stats_asociacion = asociar_expedientes()
        
        # Verificación final
        verificar_resultado()
        
        # Mostrar ejemplos
        if stats_asociacion["asociadas"] > 0:
            mostrar_ejemplos_asociados()
        
        tiempo_total = (datetime.now() - inicio).total_seconds()
        
        # RESUMEN FINAL
        print("\n" + "=" * 80)
        print("📊 RESUMEN FINAL")
        print("=" * 80)
        
        mejora = stats_asociacion["asociadas"]
        porcentaje_mejora = (mejora / stats_inicial["total"] * 100) if stats_inicial["total"] > 0 else 0
        
        print(f"\nConsultas procesadas:      {stats_asociacion['procesadas']:,}")
        print(f"✅ Expedientes asociados:   {stats_asociacion['asociadas']:,} ({porcentaje_mejora:.1f}% del total)")
        print(f"⚠️  Sin coincidencia:        {stats_asociacion['sin_coincidencia']:,}")
        print(f"⚠️  Múltiples coincidencias: {stats_asociacion['multiples_coincidencias']:,}")
        print(f"\nTiempo total:              {tiempo_total:.2f} segundos")
        
        if stats_asociacion["asociadas"] > 0:
            print("\n💡 PRÓXIMOS PASOS:")
            print(f"   Se asociaron {stats_asociacion['asociadas']:,} consultas en MySQL")
            print("   Ahora puedes re-ejecutar la migración a PostgreSQL:")
            print("   python migrate_por_tipo_consulta.py")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        mysql_db.rollback()
    
    finally:
        mysql_db.close()
        mysql_engine.dispose()

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