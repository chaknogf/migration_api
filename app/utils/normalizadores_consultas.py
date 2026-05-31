# app/utils/normalizadores_consultas.py
"""
Normalizadores específicos para consultas
Complementan los normalizadores de pacientes

FIXES aplicados:
  - normalizar_estado_ciclo() ahora acepta int, str, o None sin excepción.
    El mapeo explícito cubre las cuatro variantes que puede enviar MySQL:
      1  / "1"  → "admision"
      2  / "2"  → "archivo"
      NULL / otro → "recepcion"  (valor por defecto)
  - normalizar_consulta_completa() expone el campo "estado_ciclo" en el dict
    de retorno para que migrar_postgres.py lo lea desde c_norm en lugar de
    llamar a normalizar_estado_ciclo() una segunda vez con el entero crudo.
"""

from typing import Optional, Dict, Any
from datetime import datetime, time, date
import re

# ============================================================================
# NORMALIZADORES DE CONSULTAS
# ============================================================================

def normalizar_tipo_consulta(tipo: Optional[int]) -> Optional[int]:
    """
    Normaliza tipo de consulta.
    Valores típicos: 1=COEX, 2=Hospitalizacion, 3=Emergencia, etc.
    """
    if tipo is None:
        return None

    try:
        tipo_int = int(tipo)
        if 0 <= tipo_int <= 10:
            return tipo_int
        return None
    except (ValueError, TypeError):
        return None


def normalizar_especialidad(especialidad: Optional[int]) -> Optional[str]:
    """
    Normaliza especialidad médica.
    Convierte código numérico a código de especialidad.
    Retorna None si el valor es inválido (para usar default después).
    """
    if especialidad is None:
        return None

    try:
        esp_int = int(especialidad)

        ESPECIALIDADES_MAP = {
            0:  "GENE",
            1:  "MEDI",
            2:  "PEDI",
            3:  "GINE",
            4:  "CIRU",
            5:  "TRAU",
            6:  "PSIC",
            7:  "NUTR",
            8:  "ODON",
            -1: "NO_ESP",
        }

        return ESPECIALIDADES_MAP.get(esp_int, "NO_ESP")
    except (ValueError, TypeError):
        return None


def normalizar_servicio(
    servicio: Optional[int],
    tipo_consulta: Optional[int] = None,
    sexo: Optional[str] = None,          # 'M', 'F', o None
) -> str:
    """
    Normaliza servicio hospitalario cruzando tipo_consulta + valor numérico + sexo.

    Reglas:
      tipo_consulta = 1  → siempre 'COEX'
      tipo_consulta = 3  → siempre 'EMER'
      tipo_consulta = 2  → HOSP_MAP; los valores 4/5/6/7 se bifurcan por sexo:
                           M → CIHO / TRHO
                           F → CIMU / TRMU
                           None → CIHO / TRHO  (fallback masculino como genérico)
    """
    try:
        tc = int(tipo_consulta) if tipo_consulta is not None else None
    except (ValueError, TypeError):
        tc = None

    if tc == 1:
        return "COEX"
    if tc == 3:
        return "EMER"

    # Normalizar sexo para la bifurcación
    es_mujer = str(sexo).strip().upper() == "F" if sexo else False

    HOSP_MAP = {
        0:  "EMER",
        1:  "SOPR",
        2:  "MATE",
        3:  "GINI",
        4:  "CIMU" if es_mujer else "CIHO",   # Cirugía  ← bifurca por sexo
        5:  "CIMU" if es_mujer else "CIHO",   # Cirugía pedia  ← ídem
        6:  "TRMU" if es_mujer else "TRHO",   # Trauma  ← bifurca por sexo
        7:  "TRMU" if es_mujer else "TRHO",   # Trauma pedia  ← ídem
        8:  "CRN_",
        9:  "PEDA",
        10: "NEON",
        11: "NEON",
        12: "MEHO",
        13: "MEMU",
        14: "OTRO",   # VSVS — sin equivalente
        15: "OTRO",   # COVID — disuelto
        16: "MATE",   # Labor & parto
        17: "AROJ",
        18: "MEDI",
        19: "UCIN",
        20: "COEX",
        21: "EMER",
    }

    if servicio is None:
        return "OTRO"

    try:
        return HOSP_MAP.get(int(servicio), "OTRO")
    except (ValueError, TypeError):
        return "OTRO"
def normalizar_hoja_emergencia(hoja: Optional[str]) -> Optional[str]:
    """Normaliza número de hoja de emergencia."""
    if not hoja:
        return None

    hoja_str   = str(hoja).strip().upper()
    hoja_limpia = re.sub(r'[^A-Z0-9\-]', '', hoja_str)
    return hoja_limpia if hoja_limpia else None


def normalizar_diagnostico(dx: Optional[str]) -> Optional[str]:
    """Normaliza diagnóstico. Limpia espacios y limita longitud."""
    if not dx:
        return None

    dx_str   = str(dx).strip()
    dx_limpio = ' '.join(dx_str.split())
    return dx_limpio[:500] if dx_limpio else None


def normalizar_medico(medico: Optional[str]) -> Optional[str]:
    """Normaliza nombre de médico."""
    if not medico:
        return None

    medico_str = str(medico).strip()
    if medico_str:
        medico_limpio = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s\.]', '', medico_str)
        medico_limpio = ' '.join(medico_limpio.split())
        return medico_limpio[:100] if medico_limpio else None

    return None


def normalizar_estado_ciclo(status) -> str:
    """
    Convierte el campo status de MySQL al valor de texto que se almacena en
    la columna ultimo_estado de PostgreSQL (y en ciclo->>'estado').

    MySQL puede enviar el valor como entero o como string numérico según el
    driver y la versión de la tabla, por lo que el mapeo cubre ambas formas:

        1  / "1"  →  "admision"
        2  / "2"  →  "archivo"
        NULL / otro valor →  "recepcion"  (estado por defecto)

    La función no lanza excepciones: cualquier valor no reconocido devuelve
    el default "recepcion".
    """
    if status is None:
        return "recepcion"

    # FIX: mapa explícito con las cuatro variantes posibles de MySQL.
    # El mapeo int+str evita depender de una conversión previa al llamar
    # esta función, ya sea desde el script de migración o desde la API.
    MAPA = {
        1:   "admision",
        "1": "admision",
        2:   "archivo",
        "2": "archivo",
        # Si por alguna razón el valor ya viene normalizado como string
        # (p.ej. llamada desde otro módulo), lo pasamos tal cual.
        "admision":  "admision",
        "archivo":   "archivo",
        "recepcion": "recepcion",
    }

    try:
        # Intentar lookup directo (cubre int y str exactos del mapa)
        if status in MAPA:
            return MAPA[status]
        # Fallback: convertir a int por si llega como float (p.ej. 1.0)
        return MAPA.get(int(status), "recepcion")
    except (ValueError, TypeError):
        return "recepcion"


def normalizar_status(status: Optional[int]) -> Optional[int]:
    """
    Normaliza el status numérico de la consulta para guardarlo en ciclo JSONB.
    Rango válido: 0-10.
    """
    if status is None:
        return None

    try:
        status_int = int(status)
        if 0 <= status_int <= 10:
            return status_int
        return None
    except (ValueError, TypeError):
        return None


def normalizar_fecha_consulta(fecha: Optional[date]) -> Optional[date]:
    """
    Normaliza fecha de consulta.
    Valida que no sea fecha futura ni anterior a 1900.
    """
    if not fecha:
        return None

    try:
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, "%Y-%m-%d").date()

        hoy          = datetime.now().date()
        fecha_minima = date(1900, 1, 1)

        if fecha_minima <= fecha <= hoy:
            return fecha

        return None
    except (ValueError, TypeError):
        return None


def normalizar_hora_consulta(hora: Optional[time]) -> Optional[time]:
    """Normaliza hora de consulta."""
    if not hora:
        return None

    try:
        if isinstance(hora, str):
            hora = datetime.strptime(hora, "%H:%M:%S").time()
        return hora
    except (ValueError, TypeError):
        return None


def normalizar_acompanante(nombre: Optional[str]) -> Optional[str]:
    """Normaliza nombre de acompañante."""
    if not nombre:
        return None

    nombre_str = str(nombre).strip()
    if nombre_str:
        nombre_limpio = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]', '', nombre_str)
        nombre_limpio = ' '.join(nombre_limpio.split())
        return nombre_limpio[:100] if nombre_limpio else None

    return None


def normalizar_parentesco_acompanante(parentesco: Optional[int]) -> Optional[int]:
    """Normaliza parentesco de acompañante."""
    if parentesco is None:
        return None

    try:
        parentesco_int = int(parentesco)
        if 1 <= parentesco_int <= 20:
            return parentesco_int
        return None
    except (ValueError, TypeError):
        return None


def normalizar_notas(notas: Optional[str]) -> Optional[str]:
    """Normaliza notas de consulta."""
    if not notas:
        return None

    notas_str = str(notas).strip()
    if notas_str:
        notas_limpia = ' '.join(notas_str.split())
        return notas_limpia[:1000] if notas_limpia else None

    return None


def normalizar_folios(folios: Optional[int]) -> Optional[int]:
    """Normaliza número de folios."""
    if folios is None:
        return None

    try:
        folios_int = int(folios)
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
    Valida que una consulta tenga los campos mínimos requeridos.
    Solo fecha es obligatoria; el resto puede tener valores por defecto.
    Retorna: (es_valida, mensaje_error)
    """
    if not consulta.get("fecha_consulta"):
        return False, "Falta fecha_consulta"

    fecha = normalizar_fecha_consulta(consulta.get("fecha_consulta"))
    if not fecha:
        return False, "Fecha de consulta inválida"

    return True, ""


# ============================================================================
# FUNCIÓN PRINCIPAL DE NORMALIZACIÓN DE CONSULTA
# ============================================================================

def normalizar_consulta_completa(
    consulta_raw: Dict,
    sexo: Optional[str] = None,    # nuevo parámetro
) -> Optional[Dict]:
    """
    Normaliza todos los campos de una consulta.
    Usa valores por defecto para campos faltantes.
    Retorna la consulta normalizada o None si es inválida (sin fecha).

    El dict de retorno incluye el campo "estado_ciclo" con el valor ya
    convertido a string ("admision" / "archivo" / "recepcion") para que
    migrar_postgres.py lo lea directamente sin una segunda llamada a
    normalizar_estado_ciclo().
    """
    es_valida, mensaje = validar_consulta_completa(consulta_raw)
    if not es_valida:
        return None

    TIPO_CONSULTA_DEFAULT = 0
    ESPECIALIDAD_DEFAULT  = "NO_ESP"
    SERVICIO_DEFAULT      = "NO_ESP"
    HORA_DEFAULT          = "00:00:00"

    tipo_consulta = normalizar_tipo_consulta(consulta_raw.get("tipo_consulta"))
    if tipo_consulta is None:
        tipo_consulta = TIPO_CONSULTA_DEFAULT

    especialidad = normalizar_especialidad(consulta_raw.get("especialidad"))
    if especialidad is None:
        especialidad = ESPECIALIDAD_DEFAULT

    servicio = normalizar_servicio(
        consulta_raw.get("servicio"),
        tipo_consulta,
        sexo,
    )


    hora = normalizar_hora_consulta(consulta_raw.get("hora"))
    if hora is None:
        if consulta_raw.get("fecha_recepcion"):
            try:
                dt   = datetime.fromisoformat(str(consulta_raw["fecha_recepcion"]))
                hora = dt.time()
            except Exception:
                hora = normalizar_hora_consulta(HORA_DEFAULT)
        else:
            hora = normalizar_hora_consulta(HORA_DEFAULT)

    # FIX: normalizar_estado_ciclo() recibe el entero crudo de MySQL y devuelve
    # el string correcto.  El resultado se guarda en "estado_ciclo" para que
    # _construir_ciclo() y transformar_consulta() lo lean desde c_norm sin
    # necesidad de llamar otra vez al normalizador.
    status_raw    = consulta_raw.get("status")
    status_int    = normalizar_status(status_raw)
    estado_ciclo  = normalizar_estado_ciclo(status_raw)

    return {
        # Campos obligatorios (con defaults)
        "tipo_consulta":  tipo_consulta,
        "especialidad":   especialidad,
        "servicio":       servicio,
        "fecha_consulta": normalizar_fecha_consulta(consulta_raw.get("fecha_consulta")),
        "hora_consulta":  hora,

        # Estado normalizado — única fuente de verdad para ultimo_estado y ciclo->estado
        "status":        status_int,
        "estado_ciclo":  estado_ciclo,

        # Campos opcionales
        "hoja_emergencia":        normalizar_hoja_emergencia(consulta_raw.get("hoja_emergencia")),
        "diagnostico":            normalizar_diagnostico(consulta_raw.get("dx")),
        "medico":                 normalizar_medico(consulta_raw.get("medico")),
        "acompanante":            normalizar_acompanante(consulta_raw.get("acompa")),
        "parentesco_acompanante": normalizar_parentesco_acompanante(consulta_raw.get("parente")),
        "notas":                  normalizar_notas(consulta_raw.get("nota")),
        "folios":                 normalizar_folios(consulta_raw.get("folios")),

        # Fechas adicionales
        "fecha_egreso":    consulta_raw.get("fecha_egreso"),
        "fecha_recepcion": consulta_raw.get("fecha_recepcion"),

        # Metadata
        "created_at":   consulta_raw.get("created_at"),
        "updated_at":   consulta_raw.get("updated_at"),
        "created_by":   consulta_raw.get("created_by"),
        "archived_by":  consulta_raw.get("archived_by"),
        "consulta_por": consulta_raw.get("consulta_por"),

        # Indicadores booleanos (se pasan como referencia a _construir_indicadores)
        "prenatal":            consulta_raw.get("prenatal"),
        "lactancia":           consulta_raw.get("lactancia"),
        "bomberos":            consulta_raw.get("bomberos"),
        "transito":            consulta_raw.get("transito"),
        "arma_blanca":         consulta_raw.get("arma_blanca"),
        "arma_fuego":          consulta_raw.get("arma_fuego"),
        "estudiante_publica":  consulta_raw.get("estudiante_publica"),
        "accidente_laboral":   consulta_raw.get("accidente_laboral"),
        "personal_hospital":   consulta_raw.get("personal_hospital"),
        "reserva":             consulta_raw.get("reserva"),

        # ID original
        "id": consulta_raw.get("id"),
    }


# ============================================================================
# UTILIDADES
# ============================================================================

def estadisticas_normalizacion(consultas_raw: list) -> Dict[str, int]:
    """
    Genera estadísticas de normalización de un conjunto de consultas.
    Útil para diagnóstico antes de la migración.
    """
    stats = {
        "total":            len(consultas_raw),
        "validas":          0,
        "invalidas":        0,
        "sin_tipo":         0,
        "sin_especialidad": 0,
        "sin_servicio":     0,
        "sin_fecha":        0,
        "sin_hora":         0,
        "fechas_invalidas": 0,
    }

    for consulta in consultas_raw:
        if not consulta.get("tipo_consulta"):
            stats["sin_tipo"]    += 1
            stats["invalidas"]   += 1
            continue

        if not consulta.get("especialidad"):
            stats["sin_especialidad"] += 1
            stats["invalidas"]        += 1
            continue

        if not consulta.get("servicio"):
            stats["sin_servicio"] += 1
            stats["invalidas"]    += 1
            continue

        if not consulta.get("fecha_consulta"):
            stats["sin_fecha"]  += 1
            stats["invalidas"]  += 1
            continue

        if not consulta.get("hora"):
            stats["sin_hora"]   += 1
            stats["invalidas"]  += 1
            continue

        fecha = normalizar_fecha_consulta(consulta.get("fecha_consulta"))
        if not fecha:
            stats["fechas_invalidas"] += 1
            stats["invalidas"]        += 1
            continue

        stats["validas"] += 1

    return stats