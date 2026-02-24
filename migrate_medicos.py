#!/usr/bin/env python3
# migrate_medicos.py
"""
Script de migración específico para tabla MÉDICOS
Transforma estructura relacional MySQL -> PostgreSQL
medicos (MySQL) → medicos (PostgreSQL)

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
# especialidad en MySQL es un INT (id), lo mapeamos a texto legible.
# Ajusta este diccionario según tu catálogo real.
# ============================================================================

ESPECIALIDADES = {
    1:  "Medicina General",
    2:  "Pediatría",
    3:  "Ginecología y Obstetricia",
    4:  "Cirugía General",
    5:  "Medicina Interna",
    6:  "Anestesiología",
    7:  "Radiología",
    8:  "Traumatología",
    9:  "Cardiología",
    10: "Neurología",
    11: "Dermatología",
    12: "Oftalmología",
    13: "Psiquiatría",
    14: "Urología",
    15: "Otorrinolaringología",
    # Agrega más según tu catálogo...
}

# ============================================================================
# NORMALIZADORES
# ============================================================================

COLEGIADOS_VISTOS: set = set()
DPIS_VISTOS:       set = set()


def normalizar_nombre(name: Any) -> str:
    """Limpia y capitaliza el nombre del médico."""
    if not name or not str(name).strip():
        return "SIN NOMBRE"
    return " ".join(str(name).strip().title().split())


def normalizar_colegiado(colegiado: Any, id_mysql: Any) -> Optional[str]:
    """
    Convierte el colegiado int de MySQL a varchar(20) de Postgres.
    Si está duplicado, lo marca con sufijo para no violar el índice único (si lo hay).
    """
    if not colegiado:
        return None

    col_str = str(int(colegiado)).strip()

    if col_str in COLEGIADOS_VISTOS:
        col_nuevo = f"{col_str}-DUP-{id_mysql}"
        print(f"   ⚠️  Colegiado duplicado: '{col_str}' → '{col_nuevo}'")
        COLEGIADOS_VISTOS.add(col_nuevo)
        return col_nuevo

    COLEGIADOS_VISTOS.add(col_str)
    return col_str


def normalizar_dpi(dpi: Any, id_mysql: Any) -> Optional[int]:
    """Valida que el DPI sea numérico y único."""
    if not dpi:
        return None

    try:
        dpi_int = int(str(dpi).strip())
    except ValueError:
        print(f"   ⚠️  DPI inválido para id={id_mysql}: '{dpi}' → ignorado")
        return None

    if dpi_int in DPIS_VISTOS:
        print(f"   ⚠️  DPI duplicado: {dpi_int} (id={id_mysql}) → guardado como NULL")
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


def normalizar_especialidad(especialidad_id: Any, id_mysql: Any) -> Optional[str]:
    """
    Convierte el id entero de especialidad a texto usando el catálogo.
    Si no existe en el catálogo, retorna el id como string para no perder info.
    """
    if not especialidad_id:
        return None

    try:
        eid = int(especialidad_id)
    except (ValueError, TypeError):
        return None

    nombre = ESPECIALIDADES.get(eid)
    if nombre is None:
        print(f"   ⚠️  Especialidad desconocida id={eid} (médico mysql_id={id_mysql}) → guardada como 'Especialidad {eid}'")
        return f"Especialidad {eid}"

    return nombre


# ============================================================================
# TRANSFORMACIÓN PRINCIPAL
# ============================================================================

def transformar_medico(row: Any) -> tuple[dict, list[str]]:
    """
    Transforma un registro de medicos (MySQL) al formato de medicos (PostgreSQL).
    Retorna (registro_dict, lista_de_advertencias).
    """
    advertencias = []

    if not isinstance(row, dict):
        row = dict(row._mapping)

    id_mysql = row.get("id")

    nombre = normalizar_nombre(row.get("name"))
    if nombre == "SIN NOMBRE":
        advertencias.append(f"[id={id_mysql}] sin nombre")

    colegiado = normalizar_colegiado(row.get("colegiado"), id_mysql)
    if colegiado is None:
        advertencias.append(f"[id={id_mysql}] sin colegiado")

    dpi = normalizar_dpi(row.get("dpi"), id_mysql)

    sexo = normalizar_sexo(row.get("sexo"))

    especialidad = normalizar_especialidad(row.get("especialidad"), id_mysql)

    registro = {
        "nombre":       nombre,
        "colegiado":    colegiado,
        "dpi":          dpi,
        "sexo":         sexo,
        "especialidad": especialidad,
        "activo":       True,   # todos activos por defecto al migrar
        "created_at":   row.get("created_at") or datetime.now(),
        # guardamos mysql_id en una columna temporal si la agregas,
        # o simplemente lo omitimos ya que Postgres genera su propio id.
    }

    return registro, advertencias


# ============================================================================
# CONFIGURACIÓN DE CONEXIONES
# ============================================================================

def construir_url_mysql():
    return (
        f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:"
        f"{os.getenv('MYSQL_PASSWORD', '')}@"
        f"{os.getenv('MYSQL_HOST', 'localhost')}:"
        f"{os.getenv('MYSQL_PORT', '3306')}/"
        f"{os.getenv('MYSQL_DATABASE', 'hospital')}"
    )

def construir_url_postgres():
    return (
        f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', '')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'hospital')}"
    )

MYSQL_URL    = construir_url_mysql()
POSTGRES_URL = construir_url_postgres()

print("=" * 80)
print("👨‍⚕️  MIGRACIÓN DE MÉDICOS: MySQL → PostgreSQL")
print("=" * 80)
print(f"Origen  (MySQL):      {MYSQL_URL.split('@')[1]}")
print(f"Destino (PostgreSQL): {POSTGRES_URL.split('@')[1]}")
print("=" * 80)

print("\n🔌 Conectando a bases de datos...")
try:
    mysql_engine    = create_engine(MYSQL_URL, echo=False)
    postgres_engine = create_engine(POSTGRES_URL, echo=False)

    MySQLSession    = sessionmaker(bind=mysql_engine)
    PostgresSession = sessionmaker(bind=postgres_engine)

    with mysql_engine.connect()    as c: c.execute(text("SELECT 1"))
    with postgres_engine.connect() as c: c.execute(text("SELECT 1"))

    print("✅ Conexiones establecidas\n")
except Exception as e:
    print(f"❌ Error al conectar: {e}")
    sys.exit(1)


# ============================================================================
# QUERY DE INSERCIÓN
# ============================================================================

INSERT_QUERY = text("""
INSERT INTO medicos (
    nombre, colegiado, dpi, sexo, especialidad, activo, created_at
) VALUES (
    :nombre, :colegiado, :dpi, :sexo, :especialidad, :activo, :created_at
)
ON CONFLICT DO NOTHING
""")


# ============================================================================
# MIGRACIÓN
# ============================================================================

def migrar_medicos(batch_size: int = 200) -> dict:
    mysql_db    = MySQLSession()
    postgres_db = PostgresSession()

    stats = {
        "total":        0,
        "exitosos":     0,
        "errores":      0,
        "advertencias": [],
    }
    inicio = datetime.now()

    try:
        filas = mysql_db.execute(text("SELECT * FROM medicos")).fetchall()
        stats["total"] = len(filas)
        print(f"📋 Total de médicos a migrar: {stats['total']:,}\n")

        batch = []

        for i, fila in enumerate(filas, 1):
            try:
                registro, advertencias = transformar_medico(fila)

                if advertencias:
                    stats["advertencias"].extend(advertencias)
                    for adv in advertencias:
                        print(f"   ⚠️  {adv}")

                batch.append(registro)

                if i % batch_size == 0:
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
                msg = f"Error en fila {i} (id={fila._mapping.get('id')}): {e}"
                stats["advertencias"].append(msg)
                print(f"   ❌ {msg}")

        # Batch final
        if batch:
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
            text("SELECT COUNT(*) FROM medicos WHERE colegiado IS NULL")
        ).scalar()
        sin_dpi = postgres_db.execute(
            text("SELECT COUNT(*) FROM medicos WHERE dpi IS NULL")
        ).scalar()
        print(f"\n   Sin colegiado: {sin_colegiado:,}")
        print(f"   Sin DPI:       {sin_dpi:,}")

        print(f"\n   Distribución por especialidad:")
        especialidades = postgres_db.execute(text("""
            SELECT especialidad, COUNT(*) AS total
            FROM medicos
            GROUP BY especialidad
            ORDER BY total DESC
            LIMIT 10
        """)).fetchall()
        for esp, cnt in especialidades:
            print(f"   → {esp or 'Sin especialidad':<30} {cnt:>5}")

        print(f"\n   Últimos 5 médicos migrados:")
        ultimos = postgres_db.execute(text("""
            SELECT id, nombre, colegiado, especialidad
            FROM medicos
            ORDER BY id DESC LIMIT 5
        """)).fetchall()
        for r in ultimos:
            print(f"   → [{r[0]:>5}] {r[1]:<30} | col: {r[2]:<10} | {r[3]}")

    finally:
        mysql_db.close()
        postgres_db.close()


# ============================================================================
# MAIN
# ============================================================================

def main():
    stats = migrar_medicos()
    verificar_migracion()

    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL DE MIGRACIÓN")
    print("=" * 80)
    print(f"Total procesados:    {stats['total']:,}")
    print(f"Migrados exitosos:   {stats['exitosos']:,}")
    print(f"Errores:             {stats['errores']:,}")
    print(f"Tiempo total:        {stats.get('tiempo', 0):.2f} segundos")
    print("=" * 80)

    if stats["advertencias"]:
        print(f"\n⚠️  ADVERTENCIAS ({len(stats['advertencias'])}):")
        for adv in stats["advertencias"][:20]:
            print(f"   • {adv}")
        if len(stats["advertencias"]) > 20:
            print(f"   ... y {len(stats['advertencias']) - 20} más.")
    print()

    print("💡 Siguiente paso: ejecutar migrate_constancias.py")
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