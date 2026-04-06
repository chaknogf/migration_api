#!/usr/bin/env python3
"""
deduplicar_master.py
Deduplicación recursiva de pacientes_master con protección de nombres.

CRITERIOS (en orden de confianza):
  1) expediente  — fusiona siempre, nombres distintos no importan
  2) dpi         — fusiona SOLO si los nombres son suficientemente similares
                   si son distintos → marca como conflicto, no toca

SIMILITUD DE NOMBRES:
  Usa distancia de Levenshtein normalizada sobre nombre+apellido completo.
  Umbral configurable (default 0.70 = 70% similitud mínima).
  Nombres muy distintos con el mismo DPI se escriben en dpi_conflictos
  para revisión manual.

RECURSIVIDAD:
  Itera fases hasta convergencia (ningún cambio en una pasada completa).
"""

import sys
from sqlalchemy import text
from database.database import init_db


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

UMBRAL_SIMILITUD = 0.70   # mínimo para considerar misma persona por DPI
BATCH_COMMIT     = 200    # commit cada N grupos procesados


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def barra(actual: int, total: int, largo: int = 35, prefijo: str = "") -> None:
    if total == 0:
        return
    pct   = actual / total
    lleno = int(largo * pct)
    b     = "█" * lleno + "░" * (largo - lleno)
    print(f"\r  {prefijo}[{b}] {int(pct*100):3d}% ({actual}/{total})",
          end="", flush=True)
    if actual >= total:
        print()


def titulo(texto: str) -> None:
    linea = "─" * 60
    print(f"\n{linea}\n  {texto}\n{linea}")


def ok(msg: str)   -> None: print(f"  ✓ {msg}")
def info(msg: str) -> None: print(f"  → {msg}")
def warn(msg: str) -> None: print(f"  ⚠ {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# SIMILITUD DE NOMBRES (Levenshtein normalizado)
# ─────────────────────────────────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    if a == b: return 0
    if not a:  return len(b)
    if not b:  return len(a)
    m, n = len(a), len(b)
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            costo   = 0 if a[i-1] == b[j-1] else 1
            curr[j] = min(prev[j] + 1, curr[j-1] + 1, prev[j-1] + costo)
        prev, curr = curr, [0] * (n + 1)
    return prev[n]


def similitud_nombres(nombre_a, apellido_a, nombre_b, apellido_b) -> float:
    def norm(n, a):
        s = f"{(n or '').strip()} {(a or '').strip()}".lower()
        return " ".join(s.split())
    sa, sb = norm(nombre_a, apellido_a), norm(nombre_b, apellido_b)
    if not sa and not sb: return 1.0
    if not sa or not sb:  return 0.0
    d = _levenshtein(sa, sb)
    return 1.0 - d / max(len(sa), len(sb))


# ─────────────────────────────────────────────────────────────────────────────
# CAMPOS FUSIONABLES
# ─────────────────────────────────────────────────────────────────────────────

CAMPOS_FUSIONABLES = [
    "dpi", "nombre", "apellido", "nacimiento", "sexo",
    "pasaporte", "nacionalidad", "depto_nac", "lugar_nacimiento",
    "estado_civil", "educacion", "pueblo", "idioma", "ocupacion",
    "direccion", "municipio", "depto", "telefono", "email",
    "padre", "madre", "responsable", "parentesco",
    "dpi_responsable", "telefono_responsable", "estado",
    "exp_madre", "gemelo", "conyugue", "exp_ref",
    "created_by", "fechaDefuncion", "hora_defuncion",
]


def fusionar_registros(session, id_master: int, ids_dup: list) -> None:
    ids_str   = ",".join(str(i) for i in ids_dup)
    master    = dict(session.execute(text(
        f"SELECT * FROM pacientes_master WHERE id = {id_master}"
    )).mappings().first())
    duplicados = session.execute(text(
        f"SELECT * FROM pacientes_master WHERE id IN ({ids_str})"
    )).mappings().all()

    updates = {}
    for campo in CAMPOS_FUSIONABLES:
        if master.get(campo) in (None, "", 0):
            for dup in duplicados:
                val = dup.get(campo)
                if val not in (None, "", 0):
                    updates[campo] = val
                    break

    absorbidos = [
        str(d["expediente"]) for d in duplicados
        if d.get("expediente") and str(d["expediente"]) != str(master.get("expediente"))
    ]
    existentes = [e.strip() for e in (master.get("exp_migrado") or "").split(",") if e.strip()]
    todos = sorted(set(existentes + absorbidos))
    updates["exp_migrado"] = ",".join(todos) if todos else None

    if updates:
        sets_sql = ", ".join([f"{k} = :{k}" for k in updates])
        updates["_id"] = id_master
        session.execute(text(
            f"UPDATE pacientes_master SET {sets_sql} WHERE id = :_id"
        ), updates)


# ─────────────────────────────────────────────────────────────────────────────
# TABLA DE CONFLICTOS DPI
# ─────────────────────────────────────────────────────────────────────────────

def crear_tabla_conflictos(session) -> None:
    session.execute(text("DROP TABLE IF EXISTS dpi_conflictos"))
    session.execute(text("""
        CREATE TABLE dpi_conflictos (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            dpi           BIGINT,
            id_paciente_a INT,
            nombre_a      VARCHAR(100),
            id_paciente_b INT,
            nombre_b      VARCHAR(100),
            similitud     DECIMAL(5,4),
            detectado_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """))
    session.commit()
    ok("Tabla dpi_conflictos creada")


def registrar_conflicto(session, dpi, id_a, nombre_a, apellido_a,
                        id_b, nombre_b, apellido_b, sim) -> None:
    session.execute(text("""
        INSERT INTO dpi_conflictos
            (dpi, id_paciente_a, nombre_a, id_paciente_b, nombre_b, similitud)
        VALUES (:dpi, :id_a, :na, :id_b, :nb, :sim)
    """), {
        "dpi": dpi,
        "id_a": id_a, "na": f"{nombre_a or ''} {apellido_a or ''}".strip(),
        "id_b": id_b, "nb": f"{nombre_b or ''} {apellido_b or ''}".strip(),
        "sim": round(sim, 4),
    })


# ─────────────────────────────────────────────────────────────────────────────
# FASE 1 — EXPEDIENTE (siempre seguro)
# ─────────────────────────────────────────────────────────────────────────────

def fase_expediente(session, stats: dict) -> int:
    grupos_raw = session.execute(text("""
        SELECT p.id AS id_old, t.id_master
        FROM pacientes_master p
        JOIN (
            SELECT expediente, MIN(id) AS id_master
            FROM pacientes_master
            WHERE expediente IS NOT NULL
            GROUP BY expediente HAVING COUNT(*) > 1
        ) t ON p.expediente = t.expediente
        WHERE p.id != t.id_master
        ORDER BY t.id_master, p.id
    """)).fetchall()

    if not grupos_raw:
        ok("expediente: sin duplicados")
        return 0

    grupos: dict = {}
    for row in grupos_raw:
        grupos.setdefault(row.id_master, []).append(row.id_old)

    total = len(grupos)
    info(f"expediente: {total} grupos ({len(grupos_raw)} registros)")
    cambios = 0

    for i, (id_master, ids_dup) in enumerate(grupos.items(), 1):
        try:
            fusionar_registros(session, id_master, ids_dup)
            ids_str = ",".join(str(x) for x in ids_dup)
            r1 = session.execute(text(
                f"UPDATE consultas_master SET paciente_id = {id_master} "
                f"WHERE paciente_id IN ({ids_str})"
            ))
            r2 = session.execute(text(
                f"DELETE FROM pacientes_master WHERE id IN ({ids_str})"
            ))
            cambios += r1.rowcount + r2.rowcount
            stats["fusionados"]            += len(ids_dup)
            stats["consultas_redirigidas"] += r1.rowcount
            if i % BATCH_COMMIT == 0:
                session.commit()
        except Exception as e:
            session.rollback()
            stats["errores"] += 1
            warn(f"Error expediente master={id_master}: {e}")
        barra(i, total, prefijo="  expediente  ")

    session.commit()
    return cambios


# ─────────────────────────────────────────────────────────────────────────────
# FASE 2 — DPI + VALIDACIÓN DE NOMBRES (automático + revisión manual)
# ─────────────────────────────────────────────────────────────────────────────

def _mostrar_paciente(session, pid: int, etiqueta: str) -> None:
    """Imprime los datos de un paciente para revisión en consola."""
    row = session.execute(text(
        f"SELECT * FROM pacientes_master WHERE id = {pid}"
    )).mappings().first()
    if not row:
        print(f"    {etiqueta}: [no encontrado id={pid}]")
        return
    nac  = str(row["nacimiento"]) if row.get("nacimiento") else "—"
    dpi  = str(row["dpi"])        if row.get("dpi")        else "—"
    exp  = str(row["expediente"]) if row.get("expediente") else "—"
    tel  = str(row["telefono"])   if row.get("telefono")   else "—"
    n_con = session.execute(text(
        f"SELECT COUNT(*) FROM consultas_master WHERE paciente_id = {pid}"
    )).scalar()
    print(f"    [{etiqueta}] id={pid}")
    print(f"         Nombre     : {row.get('nombre','')} {row.get('apellido','')}")
    print(f"         Nacimiento : {nac}   Sexo: {row.get('sexo') or '—'}")
    print(f"         DPI        : {dpi}")
    print(f"         Expediente : {exp}")
    print(f"         Teléfono   : {tel}")
    print(f"         Consultas  : {n_con}")


def _pedir_decision(id_a: int, id_b: int) -> str:
    """
    Solicita al usuario qué hacer con un par conflictivo.
    Retorna: 'a' | 'b' | 'fusionar' | 'saltar' | 'salir'
    """
    while True:
        print()
        print("    ¿Qué hacer?")
        print(f"    [a] El DPI pertenece a A (id={id_a}) → B pierde el DPI")
        print(f"    [b] El DPI pertenece a B (id={id_b}) → A pierde el DPI")
        print( "    [n] Ninguno es correcto → anular DPI en ambos")
        print( "    [f] Son la misma persona → fusionar (A absorbe B)")
        print( "    [s] Saltar este par (decidir después)")
        print( "    [q] Salir y guardar progreso")
        resp = input("    Opción: ").strip().lower()
        if resp in ("a", "b", "n", "f", "s", "q"):
            return resp
        print("    Opción inválida, intenta de nuevo.")


def fase_dpi(session, stats: dict) -> int:
    # ── Obtener todos los grupos con DPI duplicado ────────────────────────
    grupos_raw = session.execute(text("""
        SELECT p.id AS id_old, p.nombre, p.apellido,
               p.nacimiento, p.expediente, p.telefono, p.dpi AS dpi_b,
               t.id_master, t.nombre_master, t.apellido_master, t.dpi
        FROM pacientes_master p
        JOIN (
            SELECT pm.dpi, MIN(pm.id) AS id_master,
                   (SELECT nombre    FROM pacientes_master WHERE id = MIN(pm.id)) AS nombre_master,
                   (SELECT apellido  FROM pacientes_master WHERE id = MIN(pm.id)) AS apellido_master
            FROM pacientes_master pm
            WHERE pm.dpi IS NOT NULL
            GROUP BY pm.dpi HAVING COUNT(*) > 1
        ) t ON p.dpi = t.dpi
        WHERE p.id != t.id_master
        ORDER BY t.id_master, p.id
    """)).fetchall()

    if not grupos_raw:
        ok("dpi: sin duplicados")
        return 0

    total_pares = len(grupos_raw)
    info(f"dpi: {total_pares} registros con DPI duplicado — validando nombres...")

    # ── Separar: automáticos (alta similitud) vs manuales ────────────────
    fusionables:  dict = {}   # id_master → [ids_dup]  (fusión automática)
    para_revisar: list = []   # pares que necesitan decisión humana

    for row in grupos_raw:
        sim = similitud_nombres(
            row.nombre_master, row.apellido_master,
            row.nombre,        row.apellido,
        )
        if sim >= UMBRAL_SIMILITUD:
            fusionables.setdefault(row.id_master, []).append(row.id_old)
        else:
            para_revisar.append((row, sim))

    # ── Fusiones automáticas ──────────────────────────────────────────────
    cambios = 0
    if fusionables:
        info(f"dpi automático: {len(fusionables)} grupos (similitud ≥ {UMBRAL_SIMILITUD:.0%})")
        for i, (id_master, ids_dup) in enumerate(fusionables.items(), 1):
            try:
                fusionar_registros(session, id_master, ids_dup)
                ids_str = ",".join(str(x) for x in ids_dup)
                r1 = session.execute(text(
                    f"UPDATE consultas_master SET paciente_id = {id_master} "
                    f"WHERE paciente_id IN ({ids_str})"
                ))
                r2 = session.execute(text(
                    f"DELETE FROM pacientes_master WHERE id IN ({ids_str})"
                ))
                cambios += r1.rowcount + r2.rowcount
                stats["fusionados"]            += len(ids_dup)
                stats["consultas_redirigidas"] += r1.rowcount
                if i % BATCH_COMMIT == 0:
                    session.commit()
            except Exception as e:
                session.rollback()
                stats["errores"] += 1
                warn(f"Error fusión auto id_master={id_master}: {e}")
            barra(i, len(fusionables), prefijo="  dpi auto     ")
        session.commit()
        print()

    # ── Revisión manual de conflictos ─────────────────────────────────────
    if not para_revisar:
        ok(f"dpi: sin conflictos manuales")
        return cambios

    print()
    linea = "═" * 60
    print(f"  {linea}")
    print(f"  REVISIÓN MANUAL: {len(para_revisar)} pares con nombres distintos")
    print(f"  {linea}")

    saltados  = 0
    salir     = False

    for idx, (row, sim) in enumerate(para_revisar, 1):
        if salir:
            # Registrar el resto como conflicto sin preguntar
            registrar_conflicto(
                session, row.dpi,
                row.id_master, row.nombre_master, row.apellido_master,
                row.id_old,    row.nombre,        row.apellido,
                sim,
            )
            stats["dpi_conflictos"] += 1
            continue

        print()
        print(f"  ─── Par {idx}/{len(para_revisar)}  "
              f"DPI: {row.dpi}  similitud: {sim:.0%} ───")
        _mostrar_paciente(session, row.id_master, "A (master)")
        _mostrar_paciente(session, row.id_old,    "B (duplicado)")

        decision = _pedir_decision(row.id_master, row.id_old)

        if decision == "q":
            salir = True
            # Registrar este par también como conflicto
            registrar_conflicto(
                session, row.dpi,
                row.id_master, row.nombre_master, row.apellido_master,
                row.id_old,    row.nombre,        row.apellido,
                sim,
            )
            stats["dpi_conflictos"] += 1
            session.commit()
            warn("Salida solicitada — pares restantes guardados en dpi_conflictos")
            continue

        if decision == "s":
            registrar_conflicto(
                session, row.dpi,
                row.id_master, row.nombre_master, row.apellido_master,
                row.id_old,    row.nombre,        row.apellido,
                sim,
            )
            stats["dpi_conflictos"] += 1
            saltados += 1
            session.commit()
            continue

        if decision == "f":
            # Fusionar: A absorbe B
            try:
                fusionar_registros(session, row.id_master, [row.id_old])
                r1 = session.execute(text(
                    f"UPDATE consultas_master SET paciente_id = {row.id_master} "
                    f"WHERE paciente_id = {row.id_old}"
                ))
                session.execute(text(
                    f"DELETE FROM pacientes_master WHERE id = {row.id_old}"
                ))
                cambios += r1.rowcount + 1
                stats["fusionados"]            += 1
                stats["consultas_redirigidas"] += r1.rowcount
                ok(f"Fusionado: B (id={row.id_old}) absorbido por A (id={row.id_master})")
            except Exception as e:
                session.rollback()
                stats["errores"] += 1
                warn(f"Error fusionando: {e}")
            session.commit()
            continue

        if decision == "a":
            # DPI pertenece a A → B pierde el DPI
            session.execute(text(
                f"UPDATE pacientes_master SET dpi = NULL WHERE id = {row.id_old}"
            ))
            cambios += 1
            stats["dpi_anulados"] += 1
            ok(f"DPI anulado en B (id={row.id_old}) — A conserva el DPI")
            session.commit()
            continue

        if decision == "b":
            # DPI pertenece a B → A pierde el DPI
            session.execute(text(
                f"UPDATE pacientes_master SET dpi = NULL WHERE id = {row.id_master}"
            ))
            cambios += 1
            stats["dpi_anulados"] += 1
            ok(f"DPI anulado en A (id={row.id_master}) — B conserva el DPI")
            session.commit()
            continue

        if decision == "n":
            # Ninguno tiene el DPI correcto → anular en ambos
            session.execute(text(
                f"UPDATE pacientes_master SET dpi = NULL "
                f"WHERE id IN ({row.id_master}, {row.id_old})"
            ))
            cambios += 2
            stats["dpi_anulados"] += 2
            ok(f"DPI anulado en A (id={row.id_master}) y B (id={row.id_old})")
            session.commit()
            continue

    if saltados:
        warn(f"{saltados} pares saltados → guardados en dpi_conflictos para revisión posterior")

    ok(f"dpi: {stats['fusionados']} fusionados, "
       f"{stats['dpi_anulados']} DPI anulados manualmente, "
       f"{stats['dpi_conflictos']} en dpi_conflictos")
    return cambios


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def deduplicar():
    titulo("DEDUPLICACIÓN RECURSIVA pacientes_master")
    db      = init_db()
    session = db["MySQLSession"]()

    stats = {
        "fusionados": 0, "consultas_redirigidas": 0,
        "dpi_conflictos": 0, "dpi_anulados": 0, "errores": 0, "iteraciones": 0,
    }

    try:
        n_pac   = session.execute(text("SELECT COUNT(*) FROM pacientes_master")).scalar()
        n_con   = session.execute(text("SELECT COUNT(*) FROM consultas_master")).scalar()
        dup_exp = session.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT expediente FROM pacientes_master
                WHERE expediente IS NOT NULL
                GROUP BY expediente HAVING COUNT(*) > 1
            ) t""")).scalar()
        dup_dpi = session.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT dpi FROM pacientes_master
                WHERE dpi IS NOT NULL
                GROUP BY dpi HAVING COUNT(*) > 1
            ) t""")).scalar()

        info(f"pacientes_master        : {n_pac:,}")
        info(f"consultas_master        : {n_con:,}")
        info(f"Grupos dup. expediente  : {dup_exp:,}")
        info(f"Grupos dup. DPI         : {dup_dpi:,}")
        info(f"Umbral similitud nombres: {UMBRAL_SIMILITUD:.0%}")

        if dup_exp + dup_dpi == 0:
            ok("Sin duplicados — nada que hacer")
            return

        crear_tabla_conflictos(session)

        # ── Bucle recursivo ───────────────────────────────────────────────
        while True:
            stats["iteraciones"] += 1
            sep = "─" * 40
            print(f"\n  {sep}\n  Iteración {stats['iteraciones']}\n  {sep}")

            iter_stats = {
                "fusionados": 0, "consultas_redirigidas": 0,
                "dpi_conflictos": 0, "dpi_anulados": 0, "errores": 0,
            }

            cambios  = fase_expediente(session, iter_stats)
            cambios += fase_dpi(session, iter_stats)

            for k in iter_stats:
                stats[k] += iter_stats[k]

            print(f"\n  Cambios iteración {stats['iteraciones']}: {cambios} "
                  f"(fusionados: {iter_stats['fusionados']}, "
                  f"redirigidas: {iter_stats['consultas_redirigidas']})")

            if cambios == 0:
                break

        # ── Resultado ─────────────────────────────────────────────────────
        titulo("RESULTADO FINAL")
        n_pac_f    = session.execute(text("SELECT COUNT(*) FROM pacientes_master")).scalar()
        n_con_ok   = session.execute(text("SELECT COUNT(*) FROM consultas_master WHERE paciente_id IS NOT NULL")).scalar()
        n_con_null = session.execute(text("SELECT COUNT(*) FROM consultas_master WHERE paciente_id IS NULL")).scalar()
        n_conf     = session.execute(text("SELECT COUNT(*) FROM dpi_conflictos")).scalar()

        print(f"  pacientes antes      : {n_pac:>8,}")
        print(f"  pacientes ahora      : {n_pac_f:>8,}")
        print(f"  eliminados           : {n_pac - n_pac_f:>8,}")
        print()
        print(f"  consultas con pac.   : {n_con_ok:>8,}")
        print(f"  consultas sin pac.   : {n_con_null:>8,}")
        print(f"  redirigidas total    : {stats['consultas_redirigidas']:>8,}")
        print()
        print(f"  conflictos DPI       : {n_conf:>8,}  → tabla dpi_conflictos")
        print(f"  DPI anulados manual  : {stats['dpi_anulados']:>8,}")
        print(f"  iteraciones          : {stats['iteraciones']:>8,}")
        print(f"  errores              : {stats['errores']:>8,}")

        dup_exp_f = session.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT expediente FROM pacientes_master
                WHERE expediente IS NOT NULL
                GROUP BY expediente HAVING COUNT(*) > 1
            ) t""")).scalar()
        dup_dpi_f = session.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT dpi FROM pacientes_master
                WHERE dpi IS NOT NULL
                  AND dpi NOT IN (SELECT DISTINCT dpi FROM dpi_conflictos WHERE dpi IS NOT NULL)
                GROUP BY dpi HAVING COUNT(*) > 1
            ) t""")).scalar()

        print()
        if dup_exp_f + dup_dpi_f == 0:
            ok("Verificación OK — cero duplicados resolubles restantes")
        else:
            warn(f"Duplicados sin resolver: expediente={dup_exp_f}, dpi={dup_dpi_f}")

        if n_conf:
            print()
            warn(f"{n_conf} pares requieren revisión manual:")
            warn("  SELECT * FROM dpi_conflictos ORDER BY similitud DESC;")

    except Exception as e:
        session.rollback()
        print(f"\n  ✗ Error: {e}")
        import traceback; traceback.print_exc()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    deduplicar()