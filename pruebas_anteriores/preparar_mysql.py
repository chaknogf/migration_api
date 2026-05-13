#!/usr/bin/env python3
# preparar_mysql.py
# Pipeline de limpieza y migración de datos hospitalarios
# Orden: consultas → pacientes → merge → master

import sys
import unicodedata
from sqlalchemy import text
from database.database import init_db
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def barra(actual: int, total: int, largo: int = 35, prefijo: str = "") -> None:
    """Imprime una barra de progreso en la misma línea."""
    if total == 0:
        return
    pct = actual / total
    lleno = int(largo * pct)
    barra_str = "█" * lleno + "░" * (largo - lleno)
    print(f"\r  {prefijo}[{barra_str}] {int(pct * 100):3d}% ({actual}/{total})", end="", flush=True)
    if actual >= total:
        print()  # salto de línea al terminar


def titulo(texto: str) -> None:
    linea = "─" * 60
    print(f"\n{linea}")
    print(f"  {texto}")
    print(linea)


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def info(msg: str) -> None:
    print(f"  → {msg}")


def limpiar_espacios_sql(session, tabla: str, campos: list[str]) -> int:
    """Elimina espacios extremos y dobles en los campos indicados."""
    # TRIM
    sets = ", ".join([f"{c} = TRIM({c})" for c in campos])
    session.execute(text(f"UPDATE {tabla} SET {sets}"))
    session.commit()

    # Espacios dobles internos (loop hasta que no haya cambios)
    total = 0
    while True:
        cambios = 0
        for c in campos:
            r = session.execute(text(
                f"UPDATE {tabla} SET {c} = REPLACE({c}, '  ', ' ') WHERE {c} LIKE '%  %'"
            ))
            cambios += r.rowcount or 0
        session.commit()
        total += cambios
        if cambios == 0:
            break
    return total


def quitar_acentos(texto: str) -> str:
    """
    Elimina acentos y diacríticos de un string.
    Ej: "María José" → "Maria Jose", "Ángel" → "Angel"
    Preserva la ñ como n (NFKD la separa en n + combining tilde).
    """
    if not texto:
        return texto
    # Descompone caracteres en forma NFKD (base + diacrítico separados)
    # luego filtra las marcas de combinación (categoría Mn)
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if unicodedata.category(c) != "Mn"
    )


def capitalizar_python(session, tabla: str, id_col: str,
                        campos: list[str]) -> int:
    """Capitaliza campos de texto usando Python (.title()) para mayor fiabilidad."""
    sets_sql = ", ".join([f"{c} = :{c}" for c in campos])
    select_cols = ", ".join([id_col] + campos)

    rows = session.execute(text(
        f"SELECT {select_cols} FROM {tabla}"
    )).fetchall()

    col_names = [id_col] + campos

    for i, row in enumerate(rows, 1):
        d = dict(zip(col_names, row))
        params = {
            c: (quitar_acentos(d[c].strip()).title() if d[c] else d[c])
            for c in campos
        }
        params[id_col] = d[id_col]
        session.execute(text(
            f"UPDATE {tabla} SET {sets_sql} WHERE {id_col} = :{id_col}"
        ), params)
        barra(i, len(rows), prefijo="  Capitalizando ")

    session.commit()
    return len(rows)


def merge_campos(base: dict, otros: list[dict],
                 excluir: set = None) -> dict:
    """
    Combina registros rellenando campos vacíos del base con valores de otros.
    Acumula expedientes migrados en exp_migrado (CSV).
    PRESERVA created_at (más antigua) y updated_at (más reciente)
    """
    excluir = excluir or {"id"}
    
    # Para created_at: tomar la más antigua (mínimo timestamp)
    # Para updated_at: tomar la más reciente (máximo timestamp)
    timestamps_base = {
        "created_at": base.get("created_at"),
        "updated_at": base.get("updated_at")
    }
    
    exp_migrados: list[str] = []

    for otro in otros:
        if otro.get("expediente"):
            exp_migrados.append(str(otro["expediente"]))
        
        # Actualizar created_at con la más antigua
        otro_created = otro.get("created_at")
        if otro_created and timestamps_base["created_at"]:
            if otro_created < timestamps_base["created_at"]:
                timestamps_base["created_at"] = otro_created
        elif otro_created and not timestamps_base["created_at"]:
            timestamps_base["created_at"] = otro_created
        
        # Actualizar updated_at con la más reciente
        otro_updated = otro.get("updated_at")
        if otro_updated and timestamps_base["updated_at"]:
            if otro_updated > timestamps_base["updated_at"]:
                timestamps_base["updated_at"] = otro_updated
        elif otro_updated and not timestamps_base["updated_at"]:
            timestamps_base["updated_at"] = otro_updated
        
        for k, v in otro.items():
            if k in excluir:
                continue
            if base.get(k) in (None, "", 0) and v not in (None, "", 0):
                base[k] = v

    # Aplicar timestamps preservados
    base["created_at"] = timestamps_base["created_at"]
    base["updated_at"] = timestamps_base["updated_at"]

    existentes = base.get("exp_migrado") or ""
    lista_exist = [e.strip() for e in existentes.split(",") if e.strip()]
    todos = sorted(set(lista_exist + exp_migrados))
    base["exp_migrado"] = ",".join(todos) if todos else None
    return base


# ─────────────────────────────────────────────────────────────────────────────
# PASO 0 — RELLENAR CONSULTAS DESDE PACIENTES
# Copia nombre, apellido, sexo, dpi desde pacientes → consultas
# para registros que tienen expediente pero campos de paciente vacíos.
# Se ejecuta antes de cualquier limpieza para enriquecer los datos crudos.
# ─────────────────────────────────────────────────────────────────────────────

def paso_0_rellenar_consultas_desde_pacientes():
    titulo("PASO 0 — RELLENAR CONSULTAS DESDE PACIENTES")
    db = init_db()
    session = db["MySQLSession"]()

    try:
        # ── Obtener consultas con expediente pero sin datos de paciente ──
        info("Buscando consultas con expediente y campos vacíos...")
        consultas = session.execute(text("""
            SELECT id, expediente, nombres, apellidos, sexo, dpi
            FROM consultas
            WHERE expediente IS NOT NULL
              AND expediente != 0
              AND (
                  nombres   IS NULL OR TRIM(nombres)   = ''
               OR apellidos IS NULL OR TRIM(apellidos) = ''
               OR sexo      IS NULL OR TRIM(sexo)      = ''
               OR dpi       IS NULL OR dpi = 0
              )
        """)).mappings().all()

        total = len(consultas)
        info(f"{total:,} consultas candidatas encontradas")

        if total == 0:
            ok("Nada que actualizar.")
            return

        # ── Procesar cada consulta ───────────────────────────────────────
        actualizadas = 0
        sin_match    = 0

        for i, c in enumerate(consultas, 1):
            # Buscar el paciente por expediente
            paciente = session.execute(text("""
                SELECT nombre, apellido, sexo, dpi
                FROM pacientes
                WHERE expediente = :exp
                LIMIT 1
            """), {"exp": c["expediente"]}).mappings().fetchone()

            barra(i, total, prefijo="  Procesando ")

            if not paciente:
                sin_match += 1
                continue

            # Construir solo los campos que faltan en la consulta
            updates = {}

            if not c.get("nombres") or str(c["nombres"]).strip() == "":
                if paciente["nombre"]:
                    updates["nombres"] = paciente["nombre"]

            if not c.get("apellidos") or str(c["apellidos"]).strip() == "":
                if paciente["apellido"]:
                    updates["apellidos"] = paciente["apellido"]

            if not c.get("sexo") or str(c["sexo"]).strip() == "":
                if paciente["sexo"]:
                    updates["sexo"] = paciente["sexo"]

            if not c.get("dpi") or c["dpi"] == 0:
                if paciente["dpi"]:
                    updates["dpi"] = paciente["dpi"]

            if not updates:
                continue  # paciente tampoco tiene esos datos

            sets_sql = ", ".join([f"{col} = :{col}" for col in updates])
            updates["id"] = c["id"]

            session.execute(text(
                f"UPDATE consultas SET {sets_sql} WHERE id = :id"
            ), updates)
            actualizadas += 1

            # Commit cada 500 para no acumular transacción enorme
            if actualizadas % 500 == 0:
                session.commit()

        session.commit()
        ok(f"Consultas actualizadas : {actualizadas:>7,}")
        if sin_match:
            print(f"  ⚠ Sin match en pacientes : {sin_match:>7,} (expediente no existe)")
        ok("PASO 0 COMPLETADO")

    except Exception as e:
        session.rollback()
        print(f"\n  ✗ Error en PASO 0: {e}")
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# PASO 1 — LIMPIAR TABLA consultas
# ─────────────────────────────────────────────────────────────────────────────

def paso_1_limpiar_consultas():
    titulo("PASO 1 — LIMPIEZA DE CONSULTAS")
    db = init_db()
    session = db["MySQLSession"]()

    try:
        # Backup
        info("Creando backup consultas_backup...")
        session.execute(text(
            "CREATE TABLE IF NOT EXISTS consultas_backup AS SELECT * FROM consultas"
        ))
        session.commit()
        ok("Backup creado")

        # Normalizar collation de consultas para evitar mezclas
        info("Normalizando collation de consultas...")
        session.execute(text(
            "ALTER TABLE consultas CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
        session.commit()
        ok("Collation normalizado")

        # Eliminar registros sin nombre o apellido — son ruido puro
        info("Eliminando registros sin nombre o apellido...")
        r1 = session.execute(text("""
            DELETE FROM consultas
            WHERE nombres   IS NULL OR TRIM(nombres)   = ''
               OR apellidos IS NULL OR TRIM(apellidos) = ''
               OR TRIM(nombres)   = 'Anulado'
               OR TRIM(apellidos) = 'Anulado'
        """))
        session.commit()
        ok(f"Eliminados por nombre/apellido nulo: {r1.rowcount} registros")

        # Eliminar registros sin fecha de consulta
        info("Eliminando registros sin fecha de consulta...")
        r2 = session.execute(text("""
            DELETE FROM consultas
            WHERE fecha_consulta IS NULL
        """))
        session.commit()
        ok(f"Eliminados por fecha nula: {r2.rowcount} registros")

        # Normalizar espacios
        info("Normalizando espacios en nombres y apellidos...")
        espacios = limpiar_espacios_sql(session, "consultas", ["nombres", "apellidos"])
        ok(f"Espacios corregidos: {espacios}")

        # Normalizar DPI: quitar guiones/espacios, dejar solo dígitos
        info("Normalizando campo DPI...")
        session.execute(text("""
            UPDATE consultas
            SET dpi = REGEXP_REPLACE(TRIM(dpi), '[^0-9]', '')
            WHERE dpi IS NOT NULL AND dpi != ''
        """))
        session.execute(text("""
            UPDATE consultas SET dpi = NULL
            WHERE dpi = '' OR dpi = '0'
        """))
        session.commit()

        # Validar que DPI tenga exactamente 13 dígitos, sino → NULL
        info("Validando longitud DPI (debe ser exactamente 13 dígitos)...")
        r = session.execute(text("""
            UPDATE consultas
            SET dpi = NULL
            WHERE dpi IS NOT NULL
              AND (CHAR_LENGTH(dpi) != 13 OR dpi REGEXP '[^0-9]')
        """))
        session.commit()
        ok(f"DPI normalizado — {r.rowcount} registros con DPI inválido → NULL")

        # Convertir columna dpi de VARCHAR a BIGINT ahora que los datos están limpios
        info("Convirtiendo columna dpi a BIGINT...")
        session.execute(text("ALTER TABLE consultas MODIFY COLUMN dpi BIGINT NULL"))
        session.commit()
        ok("Columna dpi convertida a BIGINT en consultas")

        # Capitalizar
        info("Capitalizando nombres y apellidos...")
        n = capitalizar_python(session, "consultas", "id", ["nombres", "apellidos"])
        ok(f"Registros capitalizados: {n}")

        ok("PASO 1 COMPLETADO")

    except Exception as e:
        session.rollback()
        print(f"\n  ✗ Error en PASO 1: {e}")
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# PASO 2 — LIMPIAR TABLA pacientes
# ─────────────────────────────────────────────────────────────────────────────

def paso_2_limpiar_pacientes():
    titulo("PASO 2 — LIMPIEZA DE PACIENTES")
    db = init_db()
    session = db["MySQLSession"]()

    try:
        info("Creando backup pacientes_backup...")
        session.execute(text(
            "CREATE TABLE IF NOT EXISTS pacientes_backup AS SELECT * FROM pacientes"
        ))
        session.commit()
        ok("Backup creado")

        # Normalizar collation de pacientes para evitar mezclas
        info("Normalizando collation de pacientes...")
        session.execute(text(
            "ALTER TABLE pacientes CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
        session.commit()
        ok("Collation normalizado")

        info("Eliminando pacientes sin nombre o apellido...")
        r = session.execute(text("""
            DELETE FROM pacientes
            WHERE nombre   IS NULL OR TRIM(nombre)   = ''
               OR apellido IS NULL OR TRIM(apellido) = ''
        """))
        session.commit()
        ok(f"Eliminados: {r.rowcount} registros sin nombre/apellido")

        info("Normalizando espacios...")
        espacios = limpiar_espacios_sql(session, "pacientes", ["nombre", "apellido"])
        ok(f"Espacios corregidos: {espacios}")

        # Normalizar DPI
        info("Normalizando DPI...")
        session.execute(text("""
            UPDATE pacientes
            SET dpi = REGEXP_REPLACE(TRIM(CAST(dpi AS CHAR)), '[^0-9]', '')
            WHERE dpi IS NOT NULL AND dpi != 0
        """))
        session.execute(text("""
            UPDATE pacientes SET dpi = NULL WHERE dpi = 0
        """))
        session.commit()

        # Validar que DPI tenga exactamente 13 dígitos, sino → NULL
        info("Validando longitud DPI (debe ser exactamente 13 dígitos)...")
        r = session.execute(text("""
            UPDATE pacientes
            SET dpi = NULL
            WHERE dpi IS NOT NULL
              AND (CHAR_LENGTH(CAST(dpi AS CHAR)) != 13)
        """))
        session.commit()
        ok(f"DPI normalizado — {r.rowcount} registros con DPI inválido → NULL")

        info("Capitalizando...")
        n = capitalizar_python(session, "pacientes", "id", ["nombre", "apellido"])
        ok(f"Registros capitalizados: {n}")

        ok("PASO 2 COMPLETADO")

    except Exception as e:
        session.rollback()
        print(f"\n  ✗ Error en PASO 2: {e}")
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES DE AUDITORÍA — MERGE LOG
# Deben definirse ANTES de paso_3 porque ejecutar_merge las llama.
# ─────────────────────────────────────────────────────────────────────────────

def _crear_merge_log(session) -> None:
    """
    Crea la tabla de auditoría pacientes_merge_log si no existe.
      id_eliminado         — id del registro borrado de pacientes_clean
      id_sobreviviente     — id del registro que absorbió al eliminado
      expediente_eliminado — expediente del registro borrado (trazabilidad)
      expediente_sobreviviente — expediente del ganador
      criterio             — 'expediente' | 'dpi_nombre' | 'nombre_nacimiento'
      fusionado_en         — timestamp del merge
    """
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS pacientes_merge_log (
            id                       INT AUTO_INCREMENT PRIMARY KEY,
            id_eliminado             INT NOT NULL,
            id_sobreviviente         INT NOT NULL,
            expediente_eliminado     INT,
            expediente_sobreviviente INT,
            criterio                 VARCHAR(30),
            fusionado_en             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_eliminado      (id_eliminado),
            INDEX idx_sobreviviente  (id_sobreviviente),
            INDEX idx_exp_elim       (expediente_eliminado)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """))
    session.commit()


def _registrar_merge(session, ganador: dict, perdedores: list[dict],
                     criterio: str) -> None:
    """Inserta una fila en pacientes_merge_log por cada perdedor."""
    for p in perdedores:
        session.execute(text("""
            INSERT INTO pacientes_merge_log
                (id_eliminado, id_sobreviviente,
                 expediente_eliminado, expediente_sobreviviente, criterio)
            VALUES
                (:id_elim, :id_surv, :exp_elim, :exp_surv, :criterio)
        """), {
            "id_elim":  p["id"],
            "id_surv":  ganador["id"],
            "exp_elim": p.get("expediente"),
            "exp_surv": ganador.get("expediente"),
            "criterio": criterio,
        })


# ─────────────────────────────────────────────────────────────────────────────
# PASO 3 — DEDUPLICAR Y COMBINAR pacientes → pacientes_clean
# ─────────────────────────────────────────────────────────────────────────────

def paso_3_deduplicar_pacientes():
    titulo("PASO 3 — DEDUPLICAR PACIENTES → pacientes_clean")
    db = init_db()
    session = db["MySQLSession"]()

    EXCLUIR = {"id"}

    def ejecutar_merge(registros: list, criterio: str = "desconocido") -> None:
        if len(registros) < 2:
            return
        base = dict(registros[0])
        otros = [dict(r) for r in registros[1:]]
        base = merge_campos(base, otros, excluir=EXCLUIR)

        campos_up = [k for k in base if k not in EXCLUIR]
        sets_sql = ", ".join([f"{k} = :{k}" for k in campos_up])
        params = {k: base[k] for k in campos_up}
        params["id"] = base["id"]
        session.execute(text(f"UPDATE pacientes_clean SET {sets_sql} WHERE id = :id"), params)

        # ── Registrar en el log ANTES de borrar ──────────────────────────
        # Así queda trazabilidad de qué id absorbió a quién y con qué criterio.
        _registrar_merge(session, base, otros, criterio)

        ids_borrar = [str(o["id"]) for o in otros]
        if ids_borrar:
            session.execute(text(
                f"DELETE FROM pacientes_clean WHERE id IN ({','.join(ids_borrar)})"
            ))

    try:
        # Crear / limpiar tabla de auditoría de merges
        info("Preparando tabla pacientes_merge_log...")
        session.execute(text("DROP TABLE IF EXISTS pacientes_merge_log"))
        session.commit()
        _crear_merge_log(session)
        ok("pacientes_merge_log lista")

        # Recrear tabla
        info("Recreando pacientes_clean...")
        session.execute(text("DROP TABLE IF EXISTS pacientes_clean"))
        session.commit()
        session.execute(text("CREATE TABLE pacientes_clean LIKE pacientes"))
        session.execute(text(
            "ALTER TABLE pacientes_clean CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
        session.execute(text(
            "ALTER TABLE pacientes_clean ADD COLUMN exp_migrado VARCHAR(255) NULL"
        ))
        # Columna para DPIs duplicados detectados entre registros distintos
        session.execute(text(
            "ALTER TABLE pacientes_clean ADD COLUMN cui_duplicado VARCHAR(255) NULL"
        ))
        session.commit()

        session.execute(text("""
            INSERT INTO pacientes_clean
            SELECT *, NULL AS exp_migrado, NULL AS cui_duplicado FROM pacientes
        """))
        session.commit()
        ok("Tabla pacientes_clean creada y cargada")

        # ── Fase A: por expediente ────────────────────────────────────────
        info("Fase A: deduplicar por expediente...")
        grupos = session.execute(text("""
            SELECT expediente, COUNT(*) total
            FROM pacientes_clean
            WHERE expediente IS NOT NULL
            GROUP BY expediente HAVING total > 1
        """)).fetchall()

        for i, (exp, _) in enumerate(grupos, 1):
            registros = session.execute(text("""
                SELECT * FROM pacientes_clean
                WHERE expediente = :exp ORDER BY id DESC
            """), {"exp": exp}).mappings().all()
            ejecutar_merge(list(registros), criterio="expediente")
            barra(i, len(grupos), prefijo="  Fase A ")

        session.commit()
        ok(f"Fase A: {len(grupos)} grupos unificados")

        # ── Fase B: por DPI + nombre + apellido + nacimiento ─────────────
        info("Fase B: deduplicar por DPI + nombre + nacimiento...")
        grupos = session.execute(text("""
            SELECT dpi, nombre, apellido, nacimiento, COUNT(*) total
            FROM pacientes_clean
            WHERE dpi IS NOT NULL AND dpi != 0
            GROUP BY dpi, nombre, apellido, nacimiento HAVING total > 1
        """)).fetchall()

        for i, (dpi, nombre, apellido, nac, _) in enumerate(grupos, 1):
            registros = session.execute(text("""
                SELECT * FROM pacientes_clean
                WHERE dpi = :dpi AND nombre = :nombre
                  AND apellido = :apellido AND nacimiento <=> :nac
                ORDER BY expediente DESC
            """), {"dpi": dpi, "nombre": nombre, "apellido": apellido, "nac": nac}).mappings().all()
            ejecutar_merge(list(registros), criterio="dpi_nombre")
            barra(i, len(grupos), prefijo="  Fase B ")

        session.commit()
        ok(f"Fase B: {len(grupos)} grupos unificados")

        # ── Fase C: por nombre + apellido + nacimiento (sin DPI) ─────────
        info("Fase C: deduplicar por nombre + apellido + nacimiento (sin DPI)...")
        grupos = session.execute(text("""
            SELECT nombre, apellido, nacimiento, COUNT(*) total
            FROM pacientes_clean
            WHERE dpi IS NULL OR dpi = 0
            GROUP BY nombre, apellido, nacimiento HAVING total > 1
        """)).fetchall()

        for i, (nombre, apellido, nac, _) in enumerate(grupos, 1):
            registros = session.execute(text("""
                SELECT * FROM pacientes_clean
                WHERE (dpi IS NULL OR dpi = 0)
                  AND nombre = :nombre AND apellido = :apellido
                  AND nacimiento <=> :nac
                ORDER BY expediente DESC
            """), {"nombre": nombre, "apellido": apellido, "nac": nac}).mappings().all()
            ejecutar_merge(list(registros), criterio="nombre_nacimiento")
            barra(i, len(grupos), prefijo="  Fase C ")

        session.commit()
        ok(f"Fase C: {len(grupos)} grupos unificados")

        # ── Fase D: DPI compartido entre pacientes DISTINTOS ─────────────
        # Un DPI aparece en 2+ registros con distinto nombre/nacimiento.
        # → El que tiene expediente mayor (o id mayor) conserva el DPI.
        # → Los demás: su DPI se mueve a cui_duplicado y se borra de dpi.
        info("Fase D: detectar DPI compartido entre pacientes distintos...")
        grupos_dpi = session.execute(text("""
            SELECT dpi, COUNT(*) total
            FROM pacientes_clean
            WHERE dpi IS NOT NULL AND dpi != 0
            GROUP BY dpi HAVING total > 1
        """)).fetchall()

        marcados = 0
        for i, (dpi, _) in enumerate(grupos_dpi, 1):
            registros = session.execute(text("""
                SELECT id, expediente, cui_duplicado
                FROM pacientes_clean
                WHERE dpi = :dpi
                ORDER BY
                    CASE WHEN expediente IS NOT NULL THEN 0 ELSE 1 END ASC,
                    expediente DESC,
                    id DESC
            """), {"dpi": dpi}).mappings().all()

            if len(registros) < 2:
                continue

            # El primero conserva el DPI; el resto lo pierde
            for reg in registros[1:]:
                # Acumular en cui_duplicado (puede ya tener valores)
                existentes = reg["cui_duplicado"] or ""
                lista = [x.strip() for x in existentes.split(",") if x.strip()]
                if str(dpi) not in lista:
                    lista.append(str(dpi))
                nuevo_cui_dup = ",".join(lista)

                session.execute(text("""
                    UPDATE pacientes_clean
                    SET dpi = NULL,
                        cui_duplicado = :cui_dup
                    WHERE id = :id
                """), {"cui_dup": nuevo_cui_dup, "id": reg["id"]})
                marcados += 1

            barra(i, len(grupos_dpi), prefijo="  Fase D ")

        session.commit()
        ok(f"Fase D: {len(grupos_dpi)} DPIs duplicados — {marcados} registros marcados (dpi→NULL, cui_duplicado actualizado)")

        total = session.execute(text("SELECT COUNT(*) FROM pacientes_clean")).scalar()
        ok(f"PASO 3 COMPLETADO — pacientes_clean tiene {total} registros únicos")

    except Exception as e:
        session.rollback()
        print(f"\n  ✗ Error en PASO 3: {e}")
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# PASO 3b — REPARAR RELACIONES EN consultas USANDO EL MERGE LOG
# Actualiza consultas.expediente para que apunte siempre al
# expediente del paciente sobreviviente tras la deduplicación.
# ─────────────────────────────────────────────────────────────────────────────

def paso_3b_reparar_consultas_post_merge():
    """
    Problema que resuelve:
      Durante el Paso 3, registros de pacientes_clean fueron eliminados y
      absorbidos por un ganador. Si el eliminado tenía un expediente distinto
      al del ganador, las consultas que referenciaban ese expediente quedan
      huérfanas. Este paso usa pacientes_merge_log para redirigirlas.

    Garantías:
      - Solo actualiza cuando el sobreviviente tiene expediente válido y
        distinto al eliminado.
      - Si el sobreviviente no tenía expediente, la consulta se deja intacta.
      - El log queda intacto para auditoría posterior.
    """
    titulo("PASO 3b — REPARAR CONSULTAS POST-MERGE")
    db = init_db()
    session = db["MySQLSession"]()

    try:
        total_log = session.execute(text(
            "SELECT COUNT(*) FROM pacientes_merge_log"
        )).scalar()
        info(f"pacientes_merge_log tiene {total_log:,} registros de merge")

        if total_log == 0:
            ok("No hubo merges — nada que reparar.")
            return

        # ── 1) Consultas con expediente que fue eliminado en el merge ─────
        afectadas = session.execute(text("""
            SELECT
                c.id                             AS consulta_id,
                c.expediente                     AS exp_actual,
                ml.expediente_sobreviviente      AS exp_nuevo,
                ml.criterio
            FROM consultas c
            INNER JOIN pacientes_merge_log ml
                ON c.expediente = ml.expediente_eliminado
            WHERE ml.expediente_sobreviviente IS NOT NULL
              AND ml.expediente_sobreviviente != ml.expediente_eliminado
              AND NOT EXISTS (
                  SELECT 1 FROM pacientes_clean pc
                  WHERE pc.expediente = c.expediente
              )
        """)).mappings().all()

        total_afectadas = len(afectadas)
        info(f"Consultas con expediente huérfano: {total_afectadas:,}")

        if total_afectadas == 0:
            ok("Ninguna consulta quedó huérfana — relaciones íntegras.")
            return

        # ── 2) Actualizar expediente en consultas ─────────────────────────
        actualizadas = 0
        for i, row in enumerate(afectadas, 1):
            session.execute(text("""
                UPDATE consultas
                SET expediente = :exp_nuevo
                WHERE id = :consulta_id
                  AND expediente = :exp_actual
            """), {
                "exp_nuevo":   row["exp_nuevo"],
                "consulta_id": row["consulta_id"],
                "exp_actual":  row["exp_actual"],
            })
            actualizadas += 1
            if actualizadas % 500 == 0:
                session.commit()
            barra(i, total_afectadas, prefijo="  Actualizando ")

        session.commit()
        ok(f"Consultas reparadas: {actualizadas:,}")

        # ── 3) Reportar huérfanas irresolubles (sobreviviente sin expediente) ─
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
            print(f"\n  ⚠ {huerfanas:,} consultas cuyo sobreviviente no tenía expediente.")
            print(f"    Se mantiene su expediente original como referencia histórica.")
            print(f"    Para revisión manual:")
            print(f"      SELECT c.id, c.expediente, ml.* FROM consultas c")
            print(f"      JOIN pacientes_merge_log ml ON c.expediente = ml.expediente_eliminado")
            print(f"      WHERE ml.expediente_sobreviviente IS NULL;")

        ok("PASO 3b COMPLETADO")

    except Exception as e:
        session.rollback()
        print(f"\n  ✗ Error en PASO 3b: {e}")
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# PASO 4 — EXTRAER PACIENTES NUEVOS DE consultas → pacientes_nuevos
# Pacientes que están en consultas pero NO en pacientes_clean
# ─────────────────────────────────────────────────────────────────────────────

def paso_4_pacientes_nuevos_de_consultas():
    titulo("PASO 4 — EXTRAER PACIENTES NUEVOS DE CONSULTAS")
    db = init_db()
    session = db["MySQLSession"]()

    try:
        # Recrear tabla de trabajo
        info("Recreando tabla pacientes_nuevos...")
        session.execute(text("DROP TABLE IF EXISTS pacientes_nuevos"))
        session.commit()
        session.execute(text("""
            CREATE TABLE pacientes_nuevos (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                expediente  INT,
                nombres     VARCHAR(50),
                apellidos   VARCHAR(50),
                nacimiento  DATE,
                sexo        VARCHAR(1),
                dpi         BIGINT,
                telefono    VARCHAR(50),
                direccion   VARCHAR(100),
                hojas_emergencia TEXT,
                created_at TIMESTAMP NULL,
                updated_at TIMESTAMP NULL
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
        session.commit()
        ok("Tabla pacientes_nuevos creada")

        # Agregar candidatos desde consultas (agrupados por expediente)
        info("Fase 1: candidatos por expediente...")
        session.execute(text("SET SESSION group_concat_max_len = 1000000"))
        session.execute(text("""
            INSERT INTO pacientes_nuevos
                (expediente, nombres, apellidos, nacimiento, sexo, dpi,
                 telefono, direccion, hojas_emergencia, created_at, updated_at)
            SELECT
                expediente,
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
        ok("Fase 1 completada")

        # Agregar candidatos sin expediente (por nombre+apellido+nacimiento+dpi)
        info("Fase 2: candidatos por nombre + DPI...")
        grupos = session.execute(text("""
            SELECT nombres, apellidos, nacimiento, dpi,
                   MIN(created_at) AS min_created, MAX(updated_at) AS max_updated,
                   GROUP_CONCAT(DISTINCT hoja_emergencia) AS hojas
            FROM consultas
            WHERE expediente IS NULL AND dpi IS NOT NULL
            GROUP BY nombres, apellidos, nacimiento, dpi
        """)).mappings().all()

        for i, g in enumerate(grupos, 1):
            existe = session.execute(text("""
                SELECT id FROM pacientes_nuevos
                WHERE nombres = :nombres AND apellidos = :apellidos
                  AND nacimiento <=> :nacimiento AND dpi = :dpi
                LIMIT 1
            """), g).fetchone()
            if not existe:
                session.execute(text("""
                    INSERT INTO pacientes_nuevos
                        (nombres, apellidos, nacimiento, dpi, hojas_emergencia,
                         created_at, updated_at)
                    VALUES (:nombres, :apellidos, :nacimiento, NULLIF(CAST(:dpi AS UNSIGNED), 0),
                            :hojas, :min_created, :max_updated)
                """), g)
            barra(i, len(grupos), prefijo="  Fase 2 ")
        session.commit()
        ok(f"Fase 2: {len(grupos)} grupos procesados")

        # Agregar candidatos solo por nombre+apellido+nacimiento
        # PROTECCIÓN: solo se agrupa si nacimiento NO es null (evita colapsar
        # varios "Juan Pérez" sin fecha en un solo registro fantasma)
        info("Fase 3: candidatos por nombre + nacimiento (sin DPI)...")
        grupos = session.execute(text("""
            SELECT nombres, apellidos, nacimiento,
                   COUNT(*) AS total_consultas,
                   MIN(created_at) AS min_created, MAX(updated_at) AS max_updated,
                   NULLIF(GROUP_CONCAT(DISTINCT hoja_emergencia
                          ORDER BY hoja_emergencia SEPARATOR ','), '') AS hojas
            FROM consultas
            WHERE expediente IS NULL
              AND (dpi IS NULL OR dpi = '0')
              AND nacimiento IS NOT NULL
            GROUP BY nombres, apellidos, nacimiento
        """)).mappings().all()

        ambiguos = 0
        for i, g in enumerate(grupos, 1):
            # Si hay más de 5 consultas distintas para nombre+nacimiento sin DPI
            # es sospechoso — se inserta igual pero se advierte
            if g["total_consultas"] > 5:
                ambiguos += 1

            existe = session.execute(text("""
                SELECT id FROM pacientes_nuevos
                WHERE nombres = :nombres AND apellidos = :apellidos
                  AND nacimiento <=> :nacimiento
                LIMIT 1
            """), g).fetchone()
            if not existe:
                session.execute(text("""
                    INSERT INTO pacientes_nuevos
                        (nombres, apellidos, nacimiento, hojas_emergencia,
                         created_at, updated_at)
                    VALUES (:nombres, :apellidos, :nacimiento, :hojas,
                            :min_created, :max_updated)
                """), g)
            barra(i, len(grupos), prefijo="  Fase 3 ")
        session.commit()
        if ambiguos:
            print(f"\n  ⚠ {ambiguos} grupos con >5 consultas sin DPI — revisar manualmente")
        ok(f"Fase 3: {len(grupos)} grupos procesados")

        # ── Filtrar: quitar los que YA existen en pacientes_clean ─────────
        info("Eliminando de pacientes_nuevos los que ya están en pacientes_clean...")

        # Por expediente
        session.execute(text("""
            DELETE pn FROM pacientes_nuevos pn
            INNER JOIN pacientes_clean pc ON pn.expediente = pc.expediente
            WHERE pn.expediente IS NOT NULL
        """))

        # Por DPI + nombre + nacimiento (ambos BIGINT — comparación directa)
        session.execute(text("""
            DELETE pn FROM pacientes_nuevos pn
            INNER JOIN pacientes_clean pc
              ON pn.dpi        = pc.dpi
             AND pn.nombres    = pc.nombre
             AND pn.apellidos  = pc.apellido
             AND pn.nacimiento <=> pc.nacimiento
            WHERE pn.dpi IS NOT NULL
        """))

        # Por nombre + apellido + nacimiento
        session.execute(text("""
            DELETE pn FROM pacientes_nuevos pn
            INNER JOIN pacientes_clean pc
              ON pn.nombres   = pc.nombre
             AND pn.apellidos = pc.apellido
             AND pn.nacimiento <=> pc.nacimiento
        """))

        session.commit()

        total = session.execute(text("SELECT COUNT(*) FROM pacientes_nuevos")).scalar()
        ok(f"PASO 4 COMPLETADO — {total} pacientes nuevos (no estaban en pacientes)")

    except Exception as e:
        session.rollback()
        print(f"\n  ✗ Error en PASO 4: {e}")
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDAD — GARANTIZAR UNICIDAD DE DPI EN CUALQUIER TABLA
# Regla: de cada grupo con el mismo DPI, el primer registro (según prioridad)
# conserva el DPI; TODOS los demás reciben dpi=NULL y su DPI se acumula en
# cui_duplicado.  Itera hasta convergencia total (0 duplicados restantes).
# ─────────────────────────────────────────────────────────────────────────────

def _limpiar_dpi_duplicados(session, tabla: str) -> None:
    """
    Garantiza que no haya dos filas con el mismo dpi != NULL en `tabla`.

    Para cada grupo duplicado:
      - Conserva el DPI en el registro con mayor prioridad:
          1. fuente = 'pacientes'  con expediente  (expediente DESC)
          2. fuente = 'pacientes'  sin expediente
          3. fuente = 'consultas'  con expediente  (expediente DESC)
          4. fuente = 'consultas'  sin expediente
          5. id DESC como desempate final
      - En TODOS los demás: dpi → NULL, el valor se acumula en cui_duplicado.

    Itera en rondas hasta que no quede ningún duplicado (convergencia total).
    """
    titulo(f"LIMPIEZA DE DPI DUPLICADOS — {tabla}")

    ronda = 0
    total_marcados = 0

    while True:
        ronda += 1

        # Obtener todos los DPIs que aún están duplicados
        grupos = session.execute(text(f"""
            SELECT dpi, COUNT(*) AS total
            FROM {tabla}
            WHERE dpi IS NOT NULL
            GROUP BY dpi
            HAVING COUNT(*) > 1
        """)).fetchall()

        if not grupos:
            break

        info(f"Ronda {ronda}: {len(grupos)} DPIs duplicados detectados")
        marcados_ronda = 0

        for i, (dpi, _) in enumerate(grupos, 1):
            # Obtener todos los registros con este DPI ordenados por prioridad
            # Se usa COALESCE para tablas que no tengan columna 'fuente'
            registros = session.execute(text(f"""
                SELECT id,
                       COALESCE(expediente, 0)                         AS _exp,
                       COALESCE(fuente, '')                            AS _fuente,
                       cui_duplicado,
                       created_at,
                       updated_at
                FROM {tabla}
                WHERE dpi = :dpi
                ORDER BY
                    CASE COALESCE(fuente, '')
                        WHEN 'pacientes' THEN 0
                        WHEN 'consultas' THEN 1
                        ELSE 2
                    END ASC,
                    CASE WHEN expediente IS NOT NULL THEN 0 ELSE 1 END ASC,
                    COALESCE(expediente, 0) DESC,
                    id DESC
            """), {"dpi": dpi}).mappings().all()

            if len(registros) < 2:
                # Ya no está duplicado en esta ronda (puede haber sido resuelto
                # por un commit anterior dentro del mismo loop)
                continue

            # El primero conserva el DPI — TODOS los demás lo pierden
            for reg in registros[1:]:
                existentes = reg["cui_duplicado"] or ""
                lista = [x.strip() for x in existentes.split(",") if x.strip()]
                dpi_str = str(dpi)
                if dpi_str not in lista:
                    lista.append(dpi_str)
                nuevo_cui_dup = ",".join(lista)

                session.execute(text(f"""
                    UPDATE {tabla}
                    SET    dpi          = NULL,
                           cui_duplicado = :cui_dup
                    WHERE  id = :id
                """), {"cui_dup": nuevo_cui_dup, "id": reg["id"]})
                marcados_ronda += 1

            barra(i, len(grupos), prefijo=f"  Ronda {ronda} ")

        session.commit()
        total_marcados += marcados_ronda
        ok(f"Ronda {ronda}: {marcados_ronda} registros corregidos (dpi→NULL, cui_duplicado actualizado)")

    # Verificación final inapelable
    restantes = session.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT dpi FROM {tabla}
            WHERE dpi IS NOT NULL
            GROUP BY dpi HAVING COUNT(*) > 1
        ) AS sub
    """)).scalar()

    if restantes == 0:
        ok(f"✓ Cero DPIs duplicados en {tabla} — listo para PostgreSQL UNIQUE  "
           f"(total corregidos: {total_marcados})")
    else:
        # Esto no debería ocurrir nunca, pero si ocurre lo reportamos claro
        print(f"\n  ✗ CRÍTICO: aún quedan {restantes} DPIs duplicados en {tabla} "
              f"tras {ronda} rondas — revisar datos manualmente")
        raise RuntimeError(
            f"{restantes} DPIs duplicados no resueltos en {tabla}. "
            "Posible causa: registros con id o fuente NULL que rompen el ORDER BY."
        )


# ─────────────────────────────────────────────────────────────────────────────
# PASO 5 — CONSTRUIR pacientes_master
# Une pacientes_clean + pacientes_nuevos
# Incluye fase 5b: garantizar unicidad de DPI para compatibilidad con
# el UNIQUE constraint de PostgreSQL (dpi duplicados → NULL + cui_duplicado)
# ─────────────────────────────────────────────────────────────────────────────

def paso_5_construir_master():
    titulo("PASO 5 — CONSTRUIR pacientes_master")
    db = init_db()
    session = db["MySQLSession"]()

    try:
        info("Recreando pacientes_master...")
        session.execute(text("DROP TABLE IF EXISTS pacientes_master"))
        session.commit()
        session.execute(text("""
            CREATE TABLE pacientes_master (
                id               INT AUTO_INCREMENT PRIMARY KEY,
                expediente       INT,
                nombre           VARCHAR(50),
                apellido         VARCHAR(50),
                nacimiento       DATE,
                sexo             VARCHAR(2),
                dpi              BIGINT,
                pasaporte        VARCHAR(50),
                nacionalidad     INT,
                lugar_nacimiento INT,
                depto_nac        INT,
                estado_civil     INT,
                educacion        INT,
                pueblo           INT,
                idioma           INT,
                ocupacion        VARCHAR(50),
                direccion        VARCHAR(100),
                municipio        INT,
                depto            INT,
                telefono         VARCHAR(50),
                email            VARCHAR(100),
                padre            VARCHAR(50),
                madre            VARCHAR(50),
                responsable      VARCHAR(50),
                parentesco       INT,
                dpi_responsable  BIGINT,
                telefono_responsable INT,
                estado           VARCHAR(2),
                exp_madre        INT,
                gemelo           VARCHAR(2),
                conyugue         VARCHAR(100),
                exp_ref          INT,
                created_by       VARCHAR(8),
                fechaDefuncion   VARCHAR(10),
                hora_defuncion   TIME,
                exp_migrado      VARCHAR(255),
                hojas_emergencia TEXT,
                cui_duplicado    VARCHAR(255),      -- DPIs desplazados por unicidad
                fuente           VARCHAR(20),        -- 'pacientes' | 'consultas'
                created_at TIMESTAMP NULL,
                updated_at TIMESTAMP NULL
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
        session.commit()
        ok("Tabla creada")

        # ── Insertar desde pacientes_clean ───────────────────────────────
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
                cui_duplicado, 'pacientes', created_at, updated_at
            FROM pacientes_clean
        """))
        session.commit()
        n_clean = session.execute(text("SELECT COUNT(*) FROM pacientes_master")).scalar()
        ok(f"Insertados desde pacientes_clean: {n_clean}")

        # ── Insertar desde pacientes_nuevos ──────────────────────────────
        info("Insertando desde pacientes_nuevos...")
        session.execute(text("""
            INSERT INTO pacientes_master (
                expediente, nombre, apellido, nacimiento, sexo,
                dpi, telefono, direccion, hojas_emergencia, fuente,
                created_at, updated_at
            )
            SELECT
                expediente, nombres, apellidos, nacimiento, sexo, dpi, telefono,
                direccion, hojas_emergencia, 'consultas', created_at, updated_at
            FROM pacientes_nuevos
            """))
        session.commit()

        total_antes = session.execute(text("SELECT COUNT(*) FROM pacientes_master")).scalar()
        ok(f"Total tras inserción: {total_antes} registros")

        # ── Fase 5b: garantizar unicidad de DPI ──────────────────────────
        _limpiar_dpi_duplicados(session, "pacientes_master")

        total = session.execute(text("SELECT COUNT(*) FROM pacientes_master")).scalar()
        ok(f"PASO 5 COMPLETADO — pacientes_master: {total} registros")

    except Exception as e:
        session.rollback()
        print(f"\n  ✗ Error en PASO 5: {e}")
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# PASO 6 — CREAR consultas_master CON paciente_id
# Orden de match: 1) expediente  2) nombre+apellido+DPI
#                 3) nombre+apellido+nacimiento  4) sin coincidencia → NULL
# ─────────────────────────────────────────────────────────────────────────────

def paso_6_crear_consultas_master():
    titulo("PASO 6 — CREAR consultas_master")
    db = init_db()
    session = db["MySQLSession"]()

    try:
        info("Recreando consultas_master...")
        session.execute(text("DROP TABLE IF EXISTS consultas_master"))
        session.commit()
        session.execute(text("""
            CREATE TABLE consultas_master (
                id                  INT AUTO_INCREMENT PRIMARY KEY,
                consulta_id         INT,
                paciente_id         INT,           -- FK a pacientes_master
                match_criterio      VARCHAR(30),   -- cómo se encontró el paciente

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
                reserva             TINYINT(1)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
        session.commit()
        ok("Tabla consultas_master creada")

        # Cargar todas las consultas
        consultas = session.execute(text("SELECT * FROM consultas")).mappings().all()
        total = len(consultas)
        info(f"Procesando {total} consultas...")

        # Contadores de criterio
        stats = {"expediente": 0, "nombre_dpi": 0, "nombre_nacimiento": 0, "unico_consulta": 0, "creado_directo": 0, "sin_match": 0}

        COLS_CONSULTA = [
            "hoja_emergencia", "expediente", "fecha_consulta", "hora",
            "nombres", "apellidos", "nacimiento", "edad", "sexo", "dpi",
            "direccion", "telefono", "acompa", "parente", "nota",
            "especialidad", "servicio", "status", "fecha_egreso",
            "fecha_recepcion", "tipo_consulta", "prenatal", "lactancia",
            "dx", "folios", "medico", "created_at", "updated_at",
            "archived_by", "created_by", "consulta_por",
            "bomberos", "transito", "arma_blanca", "arma_fuego",
            "estudiante_publica", "accidente_laboral", "personal_hospital", "reserva",
        ]

        for i, c in enumerate(consultas, 1):
            paciente_id = None
            criterio = "sin_match"

            # ── 1) Por expediente ─────────────────────────────────────────
            if c["expediente"]:
                row = session.execute(text("""
                    SELECT id FROM pacientes_master
                    WHERE expediente = :exp
                    LIMIT 1
                """), {"exp": c["expediente"]}).fetchone()
                if row:
                    paciente_id = row[0]
                    criterio = "expediente"

            # ── 2) Por nombre + apellido + DPI ────────────────────────────
            # Ambas tablas tienen dpi BIGINT — comparación directa sin CAST
            if not paciente_id and c["dpi"] and c["nombres"] and c["apellidos"]:
                row = session.execute(text("""
                    SELECT id FROM pacientes_master
                    WHERE nombre   = :nombres
                      AND apellido = :apellidos
                      AND dpi = :dpi
                    LIMIT 1
                """), {
                    "nombres": c["nombres"],
                    "apellidos": c["apellidos"],
                    "dpi": int(c["dpi"]),
                }).fetchone()
                if row:
                    paciente_id = row[0]
                    criterio = "nombre_dpi"

            # ── 3) Por nombre + apellido + nacimiento ─────────────────────
            # nacimiento se castea explícitamente a DATE para evitar
            # comparaciones string vs DATE que siempre devuelven 0
            if not paciente_id and c["nombres"] and c["apellidos"]:
                nac = c["nacimiento"]
                row = session.execute(text("""
                    SELECT id FROM pacientes_master
                    WHERE nombre     = :nombres
                      AND apellido   = :apellidos
                      AND nacimiento <=> CAST(:nac AS DATE)
                    LIMIT 1
                """), {
                    "nombres": c["nombres"],
                    "apellidos": c["apellidos"],
                    "nac": str(nac) if nac else None,
                }).fetchone()
                if row:
                    paciente_id = row[0]
                    criterio = "nombre_nacimiento"

            # ── 4) Registro único — busca en pacientes_master fuente=consultas ─
            # El paso 4 ya insertó estos registros en pacientes_master.
            # Primero intenta con nacimiento, si es NULL busca solo por nombre.
            if not paciente_id and c["nombres"] and c["apellidos"]:
                nac = c["nacimiento"]

                if nac:
                    # Con nacimiento — búsqueda precisa
                    row = session.execute(text("""
                        SELECT id FROM pacientes_master
                        WHERE fuente     = 'consultas'
                          AND nombre     = :nombres
                          AND apellido   = :apellidos
                          AND nacimiento = CAST(:nac AS DATE)
                        LIMIT 1
                    """), {
                        "nombres": c["nombres"],
                        "apellidos": c["apellidos"],
                        "nac": str(nac),
                    }).fetchone()
                else:
                    # Sin nacimiento — solo nombre + apellido + nacimiento NULL
                    row = session.execute(text("""
                        SELECT id FROM pacientes_master
                        WHERE fuente       = 'consultas'
                          AND nombre       = :nombres
                          AND apellido     = :apellidos
                          AND nacimiento IS NULL
                        LIMIT 1
                    """), {
                        "nombres": c["nombres"],
                        "apellidos": c["apellidos"],
                    }).fetchone()

                if row:
                    paciente_id = row[0]
                    criterio = "unico_consulta"

            # ── 5) Crear paciente en el momento — con deduplicación por DPI ─
            # Antes de insertar, verificar si el DPI ya existe en
            # pacientes_master. Si existe, reutilizar ese registro para evitar
            # crear un duplicado que bloquearía el UNIQUE de PostgreSQL.
            if not paciente_id and c["nombres"] and c["apellidos"]:

                # 5a) Búsqueda defensiva por DPI antes de insertar
                if c["dpi"]:
                    row = session.execute(text("""
                        SELECT id FROM pacientes_master
                        WHERE dpi = :dpi
                        LIMIT 1
                    """), {"dpi": int(c["dpi"])}).fetchone()
                    if row:
                        paciente_id = row[0]
                        criterio = "creado_directo"

                # 5b) Si no se encontró por DPI, crear registro nuevo
                if not paciente_id:
                    ins = session.execute(text("""
                        INSERT INTO pacientes_master
                            (nombre, apellido, nacimiento, sexo, dpi,
                             telefono, direccion, fuente, created_at, updated_at)
                        VALUES
                            (:nombres, :apellidos, :nac, :sexo, :dpi,
                             :telefono, :direccion, 'consulta_directa',
                             :created_at, :updated_at)
                    """), {
                        "nombres":   c["nombres"],
                        "apellidos": c["apellidos"],
                        "nac":       c["nacimiento"],
                        "sexo":      c["sexo"],
                        "dpi":       int(c["dpi"]) if c["dpi"] else None,
                        "telefono":  c["telefono"],
                        "direccion": c["direccion"],
                        "created_at": c["created_at"],
                        "updated_at": c["updated_at"],
                    })
                    paciente_id = ins.lastrowid
                    criterio = "creado_directo"

            # ── 6) Sin coincidencia real ──────────────────────────────────
            stats[criterio if criterio in stats else "sin_match"] += 1

            # Construir fila
            data = {col: c[col] for col in COLS_CONSULTA if col in c.keys()}
            data["consulta_id"] = c["id"]
            data["paciente_id"] = paciente_id
            data["match_criterio"] = criterio

            cols = ", ".join(data.keys())
            vals = ", ".join([f":{k}" for k in data.keys()])
            session.execute(text(f"INSERT INTO consultas_master ({cols}) VALUES ({vals})"), data)

            barra(i, total, prefijo="  Procesando ")

        session.commit()
        print()

        ok(f"PASO 6 COMPLETADO — {total} consultas insertadas")
        print()
        print("  Resumen de matching:")
        print(f"    Por expediente          : {stats['expediente']:>7,}")
        print(f"    Por nombre + DPI        : {stats['nombre_dpi']:>7,}")
        print(f"    Por nombre + nacimiento : {stats['nombre_nacimiento']:>7,}")
        print(f"    Registro único consulta : {stats['unico_consulta']:>7,}")
        print(f"    Creado en el momento    : {stats['creado_directo']:>7,}")
        print(f"    Sin coincidencia (NULL) : {stats['sin_match']:>7,}")

        # ── Red de seguridad: limpiar DPIs duplicados introducidos ───────
        # El criterio "creado_directo" puede haber insertado pacientes con
        # DPI que ya existía en pacientes_master (dos consultas con mismo DPI
        # procesadas antes de que el commit intermedio sea visible).
        # _limpiar_dpi_duplicados garantiza unicidad antes de migrar a PG.
        info("Verificando unicidad de DPI tras inserciones directas...")
        _limpiar_dpi_duplicados(session, "pacientes_master")

    except Exception as e:
        session.rollback()
        print(f"\n  ✗ Error en PASO 6: {e}")
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN FINAL
# ─────────────────────────────────────────────────────────────────────────────

def resumen_final():
    titulo("RESUMEN FINAL")
    db = init_db()
    session = db["MySQLSession"]()
    try:
        # ── Conteo de tablas ──────────────────────────────────────────────
        tablas = [
            "consultas", "consultas_master",
            "pacientes", "pacientes_clean",
            "pacientes_nuevos", "pacientes_master",
        ]
        for t in tablas:
            try:
                n = session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"  {t:<25} {n:>8,} registros")
            except Exception:
                print(f"  {t:<25} (no existe)")

        # ── Consultas sin paciente_id ─────────────────────────────────────
        sin_match = session.execute(text(
            "SELECT COUNT(*) FROM consultas_master WHERE paciente_id IS NULL"
        )).scalar()
        print(f"\n  Consultas sin paciente_id :  {sin_match:>7,}")

        # ── Resumen de integridad DPI en pacientes_master ─────────────────
        dpi_unicos = session.execute(text("""
            SELECT COUNT(DISTINCT dpi) FROM pacientes_master WHERE dpi IS NOT NULL
        """)).scalar()
        dpi_nulos = session.execute(text("""
            SELECT COUNT(*) FROM pacientes_master WHERE dpi IS NULL
        """)).scalar()
        con_cui_dup = session.execute(text("""
            SELECT COUNT(*) FROM pacientes_master WHERE cui_duplicado IS NOT NULL
        """)).scalar()
        dpi_duplicados_restantes = session.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT dpi FROM pacientes_master
                WHERE dpi IS NOT NULL
                GROUP BY dpi HAVING COUNT(*) > 1
            ) AS sub
        """)).scalar()

        print(f"\n  Integridad DPI en pacientes_master:")
        print(f"    DPIs únicos             : {dpi_unicos:>7,}")
        print(f"    Registros sin DPI       : {dpi_nulos:>7,}")
        print(f"    Con cui_duplicado       : {con_cui_dup:>7,}")
        print(f"    DPIs duplicados restant.: {dpi_duplicados_restantes:>7,}", end="")
        if dpi_duplicados_restantes == 0:
            print("  ✓ OK — listo para PostgreSQL UNIQUE")
        else:
            print("  ⚠ REVISAR — aún hay duplicados")

        if sin_match == 0:
            print("\n  ✓ Matching completo — todas las consultas tienen paciente_id")
            return

        # ── Diagnóstico de los sin match ──────────────────────────────────
        print("\n  Diagnóstico de consultas sin paciente_id:")

        sin_exp = session.execute(text("""
            SELECT COUNT(*) FROM consultas_master
            WHERE paciente_id IS NULL
              AND (expediente IS NULL OR expediente = 0)
        """)).scalar()
        con_exp = sin_match - sin_exp
        print(f"    Sin expediente en consulta  : {sin_exp:>7,}  (no hay con que buscar)")
        print(f"    Con expediente sin match    : {con_exp:>7,}  (expediente no existe en pacientes)")

        con_nombre = session.execute(text("""
            SELECT COUNT(*) FROM consultas_master
            WHERE paciente_id IS NULL
              AND nombres IS NOT NULL AND apellidos IS NOT NULL
        """)).scalar()
        print(f"    Con nombre pero sin match   : {con_nombre:>7,}")

        con_dpi = session.execute(text("""
            SELECT COUNT(*) FROM consultas_master
            WHERE paciente_id IS NULL
              AND dpi IS NOT NULL AND CHAR_LENGTH(dpi) = 13
        """)).scalar()
        print(f"    Con DPI valido sin match    : {con_dpi:>7,}")

        con_nac = session.execute(text("""
            SELECT COUNT(*) FROM consultas_master
            WHERE paciente_id IS NULL
              AND nacimiento IS NOT NULL
        """)).scalar()
        print(f"    Con nacimiento sin match    : {con_nac:>7,}")

        # Muestra 5 ejemplos para inspeccion manual
        print("\n  Muestra de consultas sin match (primeros 5):")
        print(f"  {'nombres':<20} {'apellidos':<20} {'expediente':>11} {'dpi':>15} {'nacimiento':>12}")
        print(f"  {'-'*20} {'-'*20} {'-'*11} {'-'*15} {'-'*12}")
        ejemplos = session.execute(text("""
            SELECT nombres, apellidos, expediente, dpi, nacimiento
            FROM consultas_master
            WHERE paciente_id IS NULL
            LIMIT 5
        """)).fetchall()
        for e in ejemplos:
            nombres    = (e[0] or "NULL")[:20]
            apellidos  = (e[1] or "NULL")[:20]
            expediente = str(e[2] or "NULL")
            dpi        = str(e[3] or "NULL")
            nacimiento = str(e[4] or "NULL")
            print(f"  {nombres:<20} {apellidos:<20} {expediente:>11} {dpi:>15} {nacimiento:>12}")

        if con_exp > 0:
            print(f"\n  Primeros 5 expedientes en consultas que no estan en pacientes_master:")
            faltantes = session.execute(text("""
                SELECT DISTINCT cm.expediente
                FROM consultas_master cm
                WHERE cm.paciente_id IS NULL
                  AND cm.expediente IS NOT NULL AND cm.expediente != 0
                  AND NOT EXISTS (
                      SELECT 1 FROM pacientes_master pm
                      WHERE pm.expediente = cm.expediente
                  )
                LIMIT 5
            """)).fetchall()
            for f in faltantes:
                print(f"    expediente {f[0]}")

    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    def paso_5b_standalone():
        """Ejecuta solo la limpieza de DPI duplicados sobre pacientes_master."""
        db = init_db()
        session = db["MySQLSession"]()
        try:
            _limpiar_dpi_duplicados(session, "pacientes_master")
        except Exception as e:
            session.rollback()
            print(f"\n  ✗ Error en PASO 5b: {e}")
            raise
        finally:
            session.close()

    pasos = {
        "0":  ("Rellenar consultas desde pacientes",   paso_0_rellenar_consultas_desde_pacientes),
        "1":  ("Limpiar consultas",                    paso_1_limpiar_consultas),
        "2":  ("Limpiar pacientes",                    paso_2_limpiar_pacientes),
        "3":  ("Deduplicar pacientes → clean",         paso_3_deduplicar_pacientes),
        "3b": ("Reparar consultas post-merge",          paso_3b_reparar_consultas_post_merge),
        "4":  ("Pacientes nuevos de consultas",         paso_4_pacientes_nuevos_de_consultas),
        "5":  ("Construir pacientes_master",            paso_5_construir_master),
        "5b": ("Limpiar DPI duplicados en master",      paso_5b_standalone),
        "6":  ("Crear consultas_master + paciente_id",  paso_6_crear_consultas_master),
    }

    if len(sys.argv) > 1:
        # Modo selectivo: python preparar_mysql.py 0 1 3 6
        seleccion = sys.argv[1:]
        for num in seleccion:
            if num in pasos:
                pasos[num][1]()
            else:
                print(f"Paso '{num}' no existe. Disponibles: {list(pasos.keys())}")
    else:
        # Ejecutar todo
        for num, (nombre, func) in pasos.items():
            func()

        resumen_final()