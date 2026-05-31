#!/usr/bin/env python3
# migrate_procedimientos.py
"""
Migración procedimientos + proce_medicos: MySQL → PostgreSQL

Fase 1 — MySQL (preparación y normalización):
  1. Backup:  proce_medicos → proce_medicos_backup
  2. Catálogo: DROP + CREATE procedimientos, INSERT desde definición interna
  3. Normalización: proce_medicos_backup → proce_medicos_master
       abreviatura/procedimiento → id_procedimiento (FK)
       abreviaturas desconocidas → se agregan al catálogo automáticamente

Fase 2 — PostgreSQL (migración limpia):
  4. DROP + CREATE procedimientos  → datos desde MySQL
  5. DROP + CREATE proce_medicos   → datos desde proce_medicos_master

⚠️  Ejecutar DESPUÉS de migrate_medicos.py
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
# CATÁLOGO DE PROCEDIMIENTOS
# Espejo exacto de migration_api/sql/procedimientos.sql
# (abreviatura, nombre, descripcion, anestesia)
# ============================================================================

PROCEDIMIENTOS_CATALOGO = [
    ("CCUV",   "Catéter Umbilical Venoso",           "Colocación de catéter umbilical venoso",                0),
    ("CCUA",   "Catéter Umbilical Arterial",          "Colocación de catéter umbilical arterial",              0),
    ("CVC",    "Vía Central",                         "Colocación de acceso venoso central",                   0),
    ("RVC",    "Retiro de Vía Central",               "Retiro de acceso venoso central",                       0),
    ("SONDA",  "Colocación de Sonda",                 "Colocación de sonda orogástrica o Foley",               0),
    ("IOT",    "Intubación Endotraqueal",             "Colocación de tubo endotraqueal u orotraqueal",         0),
    ("SURF",   "Administración de Surfactante",       "Aplicación de surfactante pulmonar",                    0),
    ("RCP",    "Reanimación Cardiopulmonar",          "Maniobras de reanimación cardiopulmonar",               0),
    ("IO",     "Acceso Intraóseo",                    "Colocación de acceso intraóseo",                        0),
    ("VENO",   "Venodisección",                       "Acceso venoso mediante venodisección",                  0),
    ("CURA",   "Curación de Heridas",                 "Curación simple o compleja de heridas",                 0),
    ("VAC",    "Manejo de VAC",                       "Colocación, cambio o retiro de sistema VAC",            0),
    ("SUT",    "Sutura de Herida",                    "Sutura y cierre de heridas",                            0),
    ("LYD",    "Lavado y Debridamiento",              "Lavado quirúrgico y debridamiento",                     0),
    ("DREAB",  "Drenaje de Absceso",                  "Drenaje de abscesos y colecciones",                     0),
    ("DREH",   "Drenaje de Hematoma",                 "Drenaje de hematomas",                                  0),
    ("DREQ",   "Drenaje de Quiste",                   "Drenaje de quistes",                                    0),
    ("RETPT",  "Retiro de Puntos",                    "Retiro de puntos de sutura",                            0),
    ("RETGR",  "Retiro de Grapas",                    "Retiro de grapas quirúrgicas",                          0),
    ("RETVD",  "Retiro de Vendaje",                   "Retiro o cambio de vendajes",                           0),
    ("RETCN",  "Retiro de Canales",                   "Retiro de drenajes o canales",                          0),
    ("BIOP",   "Biopsia",                             "Toma de biopsias de cualquier localización",            0),
    ("EXCQ",   "Escisión de Quiste",                  "Resección de quistes",                                  0),
    ("EXCM",   "Escisión de Masa",                    "Resección de masas, tumores o lipomas",                 0),
    ("TENO",   "Tenorrafia",                          "Reparación quirúrgica de tendones",                     1),
    ("TENOT",  "Tenotomía",                           "Sección quirúrgica de tendón",                          1),
    ("INJPI",  "Injerto de Piel",                     "Toma y colocación de injerto cutáneo",                  1),
    ("OST",    "Osteosíntesis",                       "Fijación quirúrgica de fracturas",                      1),
    ("RETMO",  "Retiro de Material de Osteosíntesis", "Retiro de clavos, placas o tornillos",                  0),
    ("FIJEX",  "Fijador Externo",                     "Colocación de fijador externo",                         1),
    ("RETFI",  "Retiro de Fijador",                   "Retiro de fijador externo",                             0),
    ("MANC",   "Manipulación Cerrada",                "Reducción o manipulación cerrada",                      0),
    ("ARTC",   "Artrocentesis",                       "Punción articular diagnóstica o terapéutica",           0),
    ("ARTP",   "Artroplastia",                        "Reemplazo articular",                                   1),
    ("ARTD",   "Artrodesis",                          "Fijación quirúrgica articular",                         1),
    ("OSTEO",  "Osteotomía",                          "Corte quirúrgico de hueso",                             1),
    ("AMP",    "Amputación",                          "Amputación de extremidad o segmento",                   1),
    ("CARPO",  "Liberación de Túnel del Carpo",       "Descompresión del nervio mediano",                      1),
    ("APEN",   "Apendicectomía",                      "Resección quirúrgica del apéndice",                     1),
    ("COLE",   "Colecistectomía",                     "Resección de vesícula biliar",                          1),
    ("LAPE",   "Laparotomía Exploratoria",            "Exploración quirúrgica abdominal",                      1),
    ("HERN",   "Herniorrafia/Hernioplastia",          "Reparación quirúrgica de hernia",                       1),
    ("HEMO",   "Hemorroidectomía",                    "Resección quirúrgica de hemorroides",                   1),
    ("PARA",   "Paracentesis",                        "Punción evacuadora abdominal",                          0),
    ("TORA",   "Toracentesis",                        "Punción evacuadora pleural",                            0),
    ("CES",    "Cesárea",                             "Parto por vía abdominal",                               1),
    ("PARTO",  "Parto Vaginal",                       "Parto eutócico",                                        1),
    ("AMEU",   "AMEU",                                "Aspiración Manual Endouterina",                         1),
    ("LEGR",   "Legrado Uterino",                     "Legrado instrumental uterino",                          1),
    ("HIST",   "Histerectomía",                       "Extirpación quirúrgica del útero",                      1),
    ("MIOM",   "Miomectomía",                         "Resección de miomas uterinos",                          1),
    ("OOF",    "Ooforectomía",                        "Resección de ovario",                                   1),
    ("CISTE",  "Cistectomía",                         "Resección de quiste",                                   1),
    ("CERC",   "Cerclaje Cervical",                   "Cerclaje del cuello uterino",                           1),
    ("EPIS",   "Episiotomía",                         "Incisión perineal obstétrica",                          0),
    ("COLPA",  "Colporrafia",                         "Reparación de pared vaginal",                           1),
    ("BAKRI",  "Balón de Bakri",                      "Colocación de balón hemostático uterino",               0),
    ("BLYN",   "Sutura B-Lynch",                      "Sutura compresiva uterina",                             0),
    ("OTB",    "Oclusión Tubárica Bilateral",         "Esterilización femenina",                               1),
    ("DIU",    "Colocación de DIU",                   "Inserción de dispositivo intrauterino",                 0),
    ("RDIU",   "Retiro de DIU",                       "Retiro de dispositivo intrauterino",                    0),
    ("JADEL",  "Implante Jadelle",                    "Colocación o retiro de Jadelle",                        0),
    ("PAP",    "Papanicolaou",                        "Citología cervical",                                    0),
    ("COLPO",  "Colposcopía",                         "Evaluación colposcópica",                               0),
    ("BIOCER", "Biopsia Cervical",                    "Biopsia de cuello uterino",                             1),
    ("ORQP",   "Orquidopexia",                        "Corrección quirúrgica de testículo no descendido",      1),
    ("ORQ",    "Orquiectomía",                        "Resección de testículo",                                1),
    ("HIDR",   "Hidrocelectomía",                     "Corrección de hidrocele",                               1),
    ("POST",   "Postectomía",                         "Circuncisión",                                          1),
    ("PROS",   "Prostatectomía",                      "Resección de próstata",                                 1),
    ("FAST",   "FAST",                                "Ultrasonido FAST para trauma",                          0),
    ("USG",    "Ultrasonido",                         "Estudio ultrasonográfico",                              0),
    ("RX",     "Radiografía",                         "Estudio radiológico convencional",                      0),
    ("TAC",    "Tomografía Computarizada",            "Tomografía axial computarizada",                        0),
    ("RMN",    "Resonancia Magnética",                "Resonancia magnética nuclear",                          0),
    ("DOP",    "Doppler",                             "Ultrasonido Doppler",                                   0),
    ("ANGIO",  "Angiografía",                         "Estudio angiográfico",                                  0),
    ("ECG",    "Electrocardiograma",                  "Registro de actividad eléctrica cardíaca",              0),
    ("EMG",    "Electromiografía",                    "Estudio electrofisiológico muscular",                   0),
    ("CENT",   "Centellograma",                       "Estudio gammagráfico",                                  0),
    ("GASO",   "Gasometría",                          "Análisis de gases sanguíneos",                         0),
    ("HEMC",   "Hemocultivo",                         "Cultivo de sangre",                                     0),
    ("HISP",   "Hisopado",                            "Toma de muestra por hisopado",                         0),
    ("GLUC",   "Glucometría",                         "Medición de glucosa capilar",                          0),
    ("FOTO",   "Fototerapia",                         "Tratamiento mediante fototerapia",                     0),
    ("YESO",   "Colocación de Yeso",                  "Inmovilización con yeso",                              0),
    ("RETY",   "Retiro de Yeso",                      "Retiro de inmovilización en yeso",                     0),
    ("INFIL",  "Infiltración",                        "Aplicación terapéutica mediante infiltración",         0),
    ("ANES",   "Procedimiento con Anestesia",         "Procedimiento realizado bajo anestesia",               0),
]

# ============================================================================
# CONEXIONES
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

MYSQL_URL    = construir_url_mysql()
POSTGRES_URL = construir_url_postgres()

print("=" * 80)
print("🏥 MIGRACIÓN: procedimientos + proce_medicos → PostgreSQL")
print("=" * 80)
print(f"Origen  (MySQL):      {MYSQL_URL.split('@')[1]}")
print(f"Destino (PostgreSQL): {POSTGRES_URL.split('@')[1]}")
print("=" * 80)

print("\n🔌 Conectando a bases de datos...")
try:
    mysql_engine    = create_engine(MYSQL_URL,    echo=False)
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
# FASE 1-A — BACKUP proce_medicos en MySQL
# ============================================================================

def mysql_backup_proce_medicos():
    db = MySQLSession()
    try:
        print("=" * 80)
        print("💾 FASE 1-A: BACKUP proce_medicos → proce_medicos_backup")
        print("=" * 80)

        db.execute(text("DROP TABLE IF EXISTS proce_medicos_backup"))
        db.execute(text("""
            CREATE TABLE proce_medicos_backup
            AS SELECT * FROM proce_medicos
        """))
        db.commit()

        total = db.execute(
            text("SELECT COUNT(*) FROM proce_medicos_backup")
        ).scalar()

        print(f"✅ Backup creado: {total:,} registros\n")

    except Exception as e:
        db.rollback()
        print(f"❌ Error en backup: {e}")
        raise
    finally:
        db.close()


# ============================================================================
# FASE 1-B — Recrear procedimientos en MySQL con catálogo limpio
# ============================================================================

def mysql_recrear_procedimientos():
    """
    DROP + CREATE procedimientos en MySQL usando el catálogo interno
    (equivalente a ejecutar migration_api/sql/procedimientos.sql).
    """
    db = MySQLSession()
    try:
        print("=" * 80)
        print("📋 FASE 1-B: RECREAR procedimientos EN MySQL")
        print("=" * 80)

        # Primero la tabla hija que tiene FK → procedimientos
        db.execute(text("DROP TABLE IF EXISTS proce_medicos_master"))
        db.execute(text("DROP TABLE IF EXISTS procedimientos"))
        db.execute(text("""
            CREATE TABLE procedimientos (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                abreviatura VARCHAR(10)  UNIQUE,
                nombre      VARCHAR(200) NOT NULL UNIQUE,
                descripcion TEXT,
                anestesia   INT          DEFAULT 0
               
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
        db.commit()
        print("✅ Tabla procedimientos recreada")

        # Insertar catálogo en lotes
        for abr, nombre, descripcion, anestesia in PROCEDIMIENTOS_CATALOGO:
            db.execute(text("""
                INSERT INTO procedimientos
                    (abreviatura, nombre, descripcion, anestesia)
                VALUES
                    (:abr, :nombre, :desc, :anes)
            """), {"abr": abr, "nombre": nombre, "desc": descripcion, "anes": anestesia})

        db.commit()
        total = db.execute(text("SELECT COUNT(*) FROM procedimientos")).scalar()
        print(f"✅ {total} procedimientos insertados en catálogo\n")

    except Exception as e:
        db.rollback()
        print(f"❌ Error al recrear procedimientos: {e}")
        raise
    finally:
        db.close()


# ============================================================================
# FASE 1-C — Construir mapa abreviatura → id  (ya en MySQL)
# ============================================================================

def mysql_cargar_mapa() -> dict[str, int]:
    """
    Lee procedimientos de MySQL y devuelve { abreviatura_upper: id }.
    """
    db = MySQLSession()
    try:
        filas = db.execute(
            text("SELECT id, abreviatura FROM procedimientos WHERE abreviatura IS NOT NULL")
        ).fetchall()
        return {str(r[1]).strip().upper(): r[0] for r in filas}
    finally:
        db.close()


# ============================================================================
# FASE 1-D — Agregar abreviaturas desconocidas al catálogo MySQL
# ============================================================================

def mysql_agregar_desconocidos(mapa: dict[str, int]) -> dict[str, int]:
    """
    Escanea proce_medicos_backup buscando abreviaturas que no estén
    en el catálogo y las inserta en procedimientos con nombre = texto
    original o 'Desconocido-XXX'.
    Retorna el mapa ampliado.
    """
    db = MySQLSession()
    nuevos = 0
    advertencias = []

    try:
        print("=" * 80)
        print("🔍 FASE 1-D: DETECTAR ABREVIATURAS NO CATALOGADAS")
        print("=" * 80)

        # Obtener combinaciones únicas abreviatura + texto del backup
        filas = db.execute(text("""
            SELECT
                UPPER(TRIM(abreviatura))   AS abr,
                TRIM(procedimiento)        AS proc_texto
            FROM proce_medicos_backup
            WHERE abreviatura IS NOT NULL
              AND TRIM(abreviatura) != ''
            GROUP BY UPPER(TRIM(abreviatura)), TRIM(procedimiento)
            ORDER BY UPPER(TRIM(abreviatura))
        """)).fetchall()

        # Agrupar: para cada abreviatura desconocida, tomar el texto más frecuente
        desconocidas: dict[str, str] = {}
        for abr, proc_texto in filas:
            if abr not in mapa and abr not in desconocidas:
                desconocidas[abr] = proc_texto or f"Desconocido-{abr}"

        print(f"   Abreviaturas no catalogadas encontradas: {len(desconocidas)}")

        for abr, nombre_raw in desconocidas.items():
            # Capitalizar y truncar
            nombre = " ".join(str(nombre_raw).strip().title().split())[:200]

            # Puede que el nombre ya exista en el catálogo con otra abreviatura
            # (ej: 'Hisopado' existe como HISP, pero alguien usó 'HSP').
            # En ese caso usamos nombre único sufijado con la abreviatura.
            nombre_final = nombre
            sufijo = 1
            while True:
                existe_nombre = db.execute(text(
                    "SELECT id FROM procedimientos WHERE nombre = :n"
                ), {"n": nombre_final}).scalar()
                if not existe_nombre:
                    break
                nombre_final = f"{nombre} [{abr}]"
                sufijo += 1
                if sufijo > 5:
                    nombre_final = f"Desconocido-{abr}"
                    break

            result = db.execute(text("""
                INSERT INTO procedimientos
                    (abreviatura, nombre, descripcion, anestesia)
                VALUES
                    (:abr, :nombre, 'Procedimiento no catalogado', 0)
            """), {"abr": abr, "nombre": nombre_final})
            db.commit()

            new_id = result.lastrowid
            mapa[abr] = new_id
            nuevos += 1
            advertencias.append(f"'{abr}' → '{nombre_final}' (id={new_id})")

        print(f"✅ {nuevos} procedimientos nuevos agregados al catálogo")

        if advertencias:
            print(f"\n   Nuevos procedimientos:")
            for adv in advertencias:
                print(f"   ➕ {adv}")

        print()
        return mapa

    except Exception as e:
        db.rollback()
        print(f"❌ Error detectando abreviaturas: {e}")
        raise
    finally:
        db.close()


# ============================================================================
# FASE 1-E — Crear proce_medicos_master en MySQL (normalizada)
# ============================================================================

def mysql_crear_master(mapa: dict[str, int], batch_size: int = 500) -> dict:
    """
    Lee proce_medicos_backup, normaliza y escribe en proce_medicos_master.
    """
    db = MySQLSession()
    stats = {
        "total": 0, "exitosos": 0, "sin_proc": 0,
        "errores": 0, "advertencias": [],
    }

    try:
        print("=" * 80)
        print("🔄 FASE 1-E: CREAR proce_medicos_master EN MySQL")
        print("=" * 80)

        # Crear tabla master
        db.execute(text("DROP TABLE IF EXISTS proce_medicos_master"))
        db.execute(text("""
            CREATE TABLE proce_medicos_master (
                id               INT AUTO_INCREMENT PRIMARY KEY,
                fecha            DATE,
                servicio         INT,
                sexo             VARCHAR(1),
                id_procedimiento INT,
                especialidad     INT,
                cantidad         INT          NOT NULL DEFAULT 1,
                medico           INT,
                anestesia        INT          DEFAULT 0,
                created_by       VARCHAR(10),
                created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
                CONSTRAINT fk_master_proc
                    FOREIGN KEY (id_procedimiento)
                    REFERENCES procedimientos(id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
        db.commit()
        print("✅ Tabla proce_medicos_master creada")

        filas = db.execute(
            text("SELECT * FROM proce_medicos_backup ORDER BY id")
        ).fetchall()

        stats["total"] = len(filas)
        print(f"📋 Registros a normalizar: {stats['total']:,}\n")

        batch = []
        inicio = datetime.now()

        for i, fila in enumerate(filas, 1):
            row = dict(fila._mapping)
            id_orig = row.get("id")

            try:
                # Resolver id_procedimiento
                abr = str(row.get("abreviatura") or "").strip().upper()
                id_proc = mapa.get(abr) if abr else None

                if not id_proc:
                    stats["sin_proc"] += 1
                    msg = f"[id={id_orig}] sin abreviatura válida → id_procedimiento=NULL"
                    stats["advertencias"].append(msg)

                # Normalizar sexo
                sexo_raw = str(row.get("sexo") or "").strip().upper()
                if sexo_raw in ("M", "MASCULINO", "H"):
                    sexo = "M"
                elif sexo_raw in ("F", "FEMENINO"):
                    sexo = "F"
                else:
                    sexo = None

                # Normalizar cantidad
                try:
                    cantidad = max(1, int(row.get("cantidad") or 1))
                except (ValueError, TypeError):
                    cantidad = 1

                # anestesia: fuente de verdad = catálogo procedimientos
                anestesia_cat = db.execute(text(
                    "SELECT anestesia FROM procedimientos WHERE id = :id"
                ), {"id": id_proc}).scalar() if id_proc else None
                anestesia = int(anestesia_cat) if anestesia_cat is not None \
                    else int(row.get("anestesia") or 0)

                batch.append({
                    "fecha":            row.get("fecha"),
                    "servicio":         row.get("servicio"),
                    "sexo":             sexo,
                    "id_procedimiento": id_proc,
                    "especialidad":     row.get("especialidad"),
                    "cantidad":         cantidad,
                    "medico":           row.get("medico"),
                    "anestesia":        anestesia,
                    "created_by":       str(row.get("created_by") or "")[:10] or None,
                    "created_at":       row.get("created_at") or datetime.now(),
                    "updated_at":       row.get("updated_at") or datetime.now(),
                })

                if len(batch) >= batch_size:
                    db.execute(text("""
                        INSERT INTO proce_medicos_master
                            (fecha, servicio, sexo, id_procedimiento,
                             especialidad, cantidad, medico, anestesia,
                             created_by, created_at, updated_at)
                        VALUES
                            (:fecha, :servicio, :sexo, :id_procedimiento,
                             :especialidad, :cantidad, :medico, :anestesia,
                             :created_by, :created_at, :updated_at)
                    """), batch)
                    db.commit()
                    stats["exitosos"] += len(batch)
                    print(f"   ✅ Normalizados {i:>6}/{stats['total']:,}")
                    batch = []

            except Exception as e:
                stats["errores"] += 1
                stats["advertencias"].append(f"Error fila {i} (id={id_orig}): {e}")
                print(f"   ❌ Error fila {i}: {e}")

        # Batch final
        if batch:
            db.execute(text("""
                INSERT INTO proce_medicos_master
                    (fecha, servicio, sexo, id_procedimiento,
                     especialidad, cantidad, medico, anestesia,
                     created_by, created_at, updated_at)
                VALUES
                    (:fecha, :servicio, :sexo, :id_procedimiento,
                     :especialidad, :cantidad, :medico, :anestesia,
                     :created_by, :created_at, :updated_at)
            """), batch)
            db.commit()
            stats["exitosos"] += len(batch)

        stats["tiempo"] = (datetime.now() - inicio).total_seconds()

        total_master = db.execute(
            text("SELECT COUNT(*) FROM proce_medicos_master")
        ).scalar()
        print(f"\n✅ proce_medicos_master: {total_master:,} registros\n")

    except Exception as e:
        db.rollback()
        print(f"❌ Error creando master: {e}")
        raise
    finally:
        db.close()

    return stats


# ============================================================================
# FASE 2-A — Migrar procedimientos MySQL → PostgreSQL
# ============================================================================

def pg_migrar_procedimientos():
    mysql_db = MySQLSession()
    pg_db    = PostgresSession()

    try:
        print("=" * 80)
        print("🚀 FASE 2-A: MIGRAR procedimientos → PostgreSQL")
        print("=" * 80)

        # DROP + CREATE en PostgreSQL
        pg_db.execute(text("DROP TABLE IF EXISTS proce_medicos CASCADE"))
        pg_db.execute(text("DROP TABLE IF EXISTS procedimientos CASCADE"))
        pg_db.execute(text("""
            CREATE TABLE procedimientos (
                id          SERIAL       PRIMARY KEY,
                abreviatura VARCHAR(10)  UNIQUE,
                nombre      VARCHAR(200) NOT NULL UNIQUE,
                descripcion TEXT,
                anestesia   INT          DEFAULT 0
                
            )
        """))
        pg_db.commit()
        print("✅ procedimientos recreada en PostgreSQL")

        filas = mysql_db.execute(
            text("SELECT * FROM procedimientos ORDER BY id")
        ).fetchall()

        for fila in filas:
            r = dict(fila._mapping)
            pg_db.execute(text("""
                INSERT INTO procedimientos
                    (id, abreviatura, nombre, descripcion, anestesia)
                VALUES
                    (:id, :abr, :nombre, :desc, :anes)
            """), {
                "id":     r["id"],
                "abr":    r.get("abreviatura"),
                "nombre": r["nombre"],
                "desc":   r.get("descripcion"),
                "anes":   r.get("anestesia", 0),
               
            })

        pg_db.commit()

        # Sincronizar secuencia SERIAL con el máximo id migrado
        pg_db.execute(text("""
            SELECT setval(
                pg_get_serial_sequence('procedimientos', 'id'),
                (SELECT MAX(id) FROM procedimientos)
            )
        """))
        pg_db.commit()

        total = pg_db.execute(
            text("SELECT COUNT(*) FROM procedimientos")
        ).scalar()
        print(f"✅ {total:,} procedimientos migrados a PostgreSQL\n")

    except Exception as e:
        pg_db.rollback()
        print(f"❌ Error migrando procedimientos a PG: {e}")
        raise
    finally:
        mysql_db.close()
        pg_db.close()


# ============================================================================
# FASE 2-B — Migrar proce_medicos_master MySQL → PostgreSQL
# ============================================================================

def pg_migrar_proce_medicos(batch_size: int = 500) -> dict:
    mysql_db = MySQLSession()
    pg_db    = PostgresSession()

    stats = {"total": 0, "exitosos": 0, "errores": 0}

    try:
        print("=" * 80)
        print("🚀 FASE 2-B: MIGRAR proce_medicos_master → PostgreSQL")
        print("=" * 80)

        # CREATE en PostgreSQL (procedimientos ya existe)
        pg_db.execute(text("""
            CREATE TABLE proce_medicos (
                id               SERIAL    PRIMARY KEY,
                fecha            DATE,
                servicio         INT,
                sexo             CHAR(1)   CHECK (sexo IN ('M', 'F')),
                id_procedimiento INT       REFERENCES procedimientos(id)
                                               ON DELETE SET NULL,
                especialidad     INT,
                cantidad         INT       NOT NULL DEFAULT 1
                                               CHECK (cantidad >= 1),
                medico           INT       REFERENCES medicos(id)
                                               ON DELETE SET NULL,
                anestesia        INT       DEFAULT 0,
                created_by       VARCHAR(10),
                created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        pg_db.execute(text("CREATE INDEX idx_pm_fecha    ON proce_medicos (fecha)"))
        pg_db.execute(text("CREATE INDEX idx_pm_medico   ON proce_medicos (medico)"))
        pg_db.execute(text("CREATE INDEX idx_pm_proc     ON proce_medicos (id_procedimiento)"))
        pg_db.execute(text("CREATE INDEX idx_pm_servicio ON proce_medicos (servicio)"))
        pg_db.commit()
        print("✅ proce_medicos creada en PostgreSQL")

        filas = mysql_db.execute(
            text("SELECT * FROM proce_medicos_master ORDER BY id")
        ).fetchall()

        stats["total"] = len(filas)
        print(f"📋 Registros a migrar: {stats['total']:,}\n")

        batch = []
        inicio = datetime.now()

        for i, fila in enumerate(filas, 1):
            r = dict(fila._mapping)
            batch.append({
                "fecha":            r.get("fecha"),
                "servicio":         r.get("servicio"),
                "sexo":             r.get("sexo"),
                "id_procedimiento": r.get("id_procedimiento"),
                "especialidad":     r.get("especialidad"),
                "cantidad":         r.get("cantidad") or 1,
                "medico":           r.get("medico"),
                "anestesia":        r.get("anestesia") or 0,
                "created_by":       r.get("created_by"),
                "created_at":       r.get("created_at") or datetime.now(),
                "updated_at":       r.get("updated_at") or datetime.now(),
            })

            if len(batch) >= batch_size:
                try:
                    pg_db.execute(text("""
                        INSERT INTO proce_medicos
                            (fecha, servicio, sexo, id_procedimiento,
                             especialidad, cantidad, medico, anestesia,
                             created_by, created_at, updated_at)
                        VALUES
                            (:fecha, :servicio, :sexo, :id_procedimiento,
                             :especialidad, :cantidad, :medico, :anestesia,
                             :created_by, :created_at, :updated_at)
                    """), batch)
                    pg_db.commit()
                    stats["exitosos"] += len(batch)
                    print(f"   ✅ Migrados {i:>6}/{stats['total']:,}")
                except Exception as e:
                    pg_db.rollback()
                    stats["errores"] += len(batch)
                    print(f"   ❌ Batch fallido en {i}: {e}")
                batch = []

        if batch:
            try:
                pg_db.execute(text("""
                    INSERT INTO proce_medicos
                        (fecha, servicio, sexo, id_procedimiento,
                         especialidad, cantidad, medico, anestesia,
                         created_by, created_at, updated_at)
                    VALUES
                        (:fecha, :servicio, :sexo, :id_procedimiento,
                         :especialidad, :cantidad, :medico, :anestesia,
                         :created_by, :created_at, :updated_at)
                """), batch)
                pg_db.commit()
                stats["exitosos"] += len(batch)
            except Exception as e:
                pg_db.rollback()
                stats["errores"] += len(batch)
                print(f"   ❌ Batch final fallido: {e}")

        stats["tiempo"] = (datetime.now() - inicio).total_seconds()

    except Exception as e:
        pg_db.rollback()
        print(f"❌ Error migrando proce_medicos a PG: {e}")
        raise
    finally:
        mysql_db.close()
        pg_db.close()

    return stats


# ============================================================================
# VERIFICACIÓN FINAL
# ============================================================================

def verificar():
    mysql_db = MySQLSession()
    pg_db    = PostgresSession()

    try:
        print("\n" + "=" * 80)
        print("🔍 VERIFICACIÓN FINAL")
        print("=" * 80)

        # Conteos
        orig   = mysql_db.execute(text("SELECT COUNT(*) FROM proce_medicos_backup")).scalar()
        master = mysql_db.execute(text("SELECT COUNT(*) FROM proce_medicos_master")).scalar()
        procs  = mysql_db.execute(text("SELECT COUNT(*) FROM procedimientos")).scalar()
        pg_pm  = pg_db.execute(text("SELECT COUNT(*) FROM proce_medicos")).scalar()
        pg_pr  = pg_db.execute(text("SELECT COUNT(*) FROM procedimientos")).scalar()

        print(f"\n📊 Conteos:")
        print(f"   MySQL  proce_medicos_backup:  {orig:>8,}  (original)")
        print(f"   MySQL  procedimientos:         {procs:>8,}  (catálogo)")
        print(f"   MySQL  proce_medicos_master:   {master:>8,}  (normalizada)")
        print(f"   PG     procedimientos:         {pg_pr:>8,}")
        print(f"   PG     proce_medicos:          {pg_pm:>8,}")

        # Integridad: cuántos sin id_procedimiento
        sin_proc = pg_db.execute(text(
            "SELECT COUNT(*) FROM proce_medicos WHERE id_procedimiento IS NULL"
        )).scalar()
        print(f"\n   Sin id_procedimiento (PG): {sin_proc:,}")

        # Top 10
        print(f"\n   Top 10 procedimientos (PG):")
        top = pg_db.execute(text("""
            SELECT p.abreviatura, p.nombre, COUNT(pm.id) AS n, SUM(pm.cantidad) AS cant
            FROM proce_medicos pm
            JOIN procedimientos p ON p.id = pm.id_procedimiento
            GROUP BY p.id ORDER BY n DESC LIMIT 10
        """)).fetchall()
        for abr, nom, n, cant in top:
            print(f"   → {(abr or '?'):<8} {nom:<40} reg:{n:>5}  cant:{cant:>6}")

        # Procedimientos no catalogados
        no_cat = pg_db.execute(text("""
            SELECT abreviatura, nombre FROM procedimientos
            WHERE descripcion = 'Procedimiento no catalogado'
            ORDER BY abreviatura
        """)).fetchall()
        if no_cat:
            print(f"\n   ⚠️  Procedimientos fuera del catálogo original ({len(no_cat)}):")
            for abr, nom in no_cat:
                print(f"   → '{abr}' — {nom}")

    finally:
        mysql_db.close()
        pg_db.close()


# ============================================================================
# MAIN
# ============================================================================

def main():
    inicio = datetime.now()

    # ── FASE 1: Todo en MySQL ────────────────────────────────────────────────
    mysql_backup_proce_medicos()          # 1-A backup
    mysql_recrear_procedimientos()        # 1-B catálogo limpio
    mapa = mysql_cargar_mapa()            # cargar mapa abr → id
    mapa = mysql_agregar_desconocidos(mapa)  # 1-D nuevas abreviaturas
    stats_norm = mysql_crear_master(mapa) # 1-E tabla normalizada

    # ── FASE 2: Migrar a PostgreSQL ──────────────────────────────────────────
    pg_migrar_procedimientos()            # 2-A catálogo
    stats_pg = pg_migrar_proce_medicos()  # 2-B registros

    # ── Verificación ─────────────────────────────────────────────────────────
    verificar()

    # ── Resumen ──────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - inicio).total_seconds()

    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL")
    print("=" * 80)
    print(f"  Normalización MySQL:")
    print(f"    Total procesados:   {stats_norm['total']:,}")
    print(f"    Normalizados:       {stats_norm['exitosos']:,}")
    print(f"    Sin procedimiento:  {stats_norm['sin_proc']:,}")
    print(f"    Errores:            {stats_norm['errores']:,}")
    print(f"  Migración PostgreSQL:")
    print(f"    Migrados exitosos:  {stats_pg['exitosos']:,}")
    print(f"    Errores:            {stats_pg['errores']:,}")
    print(f"  Tiempo total:         {elapsed:.2f}s")
    print("=" * 80)

    if stats_norm["advertencias"]:
        print(f"\n⚠️  Advertencias de normalización ({len(stats_norm['advertencias'])}):")
        for adv in stats_norm["advertencias"][:20]:
            print(f"   • {adv}")
        if len(stats_norm["advertencias"]) > 20:
            print(f"   ... y {len(stats_norm['advertencias']) - 20} más.")

    print()
    print("✅ Proceso completo.")
    print("   Tablas MySQL de referencia disponibles:")
    print("     • proce_medicos_backup  (datos originales)")
    print("     • procedimientos        (catálogo normalizado)")
    print("     • proce_medicos_master  (tabla normalizada lista)")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Cancelado por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)