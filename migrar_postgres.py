#!/usr/bin/env python3
"""
migrar_postgres.py
Migración MySQL (pacientes_master + consultas_master) → PostgreSQL

Los datos ya fueron limpiados y normalizados por preparar_mysql.py:
  - Nombres capitalizados sin acentos
  - DPI validado como BIGINT de 13 dígitos
  - Duplicados eliminados
  - Cada consulta tiene paciente_id

Este script solo transforma la estructura y migra.

FIXES aplicados:
  - Bug: normalizar_cui() se llamaba sin el argumento cuis_vistos → TypeError en runtime
  - Bug: rollback en paso 1 revertía el batch completo, corrompiendo mapeo_id
  - Bug: lotes fallidos en paso 2 descartaban registros válidos sin reintento
  - Bug: telefono_responsable se limpiaba dos veces (en transformar_paciente y en construir_referencias_jsonb)
  - Bug: expediente fallback "X?" generaba duplicados cuando consulta_id es NULL
  - Mejora: mapeo_id y mapeo_exp se serializan a disco tras paso 1 para poder reanudar
  - Mejora: reintento individual cuando falla un lote en paso 2
"""

import os
import sys
import json
from datetime import datetime, date, time
from typing import Optional, Dict, Any, List

from sqlalchemy import create_engine, text, bindparam, JSON
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.utils.normalizadores import (
    CUIS_VISTOS,                    # FIX: importar el set global
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
)
from app.utils.normalizadores_consultas import (
    normalizar_consulta_completa,
    normalizar_estado_ciclo,
)

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def _url_mysql() -> str:
    return (
        f"mysql+pymysql://{os.getenv('MYSQL_USER','root')}:"
        f"{os.getenv('MYSQL_PASSWORD','')}@"
        f"{os.getenv('MYSQL_HOST','localhost')}:"
        f"{os.getenv('MYSQL_PORT','3306')}/"
        f"{os.getenv('MYSQL_DATABASE','test_api')}"
    )

def _url_postgres() -> str:
    return (
        f"postgresql://{os.getenv('POSTGRES_USER','postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD','')}@"
        f"{os.getenv('POSTGRES_HOST','localhost')}:"
        f"{os.getenv('POSTGRES_PORT','5432')}/"
        f"{os.getenv('POSTGRES_DB','hospital')}"
    )

mysql_engine    = create_engine(_url_mysql(),    echo=False)
postgres_engine = create_engine(_url_postgres(), echo=False)
MySQLSession    = sessionmaker(bind=mysql_engine)
PostgresSession = sessionmaker(bind=postgres_engine)

BATCH_SIZE   = 500    # registros por commit
MAPEO_FILE   = "mapeo_migracion.json"   # archivo de reanudación


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def barra(actual: int, total: int, largo: int = 35, prefijo: str = "") -> None:
    if total == 0:
        return
    pct     = actual / total
    lleno   = int(largo * pct)
    barra_s = "█" * lleno + "░" * (largo - lleno)
    print(f"\r  {prefijo}[{barra_s}] {int(pct*100):3d}% ({actual}/{total})",
          end="", flush=True)
    if actual >= total:
        print()


def titulo(texto: str) -> None:
    linea = "─" * 60
    print(f"\n{linea}\n  {texto}\n{linea}")


def ok(msg: str)   -> None: print(f"  ✓ {msg}")
def info(msg: str) -> None: print(f"  → {msg}")
def warn(msg: str) -> None: print(f"  ⚠ {msg}")


def json_serial(obj):
    """Serializa tipos Python que json.dumps no soporta."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def guardar_mapeo(mapeo_id: Dict[int, int], mapeo_exp: Dict[str, str]) -> None:
    """
    Serializa los mapeos a disco para poder reanudar el paso 2
    sin re-migrar pacientes si el proceso muere a mitad.
    """
    payload = {
        "mapeo_id":  {str(k): v for k, v in mapeo_id.items()},
        "mapeo_exp": mapeo_exp,
    }
    with open(MAPEO_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    ok(f"Mapeo guardado en {MAPEO_FILE} ({len(mapeo_id):,} pacientes)")


def cargar_mapeo() -> Optional[tuple[Dict[int, int], Dict[str, str]]]:
    """
    Carga los mapeos desde disco si el archivo existe.
    Retorna None si no existe.
    """
    if not os.path.exists(MAPEO_FILE):
        return None
    with open(MAPEO_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    mapeo_id  = {int(k): v for k, v in payload["mapeo_id"].items()}
    mapeo_exp = payload["mapeo_exp"]
    ok(f"Mapeo cargado desde {MAPEO_FILE} ({len(mapeo_id):,} pacientes)")
    return mapeo_id, mapeo_exp


# ─────────────────────────────────────────────────────────────────────────────
# QUERIES POSTGRES
# ─────────────────────────────────────────────────────────────────────────────

INSERT_PACIENTE = text("""
INSERT INTO pacientes (
    expediente, cui, pasaporte, nombre, sexo, fecha_nacimiento,
    contacto, referencias, datos_extra, estado, metadatos,
    nombre_completo, creado_en, actualizado_en
) VALUES (
    :expediente, :cui, :pasaporte, :nombre, :sexo, :fecha_nacimiento,
    :contacto, :referencias, :datos_extra, :estado, :metadatos,
    :nombre_completo, :creado_en, :actualizado_en
)
ON CONFLICT (expediente) DO UPDATE SET
    cui             = COALESCE(EXCLUDED.cui, pacientes.cui),
    nombre          = EXCLUDED.nombre,
    nombre_completo = EXCLUDED.nombre_completo,
    actualizado_en  = NOW()
RETURNING id
""").bindparams(
    bindparam("nombre",      type_=JSON),
    bindparam("contacto",    type_=JSON),
    bindparam("referencias", type_=JSON),
    bindparam("datos_extra", type_=JSON),
    bindparam("metadatos",   type_=JSON),
)

INSERT_CONSULTA = text("""
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
    bindparam("ciclo",       type_=JSON),
)


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFORMADORES
# ─────────────────────────────────────────────────────────────────────────────

def _nombre_completo(nombre: str, apellido: str) -> str:
    """Genera nombre_completo para el índice trgm de PostgreSQL."""
    partes = [p for p in [nombre, apellido] if p]
    return " ".join(partes).strip()


def transformar_paciente(row: Dict) -> Dict:
    """
    Convierte una fila de pacientes_master al formato PostgreSQL.
    La limpieza (acentos, DPI, capitalización) ya fue hecha en preparar_mysql.py.
    """
    id_mysql            = row["id"]
    expediente_original = row.get("expediente")
    es_duplicado        = validar_expediente_duplicado(expediente_original)
    expediente          = normalizar_expediente(expediente_original, id_mysql)

    # FIX: pasar CUIS_VISTOS como segundo argumento (antes faltaba → TypeError)
    cui = normalizar_cui(row.get("dpi"), CUIS_VISTOS)

    nombre_json = construir_nombre_jsonb(
        nombre   = row.get("nombre"),
        apellido = row.get("apellido"),
    )

    contacto_json = construir_contacto_jsonb(
        telefonos = limpiar_telefono(row.get("telefono")),
        email     = row.get("email"),
        domicilio = row.get("direccion"),
        municipio = str(row["municipio"]) if row.get("municipio") else None,
    )

    # FIX: NO limpiar telefono_responsable aquí — construir_referencias_jsonb ya lo hace
    # internamente. Limpiar dos veces era redundante y podía confundir el flujo.
    referencias_json = construir_referencias_jsonb(
        padre                  = row.get("padre"),
        madre                  = row.get("madre"),
        responsable            = row.get("responsable"),
        parentesco_responsable = row.get("parentesco"),
        dpi_responsable        = row.get("dpi_responsable"),
        telefono_responsable   = row.get("telefono_responsable"),   # sin pre-limpiar
        conyugue               = row.get("conyugue"),
    )

    datos_extra_json = construir_datos_extra_jsonb(
        nacionalidad     = row.get("nacionalidad"),
        depto_nac        = str(row["depto_nac"]) if row.get("depto_nac") else None,
        lugar_nacimiento = str(row["lugar_nacimiento"]) if row.get("lugar_nacimiento") else None,
        estado_civil     = row.get("estado_civil"),
        educacion        = row.get("educacion"),
        pueblo           = row.get("pueblo"),
        idioma           = row.get("idioma"),
        ocupacion        = row.get("ocupacion"),
        fecha_defuncion  = row.get("fechaDefuncion"),
        hora_defuncion   = str(row["hora_defuncion"]) if row.get("hora_defuncion") else None,
        gemelo           = row.get("gemelo"),
        expediente_madre = str(row["exp_madre"]) if row.get("exp_madre") else None,
        personaid        = str(cui) if cui else None,
    )

    metadatos_json = construir_metadatos_jsonb(
        id_mysql             = id_mysql,
        created_by           = row.get("created_by"),
        created_at           = str(row["created_at"]) if row.get("created_at") else None,
        expediente_duplicado = es_duplicado,
    )

    if row.get("exp_migrado") and metadatos_json:
        metadatos_json[0]["exp_migrado"] = row["exp_migrado"]

    if row.get("fuente") and metadatos_json:
        metadatos_json[0]["fuente_mysql"] = row["fuente"]

    return {
        "expediente":       expediente,
        "cui":              cui,
        "pasaporte":        normalizar_pasaporte(row.get("pasaporte")),
        "nombre":           json_safe(nombre_json),
        "sexo":             normalizar_sexo(row.get("sexo")),
        "fecha_nacimiento": row.get("nacimiento"),
        "contacto":         json_safe(contacto_json),
        "referencias":      json_safe(referencias_json),
        "datos_extra":      json_safe(datos_extra_json),
        "estado":           normalizar_estado(row.get("estado")),
        "metadatos":        json_safe(metadatos_json),
        "nombre_completo":  _nombre_completo(row.get("nombre",""), row.get("apellido","")),
        "creado_en":        row.get("created_at") or datetime.now(),
        "actualizado_en":   row.get("update_at")  or datetime.now(),
    }


def _construir_indicadores(c: Dict) -> Optional[Dict]:
    """Construye JSONB de indicadores booleanos desde consultas_master."""
    campos = [
        "prenatal", "lactancia", "bomberos", "transito",
        "arma_blanca", "arma_fuego", "estudiante_publica",
        "accidente_laboral", "personal_hospital", "reserva",
    ]
    ind = {}
    for campo in campos:
        val = c.get(campo)
        if val:
            try:
                if int(val) > 0:
                    ind[campo] = True
            except (TypeError, ValueError):
                pass
    return ind if ind else None


def _construir_ciclo(c: Dict, c_norm: Dict) -> Dict:
    """Construye JSONB ciclo mezclando datos crudos y normalizados."""
    ciclo = {
        "id_mysql":               c.get("consulta_id"),
        "match_criterio":         c.get("match_criterio"),
        "hoja_emergencia":        c_norm.get("hoja_emergencia"),
        "diagnostico":            c_norm.get("diagnostico"),
        "medico":                 c_norm.get("medico"),
        "acompanante":            c_norm.get("acompanante"),
        "parentesco_acompanante": c_norm.get("parentesco_acompanante"),
        "notas":                  c_norm.get("notas"),
        "folios":                 c_norm.get("folios"),
        "fecha_egreso":           str(c["fecha_egreso"]) if c.get("fecha_egreso") else None,
        "fecha_recepcion":        str(c["fecha_recepcion"]) if c.get("fecha_recepcion") else None,
        "consulta_por":           c.get("consulta_por"),
        "created_by":             c.get("created_by"),
        "archived_by":            c.get("archived_by"),
        "estado":                 normalizar_estado_ciclo(c.get("status")),
    }
    return {k: v for k, v in ciclo.items() if v is not None}


def transformar_consulta(row: Dict, expediente_pg: str) -> Optional[Dict]:
    """
    Convierte una fila de consultas_master al formato PostgreSQL.
    """
    c_norm = normalizar_consulta_completa(row)

    if not c_norm:
        return None   # Sin fecha válida — no migrar

    return {
        "expediente":     expediente_pg,
        "paciente_id":    row["paciente_id"],
        "tipo_consulta":  c_norm["tipo_consulta"],
        "especialidad":   c_norm["especialidad"],
        "servicio":       c_norm["servicio"],
        "documento":      c_norm.get("hoja_emergencia"),
        "fecha_consulta": c_norm["fecha_consulta"],
        "hora_consulta":  c_norm["hora_consulta"],
        "indicadores":    json_safe(_construir_indicadores(row)),
        "ciclo":          json_safe(_construir_ciclo(row, c_norm)),
        "orden":          None,
        "creado_en":      row.get("created_at") or datetime.now(),
        "actualizado_en": row.get("updated_at") or datetime.now(),
        "activo":         True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PASO 0 — LIMPIAR TABLAS POSTGRESQL
# ─────────────────────────────────────────────────────────────────────────────

def limpiar_tablas_postgres() -> None:
    titulo("PASO 0 — LIMPIAR TABLAS POSTGRESQL")

    postgres_db = PostgresSession()
    TABLAS = ["consultas", "pacientes"]

    try:
        for tabla in TABLAS:
            n_antes = postgres_db.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
            info(f"Truncando {tabla} ({n_antes:,} registros)...")
            postgres_db.execute(text(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE"))

        postgres_db.commit()
        ok("Tablas limpiadas — secuencias reiniciadas")

    except Exception as e:
        postgres_db.rollback()
        raise RuntimeError(f"Error limpiando tablas PostgreSQL: {e}") from e
    finally:
        postgres_db.close()

    # Limpiar también el archivo de mapeo previo para que no quede desincronizado
    if os.path.exists(MAPEO_FILE):
        os.remove(MAPEO_FILE)
        info(f"Archivo de mapeo anterior eliminado: {MAPEO_FILE}")


# ─────────────────────────────────────────────────────────────────────────────
# PASO 1 — MIGRAR pacientes_master → pacientes (PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────

def paso_1_migrar_pacientes() -> Dict[str, Any]:
    titulo("PASO 1 — MIGRAR pacientes_master → PostgreSQL")

    mysql_db    = MySQLSession()
    postgres_db = PostgresSession()

    mapeo_id:  Dict[int, int]  = {}
    mapeo_exp: Dict[str, str]  = {}
    stats = {"ok": 0, "error": 0, "total": 0}

    try:
        stats["total"] = mysql_db.execute(
            text("SELECT COUNT(*) FROM pacientes_master")
        ).scalar()
        info(f"Total pacientes_master: {stats['total']:,}")

        rows = mysql_db.execute(
            text("SELECT * FROM pacientes_master ORDER BY id")
        ).mappings().all()

        for i, row in enumerate(rows, 1):
            row = dict(row)
            try:
                paciente_pg = transformar_paciente(row)
                res  = postgres_db.execute(INSERT_PACIENTE, paciente_pg)
                pg_id = res.fetchone()[0]

                # Guardar mapeo ANTES del commit para que sea consistente
                mapeo_id[row["id"]] = pg_id
                exp_mysql = str(row["expediente"]) if row.get("expediente") else None
                if exp_mysql:
                    mapeo_exp[exp_mysql] = paciente_pg["expediente"]

                stats["ok"] += 1

                # FIX: commit individual por batch — si falla un registro se revierte
                # solo él (el try/except está por fila, no por batch), nunca los anteriores.
                if stats["ok"] % BATCH_SIZE == 0:
                    postgres_db.commit()

            except Exception as e:
                # FIX: rollback solo del registro actual, no del batch entero.
                # Al estar el try dentro del for, el rollback no afecta los registros
                # ya commiteados en batches anteriores.
                postgres_db.rollback()
                stats["error"] += 1
                # Asegurarse de NO agregar este id al mapeo si falló
                mapeo_id.pop(row.get("id"), None)
                if stats["error"] <= 10:
                    warn(f"Error paciente id={row.get('id')}: {e}")

            barra(i, stats["total"], prefijo="  Pacientes ")

        # Commit del último batch parcial
        postgres_db.commit()
        ok(f"Migrados: {stats['ok']:,}  Errores: {stats['error']:,}")

    finally:
        mysql_db.close()
        postgres_db.close()

    # FIX: guardar mapeo a disco para poder reanudar el paso 2 sin repetir el paso 1
    guardar_mapeo(mapeo_id, mapeo_exp)

    return {"stats": stats, "mapeo_id": mapeo_id, "mapeo_exp": mapeo_exp}


# ─────────────────────────────────────────────────────────────────────────────
# PASO 2 — MIGRAR consultas_master → consultas (PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────

def _flush_batch_con_reintento(
    postgres_db,
    batch: List[Dict],
    stats: Dict,
) -> None:
    """
    Intenta insertar el batch completo.
    Si falla, reintenta fila a fila para aislar el registro problemático
    y no descartar consultas válidas junto con la inválida.
    """
    try:
        postgres_db.execute(INSERT_CONSULTA, batch)
        postgres_db.commit()
        stats["ok"] += len(batch)
    except Exception as e_lote:
        postgres_db.rollback()
        warn(f"Lote falló ({len(batch)} registros), reintentando uno a uno: {e_lote}")
        for consulta in batch:
            try:
                postgres_db.execute(INSERT_CONSULTA, consulta)
                postgres_db.commit()
                stats["ok"] += 1
            except Exception as e_fila:
                postgres_db.rollback()
                stats["error"] += 1
                if stats["error"] <= 10:
                    warn(f"  Error consulta id_mysql={consulta.get('ciclo', {}).get('id_mysql','?')}: {e_fila}")


def paso_2_migrar_consultas(mapeo_id: Dict[int, int], mapeo_exp: Dict[str, str]) -> Dict:
    titulo("PASO 2 — MIGRAR consultas_master → PostgreSQL")

    mysql_db    = MySQLSession()
    postgres_db = PostgresSession()

    stats = {
        "ok": 0, "error": 0, "sin_fecha": 0,
        "sin_paciente": 0, "total": 0,
    }

    try:
        stats["total"] = mysql_db.execute(
            text("SELECT COUNT(*) FROM consultas_master")
        ).scalar()
        info(f"Total consultas_master: {stats['total']:,}")

        rows = mysql_db.execute(
            text("SELECT * FROM consultas_master ORDER BY id")
        ).mappings().all()

        batch: List[Dict] = []

        for i, row in enumerate(rows, 1):
            row = dict(row)

            # ── Resolver paciente_id en PostgreSQL ────────────────────────
            pg_paciente_id = mapeo_id.get(row.get("paciente_id"))
            if not pg_paciente_id:
                stats["sin_paciente"] += 1
                barra(i, stats["total"], prefijo="  Consultas ")
                continue

            # ── Resolver expediente en PostgreSQL ─────────────────────────
            exp_mysql = str(row["expediente"]) if row.get("expediente") else None

            # FIX: fallback seguro — usar row["id"] como último recurso para
            # evitar expediente "X?" cuando consulta_id es NULL (genera duplicados)
            if not exp_mysql:
                fallback_id = row.get("consulta_id") or row.get("id")
                expediente_pg = f"XCONSULTA{fallback_id}"
            else:
                expediente_pg = mapeo_exp.get(exp_mysql, exp_mysql)

            # ── Transformar ───────────────────────────────────────────────
            consulta_pg = transformar_consulta(dict(row), expediente_pg)

            if not consulta_pg:
                stats["sin_fecha"] += 1
                barra(i, stats["total"], prefijo="  Consultas ")
                continue

            consulta_pg["paciente_id"] = pg_paciente_id
            batch.append(consulta_pg)

            # ── Flush por lotes con reintento individual ──────────────────
            if len(batch) >= BATCH_SIZE:
                _flush_batch_con_reintento(postgres_db, batch, stats)
                batch = []

            barra(i, stats["total"], prefijo="  Consultas ")

        # ── Último lote ───────────────────────────────────────────────────
        if batch:
            _flush_batch_con_reintento(postgres_db, batch, stats)

        ok(f"Migradas: {stats['ok']:,}  "
           f"Sin paciente: {stats['sin_paciente']:,}  "
           f"Sin fecha: {stats['sin_fecha']:,}  "
           f"Errores: {stats['error']:,}")

    finally:
        mysql_db.close()
        postgres_db.close()

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# VERIFICACIÓN POST-MIGRACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def verificar():
    titulo("VERIFICACIÓN POST-MIGRACIÓN")

    mysql_db    = MySQLSession()
    postgres_db = PostgresSession()

    try:
        tablas_mysql = [
            ("pacientes_master", "SELECT COUNT(*) FROM pacientes_master"),
            ("consultas_master", "SELECT COUNT(*) FROM consultas_master"),
        ]
        tablas_pg = [
            ("pacientes (PG)",   "SELECT COUNT(*) FROM pacientes"),
            ("consultas (PG)",   "SELECT COUNT(*) FROM consultas"),
        ]

        print()
        print(f"  {'Tabla':<25} {'Registros':>12}")
        print(f"  {'─'*25} {'─'*12}")

        for nombre, query in tablas_mysql:
            n = mysql_db.execute(text(query)).scalar()
            print(f"  {nombre:<25} {n:>12,}")

        print()
        for nombre, query in tablas_pg:
            n = postgres_db.execute(text(query)).scalar()
            print(f"  {nombre:<25} {n:>12,}")

        # Consultas sin paciente_id en PostgreSQL
        huerfanas = postgres_db.execute(text(
            "SELECT COUNT(*) FROM consultas WHERE paciente_id IS NULL"
        )).scalar()
        print(f"\n  Consultas sin paciente_id (PG): {huerfanas:,}")

        # Distribución match_criterio
        print("\n  Distribución por criterio de match (desde ciclo JSONB):")
        criterios = postgres_db.execute(text("""
            SELECT ciclo->>'match_criterio' AS criterio, COUNT(*) AS total
            FROM consultas
            WHERE ciclo IS NOT NULL
            GROUP BY criterio
            ORDER BY total DESC
        """)).fetchall()
        for criterio, total in criterios:
            print(f"    {(criterio or 'NULL'):<25} {total:>10,}")

    finally:
        mysql_db.close()
        postgres_db.close()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  MIGRACIÓN MySQL → PostgreSQL")
    print("  Origen : pacientes_master + consultas_master")
    print("  Destino: pacientes + consultas (PostgreSQL)")
    print("=" * 60)
    print(f"\n  Batch size : {BATCH_SIZE}")
    print(f"  MySQL      : {os.getenv('MYSQL_DATABASE','?')}@{os.getenv('MYSQL_HOST','localhost')}")
    print(f"  PostgreSQL : {os.getenv('POSTGRES_DB','?')}@{os.getenv('POSTGRES_HOST','localhost')}")

    # ── Detección de mapeo guardado (reanudación) ─────────────────────────
    mapeo_guardado = cargar_mapeo()
    if mapeo_guardado:
        print(f"\n  Se encontró mapeo previo en '{MAPEO_FILE}'.")
        resp_mapeo = input("  ¿Reanudar solo el paso 2 con este mapeo? (s/n): ").strip().lower()
        if resp_mapeo == "s":
            mapeo_id, mapeo_exp = mapeo_guardado
            r2 = paso_2_migrar_consultas(mapeo_id, mapeo_exp)
            verificar()
            titulo("RESUMEN FINAL (reanudación)")
            print(f"  Consultas migradas  : {r2['ok']:>8,}")
            print(f"  Consultas sin pac.  : {r2['sin_paciente']:>8,}")
            print(f"  Consultas sin fecha : {r2['sin_fecha']:>8,}")
            print(f"  Consultas con error : {r2['error']:>8,}")
            return

    resp = input("\n¿Continuar migración completa? (s/n): ").strip().lower()
    if resp != "s":
        print("Cancelado.")
        return

    inicio = datetime.now()

    # ── Paso 0: limpiar tablas PostgreSQL ─────────────────────────────────
    limpiar_tablas_postgres()

    # ── Paso 1: pacientes ─────────────────────────────────────────────────
    r1 = paso_1_migrar_pacientes()

    # ── Paso 2: consultas ─────────────────────────────────────────────────
    r2 = paso_2_migrar_consultas(r1["mapeo_id"], r1["mapeo_exp"])

    # ── Verificación ──────────────────────────────────────────────────────
    verificar()

    # ── Resumen ───────────────────────────────────────────────────────────
    elapsed = (datetime.now() - inicio).total_seconds()
    titulo("RESUMEN FINAL")
    print(f"  Pacientes migrados  : {r1['stats']['ok']:>8,}")
    print(f"  Pacientes con error : {r1['stats']['error']:>8,}")
    print(f"  Consultas migradas  : {r2['ok']:>8,}")
    print(f"  Consultas sin pac.  : {r2['sin_paciente']:>8,}")
    print(f"  Consultas sin fecha : {r2['sin_fecha']:>8,}")
    print(f"  Consultas con error : {r2['error']:>8,}")
    print(f"  Tiempo total        : {elapsed:>8.1f}s")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)