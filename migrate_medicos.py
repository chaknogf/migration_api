#!/usr/bin/env python3
# migrate_medicos.py
"""
Script de migración específico para tabla MÉDICOS
Transforma estructura relacional MySQL -> PostgreSQL

medicos (MySQL) → medicos (PostgreSQL)

⚠️ IMPORTANTE:
Este script hace TRUNCATE de la tabla medicos en PostgreSQL
antes de iniciar la migración.

Debe ejecutarse ANTES de migrate_constancias.py
ya que constancia_nacimiento tiene FK → medicos.id
"""

import os
import sys
from datetime import datetime
from typing import Optional, Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CATÁLOGO DE ESPECIALIDADES
# ============================================================================

ESPECIALIDADES = {
    1: "Medicina General",
    2: "Pediatría",
    3: "Ginecología y Obstetricia",
    4: "Cirugía General",
    5: "Medicina Interna",
    6: "Anestesiología",
    7: "Radiología",
    8: "Traumatología",
    9: "Cardiología",
    10: "Neurología",
    11: "Dermatología",
    12: "Oftalmología",
    13: "Psiquiatría",
    14: "Urología",
    15: "Otorrinolaringología",
}

# ============================================================================
# NORMALIZADORES
# ============================================================================

COLEGIADOS_VISTOS: set = set()
DPIS_VISTOS: set = set()

_SKIP = object()  # Sentinel para indicar "omitir registro"


def normalizar_nombre(name: Any) -> str:
    """Limpia y capitaliza el nombre del médico."""
    if not name or not str(name).strip():
        return "SIN NOMBRE"

    return " ".join(str(name).strip().title().split())


def normalizar_colegiado(colegiado: Any, id_mysql: Any):
    """
    Convierte el colegiado int de MySQL a varchar(20) de PostgreSQL.
    Retorna _SKIP si el colegiado ya existe (duplicado).
    """

    if not colegiado:
        return None

    try:
        col_str = str(int(colegiado)).strip()
    except Exception:
        col_str = str(colegiado).strip()

    if col_str in COLEGIADOS_VISTOS:
        print(
            f"   ⚠️ Colegiado duplicado: '{col_str}' "
            f"(id={id_mysql}) → registro omitido"
        )
        return _SKIP

    COLEGIADOS_VISTOS.add(col_str)

    return col_str


def normalizar_dpi(dpi: Any, id_mysql: Any) -> Optional[int]:
    """Valida que el DPI sea numérico y único."""

    if not dpi:
        return None

    try:
        dpi_int = int(str(dpi).strip())

    except ValueError:
        print(
            f"   ⚠️ DPI inválido para id={id_mysql}: "
            f"'{dpi}' → ignorado"
        )
        return None

    if dpi_int in DPIS_VISTOS:
        print(
            f"   ⚠️ DPI duplicado: {dpi_int} "
            f"(id={id_mysql}) → guardado como NULL"
        )
        return None

    DPIS_VISTOS.add(dpi_int)

    return dpi_int


def normalizar_sexo(sexo: Any) -> Optional[str]:
    """Normaliza el sexo a M / F / None."""

    if not sexo:
        return None

    s = str(sexo).strip().upper()

    if s in ("M", "MASCULINO", "H", "HOMBRE"):
        return "M"

    if s in ("F", "FEMENINO", "MUJER"):
        return "F"

    return None


def normalizar_especialidad(
    especialidad_id: Any,
    id_mysql: Any
) -> Optional[str]:
    """
    Convierte el id entero de especialidad a texto.
    """

    if not especialidad_id:
        return None

    try:
        eid = int(especialidad_id)

    except (ValueError, TypeError):
        return None

    nombre = ESPECIALIDADES.get(eid)

    if nombre is None:
        print(
            f"   ⚠️ Especialidad desconocida id={eid} "
            f"(médico mysql_id={id_mysql})"
        )

        return f"Especialidad {eid}"

    return nombre


# ============================================================================
# TRANSFORMACIÓN PRINCIPAL
# ============================================================================

def transformar_medico(row: Any) -> tuple[Optional[dict], list[str]]:
    """
    Transforma un registro de MySQL a PostgreSQL.
    Retorna (None, advertencias) si el registro debe omitirse.
    """

    advertencias = []

    if not isinstance(row, dict):
        row = dict(row._mapping)

    id_mysql = row.get("id")

    nombre = normalizar_nombre(row.get("name"))

    if nombre == "SIN NOMBRE":
        advertencias.append(f"[id={id_mysql}] sin nombre")

    colegiado = normalizar_colegiado(row.get("colegiado"), id_mysql)

    if colegiado is _SKIP:
        return None, [f"[id={id_mysql}] colegiado duplicado → omitido"]

    if colegiado is None:
        advertencias.append(f"[id={id_mysql}] sin colegiado")

    dpi = normalizar_dpi(
        row.get("dpi"),
        id_mysql
    )

    sexo = normalizar_sexo(
        row.get("sexo")
    )

    especialidad = normalizar_especialidad(
        row.get("especialidad"),
        id_mysql
    )

    registro = {
        "nombre": nombre,
        "colegiado": colegiado,
        "dpi": dpi,
        "sexo": sexo,
        "especialidad": especialidad,
        "activo": True,
        "created_at": row.get("created_at") or datetime.now(),
    }

    return registro, advertencias


# ============================================================================
# CONFIGURACIÓN DE CONEXIONES
# ============================================================================

def construir_url_mysql():
    return (
        f"mysql+pymysql://"
        f"{os.getenv('MYSQL_USER', 'root')}:"
        f"{os.getenv('MYSQL_PASSWORD', 'Prometeus.0')}@"
        f"{os.getenv('MYSQL_HOST', 'localhost')}:"
        f"{os.getenv('MYSQL_PORT', '3306')}/"
        f"{os.getenv('MYSQL_DATABASE', 'test_api')}"
    )


def construir_url_postgres():
    return (
        f"postgresql://"
        f"{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'secreto123')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'hospital')}"
    )


MYSQL_URL = construir_url_mysql()
POSTGRES_URL = construir_url_postgres()

print("=" * 80)
print("👨‍⚕️ MIGRACIÓN DE MÉDICOS: MySQL → PostgreSQL")
print("=" * 80)
print(f"Origen  (MySQL):      {MYSQL_URL.split('@')[1]}")
print(f"Destino (PostgreSQL): {POSTGRES_URL.split('@')[1]}")
print("=" * 80)

print("\n🔌 Conectando a bases de datos...")

try:
    mysql_engine = create_engine(MYSQL_URL, echo=False)
    postgres_engine = create_engine(POSTGRES_URL, echo=False)

    MySQLSession = sessionmaker(bind=mysql_engine)
    PostgresSession = sessionmaker(bind=postgres_engine)

    with mysql_engine.connect() as c:
        c.execute(text("SELECT 1"))

    with postgres_engine.connect() as c:
        c.execute(text("SELECT 1"))

    print("✅ Conexiones establecidas\n")

except Exception as e:
    print(f"❌ Error al conectar: {e}")
    sys.exit(1)

# ============================================================================
# QUERY DE INSERCIÓN
# ============================================================================

INSERT_QUERY = text("""
INSERT INTO medicos (
    nombre,
    colegiado,
    dpi,
    sexo,
    especialidad,
    activo,
    created_at
)
VALUES (
    :nombre,
    :colegiado,
    :dpi,
    :sexo,
    :especialidad,
    :activo,
    :created_at
)
ON CONFLICT DO NOTHING
""")

# ============================================================================
# TRUNCATE TABLA POSTGRES
# ============================================================================

def truncar_tabla_postgres():
    """
    Hace TRUNCATE de la tabla medicos en PostgreSQL
    y reinicia el autoincrement.
    """

    postgres_db = PostgresSession()

    try:
        print("=" * 80)
        print("🗑️ LIMPIANDO TABLA POSTGRESQL")
        print("=" * 80)

        postgres_db.execute(
            text("""
                TRUNCATE TABLE medicos
                RESTART IDENTITY CASCADE
            """)
        )

        postgres_db.commit()

        print("✅ Tabla medicos truncada correctamente")
        print("✅ IDs reiniciados")
        print()

    except Exception as e:
        postgres_db.rollback()

        print(f"❌ Error al truncar tabla: {e}")
        raise

    finally:
        postgres_db.close()


# ============================================================================
# MIGRACIÓN
# ============================================================================

def migrar_medicos(batch_size: int = 200) -> dict:

    mysql_db = MySQLSession()
    postgres_db = PostgresSession()

    stats = {
        "total": 0,
        "exitosos": 0,
        "omitidos": 0,
        "errores": 0,
        "advertencias": [],
    }

    inicio = datetime.now()

    try:
        filas = mysql_db.execute(
            text("SELECT * FROM medicos")
        ).fetchall()

        stats["total"] = len(filas)

        print(
            f"📋 Total de médicos a migrar: "
            f"{stats['total']:,}\n"
        )

        batch = []

        for i, fila in enumerate(filas, 1):

            try:
                registro, advertencias = transformar_medico(fila)

                if advertencias:
                    stats["advertencias"].extend(advertencias)

                    for adv in advertencias:
                        print(f"   ⚠️ {adv}")

                # Registro omitido (colegiado duplicado u otra razón)
                if registro is None:
                    stats["omitidos"] += 1
                    continue

                batch.append(registro)

                if i % batch_size == 0:

                    try:
                        postgres_db.execute(
                            INSERT_QUERY,
                            batch
                        )

                        postgres_db.commit()

                        stats["exitosos"] += len(batch)

                        print(
                            f"✅ Migrados "
                            f"{i}/{stats['total']}"
                        )

                    except Exception as e:
                        postgres_db.rollback()

                        stats["errores"] += len(batch)

                        print(
                            f"❌ Batch fallido en "
                            f"{i}: {e}"
                        )

                    batch = []

            except Exception as e:

                stats["errores"] += 1

                msg = (
                    f"Error en fila {i} "
                    f"(id={fila._mapping.get('id')}): {e}"
                )

                stats["advertencias"].append(msg)

                print(f"   ❌ {msg}")

        # Batch final
        if batch:

            try:
                postgres_db.execute(
                    INSERT_QUERY,
                    batch
                )

                postgres_db.commit()

                stats["exitosos"] += len(batch)

            except Exception as e:
                postgres_db.rollback()

                stats["errores"] += len(batch)

                print(f"❌ Batch final fallido: {e}")

        stats["tiempo"] = (
            datetime.now() - inicio
        ).total_seconds()

    finally:
        mysql_db.close()
        postgres_db.close()

    return stats


# ============================================================================
# VERIFICACIÓN
# ============================================================================

def verificar_migracion():

    mysql_db = MySQLSession()
    postgres_db = PostgresSession()

    try:
        print("\n" + "=" * 80)
        print("🔍 VERIFICACIÓN DE MIGRACIÓN")
        print("=" * 80)

        total_mysql = mysql_db.execute(
            text("SELECT COUNT(*) FROM medicos")
        ).scalar()

        total_pg = postgres_db.execute(
            text("SELECT COUNT(*) FROM medicos")
        ).scalar()

        print(f"\n📊 Conteo de registros:")
        print(f"   MySQL:      {total_mysql:,}")
        print(f"   PostgreSQL: {total_pg:,}")

        sin_colegiado = postgres_db.execute(
            text("""
                SELECT COUNT(*)
                FROM medicos
                WHERE colegiado IS NULL
            """)
        ).scalar()

        sin_dpi = postgres_db.execute(
            text("""
                SELECT COUNT(*)
                FROM medicos
                WHERE dpi IS NULL
            """)
        ).scalar()

        print(f"\n   Sin colegiado: {sin_colegiado:,}")
        print(f"   Sin DPI:       {sin_dpi:,}")

        print(f"\n   Distribución por especialidad:")

        especialidades = postgres_db.execute(text("""
            SELECT
                especialidad,
                COUNT(*) AS total
            FROM medicos
            GROUP BY especialidad
            ORDER BY total DESC
            LIMIT 10
        """)).fetchall()

        for esp, cnt in especialidades:
            print(
                f"   → "
                f"{(esp or 'Sin especialidad'):<30} "
                f"{cnt:>5}"
            )

        print(f"\n   Últimos 5 médicos migrados:")

        ultimos = postgres_db.execute(text("""
            SELECT
                id,
                nombre,
                colegiado,
                especialidad
            FROM medicos
            ORDER BY id DESC
            LIMIT 5
        """)).fetchall()

        for r in ultimos:
            print(
                f"   → "
                f"[{r[0]:>5}] "
                f"{r[1]:<30} | "
                f"col: {str(r[2]):<10} | "
                f"{r[3]}"
            )

    finally:
        mysql_db.close()
        postgres_db.close()


# ============================================================================
# MAIN
# ============================================================================

def main():

    # ----------------------------------------------------------------------
    # TRUNCATE TABLA POSTGRES
    # ----------------------------------------------------------------------

    truncar_tabla_postgres()

    # ----------------------------------------------------------------------
    # MIGRAR
    # ----------------------------------------------------------------------

    stats = migrar_medicos()

    # ----------------------------------------------------------------------
    # VERIFICAR
    # ----------------------------------------------------------------------

    verificar_migracion()

    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL DE MIGRACIÓN")
    print("=" * 80)

    print(f"Total procesados:    {stats['total']:,}")
    print(f"Migrados exitosos:   {stats['exitosos']:,}")
    print(f"Omitidos:            {stats['omitidos']:,}")
    print(f"Errores:             {stats['errores']:,}")

    print(
        f"Tiempo total: "
        f"{stats.get('tiempo', 0):.2f} segundos"
    )

    print("=" * 80)

    if stats["advertencias"]:

        print(
            f"\n⚠️ ADVERTENCIAS "
            f"({len(stats['advertencias'])}):"
        )

        for adv in stats["advertencias"][:20]:
            print(f"   • {adv}")

        if len(stats["advertencias"]) > 20:
            print(
                f"   ... y "
                f"{len(stats['advertencias']) - 20} más."
            )

    print()

    print(
        "💡 Siguiente paso: "
        "ejecutar migrate_constancias.py"
    )

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