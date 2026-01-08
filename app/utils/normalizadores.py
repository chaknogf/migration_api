import re
from typing import Dict, Optional, Any
from datetime import datetime, time

CUIS_VISTOS: set[int] = set()

# ============================================================================
# NORMALIZADORES BÁSICOS
# ============================================================================

def normalizar_cui(cui: Optional[int], cuis_vistos: set[int]) -> Optional[int]:
    if not cui:
        return None

    cui_str = str(cui).strip()
    if len(cui_str) != 13 or not cui_str.isdigit():
        return None

    cui_int = int(cui_str)
    if cui_int in cuis_vistos:
        return None

    cuis_vistos.add(cui_int)
    return cui_int


def normalizar_expediente(expediente: Optional[int], id_mysql: int) -> str:
    """
    Si el expediente viene vacío o en 0, se genera uno sintético
    claramente identificable y único.
    """
    if expediente is None or expediente == 0:
        return f"X{id_mysql}"
    return str(expediente)


def validar_expediente_duplicado(expediente: Optional[int]) -> bool:
    """
    Indica si el expediente original era inválido
    y fue reemplazado por uno sintético.
    """
    return expediente is None or expediente == 0

def normalizar_pasaporte(p):
    if not p:
        return None
    p = p.strip()
    return p if p else None

def normalizar_sexo(sexo: Optional[str]) -> str:
    if not sexo:
        return None

    sexo = sexo.strip().upper()
    if sexo in ("M", "MASCULINO", "HOMBRE"):
        return "M"
    if sexo in ("F", "FEMENINO", "MUJER"):
        return "F"
    return None

def normalizar_estado(estado: Optional[str]) -> str:
    if not estado:
        return "V"

    estado = estado.strip().upper()
    if estado in ("F", "FALLECIDO", "MUERTO", "DEAD"):
        return "F"
    return "V"


def limpiar_telefono(telefono: Optional[str]) -> Optional[str]:
    if not telefono:
        return None
    tel = re.sub(r"[^\d]", "", str(telefono))
    return tel if tel else None

# ============================================================================
# NOMBRE
# ============================================================================

def extraer_nombres(nombre: Optional[str]) -> Dict[str, Optional[str]]:
    if not nombre:
        return {
            "primer_nombre": None,
            "segundo_nombre": None,
            "otro_nombre": None
        }

    partes = nombre.strip().split()
    if len(partes) == 1:
        return {"primer_nombre": partes[0], "segundo_nombre": None, "otro_nombre": None}
    if len(partes) == 2:
        return {"primer_nombre": partes[0], "segundo_nombre": partes[1], "otro_nombre": None}

    return {
        "primer_nombre": partes[0],
        "segundo_nombre": partes[1],
        "otro_nombre": " ".join(partes[2:])
    }


def extraer_apellidos(apellido: Optional[str]) -> Dict[str, Optional[str]]:
    if not apellido:
        return {
            "primer_apellido": None,
            "segundo_apellido": None,
            "apellido_casada": None
        }

    partes = apellido.strip().split()
    primer = partes[0]
    segundo = None
    casada = None

    if "de" in partes[1:]:
        idx = partes.index("de")
        if idx > 1:
            segundo = " ".join(partes[1:idx])
        casada = " ".join(partes[idx + 1:])
    elif len(partes) > 1:
        segundo = " ".join(partes[1:])

    return {
        "primer_apellido": primer,
        "segundo_apellido": segundo,
        "apellido_casada": casada
    }


def construir_nombre_jsonb(nombre: Optional[str], apellido: Optional[str]) -> Dict[str, Any]:
    return {
        **extraer_nombres(nombre),
        **extraer_apellidos(apellido)
    }

# ============================================================================
# CONTACTO
# ============================================================================

def construir_contacto_jsonb(
    telefono: Optional[str],
    email: Optional[str],
    direccion: Optional[str],
    municipio: Optional[str],
    depto: Optional[str]
) -> Dict[str, Any]:
    return {
        "domicilio": direccion,
        "vecindad": None,
        "municipio": municipio,
        "telefonos": limpiar_telefono(telefono)
    }

# ============================================================================
# REFERENCIAS
# ============================================================================

PARENTESCOS_MAP = {
    1: "madre/padre",
    2: "hijo/a",
    3: "hermano/a",
    4: "abuelo/a",
    5: "tio/a",
    6: "primo/a",
    7: "sobrino/a",
    8: "yerno/nuera",
    9: "esposo/a",
    10: "suegro/a",
    11: "tutor",
    12: "amistad",
    13: "novio/a",
    14: "cuñado/a",
    15: "nieto/a",
    16: "hijastro/a",
    17: "padrastro/madrastra",
    18: "otro",
}

def construir_referencias_jsonb(
    padre: Optional[str],
    madre: Optional[str],
    responsable: Optional[str],
    parentesco_responsable: Optional[int | str],
    dpi_responsable: Optional[int],
    telefono_responsable: Optional[str],
    conyugue: Optional[str]
) -> Optional[list[dict]]:

    def normalizar_parentesco(v):
        if isinstance(v, str):
            return v.lower()
        return PARENTESCOS_MAP.get(v, "otro")

    refs = []

    if padre:
        refs.append({"nombre": padre.strip(), "parentesco": "padre", "telefono": None})
    if madre:
        refs.append({"nombre": madre.strip(), "parentesco": "madre", "telefono": None})
    if conyugue:
        refs.append({"nombre": conyugue.strip(), "parentesco": "esposo/a", "telefono": None})
    if responsable:
        refs.append({
            "nombre": responsable.strip(),
            "parentesco": normalizar_parentesco(parentesco_responsable),
            "telefono": limpiar_telefono(telefono_responsable)
        })

    return refs if refs else None

# ============================================================================
# DATOS EXTRA Y METADATOS
# ============================================================================

def construir_datos_extra_jsonb(
    nacionalidad, depto_nac, lugar_nacimiento,
    estado_civil, educacion, pueblo, idioma,
    ocupacion, fecha_defuncion, hora_defuncion
) -> Dict[str, Any]:

    fecha = None
    if fecha_defuncion:
        try:
            fecha = datetime.strptime(fecha_defuncion, "%Y-%m-%d")
        except:
            fecha = None

    return {
        "demograficos": {
            "nacionalidad_id": nacionalidad,
            "departamento_nacimiento_id": depto_nac,
            "lugar_nacimiento_id": lugar_nacimiento,
            "estado_civil_id": estado_civil,
            "pueblo_id": pueblo,
            "idioma_id": idioma
        },
        "socioeconomicos": {
            "educacion_id": educacion,
            "ocupacion": ocupacion
        },
        "defuncion": {
            "fecha_hora": fecha.isoformat() if fecha else None
        } if fecha else None
    }


def construir_metadatos_jsonb(id_mysql: int, created_by: Optional[str], expediente_duplicado: bool) -> Dict[str, Any]:
    return {
        "sistema_origen": "mysql_legacy",
        "id_origen": id_mysql,
        "creado_por": created_by,
        "migrado_en": datetime.now().isoformat(),
        "version_migracion": "1.0",
        "expediente_duplicado": expediente_duplicado
    }