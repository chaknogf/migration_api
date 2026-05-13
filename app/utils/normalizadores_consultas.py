# app/utils/normalizadores_consultas.py
"""
Normalizadores específicos para consultas
Complementan los normalizadores de pacientes
"""

from typing import Optional, Dict, Any
from datetime import datetime, time, date
import re

# ============================================================================
# NORMALIZADORES DE CONSULTAS
# ============================================================================

def normalizar_tipo_consulta(tipo: Optional[int]) -> Optional[int]:
    """
    Normaliza tipo de consulta
    Valores típicos: 1=COEX, 2=Hospitalizacion, 3=Emergencia, etc.
    """
    if tipo is None:
        return None
    
    try:
        tipo_int = int(tipo)
        # Validar rango razonable (ajustar según tu sistema)
        if 0 <= tipo_int <= 10:
            return tipo_int
        return None
    except (ValueError, TypeError):
        return None

def normalizar_especialidad(especialidad: Optional[int]) -> Optional[str]:
    """
    Normaliza especialidad médica
    Convierte código numérico a código de especialidad
    Retorna None solo si el valor es inválido (para usar default después)
    """
    if especialidad is None:
        return None  # Permitir que se use el default
    
    try:
        esp_int = int(especialidad)
        
        # Mapeo específico de especialidades
        ESPECIALIDADES_MAP = {
            0: "GENE",    # General
            1: "MEDI",    # Medicina
            2: "PEDI",    # Pediatría
            3: "GINE",    # Ginecología
            4: "CIRU",    # Cirugía
            5: "TRAU",    # Traumatología
            6: "PSIC",    # Psicología
            7: "NUTR",    # Nutrición
            8: "ODON",    # Odontología
            -1: "NO_ESP", # No especificada
        }
        
        return ESPECIALIDADES_MAP.get(esp_int, "NO_ESP")
    except (ValueError, TypeError):
        return None  # Permitir que se use el default

def normalizar_servicio(servicio: Optional[int]) -> Optional[str]:
    """
    Normaliza servicio hospitalario
    Convierte código numérico a nombre de servicio
    Retorna None solo si el valor es inválido (para usar default después)
    """
    if servicio is None:
        return None  # Permitir que se use el default
    
    try:
        serv_int = int(servicio)
        
        # Mapeo específico de servicios (MAX 20 caracteres)
        SERVICIOS_MAP = {
            0: "NO_ESP",             # No especificado
            1: "SOP",
            2: "MATERNIDAD",
            3: "GINECOLOGIA",
            4: "CIRUGIA",
            5: "CIRUGIA PEDIA",      
            6: "TRAUMATOLOGIA",
            7: "TRAUMA PEDIA",      
            8: "CRN",
            9: "PEDIATRIA",
            10: "ALOJ CONJUNTO",     
            11: "NEONATOS",
            12: "MEDICINA HOMBRES",
            13: "MEDICINA MUJERES",
            14: "VSVS",             
            15: "COVID",
            16: "LABOR Y PARTO",
            17: "AREA ROJA",         
            18: "UCIN",
            -1: "NO_ESP",            # No especificado
        }
        
        return SERVICIOS_MAP.get(serv_int, "NO_ESP")
    except (ValueError, TypeError):
        return None  # Permitir que se use el default

def normalizar_hoja_emergencia(hoja: Optional[str]) -> Optional[str]:
    """
    Normaliza número de hoja de emergencia
    """
    if not hoja:
        return None
    
    hoja_str = str(hoja).strip().upper()
    
    # Eliminar caracteres no alfanuméricos excepto guiones
    hoja_limpia = re.sub(r'[^A-Z0-9\-]', '', hoja_str)
    
    return hoja_limpia if hoja_limpia else None

def normalizar_diagnostico(dx: Optional[str]) -> Optional[str]:
    """
    Normaliza diagnóstico
    Limpia espacios y convierte a mayúsculas
    """
    if not dx:
        return None
    
    dx_str = str(dx).strip()
    
    if not dx_str:
        return None
    
    # Limpiar múltiples espacios
    dx_limpio = ' '.join(dx_str.split())
    
    return dx_limpio[:500] if dx_limpio else None  # Limitar longitud

def normalizar_medico(medico: Optional[str]) -> Optional[str]:
    """
    Normaliza nombre de médico
    """
    if not medico:
        return None
    
    medico_str = str(medico).strip()
    
    # Limpiar y capitalizar
    if medico_str:
        # Eliminar números y caracteres especiales
        medico_limpio = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s\.]', '', medico_str)
        medico_limpio = ' '.join(medico_limpio.split())
        return medico_limpio[:100] if medico_limpio else None
    
    return None

def normalizar_estado_ciclo(status: Optional[int]) -> str:
    """
    Normaliza el estado del ciclo basado en el status de la consulta
    1 = "admision"
    2 = "archivo"
    Otro/NULL = "recepcion" (por defecto)
    """
    if status is None:
        return "recepcion"  # Default
    
    try:
        status_int = int(status)
        
        # Mapeo de status a estado del ciclo
        STATUS_TO_ESTADO = {
            1: "admision",
            2: "archivo",
        }
        
        return STATUS_TO_ESTADO.get(status_int, "recepcion")
    except (ValueError, TypeError):
        return "recepcion"  # Default


def normalizar_status(status: Optional[int]) -> Optional[int]:
    """
    Normaliza status de consulta
    Valores típicos: 1=Activa, 2=Finalizada, 3=Cancelada, etc.
    """
    if status is None:
        return None
    
    try:
        status_int = int(status)
        # Validar rango razonable
        if 0 <= status_int <= 10:
            return status_int
        return None
    except (ValueError, TypeError):
        return None

def normalizar_fecha_consulta(fecha: Optional[date]) -> Optional[date]:
    """
    Normaliza fecha de consulta
    Valida que no sea fecha futura ni muy antigua
    """
    if not fecha:
        return None
    
    try:
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, "%Y-%m-%d").date()
        
        # Validar rango razonable (1900 - hoy + 1 día)
        hoy = datetime.now().date()
        fecha_minima = date(1900, 1, 1)
        fecha_maxima = date(hoy.year, hoy.month, hoy.day)
        
        if fecha_minima <= fecha <= fecha_maxima:
            return fecha
        
        return None
    except (ValueError, TypeError):
        return None

def normalizar_hora_consulta(hora: Optional[time]) -> Optional[time]:
    """
    Normaliza hora de consulta
    """
    if not hora:
        return None
    
    try:
        if isinstance(hora, str):
            hora = datetime.strptime(hora, "%H:%M:%S").time()
        
        return hora
    except (ValueError, TypeError):
        return None

def normalizar_acompanante(nombre: Optional[str]) -> Optional[str]:
    """
    Normaliza nombre de acompañante
    """
    if not nombre:
        return None
    
    nombre_str = str(nombre).strip()
    
    if nombre_str:
        # Limpiar y capitalizar
        nombre_limpio = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]', '', nombre_str)
        nombre_limpio = ' '.join(nombre_limpio.split())
        return nombre_limpio[:100] if nombre_limpio else None
    
    return None

def normalizar_parentesco_acompanante(parentesco: Optional[int]) -> Optional[int]:
    """
    Normaliza parentesco de acompañante
    """
    if parentesco is None:
        return None
    
    try:
        parentesco_int = int(parentesco)
        # Validar rango razonable (1-20 típicamente)
        if 1 <= parentesco_int <= 20:
            return parentesco_int
        return None
    except (ValueError, TypeError):
        return None

def normalizar_notas(notas: Optional[str]) -> Optional[str]:
    """
    Normaliza notas de consulta
    """
    if not notas:
        return None
    
    notas_str = str(notas).strip()
    
    if notas_str:
        # Limpiar múltiples espacios
        notas_limpia = ' '.join(notas_str.split())
        return notas_limpia[:1000] if notas_limpia else None
    
    return None

def normalizar_folios(folios: Optional[int]) -> Optional[int]:
    """
    Normaliza número de folios
    """
    if folios is None:
        return None
    
    try:
        folios_int = int(folios)
        # Validar rango razonable (0-100)
        if 0 <= folios_int <= 100:
            return folios_int
        return None
    except (ValueError, TypeError):
        return None

# ============================================================================
# VALIDADORES
# ============================================================================

def validar_consulta_completa(consulta: Dict) -> tuple[bool, str]:
    """
    Valida que una consulta tenga los campos mínimos requeridos
    SOLO fecha es obligatoria - todo lo demás puede tener valores por defecto
    Retorna: (es_valida, mensaje_error)
    """
    
    # Solo fecha es realmente obligatoria
    if not consulta.get("fecha_consulta"):
        return False, "Falta fecha_consulta"
    
    # Validar fecha razonable
    fecha = normalizar_fecha_consulta(consulta.get("fecha_consulta"))
    if not fecha:
        return False, "Fecha de consulta inválida"
    
    # Todo lo demás es opcional con valores por defecto
    return True, ""

# ============================================================================
# FUNCIÓN PRINCIPAL DE NORMALIZACIÓN DE CONSULTA
# ============================================================================

def normalizar_consulta_completa(consulta_raw: Dict) -> Optional[Dict]:
    """
    Normaliza todos los campos de una consulta
    USA VALORES POR DEFECTO para campos faltantes
    Retorna: consulta normalizada o None si es inválida
    """
    
    # Validar primero (solo fecha es obligatoria)
    es_valida, mensaje = validar_consulta_completa(consulta_raw)
    if not es_valida:
        return None
    
    # Valores por defecto
    TIPO_CONSULTA_DEFAULT = 0  # 0 = No especificado
    ESPECIALIDAD_DEFAULT = "NO_ESP"  # No especificada
    SERVICIO_DEFAULT = "NO_ESP"  # No especificado
    HORA_DEFAULT = "00:00:00"  # Medianoche si no hay hora
    
    # Normalizar tipo_consulta con default
    tipo_consulta = normalizar_tipo_consulta(consulta_raw.get("tipo_consulta"))
    if tipo_consulta is None:
        tipo_consulta = TIPO_CONSULTA_DEFAULT
    
    # Normalizar especialidad con default
    especialidad = normalizar_especialidad(consulta_raw.get("especialidad"))
    if especialidad is None:
        especialidad = ESPECIALIDAD_DEFAULT
    
    # Normalizar servicio con default
    servicio = normalizar_servicio(consulta_raw.get("servicio"))
    if servicio is None:
        servicio = SERVICIO_DEFAULT
    
    # Normalizar hora con default
    hora = normalizar_hora_consulta(consulta_raw.get("hora"))
    if hora is None:
        # Intentar obtener hora de fecha_recepcion
        if consulta_raw.get("fecha_recepcion"):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(str(consulta_raw["fecha_recepcion"]))
                hora = dt.time()
            except:
                hora = normalizar_hora_consulta(HORA_DEFAULT)
        else:
            hora = normalizar_hora_consulta(HORA_DEFAULT)
    
    # Normalizar status y derivar estado del ciclo
    status_normalizado = normalizar_status(consulta_raw.get("status"))
    estado_ciclo = normalizar_estado_ciclo(consulta_raw.get("status"))
    
    # Normalizar campos
    consulta_normalizada = {
        # Campos obligatorios (con defaults)
        "tipo_consulta": tipo_consulta,
        "especialidad": especialidad,
        "servicio": servicio,
        "fecha_consulta": normalizar_fecha_consulta(consulta_raw.get("fecha_consulta")),
        "hora_consulta": hora,
        
        # Campos opcionales
        "hoja_emergencia": normalizar_hoja_emergencia(consulta_raw.get("hoja_emergencia")),
        "diagnostico": normalizar_diagnostico(consulta_raw.get("dx")),
        "medico": normalizar_medico(consulta_raw.get("medico")),
        "status": status_normalizado,
        "estado_ciclo": estado_ciclo,  # ✅ Nuevo campo derivado de status
        "acompanante": normalizar_acompanante(consulta_raw.get("acompa")),
        "parentesco_acompanante": normalizar_parentesco_acompanante(consulta_raw.get("parente")),
        "notas": normalizar_notas(consulta_raw.get("nota")),
        "folios": normalizar_folios(consulta_raw.get("folios")),
        
        # Fechas adicionales
        "fecha_egreso": consulta_raw.get("fecha_egreso"),
        "fecha_recepcion": consulta_raw.get("fecha_recepcion"),
        
        # Metadata
        "created_at": consulta_raw.get("created_at"),
        "updated_at": consulta_raw.get("updated_at"),
        "created_by": consulta_raw.get("created_by"),
        "archived_by": consulta_raw.get("archived_by"),
        "consulta_por": consulta_raw.get("consulta_por"),
        
        # Indicadores booleanos
        "prenatal": consulta_raw.get("prenatal"),
        "lactancia": consulta_raw.get("lactancia"),
        "bomberos": consulta_raw.get("bomberos"),
        "transito": consulta_raw.get("transito"),
        "arma_blanca": consulta_raw.get("arma_blanca"),
        "arma_fuego": consulta_raw.get("arma_fuego"),
        "estudiante_publica": consulta_raw.get("estudiante_publica"),
        "accidente_laboral": consulta_raw.get("accidente_laboral"),
        "personal_hospital": consulta_raw.get("personal_hospital"),
        "reserva": consulta_raw.get("reserva"),
        
        # ID original
        "id": consulta_raw.get("id")
    }
    
    return consulta_normalizada

# ============================================================================
# UTILIDADES
# ============================================================================

def estadisticas_normalizacion(consultas_raw: list) -> Dict[str, int]:
    """
    Genera estadísticas de normalización de un conjunto de consultas
    """
    stats = {
        "total": len(consultas_raw),
        "validas": 0,
        "invalidas": 0,
        "sin_tipo": 0,
        "sin_especialidad": 0,
        "sin_servicio": 0,
        "sin_fecha": 0,
        "sin_hora": 0,
        "fechas_invalidas": 0
    }
    
    for consulta in consultas_raw:
        if not consulta.get("tipo_consulta"):
            stats["sin_tipo"] += 1
            stats["invalidas"] += 1
            continue
        
        if not consulta.get("especialidad"):
            stats["sin_especialidad"] += 1
            stats["invalidas"] += 1
            continue
        
        if not consulta.get("servicio"):
            stats["sin_servicio"] += 1
            stats["invalidas"] += 1
            continue
        
        if not consulta.get("fecha_consulta"):
            stats["sin_fecha"] += 1
            stats["invalidas"] += 1
            continue
        
        if not consulta.get("hora"):
            stats["sin_hora"] += 1
            stats["invalidas"] += 1
            continue
        
        # Validar fecha
        fecha = normalizar_fecha_consulta(consulta.get("fecha_consulta"))
        if not fecha:
            stats["fechas_invalidas"] += 1
            stats["invalidas"] += 1
            continue
        
        stats["validas"] += 1
    
    return stats