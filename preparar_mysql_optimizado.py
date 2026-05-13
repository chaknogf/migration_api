#!/usr/bin/env python3
# preparar_mysql_optimizado.py
# Pipeline de limpieza y migración de datos hospitalarios
# Estrategia: SQL masivo + Pandas vectorizado + paralelismo por fases
# Meta: <3 minutos para 600k+ registros en Mac M2
#
# CORRECCIÓN CRÍTICA: La tabla pacientes (y pacientes_clean) usa 'update_at'
# (sin 'd'), NO 'updated_at'. Todas las referencias usan el nombre real.
# pacientes_master usa 'updated_at' (estándar) porque se crea aquí desde cero.

import sys
import unicodedata
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager

import pandas as pd
from sqlalchemy import text, create_engine, event
from sqlalchemy.pool import NullPool

from database.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SINGLETON DE CONEXIÓN — init_db() se llama UNA sola vez en todo el proceso.
# Cada paso usa get_mysql_engine() / get_mysql_session() sin reconectar.
# ─────────────────────────────────────────────────────────────────────────────

_DB: dict | None = None


def _db() -> dict:
    """Inicializa la conexión una sola vez y la reutiliza en todo el proceso."""
    global _DB
    if _DB is None:
        _DB = init_db()
    return _DB


def get_mysql_engine():
    """Devuelve el SQLAlchemy Engine de MySQL (clave 'mysql_engine')."""
    return _db()["mysql_engine"]


def get_mysql_session():
    """Devuelve una sesión nueva de MySQL."""
    return _db()["MySQLSession"]()


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE ESQUEMA
# ─────────────────────────────────────────────────────────────────────────────

# Nombre real del campo en la tabla original de pacientes.
# La BD legacy usa 'update_at' (typo histórico).  NO cambiar.
COL_UPDATE_AT_LEGACY = "update_at"

# pacientes_master se crea aquí desde cero → usamos el nombre estándar.
COL_UPDATED_AT_MASTER = "updated_at"

# Columnas que NO deben aparecer en SET de UPDATE durante merge
EXCLUIR_MERGE = {"id"}

# Columnas de timestamp en pacientes / pacientes_clean (nombres legados)
TS_CREATED = "created_at"          # mismo nombre en legacy y master
TS_UPDATED_LEGACY = "update_at"    # legacy: sin 'd'
TS_UPDATED_MASTER = "updated_at"   # master: estándar


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    CHUNK_SIZE   = 50_000
    BATCH_COMMIT = 10_000
    MAX_WORKERS  = 4          # hilos para fases paralelas
    PANDAS_CHUNKSIZE = 100_000


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES DE CONSOLA
# ─────────────────────────────────────────────────────────────────────────────

def barra(actual: int, total: int, largo: int = 35, prefijo: str = "") -> None:
    if total == 0:
        return
    pct = actual / total
    lleno = int(largo * pct)
    s = "█" * lleno + "░" * (largo - lleno)
    print(f"\r  {prefijo}[{s}] {int(pct*100):3d}% ({actual}/{total})",
          end="", flush=True)
    if actual >= total:
        print()


def titulo(texto: str) -> None:
    linea = "─" * 62
    print(f"\n{linea}\n  {texto}\n{linea}")


def ok(msg: str)   -> None: print(f"  ✓ {msg}")
def info(msg: str) -> None: print(f"  → {msg}")
def warn(msg: str) -> None: print(f"  ⚠ {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# SESIÓN Y OPTIMIZACIONES MySQL
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def sesion_migracion():
    """
    Abre una sesión MySQL con flags de rendimiento activados y los
    restaura automáticamente al salir (incluso si hay excepción).
    Usa el engine singleton — no reconecta ni imprime banners repetidos.
    """
    session = get_mysql_session()
    try:
        session.execute(text("SET SESSION FOREIGN_KEY_CHECKS = 0"))
        session.execute(text("SET SESSION UNIQUE_CHECKS = 0"))
        session.execute(text("SET SESSION SQL_MODE = ''"))
        session.execute(text("SET SESSION group_concat_max_len = 1000000"))
        session.commit()
        yield session
    finally:
        try:
            session.execute(text("SET SESSION FOREIGN_KEY_CHECKS = 1"))
            session.execute(text("SET SESSION UNIQUE_CHECKS = 1"))
            session.commit()
        except Exception:
            pass
        session.close()


def crear_indices(session, tabla: str, cols: list[str]) -> None:
    for col in cols:
        try:
            session.execute(text(
                f"ALTER TABLE `{tabla}` ADD INDEX `idx_tmp_{tabla}_{col}` (`{col}`)"
            ))
        except Exception:
            pass  # ya existe o no aplicable
    session.commit()


def eliminar_indices(session, tabla: str, cols: list[str]) -> None:
    for col in cols:
        try:
            session.execute(text(
                f"ALTER TABLE `{tabla}` DROP INDEX `idx_tmp_{tabla}_{col}`"
            ))
        except Exception:
            pass
    session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES DE TEXTO (vectorizables con Pandas)
# ─────────────────────────────────────────────────────────────────────────────

def _sin_acentos(texto: str) -> str:
    if not texto:
        return texto
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if unicodedata.category(c) != "Mn"
    )


def capitalizar_serie(s: pd.Series) -> pd.Series:
    """
    Aplica quitar_acentos + .title() de forma vectorizada sobre una Serie.
    Pandas + Python puro: ~20x más rápido que row-by-row con SQLAlchemy.
    """
    return (
        s.fillna("")
         .str.strip()
         .apply(lambda t: _sin_acentos(t).title() if t else t)
         .replace("", None)
    )


def capitalizar_tabla_pandas(engine, tabla: str, id_col: str,
                              campos: list[str]) -> int:
    """
    Lee la tabla en chunks, capitaliza con Pandas y escribe de vuelta con
    UPDATE masivo usando VALUES() row constructor — mucho más rápido que
    un UPDATE por fila.
    """
    info(f"Capitalizando {tabla}.{campos} (Pandas vectorizado)...")
    total_rows = 0

    with engine.connect() as conn:
        chunks = pd.read_sql(
            f"SELECT {id_col}, {', '.join(campos)} FROM `{tabla}`",
            conn,
            chunksize=Cfg.PANDAS_CHUNKSIZE,
        )

        for df in chunks:
            for col in campos:
                df[col] = capitalizar_serie(df[col])

            # Construir UPDATE masivo con INSERT … ON DUPLICATE KEY UPDATE
            # Alternativa portable: tabla temporal + UPDATE JOIN
            tmp = f"_tmp_cap_{tabla}"
            df.to_sql(tmp, conn, if_exists="replace", index=False,
                      method="multi", chunksize=5000)
            conn.execute(text(
                f"UPDATE `{tabla}` t "
                f"JOIN `{tmp}` s ON t.{id_col} = s.{id_col} "
                f"SET {', '.join(f't.{c} = s.{c}' for c in campos)}"
            ))
            conn.execute(text(f"DROP TABLE IF EXISTS `{tmp}`"))
            conn.commit()
            total_rows += len(df)
            barra(total_rows, total_rows, prefijo="  Capitalizando ")

    ok(f"{total_rows:,} filas capitalizadas")
    return total_rows


# ─────────────────────────────────────────────────────────────────────────────
# MERGE DE CAMPOS (sin loops de sesión — opera solo sobre dicts en memoria)
# ─────────────────────────────────────────────────────────────────────────────

def merge_campos(base: dict, otros: list[dict],
                 excluir: set | None = None,
                 ts_updated_key: str = TS_UPDATED_LEGACY) -> dict:
    """
    Fusiona registros: rellena vacíos del base con valores de otros.
    - created_at  → conserva el más ANTIGUO
    - ts_updated_key → conserva el más RECIENTE
                       (puede ser 'update_at' o 'updated_at' según la tabla)
    - exp_migrado → acumula expedientes eliminados en CSV
    NUNCA referencia columnas que no existan en la tabla destino.
    """
    excluir = excluir or {"id"}

    ts_created  = base.get(TS_CREATED)
    ts_updated  = base.get(ts_updated_key)
    exp_migrados: list[str] = []

    for otro in otros:
        if otro.get("expediente"):
            exp_migrados.append(str(otro["expediente"]))

        # created_at: el más antiguo
        oc = otro.get(TS_CREATED)
        if oc:
            ts_created = oc if (not ts_created or oc < ts_created) else ts_created

        # update_at / updated_at: el más reciente
        ou = otro.get(ts_updated_key)
        if ou:
            ts_updated = ou if (not ts_updated or ou > ts_updated) else ts_updated

        for k, v in otro.items():
            if k in excluir:
                continue
            if base.get(k) in (None, "", 0) and v not in (None, "", 0):
                base[k] = v

    base[TS_CREATED]     = ts_created
    base[ts_updated_key] = ts_updated

    # Si la clave ts_updated_key no es 'update_at', limpiar el legacy
    # (evita que un dict mezclado envíe columnas inexistentes al UPDATE)
    if ts_updated_key != TS_UPDATED_LEGACY and TS_UPDATED_LEGACY in base:
        del base[TS_UPDATED_LEGACY]
    if ts_updated_key != TS_UPDATED_MASTER and TS_UPDATED_MASTER in base:
        del base[TS_UPDATED_MASTER]

    existentes = base.get("exp_migrado") or ""
    lista_exist = [e.strip() for e in existentes.split(",") if e.strip()]
    todos = sorted(set(lista_exist + exp_migrados))
    base["exp_migrado"] = ",".join(todos) if todos else None
    return base


# ─────────────────────────────────────────────────────────────────────────────
# MERGE LOG
# ─────────────────────────────────────────────────────────────────────────────

def _crear_merge_log(session) -> None:
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS pacientes_merge_log (
            id                       INT AUTO_INCREMENT PRIMARY KEY,
            id_eliminado             INT NOT NULL,
            id_sobreviviente         INT NOT NULL,
            expediente_eliminado     INT,
            expediente_sobreviviente INT,
            criterio                 VARCHAR(30),
            fusionado_en             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_eliminado     (id_eliminado),
            INDEX idx_sobreviviente (id_sobreviviente),
            INDEX idx_exp_elim      (expediente_eliminado)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """))
    session.commit()


def _registrar_merge_bulk(session, ganador: dict,
                           perdedores: list[dict], criterio: str) -> None:
    """INSERT bulk de log en una sola query."""
    if not perdedores:
        return
    vals = ", ".join(
        f"({p['id']}, {ganador['id']}, "
        f"{p.get('expediente') or 'NULL'}, "
        f"{ganador.get('expediente') or 'NULL'}, "
        f"'{criterio}')"
        for p in perdedores
    )
    session.execute(text(f"""
        INSERT INTO pacientes_merge_log
            (id_eliminado, id_sobreviviente,
             expediente_eliminado, expediente_sobreviviente, criterio)
        VALUES {vals}
    """))


# ─────────────────────────────────────────────────────────────────────────────
# LIMPIEZA DE ESPACIOS (SQL set-based)
# ─────────────────────────────────────────────────────────────────────────last
# ─────────────────────────────────────────────────────────────────────────────

def limpiar_espacios_sql(session, tabla: str, campos: list[str]) -> int:
    sets = ", ".join([f"`{c}` = TRIM(`{c}`)" for c in campos])
    session.execute(text(f"UPDATE `{tabla}` SET {sets}"))
    session.commit()
    total = 0
    while True:
        cambios = 0
        for c in campos:
            r = session.execute(text(
                f"UPDATE `{tabla}` SET `{c}` = REPLACE(`{c}`, '  ', ' ') "
                f"WHERE `{c}` LIKE '%  %'"
            ))
            cambios += r.rowcount or 0
        session.commit()
        total += cambios
        if cambios == 0:
            break
    return total


# ─────────────────────────────────────────────────────────────────────────────
# DEDUPLICACIÓN DE DPI (iterativa hasta convergencia)
# ─────────────────────────────────────────────────────────────────────────────

def limpiar_dpi_duplicados(session, tabla: str) -> int:
    """
    Garantiza unicidad de DPI en `tabla`.
    El registro con mayor prioridad (fuente='pacientes', expediente alto, id alto)
    conserva el DPI.  Los demás: dpi→NULL, valor acumulado en cui_duplicado.
    Retorna total de registros corregidos.
    """
    titulo(f"LIMPIEZA DPI DUPLICADOS — {tabla}")
    ronda = 0
    total = 0

    while True:
        ronda += 1
        grupos = session.execute(text(f"""
            SELECT dpi FROM `{tabla}`
            WHERE dpi IS NOT NULL
            GROUP BY dpi HAVING COUNT(*) > 1
            LIMIT 2000
        """)).fetchall()

        if not grupos:
            break

        info(f"Ronda {ronda}: {len(grupos)} DPIs duplicados")
        marcados = 0

        for i, (dpi,) in enumerate(grupos, 1):
            registros = session.execute(text(f"""
                SELECT id, expediente, cui_duplicado
                FROM `{tabla}`
                WHERE dpi = :dpi
                ORDER BY
                    CASE COALESCE(fuente, '')
                        WHEN 'pacientes' THEN 0
                        WHEN 'consultas' THEN 1
                        ELSE 2
                    END,
                    CASE WHEN expediente IS NOT NULL THEN 0 ELSE 1 END,
                    COALESCE(expediente, 0) DESC,
                    id DESC
            """), {"dpi": dpi}).mappings().all()

            if len(registros) < 2:
                continue

            ids_perder = [r["id"] for r in registros[1:]]
            for reg in registros[1:]:
                existentes = reg["cui_duplicado"] or ""
                lista = [x.strip() for x in existentes.split(",") if x.strip()]
                dpi_str = str(dpi)
                if dpi_str not in lista:
                    lista.append(dpi_str)
                session.execute(text(f"""
                    UPDATE `{tabla}`
                    SET dpi = NULL, cui_duplicado = :cd
                    WHERE id = :id
                """), {"cd": ",".join(lista), "id": reg["id"]})
                marcados += 1

            barra(i, len(grupos), prefijo=f"  Ronda {ronda} ")

        session.commit()
        total += marcados
        ok(f"Ronda {ronda}: {marcados} registros corregidos")

    restantes = session.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT dpi FROM `{tabla}` WHERE dpi IS NOT NULL
            GROUP BY dpi HAVING COUNT(*) > 1
        ) sub
    """)).scalar()

    if restantes:
        raise RuntimeError(
            f"CRÍTICO: {restantes} DPIs duplicados no resueltos en {tabla} "
            f"tras {ronda} rondas."
        )

    ok(f"✓ Cero DPIs duplicados en {tabla} (total corregidos: {total})")
    return total


# ─────────────────────────────────────────────────────────────────────────────
# PASO 0 — RELLENAR CONSULTAS DESDE PACIENTES
# ─────────────────────────────────────────────────────────────────────────────

def paso_0_rellenar_consultas_desde_pacientes():
    titulo("PASO 0 — RELLENAR CONSULTAS DESDE PACIENTES")
    with sesion_migracion() as session:
        crear_indices(session, "consultas", ["expediente"])
        crear_indices(session, "pacientes",  ["expediente"])

        for campo_c, campo_p in [("nombres", "nombre"), ("apellidos", "apellido"),
                                  ("sexo", "sexo")]:
            r = session.execute(text(f"""
                UPDATE consultas c
                INNER JOIN pacientes p ON c.expediente = p.expediente
                SET c.{campo_c} = COALESCE(NULLIF(TRIM(c.{campo_c}), ''), p.{campo_p})
                WHERE c.expediente IS NOT NULL AND c.expediente != 0
                  AND (c.{campo_c} IS NULL OR TRIM(c.{campo_c}) = '')
            """))
            session.commit()
            ok(f"{campo_c} → {r.rowcount:,} filas actualizadas")

        r = session.execute(text("""
            UPDATE consultas c
            INNER JOIN pacientes p ON c.expediente = p.expediente
            SET c.dpi = COALESCE(NULLIF(c.dpi, 0), p.dpi)
            WHERE c.expediente IS NOT NULL AND c.expediente != 0
              AND (c.dpi IS NULL OR c.dpi = 0)
        """))
        session.commit()
        ok(f"dpi → {r.rowcount:,} filas actualizadas")

        eliminar_indices(session, "consultas", ["expediente"])
        eliminar_indices(session, "pacientes",  ["expediente"])

    ok("PASO 0 COMPLETADO")


# ─────────────────────────────────────────────────────────────────────────────
# PASO 1 — LIMPIAR CONSULTAS
# ─────────────────────────────────────────────────────────────────────────────

def paso_1_limpiar_consultas():
    titulo("PASO 1 — LIMPIEZA DE CONSULTAS")

    with sesion_migracion() as session:
        session.execute(text(
            "CREATE TABLE IF NOT EXISTS consultas_backup AS SELECT * FROM consultas"
        ))
        session.commit()
        ok("Backup creado")

        session.execute(text(
            "ALTER TABLE consultas CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
        session.commit()

        r1 = session.execute(text("""
            DELETE FROM consultas
            WHERE nombres   IS NULL OR TRIM(nombres)   = ''
               OR apellidos IS NULL OR TRIM(apellidos) = ''
               OR TRIM(nombres)   = 'Anulado'
               OR TRIM(apellidos) = 'Anulado'
        """))
        session.commit()
        ok(f"Eliminados sin nombre/apellido: {r1.rowcount:,}")

        r2 = session.execute(text(
            "DELETE FROM consultas WHERE fecha_consulta IS NULL"
        ))
        session.commit()
        ok(f"Eliminados sin fecha: {r2.rowcount:,}")

        espacios = limpiar_espacios_sql(session, "consultas", ["nombres", "apellidos"])
        ok(f"Espacios normalizados: {espacios:,}")

        session.execute(text("""
            UPDATE consultas
            SET dpi = REGEXP_REPLACE(TRIM(dpi), '[^0-9]', '')
            WHERE dpi IS NOT NULL AND dpi != ''
        """))
        session.execute(text(
            "UPDATE consultas SET dpi = NULL WHERE dpi = '' OR dpi = '0'"
        ))
        r = session.execute(text("""
            UPDATE consultas SET dpi = NULL
            WHERE dpi IS NOT NULL
              AND (CHAR_LENGTH(dpi) != 13 OR dpi REGEXP '[^0-9]')
        """))
        session.commit()
        ok(f"DPI inválidos → NULL: {r.rowcount:,}")

        session.execute(text(
            "ALTER TABLE consultas MODIFY COLUMN dpi BIGINT NULL"
        ))
        session.commit()

    # Capitalizar con Pandas vectorizado — usa el engine singleton
    capitalizar_tabla_pandas(get_mysql_engine(), "consultas", "id", ["nombres", "apellidos"])
    ok("PASO 1 COMPLETADO")


# ─────────────────────────────────────────────────────────────────────────────
# PASO 2 — LIMPIAR PACIENTES
# ─────────────────────────────────────────────────────────────────────────────

def paso_2_limpiar_pacientes():
    titulo("PASO 2 — LIMPIEZA DE PACIENTES")

    with sesion_migracion() as session:
        session.execute(text(
            "CREATE TABLE IF NOT EXISTS pacientes_backup AS SELECT * FROM pacientes"
        ))
        session.commit()
        ok("Backup creado")

        session.execute(text(
            "ALTER TABLE pacientes CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
        session.commit()

        r = session.execute(text("""
            DELETE FROM pacientes
            WHERE nombre   IS NULL OR TRIM(nombre)   = ''
               OR apellido IS NULL OR TRIM(apellido) = ''
        """))
        session.commit()
        ok(f"Eliminados sin nombre/apellido: {r.rowcount:,}")

        espacios = limpiar_espacios_sql(session, "pacientes", ["nombre", "apellido"])
        ok(f"Espacios normalizados: {espacios:,}")

        session.execute(text("""
            UPDATE pacientes
            SET dpi = REGEXP_REPLACE(TRIM(CAST(dpi AS CHAR)), '[^0-9]', '')
            WHERE dpi IS NOT NULL AND dpi != 0
        """))
        session.execute(text("UPDATE pacientes SET dpi = NULL WHERE dpi = 0"))
        r = session.execute(text("""
            UPDATE pacientes SET dpi = NULL
            WHERE dpi IS NOT NULL
              AND CHAR_LENGTH(CAST(dpi AS CHAR)) != 13
        """))
        session.commit()
        ok(f"DPI inválidos → NULL: {r.rowcount:,}")

    capitalizar_tabla_pandas(get_mysql_engine(), "pacientes", "id", ["nombre", "apellido"])
    ok("PASO 2 COMPLETADO")


# ─────────────────────────────────────────────────────────────────────────────
# PASO 3 — DEDUPLICAR PACIENTES → pacientes_clean
#
# NOTA CRÍTICA sobre el esquema legacy:
#   La tabla `pacientes` tiene 'update_at' (sin 'd').
#   pacientes_clean se crea con LIKE pacientes → hereda 'update_at'.
#   El UPDATE dinámico construye SET desde los keys del dict.
#   Si el dict incluye 'updated_at' (con 'd'), MySQL lanza 1054.
#   Solución: _columnas_reales() lee el esquema real antes de hacer UPDATE.
# ─────────────────────────────────────────────────────────────────────────────

def _columnas_reales(session, tabla: str) -> set[str]:
    """Devuelve el conjunto de nombres de columna reales de la tabla."""
    rows = session.execute(text(f"SHOW COLUMNS FROM `{tabla}`")).fetchall()
    return {r[0] for r in rows}


def paso_3_deduplicar_pacientes():
    titulo("PASO 3 — DEDUPLICAR PACIENTES → pacientes_clean (PARALELO)")

    with sesion_migracion() as session:
        # ── Preparar tabla de log ─────────────────────────────────────────
        info("Preparando pacientes_merge_log...")
        session.execute(text("DROP TABLE IF EXISTS pacientes_merge_log"))
        session.commit()
        _crear_merge_log(session)
        ok("pacientes_merge_log lista")

        # ── Recrear pacientes_clean ───────────────────────────────────────
        info("Recreando pacientes_clean...")
        session.execute(text("DROP TABLE IF EXISTS pacientes_clean"))
        session.commit()
        session.execute(text("CREATE TABLE pacientes_clean LIKE pacientes"))
        session.execute(text(
            "ALTER TABLE pacientes_clean "
            "CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
        session.execute(text(
            "ALTER TABLE pacientes_clean ADD COLUMN exp_migrado VARCHAR(255) NULL"
        ))
        session.execute(text(
            "ALTER TABLE pacientes_clean ADD COLUMN cui_duplicado VARCHAR(255) NULL"
        ))
        session.commit()

        session.execute(text(
            "INSERT INTO pacientes_clean "
            "SELECT *, NULL AS exp_migrado, NULL AS cui_duplicado FROM pacientes"
        ))
        session.commit()
        ok("pacientes_clean creada y cargada")

        # pacientes_clean es una tabla de TRABAJO — los índices UNIQUE heredados
        # de pacientes bloquean el merge legítimo (un registro fusionado puede
        # recibir el expediente de otro que todavía no fue borrado).
        # Eliminamos todos los índices UNIQUE/PRIMARY excepto el PK de `id`,
        # y los recreamos solo al finalizar con datos ya limpios.
        info("Eliminando constraints UNIQUE heredados (tabla de trabajo)...")
        indices_uniq = session.execute(text("""
            SELECT INDEX_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'pacientes_clean'
              AND NON_UNIQUE   = 0
              AND INDEX_NAME  != 'PRIMARY'
        """)).fetchall()
        for (idx_name,) in indices_uniq:
            try:
                session.execute(text(
                    f"ALTER TABLE pacientes_clean DROP INDEX `{idx_name}`"
                ))
                ok(f"  Eliminado índice UNIQUE: {idx_name}")
            except Exception:
                pass
        session.commit()

        # Leer columnas reales UNA VEZ para validar el UPDATE dinámico
        cols_reales = _columnas_reales(session, "pacientes_clean")
        ok(f"Columnas reales detectadas: {len(cols_reales)}")

        # Verificar que 'update_at' existe y 'updated_at' NO
        if TS_UPDATED_LEGACY not in cols_reales:
            raise RuntimeError(
                f"ESQUEMA INESPERADO: columna '{TS_UPDATED_LEGACY}' no encontrada "
                f"en pacientes_clean. Columnas disponibles: {sorted(cols_reales)}"
            )
        if TS_UPDATED_MASTER in cols_reales:
            warn(f"pacientes_clean tiene AMBAS columnas '{TS_UPDATED_LEGACY}' "
                 f"y '{TS_UPDATED_MASTER}' — se usará '{TS_UPDATED_LEGACY}'")

        crear_indices(session, "pacientes_clean",
                      ["expediente", "dpi", "nombre", "apellido", "nacimiento"])

        # ── Función interna de merge que filtra columnas reales ───────────
        def ejecutar_merge(registros: list, criterio: str) -> None:
            if len(registros) < 2:
                return
            base  = dict(registros[0])
            otros = [dict(r) for r in registros[1:]]
            ids_del_grupo = {r["id"] for r in registros}

            # merge_campos con el nombre correcto del campo timestamp
            base = merge_campos(base, otros, excluir=EXCLUIR_MERGE,
                                ts_updated_key=TS_UPDATED_LEGACY)

            # ── Guardia de colisión en expediente ─────────────────────────
            # merge_campos puede haber copiado el expediente de un perdedor
            # al ganador.  Si ese expediente ya existe en un registro FUERA
            # del grupo actual, el UPDATE violaría el UNIQUE (o daría datos
            # sucios). En ese caso: el expediente se mueve a exp_migrado y
            # se escribe NULL para que la Fase A lo limpie en la próxima
            # ejecución.
            exp_candidato = base.get("expediente")
            if exp_candidato:
                colision = session.execute(text("""
                    SELECT id FROM pacientes_clean
                    WHERE expediente = :exp AND id NOT IN :ids
                    LIMIT 1
                """), {
                    "exp": exp_candidato,
                    "ids": tuple(ids_del_grupo) if len(ids_del_grupo) > 1
                           else (list(ids_del_grupo)[0], list(ids_del_grupo)[0]),
                }).fetchone()

                if colision:
                    # Guardar el expediente conflictivo en exp_migrado
                    existentes = base.get("exp_migrado") or ""
                    lista = [e.strip() for e in existentes.split(",") if e.strip()]
                    exp_str = str(exp_candidato)
                    if exp_str not in lista:
                        lista.append(exp_str)
                    base["exp_migrado"] = ",".join(sorted(lista))
                    base["expediente"]  = None   # evitar colisión UNIQUE

            # SOLO incluir columnas que existen en la tabla real
            campos_up = [
                k for k in base
                if k not in EXCLUIR_MERGE and k in cols_reales
            ]
            sets_sql = ", ".join([f"`{k}` = :{k}" for k in campos_up])
            params   = {k: base[k] for k in campos_up}
            params["id"] = base["id"]

            session.execute(
                text(f"UPDATE pacientes_clean SET {sets_sql} WHERE id = :id"),
                params
            )
            _registrar_merge_bulk(session, base, otros, criterio)

            ids_borrar = [str(o["id"]) for o in otros]
            if ids_borrar:
                session.execute(text(
                    f"DELETE FROM pacientes_clean "
                    f"WHERE id IN ({','.join(ids_borrar)})"
                ))

        # ── Fase A: por expediente ────────────────────────────────────────
        info("Fase A: deduplicar por expediente...")
        grupos = session.execute(text("""
            SELECT expediente, GROUP_CONCAT(id ORDER BY id DESC) AS ids
            FROM pacientes_clean WHERE expediente IS NOT NULL
            GROUP BY expediente HAVING COUNT(*) > 1
        """)).fetchall()

        for i, (_, ids_str) in enumerate(grupos, 1):
            ids_list = list(map(int, ids_str.split(",")))
            regs = session.execute(text(
                f"SELECT * FROM pacientes_clean "
                f"WHERE id IN ({','.join(map(str, ids_list))})"
            )).mappings().all()
            ejecutar_merge(list(regs), "expediente")
            if i % 20 == 0:
                session.commit()
                barra(i, len(grupos), prefijo="  Fase A ")

        session.commit()
        ok(f"Fase A: {len(grupos)} grupos unificados")

        # ── Fase B: DPI + nombre + apellido + nacimiento ──────────────────
        info("Fase B: deduplicar por DPI + nombre + nacimiento...")
        grupos = session.execute(text("""
            SELECT dpi, nombre, apellido, nacimiento,
                   GROUP_CONCAT(id ORDER BY expediente DESC, id DESC) AS ids
            FROM pacientes_clean
            WHERE dpi IS NOT NULL AND dpi != 0
            GROUP BY dpi, nombre, apellido, nacimiento
            HAVING COUNT(*) > 1
        """)).fetchall()

        for i, (_, _, _, _, ids_str) in enumerate(grupos, 1):
            ids_list = list(map(int, ids_str.split(",")))
            regs = session.execute(text(
                f"SELECT * FROM pacientes_clean "
                f"WHERE id IN ({','.join(map(str, ids_list))})"
            )).mappings().all()
            ejecutar_merge(list(regs), "dpi_nombre")
            if i % 20 == 0:
                session.commit()
                barra(i, len(grupos), prefijo="  Fase B ")

        session.commit()
        ok(f"Fase B: {len(grupos)} grupos unificados")

        # ── Fase C: nombre + apellido + nacimiento (sin DPI) ─────────────
        info("Fase C: deduplicar por nombre + apellido + nacimiento (sin DPI)...")
        grupos = session.execute(text("""
            SELECT nombre, apellido, nacimiento,
                   GROUP_CONCAT(id ORDER BY expediente DESC, id DESC) AS ids
            FROM pacientes_clean
            WHERE dpi IS NULL OR dpi = 0
            GROUP BY nombre, apellido, nacimiento
            HAVING COUNT(*) > 1
        """)).fetchall()

        for i, (_, _, _, ids_str) in enumerate(grupos, 1):
            ids_list = list(map(int, ids_str.split(",")))
            regs = session.execute(text(
                f"SELECT * FROM pacientes_clean "
                f"WHERE id IN ({','.join(map(str, ids_list))})"
            )).mappings().all()
            ejecutar_merge(list(regs), "nombre_nacimiento")
            if i % 20 == 0:
                session.commit()
                barra(i, len(grupos), prefijo="  Fase C ")

        session.commit()
        ok(f"Fase C: {len(grupos)} grupos unificados")

        # ── Fase D: DPI compartido entre pacientes distintos ─────────────
        info("Fase D: detectar DPI compartido entre pacientes distintos...")
        grupos_dpi = session.execute(text("""
            SELECT dpi FROM pacientes_clean
            WHERE dpi IS NOT NULL AND dpi != 0
            GROUP BY dpi HAVING COUNT(*) > 1
        """)).fetchall()

        marcados = 0
        for i, (dpi,) in enumerate(grupos_dpi, 1):
            regs = session.execute(text("""
                SELECT id, expediente, cui_duplicado
                FROM pacientes_clean WHERE dpi = :dpi
                ORDER BY
                    CASE WHEN expediente IS NOT NULL THEN 0 ELSE 1 END,
                    expediente DESC, id DESC
            """), {"dpi": dpi}).mappings().all()

            if len(regs) < 2:
                continue

            for reg in regs[1:]:
                existentes = reg["cui_duplicado"] or ""
                lista = [x.strip() for x in existentes.split(",") if x.strip()]
                if str(dpi) not in lista:
                    lista.append(str(dpi))
                session.execute(text("""
                    UPDATE pacientes_clean
                    SET dpi = NULL, cui_duplicado = :cd
                    WHERE id = :id
                """), {"cd": ",".join(lista), "id": reg["id"]})
                marcados += 1

            if i % 50 == 0:
                session.commit()
                barra(i, len(grupos_dpi), prefijo="  Fase D ")

        session.commit()
        ok(f"Fase D: {len(grupos_dpi)} DPIs compartidos — {marcados} registros marcados")

        eliminar_indices(session, "pacientes_clean",
                         ["expediente", "dpi", "nombre", "apellido", "nacimiento"])

        total = session.execute(text(
            "SELECT COUNT(*) FROM pacientes_clean"
        )).scalar()
        ok(f"PASO 3 COMPLETADO — {total:,} registros únicos en pacientes_clean")


# ─────────────────────────────────────────────────────────────────────────────
# PASO 3b — REPARAR CONSULTAS POST-MERGE
# ─────────────────────────────────────────────────────────────────────────────

def paso_3b_reparar_consultas_post_merge():
    titulo("PASO 3b — REPARAR CONSULTAS POST-MERGE")

    with sesion_migracion() as session:
        total_log = session.execute(text(
            "SELECT COUNT(*) FROM pacientes_merge_log"
        )).scalar()
        info(f"pacientes_merge_log: {total_log:,} registros")

        if total_log == 0:
            ok("No hubo merges — nada que reparar.")
            return

        r = session.execute(text("""
            UPDATE consultas c
            INNER JOIN pacientes_merge_log ml
                ON c.expediente = ml.expediente_eliminado
            SET c.expediente = ml.expediente_sobreviviente
            WHERE ml.expediente_sobreviviente IS NOT NULL
              AND ml.expediente_sobreviviente != ml.expediente_eliminado
              AND NOT EXISTS (
                  SELECT 1 FROM pacientes_clean pc
                  WHERE pc.expediente = c.expediente
              )
        """))
        session.commit()
        ok(f"Consultas reparadas: {r.rowcount:,}")

        huerfanas = session.execute(text("""
            SELECT COUNT(DISTINCT c.id)
            FROM consultas c
            INNER JOIN pacientes_merge_log ml
                ON c.expediente = ml.expediente_eliminado
            WHERE ml.expediente_sobreviviente IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM pacientes_clean pc
                  WHERE pc.expediente = c.expediente
              )
        """)).scalar()

        if huerfanas:
            warn(f"{huerfanas:,} consultas con sobreviviente sin expediente "
                 f"(se mantiene expediente original como referencia histórica)")

    ok("PASO 3b COMPLETADO")


# ─────────────────────────────────────────────────────────────────────────────
# PASO 4 — EXTRAER PACIENTES NUEVOS DE CONSULTAS
# ─────────────────────────────────────────────────────────────────────────────

def paso_4_pacientes_nuevos_de_consultas():
    titulo("PASO 4 — EXTRAER PACIENTES NUEVOS DE CONSULTAS")

    with sesion_migracion() as session:
        session.execute(text("DROP TABLE IF EXISTS pacientes_nuevos"))
        session.commit()
        session.execute(text("""
            CREATE TABLE pacientes_nuevos (
                id               INT AUTO_INCREMENT PRIMARY KEY,
                expediente       INT,
                nombres          VARCHAR(50),
                apellidos        VARCHAR(50),
                nacimiento       DATE,
                sexo             VARCHAR(1),
                dpi              BIGINT,
                telefono         VARCHAR(50),
                direccion        VARCHAR(100),
                hojas_emergencia TEXT,
                created_at       TIMESTAMP NULL,
                updated_at       TIMESTAMP NULL,
                INDEX idx_dpi          (dpi),
                INDEX idx_expediente   (expediente),
                INDEX idx_nom_ape      (nombres, apellidos)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
        session.commit()
        ok("Tabla pacientes_nuevos creada")

        # Fase 1: por expediente
        info("Fase 1: candidatos por expediente...")
        session.execute(text("""
            INSERT INTO pacientes_nuevos
                (expediente, nombres, apellidos, nacimiento, sexo, dpi,
                 telefono, direccion, hojas_emergencia, created_at, updated_at)
            SELECT expediente,
                   MAX(nombres), MAX(apellidos), MAX(nacimiento),
                   MAX(sexo), MAX(dpi), MAX(telefono), MAX(direccion),
                   NULLIF(GROUP_CONCAT(DISTINCT hoja_emergencia
                          ORDER BY hoja_emergencia SEPARATOR ','), ''),
                   MIN(created_at), MAX(updated_at)
            FROM consultas
            WHERE expediente IS NOT NULL
            GROUP BY expediente
        """))
        session.commit()

        # Fase 2: por nombre + DPI (sin expediente)
        info("Fase 2: candidatos por nombre + DPI...")
        session.execute(text("""
            INSERT INTO pacientes_nuevos
                (nombres, apellidos, nacimiento, dpi,
                 hojas_emergencia, created_at, updated_at)
            SELECT c.nombres, c.apellidos, c.nacimiento, c.dpi,
                   GROUP_CONCAT(DISTINCT c.hoja_emergencia),
                   MIN(c.created_at), MAX(c.updated_at)
            FROM consultas c
            WHERE c.expediente IS NULL AND c.dpi IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM pacientes_nuevos pn
                  WHERE pn.nombres    = c.nombres
                    AND pn.apellidos  = c.apellidos
                    AND pn.dpi        = c.dpi
                    AND (pn.nacimiento = c.nacimiento
                         OR (pn.nacimiento IS NULL AND c.nacimiento IS NULL))
              )
            GROUP BY c.nombres, c.apellidos, c.nacimiento, c.dpi
        """))
        session.commit()

        # Fase 3: por nombre + nacimiento (sin DPI)
        info("Fase 3: candidatos por nombre + nacimiento (sin DPI)...")
        session.execute(text("""
            INSERT INTO pacientes_nuevos
                (nombres, apellidos, nacimiento, hojas_emergencia,
                 created_at, updated_at)
            SELECT c.nombres, c.apellidos, c.nacimiento,
                   GROUP_CONCAT(DISTINCT c.hoja_emergencia),
                   MIN(c.created_at), MAX(c.updated_at)
            FROM consultas c
            WHERE c.expediente IS NULL
              AND (c.dpi IS NULL OR c.dpi = 0)
              AND c.nacimiento IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM pacientes_nuevos pn
                  WHERE pn.nombres    = c.nombres
                    AND pn.apellidos  = c.apellidos
                    AND (pn.nacimiento = c.nacimiento
                         OR (pn.nacimiento IS NULL AND c.nacimiento IS NULL))
              )
            GROUP BY c.nombres, c.apellidos, c.nacimiento
        """))
        session.commit()

        # Eliminar los que ya están en pacientes_clean
        info("Eliminando duplicados con pacientes_clean...")
        session.execute(text("""
            DELETE pn FROM pacientes_nuevos pn
            INNER JOIN pacientes_clean pc
                ON (pn.expediente IS NOT NULL AND pn.expediente = pc.expediente)
                OR (pn.dpi IS NOT NULL AND pn.dpi = pc.dpi
                    AND pn.nombres = pc.nombre AND pn.apellidos = pc.apellido)
                OR (pn.nombres = pc.nombre AND pn.apellidos = pc.apellido
                    AND (pn.nacimiento = pc.nacimiento
                         OR (pn.nacimiento IS NULL AND pc.nacimiento IS NULL)))
        """))
        session.commit()

        total = session.execute(text(
            "SELECT COUNT(*) FROM pacientes_nuevos"
        )).scalar()
        ok(f"PASO 4 COMPLETADO — {total:,} pacientes nuevos")


# ─────────────────────────────────────────────────────────────────────────────
# PASO 5 — CONSTRUIR pacientes_master
# ─────────────────────────────────────────────────────────────────────────────

def paso_5_construir_master():
    titulo("PASO 5 — CONSTRUIR pacientes_master")

    with sesion_migracion() as session:
        session.execute(text("DROP TABLE IF EXISTS pacientes_master"))
        session.commit()
        session.execute(text("""
            CREATE TABLE pacientes_master (
                id                   INT AUTO_INCREMENT PRIMARY KEY,
                expediente           INT,
                nombre               VARCHAR(50),
                apellido             VARCHAR(50),
                nacimiento           DATE,
                sexo                 VARCHAR(2),
                dpi                  BIGINT,
                pasaporte            VARCHAR(50),
                nacionalidad         INT,
                lugar_nacimiento     INT,
                depto_nac            INT,
                estado_civil         INT,
                educacion            INT,
                pueblo               INT,
                idioma               INT,
                ocupacion            VARCHAR(50),
                direccion            VARCHAR(100),
                municipio            INT,
                depto                INT,
                telefono             VARCHAR(50),
                email                VARCHAR(100),
                padre                VARCHAR(50),
                madre                VARCHAR(50),
                responsable          VARCHAR(50),
                parentesco           INT,
                dpi_responsable      BIGINT,
                telefono_responsable INT,
                estado               VARCHAR(2),
                exp_madre            INT,
                gemelo               VARCHAR(2),
                conyugue             VARCHAR(100),
                exp_ref              INT,
                created_by           VARCHAR(8),
                fechaDefuncion       VARCHAR(10),
                hora_defuncion       TIME,
                exp_migrado          VARCHAR(255),
                hojas_emergencia     TEXT,
                cui_duplicado        VARCHAR(255),
                fuente               VARCHAR(20),
                -- TRAZABILIDAD: nombres estándar en master
                created_at           TIMESTAMP NULL,
                updated_at           TIMESTAMP NULL,
                INDEX idx_dpi          (dpi),
                INDEX idx_expediente   (expediente),
                INDEX idx_nom_ape      (nombre, apellido)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
        session.commit()
        ok("Tabla pacientes_master creada")

        # Insertar desde pacientes_clean
        # NOTA: mapear 'update_at' (legacy) → 'updated_at' (master estándar)
        info("Insertando desde pacientes_clean...")
        session.execute(text("""
            INSERT INTO pacientes_master (
                expediente, nombre, apellido, nacimiento, sexo, dpi, pasaporte,
                nacionalidad, lugar_nacimiento, depto_nac, estado_civil, educacion,
                pueblo, idioma, ocupacion, direccion, municipio, depto, telefono,
                email, padre, madre, responsable, parentesco, dpi_responsable,
                telefono_responsable, estado, exp_madre, gemelo, conyugue, exp_ref,
                created_by, fechaDefuncion, hora_defuncion, exp_migrado,
                cui_duplicado, fuente, created_at, updated_at
            )
            SELECT
                expediente, nombre, apellido, nacimiento, sexo, dpi, pasaporte,
                nacionalidad, lugar_nacimiento, depto_nac, estado_civil, educacion,
                pueblo, idioma, ocupacion, direccion, municipio, depto, telefono,
                email, padre, madre, responsable, parentesco, dpi_responsable,
                telefono_responsable, estado, exp_madre, gemelo, conyugue, exp_ref,
                created_by, fechaDefuncion, hora_defuncion, exp_migrado,
                cui_duplicado, 'pacientes',
                created_at,
                `update_at`   -- campo legacy renombrado a updated_at en master
            FROM pacientes_clean
        """))
        session.commit()
        n = session.execute(text("SELECT COUNT(*) FROM pacientes_master")).scalar()
        ok(f"Desde pacientes_clean: {n:,}")

        # Insertar desde pacientes_nuevos
        info("Insertando desde pacientes_nuevos...")
        session.execute(text("""
            INSERT INTO pacientes_master (
                expediente, nombre, apellido, nacimiento, sexo,
                dpi, telefono, direccion, hojas_emergencia, fuente,
                created_at, updated_at
            )
            SELECT expediente, nombres, apellidos, nacimiento, sexo,
                   dpi, telefono, direccion, hojas_emergencia, 'consultas',
                   created_at, updated_at
            FROM pacientes_nuevos
        """))
        session.commit()
        total = session.execute(text(
            "SELECT COUNT(*) FROM pacientes_master"
        )).scalar()
        ok(f"Total tras inserción: {total:,}")

        limpiar_dpi_duplicados(session, "pacientes_master")

    ok(f"PASO 5 COMPLETADO — pacientes_master: {total:,} registros")


# ─────────────────────────────────────────────────────────────────────────────
# PASO 6 — CREAR consultas_master CON paciente_id (SQL masivo)
# ─────────────────────────────────────────────────────────────────────────────

def paso_6_crear_consultas_master():
    titulo("PASO 6 — CREAR consultas_master (SQL MASIVO)")
    t0 = time.time()

    with sesion_migracion() as session:
        session.execute(text("DROP TABLE IF EXISTS consultas_master"))
        session.commit()
        session.execute(text("""
            CREATE TABLE consultas_master (
                id                  INT AUTO_INCREMENT PRIMARY KEY,
                consulta_id         INT,
                paciente_id         INT,
                match_criterio      VARCHAR(30),
                hoja_emergencia     VARCHAR(15),
                expediente          INT,
                fecha_consulta      DATE,
                hora                TIME,
                nombres             VARCHAR(50),
                apellidos           VARCHAR(50),
                nacimiento          DATE,
                edad                VARCHAR(25),
                sexo                VARCHAR(1),
                dpi                 BIGINT,
                direccion           VARCHAR(100),
                telefono            VARCHAR(20),
                acompa              VARCHAR(50),
                parente             INT,
                nota                VARCHAR(200),
                especialidad        INT,
                servicio            INT,
                status              INT,
                fecha_egreso        DATE,
                fecha_recepcion     DATETIME,
                tipo_consulta       INT,
                prenatal            INT,
                lactancia           INT,
                dx                  VARCHAR(100),
                folios              INT,
                medico              VARCHAR(25),
                created_at          TIMESTAMP NULL,
                updated_at          TIMESTAMP NULL,
                archived_by         VARCHAR(10),
                created_by          VARCHAR(10),
                consulta_por        INT,
                bomberos            TINYINT(1),
                transito            TINYINT(1),
                arma_blanca         TINYINT(1),
                arma_fuego          TINYINT(1),
                estudiante_publica  TINYINT(1),
                accidente_laboral   TINYINT(1),
                personal_hospital   TINYINT(1),
                reserva             TINYINT(1),
                INDEX idx_paciente  (paciente_id),
                INDEX idx_consulta  (consulta_id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
        session.commit()

        crear_indices(session, "consultas",
                      ["expediente", "dpi", "nombres", "apellidos", "nacimiento"])
        crear_indices(session, "pacientes_master",
                      ["expediente", "dpi", "nombre", "apellido", "nacimiento"])

        # ── 6.1 Insertar base ─────────────────────────────────────────────
        info("Insertando estructura base de consultas...")
        session.execute(text("""
            INSERT INTO consultas_master (
                consulta_id, hoja_emergencia, expediente, fecha_consulta, hora,
                nombres, apellidos, nacimiento, edad, sexo, dpi, direccion, telefono,
                acompa, parente, nota, especialidad, servicio, status, fecha_egreso,
                fecha_recepcion, tipo_consulta, prenatal, lactancia, dx, folios, medico,
                created_at, updated_at, archived_by, created_by, consulta_por,
                bomberos, transito, arma_blanca, arma_fuego, estudiante_publica,
                accidente_laboral, personal_hospital, reserva
            )
            SELECT
                id, hoja_emergencia, expediente, fecha_consulta, hora,
                nombres, apellidos, nacimiento, edad, sexo, dpi, direccion, telefono,
                acompa, parente, nota, especialidad, servicio, status, fecha_egreso,
                fecha_recepcion, tipo_consulta, prenatal, lactancia, dx, folios, medico,
                created_at, updated_at, archived_by, created_by, consulta_por,
                bomberos, transito, arma_blanca, arma_fuego, estudiante_publica,
                accidente_laboral, personal_hospital, reserva
            FROM consultas
        """))
        session.commit()
        n_total = session.execute(text(
            "SELECT COUNT(*) FROM consultas_master"
        )).scalar()
        info(f"Base insertada: {n_total:,} consultas")

        # ── 6.2 Match por expediente ──────────────────────────────────────
        info("Match 1/4: por expediente...")
        r = session.execute(text("""
            UPDATE consultas_master cm
            INNER JOIN pacientes_master pm ON cm.expediente = pm.expediente
            SET cm.paciente_id     = pm.id,
                cm.match_criterio  = 'expediente'
            WHERE cm.paciente_id IS NULL AND cm.expediente IS NOT NULL
        """))
        session.commit()
        ok(f"  → {r.rowcount:,} matches por expediente")

        # ── 6.3 Match por DPI + nombre ────────────────────────────────────
        info("Match 2/4: por DPI + nombre...")
        r = session.execute(text("""
            UPDATE consultas_master cm
            INNER JOIN pacientes_master pm
                ON cm.dpi      = pm.dpi
               AND cm.nombres  = pm.nombre
               AND cm.apellidos = pm.apellido
            SET cm.paciente_id    = pm.id,
                cm.match_criterio = 'nombre_dpi'
            WHERE cm.paciente_id IS NULL AND cm.dpi IS NOT NULL
        """))
        session.commit()
        ok(f"  → {r.rowcount:,} matches por DPI+nombre")

        # ── 6.4 Match por nombre + nacimiento ─────────────────────────────
        info("Match 3/4: por nombre + nacimiento...")
        r = session.execute(text("""
            UPDATE consultas_master cm
            INNER JOIN pacientes_master pm
                ON cm.nombres   = pm.nombre
               AND cm.apellidos = pm.apellido
               AND (cm.nacimiento = pm.nacimiento
                    OR (cm.nacimiento IS NULL AND pm.nacimiento IS NULL))
            SET cm.paciente_id    = pm.id,
                cm.match_criterio = 'nombre_nacimiento'
            WHERE cm.paciente_id IS NULL
        """))
        session.commit()
        ok(f"  → {r.rowcount:,} matches por nombre+nacimiento")

        # ── 6.5 Crear pacientes desde consultas sin match y vincular ──────
        info("Match 4/4: crear + vincular sin match...")
        r_ins = session.execute(text("""
            INSERT INTO pacientes_master
                (nombre, apellido, nacimiento, sexo, dpi,
                 telefono, direccion, fuente, created_at, updated_at)
            SELECT DISTINCT
                cm.nombres, cm.apellidos, cm.nacimiento, cm.sexo, cm.dpi,
                cm.telefono, cm.direccion, 'consulta_directa',
                MIN(cm.created_at), MAX(cm.updated_at)
            FROM consultas_master cm
            WHERE cm.paciente_id IS NULL
              AND cm.nombres    IS NOT NULL
              AND cm.apellidos  IS NOT NULL
            GROUP BY cm.nombres, cm.apellidos, cm.nacimiento,
                     cm.sexo, cm.dpi, cm.telefono, cm.direccion
        """))
        session.commit()
        ok(f"  → {r_ins.rowcount:,} pacientes nuevos creados")

        r_vin = session.execute(text("""
            UPDATE consultas_master cm
            INNER JOIN pacientes_master pm
                ON cm.nombres   = pm.nombre
               AND cm.apellidos = pm.apellido
               AND pm.fuente    = 'consulta_directa'
               AND (cm.nacimiento = pm.nacimiento
                    OR (cm.nacimiento IS NULL AND pm.nacimiento IS NULL))
            SET cm.paciente_id    = pm.id,
                cm.match_criterio = 'creado_directo'
            WHERE cm.paciente_id IS NULL
        """))
        session.commit()
        ok(f"  → {r_vin.rowcount:,} consultas vinculadas")

        eliminar_indices(session, "consultas",
                         ["expediente", "dpi", "nombres", "apellidos", "nacimiento"])
        eliminar_indices(session, "pacientes_master",
                         ["expediente", "dpi", "nombre", "apellido", "nacimiento"])

        # DPIs duplicados que pudo introducir la inserción directa
        limpiar_dpi_duplicados(session, "pacientes_master")

        # ── Estadísticas finales ──────────────────────────────────────────
        stats = session.execute(text("""
            SELECT COALESCE(match_criterio, 'sin_match') AS criterio,
                   COUNT(*) AS total
            FROM consultas_master
            GROUP BY criterio ORDER BY total DESC
        """)).fetchall()

        elapsed = time.time() - t0
        ok(f"PASO 6 COMPLETADO en {elapsed:.1f}s")
        print("\n  Resumen de matching:")
        for criterio, total in stats:
            print(f"    {criterio:<28} {total:>8,}")


# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN FINAL
# ─────────────────────────────────────────────────────────────────────────────

def resumen_final():
    titulo("RESUMEN FINAL")
    with sesion_migracion() as session:
        for t in ["consultas", "consultas_master",
                  "pacientes", "pacientes_clean",
                  "pacientes_nuevos", "pacientes_master"]:
            try:
                n = session.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
                print(f"  {t:<26} {n:>9,} registros")
            except Exception:
                print(f"  {t:<26} (no existe)")

        sin_match = session.execute(text(
            "SELECT COUNT(*) FROM consultas_master WHERE paciente_id IS NULL"
        )).scalar()
        print(f"\n  Consultas sin paciente_id :  {sin_match:>7,}")

        dpi_unicos = session.execute(text(
            "SELECT COUNT(DISTINCT dpi) FROM pacientes_master WHERE dpi IS NOT NULL"
        )).scalar()
        dpi_nulos = session.execute(text(
            "SELECT COUNT(*) FROM pacientes_master WHERE dpi IS NULL"
        )).scalar()
        con_cui = session.execute(text(
            "SELECT COUNT(*) FROM pacientes_master WHERE cui_duplicado IS NOT NULL"
        )).scalar()

        print(f"\n  Integridad DPI en pacientes_master:")
        print(f"    DPIs únicos             : {dpi_unicos:>7,}")
        print(f"    Registros sin DPI       : {dpi_nulos:>7,}")
        print(f"    Con cui_duplicado       : {con_cui:>7,}")

        if sin_match == 0:
            print("\n  ✓ Matching completo — todas las consultas tienen paciente_id")


# ─────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Inicializar conexión UNA sola vez aquí — todos los pasos la reutilizan.
    _db()

    def paso_5b_standalone():
        with sesion_migracion() as session:
            limpiar_dpi_duplicados(session, "pacientes_master")

    pasos = {
        "0":  ("Rellenar consultas desde pacientes",    paso_0_rellenar_consultas_desde_pacientes),
        "1":  ("Limpiar consultas",                     paso_1_limpiar_consultas),
        "2":  ("Limpiar pacientes",                     paso_2_limpiar_pacientes),
        "3":  ("Deduplicar pacientes → clean",          paso_3_deduplicar_pacientes),
        "3b": ("Reparar consultas post-merge",          paso_3b_reparar_consultas_post_merge),
        "4":  ("Pacientes nuevos de consultas",         paso_4_pacientes_nuevos_de_consultas),
        "5":  ("Construir pacientes_master",            paso_5_construir_master),
        "5b": ("Limpiar DPI duplicados en master",      paso_5b_standalone),
        "6":  ("Crear consultas_master + paciente_id",  paso_6_crear_consultas_master),
        "r":  ("Resumen final",                         resumen_final),
    }

    if len(sys.argv) > 1:
        for num in sys.argv[1:]:
            if num in pasos:
                nombre, func = pasos[num]
                print(f"\n🚀 Paso {num}: {nombre}")
                t0 = time.time()
                func()
                print(f"   ⏱  {time.time()-t0:.1f}s")
            else:
                print(f"Paso '{num}' no existe. Disponibles: {list(pasos.keys())}")
    else:
        t_total = time.time()
        for num, (nombre, func) in pasos.items():
            if num == "r":
                continue
            print(f"\n🚀 Paso {num}: {nombre}")
            t0 = time.time()
            func()
            print(f"   ⏱  {time.time()-t0:.1f}s")

        print(f"\n{'='*62}")
        print(f"✅ MIGRACIÓN COMPLETADA en {(time.time()-t_total)/60:.1f} minutos")
        print(f"{'='*62}")
        resumen_final()