#!/usr/bin/env python3
"""
MIGRACIÓN DE TABLA CITAS
MySQL → PostgreSQL

Columnas origen (MySQL):
    id, fecha, expediente (int), especialidad (int),
    fecha_cita, nota, tipo, lab, fecha_lab,
    created_at, updated_at, created_by

Columnas destino (PostgreSQL):
    id (identity), fecha_registro, paciente_id, especialidad (VARCHAR 6),
    fecha_cita, expediente (VARCHAR 20), datos_extra (JSONB),
    created_at, updated_at, created_by
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

BATCH_SIZE      = 500
LOG_INTERVAL    = 5_000
CHECKPOINT_FILE = Path("checkpoint_citas.txt")
SKIPPED_FILE    = Path("citas_omitidas.csv")
ERROR_FILE      = Path("citas_errores.csv")

# Mapeo especialidad numérica (MySQL int) → código (PostgreSQL VARCHAR 6)
# Fuente: getCitaTabla(fecha, especialidad, tipo) — segundo parámetro
ESPECIALIDADES_MAP: dict[int, str] = {
    0: "GENE",   # Medicina General (sin equivalente en UI, código propio)
    1: "MEDI",   # Medicina Interna
    2: "PEDI",   # Pediatría
    3: "GINE",   # Ginecología
    4: "CIRU",   # Cirugía
    5: "TRAU",   # Traumatología
    6: "PSIC",   # Psicología
    7: "NUTR",   # Nutrición
    8: "ODON",   # Odontología — confirmado: odonto_consulta(fecha, 8, 1)
}

# Mapeo tipo (MySQL int) → razon_consulta
#   tipo 0 → None            sin tipo definido
#   tipo 1 → "control"       Control - Reconsulta
#   tipo 2 → "ingreso"       Ingreso SOP
#   tipo 3, 4, 5 → "procedimiento"  Procedimiento Menor
#   tipo 9 → "preoperatorio" Preoperatorio
RAZON_CONSULTA_MAP: dict[int, str] = {
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
    migradas: int = 0
    omitidas: int = 0
    errores:  int = 0
    inicio:   datetime = field(default_factory=datetime.now)

    def resumen(self) -> str:
        elapsed = (datetime.now() - self.inicio).total_seconds()
        rate    = self.migradas / elapsed if elapsed else 0
        return (
            f"\n{'='*60}\n"
            f"  ✅  Migradas : {self.migradas:>10,}\n"
            f"  ⚠️   Omitidas : {self.omitidas:>10,}\n"
            f"  ❌  Errores  : {self.errores:>10,}\n"
            f"  ⏱   Tiempo   : {elapsed:>10.1f} s\n"
            f"  🚀  Velocidad: {rate:>10.0f} filas/s\n"
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
        self._writer.writerow({k: str(v) if v is not None else "" for k, v in row.items()})

    def close(self) -> None:
        if self._file:
            self._file.close()

# ============================================================================
# MAPEO DE PACIENTES
# expediente (MySQL int) → paciente_id (PostgreSQL int)
# ============================================================================

def obtener_mapeo_pacientes(pg_conn) -> dict[str, int]:
    """
    Lee todos los pacientes de PostgreSQL y construye:
        str(expediente) → id
    """
    rows  = pg_conn.execute(text("SELECT id, expediente FROM pacientes"))
    mapeo = {}
    for r in rows:
        pid = r[0]
        exp = r[1]
        if exp is not None:
            mapeo[str(exp).strip()] = pid
    return mapeo

# ============================================================================
# TRANSFORMACIÓN
# ============================================================================

def _safe_date(val):
    """datetime → date, None si nulo."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    return val


def _construir_datos_extra(raw: dict) -> str | None:
    """
    Construye el JSONB datos_extra a partir de los campos MySQL sin columna
    propia en PostgreSQL:

        nota          → datos_extra.nota       (str)
        tipo          → datos_extra.razon_consulta  (ref de la UI)
        lab           → datos_extra.lab        (int)
        fecha_lab     → datos_extra.fecha_lab  (ISO date str)

    Retorna JSON serializado o None si no hay datos.

    Mapeo razon_consulta:
        tipo 1 → "control"       (Control - Reconsulta)
        tipo 9 → "preoperatorio" (Preoperatorio)
        tipo 2 → "ingreso"       (Ingreso SOP)
        tipo 3, 4, 5 → "procedimiento" (Procedimiento Menor)
    """
    extras: dict = {}

    if raw.get("nota"):
        extras["nota"] = raw["nota"]

    tipo = raw.get("tipo")
    if tipo is not None:
        razon = RAZON_CONSULTA_MAP.get(int(tipo))
        if razon:
            extras["razon_consulta"] = razon
        else:
            # Preservar el valor original para tipos no mapeados
            extras["tipo_original"] = int(tipo)

    if raw.get("lab") is not None:
        extras["lab"] = int(raw["lab"])

    if raw.get("fecha_lab"):
        fl = _safe_date(raw["fecha_lab"])
        extras["fecha_lab"] = fl.isoformat() if fl else None

    return json.dumps(extras, default=str) if extras else None


def transformar_cita(raw: dict, paciente_id: int) -> dict:
    """
    Mapea columnas MySQL → PostgreSQL:

        fecha         → fecha_registro
        expediente    → expediente (VARCHAR 20)  +  paciente_id (FK)
        especialidad  → especialidad VARCHAR(6) via ESPECIALIDADES_MAP
        fecha_cita    → fecha_cita (mismo nombre, ya es date)
        nota, tipo, lab, fecha_lab → datos_extra (JSONB)
    """
    now = datetime.now()

    esp_raw      = raw.get("especialidad")
    especialidad = ESPECIALIDADES_MAP.get(int(esp_raw)) if esp_raw is not None else None

    return {
        "fecha_registro": _safe_date(raw.get("fecha")),
        "paciente_id":    paciente_id,
        "especialidad":   especialidad,
        "fecha_cita":     _safe_date(raw.get("fecha_cita")),
        "expediente":     str(raw["expediente"]).strip() if raw.get("expediente") is not None else None,
        "datos_extra":    _construir_datos_extra(raw),
        "created_at":     raw.get("created_at") or now,
        "updated_at":     raw.get("updated_at") or now,
        "created_by":     raw.get("created_by"),
    }

# ============================================================================
# INSERT
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
    """Intenta lote completo; si falla, reintenta fila a fila."""
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
# DIAGNÓSTICO
# ============================================================================

def diagnosticar(pg_conn, mysql_conn, mapeo: dict) -> None:
    """Imprime info útil para detectar problemas de mapeo."""
    log.info("─" * 60)
    log.info("🔬  DIAGNÓSTICO")

    cols = pg_conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'pacientes'
        ORDER BY ordinal_position
    """))
    log.info("   Columnas pacientes (PG): %s", [c[0] for c in cols])

    sample_pg = list(mapeo.keys())[:5]
    log.info("   Expedientes PG (muestra): %s", sample_pg)

    sample_my = mysql_conn.execute(
        text("SELECT id, expediente, especialidad, tipo FROM citas LIMIT 5")
    )
    for r in sample_my:
        razon = RAZON_CONSULTA_MAP.get(r[3]) if r[3] is not None else None
        log.info(
            "   MySQL cita id=%s  expediente=%s  especialidad=%s  tipo=%s → razon=%s",
            r[0], r[1], r[2], r[3], razon,
        )

    log.info("─" * 60)

# ============================================================================
# MIGRACIÓN PRINCIPAL
# ============================================================================

# ============================================================================
# LIMPIEZA PREVIA
# ============================================================================

def limpiar_tabla_citas(pg_conn) -> None:
    """
    Vacía la tabla citas y reinicia el serial (identity) desde 1.
    Se ejecuta ANTES de la migración cuando no se está reanudando.
    """
    log.info("🗑   Vaciando tabla citas y reiniciando secuencia...")
    pg_conn.execute(text("TRUNCATE TABLE citas RESTART IDENTITY CASCADE"))
    pg_conn.commit()
    log.info("   Tabla citas lista (0 filas, id reiniciado a 1)")


def migrar_citas(reanudar: bool = False) -> Stats:
    log.info("=" * 60)
    log.info("📅  MIGRACIÓN DE CITAS  MySQL → PostgreSQL")
    log.info("=" * 60)

    stats = Stats()
    mysql_eng, pg_eng = crear_motores()

    skipped_writer = CsvWriter(SKIPPED_FILE, ["mysql_id", "expediente", "motivo"])
    error_writer   = CsvWriter(
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

            # Limpiar solo en migración fresca (no al reanudar desde checkpoint)
            if not reanudar:
                limpiar_tabla_citas(pg_conn)

            total = mysql_conn.execute(
                text("SELECT COUNT(*) FROM citas WHERE id > :u"), {"u": ultimo_id_ok}
            ).scalar()
            log.info("📊  Citas en MySQL a procesar: %d", total)

            log.info("🔎  Construyendo mapeo de pacientes...")
            mapeo = obtener_mapeo_pacientes(pg_conn)
            log.info("   Pacientes mapeados: %d", len(mapeo))

            if len(mapeo) == 0:
                log.error("❌  0 pacientes encontrados en PostgreSQL. Abortando.")
                diagnosticar(pg_conn, mysql_conn, mapeo)
                return stats

            diagnosticar(pg_conn, mysql_conn, mapeo)

            resultado = mysql_conn.execute(
                text("SELECT * FROM citas WHERE id > :u ORDER BY id"),
                {"u": ultimo_id_ok},
            )

            lote:      list[dict] = []
            ultimo_id: int        = ultimo_id_ok

            for row in resultado:
                raw        = dict(row._mapping)
                mysql_id   = raw.get("id")
                expediente = raw.get("expediente")

                if expediente is None:
                    stats.omitidas += 1
                    skipped_writer.write({
                        "mysql_id": mysql_id, "expediente": None,
                        "motivo": "sin_expediente",
                    })
                    continue

                paciente_id = mapeo.get(str(expediente).strip())
                if paciente_id is None:
                    stats.omitidas += 1
                    skipped_writer.write({
                        "mysql_id": mysql_id, "expediente": expediente,
                        "motivo": "expediente_no_encontrado_en_pacientes",
                    })
                    continue

                lote.append(transformar_cita(raw, paciente_id))
                stats.migradas += 1
                ultimo_id = mysql_id

                if len(lote) >= BATCH_SIZE:
                    insertar_lote(pg_conn, lote, stats, error_writer)
                    guardar_checkpoint(ultimo_id)
                    lote = []
                    if stats.migradas % LOG_INTERVAL == 0:
                        log.info("   → %d migradas | %d omitidas | %d errores",
                                 stats.migradas, stats.omitidas, stats.errores)

            if lote:
                insertar_lote(pg_conn, lote, stats, error_writer)
                guardar_checkpoint(ultimo_id)

    finally:
        skipped_writer.close()
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