#!/usr/bin/env python3
# migrate_constancias.py
"""
Script de migración específico para tabla CONSTANCIAS DE NACIMIENTO
Transforma estructura relacional MySQL -> estructura JSONB PostgreSQL
cons_nac (MySQL) → constancia_nacimiento (PostgreSQL)
"""

import os
import sys
import json
from datetime import datetime, date, time
from collections import Counter
from typing import List, Dict, Optional, Any

from sqlalchemy import create_engine, text, bindparam, JSON
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# NORMALIZADORES
# ============================================================================

DOCS_VISTOS = set()


def json_safe(obj: Any) -> Any:
    """Convierte objetos no serializables a tipos JSON-compatibles."""
    from datetime import timedelta
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.strftime("%H:%M:%S")
    if isinstance(obj, timedelta):
        # MySQL TIME devuelto como timedelta → convertir a HH:MM:SS
        total = int(obj.total_seconds())
        h, rem = divmod(abs(total), 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    return obj


def normalizar_documento(doc: Any, id_mysql: Any) -> str:
    """
    Normaliza el número de documento de la constancia.
    Si está vacío o duplicado, genera uno con prefijo CN + id_mysql.
    """
    if not doc or not str(doc).strip():
        return f"CN-AUTO-{id_mysql}"

    doc_limpio = str(doc).strip().upper()

    if doc_limpio in DOCS_VISTOS:
        doc_nuevo = f"CN-DUP-{id_mysql}-{doc_limpio}"
        print(f"   ⚠️  Documento duplicado: '{doc_limpio}' → renombrado a '{doc_nuevo}'")
        DOCS_VISTOS.add(doc_nuevo)
        return doc_nuevo

    DOCS_VISTOS.add(doc_limpio)
    return doc_limpio


def normalizar_expediente(exp: str) -> str:
    return str(exp).strip().upper().lstrip("0")


def normalizar_sexo_rn(sexo: Any) -> Optional[str]:
    """Normaliza el sexo del recién nacido a M/F."""
    if not sexo:
        return None
    s = str(sexo).strip().upper()
    if s in ("M", "MASCULINO", "H", "HOMBRE"):
        return "M"
    if s in ("F", "FEMENINO", "MUJER"):
        return "F"
    return None


def construir_menor_edad_jsonb(row: dict) -> dict:
    """Construye el JSONB con los datos del recién nacido."""
    return json_safe({
        "sexo":        normalizar_sexo_rn(row.get("sexo_rn")),
        "fecha_parto": row.get("fecha_parto"),
        "hora_parto":  row.get("hora"),
        "peso_lb":     row.get("lb"),
        "peso_onz":    row.get("onz"),
        "tipo_parto":  row.get("tipo_parto"),
        "clase_parto": row.get("clase_parto"),
        "edad_madre":  row.get("edad"),
    })


def construir_metadata_jsonb(row: dict, id_mysql: Any) -> dict:
    """Construye el JSONB con todos los campos sin columna propia en Postgres."""
    return json_safe({
        "mysql_id":      id_mysql,
        "cor":           row.get("cor"),
        "ao":            row.get("ao"),
        "libro":         row.get("libro"),
        "folio":         row.get("folio"),
        "partida":       row.get("partida"),
        "expediente":    row.get("expediente"),
        "dpi_madre":     row.get("dpi"),
        "passport":      row.get("passport"),
        "pais":          row.get("pais"),
        "nacionalidad":  row.get("nacionalidad"),
        "certifica":     row.get("certifica"),
        "medico_nombre": row.get("medico"),
        "colegiado":     row.get("colegiado"),
        "muni_id":       row.get("muni"),
        "depto_id":      row.get("depto"),
        "vecindad_id":   row.get("vecindad"),
        "create_by":     row.get("create_by"),
    })


# ============================================================================
# HELPER DE QUERY — usa postgres_ro_engine (definido más adelante globalmente)
# ============================================================================

def _query_one(sql: str, params: dict) -> Optional[Any]:
    """
    Ejecuta un SELECT de lookup usando el engine AUTOCOMMIT.
    Cada llamada abre y cierra su propia conexión, nunca deja
    una transacción rota.
    """
    try:
        with postgres_ro_engine.connect() as conn:
            return conn.execute(text(sql), params).fetchone()
    except Exception as e:
        print(f"   ⚠️  Resolver error: {e}")
        return None


# ============================================================================
# CARGA DE MAPA EN MEMORIA
# ============================================================================

def cargar_mapa_expedientes() -> dict:
    """
    Precarga todos los expedientes de pacientes activos en un dict
    {expediente_normalizado: paciente_id} para evitar un SELECT por fila.
    """
    with postgres_ro_engine.connect() as conn:
        filas = conn.execute(text("""
            SELECT expediente, id
            FROM pacientes
            WHERE expediente IS NOT NULL
              AND estado <> 'I'
        """)).fetchall()

    mapa = {}
    for exp, pid in filas:
        if exp:
            mapa[normalizar_expediente(exp)] = pid
    return mapa


# ============================================================================
# RESOLVERS (sin pg_conn — usan _query_one con engine global AUTOCOMMIT)
# ============================================================================

def resolver_paciente_id(row: dict, mapa_expedientes: dict) -> Optional[int]:
    """
    1° Busca por expediente en el mapa en memoria.
    2° Fallback: DPI/CUI directo en BD.
    """
    expediente = row.get("expediente")
    if expediente and str(expediente).strip():
        paciente_id = mapa_expedientes.get(normalizar_expediente(expediente))
        if paciente_id:
            return paciente_id

    dpi = row.get("dpi")
    if dpi:
        try:
            result = _query_one(
                "SELECT id FROM pacientes WHERE cui = :cui AND estado <> 'I' LIMIT 1",
                {"cui": int(dpi)}
            )
            if result:
                return result[0]
        except (ValueError, TypeError):
            pass

    return None


def resolver_medico_id(row: dict) -> Optional[int]:
    """
    1° Busca por colegiado (int).
    2° Fallback: DPI del médico.
    """
    colegiado = row.get("colegiado")
    if colegiado and str(colegiado).strip():
        try:
            result = _query_one(
                "SELECT id FROM medicos WHERE colegiado = :col LIMIT 1",
                {"col": int(str(colegiado).strip())}
            )
            if result:
                return result[0]
        except (ValueError, TypeError):
            pass

    dpi_medico = row.get("dpi_medico")
    if dpi_medico and str(dpi_medico).strip():
        try:
            result = _query_one(
                "SELECT id FROM medicos WHERE dpi = :dpi LIMIT 1",
                {"dpi": int(str(dpi_medico).strip())}
            )
            if result:
                return result[0]
        except (ValueError, TypeError):
            pass

    return None


def resolver_registrador_id(row: dict, fallback_id: int = 1) -> int:
    """Busca por username (create_by). Si no existe, usa fallback_id."""
    create_by = row.get("create_by")
    if create_by and str(create_by).strip():
        result = _query_one(
            "SELECT id FROM users WHERE username = :usr LIMIT 1",
            {"usr": str(create_by).strip()}
        )
        if result:
            return result[0]
    return fallback_id


def resolver_vecindad_texto(row: dict) -> Optional[str]:
    """Construye texto de vecindad_madre a partir de muni y depto."""
    partes = []

    muni_id = row.get("muni")
    if muni_id:
        result = _query_one(
            "SELECT nombre FROM municipios WHERE id = :id LIMIT 1",
            {"id": muni_id}
        )
        if result:
            partes.append(result[0])

    depto_id = row.get("depto")
    if depto_id:
        result = _query_one(
            "SELECT nombre FROM departamentos WHERE id = :id LIMIT 1",
            {"id": depto_id}
        )
        if result:
            partes.append(result[0])

    return ", ".join(partes) if partes else None


# ============================================================================
# CONFIGURACIÓN DE CONEXIONES
# ============================================================================

def construir_url_mysql():
    return (
        f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:"
        f"{os.getenv('MYSQL_PASSWORD', 'Prometeus.0')}@"
        f"{os.getenv('MYSQL_HOST', 'localhost')}:"
        f"{os.getenv('MYSQL_PORT', '3306')}/"
        f"{os.getenv('MYSQL_DATABASE', 'test_api')}"
    )

def construir_url_postgres():
    return (
        f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'secreto123')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'hospital')}"
    )

MYSQL_URL    = construir_url_mysql()
POSTGRES_URL = construir_url_postgres()

print("=" * 80)
print("🏥  MIGRACIÓN CONSTANCIAS DE NACIMIENTO: MySQL → PostgreSQL")
print("=" * 80)
print(f"Origen  (MySQL):      {MYSQL_URL.split('@')[1]}")
print(f"Destino (PostgreSQL): {POSTGRES_URL.split('@')[1]}")
print("=" * 80)

print("\n🔌 Conectando a bases de datos...")
try:
    mysql_engine    = create_engine(MYSQL_URL, echo=False)
    postgres_engine = create_engine(POSTGRES_URL, echo=False)

    # Engine AUTOCOMMIT para resolvers: cada SELECT es independiente,
    # nunca queda una transacción rota que contamine los siguientes queries.
    postgres_ro_engine = create_engine(
        POSTGRES_URL, echo=False, isolation_level="AUTOCOMMIT"
    )

    MySQLSession    = sessionmaker(bind=mysql_engine)
    PostgresSession = sessionmaker(bind=postgres_engine)

    with mysql_engine.connect()    as c: c.execute(text("SELECT 1"))
    with postgres_engine.connect() as c: c.execute(text("SELECT 1"))

    print("✅ Conexiones establecidas\n")
except Exception as e:
    print(f"❌ Error al conectar: {e}")
    sys.exit(1)


# ============================================================================
# TRANSFORMACIÓN PRINCIPAL
# ============================================================================

def transformar_constancia(row: Any, mapa_expedientes: dict) -> tuple[dict, list[str]]:
    """
    Transforma un registro de cons_nac (MySQL) al formato
    de constancia_nacimiento (PostgreSQL).
    Retorna (registro_dict, lista_de_advertencias).
    """
    advertencias = []

    if not isinstance(row, dict):
        row = dict(row._mapping)

    id_mysql = row.get("id")

    documento    = normalizar_documento(row.get("doc"), id_mysql)
    paciente_id  = resolver_paciente_id(row, mapa_expedientes)
    medico_id    = resolver_medico_id(row)
    registrador_id = resolver_registrador_id(row, fallback_id=1)
    vecindad_madre = resolver_vecindad_texto(row)
    menor_edad   = construir_menor_edad_jsonb(row)
    metadata     = construir_metadata_jsonb(row, id_mysql)

    if paciente_id is None:
        advertencias.append(
            f"[id={id_mysql}] paciente_id no encontrado "
            f"(dpi={row.get('dpi')}, expediente={row.get('expediente')}, "
            f"madre='{row.get('madre')}')"
        )
    if medico_id is None:
        advertencias.append(
            f"[id={id_mysql}] medico_id no encontrado "
            f"(colegiado={row.get('colegiado')}, dpi_medico={row.get('dpi_medico')})"
        )

    registro = {
        "documento":      documento,
        "paciente_id":    paciente_id,
        "medico_id":      medico_id,
        "registrador_id": registrador_id,
        "nombre_madre":   str(row.get("madre") or "").strip() or "DESCONOCIDA",
        "vecindad_madre": vecindad_madre,
        "fecha_registro": row.get("fecha") or date.today(),
        "menor_edad":     menor_edad,
        "hijos":          row.get("hijos"),
        "vivos":          row.get("vivos"),
        "muertos":        row.get("muertos"),
        "observaciones":  None,
        "metadata":       metadata,
        "created_at":     row.get("created_at") or datetime.now(),
        "updated_at":     row.get("updated_at") or datetime.now(),
    }

    return registro, advertencias


# ============================================================================
# QUERY DE INSERCIÓN
# ============================================================================

INSERT_QUERY = text("""
INSERT INTO constancia_nacimiento (
    documento, paciente_id, medico_id, registrador_id,
    nombre_madre, vecindad_madre, fecha_registro,
    menor_edad, hijos, vivos, muertos,
    observaciones, metadata, created_at, updated_at
) VALUES (
    :documento, :paciente_id, :medico_id, :registrador_id,
    :nombre_madre, :vecindad_madre, :fecha_registro,
    :menor_edad, :hijos, :vivos, :muertos,
    :observaciones, :metadata, :created_at, :updated_at
)
ON CONFLICT (documento) DO UPDATE SET
    paciente_id    = EXCLUDED.paciente_id,
    medico_id      = EXCLUDED.medico_id,
    registrador_id = EXCLUDED.registrador_id,
    nombre_madre   = EXCLUDED.nombre_madre,
    vecindad_madre = EXCLUDED.vecindad_madre,
    fecha_registro = EXCLUDED.fecha_registro,
    menor_edad     = EXCLUDED.menor_edad,
    hijos          = EXCLUDED.hijos,
    vivos          = EXCLUDED.vivos,
    muertos        = EXCLUDED.muertos,
    metadata       = EXCLUDED.metadata,
    updated_at     = NOW()
""").bindparams(
    bindparam("menor_edad", type_=JSON),
    bindparam("metadata",   type_=JSON),
)


# ============================================================================
# MIGRACIÓN
# ============================================================================

def imprimir_docs_duplicados(batch: List[Dict], contexto: str = "") -> None:
    """Detecta e imprime documentos duplicados dentro de un batch."""
    conteo = Counter(r["documento"] for r in batch if r.get("documento"))
    duplicados = {d: c for d, c in conteo.items() if c > 1}
    if duplicados:
        print(f"\n⚠️  DOCUMENTOS DUPLICADOS EN BATCH [{contexto}]")
        for doc, veces in duplicados.items():
            print(f"   🔁 {doc} → {veces} veces")
        print()


def migrar_constancias(batch_size: int = 500) -> dict:
    mysql_db    = MySQLSession()
    postgres_db = PostgresSession()

    stats = {
        "total":        0,
        "exitosos":     0,
        "errores":      0,
        "sin_paciente": 0,
        "sin_medico":   0,
        "advertencias": [],
    }
    inicio = datetime.now()

    try:
        print("📦 Cargando mapa de expedientes en memoria...")
        mapa_expedientes = cargar_mapa_expedientes()
        print(f"   {len(mapa_expedientes):,} expedientes cargados\n")

        filas = mysql_db.execute(text("SELECT * FROM cons_nac")).fetchall()
        stats["total"] = len(filas)
        print(f"📋 Total de registros a migrar: {stats['total']:,}\n")

        batch = []

        for i, fila in enumerate(filas, 1):
            try:
                registro, advertencias = transformar_constancia(fila, mapa_expedientes)

                if advertencias:
                    stats["advertencias"].extend(advertencias)
                    if any("paciente_id" in a for a in advertencias):
                        stats["sin_paciente"] += 1
                    if any("medico_id" in a for a in advertencias):
                        stats["sin_medico"] += 1

                # Sin FK obligatorias no se puede insertar
                if registro["paciente_id"] is None or registro["medico_id"] is None:
                    print(
                        f"   ⛔ Omitido id={fila._mapping.get('id')}: "
                        f"paciente_id={registro['paciente_id']} | "
                        f"medico_id={registro['medico_id']}"
                    )
                    stats["errores"] += 1
                    continue

                batch.append(registro)

                if i % batch_size == 0:
                    imprimir_docs_duplicados(batch, contexto=f"hasta registro {i}")
                    try:
                        postgres_db.execute(INSERT_QUERY, batch)
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
                stats["advertencias"].append(f"Error en fila {i}: {e}")

        # Batch final
        if batch:
            imprimir_docs_duplicados(batch, contexto="batch final")
            try:
                postgres_db.execute(INSERT_QUERY, batch)
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

def verificar_migracion() -> None:
    mysql_db    = MySQLSession()
    postgres_db = PostgresSession()

    try:
        print("\n" + "=" * 80)
        print("🔍 VERIFICACIÓN DE MIGRACIÓN")
        print("=" * 80)

        total_mysql = mysql_db.execute(text("SELECT COUNT(*) FROM cons_nac")).scalar()
        total_pg    = postgres_db.execute(text("SELECT COUNT(*) FROM constancia_nacimiento")).scalar()

        print(f"\n📊 Conteo de registros:")
        print(f"   MySQL (cons_nac):                  {total_mysql:,}")
        print(f"   PostgreSQL (constancia_nacimiento): {total_pg:,}")

        masculinos = postgres_db.execute(text(
            "SELECT COUNT(*) FROM constancia_nacimiento WHERE menor_edad->>'sexo' = 'M'"
        )).scalar()
        femeninos = postgres_db.execute(text(
            "SELECT COUNT(*) FROM constancia_nacimiento WHERE menor_edad->>'sexo' = 'F'"
        )).scalar()
        print(f"\n   Recién nacidos M: {masculinos:,} | F: {femeninos:,}")

        print(f"\n   Últimas 5 constancias migradas:")
        ultimas = postgres_db.execute(text("""
            SELECT id, documento, nombre_madre, fecha_registro
            FROM constancia_nacimiento
            ORDER BY id DESC LIMIT 5
        """)).fetchall()
        for r in ultimas:
            print(f"   → [{r[0]}] {r[1]} | {r[2]} | {r[3]}")

    finally:
        mysql_db.close()
        postgres_db.close()


# ============================================================================
# MAIN
# ============================================================================

def main():
    stats = migrar_constancias()
    verificar_migracion()

    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL DE MIGRACIÓN")
    print("=" * 80)
    print(f"Total procesados:          {stats['total']:,}")
    print(f"Migrados exitosos:         {stats['exitosos']:,}")
    print(f"Errores / omitidos:        {stats['errores']:,}")
    print(f"Sin paciente encontrado:   {stats['sin_paciente']:,}")
    print(f"Sin médico encontrado:     {stats['sin_medico']:,}")
    print(f"Tiempo total:              {stats.get('tiempo', 0):.2f} segundos")
    print("=" * 80)

    if stats["advertencias"]:
        print(f"\n⚠️  ADVERTENCIAS ({len(stats['advertencias'])}):")
        for adv in stats["advertencias"][:20]:
            print(f"   • {adv}")
        if len(stats["advertencias"]) > 20:
            print(f"   ... y {len(stats['advertencias']) - 20} más.")
    print()


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