#!/usr/bin/env python3
#migrate_fases.py
"""
MIGRACIÓN POR FASES CON TRAZABILIDAD COMPLETA

FASE 1: Pacientes principales + Consultas con expediente exacto
FASE 2: Consultas con expediente actualizado (usando exp_ref)
FASE 3: Consultas por DPI coincidente
FASE 4: Pacientes sin expediente + Consultas restantes (por nombre+apellido+nacimiento)
"""

import os
from sqlalchemy import create_engine, text, bindparam, JSON
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from dotenv import load_dotenv
import sys
from typing import Dict, List, Tuple, Optional

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
    json_safe,
    CUIS_VISTOS
)

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
print("🏥 MIGRACIÓN POR FASES CON TRAZABILIDAD")
print("=" * 80)

# Conexiones
mysql_engine = create_engine(MYSQL_URL, echo=False)
postgres_engine = create_engine(POSTGRES_URL, echo=False)

MySQLSession = sessionmaker(bind=mysql_engine)
PostgresSession = sessionmaker(bind=postgres_engine)

# ============================================================================
# QUERIES DE INSERCIÓN (reutilizan normalizadores)
# ============================================================================

insert_paciente_query = text("""
INSERT INTO pacientes (
    expediente, cui, pasaporte, nombre, sexo, fecha_nacimiento,
    contacto, referencias, datos_extra, estado, metadatos,
    creado_en, actualizado_en
) VALUES (
    :expediente, :cui, :pasaporte, :nombre, :sexo, :fecha_nacimiento,
    :contacto, :referencias, :datos_extra, :estado, :metadatos,
    :creado_en, :actualizado_en
)
ON CONFLICT (expediente) DO UPDATE SET
    cui = COALESCE(EXCLUDED.cui, pacientes.cui),
    nombre = EXCLUDED.nombre,
    sexo = EXCLUDED.sexo,
    fecha_nacimiento = EXCLUDED.fecha_nacimiento,
    contacto = EXCLUDED.contacto,
    referencias = EXCLUDED.referencias,
    datos_extra = EXCLUDED.datos_extra,
    actualizado_en = NOW()
RETURNING id
""").bindparams(
    bindparam("nombre", type_=JSON),
    bindparam("contacto", type_=JSON),
    bindparam("referencias", type_=JSON),
    bindparam("datos_extra", type_=JSON),
    bindparam("metadatos", type_=JSON)
)

insert_consulta_query = text("""
INSERT INTO consultas (
    expediente, paciente_id, tipo_consulta, especialidad, servicio,
    documento, fecha_consulta, hora_consulta, indicadores, ciclo,
    orden, creado_en, actualizado_en, activo
) VALUES (
    :expediente, :paciente_id, :tipo_consulta, :especialidad, :servicio,
    :documento, :fecha_consulta, :hora_consulta, :indicadores, :ciclo,
    :orden, :creado_en, :actualizado_en, :activo
)
""").bindparams(
    bindparam("indicadores", type_=JSON),
    bindparam("ciclo", type_=JSON)
)

# ============================================================================
# FUNCIONES DE CONSTRUCCIÓN DE INDICADORES Y CICLO
# ============================================================================

def construir_indicadores_jsonb(consulta: Dict) -> Optional[Dict]:
    """Construye indicadores desde consulta completa"""
    indicadores = {}
    
    if consulta.get("prenatal"):
        indicadores["prenatal"] = bool(consulta["prenatal"])
    if consulta.get("lactancia"):
        indicadores["lactancia"] = bool(consulta["lactancia"])
    if consulta.get("bomberos"):
        indicadores["bomberos"] = True
    if consulta.get("transito"):
        indicadores["transito"] = True
    if consulta.get("arma_blanca"):
        indicadores["arma_blanca"] = True
    if consulta.get("arma_fuego"):
        indicadores["arma_fuego"] = True
    if consulta.get("estudiante_publica"):
        indicadores["estudiante_publica"] = True
    if consulta.get("accidente_laboral"):
        indicadores["accidente_laboral"] = True
    if consulta.get("personal_hospital"):
        indicadores["personal_hospital"] = True
    if consulta.get("reserva"):
        indicadores["reserva"] = True
    
    return indicadores if indicadores else None

def construir_ciclo_jsonb(consulta: Dict) -> Dict:
    """Construye ciclo desde consulta completa"""
    return {
        "id_mysql": consulta.get("id"),
        "hoja_emergencia": consulta.get("hoja_emergencia"),
        "acompanante": consulta.get("acompa"),
        "parentesco_acompanante": consulta.get("parente"),
        "notas": consulta.get("nota"),
        "diagnostico": consulta.get("dx"),
        "folios": consulta.get("folios"),
        "medico": consulta.get("medico"),
        "fecha_egreso": str(consulta.get("fecha_egreso")) if consulta.get("fecha_egreso") else None,
        "fecha_recepcion": str(consulta.get("fecha_recepcion")) if consulta.get("fecha_recepcion") else None,
        "status": consulta.get("status"),
        "consulta_por": consulta.get("consulta_por"),
        "created_by": consulta.get("created_by"),
        "archived_by": consulta.get("archived_by")
    }

def transformar_paciente(row: Dict) -> Dict:
    """Transforma paciente MySQL → PostgreSQL usando normalizadores"""
    
    id_mysql = row.get("id")
    expediente_original = row.get("expediente")
    es_duplicado = validar_expediente_duplicado(expediente_original)
    expediente_normalizado = normalizar_expediente(expediente_original, id_mysql)
    
    cui = normalizar_cui(row.get("dpi"), CUIS_VISTOS)
    
    nombre_json = construir_nombre_jsonb(
        row.get("nombre"),
        row.get("apellido")
    )
    
    contacto_json = construir_contacto_jsonb(
        limpiar_telefono(row.get("telefono")),
        row.get("email"),
        row.get("direccion"),
        row.get("municipio")
    )
    
    referencias_json = construir_referencias_jsonb(
        row.get("padre"),
        row.get("madre"),
        row.get("responsable"),
        row.get("parentesco"),
        row.get("dpi_responsable"),
        limpiar_telefono(row.get("telefono_responsable")),
        row.get("conyugue")
    )
    
    datos_extra_json = construir_datos_extra_jsonb(
        nacionalidad=row.get("nacionalidad"),
        depto_nac=row.get("depto_nac"),
        lugar_nacimiento=row.get("lugar_nacimiento"),
        estado_civil=row.get("estado_civil"),
        educacion=row.get("educacion"),
        pueblo=row.get("pueblo"),
        idioma=row.get("idioma"),
        ocupacion=row.get("ocupacion"),
        fecha_defuncion=row.get("fechaDefuncion"),
        hora_defuncion=row.get("hora_defuncion"),
        personaid=str(row.get("dpi")).strip() if row.get("dpi") else None
    )
    
    metadatos_json = construir_metadatos_jsonb(
        id_mysql,
        row.get("created_by"),
        row.get("created_at"),
        es_duplicado
    )
    
    return {
        "expediente": expediente_normalizado,
        "cui": cui,
        "pasaporte": normalizar_pasaporte(row.get("pasaporte")),
        "nombre": nombre_json,
        "sexo": normalizar_sexo(row.get("sexo")),
        "fecha_nacimiento": row.get("nacimiento"),
        "contacto": contacto_json,
        "referencias": referencias_json,
        "datos_extra": datos_extra_json,
        "estado": normalizar_estado(row.get("estado")),
        "metadatos": json_safe(metadatos_json),
        "creado_en": row.get("created_at", datetime.now()),
        "actualizado_en": row.get("update_at", datetime.now())
    }

def transformar_consulta(row: Dict, paciente_id: int, expediente: str) -> Optional[Dict]:
    """Transforma consulta MySQL → PostgreSQL"""
    
    if not all([
        row.get("tipo_consulta"),
        row.get("especialidad"),
        row.get("servicio"),
        row.get("fecha_consulta"),
        row.get("hora")
    ]):
        return None
    
    indicadores = construir_indicadores_jsonb(row)
    ciclo = construir_ciclo_jsonb(row)
    
    return {
        "expediente": expediente,
        "paciente_id": paciente_id,
        "tipo_consulta": row.get("tipo_consulta"),
        "especialidad": str(row.get("especialidad")),
        "servicio": str(row.get("servicio")),
        "documento": row.get("hoja_emergencia"),
        "fecha_consulta": row.get("fecha_consulta"),
        "hora_consulta": row.get("hora"),
        "indicadores": indicadores,
        "ciclo": ciclo,
        "orden": None,
        "creado_en": row.get("created_at", datetime.now()),
        "actualizado_en": row.get("updated_at", datetime.now()),
        "activo": True
    }

# ============================================================================
# FASE 1: PACIENTES PRINCIPALES + CONSULTAS CON EXPEDIENTE EXACTO
# ============================================================================

def fase1_pacientes_y_consultas_exactas():
    """
    Migra:
    1. TODOS los pacientes de tabla pacientes
    2. Consultas donde expediente coincide EXACTAMENTE
    """
    
    print("\n" + "=" * 80)
    print("📍 FASE 1: PACIENTES PRINCIPALES + CONSULTAS CON EXPEDIENTE EXACTO")
    print("=" * 80)
    
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()
    
    stats = {
        "pacientes": 0,
        "consultas": 0,
        "consultas_omitidas": 0,
        "errores_pacientes": 0,
        "errores_consultas": 0
    }
    
    # Mapeo: expediente_mysql → paciente_id_postgres
    mapeo_expedientes = {}
    
    try:
        # 1.1 Migrar TODOS los pacientes
        print("\n📦 Migrando pacientes...")
        resultado = mysql_db.execute(text("SELECT * FROM pacientes ORDER BY id"))
        pacientes = resultado.fetchall()
        
        for paciente_row in pacientes:
            try:
                paciente_dict = dict(paciente_row._mapping)
                paciente_pg = transformar_paciente(paciente_dict)
                
                # Insertar y obtener ID
                resultado = postgres_db.execute(insert_paciente_query, paciente_pg)
                paciente_id_pg = resultado.fetchone()[0]
                postgres_db.commit()
                
                # Guardar mapeo
                exp_mysql = paciente_dict.get("expediente")
                exp_normalizado = paciente_pg["expediente"]
                
                if exp_mysql:
                    mapeo_expedientes[str(exp_mysql)] = {
                        "paciente_id": paciente_id_pg,
                        "expediente_pg": exp_normalizado
                    }
                
                stats["pacientes"] += 1
                
                if stats["pacientes"] % 500 == 0:
                    print(f"   Migrados {stats['pacientes']} pacientes...")
                    
            except Exception as e:
                postgres_db.rollback()
                stats["errores_pacientes"] += 1
                if stats["errores_pacientes"] <= 5:
                    print(f"   ❌ Error paciente ID {paciente_dict.get('id')}: {e}")
        
        print(f"✅ Pacientes migrados: {stats['pacientes']:,}")
        print(f"✅ Mapeo creado: {len(mapeo_expedientes):,} expedientes")
        
        # 1.2 Migrar consultas con expediente EXACTO
        print("\n📋 Migrando consultas con expediente exacto...")
        resultado = mysql_db.execute(text("""
            SELECT * FROM consultas 
            WHERE expediente IS NOT NULL 
            AND expediente != 0
            ORDER BY id
        """))
        consultas = resultado.fetchall()
        
        batch = []
        for consulta_row in consultas:
            consulta_dict = dict(consulta_row._mapping)
            exp_consulta = str(consulta_dict.get("expediente"))
            
            # Buscar en mapeo
            if exp_consulta in mapeo_expedientes:
                mapeo = mapeo_expedientes[exp_consulta]
                consulta_pg = transformar_consulta(
                    consulta_dict,
                    mapeo["paciente_id"],
                    mapeo["expediente_pg"]
                )
                
                if consulta_pg:
                    batch.append(consulta_pg)
                else:
                    stats["consultas_omitidas"] += 1
                
                # Insertar batch
                if len(batch) >= 1000:
                    try:
                        postgres_db.execute(insert_consulta_query, batch)
                        postgres_db.commit()
                        stats["consultas"] += len(batch)
                        print(f"   Migradas {stats['consultas']:,} consultas...")
                        batch = []
                    except Exception as e:
                        postgres_db.rollback()
                        stats["errores_consultas"] += len(batch)
                        print(f"   ❌ Error en batch: {e}")
                        batch = []
        
        # Batch final
        if batch:
            try:
                postgres_db.execute(insert_consulta_query, batch)
                postgres_db.commit()
                stats["consultas"] += len(batch)
            except Exception as e:
                postgres_db.rollback()
                stats["errores_consultas"] += len(batch)
        
        print(f"✅ Consultas migradas: {stats['consultas']:,}")
        
    finally:
        mysql_db.close()
        postgres_db.close()
    
    return stats, mapeo_expedientes

# ============================================================================
# FASE 2: CONSULTAS CON EXPEDIENTE ACTUALIZADO (exp_ref)
# ============================================================================

def fase2_consultas_exp_ref(mapeo_expedientes: Dict):
    """
    Migra consultas donde:
    - expediente no coincide directamente
    - PERO exp_ref (expediente de referencia) SÍ coincide
    
    Requiere: campo exp_ref en tabla pacientes
    """
    
    print("\n" + "=" * 80)
    print("📍 FASE 2: CONSULTAS CON EXPEDIENTE ACTUALIZADO (exp_ref)")
    print("=" * 80)
    
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()
    
    stats = {
        "consultas": 0,
        "consultas_omitidas": 0,
        "errores": 0
    }
    
    try:
        # Verificar si existe campo exp_ref
        print("\n🔍 Verificando existencia de campo exp_ref...")
        try:
            resultado = mysql_db.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_schema = DATABASE()
                AND table_name = 'pacientes' 
                AND column_name = 'exp_ref'
            """))
            tiene_exp_ref = resultado.scalar() > 0
            
            if not tiene_exp_ref:
                print("⚠️  Campo exp_ref no existe en tabla pacientes")
                print("   Esta fase se omite")
                return stats
            
            print("✅ Campo exp_ref encontrado")
            
        except Exception as e:
            print(f"⚠️  No se pudo verificar exp_ref: {e}")
            print("   Esta fase se omite")
            return stats
        
        # Crear mapeo: exp_ref → expediente_actual
        print("\n📦 Creando mapeo exp_ref → expediente actual...")
        resultado = mysql_db.execute(text("""
            SELECT expediente, exp_ref 
            FROM pacientes 
            WHERE exp_ref IS NOT NULL 
            AND exp_ref != 0
            AND exp_ref != expediente
        """))
        
        mapeo_exp_ref = {}
        for row in resultado:
            exp_actual = str(row[0])
            exp_antiguo = str(row[1])
            
            # Buscar el paciente_id del expediente actual
            if exp_actual in mapeo_expedientes:
                mapeo_exp_ref[exp_antiguo] = mapeo_expedientes[exp_actual]
        
        if not mapeo_exp_ref:
            print("⚠️  No hay expedientes con exp_ref diferente")
            print("   Esta fase se omite")
            return stats
        
        print(f"✅ Mapeo exp_ref creado: {len(mapeo_exp_ref):,} expedientes antiguos")
        
        # Obtener consultas que pueden tener expediente antiguo
        print("\n📋 Buscando consultas con expediente antiguo...")
        resultado = mysql_db.execute(text("""
            SELECT * FROM consultas
            WHERE expediente IS NOT NULL
            AND expediente != 0
            ORDER BY id
        """))
        
        batch = []
        procesadas = 0
        
        for consulta_row in resultado:
            consulta_dict = dict(consulta_row._mapping)
            exp_consulta = str(consulta_dict.get("expediente"))
            
            # Verificar si este expediente es un exp_ref (antiguo)
            if exp_consulta in mapeo_exp_ref:
                mapeo = mapeo_exp_ref[exp_consulta]
                consulta_pg = transformar_consulta(
                    consulta_dict,
                    mapeo["paciente_id"],
                    mapeo["expediente_pg"]  # Usar expediente actual
                )
                
                if consulta_pg:
                    # Marcar en metadatos que se usó exp_ref
                    if consulta_pg.get("ciclo"):
                        consulta_pg["ciclo"]["metodo_vinculacion"] = "exp_ref"
                        consulta_pg["ciclo"]["expediente_original"] = exp_consulta
                    
                    batch.append(consulta_pg)
                else:
                    stats["consultas_omitidas"] += 1
                
                procesadas += 1
                
                # Insertar batch
                if len(batch) >= 1000:
                    try:
                        postgres_db.execute(insert_consulta_query, batch)
                        postgres_db.commit()
                        stats["consultas"] += len(batch)
                        print(f"   Migradas {stats['consultas']:,} consultas por exp_ref...")
                        batch = []
                    except Exception as e:
                        postgres_db.rollback()
                        stats["errores"] += len(batch)
                        print(f"   ❌ Error en batch: {e}")
                        batch = []
        
        # Batch final
        if batch:
            try:
                postgres_db.execute(insert_consulta_query, batch)
                postgres_db.commit()
                stats["consultas"] += len(batch)
            except Exception as e:
                postgres_db.rollback()
                stats["errores"] += len(batch)
        
        print(f"✅ Consultas migradas por exp_ref: {stats['consultas']:,}")
        print(f"   Consultas procesadas: {procesadas:,}")
        
    finally:
        mysql_db.close()
        postgres_db.close()
    
    return stats

# ============================================================================
# FASE 3: CONSULTAS POR DPI COINCIDENTE
# ============================================================================

def fase3_consultas_por_dpi(mapeo_expedientes: Dict):
    """
    Migra consultas donde:
    - expediente no coincide
    - PERO DPI coincide con un paciente
    """
    
    print("\n" + "=" * 80)
    print("📍 FASE 3: CONSULTAS POR DPI COINCIDENTE")
    print("=" * 80)
    
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()
    
    stats = {
        "consultas": 0,
        "consultas_omitidas": 0,
        "consultas_duplicadas": 0,  # Ya migradas en fase 1 o 2
        "errores": 0
    }
    
    try:
        # Crear mapeo: DPI → paciente_id_postgres
        print("\n📦 Creando mapeo DPI → paciente_id...")
        mapeo_dpi = {}
        resultado_pg = postgres_db.execute(text("""
            SELECT id, cui, expediente FROM pacientes WHERE cui IS NOT NULL
        """))
        
        for row in resultado_pg:
            mapeo_dpi[row[1]] = {  # cui
                "paciente_id": row[0],
                "expediente_pg": row[2]
            }
        
        print(f"✅ Mapeo DPI creado: {len(mapeo_dpi):,} registros")
        
        # Obtener consultas con DPI válido
        print("\n📋 Buscando consultas por DPI...")
        resultado = mysql_db.execute(text("""
            SELECT * FROM consultas
            WHERE dpi IS NOT NULL
            AND CHAR_LENGTH(TRIM(dpi)) = 13
            ORDER BY id
        """))
        
        batch = []
        total_procesadas = 0
        
        for consulta_row in resultado:
            consulta_dict = dict(consulta_row._mapping)
            dpi_consulta = consulta_dict.get("dpi")
            
            try:
                # Normalizar DPI
                dpi_str = str(dpi_consulta).strip()
                if len(dpi_str) != 13 or not dpi_str.isdigit():
                    continue
                
                dpi_int = int(dpi_str)
                total_procesadas += 1
                
                # Buscar en mapeo
                if dpi_int in mapeo_dpi:
                    mapeo = mapeo_dpi[dpi_int]
                    consulta_pg = transformar_consulta(
                        consulta_dict,
                        mapeo["paciente_id"],
                        mapeo["expediente_pg"]
                    )
                    
                    if consulta_pg:
                        # Marcar método de vinculación
                        if consulta_pg.get("ciclo"):
                            consulta_pg["ciclo"]["metodo_vinculacion"] = "dpi"
                            consulta_pg["ciclo"]["dpi_usado"] = dpi_int
                        
                        batch.append(consulta_pg)
                    else:
                        stats["consultas_omitidas"] += 1
                    
                    # Insertar batch
                    if len(batch) >= 1000:
                        try:
                            postgres_db.execute(insert_consulta_query, batch)
                            postgres_db.commit()
                            stats["consultas"] += len(batch)
                            print(f"   Migradas {stats['consultas']:,} consultas por DPI...")
                            batch = []
                        except Exception as e:
                            # Puede ser que ya se hayan migrado en fase 1 o 2
                            if "duplicate key" in str(e).lower():
                                stats["consultas_duplicadas"] += len(batch)
                            else:
                                stats["errores"] += len(batch)
                                print(f"   ⚠️  Error en batch: {str(e)[:100]}")
                            postgres_db.rollback()
                            batch = []
                            
            except (ValueError, TypeError) as e:
                continue
        
        # Batch final
        if batch:
            try:
                postgres_db.execute(insert_consulta_query, batch)
                postgres_db.commit()
                stats["consultas"] += len(batch)
            except Exception as e:
                if "duplicate key" in str(e).lower():
                    stats["consultas_duplicadas"] += len(batch)
                else:
                    stats["errores"] += len(batch)
                postgres_db.rollback()
        
        print(f"✅ Consultas migradas por DPI: {stats['consultas']:,}")
        print(f"   Consultas procesadas: {total_procesadas:,}")
        if stats["consultas_duplicadas"] > 0:
            print(f"   ⚠️  Ya migradas (duplicadas): {stats['consultas_duplicadas']:,}")
        
    finally:
        mysql_db.close()
        postgres_db.close()
    
    return stats

# ============================================================================
# FASE 4: PACIENTES SIN EXPEDIENTE + CONSULTAS RESTANTES
# ============================================================================

def fase4_sin_expediente():
    """
    Migra:
    1. Pacientes únicos por nombre+apellido+nacimiento (sin expediente válido)
    2. Consultas restantes asociadas a estos pacientes
    """
    
    print("\n" + "=" * 80)
    print("📍 FASE 4: PACIENTES SIN EXPEDIENTE + CONSULTAS RESTANTES")
    print("=" * 80)
    
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()
    
    stats = {
        "pacientes_sin_exp": 0,
        "consultas": 0,
        "errores": 0
    }
    
    try:
        # Obtener consultas sin expediente ni DPI válido
        print("\n📋 Buscando consultas sin expediente/DPI...")
        resultado = mysql_db.execute(text("""
            SELECT 
                nombres,
                apellidos,
                nacimiento,
                COUNT(*) as total_consultas
            FROM consultas
            WHERE (expediente IS NULL OR expediente = 0)
            AND (dpi IS NULL OR LENGTH(TRIM(dpi)) != 13)
            AND nombres IS NOT NULL
            AND apellidos IS NOT NULL
            GROUP BY nombres, apellidos, nacimiento
            HAVING COUNT(*) > 0
            ORDER BY total_consultas DESC
        """))
        
        pacientes_sin_exp = resultado.fetchall()
        print(f"✅ Encontrados {len(pacientes_sin_exp):,} pacientes únicos sin expediente")
        
        # Por cada grupo único (nombre+apellido+nacimiento)
        for pac in pacientes_sin_exp:
            nombres, apellidos, nacimiento, total = pac
            
            try:
                # Crear paciente sintético
                nombre_json = construir_nombre_jsonb(nombres, apellidos)
                expediente_sintetico = f"SIN-{hash(f'{nombres}{apellidos}{nacimiento}')}"[:20]
                
                paciente_pg = {
                    "expediente": expediente_sintetico,
                    "cui": None,
                    "pasaporte": None,
                    "nombre": nombre_json,
                    "sexo": None,
                    "fecha_nacimiento": nacimiento,
                    "contacto": {},
                    "referencias": None,
                    "datos_extra": {
                        "defuncion": None,
                        "personaid": None,
                        "demograficos": {},
                        "socioeconomicos": {}
                    },
                    "estado": "V",
                    "metadatos": json_safe([{
                        "accion": "CREADO",
                        "usuario": "SISTEMA",
                        "registro": datetime.now().isoformat(),
                        "expediente_duplicado": False,
                        "origen": "FASE4_SIN_EXPEDIENTE",
                        "total_consultas": total
                    }]),
                    "creado_en": datetime.now(),
                    "actualizado_en": datetime.now()
                }
                
                # Insertar paciente
                resultado = postgres_db.execute(insert_paciente_query, paciente_pg)
                paciente_id_pg = resultado.fetchone()[0]
                postgres_db.commit()
                stats["pacientes_sin_exp"] += 1
                
                # Obtener y migrar sus consultas
                consultas_resultado = mysql_db.execute(text("""
                    SELECT * FROM consultas
                    WHERE (expediente IS NULL OR expediente = 0)
                    AND (dpi IS NULL OR LENGTH(TRIM(dpi)) != 13)
                    AND nombres = :nombres
                    AND apellidos = :apellidos
                    AND nacimiento = :nacimiento
                """), {"nombres": nombres, "apellidos": apellidos, "nacimiento": nacimiento})
                
                for consulta_row in consultas_resultado:
                    consulta_dict = dict(consulta_row._mapping)
                    consulta_pg = transformar_consulta(
                        consulta_dict,
                        paciente_id_pg,
                        expediente_sintetico
                    )
                    
                    if consulta_pg:
                        postgres_db.execute(insert_consulta_query, consulta_pg)
                        stats["consultas"] += 1
                
                postgres_db.commit()
                
                if stats["pacientes_sin_exp"] % 100 == 0:
                    print(f"   Procesados {stats['pacientes_sin_exp']} pacientes...")
                    
            except Exception as e:
                postgres_db.rollback()
                stats["errores"] += 1
                if stats["errores"] <= 5:
                    print(f"   ❌ Error: {e}")
        
        print(f"✅ Pacientes sin expediente: {stats['pacientes_sin_exp']:,}")
        print(f"✅ Consultas asociadas: {stats['consultas']:,}")
        
    finally:
        mysql_db.close()
        postgres_db.close()
    
    return stats

# ============================================================================
# MAIN - EJECUTAR TODAS LAS FASES
# ============================================================================

def main():
    print("\n💡 MIGRACIÓN POR FASES")
    print("\nEste script ejecuta la migración en 4 fases:")
    print("  1️⃣  Pacientes principales + Consultas con expediente exacto")
    print("  2️⃣  Consultas con expediente actualizado (exp_ref)")
    print("  3️⃣  Consultas por DPI coincidente")
    print("  4️⃣  Pacientes sin expediente + Consultas restantes")
    print()
    
    respuesta = input("¿Desea continuar? (s/n): ")
    if respuesta.lower() != 's':
        print("❌ Migración cancelada")
        return
    
    inicio = datetime.now()
    
    # FASE 1
    stats_f1, mapeo_exp = fase1_pacientes_y_consultas_exactas()
    
    # FASE 2
    stats_f2 = fase2_consultas_exp_ref(mapeo_exp)
    
    # FASE 3
    stats_f3 = fase3_consultas_por_dpi(mapeo_exp)
    
    # FASE 4
    stats_f4 = fase4_sin_expediente()
    
    tiempo_total = (datetime.now() - inicio).total_seconds()
    
    # RESUMEN FINAL
    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL DE MIGRACIÓN POR FASES")
    print("=" * 80)
    
    print(f"\n📍 FASE 1: Pacientes principales + Consultas exactas")
    print(f"   Pacientes migrados:    {stats_f1['pacientes']:,}")
    print(f"   Consultas migradas:    {stats_f1['consultas']:,}")
    print(f"   Consultas omitidas:    {stats_f1['consultas_omitidas']:,}")
    if stats_f1['errores_pacientes'] > 0:
        print(f"   ⚠️  Errores pacientes:  {stats_f1['errores_pacientes']:,}")
    if stats_f1['errores_consultas'] > 0:
        print(f"   ⚠️  Errores consultas:  {stats_f1['errores_consultas']:,}")
    
    print(f"\n📍 FASE 2: Consultas con exp_ref")
    print(f"   Consultas migradas:    {stats_f2['consultas']:,}")
    if stats_f2['consultas'] > 0:
        print(f"   ✅ Recuperadas por expediente actualizado")
    
    print(f"\n📍 FASE 3: Consultas por DPI")
    print(f"   Consultas migradas:    {stats_f3['consultas']:,}")
    if stats_f3.get('consultas_duplicadas', 0) > 0:
        print(f"   ⚠️  Ya migradas:        {stats_f3['consultas_duplicadas']:,}")
    
    print(f"\n📍 FASE 4: Sin expediente")
    print(f"   Pacientes sintéticos:  {stats_f4['pacientes_sin_exp']:,}")
    print(f"   Consultas migradas:    {stats_f4['consultas']:,}")
    
    total_pacientes = stats_f1['pacientes'] + stats_f4['pacientes_sin_exp']
    total_consultas = (
        stats_f1['consultas'] + 
        stats_f2['consultas'] + 
        stats_f3['consultas'] + 
        stats_f4['consultas']
    )
    
    print(f"\n" + "=" * 80)
    print(f"📊 TOTALES GENERALES")
    print(f"=" * 80)
    print(f"Total pacientes:       {total_pacientes:,}")
    print(f"  └─ Principales:      {stats_f1['pacientes']:,}")
    print(f"  └─ Sintéticos:       {stats_f4['pacientes_sin_exp']:,}")
    print(f"\nTotal consultas:       {total_consultas:,}")
    print(f"  └─ Expediente exacto: {stats_f1['consultas']:,} ({stats_f1['consultas']/total_consultas*100 if total_consultas > 0 else 0:.1f}%)")
    print(f"  └─ Por exp_ref:       {stats_f2['consultas']:,} ({stats_f2['consultas']/total_consultas*100 if total_consultas > 0 else 0:.1f}%)")
    print(f"  └─ Por DPI:           {stats_f3['consultas']:,} ({stats_f3['consultas']/total_consultas*100 if total_consultas > 0 else 0:.1f}%)")
    print(f"  └─ Sin identificación: {stats_f4['consultas']:,} ({stats_f4['consultas']/total_consultas*100 if total_consultas > 0 else 0:.1f}%)")
    print(f"\nTiempo total:          {tiempo_total:.2f} segundos")
    print("=" * 80)
    
    # Recomendaciones post-migración
    print("\n💡 RECOMENDACIONES POST-MIGRACIÓN:")
    
    if stats_f4['pacientes_sin_exp'] > 0:
        print(f"\n⚠️  Se crearon {stats_f4['pacientes_sin_exp']:,} pacientes sintéticos")
        print("   Revisar con este query:")
        print("   SELECT * FROM pacientes WHERE expediente LIKE 'SIN-%';")
    
    if stats_f2['consultas'] > 0:
        print(f"\n✅ {stats_f2['consultas']:,} consultas recuperadas por exp_ref")
        print("   Verificar con:")
        print("   SELECT COUNT(*) FROM consultas WHERE ciclo->>'metodo_vinculacion' = 'exp_ref';")
    
    if stats_f3['consultas'] > 0:
        print(f"\n✅ {stats_f3['consultas']:,} consultas vinculadas por DPI")
        print("   Verificar con:")
        print("   SELECT COUNT(*) FROM consultas WHERE ciclo->>'metodo_vinculacion' = 'dpi';")
    
    print("\n🔍 Verificación de integridad:")
    print("   SELECT COUNT(*) FROM consultas c")
    print("   LEFT JOIN pacientes p ON c.paciente_id = p.id")
    print("   WHERE p.id IS NULL;  -- Debe ser 0")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Migración cancelada")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)