#!/usr/bin/env python3
"""
MIGRACIÓN DE TABLA CITAS
MySQL → PostgreSQL

FASE 1 — Preparación en MySQL:
    Crea `citas_master` copiando `citas` + columna `id_paciente` resuelta
    en cascada desde `pacientes_master`.

FASE 2 — Migración MySQL → PostgreSQL:
    Lee citas_master, traduce id_paciente de MySQL → PG usando
    mapeo_migracion.json generado por migrar_postgres.py, e inserta en PG.

Columnas origen (MySQL citas_master):
    id, fecha, expediente, especialidad (int), fecha_cita,
    nota, tipo, lab, fecha_lab, created_at, updated_at, created_by,
    id_paciente  ← añadida en Fase 1

Columnas destino (PostgreSQL citas):
    id (identity), fecha_registro, paciente_id, especialidad (VARCHAR 6),
    fecha_cita, expediente (VARCHAR 20), datos_extra (JSONB),
    created_at, updated_at, created_by

Mapeo de fechas:
    fecha      (MySQL) → fecha_cita      (PG) — cuándo está agendada la cita
    fecha_cita (MySQL) → fecha_registro  (PG) — cuándo se creó el registro
"""

import os
import sys
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

BATCH_SIZE        = 500
LOG_INTERVAL      = 5_000
CHECKPOINT_FILE   = Path("checkpoint_citas.txt")
ERROR_FILE        = Path("citas_errores.csv")
SIN_PACIENTE_FILE = Path("citas_sin_paciente.csv")
MAPEO_FILE        = Path("mapeo_migracion.json")

ESPECIALIDADES_MAP: dict[int, str] = {
    1: "MEDI",   # Medicina Interna
    2: "PEDI",   # Pediatría
    3: "GINE",   # Ginecología
    4: "CIRU",   # Cirugía
    5: "TRAU",   # Traumatología
    6: "PSIC",   # Psicología
    7: "NUTR",   # Nutrición
    8: "ODON",   # Odontología
}

RAZON_CONSULTA_MAP: dict[int, str] = {
    0: "control",
    1: "control",
    2: "ingreso",
    3: "procedimiento",
    4: "procedimiento",
    5: "procedimiento",
    9: "preoperatorio",
}

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("migracion_citas.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ============================================================================
# ESTADÍSTICAS
# ============================================================================

@dataclass
class Stats:
    migradas:       int = 0
    errores:        int = 0
    sin_paciente:   int = 0
    sin_mapeo:      int = 0   # id_paciente MySQL sin entrada en mapeo_migracion.json
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
    mysql_engine = create_engine(_url_mysql(),    echo=False, pool_pre_ping=True)
    pg_engine    = create_engine(_url_postgres(), echo=False, pool_pre_ping=True,
                                 pool_size=2, max_overflow=2)
    return mysql_engine, pg_engine

# ============================================================================
# MAPEO DE PACIENTES  mysql_id → pg_id
# ============================================================================

def cargar_mapeo_pacientes() -> dict[int, int]:
    """
    Carga mapeo_migracion.json generado por migrar_postgres.py.
    Retorna {mysql_id: pg_id} para traducir id_paciente antes de insertar.
    Sin este mapeo las citas quedarían con el ID de MySQL en paciente_id,
    apuntando al paciente equivocado en PostgreSQL.
    """
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
# CHECKPOINT
# ============================================================================

def leer_checkpoint() -> int:
    if CHECKPOINT_FILE.exists():
        try:
            return int(CHECKPOINT_FILE.read_text().strip())
        except ValueError:
            pass
    return 0

def guardar_checkpoint(ultimo_id: int) -> None:
    CHECKPOINT_FILE.write_text(str(ultimo_id))

def borrar_checkpoint() -> None:
    CHECKPOINT_FILE.unlink(missing_ok=True)

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
# FASE 1 — PREPARACIÓN MySQL: crear citas_master
# ============================================================================

SQL_CREAR_CITAS_MASTER = """
DROP TABLE IF EXISTS citas_master;

CREATE TABLE citas_master LIKE citas;
ALTER TABLE citas_master
    ADD COLUMN id_paciente INT NOT NULL COMMENT 'FK resuelta a pacientes_master.id',
    ADD COLUMN nivel_match TINYINT NOT NULL DEFAULT 0
        COMMENT '1=expediente directo, 2=exp_migrado, 3=exp_ref';

-- NIVEL 1: expediente directo
INSERT INTO citas_master
SELECT
    c.*,
    p.id   AS id_paciente,
    1      AS nivel_match
FROM citas c
INNER JOIN pacientes_master p
    ON c.expediente IS NOT NULL
    AND c.expediente = p.expediente
WHERE c.especialidad IS NOT NULL
  AND c.especialidad != 0;

-- NIVEL 2: exp_migrado
INSERT INTO citas_master
SELECT
    c.*,
    p.id AS id_paciente,
    2    AS nivel_match
FROM citas c
INNER JOIN pacientes_master p
    ON c.expediente IS NOT NULL
    AND p.exp_migrado IS NOT NULL
    AND p.exp_migrado != ''
    AND FIND_IN_SET(CONVERT(CAST(c.expediente AS CHAR) USING utf8mb4) COLLATE utf8mb4_unicode_ci,
                   CONVERT(p.exp_migrado USING utf8mb4) COLLATE utf8mb4_unicode_ci) > 0
LEFT JOIN citas_master cm ON c.id = cm.id
WHERE cm.id IS NULL
  AND c.especialidad IS NOT NULL
  AND c.especialidad != 0;

-- NIVEL 3: exp_ref
INSERT INTO citas_master
SELECT
    c.*,
    p.id AS id_paciente,
    3    AS nivel_match
FROM citas c
INNER JOIN pacientes_master p
    ON c.expediente IS NOT NULL
    AND p.exp_ref IS NOT NULL
    AND c.expediente = p.exp_ref
LEFT JOIN citas_master cm ON c.id = cm.id
WHERE cm.id IS NULL
  AND c.especialidad IS NOT NULL
  AND c.especialidad != 0;

ALTER TABLE citas_master ADD INDEX idx_id (id);
"""

SQL_SIN_PACIENTE = """
SELECT
    c.id          AS mysql_id,
    c.expediente,
    c.especialidad,
    c.fecha
FROM citas c
LEFT JOIN citas_master cm ON c.id = cm.id
WHERE cm.id IS NULL
ORDER BY c.id;
"""

SQL_RESUMEN_NIVELES = """
SELECT nivel_match, COUNT(*) AS total
FROM citas_master
GROUP BY nivel_match
ORDER BY nivel_match;
"""


def preparar_citas_master(mysql_eng, stats: Stats, sin_pac_writer: CsvWriter) -> int:
    log.info("─" * 60)
    log.info("🔧  FASE 1 — Preparando citas_master en MySQL...")

    with mysql_eng.connect() as ddl_conn:
        for stmt in [s.strip() for s in SQL_CREAR_CITAS_MASTER.split(";") if s.strip()]:
            ddl_conn.execute(text(stmt))
        ddl_conn.commit()

    with mysql_eng.connect() as audit_conn:
        total = 0
        for r in audit_conn.execute(text(SQL_RESUMEN_NIVELES)):
            label = {1: "expediente directo", 2: "exp_migrado", 3: "exp_ref"}.get(r[0], "?")
            log.info("   Nivel %d (%s): %d citas", r[0], label, r[1])
            total += r[1]
        log.info("   Total en citas_master: %d", total)

    with mysql_eng.connect() as audit_conn:
        for r in audit_conn.execute(text(SQL_SIN_PACIENTE)):
            stats.sin_paciente += 1
            sin_pac_writer.write({
                "mysql_id":     r[0],
                "expediente":   r[1],
                "especialidad": r[2],
                "fecha":        r[3],
            })

    if stats.sin_paciente:
        log.warning("   ⚠️  %d citas sin paciente → %s", stats.sin_paciente, SIN_PACIENTE_FILE)
    else:
        log.info("   ✅  Todas las citas con especialidad fueron vinculadas.")

    log.info("─" * 60)
    return total

# ============================================================================
# FASE 2 — TRANSFORMACIÓN
# ============================================================================

def _safe_date(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    return val


def _construir_datos_extra(raw: dict) -> str | None:
    extras: dict = {}

    if raw.get("nota"):
        extras["nota"] = raw["nota"]

    tipo = raw.get("tipo")
    if tipo is not None:
        razon = RAZON_CONSULTA_MAP.get(int(tipo))
        if razon:
            extras["razon_consulta"] = razon
        else:
            extras["tipo_original"] = int(tipo)

    if raw.get("lab") is not None:
        extras["lab"] = int(raw["lab"])

    if raw.get("fecha_lab"):
        fl = _safe_date(raw["fecha_lab"])
        extras["fecha_lab"] = fl.isoformat() if fl else None

    return json.dumps(extras, default=str) if extras else None


def transformar_cita(raw: dict, mapeo_pacientes: dict[int, int]) -> dict | None:
    """
    Mapeo de fechas:
        fecha      (MySQL) → fecha_cita      (PG) — cuándo está agendada la cita
        fecha_cita (MySQL) → fecha_registro  (PG) — cuándo se creó el registro

    Mapeo de IDs:
        id_paciente (MySQL) → traducido a pg_id via mapeo_migracion.json
        Si no existe en el mapeo, retorna None (la cita se omite y se cuenta).
    """
    now = datetime.now()

    # Traducir id_paciente de MySQL → PostgreSQL
    mysql_paciente_id = raw["id_paciente"]
    pg_paciente_id    = mapeo_pacientes.get(mysql_paciente_id)
    if pg_paciente_id is None:
        return None  # señal para contar como sin_mapeo y omitir

    esp_raw      = raw.get("especialidad")
    especialidad = ESPECIALIDADES_MAP.get(int(esp_raw)) if esp_raw is not None else None

    return {
        "fecha_registro": _safe_date(raw.get("fecha_cita")),  # creación del registro
        "paciente_id":    pg_paciente_id,                      # ID correcto en PostgreSQL ← FIX
        "especialidad":   especialidad,
        "fecha_cita":     _safe_date(raw.get("fecha")),        # fecha agendada de la cita
        "expediente":     str(raw["expediente"]).strip() if raw.get("expediente") is not None else None,
        "datos_extra":    _construir_datos_extra(raw),
        "created_at":     raw.get("created_at") or now,
        "updated_at":     raw.get("updated_at") or now,
        "created_by":     raw.get("created_by"),
    }

# ============================================================================
# INSERT PostgreSQL
# ============================================================================

INSERT_CITA = text("""
    INSERT INTO citas (
        fecha_registro, paciente_id, especialidad,
        fecha_cita, expediente,
        datos_extra, created_at, updated_at, created_by
    ) VALUES (
        :fecha_registro, :paciente_id, :especialidad,
        :fecha_cita, :expediente,
        NULLIF(:datos_extra, 'null')::jsonb, :created_at, :updated_at, :created_by
    )
""")


def insertar_lote(pg_conn, lote: list[dict], stats: Stats, err_writer: CsvWriter) -> None:
    try:
        pg_conn.execute(INSERT_CITA, lote)
        pg_conn.commit()
    except Exception as bulk_err:
        pg_conn.rollback()
        log.warning("⚠️  Fallo en lote (%d filas) — reintentando uno a uno: %s",
                    len(lote), bulk_err)
        for fila in lote:
            try:
                pg_conn.execute(INSERT_CITA, fila)
                pg_conn.commit()
            except Exception as row_err:
                pg_conn.rollback()
                stats.migradas -= 1
                stats.errores  += 1
                err_writer.write({**fila, "error": str(row_err)})

# ============================================================================
# LIMPIEZA PREVIA PostgreSQL
# ============================================================================

def limpiar_tabla_citas(pg_conn) -> None:
    log.info("🗑   Vaciando tabla citas y reiniciando secuencia...")
    pg_conn.execute(text("TRUNCATE TABLE citas RESTART IDENTITY CASCADE"))
    pg_conn.commit()
    log.info("   Tabla citas lista (0 filas, id reiniciado a 1)")

# ============================================================================
# DIAGNÓSTICO
# ============================================================================

def diagnosticar(mysql_conn, mapeo_pacientes: dict[int, int]) -> None:
    log.info("─" * 60)
    log.info("🔬  DIAGNÓSTICO — muestra citas_master (con traducción de IDs)")
    sample = mysql_conn.execute(text(
        "SELECT id, expediente, id_paciente, nivel_match, especialidad, tipo, "
        "fecha, fecha_cita FROM citas_master LIMIT 5"
    ))
    for r in sample:
        esp         = ESPECIALIDADES_MAP.get(r[4]) if r[4] is not None else None
        razon       = RAZON_CONSULTA_MAP.get(r[5]) if r[5] is not None else None
        nivel_label = {1: "directo", 2: "exp_migrado", 3: "exp_ref"}.get(r[3], "?")
        pg_id       = mapeo_pacientes.get(r[2], "⚠️ SIN MAPEO")
        log.info(
            "   id=%-6s  exp=%-8s  mysql_pac=%-6s  pg_pac=%-6s  nivel=%s(%s)  esp=%s  razon=%s  fecha=%s  fecha_cita=%s",
            r[0], r[1], r[2], pg_id, r[3], nivel_label, esp, razon, r[6], r[7],
        )
    log.info("─" * 60)

# ============================================================================
# MIGRACIÓN PRINCIPAL
# ============================================================================

def migrar_citas(reanudar: bool = False) -> Stats:
    log.info("=" * 60)
    log.info("📅  MIGRACIÓN DE CITAS  MySQL → PostgreSQL")
    log.info("=" * 60)

    # Cargar mapeo ANTES de conectar a las BDs — falla rápido si no existe
    mapeo_pacientes = cargar_mapeo_pacientes()

    stats         = Stats()
    mysql_eng, pg_eng = crear_motores()

    sin_pac_writer = CsvWriter(
        SIN_PACIENTE_FILE,
        ["mysql_id", "expediente", "especialidad", "fecha"],
    )
    error_writer = CsvWriter(
        ERROR_FILE,
        ["fecha_registro", "paciente_id", "especialidad", "fecha_cita",
         "expediente", "datos_extra", "created_at", "updated_at", "created_by", "error"],
    )

    ultimo_id_ok = leer_checkpoint() if reanudar else 0
    if ultimo_id_ok:
        log.info("♻️   Reanudando desde id > %d", ultimo_id_ok)

    try:
        with mysql_eng.connect() as mysql_conn, pg_eng.connect() as pg_conn:

            mysql_conn = mysql_conn.execution_options(stream_results=True)

            if not reanudar:
                preparar_citas_master(mysql_eng, stats, sin_pac_writer)
                limpiar_tabla_citas(pg_conn)

            total = mysql_conn.execute(
                text("SELECT COUNT(*) FROM citas_master WHERE id > :u"),
                {"u": ultimo_id_ok},
            ).scalar()
            log.info("📊  Citas en citas_master a procesar: %d", total)

            diagnosticar(mysql_conn, mapeo_pacientes)

            resultado = mysql_conn.execute(
                text("SELECT * FROM citas_master WHERE id > :u ORDER BY id"),
                {"u": ultimo_id_ok},
            )

            lote:      list[dict] = []
            ultimo_id: int        = ultimo_id_ok

            for row in resultado:
                raw = dict(row._mapping)

                transformada = transformar_cita(raw, mapeo_pacientes)
                if transformada is None:
                    # id_paciente de MySQL no tiene entrada en el mapeo de PG
                    stats.sin_mapeo += 1
                    if stats.sin_mapeo <= 5:
                        log.warning(
                            "   ⚠️  Sin mapeo PG: cita_id=%s  mysql_paciente_id=%s  expediente=%s",
                            raw["id"], raw["id_paciente"], raw.get("expediente"),
                        )
                    ultimo_id = raw["id"]
                    continue

                lote.append(transformada)
                stats.migradas += 1
                ultimo_id = raw["id"]

                if len(lote) >= BATCH_SIZE:
                    insertar_lote(pg_conn, lote, stats, error_writer)
                    guardar_checkpoint(ultimo_id)
                    lote = []
                    if stats.migradas % LOG_INTERVAL == 0:
                        log.info("   → %d migradas | %d errores | %d sin mapeo",
                                 stats.migradas, stats.errores, stats.sin_mapeo)

            if lote:
                insertar_lote(pg_conn, lote, stats, error_writer)
                guardar_checkpoint(ultimo_id)

    finally:
        sin_pac_writer.close()
        error_writer.close()
        mysql_eng.dispose()
        pg_eng.dispose()

    if stats.errores == 0:
        borrar_checkpoint()

    log.info(stats.resumen())
    return stats

# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    print("\n" + "="*60)
    print("  MIGRACIÓN DE CITAS  MySQL → PostgreSQL")
    print("="*60)

    reanudar = False
    if CHECKPOINT_FILE.exists():
        ultimo = leer_checkpoint()
        r = input(f"\n🔁 Checkpoint en id={ultimo}. ¿Reanudar? (s/n): ")
        reanudar = r.strip().lower() == "s"

    r = input("\n¿Iniciar migración? (s/n): ")
    if r.strip().lower() != "s":
        print("❌ Cancelado.")
        sys.exit(0)

    try:
        migrar_citas(reanudar=reanudar)
    except KeyboardInterrupt:
        print("\n⚠️  Interrumpido. Checkpoint guardado; puede reanudar luego.")
        sys.exit(1)
    except Exception as exc:
        log.exception("❌ Error inesperado: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()