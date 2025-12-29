import re
from typing import Dict, Optional, Any
from datetime import datetime, date, time

def normalizar_cui(dpi: Optional[int]) -> Optional[int]:
    """
    Valida y normaliza CUI guatemalteco (13 dígitos)
    Si no cumple, retorna None
    """
    if not dpi:
        return None
    
    cui_str = str(dpi).strip()
    
    # Debe tener exactamente 13 dígitos
    if len(cui_str) != 13 or not cui_str.isdigit():
        return None
    
    return int(cui_str)

def normalizar_expediente(expediente: Optional[int], id_mysql: int) -> str:
    """
    Normaliza expediente, si es None o duplicado genera uno único
    Formato: EXP-{expediente} o DUP-{id_mysql} para duplicados/nulos
    """
    if expediente is None or expediente == 0:
        return f"DUP-{id_mysql}"
    
    return str(expediente)

def validar_expediente_duplicado(expediente: Optional[int]) -> bool:
    """Retorna True si el expediente es considerado duplicado o inválido"""
    return expediente is None or expediente == 0

def normalizar_sexo(sexo: Optional[str]) -> str:
    """MySQL: M/F/? → PostgreSQL: M/F/NF"""
    if not sexo:
        return "NF"
    
    sexo = sexo.strip().upper()
    if sexo in ("M", "MASCULINO", "HOMBRE"):
        return "M"
    elif sexo in ("F", "FEMENINO", "MUJER"):
        return "F"
    else:
        return "NF"

def normalizar_estado(estado: Optional[str]) -> str:
    """MySQL: varios formatos → PostgreSQL: V/F"""
    if not estado:
        return "V"
    
    estado = estado.strip().upper()
    if estado in ("F", "FALLECIDO", "MUERTO", "DEAD"):
        return "F"
    else:
        return "V"

def normalizar_email(email: Optional[str]) -> Optional[str]:
    """
    Normaliza email, retorna None si no es válido o está vacío
    No validamos formato, solo limpiamos
    """
    if not email:
        return None
    
    email = email.strip().lower()
    
    # Si está vacío o es placeholder
    if not email or email in ("", "n/a", "na", "null", "none"):
        return None
    
    return email

def parsear_fecha_defuncion(
    fecha_str: Optional[str], 
    hora: Optional[time]
) -> Optional[datetime]:
    """
    Combina fecha (VARCHAR) y hora (TIME) en un datetime
    Formatos esperados: 'YYYY-MM-DD', 'DD/MM/YYYY', etc.
    """
    if not fecha_str:
        return None
    
    fecha_str = fecha_str.strip()
    
    # Intentar varios formatos
    formatos = [
        '%Y-%m-%d',      # 2024-01-15
        '%d/%m/%Y',      # 15/01/2024
        '%Y/%m/%d',      # 2024/01/15
        '%d-%m-%Y',      # 15-01-2024
    ]
    
    fecha_obj = None
    for formato in formatos:
        try:
            fecha_obj = datetime.strptime(fecha_str, formato).date()
            break
        except ValueError:
            continue
    
    if not fecha_obj:
        return None
    
    # Si hay hora, combinar
    if hora:
        try:
            return datetime.combine(fecha_obj, hora)
        except:
            return datetime.combine(fecha_obj, time(0, 0, 0))
    
    # Sin hora, poner medianoche
    return datetime.combine(fecha_obj, time(0, 0, 0))

def extraer_nombres(nombre_completo: Optional[str]) -> Dict[str, Optional[str]]:
    """Divide nombre completo en componentes"""
    if not nombre_completo:
        return {
            "primer_nombre": None,
            "segundo_nombre": None,
            "otros_nombres": None
        }
    
    # Limpiar y normalizar
    nombre_completo = " ".join(nombre_completo.strip().split())
    partes = nombre_completo.split()
    
    if len(partes) == 0:
        return {"primer_nombre": None, "segundo_nombre": None, "otros_nombres": None}
    elif len(partes) == 1:
        return {"primer_nombre": partes[0], "segundo_nombre": None, "otros_nombres": None}
    elif len(partes) == 2:
        return {"primer_nombre": partes[0], "segundo_nombre": partes[1], "otros_nombres": None}
    else:
        return {
            "primer_nombre": partes[0],
            "segundo_nombre": partes[1],
            "otros_nombres": " ".join(partes[2:])
        }

def extraer_apellidos(apellido_completo: Optional[str]) -> Dict[str, Optional[str]]:
    """Divide apellido completo en componentes"""
    if not apellido_completo:
        return {"primer_apellido": None, "segundo_apellido": None}
    
    # Limpiar y normalizar
    apellido_completo = " ".join(apellido_completo.strip().split())
    partes = apellido_completo.split()
    
    if len(partes) == 0:
        return {"primer_apellido": None, "segundo_apellido": None}
    elif len(partes) == 1:
        return {"primer_apellido": partes[0], "segundo_apellido": None}
    else:
        return {"primer_apellido": partes[0], "segundo_apellido": " ".join(partes[1:])}

def construir_nombre_jsonb(
    nombre: Optional[str],
    apellido: Optional[str],
    conyugue: Optional[str] = None
) -> Dict[str, Any]:
    """Construye el JSONB de nombre completo"""
    nombres = extraer_nombres(nombre)
    apellidos = extraer_apellidos(apellido)
    
    return {
        **nombres,
        **apellidos,
        "apellido_casada": conyugue if conyugue else None
    }

def construir_contacto_jsonb(
    telefono: Optional[str],
    email: Optional[str],
    direccion: Optional[str],
    municipio: Optional[int],
    depto: Optional[int]
) -> Dict[str, Any]:
    """Construye el JSONB de contacto"""
    email_normalizado = normalizar_email(email)
    
    return {
        "telefono_principal": telefono,
        "email": email_normalizado,  # Siempre será None según tu indicación
        "direccion": {
            "linea1": direccion,
            "municipio_id": municipio,
            "departamento_id": depto
        } if direccion or municipio or depto else None
    }

def construir_referencias_jsonb(
    padre: Optional[str],
    madre: Optional[str],
    exp_madre: Optional[int],
    responsable: Optional[str],
    parentesco: Optional[int],
    dpi_responsable: Optional[int],
    telefono_responsable: Optional[int],
    exp_ref: Optional[int],
    conyugue: Optional[str],
    gemelo: Optional[str]
) -> Dict[str, Any]:
    """Construye el JSONB de referencias familiares"""
    
    # Normalizar CUI del responsable
    cui_responsable = normalizar_cui(dpi_responsable)
    
    return {
        "padre": padre,
        "madre": madre,
        "expediente_madre": exp_madre,
        "responsable": {
            "nombre": responsable,
            "parentesco_id": parentesco,
            "cui": cui_responsable,  # Puede ser None si no cumple
            "telefono": telefono_responsable,
            "expediente": exp_ref
        } if responsable else None,
        "conyugue": conyugue,
        "es_gemelo": gemelo and gemelo.upper() in ("SI", "S", "YES", "Y", "1")
    }

def construir_datos_extra_jsonb(
    nacionalidad: Optional[int],
    depto_nac: Optional[int],
    lugar_nacimiento: Optional[int],
    estado_civil: Optional[int],
    educacion: Optional[int],
    pueblo: Optional[int],
    idioma: Optional[int],
    ocupacion: Optional[str],
    fecha_defuncion: Optional[str],
    hora_defuncion: Optional[Any]
) -> Dict[str, Any]:
    """Construye el JSONB de datos extra"""
    
    # Parsear fecha y hora de defunción
    fecha_hora_defuncion = parsear_fecha_defuncion(fecha_defuncion, hora_defuncion)
    
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
            "fecha_hora": fecha_hora_defuncion.isoformat() if fecha_hora_defuncion else None
        } if fecha_hora_defuncion else None
    }

def construir_metadatos_jsonb(
    id_mysql: int,
    created_by: Optional[str],
    expediente_duplicado: bool = False
) -> Dict[str, Any]:
    """Construye el JSONB de metadatos del sistema"""
    
    return {
        "sistema_origen": "mysql_legacy",
        "id_origen": id_mysql,
        "creado_por": created_by,
        "migrado_en": datetime.now().isoformat(),
        "version_migracion": "1.0",
        "expediente_duplicado": expediente_duplicado,  # Flag para duplicados
        "notas": "Expediente marcado como duplicado o nulo" if expediente_duplicado else None
    }

def limpiar_telefono(telefono: Optional[str]) -> Optional[str]:
    """
    Limpia y normaliza número de teléfono
    Remueve caracteres no numéricos
    """
    if not telefono:
        return None
    
    # Remover todo excepto números
    telefono_limpio = re.sub(r'[^\d]', '', str(telefono))
    
    if not telefono_limpio:
        return None
    
    return telefono_limpio