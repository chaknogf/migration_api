#!/usr/bin/env python3
# backup_postgres_remote.py

"""
Backup PostgreSQL + compresión GZIP + envío SCP

✔ Genera:
    hospital_backup.sql

✔ Comprime:
    hospital_backup.sql.gz

✔ Envía automáticamente:
    hospital_backup.sql.gz

✔ Muestra progreso SCP

✔ Reduce muchísimo el tamaño del backup

Requisitos:
    sudo dnf install postgresql openssh-clients
o
    sudo apt install postgresql-client openssh-client
"""

import os
import sys
import gzip
import shutil
import subprocess

from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# ============================================================================
# LOAD ENV
# ============================================================================

load_dotenv()

# ============================================================================
# CONFIG POSTGRES
# ============================================================================

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "secreto123")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "hospital")

# ============================================================================
# CONFIG ARCHIVOS
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent

SQL_FILENAME = "hospital_backup.sql"
GZ_FILENAME = "hospital_backup.sql.gz"

SQL_PATH = BASE_DIR / SQL_FILENAME
GZ_PATH = BASE_DIR / GZ_FILENAME

# ============================================================================
# CONFIG SCP
# ============================================================================

REMOTE_USER = "matrix"
REMOTE_HOST = "200.12.44.174"
REMOTE_PORT = "2222"

REMOTE_PATH = "/home/matrix/"

# ============================================================================
# UTILIDADES
# ============================================================================

def verificar_dependencias():

    if shutil.which("pg_dump") is None:
        print("❌ pg_dump no está instalado")
        sys.exit(1)

    if shutil.which("scp") is None:
        print("❌ scp no está instalado")
        sys.exit(1)


def mostrar_info():

    print("=" * 80)
    print("🛡️ BACKUP POSTGRESQL + GZIP + SCP")
    print("=" * 80)

    print(f"📦 Base de datos : {POSTGRES_DB}")
    print(f"🖥️ Host DB       : {POSTGRES_HOST}")
    print(f"👤 Usuario DB    : {POSTGRES_USER}")

    print()

    print(f"📄 SQL           : {SQL_FILENAME}")
    print(f"🗜️ GZIP          : {GZ_FILENAME}")

    print()

    print("🚀 Destino SCP")
    print(f"👤 Usuario       : {REMOTE_USER}")
    print(f"🌐 Host          : {REMOTE_HOST}")
    print(f"🔌 Puerto        : {REMOTE_PORT}")
    print(f"📁 Ruta          : {REMOTE_PATH}")

    print("=" * 80)
    print()


# ============================================================================
# CREAR BACKUP
# ============================================================================

def crear_backup():

    print("🚀 Generando backup PostgreSQL...")
    print()

    env = os.environ.copy()
    env["PGPASSWORD"] = POSTGRES_PASSWORD

    comando = [
        "pg_dump",
        "-h", POSTGRES_HOST,
        "-p", POSTGRES_PORT,
        "-U", POSTGRES_USER,
        "-F", "p",
        "-d", POSTGRES_DB,
        "-f", str(SQL_PATH),
        "--clean",
        "--if-exists",
        "--create",
    ]

    resultado = subprocess.run(
        comando,
        env=env,
        capture_output=True,
        text=True
    )

    if resultado.returncode != 0:

        print("❌ Error creando backup")
        print()
        print(resultado.stderr)

        sys.exit(1)

    tamaño = SQL_PATH.stat().st_size / (1024 * 1024)

    print("✅ Backup SQL generado")
    print(f"📄 Archivo: {SQL_FILENAME}")
    print(f"📦 Tamaño : {tamaño:.2f} MB")
    print()


# ============================================================================
# COMPRIMIR
# ============================================================================

def comprimir_backup():

    print("🗜️ Comprimiendo backup...")
    print()

    try:

        with open(SQL_PATH, "rb") as f_in:
            with gzip.open(GZ_PATH, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        tamaño_sql = SQL_PATH.stat().st_size / (1024 * 1024)
        tamaño_gz = GZ_PATH.stat().st_size / (1024 * 1024)

        reduccion = (
            (1 - (tamaño_gz / tamaño_sql)) * 100
        )

        print("✅ Backup comprimido")
        print()

        print(f"📄 SQL : {tamaño_sql:.2f} MB")
        print(f"🗜️ GZ  : {tamaño_gz:.2f} MB")
        print(f"📉 Reducción: {reduccion:.2f}%")
        print()

        # eliminar sql original
        SQL_PATH.unlink()

        print("🧹 SQL original eliminado")
        print()

    except Exception as e:

        print(f"❌ Error comprimiendo backup: {e}")
        sys.exit(1)


# ============================================================================
# ENVIAR SCP
# ============================================================================

def enviar_backup():

    print("📡 Enviando backup comprimido por SCP...")
    print()

    destino = (
        f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}"
    )

    comando = [
        "scp",
        "-P",
        REMOTE_PORT,
        str(GZ_PATH),
        destino
    ]

    # IMPORTANTE:
    # NO usamos capture_output para ver progreso real
    resultado = subprocess.run(comando)

    if resultado.returncode != 0:

        print()
        print("❌ Error enviando backup")
        sys.exit(1)

    print()
    print("✅ Backup enviado correctamente")
    print()

    print(
        f"📡 Destino: "
        f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}"
    )

    print()


# ============================================================================
# RESTORE
# ============================================================================

def mostrar_restore():

    print("=" * 80)
    print("♻️ RESTAURAR BACKUP")
    print("=" * 80)
    print()

    print("1️⃣ Descomprimir:")
    print()
    print("   gunzip hospital_backup.sql.gz")
    print()

    print("2️⃣ Restaurar:")
    print()

    print(
        f"   psql "
        f"-U {POSTGRES_USER} "
        f"-h {POSTGRES_HOST} "
        f"-p {POSTGRES_PORT} "
        f"-f hospital_backup.sql"
    )

    print()
    print("=" * 80)
    print()


# ============================================================================
# MAIN
# ============================================================================

def main():

    inicio = datetime.now()

    verificar_dependencias()

    mostrar_info()

    crear_backup()

    comprimir_backup()

    enviar_backup()

    tiempo = (
        datetime.now() - inicio
    ).total_seconds()

    print("=" * 80)
    print("✅ PROCESO FINALIZADO")
    print("=" * 80)

    print(f"⏱️ Tiempo total : {tiempo:.2f} segundos")
    print(f"🗜️ Archivo final: {GZ_FILENAME}")

    print("=" * 80)
    print()

    mostrar_restore()


# ============================================================================
# ENTRYPOINT
# ============================================================================

if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        print("\n❌ Proceso cancelado por usuario")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        sys.exit(1)