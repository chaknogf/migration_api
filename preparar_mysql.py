#!/usr/bin/env python3
# preparar_mysql.py
# Pipeline de limpieza y migración de datos hospitalarios
# Orden: consultas → pacientes → merge → master

import sys
import unicodedata
from sqlalchemy import text
from database.database import init_db


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
    """
    excluir = excluir or {"id", "created_at", "update_at", "updated_at"}
    exp_migrados: list[str] = []

    for otro in otros:
        if otro.get("expediente"):
            exp_migrados.append(str(otro["expediente"]))
        for k, v in otro.items():
            if k in excluir:
                continue
            if base.get(k) in (None, "", 0) and v not in (None, "", 0):
                base[k] = v

    existentes = base.get("exp_migrado") or ""
    lista_exist = [e.strip() for e in existentes.split(",") if e.strip()]
    todos = sorted(set(lista_exist + exp_migrados))
    base["exp_migrado"] = ",".join(todos) if todos else None
    return base


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
# PASO 3 — DEDUPLICAR Y COMBINAR pacientes → pacientes_clean
# ─────────────────────────────────────────────────────────────────────────────

def paso_3_deduplicar_pacientes():
    titulo("PASO 3 — DEDUPLICAR PACIENTES → pacientes_clean")
    db = init_db()
    session = db["MySQLSession"]()

    EXCLUIR = {"id", "created_at", "update_at"}

    def ejecutar_merge(registros: list) -> None:
        if len(registros) < 2:
            return
        base = dict(registros[0])
        otros = [dict(r) for r in registros[1:]]
        base = merge_campos(base, otros, excluir=EXCLUIR)

        campos_up = [k for k in base if k not in EXCLUIR and k != "id"]
        sets_sql = ", ".join([f"{k} = :{k}" for k in campos_up])
        params = {k: base[k] for k in campos_up}
        params["id"] = base["id"]
        session.execute(text(f"UPDATE pacientes_clean SET {sets_sql} WHERE id = :id"), params)

        ids_borrar = [str(o["id"]) for o in otros]
        if ids_borrar:
            session.execute(text(
                f"DELETE FROM pacientes_clean WHERE id IN ({','.join(ids_borrar)})"
            ))

    try:
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
            ejecutar_merge(list(registros))
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
            ejecutar_merge(list(registros))
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
            ejecutar_merge(list(registros))
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
                hojas_emergencia TEXT
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
                 telefono, direccion, hojas_emergencia)
            SELECT
                expediente,
                MAX(nombres), MAX(apellidos), MAX(nacimiento),
                MAX(sexo), MAX(dpi), MAX(telefono), MAX(direccion),
                NULLIF(GROUP_CONCAT(DISTINCT hoja_emergencia
                       ORDER BY hoja_emergencia SEPARATOR ','), '')
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
                        (nombres, apellidos, nacimiento, dpi, hojas_emergencia)
                    VALUES (:nombres, :apellidos, :nacimiento, NULLIF(CAST(:dpi AS UNSIGNED), 0), :hojas)
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
                        (nombres, apellidos, nacimiento, hojas_emergencia)
                    VALUES (:nombres, :apellidos, :nacimiento, :hojas)
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
                       cui_duplicado
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
                fuente           VARCHAR(20)        -- 'pacientes' | 'consultas'
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
                cui_duplicado, fuente
            )
            SELECT
                expediente, nombre, apellido, nacimiento, sexo, dpi, pasaporte,
                nacionalidad, lugar_nacimiento, depto_nac, estado_civil, educacion,
                pueblo, idioma, ocupacion, direccion, municipio, depto, telefono,
                email, padre, madre, responsable, parentesco, dpi_responsable,
                telefono_responsable, estado, exp_madre, gemelo, conyugue, exp_ref,
                created_by, fechaDefuncion, hora_defuncion, exp_migrado,
                cui_duplicado, 'pacientes'
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
                dpi, telefono, direccion, hojas_emergencia, fuente
            )
            SELECT
                expediente, nombres, apellidos, nacimiento, sexo,
                dpi, telefono, direccion, hojas_emergencia, 'consultas'
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

                created_at          TIMESTAMP,
                updated_at          TIMESTAMP,
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

            # ── 5) Sin datos mínimos — crear paciente en el momento ───────
            # Solo llega aquí si no tiene nombre ni apellido (ruido residual)
            # o si por alguna razón no se encontró en pacientes_master.
            # En ese caso se inserta como paciente nuevo ahora mismo.
            if not paciente_id and c["nombres"] and c["apellidos"]:
                ins = session.execute(text("""
                    INSERT INTO pacientes_master
                        (nombre, apellido, nacimiento, sexo, dpi,
                         telefono, direccion, fuente)
                    VALUES
                        (:nombres, :apellidos, :nac, :sexo, :dpi,
                         :telefono, :direccion, 'consulta_directa')
                """), {
                    "nombres":   c["nombres"],
                    "apellidos": c["apellidos"],
                    "nac":       c["nacimiento"],
                    "sexo":      c["sexo"],
                    "dpi":       int(c["dpi"]) if c["dpi"] else None,
                    "telefono":  c["telefono"],
                    "direccion": c["direccion"],
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
        "1":  ("Limpiar consultas",                   paso_1_limpiar_consultas),
        "2":  ("Limpiar pacientes",                    paso_2_limpiar_pacientes),
        "3":  ("Deduplicar pacientes → clean",         paso_3_deduplicar_pacientes),
        "4":  ("Pacientes nuevos de consultas",         paso_4_pacientes_nuevos_de_consultas),
        "5":  ("Construir pacientes_master",            paso_5_construir_master),
        "5b": ("Limpiar DPI duplicados en master",      paso_5b_standalone),
        "6":  ("Crear consultas_master + paciente_id",  paso_6_crear_consultas_master),
    }

    if len(sys.argv) > 1:
        # Modo selectivo: python preparar_mysql.py 1 3 6
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