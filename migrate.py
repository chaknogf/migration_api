#!/usr/bin/env python3
"""
Script de migración específico para tabla PACIENTES
Transforma estructura relacional MySQL -> estructura JSONB PostgreSQL
Usa schemas Pydantic y normalizadores
"""

import os
from sqlalchemy import create_engine, text, bindparam, JSON
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from dotenv import load_dotenv
import sys
from collections import Counter
from typing import List, Dict

def imprimir_expedientes_duplicados(batch: List[Dict], contexto: str = "") -> None:
    """
    Detecta e imprime expedientes duplicados dentro de un batch.
    No modifica datos, solo informa.
    """
    conteo = Counter(p["expediente"] for p in batch if p.get("expediente"))

    duplicados = {e: c for e, c in conteo.items() if c > 1}

    if duplicados:
        print("\n⚠️  EXPEDIENTES DUPLICADOS DETECTADOS", f"[{contexto}]" if contexto else "")
        for exp, veces in duplicados.items():
            print(f"   🔁 {exp} → {veces} veces")
        print("⚠️  Estos expedientes deben normalizarse antes del INSERT\n")
        
        


# Importar normalizadores
from app.utils.normalizadores import (
    normalizar_cui,
    normalizar_expediente,
    validar_expediente_duplicado,
    normalizar_sexo,
    normalizar_estado,
    construir_nombre_jsonb,
    construir_contacto_jsonb,
    construir_referencias_jsonb,
    construir_datos_extra_jsonb,
    construir_metadatos_jsonb,
    limpiar_telefono,
    normalizar_pasaporte,
    _normalizar_codigo,
    normalizar_nacionalidad,
    CUIS_VISTOS
)

# Cargar variables de entorno
load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

def construir_url_mysql():
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DATABASE", "test_api")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

def construir_url_postgres():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "hospital")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

MYSQL_URL = construir_url_mysql()
POSTGRES_URL = construir_url_postgres()

print("=" * 80)
print("🏥 MIGRACIÓN DE PACIENTES: MySQL → PostgreSQL")
print("=" * 80)
print(f"Origen (MySQL):       {MYSQL_URL.split('@')[1]}")
print(f"Destino (PostgreSQL): {POSTGRES_URL.split('@')[1]}")
print("=" * 80)

# ============================================================================
# CONEXIONES
# ============================================================================

print("\n🔌 Conectando a bases de datos...")
try:
    mysql_engine = create_engine(MYSQL_URL, echo=False)
    postgres_engine = create_engine(POSTGRES_URL, echo=False)
    
    MySQLSession = sessionmaker(bind=mysql_engine)
    PostgresSession = sessionmaker(bind=postgres_engine)
    
    # Probar conexiones
    with mysql_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    with postgres_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    
    print("✅ Conexiones establecidas\n")
except Exception as e:
    print(f"❌ Error al conectar: {e}")
    sys.exit(1)

# ============================================================================
# FUNCIÓN DE TRANSFORMACIÓN
# ============================================================================

def transformar_paciente(row):
    """Transforma un registro de MySQL a formato PostgreSQL usando normalizadores"""
    if not isinstance(row, dict):
        row = dict(row._mapping)

    id_mysql = row.get("id")
    expediente_original = row.get("expediente")
    es_duplicado = validar_expediente_duplicado(expediente_original)
    expediente_normalizado = normalizar_expediente(expediente_original, id_mysql)

    cui_original = row.get("dpi")
    cui = normalizar_cui(cui_original, CUIS_VISTOS)
    nombre_json = construir_nombre_jsonb(
        nombre=row.get("nombre"),
        apellido=row.get("apellido"),
    )
    sexo = normalizar_sexo(row.get("sexo"))
    fecha_nacimiento = row.get("nacimiento")

    telefono_limpio = limpiar_telefono(row.get("telefono"))
    contacto_json = construir_contacto_jsonb(
        telefono=telefono_limpio,
        email=row.get("email"),
        direccion=row.get("direccion"),
        municipio=row.get("municipio"),
        depto=row.get("depto")
    )

    telefono_responsable_limpio = limpiar_telefono(row.get("telefono_responsable"))
    referencias_json = construir_referencias_jsonb(
        padre=row.get("padre"),
        madre=row.get("madre"),
        responsable=row.get("responsable"),
        parentesco_responsable=row.get("parentesco"),
        dpi_responsable=row.get("dpi_responsable"),
        telefono_responsable=telefono_responsable_limpio,
        conyugue=row.get("conyugue")
    )

    datos_extra_json = construir_datos_extra_jsonb(
        nacionalidad=row.get("nacionalidad"),
        depto_nac=row.get("depto_nac"),
        lugar_nacimiento=_normalizar_codigo(row.get("lugar_nacimiento")),
        estado_civil=row.get("estado_civil"),
        educacion=row.get("educacion"),
        pueblo=row.get("pueblo"),
        idioma=row.get("idioma"),
        ocupacion=row.get("ocupacion"),
        fecha_defuncion=row.get("fechaDefuncion"),
        hora_defuncion=row.get("hora_defuncion")
    )
    if datos_extra_json is None:
        datos_extra_json = {}

    datos_extra_json["personaid"] = (
    str(cui_original).strip()
    if cui_original and str(cui_original).strip()
    else None
)

    estado = normalizar_estado(row.get("estado"))
    metadatos_json = construir_metadatos_jsonb(
        id_mysql=id_mysql,
        created_by=row.get("created_by"),
        expediente_duplicado=es_duplicado
    )
    

    paciente_postgres = {
        
        "expediente": expediente_normalizado,
        "cui": cui,
        "pasaporte": normalizar_pasaporte(row.get("pasaporte")),
        "nombre": nombre_json, 
        "sexo": sexo,
        "fecha_nacimiento": fecha_nacimiento,
        "contacto": contacto_json,
        "referencias": referencias_json,
        "datos_extra": datos_extra_json,
        "estado": estado,
        "metadatos": metadatos_json,
        "creado_en": row.get("created_at", datetime.now()),
        "actualizado_en": row.get("update_at")
    }

    return paciente_postgres, es_duplicado, cui is None

# ============================================================================
# QUERY DE INSERCIÓN
# ============================================================================

insert_query = text("""
INSERT INTO pacientes (
  
    expediente, cui, pasaporte, nombre, sexo, fecha_nacimiento,
    contacto, referencias, datos_extra, estado, metadatos,
    creado_en, actualizado_en
) VALUES (
    
    :expediente,
    :cui,
    :pasaporte,
    :nombre,
    :sexo,
    :fecha_nacimiento,
    :contacto,
    :referencias,
    :datos_extra,
    :estado,
    :metadatos,
    :creado_en,
    :actualizado_en
)
ON CONFLICT (expediente) DO UPDATE SET
   
    cui = EXCLUDED.cui,
    pasaporte = EXCLUDED.pasaporte,
    nombre = EXCLUDED.nombre,
    sexo = EXCLUDED.sexo,
    fecha_nacimiento = EXCLUDED.fecha_nacimiento,
    contacto = EXCLUDED.contacto,
    referencias = EXCLUDED.referencias,
    datos_extra = EXCLUDED.datos_extra,
    estado = EXCLUDED.estado,
    metadatos = EXCLUDED.metadatos,
    actualizado_en = NOW()
""").bindparams(
    bindparam("nombre", type_=JSON),
    bindparam("contacto", type_=JSON),
    bindparam("referencias", type_=JSON),
    bindparam("datos_extra", type_=JSON),
    bindparam("metadatos", type_=JSON),
)

# ============================================================================
# MIGRACIÓN
# ============================================================================

def migrar_pacientes(batch_size=500):
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()

    stats = {
        "total": 0,
        "exitosos": 0,
        "errores": 0,
        "expedientes_duplicados": 0,
        "cui_invalidos": 0,
        "advertencias": []
    }

    inicio = datetime.now()

    try:
        resultado = mysql_db.execute(text("SELECT * FROM pacientes"))
        pacientes_mysql = resultado.fetchall()
        stats["total"] = len(pacientes_mysql)

        batch = []

        for i, paciente_mysql in enumerate(pacientes_mysql, 1):
            try:
                paciente_postgres, es_duplicado, cui_invalido = transformar_paciente(paciente_mysql)

                if es_duplicado:
                    stats["expedientes_duplicados"] += 1
                if cui_invalido:
                    stats["cui_invalidos"] += 1

                batch.append(paciente_postgres)


                if i % batch_size == 0:
                    try:    
                        # 🔍 Detectar duplicados ANTES del INSERT
                        imprimir_expedientes_duplicados(
                            batch,
                            contexto=f"batch terminado en registro {i}"
                        )
                        
                
                        postgres_db.execute(insert_query, batch)
                        postgres_db.commit()
                        stats["exitosos"] += len(batch)
                        print(f"✅ Migrados {i}/{stats['total']}")
                    except Exception as e:
                        postgres_db.rollback()
                        stats["errores"] += len(batch)
                        print(f"❌ Batch fallido en {i}: {e}")
                    batch = []

            except Exception as e:
                stats["errores"] += 1
                stats["advertencias"].append(str(e))

        # Batch final
        if batch:
            try:
                imprimir_expedientes_duplicados(
                    batch,
                    contexto="batch final"
                )

                postgres_db.execute(insert_query, batch)
                postgres_db.commit()
                stats["exitosos"] += len(batch)
            except Exception as e:
                postgres_db.rollback()
                stats["errores"] += len(batch)
                print(f"❌ Batch final fallido: {e}")

        stats["tiempo"] = (datetime.now() - inicio).total_seconds()

    finally:
        mysql_db.close()
        postgres_db.close()

    return stats

# ============================================================================
# VERIFICACIÓN
# ============================================================================

def verificar_migracion():
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()

    try:
        print("\n" + "=" * 80)
        print("🔍 VERIFICACIÓN DE MIGRACIÓN")
        print("=" * 80)

        count_mysql = mysql_db.execute(text("SELECT COUNT(*) FROM pacientes")).scalar()
        count_postgres = postgres_db.execute(text("SELECT COUNT(*) FROM pacientes")).scalar()

        print(f"\n📊 Conteo de registros:")
        print(f"   MySQL:      {count_mysql:,}")
        print(f"   PostgreSQL: {count_postgres:,}")

        duplicados = postgres_db.execute(text("""
            SELECT COUNT(*) FROM pacientes WHERE metadatos->>'expediente_duplicado' = 'true'
        """)).scalar()
        print(f"   Expedientes duplicados marcados: {duplicados:,}")

        cui_validos = postgres_db.execute(text("SELECT COUNT(*) FROM pacientes WHERE cui IS NOT NULL")).scalar()
        cui_nulos = postgres_db.execute(text("SELECT COUNT(*) FROM pacientes WHERE cui IS NULL")).scalar()
        print(f"   CUI válidos:   {cui_validos:,}")
        print(f"   CUI inválidos: {cui_nulos:,}")

    finally:
        mysql_db.close()
        postgres_db.close()

# ============================================================================
# MAIN
# ============================================================================

def main():
    stats = migrar_pacientes()
    verificar_migracion()

    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL DE MIGRACIÓN")
    print("=" * 80)
    print(f"Total procesados:         {stats['total']:,}")
    print(f"Migrados exitosos:        {stats['exitosos']:,}")
    print(f"Errores:                  {stats['errores']:,}")
    print(f"Expedientes duplicados:   {stats['expedientes_duplicados']:,}")
    print(f"CUI inválidos:            {stats['cui_invalidos']:,}")
    print(f"Tiempo total:             {stats.get('tiempo', 0):.2f} segundos")
    print("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Migración cancelada por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)