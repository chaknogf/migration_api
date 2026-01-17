# app/utils/normalizadores.py
import re
from typing import Dict, Optional, Any, Union, List
from datetime import datetime, time, date


CUIS_VISTOS: set[int] = set()



def json_safe(obj):
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj
# ============================================================================
# NORMALIZADORES BÁSICOS
# ============================================================================

# def normalizar_cui(cui: Optional[int]) -> Optional[int]:
#     if not cui:
#         return None
#     cui_str = str(cui).strip()
#     if len(cui_str) != 13 or not cui_str.isdigit():
#         return None
#     return int(cui_str)

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

def normalizar_sexo(sexo: Optional[str]) -> Optional[str]:
    if not sexo:
        return None

    # Elimina todo lo que no sea letra
    limpio = re.sub(r"[^A-Za-z]", "", sexo).upper()

    if not limpio:
        return None

    if limpio[0] == "M":
        return "M"
    if limpio[0] == "F":
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
    """Construye estructura Nombre según interfaz TypeScript"""
    return {
        **extraer_nombres(nombre),
        **extraer_apellidos(apellido)
    }

# ============================================================================
# CONTACTO
# ============================================================================

def _normalizar_codigo(valor: Optional[str]) -> Optional[str]:
    if not valor:
        return None

    valor_str = str(valor).strip()

    if valor_str.isdigit() and len(valor_str) == 3:
        return f"0{valor_str}"

    return valor_str


def construir_contacto_jsonb(
    telefonos: Optional[str],
    email: Optional[str],
    domicilio: Optional[str],
    municipio: Optional[str]
) -> Dict[str, Any]:
    """Construye estructura Contacto según interfaz TypeScript"""
    return {
        "domicilio": domicilio,
        "municipio": _normalizar_codigo(municipio),
        "telefonos": limpiar_telefono(telefonos),
        "email": email
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
    """
    Construye estructura Referencia según interfaz TypeScript.
    Retorna lista de referencias o None si está vacía.
    """

    def normalizar_parentesco(v):
        if v is None:
            return "otro"
        try:
            v_int = int(v)
            return PARENTESCOS_MAP.get(v_int, "otro")
        except (ValueError, TypeError):
            pass
        v_str = str(v).strip().lower()
        if v_str in PARENTESCOS_MAP.values():
            return v_str
        return "otro"

    def normalizar_nombre(v: str) -> str:
        return " ".join(v.strip().lower().split())

    refs = []

    nombre_responsable_norm = (
        normalizar_nombre(responsable)
        if responsable
        else None
    )

    if padre:
        if not nombre_responsable_norm or normalizar_nombre(padre) != nombre_responsable_norm:
            refs.append({
                "nombre": padre.strip(),
                "parentesco": "padre",
                "telefonos": None,
                "expediente": None,
                "idpersona": str(dpi_responsable) if dpi_responsable else None,
                "responsable": False
            })

    if madre:
        if not nombre_responsable_norm or normalizar_nombre(madre) != nombre_responsable_norm:
            refs.append({
                "nombre": madre.strip(),
                "parentesco": "madre",
                "telefonos": None,
                "expediente": None,
                "idpersona": None,
                "responsable": False
            })

    if conyugue:
        if not nombre_responsable_norm or normalizar_nombre(conyugue) != nombre_responsable_norm:
            refs.append({
                "nombre": conyugue.strip(),
                "parentesco": "esposo/a",
                "telefonos": None,
                "expediente": None,
                "idpersona": None,
                "responsable": False
            })

    if responsable:
        refs.append({
            "nombre": responsable.strip(),
            "parentesco": normalizar_parentesco(parentesco_responsable),
            "telefonos": limpiar_telefono(telefono_responsable),
            "expediente": None,
            "idpersona": str(dpi_responsable) if dpi_responsable else None,
            "responsable": True
        })

    return refs if refs else None

# ============================================================================
# DATOS EXTRA Y METADATOS
# ============================================================================

NACIONALIDADES_MAP = {
    1: 'GTM',
    2: 'BLZ',
    3: 'SLV',
    4: 'HND',
    5: 'NIC',
    6: 'CRI',
    7: 'PAN',
    8: 'MEX',
    9: 'OTRO',
    0: 'NO_INDICA'
}
  
def normalizar_nacionalidad(nacionalidad: Optional[int | str]) -> str:
    """Normaliza nacionalidad a código ISO de 3 letras"""
    DEFAULT = "GTM"

    if nacionalidad is None:
        return DEFAULT

    try:
        nacionalidad = int(nacionalidad)
    except (TypeError, ValueError):
        return DEFAULT

    if nacionalidad == 0:
        return DEFAULT

    return NACIONALIDADES_MAP.get(nacionalidad, DEFAULT)


def normalizar_parto(parto: Optional[str]) -> Optional[str]:
    """
    Normaliza tipo de parto.
    P = Parto vaginal, C = Cesárea
    """
    if not parto:
        return None
    
    parto_str = str(parto).strip().upper()
    if parto_str in ('P', 'PARTO', 'VAGINAL'):
        return 'P'
    if parto_str in ('C', 'CESAREA', 'CESAREO'):
        return 'C'
    
    return None


def normalizar_si_no(valor: Optional[str]) -> Optional[str]:
    """
    Normaliza valores S/N (Sí/No)
    """
    if not valor:
        return None
    
    valor_str = str(valor).strip().upper()
    if valor_str in ('S', 'SI', 'YES', 'Y', '1'):
        return 'S'
    if valor_str in ('N', 'NO', 'NOT', '0'):
        return 'N'
    
    return None


def construir_datos_extra_jsonb(
    nacionalidad: Optional[int | str],
    depto_nac: Optional[str],
    lugar_nacimiento: Optional[str],
    estado_civil: Optional[int],
    educacion: Optional[int],
    pueblo: Optional[int],
    idioma: Optional[int],
    ocupacion: Optional[str],
    fecha_defuncion: Optional[str],
    hora_defuncion: Optional[str],
    peso_nacimiento: Optional[str] = None,
    edad_gestacional: Optional[str] = None,
    parto: Optional[str] = None,
    gemelo: Optional[str] = None,
    expediente_madre: Optional[str] = None,
    extrahospitalario: Optional[str] = None,
    personaid: Optional[str] = None
) -> Dict[str, Any]:
    """
    Construye estructura DatosExtra según interfaz TypeScript.
    Incluye demograficos, socioeconomicos, neonatales y defunción.
    """

    # Procesar defunción
    defuncion_fecha = None
    if fecha_defuncion:
        try:
            fecha_obj = datetime.strptime(str(fecha_defuncion), "%Y-%m-%d")
            if hora_defuncion:
                try:
                    hora_obj = datetime.strptime(str(hora_defuncion), "%H:%M:%S")
                    defuncion_fecha = f"{fecha_obj.date().isoformat()}T{hora_obj.time().isoformat()}"
                except:
                    defuncion_fecha = fecha_obj.date().isoformat()
            else:
                defuncion_fecha = fecha_obj.date().isoformat()
        except:
            defuncion_fecha = None

    # Estructura Demograficos
    demograficos = {
        "idioma": idioma,
        "pueblo": pueblo,
        "nacionalidad": normalizar_nacionalidad(nacionalidad),
        "lugar_nacimiento": _normalizar_codigo(lugar_nacimiento),
        "vecindad": None
    }

    # Estructura Socioeconomicos
    socioeconomicos = {
        "estado_civil": estado_civil,
        "ocupacion": ocupacion,
        "educacion": educacion,
        "estudiante_publico": None,
        "empleado_publico": None,
        "discapacidad": None
    }

    # Estructura Neonatales (solo si hay datos relevantes)
    neonatales = None
    if any([peso_nacimiento, edad_gestacional, parto, gemelo, expediente_madre, extrahospitalario]):
        neonatales = {
            "peso_nacimiento": peso_nacimiento,
            "edad_gestacional": edad_gestacional,
            "parto": normalizar_parto(parto),
            "gemelo": gemelo,
            "expediente_madre": expediente_madre,
            "extrahositalario": normalizar_si_no(extrahospitalario)
        }

    # Construir respuesta final
    resultado = {
        "defuncion": defuncion_fecha,
        "personaid": personaid,
        "demograficos": demograficos,
        "socioeconomicos": socioeconomicos
    }

    # Solo incluir neonatales si hay datos
    if neonatales:
        resultado["neonatales"] = neonatales

    return resultado


def construir_metadatos_jsonb(
    id_mysql: int,
    created_by: Optional[str],
    created_at: Optional[str],
    expediente_duplicado: bool
) -> List[Dict[str, Any]]:
    return [
        {
            "accion": "CREADO",
            "usuario": created_by,
            "registro": created_at or datetime.now().isoformat(),
            "expediente_duplicado": expediente_duplicado,
            "origen_mysql_id": id_mysql
        }
    ]