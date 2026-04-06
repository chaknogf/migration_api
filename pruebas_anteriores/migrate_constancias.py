#!/usr/bin/env python3
# migrate_nacimientos_legacy.py
"""
Migración directa de cons_nac (MySQL) → nacimientos_legacy (PostgreSQL)
Copia los datos tal cual, sin transformaciones ni FKs.
Solo convierte timedelta → string para el campo hora.
"""

import os
import sys
from datetime import datetime, timedelta, date, time as dt_time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONEXIONES
# ============================================================================

def construir_url_mysql():
    return (
        f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:"
        f"{os.getenv('MYSQL_PASSWORD', 'Prometeus.0')}@"
        f"{os.getenv('MYSQL_HOST', 'localhost')}:"
        f"{os.getenv('MYSQL_PORT', '3306')}/"
        f"{os.getenv('MYSQL_DATABASE', 'test_api')}"
    )

def construir_url_postgres():
    return (
        f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'secreto123')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'hospital')}"
    )

MYSQL_URL    = construir_url_mysql()
POSTGRES_URL = construir_url_postgres()

print("=" * 70)
print("📋  MIGRACIÓN LEGACY: cons_nac → nacimientos_legacy")
print("=" * 70)

print("\n🔌 Conectando...")
try:
    mysql_engine    = create_engine(MYSQL_URL, echo=False)
    postgres_engine = create_engine(POSTGRES_URL, echo=False)
    MySQLSession    = sessionmaker(bind=mysql_engine)
    PostgresSession = sessionmaker(bind=postgres_engine)
    with mysql_engine.connect()    as c: c.execute(text("SELECT 1"))
    with postgres_engine.connect() as c: c.execute(text("SELECT 1"))
    print("✅ Conexiones OK\n")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)


# ============================================================================
# NORMALIZACIÓN MÍNIMA
# ============================================================================

def normalizar_fila(row: dict) -> dict:
    """
    Convierte tipos Python no soportados por psycopg2:
    - timedelta → 'HH:MM:SS'  (campo hora de MySQL)
    - Otros tipos se pasan tal cual.
    """
    resultado = {}
    for k, v in row.items():
        if isinstance(v, timedelta):
            total = int(v.total_seconds())
            h, rem = divmod(abs(total), 3600)
            m, s   = divmod(rem, 60)
            resultado[k] = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            resultado[k] = v
    return resultado


# ============================================================================
# MIGRACIÓN
# ============================================================================

def migrar(batch_size: int = 500):
    mysql_db = MySQLSession()
    pg_db    = PostgresSession()

    stats = {"total": 0, "exitosos": 0, "errores": 0}
    inicio = datetime.now()

    try:
        filas = mysql_db.execute(text("SELECT * FROM cons_nac")).fetchall()
        stats["total"] = len(filas)
        print(f"📦 Registros encontrados: {stats['total']:,}")

        # Construir INSERT dinámico con las columnas reales de MySQL
        if not filas:
            print("ℹ️  Sin registros.")
            return stats

        columnas = list(filas[0]._mapping.keys())
        insert_sql = text(f"""
            INSERT INTO nacimientos_legacy ({', '.join(columnas)})
            VALUES ({', '.join(':' + c for c in columnas)})
            ON CONFLICT (doc) DO NOTHING
        """)

        batch = []

        for i, fila in enumerate(filas, 1):
            row = normalizar_fila(dict(fila._mapping))
            batch.append(row)

            if i % batch_size == 0:
                try:
                    pg_db.execute(insert_sql, batch)
                    pg_db.commit()
                    stats["exitosos"] += len(batch)
                    print(f"   ✅ {i:>5}/{stats['total']}")
                except Exception as e:
                    pg_db.rollback()
                    stats["errores"] += len(batch)
                    print(f"   ❌ Batch fallido en {i}: {e}")
                batch = []

        # Batch final
        if batch:
            try:
                pg_db.execute(insert_sql, batch)
                pg_db.commit()
                stats["exitosos"] += len(batch)
                print(f"   ✅ Batch final ({len(batch)} registros)")
            except Exception as e:
                pg_db.rollback()
                stats["errores"] += len(batch)
                print(f"   ❌ Batch final fallido: {e}")

    finally:
        mysql_db.close()
        pg_db.close()

    stats["tiempo"] = (datetime.now() - inicio).total_seconds()
    return stats


# ============================================================================
# VERIFICACIÓN
# ============================================================================

def verificar():
    mysql_db = MySQLSession()
    pg_db    = PostgresSession()
    try:
        total_mysql = mysql_db.execute(text("SELECT COUNT(*) FROM cons_nac")).scalar()
        total_pg    = pg_db.execute(text("SELECT COUNT(*) FROM nacimientos_legacy")).scalar()
        print(f"\n📊 Verificación:")
        print(f"   MySQL (cons_nac):           {total_mysql:,}")
        print(f"   PostgreSQL (legacy):        {total_pg:,}")
        print(f"   Diferencia:                 {total_mysql - total_pg:,}")
    finally:
        mysql_db.close()
        pg_db.close()


# ============================================================================
# MAIN
# ============================================================================

def main():
    stats = migrar()
    verificar()

    print("\n" + "=" * 70)
    print("📊 RESUMEN FINAL")
    print("=" * 70)
    print(f"Total procesados:  {stats['total']:,}")
    print(f"Exitosos:          {stats['exitosos']:,}")
    print(f"Errores:           {stats['errores']:,}")
    print(f"Tiempo:            {stats.get('tiempo', 0):.2f} s")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Cancelado")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)