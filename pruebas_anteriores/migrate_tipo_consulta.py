#!/usr/bin/env python3
"""
MIGRACIÓN REFACTORIZADA POR TIPO DE CONSULTA

ESTRATEGIA:
- tipo_consulta 1 y 2: Vinculación por expediente o exp_ref
- tipo_consulta 3 CON expediente: Vinculación por expediente
- tipo_consulta 3 SIN expediente: Buscar por DPI/CUI, si no existe crear paciente desde consulta
"""

import os
from sqlalchemy import create_engine, text, bindparam, JSON
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from dotenv import load_dotenv
import sys
from typing import Dict, List, Tuple, Optional
import hashlib

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

from app.utils.normalizadores_consultas import (
    normalizar_consulta_completa,
    normalizar_estado_ciclo
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
print("🏥 MIGRACIÓN REFACTORIZADA POR TIPO DE CONSULTA")
print("=" * 80)

# Conexiones
mysql_engine = create_engine(MYSQL_URL, echo=False)
postgres_engine = create_engine(POSTGRES_URL, echo=False)

MySQLSession = sessionmaker(bind=mysql_engine)
PostgresSession = sessionmaker(bind=postgres_engine)

# ============================================================================
# QUERIES
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
# FUNCIONES AUXILIARES
# ============================================================================

def construir_indicadores_jsonb(consulta: Dict) -> Optional[Dict]:
    """Construye indicadores desde consulta normalizada"""
    indicadores = {}
    
    if consulta.get("prenatal"):
        try:
            if int(consulta["prenatal"]) > 0:
                indicadores["prenatal"] = True
        except (ValueError, TypeError):
            pass
    
    if consulta.get("lactancia"):
        try:
            if int(consulta["lactancia"]) > 0:
                indicadores["lactancia"] = True
        except (ValueError, TypeError):
            pass
    
    for campo in ["bomberos", "transito", "arma_blanca", "arma_fuego",
                  "estudiante_publica", "accidente_laboral", "personal_hospital", "reserva"]:
        if consulta.get(campo):
            indicadores[campo] = True
    
    return indicadores if indicadores else None

def construir_ciclo_jsonb_normalizado(consulta: Dict) -> Dict:
    """Construye ciclo desde consulta NORMALIZADA"""
    estado = normalizar_estado_ciclo(consulta.get("status"))
    
    ciclo = {
        "id_mysql": consulta.get("id"),
        "hoja_emergencia": consulta.get("hoja_emergencia"),
        "diagnostico": consulta.get("diagnostico"),
        "medico": consulta.get("medico"),
        "acompanante": consulta.get("acompanante"),
        "parentesco_acompanante": consulta.get("parentesco_acompanante"),
        "notas": consulta.get("notas"),
        "folios": consulta.get("folios"),
        "fecha_egreso": str(consulta.get("fecha_egreso")) if consulta.get("fecha_egreso") else None,
        "fecha_recepcion": str(consulta.get("fecha_recepcion")) if consulta.get("fecha_recepcion") else None,
        "consulta_por": consulta.get("consulta_por"),
        "created_by": consulta.get("created_by"),
        "archived_by": consulta.get("archived_by"),
        "estado": estado
    }
    
    return {k: v for k, v in ciclo.items() if v is not None}

def transformar_paciente(row: Dict) -> tuple[Dict, bool, bool]:
    """Transforma paciente MySQL → PostgreSQL"""
    
    id_mysql = row.get("id")
    expediente_original = row.get("expediente")
    es_duplicado = validar_expediente_duplicado(expediente_original)
    expediente_normalizado = normalizar_expediente(expediente_original, id_mysql)
    
    cui_original = row.get("dpi")
    cui = normalizar_cui(cui_original, CUIS_VISTOS)
    
    nombre_json = construir_nombre_jsonb(
        nombre=row.get("nombre"),
        apellido=row.get("apellido")
    )
    
    telefono_limpio = limpiar_telefono(row.get("telefono"))
    contacto_json = construir_contacto_jsonb(
        telefonos=telefono_limpio,
        email=row.get("email"),
        domicilio=row.get("direccion"),
        municipio=row.get("municipio")
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
    
    personaid = str(cui_original).strip() if cui_original and str(cui_original).strip() else None
    
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
        peso_nacimiento=row.get("peso_nacimiento"),
        edad_gestacional=row.get("edad_gestacional"),
        parto=row.get("parto"),
        gemelo=row.get("gemelo"),
        expediente_madre=row.get("exp_madre"),
        extrahospitalario=row.get("extrahospitalario"),
        personaid=personaid
    )
    
    metadatos_json = construir_metadatos_jsonb(
        id_mysql=id_mysql,
        created_by=row.get("created_by"),
        created_at=row.get("created_at"),
        expediente_duplicado=es_duplicado
    )
    
    paciente_postgres = {
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
    
    return paciente_postgres, es_duplicado, cui is None

def crear_paciente_desde_consulta(consulta_dict: Dict, postgres_db) -> Tuple[int, str]:
    """
    Crea un paciente en PostgreSQL usando los datos de la consulta
    Retorna: (paciente_id, expediente)
    """
    
    # Generar expediente único basado en datos de la consulta
    hash_base = f"{consulta_dict.get('nombres', '')}{consulta_dict.get('apellidos', '')}{consulta_dict.get('nacimiento', '')}{consulta_dict.get('id', '')}"
    hash_hex = hashlib.md5(hash_base.encode()).hexdigest()[:8].upper()
    expediente_urgencia = f"URG-{hash_hex}"
    
    # Construir nombre desde consulta
    nombre_json = construir_nombre_jsonb(
        nombre=consulta_dict.get("nombres"),
        apellido=consulta_dict.get("apellidos")
    )
    
    # Normalizar CUI de consulta - MANEJO ROBUSTO DE DPIs INVÁLIDOS
    cui_consulta = None
    if consulta_dict.get("dpi"):
        try:
            dpi_raw = str(consulta_dict["dpi"]).strip()
            # Eliminar caracteres no numéricos
            dpi_clean = ''.join(c for c in dpi_raw if c.isdigit())
            
            # Validar que sea exactamente 13 dígitos
            if len(dpi_clean) == 13:
                cui_int = int(dpi_clean)
                if cui_int not in CUIS_VISTOS:
                    CUIS_VISTOS.add(cui_int)
                    cui_consulta = cui_int
        except (ValueError, TypeError):
            # DPI inválido, continuar sin CUI
            pass
    
    # Construir paciente mínimo
    paciente_urgencia = {
        "expediente": expediente_urgencia,
        "cui": cui_consulta,
        "pasaporte": None,
        "nombre": nombre_json,
        "sexo": normalizar_sexo(consulta_dict.get("sexo")),
        "fecha_nacimiento": consulta_dict.get("nacimiento"),
        "contacto": {},
        "referencias": None,
        "datos_extra": {
            "defuncion": None,
            "personaid": str(consulta_dict.get("dpi")).strip() if consulta_dict.get("dpi") else None,
            "demograficos": {},
            "socioeconomicos": {}
        },
        "estado": "V",
        "metadatos": json_safe([{
            "accion": "CREADO",
            "usuario": consulta_dict.get("created_by") or "sys",
            "registro": datetime.now().isoformat(),
            "expediente_duplicado": False,
            "origen": "2chance",
            "origen_mysql_consulta_id": consulta_dict.get("id")
        }]),
        "creado_en": datetime.now(),
        "actualizado_en": datetime.now()
    }
    
    # Insertar paciente
    resultado = postgres_db.execute(insert_paciente_query, paciente_urgencia)
    paciente_id = resultado.fetchone()[0]
    postgres_db.commit()
    
    return paciente_id, expediente_urgencia

def transformar_consulta(row: Dict, paciente_id: int, expediente: str) -> Optional[Dict]:
    """Transforma consulta MySQL → PostgreSQL CON NORMALIZACIÓN"""
    
    consulta_normalizada = normalizar_consulta_completa(row)
    
    if not consulta_normalizada:
        return None
    
    indicadores = construir_indicadores_jsonb(consulta_normalizada)
    ciclo = construir_ciclo_jsonb_normalizado(consulta_normalizada)
    
    return {
        "expediente": expediente,
        "paciente_id": paciente_id,
        "tipo_consulta": consulta_normalizada["tipo_consulta"],
        "especialidad": consulta_normalizada["especialidad"],
        "servicio": consulta_normalizada["servicio"],
        "documento": consulta_normalizada["hoja_emergencia"],
        "fecha_consulta": consulta_normalizada["fecha_consulta"],
        "hora_consulta": consulta_normalizada["hora_consulta"],
        "indicadores": indicadores,
        "ciclo": ciclo,
        "orden": None,
        "creado_en": consulta_normalizada.get("created_at", datetime.now()),
        "actualizado_en": consulta_normalizada.get("updated_at", datetime.now()),
        "activo": True
    }

# ============================================================================
# PASO 1: MIGRAR TODOS LOS PACIENTES
# ============================================================================

def paso1_migrar_pacientes():
    """Migra TODOS los pacientes de la tabla pacientes"""
    
    print("\n" + "=" * 80)
    print("📍 PASO 1: MIGRAR TODOS LOS PACIENTES")
    print("=" * 80)
    
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()
    
    stats = {
        "pacientes": 0,
        "errores": 0
    }
    
    mapeo_expedientes = {}  # expediente_mysql → {paciente_id, expediente_pg}
    mapeo_dpi = {}  # dpi → {paciente_id, expediente_pg}
    mapeo_exp_ref = {}  # exp_ref → {paciente_id, expediente_pg}
    
    try:
        print("\n📦 Migrando pacientes...")
        resultado = mysql_db.execute(text("SELECT * FROM pacientes ORDER BY id"))
        pacientes = resultado.fetchall()
        
        for paciente_row in pacientes:
            try:
                paciente_dict = dict(paciente_row._mapping)
                paciente_pg, es_duplicado, cui_invalido = transformar_paciente(paciente_dict)
                
                resultado = postgres_db.execute(insert_paciente_query, paciente_pg)
                paciente_id_pg = resultado.fetchone()[0]
                postgres_db.commit()
                
                # Mapeos
                exp_mysql = paciente_dict.get("expediente")
                exp_normalizado = paciente_pg["expediente"]
                
                if exp_mysql:
                    mapeo_expedientes[str(exp_mysql)] = {
                        "paciente_id": paciente_id_pg,
                        "expediente_pg": exp_normalizado
                    }
                
                # Mapeo DPI
                if paciente_pg.get("cui"):
                    mapeo_dpi[paciente_pg["cui"]] = {
                        "paciente_id": paciente_id_pg,
                        "expediente_pg": exp_normalizado
                    }
                
                # Mapeo exp_ref
                exp_ref = paciente_dict.get("exp_ref")
                if exp_ref and exp_ref != exp_mysql:
                    mapeo_exp_ref[str(exp_ref)] = {
                        "paciente_id": paciente_id_pg,
                        "expediente_pg": exp_normalizado
                    }
                
                stats["pacientes"] += 1
                
                if stats["pacientes"] % 500 == 0:
                    print(f"   Migrados {stats['pacientes']} pacientes...")
                    
            except Exception as e:
                postgres_db.rollback()
                stats["errores"] += 1
                if stats["errores"] <= 5:
                    print(f"   ❌ Error: {e}")
        
        print(f"✅ Pacientes migrados: {stats['pacientes']:,}")
        print(f"   Mapeo expediente: {len(mapeo_expedientes):,}")
        print(f"   Mapeo DPI: {len(mapeo_dpi):,}")
        print(f"   Mapeo exp_ref: {len(mapeo_exp_ref):,}")
        
    finally:
        mysql_db.close()
        postgres_db.close()
    
    return stats, mapeo_expedientes, mapeo_dpi, mapeo_exp_ref

# ============================================================================
# PASO 2: MIGRAR CONSULTAS TIPO 1 Y 2 (POR EXPEDIENTE/EXP_REF)
# ============================================================================

def paso2_consultas_tipo_1_y_2(mapeo_expedientes: Dict, mapeo_exp_ref: Dict):
    """Migra consultas tipo 1 y 2 usando expediente o exp_ref"""
    
    print("\n" + "=" * 80)
    print("📍 PASO 2: CONSULTAS TIPO 1 Y 2 (Primera y Subsecuente)")
    print("=" * 80)
    
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()
    
    stats = {
        "consultas_tipo_1": 0,
        "consultas_tipo_2": 0,
        "por_expediente": 0,
        "por_exp_ref": 0,
        "omitidas": 0,
        "errores": 0
    }
    
    try:
        print("\n📋 Buscando consultas tipo 1 y 2...")
        resultado = mysql_db.execute(text("""
            SELECT * FROM consultas
            WHERE tipo_consulta IN (1, 2)
            AND expediente IS NOT NULL
            AND expediente != 0
            ORDER BY id
        """))
        
        batch = []
        for consulta_row in resultado:
            consulta_dict = dict(consulta_row._mapping)
            exp_consulta = str(consulta_dict.get("expediente"))
            tipo = consulta_dict.get("tipo_consulta")
            
            # Buscar en mapeo expediente
            mapeo = mapeo_expedientes.get(exp_consulta)
            metodo = "expediente"
            
            # Si no está, buscar en exp_ref
            if not mapeo:
                mapeo = mapeo_exp_ref.get(exp_consulta)
                metodo = "exp_ref"
            
            if mapeo:
                consulta_pg = transformar_consulta(
                    consulta_dict,
                    mapeo["paciente_id"],
                    mapeo["expediente_pg"]
                )
                
                if consulta_pg:
                    # Marcar método
                    if consulta_pg.get("ciclo") and metodo == "exp_ref":
                        consulta_pg["ciclo"]["metodo_vinculacion"] = "exp_ref"
                    
                    batch.append(consulta_pg)
                    
                    if tipo == 1:
                        stats["consultas_tipo_1"] += 1
                    else:
                        stats["consultas_tipo_2"] += 1
                    
                    if metodo == "expediente":
                        stats["por_expediente"] += 1
                    else:
                        stats["por_exp_ref"] += 1
                else:
                    stats["omitidas"] += 1
            else:
                stats["omitidas"] += 1
            
            if len(batch) >= 1000:
                try:
                    postgres_db.execute(insert_consulta_query, batch)
                    postgres_db.commit()
                    total = stats["consultas_tipo_1"] + stats["consultas_tipo_2"]
                    print(f"   Migradas {total:,} consultas...")
                    batch = []
                except Exception as e:
                    postgres_db.rollback()
                    stats["errores"] += len(batch)
                    print(f"   ❌ Error: {e}")
                    batch = []
        
        if batch:
            try:
                postgres_db.execute(insert_consulta_query, batch)
                postgres_db.commit()
            except Exception as e:
                postgres_db.rollback()
                stats["errores"] += len(batch)
        
        total = stats["consultas_tipo_1"] + stats["consultas_tipo_2"]
        print(f"✅ Consultas tipo 1 y 2: {total:,}")
        print(f"   Tipo 1 (Primera):     {stats['consultas_tipo_1']:,}")
        print(f"   Tipo 2 (Subsecuente): {stats['consultas_tipo_2']:,}")
        print(f"   Por expediente:       {stats['por_expediente']:,}")
        print(f"   Por exp_ref:          {stats['por_exp_ref']:,}")
        
    finally:
        mysql_db.close()
        postgres_db.close()
    
    return stats

# ============================================================================
# PASO 3: MIGRAR CONSULTAS TIPO 3 CON EXPEDIENTE
# ============================================================================

def paso3_consultas_tipo_3_con_expediente(mapeo_expedientes: Dict):
    """Migra consultas tipo 3 (Urgencia) que tienen expediente"""
    
    print("\n" + "=" * 80)
    print("📍 PASO 3: CONSULTAS TIPO 3 CON EXPEDIENTE (Urgencias registradas)")
    print("=" * 80)
    
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()
    
    stats = {
        "consultas": 0,
        "omitidas": 0,
        "errores": 0
    }
    
    try:
        print("\n📋 Buscando consultas tipo 3 con expediente...")
        resultado = mysql_db.execute(text("""
            SELECT * FROM consultas
            WHERE tipo_consulta = 3
            AND expediente IS NOT NULL
            AND expediente != 0
            ORDER BY id
        """))
        
        batch = []
        for consulta_row in resultado:
            consulta_dict = dict(consulta_row._mapping)
            exp_consulta = str(consulta_dict.get("expediente"))
            
            mapeo = mapeo_expedientes.get(exp_consulta)
            
            if mapeo:
                consulta_pg = transformar_consulta(
                    consulta_dict,
                    mapeo["paciente_id"],
                    mapeo["expediente_pg"]
                )
                
                if consulta_pg:
                    batch.append(consulta_pg)
                    stats["consultas"] += 1
                else:
                    stats["omitidas"] += 1
            else:
                stats["omitidas"] += 1
            
            if len(batch) >= 1000:
                try:
                    postgres_db.execute(insert_consulta_query, batch)
                    postgres_db.commit()
                    print(f"   Migradas {stats['consultas']:,} consultas...")
                    batch = []
                except Exception as e:
                    postgres_db.rollback()
                    stats["errores"] += len(batch)
                    batch = []
        
        if batch:
            try:
                postgres_db.execute(insert_consulta_query, batch)
                postgres_db.commit()
            except Exception as e:
                postgres_db.rollback()
                stats["errores"] += len(batch)
        
        print(f"✅ Consultas tipo 3 con expediente: {stats['consultas']:,}")
        
    finally:
        mysql_db.close()
        postgres_db.close()
    
    return stats

# ============================================================================
# PASO 4: MIGRAR CONSULTAS TIPO 3 SIN EXPEDIENTE
# ============================================================================

def paso4_consultas_tipo_3_sin_expediente(mapeo_dpi: Dict):
    """
    Migra consultas tipo 3 (Urgencia) SIN expediente
    - Busca por DPI/CUI
    - Si no existe, crea paciente desde consulta
    """
    
    print("\n" + "=" * 80)
    print("📍 PASO 4: CONSULTAS TIPO 3 SIN EXPEDIENTE (Urgencias sin registro)")
    print("=" * 80)
    
    mysql_db = MySQLSession()
    postgres_db = PostgresSession()
    
    stats = {
        "consultas": 0,
        "por_dpi": 0,
        "pacientes_creados": 0,
        "omitidas": 0,
        "errores": 0
    }
    
    try:
        print("\n📋 Buscando consultas tipo 3 sin expediente...")
        resultado = mysql_db.execute(text("""
            SELECT * FROM consultas
            WHERE tipo_consulta = 3
            AND (expediente IS NULL OR expediente = 0)
            ORDER BY id
        """))
        
        batch_consultas = []
        
        for consulta_row in resultado:
            consulta_dict = dict(consulta_row._mapping)
            
            paciente_id = None
            expediente_pg = None
            metodo = None
            
            # 1. Intentar por DPI - MANEJO ROBUSTO
            dpi_consulta = consulta_dict.get("dpi")
            if dpi_consulta:
                try:
                    dpi_raw = str(dpi_consulta).strip()
                    # Eliminar caracteres no numéricos
                    dpi_clean = ''.join(c for c in dpi_raw if c.isdigit())
                    
                    # Validar exactamente 13 dígitos
                    if len(dpi_clean) == 13:
                        dpi_int = int(dpi_clean)
                        mapeo = mapeo_dpi.get(dpi_int)
                        if mapeo:
                            paciente_id = mapeo["paciente_id"]
                            expediente_pg = mapeo["expediente_pg"]
                            metodo = "dpi"
                            stats["por_dpi"] += 1
                except (ValueError, TypeError):
                    # DPI inválido, continuar sin DPI
                    pass
            
            # 2. Si no existe por DPI, crear paciente
            if not paciente_id:
                try:
                    paciente_id, expediente_pg = crear_paciente_desde_consulta(
                        consulta_dict,
                        postgres_db
                    )
                    metodo = "creado_urgencia"
                    stats["pacientes_creados"] += 1
                    
                    # Actualizar mapeo DPI
                    if dpi_consulta and len(str(dpi_consulta).strip()) == 13:
                        dpi_int = int(str(dpi_consulta).strip())
                        mapeo_dpi[dpi_int] = {
                            "paciente_id": paciente_id,
                            "expediente_pg": expediente_pg
                        }
                    
                except Exception as e:
                    stats["errores"] += 1
                    print(f"   ❌ Error creando paciente: {e}")
                    continue
            
            # 3. Crear consulta
            if paciente_id:
                consulta_pg = transformar_consulta(
                    consulta_dict,
                    paciente_id,
                    expediente_pg
                )
                
                if consulta_pg:
                    if consulta_pg.get("ciclo"):
                        consulta_pg["ciclo"]["metodo_vinculacion"] = metodo
                    
                    batch_consultas.append(consulta_pg)
                    stats["consultas"] += 1
                else:
                    stats["omitidas"] += 1
            
            if len(batch_consultas) >= 1000:
                try:
                    postgres_db.execute(insert_consulta_query, batch_consultas)
                    postgres_db.commit()
                    print(f"   Migradas {stats['consultas']:,} consultas (creados {stats['pacientes_creados']:,} pacientes)...")
                    batch_consultas = []
                except Exception as e:
                    postgres_db.rollback()
                    stats["errores"] += len(batch_consultas)
                    print(f"   ❌ Error: {e}")
                    batch_consultas = []
        
        if batch_consultas:
            try:
                postgres_db.execute(insert_consulta_query, batch_consultas)
                postgres_db.commit()
            except Exception as e:
                postgres_db.rollback()
                stats["errores"] += len(batch_consultas)
        
        print(f"✅ Consultas tipo 3 sin expediente: {stats['consultas']:,}")
        print(f"   Vinculadas por DPI:     {stats['por_dpi']:,}")
        print(f"   Pacientes creados:      {stats['pacientes_creados']:,}")
        
    finally:
        mysql_db.close()
        postgres_db.close()
    
    return stats

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n💡 MIGRACIÓN POR TIPO DE CONSULTA")
    print("\nEstrategia:")
    print("  1️⃣  Migrar todos los pacientes")
    print("  2️⃣  Tipo 1 y 2: Por expediente/exp_ref")
    print("  3️⃣  Tipo 3 CON expediente: Por expediente")
    print("  4️⃣  Tipo 3 SIN expediente: Por DPI o crear paciente")
    print()
    
    respuesta = input("¿Desea continuar? (s/n): ")
    if respuesta.lower() != 's':
        print("❌ Migración cancelada")
        return
    
    inicio = datetime.now()
    
    # PASO 1
    stats_p1, mapeo_exp, mapeo_dpi, mapeo_exp_ref = paso1_migrar_pacientes()
    
    # PASO 2
    stats_p2 = paso2_consultas_tipo_1_y_2(mapeo_exp, mapeo_exp_ref)
    
    # PASO 3
    stats_p3 = paso3_consultas_tipo_3_con_expediente(mapeo_exp)
    
    # PASO 4
    stats_p4 = paso4_consultas_tipo_3_sin_expediente(mapeo_dpi)
    
    tiempo_total = (datetime.now() - inicio).total_seconds()
    
    # RESUMEN
    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL")
    print("=" * 80)
    
    print(f"\nPASO 1: Pacientes")
    print(f"  Total migrados: {stats_p1['pacientes']:,}")
    
    print(f"\nPASO 2: Consultas tipo 1 y 2")
    print(f"  Total: {stats_p2['consultas_tipo_1'] + stats_p2['consultas_tipo_2']:,}")
    print(f"    └─ Tipo 1: {stats_p2['consultas_tipo_1']:,}")
    print(f"    └─ Tipo 2: {stats_p2['consultas_tipo_2']:,}")
    
    print(f"\nPASO 3: Consultas tipo 3 con expediente")
    print(f"  Total: {stats_p3['consultas']:,}")
    
    print(f"\nPASO 4: Consultas tipo 3 sin expediente")
    print(f"  Total: {stats_p4['consultas']:,}")
    print(f"    └─ Por DPI: {stats_p4['por_dpi']:,}")
    print(f"    └─ Pacientes creados: {stats_p4['pacientes_creados']:,}")
    
    total_pacientes = stats_p1['pacientes'] + stats_p4['pacientes_creados']
    total_consultas = (
        stats_p2['consultas_tipo_1'] +
        stats_p2['consultas_tipo_2'] +
        stats_p3['consultas'] +
        stats_p4['consultas']
    )
    
    print(f"\n" + "=" * 80)
    print(f"TOTALES:")
    print(f"  Pacientes: {total_pacientes:,}")
    print(f"  Consultas: {total_consultas:,}")
    print(f"  Tiempo: {tiempo_total:.2f} segundos")
    print("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Cancelado")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)