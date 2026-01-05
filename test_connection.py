#!/usr/bin/env python3
"""
Script de diagnóstico para probar conexiones a bases de datos
"""

import os
import sys
from dotenv import load_dotenv

# Cargar .env
load_dotenv()

print("🔍 Diagnóstico de Conexiones a Bases de Datos")
print("=" * 70)

# 1. Verificar dependencias
print("\n1️⃣ Verificando dependencias instaladas...")
dependencias = {
    "sqlalchemy": None,
    "pymysql": None,
    "psycopg2": None,
    "cryptography": None,
    "dotenv": None
}

for dep in dependencias:
    try:
        if dep == "dotenv":
            __import__("dotenv")
        else:
            __import__(dep)
        dependencias[dep] = "✅ Instalado"
    except ImportError:
        dependencias[dep] = "❌ NO INSTALADO"

for dep, status in dependencias.items():
    print(f"   {dep:15s}: {status}")

# Verificar si falta algo
faltantes = [dep for dep, status in dependencias.items() if "NO INSTALADO" in status]
if faltantes:
    print(f"\n❌ Faltan dependencias: {', '.join(faltantes)}")
    print(f"   Ejecuta: pip install {' '.join(faltantes)}")
    sys.exit(1)

print("\n✅ Todas las dependencias están instaladas")

# 2. Verificar variables de entorno
print("\n2️⃣ Verificando variables de entorno...")

# Función para construir URLs
def construir_url_mysql():
    if os.getenv("MYSQL_URL"):
        return os.getenv("MYSQL_URL")
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DATABASE", "test_api")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

def construir_url_postgres():
    if os.getenv("POSTGRES_URL"):
        return os.getenv("POSTGRES_URL")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "hospital")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

MYSQL_URL = construir_url_mysql()
POSTGRES_URL = construir_url_postgres()

# Mostrar configuración (sin passwords)
print("\n   MySQL:")
print(f"      Host: {os.getenv('MYSQL_HOST', 'localhost')}")
print(f"      Port: {os.getenv('MYSQL_PORT', '3306')}")
print(f"      User: {os.getenv('MYSQL_USER', 'root')}")
print(f"      Database: {os.getenv('MYSQL_DATABASE', 'test_api')}")

print("\n   PostgreSQL:")
print(f"      Host: {os.getenv('POSTGRES_HOST', 'localhost')}")
print(f"      Port: {os.getenv('POSTGRES_PORT', '5432')}")
print(f"      User: {os.getenv('POSTGRES_USER', 'postgres')}")
print(f"      Database: {os.getenv('POSTGRES_DB', 'hospital')}")

# 3. Probar conexión a MySQL
print("\n3️⃣ Probando conexión a MySQL...")
try:
    from sqlalchemy import create_engine, text
    mysql_engine = create_engine(MYSQL_URL)
    with mysql_engine.connect() as conn:
        result = conn.execute(text("SELECT VERSION()")).scalar()
        print(f"   ✅ Conectado a MySQL {result}")
except Exception as e:
    print(f"   ❌ Error al conectar a MySQL: {e}")
    print("\n💡 Soluciones posibles:")
    print("   1. Verifica usuario y contraseña en .env")
    print("   2. Verifica que MySQL esté corriendo: mysql -u root -p")
    print("   3. Verifica el nombre de la base de datos")
    print("   4. Instala cryptography: pip install cryptography")
    sys.exit(1)

# 4. Probar conexión a PostgreSQL
print("\n4️⃣ Probando conexión a PostgreSQL...")
try:
    from sqlalchemy import create_engine, text
    postgres_engine = create_engine(POSTGRES_URL)
    with postgres_engine.connect() as conn:
        result = conn.execute(text("SELECT version()")).scalar()
        print(f"   ✅ Conectado a PostgreSQL")
        print(f"      {result[:60]}...")
except Exception as e:
    print(f"   ❌ Error al conectar a PostgreSQL: {e}")
    print("\n💡 Soluciones posibles:")
    print("   1. Verifica usuario y contraseña en .env")
    print("   2. Verifica que PostgreSQL esté corriendo")
    print("   3. Verifica el nombre de la base de datos")
    print("   4. Crea la base de datos si no existe:")
    print(f"      createdb -U {os.getenv('POSTGRES_USER', 'postgres')} {os.getenv('POSTGRES_DB', 'hospital')}")
    sys.exit(1)

# 5. Listar tablas disponibles
print("\n5️⃣ Listando tablas disponibles...")

print("\n   📊 MySQL:")
try:
    with mysql_engine.connect() as conn:
        result = conn.execute(text("SHOW TABLES"))
        tablas = [row[0] for row in result]
        if tablas:
            print(f"      Encontradas {len(tablas)} tablas:")
            for tabla in tablas[:10]:  # Mostrar máximo 10
                # Contar registros
                count = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
                print(f"      - {tabla:30s} ({count:,} registros)")
            if len(tablas) > 10:
                print(f"      ... y {len(tablas) - 10} más")
        else:
            print("      ⚠️  No hay tablas")
except Exception as e:
    print(f"      ❌ Error: {e}")

print("\n   📊 PostgreSQL:")
try:
    with postgres_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
        """))
        tablas = [row[0] for row in result]
        if tablas:
            print(f"      Encontradas {len(tablas)} tablas:")
            for tabla in tablas[:10]:  # Mostrar máximo 10
                # Contar registros
                count = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
                print(f"      - {tabla:30s} ({count:,} registros)")
            if len(tablas) > 10:
                print(f"      ... y {len(tablas) - 10} más")
        else:
            print("      ⚠️  No hay tablas (base de datos vacía)")
except Exception as e:
    print(f"      ❌ Error: {e}")

print("\n" + "=" * 70)
print("🎉 Diagnóstico completado exitosamente!")
print("\n✅ Ambas bases de datos están accesibles")
print("✅ Puedes ejecutar la migración con: python migrate.py")
print("=" * 70)