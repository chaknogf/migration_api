#!/usr/bin/env python3
"""
migrate_uisau.py
Migración de tabla uisau: MySQL → PostgreSQL

Sigue la misma lógica que migrate_citas.py:

FASE 1 — MySQL (preparación):
    1-A: uisau → uisau_backup  (copia exacta)
    1-B: uisau_backup + pacientes_master → uisau_master
         Resuelve id_paciente en 3 niveles:
           Nivel 1: expediente directo
           Nivel 2: exp_migrado
           Nivel 3: exp_ref
         Los registros sin paciente van a uisau_sin_paciente.csv

FASE 2 — PostgreSQL (migración):
    2-A: DROP + CREATE tabla uisau (esquema normalizado)
    2-B: uisau_master → uisau usando mapeo_migracion.json
         para traducir mysql_paciente_id → pg_paciente_id

Normalización aplicada:
    - articulos  JSONB: shampoo, toalla, peine, jabon, cepillo_dientes,
                        pasta_dental, sandalias, agua, papel, panales,
                        toalla_humeda, ropa_bebe, ropa_interior, panal_bebe,
                        panal_adulto, babero, otros
    - diagnosticos JSONB: dxA, dxB, dxC, dxD, dxE
    - nombres/apellidos/contacto/expediente: saneados pero no usados en PG
      (el paciente se une por id_paciente)

⚠️  Ejecutar DESPUÉS de migrar_postgres.py (necesita mapeo_migracion.json)
"""

import os
import sys
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.types import JSON
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

BATCH_SIZE        = 500
LOG_INTERVAL      = 5_000
MAPEO_FILE        = Path("mapeo_migracion.json")
SIN_PACIENTE_FILE = Path("uisau_sin_paciente.csv")
ERROR_FILE        = Path("uisau_errores.csv")

# Campos tinyint(1) que se agrupan en JSONB articulos
CAMPOS_ARTICULOS = [
    "shampoo", "toalla", "peine", "jabon", "cepillo_dientes",
    "pasta_dental", "sandalias", "agua", "papel", "panales",
    "toalla_humeda", "ropa_bebe", "ropa_interior", "panal_bebe",
    "panal_adulto", "babero", "otros",
]

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("migracion_uisau.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ============================================================================
# ESTADÍSTICAS
# ============================================================================

@dataclass
class Stats:
    migradas:     int = 0
    errores:      int = 0
    sin_paciente: int = 0  # sin match en pacientes_master (MySQL)
    sin_mapeo:    int = 0  # id_paciente MySQL sin entrada en mapeo PG
    inicio: datetime = field(default_factory=datetime.now)

    def resumen(self) -> str:
        elapsed = (datetime.now() - self.inicio).total_seconds()
        rate    = self.migradas / elapsed if elapsed else 0
        return (
            f"\n{'='*60}\n"
            f"  ✅  Migradas        : {self.migradas:>10,}\n"
            f"  👻  Sin paciente    : {self.sin_paciente:>10,}\n"
            f"  🗺   Sin mapeo PG   : {self.sin_mapeo:>10,}\n"
            f"  ❌  Errores        : {self.errores:>10,}\n"
            f"  ⏱   Tiempo         : {elapsed:>10.1f} s\n"
            f"  🚀  Velocidad      : {rate:>10.0f} filas/s\n"
            f"{'='*60}"
        )

# ============================================================================
# CONEXIONES
# ============================================================================

def _url_mysql() -> str:
    return (
        f"mysql+pymysql://"
        f"{os.getenv('MYSQL_USER', 'root')}:"
        f"{os.getenv('MYSQL_PASSWORD', '')}@"
        f"{os.getenv('MYSQL_HOST', 'localhost')}:"
        f"{os.getenv('MYSQL_PORT', '3306')}/"
        f"{os.getenv('MYSQL_DATABASE', 'test_api')}"
    )

def _url_postgres() -> str:
    return (
        f"postgresql://"
        f"{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', '')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'hospital')}"
    )

def crear_motores():
    mysql_eng = create_engine(_url_mysql(),    echo=False, pool_pre_ping=True)
    pg_eng    = create_engine(_url_postgres(), echo=False, pool_pre_ping=True,
                              pool_size=2, max_overflow=2)
    return mysql_eng, pg_eng

# ============================================================================
# MAPEO DE PACIENTES  mysql_id → pg_id
# ============================================================================

def cargar_mapeo_pacientes() -> dict[int, int]:
    if not MAPEO_FILE.exists():
        raise FileNotFoundError(
            f"No se encontró {MAPEO_FILE}. "
            "Ejecuta primero migrar_postgres.py para generar el mapeo de pacientes."
        )
    with open(MAPEO_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    mapeo = {int(k): v for k, v in payload["mapeo_id"].items()}
    log.info("🗺   Mapeo cargado: %d pacientes (mysql_id → pg_id)", len(mapeo))
    return mapeo

# ============================================================================
# CSV WRITER
# ============================================================================

class CsvWriter:
    def __init__(self, path: Path, fieldnames: list[str]):
        self.path       = path
        self.fieldnames = fieldnames
        self._file      = None
        self._writer    = None

    def write(self, row: dict) -> None:
        if self._file is None:
            self._file   = open(self.path, "w", newline="", encoding="utf-8")
            self._writer = csv.DictWriter(
                self._file, fieldnames=self.fieldnames, extrasaction="ignore"
            )
            self._writer.writeheader()
        self._writer.writerow(
            {k: str(v) if v is not None else "" for k, v in row.items()}
        )

    def close(self) -> None:
        if self._file:
            self._file.close()

# ============================================================================
# FASE 1-A — BACKUP uisau en MySQL
# ============================================================================

def mysql_backup(mysql_eng):
    log.info("─" * 60)
    log.info("💾  FASE 1-A: uisau → uisau_backup")

    with mysql_eng.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS uisau_backup"))
        conn.execute(text("CREATE TABLE uisau_backup AS SELECT * FROM uisau"))
        conn.commit()
        total = conn.execute(text("SELECT COUNT(*) FROM uisau_backup")).scalar()

    log.info("   ✅ Backup creado: %d registros", total)

# ============================================================================
# FASE 1-B — Crear uisau_master en MySQL con id_paciente resuelto
# ============================================================================

SQL_CREAR_MASTER = """
DROP TABLE IF EXISTS uisau_master;

CREATE TABLE uisau_master LIKE uisau;
ALTER TABLE uisau_master
    ADD COLUMN id_paciente INT     NULL COMMENT 'FK resuelta a pacientes_master.id',
    ADD COLUMN nivel_match TINYINT NULL DEFAULT 0
        COMMENT '1=expediente directo, 2=exp_migrado, 3=exp_ref';

-- NIVEL 1: expediente directo
INSERT INTO uisau_master
SELECT u.*, p.id AS id_paciente, 1 AS nivel_match
FROM uisau_backup u
INNER JOIN pacientes_master p
    ON u.expediente IS NOT NULL
    AND u.expediente = p.expediente;

-- NIVEL 2: exp_migrado (expediente en la lista CSV de exp_migrado)
INSERT INTO uisau_master
SELECT u.*, p.id AS id_paciente, 2 AS nivel_match
FROM uisau_backup u
INNER JOIN pacientes_master p
    ON u.expediente IS NOT NULL
    AND p.exp_migrado IS NOT NULL
    AND p.exp_migrado != ''
    AND FIND_IN_SET(
        CONVERT(CAST(u.expediente AS CHAR) USING utf8mb4) COLLATE utf8mb4_unicode_ci,
        CONVERT(p.exp_migrado USING utf8mb4) COLLATE utf8mb4_unicode_ci
    ) > 0
LEFT JOIN uisau_master um ON u.id = um.id
WHERE um.id IS NULL;

-- NIVEL 3: exp_ref
INSERT INTO uisau_master
SELECT u.*, p.id AS id_paciente, 3 AS nivel_match
FROM uisau_backup u
INNER JOIN pacientes_master p
    ON u.expediente IS NOT NULL
    AND p.exp_ref IS NOT NULL
    AND u.expediente = p.exp_ref
LEFT JOIN uisau_master um ON u.id = um.id
WHERE um.id IS NULL;

ALTER TABLE uisau_master ADD INDEX idx_id         (id);
ALTER TABLE uisau_master ADD INDEX idx_id_pac     (id_paciente);
ALTER TABLE uisau_master ADD INDEX idx_expediente (expediente);
"""

SQL_SIN_PACIENTE = """
SELECT u.id AS mysql_id, u.expediente, u.nombres, u.apellidos, u.fecha
FROM uisau_backup u
LEFT JOIN uisau_master um ON u.id = um.id
WHERE um.id IS NULL
ORDER BY u.id;
"""

SQL_RESUMEN_NIVELES = """
SELECT nivel_match, COUNT(*) AS total
FROM uisau_master
GROUP BY nivel_match
ORDER BY nivel_match;
"""


def mysql_crear_master(mysql_eng, stats: Stats, sin_pac_writer: CsvWriter) -> int:
    log.info("─" * 60)
    log.info("🔧  FASE 1-B: Creando uisau_master en MySQL...")

    with mysql_eng.connect() as conn:
        for stmt in [s.strip() for s in SQL_CREAR_MASTER.split(";") if s.strip()]:
            conn.execute(text(stmt))
        conn.commit()

    with mysql_eng.connect() as conn:
        total = 0
        for row in conn.execute(text(SQL_RESUMEN_NIVELES)):
            label = {1: "expediente directo", 2: "exp_migrado", 3: "exp_ref"}.get(row[0], "?")
            log.info("   Nivel %d (%s): %d registros", row[0], label, row[1])
            total += row[1]
        log.info("   Total en uisau_master: %d", total)

    with mysql_eng.connect() as conn:
        for row in conn.execute(text(SQL_SIN_PACIENTE)):
            stats.sin_paciente += 1
            sin_pac_writer.write({
                "mysql_id":   row[0],
                "expediente": row[1],
                "nombres":    row[2],
                "apellidos":  row[3],
                "fecha":      row[4],
            })

    if stats.sin_paciente:
        log.warning("   ⚠️  %d registros sin paciente → %s",
                    stats.sin_paciente, SIN_PACIENTE_FILE)
    else:
        log.info("   ✅  Todos los registros fueron vinculados a un paciente.")

    log.info("─" * 60)
    return total

# ============================================================================
# FASE 2-A — DROP + CREATE tabla uisau en PostgreSQL
# ============================================================================

DDL_UISAU_PG = """
DROP TABLE IF EXISTS uisau CASCADE;

CREATE TABLE uisau (
    id               SERIAL      PRIMARY KEY,

    -- Vínculo normalizado al paciente
    id_paciente      INT         REFERENCES pacientes(id) ON DELETE SET NULL,

    -- Datos de la visita
    fecha            DATE,
    hora             TIME,
    estado           INT,
    situacion        INT,
    lugar_referencia INT,
    fecha_referencia DATE,
    estadia          INT,
    cama             INT,
    especialidad     INT,
    servicio         INT,

    -- Información clínica
    informacion      VARCHAR(2),
    nota             TEXT,
    estudios         VARCHAR(255),
    evolucion        TEXT,
    receta           VARCHAR(100),
    receta_por       VARCHAR(2),

    -- Diagnósticos agrupados
    diagnosticos     JSONB,

    -- Artículos entregados agrupados
    articulos        JSONB,

    -- Contacto de emergencia
    contacto         VARCHAR(255),
    parentesco       INT,
    telefono         BIGINT,
    fecha_contacto   DATE,
    hora_contacto    TIME,

    -- Relaciones
    id_consulta      INT,
    consulta_id      INT,

    -- Metadatos
    created_by       VARCHAR(8),
    update_by        VARCHAR(8),
    created_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_uisau_paciente    ON uisau (id_paciente);
CREATE INDEX idx_uisau_fecha       ON uisau (fecha);
CREATE INDEX idx_uisau_servicio    ON uisau (servicio);
CREATE INDEX idx_uisau_especialidad ON uisau (especialidad);
"""


def pg_crear_tabla(pg_eng):
    log.info("─" * 60)
    log.info("🏗   FASE 2-A: Recreando tabla uisau en PostgreSQL...")

    with pg_eng.connect() as conn:
        for stmt in [s.strip() for s in DDL_UISAU_PG.split(";") if s.strip()]:
            conn.execute(text(stmt))
        conn.commit()

    log.info("   ✅ Tabla uisau creada en PostgreSQL")
    log.info("─" * 60)

# ============================================================================
# TRANSFORMACIÓN
# ============================================================================

def _construir_articulos(raw: dict) -> Optional[dict]:
    """Agrupa los campos tinyint en un dict para JSONB. Siempre retorna dict o None."""
    articulos = {}
    for campo in CAMPOS_ARTICULOS:
        val = raw.get(campo)
        if val is not None:
            try:
                if int(val) == 1:
                    articulos[campo] = True
            except (TypeError, ValueError):
                pass
    # Siempre retorna un dict aunque esté vacío, o None si no hay artículos
    # Es mejor retornar None para que el campo sea NULL en la BD
    return articulos if articulos else None


def _construir_diagnosticos(raw: dict) -> Optional[dict]:
    """Agrupa dxA…dxE en un dict para JSONB. Solo incluye los no vacíos."""
    dx = {}
    for campo in ["dxA", "dxB", "dxC", "dxD", "dxE"]:
        val = raw.get(campo)
        if val and str(val).strip():
            dx[campo] = str(val).strip()
    return dx if dx else None


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _timedelta_to_time(val) -> Optional[str]:
    """
    MySQL devuelve TIME como timedelta. PostgreSQL espera 'HH:MM:SS'.
    Convierte timedelta → string 'HH:MM:SS', o pasa None si es None.
    """
    if val is None:
        return None
    if hasattr(val, 'seconds'):  # es timedelta
        total = int(val.total_seconds())
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    return str(val)  # ya es time o string


def transformar_uisau(raw: dict, mapeo_pacientes: dict[int, int]) -> Optional[dict]:
    """
    Transforma un registro de uisau_master al formato PostgreSQL.
    Retorna None si no tiene mapeo PG (se cuenta como sin_mapeo).
    """
    now = datetime.now()

    mysql_paciente_id = raw.get("id_paciente")
    pg_paciente_id    = mapeo_pacientes.get(mysql_paciente_id) if mysql_paciente_id else None

    if pg_paciente_id is None:
        return None  # sin_mapeo

    # telefono: en MySQL es INT, puede desbordarse → usar BIGINT en PG
    tel = _safe_int(raw.get("telefono"))
    
    # Construir articulos y diagnosticos
    articulos = _construir_articulos(raw)
    diagnosticos = _construir_diagnosticos(raw)

    return {
        "id_paciente":      pg_paciente_id,
        "fecha":            raw.get("fecha"),
        "hora":             _timedelta_to_time(raw.get("hora")),
        "estado":           _safe_int(raw.get("estado")),
        "situacion":        _safe_int(raw.get("situacion")),
        "lugar_referencia": _safe_int(raw.get("lugar_referencia")),
        "fecha_referencia": raw.get("fecha_referencia"),
        "estadia":          _safe_int(raw.get("estadia")),
        "cama":             _safe_int(raw.get("cama")),
        "especialidad":     _safe_int(raw.get("especialidad")),
        "servicio":         _safe_int(raw.get("servicio")),
        "informacion":      raw.get("informacion"),
        "nota":             raw.get("nota"),
        "estudios":         raw.get("estudios"),
        "evolucion":        raw.get("evolucion"),
        "receta":           raw.get("receta"),
        "receta_por":       raw.get("receta_por"),
        "diagnosticos":     diagnosticos,  # None o dict
        "articulos":        articulos,     # None o dict
        "contacto":         raw.get("contacto"),
        "parentesco":       _safe_int(raw.get("parentesco")),
        "telefono":         tel,
        "fecha_contacto":   raw.get("fecha_contacto"),
        "hora_contacto":    _timedelta_to_time(raw.get("hora_contacto")),
        "id_consulta":      _safe_int(raw.get("id_consulta")),
        "consulta_id":      _safe_int(raw.get("consulta_id")),
        "created_by":       str(raw.get("created_by") or "")[:8] or None,
        "update_by":        str(raw.get("update_by") or "")[:8] or None,
        "created_at":       raw.get("created_at") or now,
        "updated_at":       raw.get("updated_at") or now,
    }
    
# ============================================================================
# INSERT PostgreSQL
# ============================================================================

INSERT_UISAU = text("""
    INSERT INTO uisau (
        id_paciente, fecha, hora, estado, situacion,
        lugar_referencia, fecha_referencia, estadia, cama,
        especialidad, servicio, informacion, nota, estudios,
        evolucion, receta, receta_por,
        diagnosticos, articulos,
        contacto, parentesco, telefono, fecha_contacto, hora_contacto,
        id_consulta, consulta_id,
        created_by, update_by, created_at, updated_at
    ) VALUES (
        :id_paciente, :fecha, :hora, :estado, :situacion,
        :lugar_referencia, :fecha_referencia, :estadia, :cama,
        :especialidad, :servicio, :informacion, :nota, :estudios,
        :evolucion, :receta, :receta_por,
        :diagnosticos, :articulos,
        :contacto, :parentesco, :telefono, :fecha_contacto, :hora_contacto,
        :id_consulta, :consulta_id,
        :created_by, :update_by, :created_at, :updated_at
    )
""").bindparams(
    bindparam("diagnosticos", type_=JSON),
    bindparam("articulos",    type_=JSON),
)


def insertar_lote(pg_conn, lote: list[dict], stats: Stats,
                  err_writer: CsvWriter) -> None:
    try:
        pg_conn.execute(INSERT_UISAU, lote)
        pg_conn.commit()
        stats.migradas += len(lote)
    except Exception as bulk_err:
        pg_conn.rollback()
        log.warning("⚠️  Fallo en lote (%d filas) — reintentando uno a uno: %s",
                    len(lote), bulk_err)
        for fila in lote:
            try:
                pg_conn.execute(INSERT_UISAU, fila)
                pg_conn.commit()
                stats.migradas += 1
            except Exception as row_err:
                pg_conn.rollback()
                stats.errores += 1
                err_writer.write({**fila, "error": str(row_err)})

# ============================================================================
# FASE 2-B — Migrar uisau_master → PostgreSQL
# ============================================================================

def pg_migrar(mysql_eng, pg_eng, mapeo_pacientes: dict[int, int],
              stats: Stats, err_writer: CsvWriter) -> None:
    log.info("─" * 60)
    log.info("🚀  FASE 2-B: Migrando uisau_master → PostgreSQL...")

    with mysql_eng.connect() as mysql_conn, pg_eng.connect() as pg_conn:
        mysql_conn = mysql_conn.execution_options(stream_results=True)

        total = mysql_conn.execute(
            text("SELECT COUNT(*) FROM uisau_master")
        ).scalar()
        log.info("   Registros en uisau_master: %d", total)

        resultado = mysql_conn.execute(
            text("SELECT * FROM uisau_master ORDER BY id")
        )

        lote:  list[dict] = []
        count: int        = 0

        for row in resultado:
            raw = dict(row._mapping)
            count += 1

            transformado = transformar_uisau(raw, mapeo_pacientes)

            if transformado is None:
                stats.sin_mapeo += 1
                if stats.sin_mapeo <= 5:
                    log.warning(
                        "   ⚠️  Sin mapeo PG: uisau_id=%s  mysql_pac=%s  expediente=%s",
                        raw.get("id"), raw.get("id_paciente"), raw.get("expediente"),
                    )
                continue

            lote.append(transformado)

            if len(lote) >= BATCH_SIZE:
                insertar_lote(pg_conn, lote, stats, err_writer)
                lote = []
                if stats.migradas % LOG_INTERVAL == 0:
                    log.info("   → %d migradas | %d errores | %d sin mapeo",
                             stats.migradas, stats.errores, stats.sin_mapeo)

        if lote:
            insertar_lote(pg_conn, lote, stats, err_writer)

    log.info("─" * 60)

# ============================================================================
# VERIFICACIÓN FINAL
# ============================================================================

def verificar(mysql_eng, pg_eng):
    log.info("─" * 60)
    log.info("🔍  VERIFICACIÓN FINAL")

    with mysql_eng.connect() as mc, pg_eng.connect() as pc:
        orig   = mc.execute(text("SELECT COUNT(*) FROM uisau_backup")).scalar()
        master = mc.execute(text("SELECT COUNT(*) FROM uisau_master")).scalar()
        pg_tot = pc.execute(text("SELECT COUNT(*) FROM uisau")).scalar()

        log.info("   MySQL  uisau_backup  : %8d  (original)", orig)
        log.info("   MySQL  uisau_master  : %8d  (con id_paciente)", master)
        log.info("   PG     uisau         : %8d", pg_tot)

        sin_pac = pc.execute(text(
            "SELECT COUNT(*) FROM uisau WHERE id_paciente IS NULL"
        )).scalar()
        log.info("   Sin id_paciente (PG) : %8d", sin_pac)

        log.info("\n   Top 5 especialidades:")
        top = pc.execute(text("""
            SELECT especialidad, COUNT(*) AS n
            FROM uisau GROUP BY especialidad
            ORDER BY n DESC LIMIT 5
        """)).fetchall()
        for esp, n in top:
            log.info("   → especialidad %-4s  %d registros", esp or "NULL", n)

        log.info("\n   Artículos más frecuentes:")
        # Consulta corregida: solo procesar JSONB de tipo 'object'
        try:
            arts = pc.execute(text("""
                SELECT key, COUNT(*) AS n
                FROM uisau, jsonb_each(articulos)
                WHERE articulos IS NOT NULL 
                  AND jsonb_typeof(articulos) = 'object'
                GROUP BY key ORDER BY n DESC LIMIT 10
            """)).fetchall()
            for art, n in arts:
                log.info("   → %-20s %d", art, n)
        except Exception as e:
            log.warning("   No se pudo analizar artículos: %s", e)
            # Consulta alternativa: contar registros con artículos no nulos
            arts_count = pc.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN jsonb_typeof(articulos) = 'object' THEN 1 END) as objetos,
                    COUNT(CASE WHEN jsonb_typeof(articulos) = 'string' THEN 1 END) as strings,
                    COUNT(CASE WHEN jsonb_typeof(articulos) = 'number' THEN 1 END) as numeros
                FROM uisau 
                WHERE articulos IS NOT NULL
            """)).fetchone()
            log.info("   Artículos no nulos: total=%d, objetos=%d, strings=%d, numeros=%d", 
                     arts_count[0], arts_count[1], arts_count[2], arts_count[3])

        log.info("\n   Diagnósticos (dxA presentes): %d",
            pc.execute(text(
                "SELECT COUNT(*) FROM uisau WHERE diagnosticos ? 'dxA'"
            )).scalar()
        )
        
        # Verificar tipos de datos en articulos
        log.info("\n   Verificación de tipos JSONB en articulos:")
        tipos = pc.execute(text("""
            SELECT 
                jsonb_typeof(articulos) as tipo,
                COUNT(*) as cantidad
            FROM uisau 
            WHERE articulos IS NOT NULL
            GROUP BY jsonb_typeof(articulos)
        """)).fetchall()
        for tipo, cant in tipos:
            log.info("   → Tipo: %-10s  %d registros", tipo or 'null', cant)

    log.info("─" * 60)
    
# ============================================================================
# MAIN
# ============================================================================

def main():
    log.info("=" * 60)
    log.info("🏥  MIGRACIÓN uisau  MySQL → PostgreSQL")
    log.info("=" * 60)

    # Cargar mapeo ANTES de conectar — falla rápido si no existe
    mapeo_pacientes = cargar_mapeo_pacientes()

    stats         = Stats()
    mysql_eng, pg_eng = crear_motores()

    sin_pac_writer = CsvWriter(
        SIN_PACIENTE_FILE,
        ["mysql_id", "expediente", "nombres", "apellidos", "fecha"],
    )
    error_writer = CsvWriter(
        ERROR_FILE,
        ["id_paciente", "fecha", "especialidad", "servicio", "created_at", "error"],
    )

    try:
        # ── Fase 1: MySQL ────────────────────────────────────────────────
        mysql_backup(mysql_eng)
        mysql_crear_master(mysql_eng, stats, sin_pac_writer)

        # ── Fase 2: PostgreSQL ───────────────────────────────────────────
        pg_crear_tabla(pg_eng)
        pg_migrar(mysql_eng, pg_eng, mapeo_pacientes, stats, error_writer)

        # ── Verificación ─────────────────────────────────────────────────
        verificar(mysql_eng, pg_eng)

    finally:
        sin_pac_writer.close()
        error_writer.close()
        mysql_eng.dispose()
        pg_eng.dispose()

    log.info(stats.resumen())

    log.info("Tablas MySQL de referencia disponibles:")
    log.info("  • uisau_backup   (datos originales)")
    log.info("  • uisau_master   (normalizada con id_paciente)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("❌ Cancelado por el usuario")
        sys.exit(1)
    except Exception as e:
        log.exception("❌ Error fatal: %s", e)
        sys.exit(1)