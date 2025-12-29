# app/services/validacion.py
"""
Servicio de validación para datos de pacientes
Contiene validaciones de negocio y reglas específicas del dominio
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import date, datetime
import re


class ValidacionError(Exception):
    """Excepción personalizada para errores de validación"""
    def __init__(self, campo: str, mensaje: str):
        self.campo = campo
        self.mensaje = mensaje
        super().__init__(f"{campo}: {mensaje}")


class ValidadorPaciente:
    """Validador de datos de pacientes"""
    
    # Constantes de validación
    CUI_LONGITUD = 13
    PASAPORTE_MAX_LENGTH = 50
    EXPEDIENTE_MAX_LENGTH = 20
    NOMBRE_MAX_LENGTH = 100
    TELEFONO_MAX_LENGTH = 20
    
    # Expresiones regulares
    REGEX_EMAIL = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    REGEX_TELEFONO_GT = re.compile(r'^[2-7]\d{7}$|^[3-5]\d{7}$')  # Fijo o móvil GT
    
    @staticmethod
    def validar_cui(cui: Optional[int]) -> Tuple[bool, Optional[str]]:
        """
        Valida CUI guatemalteco (DPI)
        
        Returns:
            (es_valido, mensaje_error)
        """
        if cui is None:
            return True, None  # CUI es opcional
        
        cui_str = str(cui)
        
        # Validar longitud
        if len(cui_str) != ValidadorPaciente.CUI_LONGITUD:
            return False, f"CUI debe tener {ValidadorPaciente.CUI_LONGITUD} dígitos"
        
        # Validar que sean solo números
        if not cui_str.isdigit():
            return False, "CUI debe contener solo números"
        
        # Validar dígito verificador (algoritmo de Guatemala)
        return ValidadorPaciente._validar_digito_verificador_cui(cui_str)
    
    @staticmethod
    def _validar_digito_verificador_cui(cui: str) -> Tuple[bool, Optional[str]]:
        """
        Valida el dígito verificador del CUI guatemalteco
        Algoritmo: módulo 11
        """
        try:
            # Los primeros 8 dígitos son el número base
            # Los siguientes 4 son el código de municipio
            # El último es el dígito verificador
            
            numero_base = cui[:8]
            codigo_municipio = cui[8:12]
            digito_verificador = int(cui[12])
            
            # Concatenar número base + código municipio
            numero_completo = numero_base + codigo_municipio
            
            # Calcular suma ponderada
            suma = 0
            for i, digito in enumerate(reversed(numero_completo)):
                suma += int(digito) * (i + 2)
            
            # Calcular módulo 11
            modulo = suma % 11
            digito_calculado = 11 - modulo
            
            # Si el dígito calculado es 11, el verificador debe ser 0
            if digito_calculado == 11:
                digito_calculado = 0
            # Si el dígito calculado es 10, el CUI es inválido
            elif digito_calculado == 10:
                return False, "CUI con dígito verificador inválido (módulo 10)"
            
            if digito_calculado != digito_verificador:
                return False, f"Dígito verificador incorrecto (esperado: {digito_calculado})"
            
            return True, None
            
        except (ValueError, IndexError) as e:
            return False, f"Error al validar CUI: {str(e)}"
    
    @staticmethod
    def validar_pasaporte(pasaporte: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Valida formato de pasaporte"""
        if not pasaporte:
            return True, None  # Pasaporte es opcional
        
        pasaporte = pasaporte.strip()
        
        if len(pasaporte) > ValidadorPaciente.PASAPORTE_MAX_LENGTH:
            return False, f"Pasaporte muy largo (máx {ValidadorPaciente.PASAPORTE_MAX_LENGTH})"
        
        # Validar que contenga al menos letras y números
        if not any(c.isalpha() for c in pasaporte) or not any(c.isdigit() for c in pasaporte):
            return False, "Pasaporte debe contener letras y números"
        
        return True, None
    
    @staticmethod
    def validar_expediente(expediente: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Valida formato de expediente"""
        if not expediente:
            return False, "Expediente es requerido"
        
        expediente = expediente.strip()
        
        if len(expediente) > ValidadorPaciente.EXPEDIENTE_MAX_LENGTH:
            return False, f"Expediente muy largo (máx {ValidadorPaciente.EXPEDIENTE_MAX_LENGTH})"
        
        # Permitir formato DUP-{id} para duplicados
        if expediente.startswith("DUP-"):
            return True, None
        
        # Validar que sea numérico
        if not expediente.isdigit():
            return False, "Expediente debe ser numérico o formato DUP-{id}"
        
        return True, None
    
    @staticmethod
    def validar_identificadores(
        expediente: Optional[str],
        cui: Optional[int],
        pasaporte: Optional[str]
    ) -> Tuple[bool, List[str]]:
        """
        Valida que exista al menos un identificador válido
        
        Returns:
            (es_valido, lista_errores)
        """
        errores = []
        
        # Validar cada identificador
        valido_exp, error_exp = ValidadorPaciente.validar_expediente(expediente)
        if not valido_exp:
            errores.append(error_exp)
        
        valido_cui, error_cui = ValidadorPaciente.validar_cui(cui)
        if not valido_cui:
            errores.append(error_cui)
        
        valido_pass, error_pass = ValidadorPaciente.validar_pasaporte(pasaporte)
        if not valido_pass:
            errores.append(error_pass)
        
        # Al menos uno debe ser válido
        if not (valido_exp or valido_cui or valido_pass):
            errores.append("Debe proporcionar al menos un identificador válido")
            return False, errores
        
        return True, errores
    
    @staticmethod
    def validar_nombre_jsonb(nombre: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Valida estructura y contenido del JSONB de nombre
        
        Estructura esperada:
        {
            "primer_nombre": "Juan",
            "segundo_nombre": "Carlos",
            "otros_nombres": None,
            "primer_apellido": "Pérez",
            "segundo_apellido": "García",
            "apellido_casada": None
        }
        """
        errores = []
        
        if not isinstance(nombre, dict):
            return False, ["Nombre debe ser un objeto JSON"]
        
        # Campos requeridos
        campos_requeridos = ["primer_nombre", "primer_apellido"]
        for campo in campos_requeridos:
            if not nombre.get(campo):
                errores.append(f"{campo} es requerido")
        
        # Validar longitud de nombres
        for campo, valor in nombre.items():
            if valor and isinstance(valor, str):
                if len(valor) > ValidadorPaciente.NOMBRE_MAX_LENGTH:
                    errores.append(
                        f"{campo} muy largo (máx {ValidadorPaciente.NOMBRE_MAX_LENGTH})"
                    )
                
                # Validar que solo contenga letras, espacios y caracteres válidos
                if not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s\'-]+$', valor):
                    errores.append(f"{campo} contiene caracteres inválidos")
        
        return len(errores) == 0, errores
    
    @staticmethod
    def validar_sexo(sexo: str) -> Tuple[bool, Optional[str]]:
        """Valida valor de sexo"""
        valores_validos = ['M', 'F', 'NF']
        
        if sexo not in valores_validos:
            return False, f"Sexo debe ser uno de: {', '.join(valores_validos)}"
        
        return True, None
    
    @staticmethod
    def validar_fecha_nacimiento(fecha: Optional[date]) -> Tuple[bool, Optional[str]]:
        """Valida fecha de nacimiento"""
        if not fecha:
            return True, None  # Fecha es opcional
        
        hoy = date.today()
        
        # No puede ser fecha futura
        if fecha > hoy:
            return False, "Fecha de nacimiento no puede ser futura"
        
        # Edad máxima razonable (150 años)
        edad_maxima = 150
        fecha_minima = date(hoy.year - edad_maxima, hoy.month, hoy.day)
        
        if fecha < fecha_minima:
            return False, f"Fecha de nacimiento muy antigua (máx {edad_maxima} años)"
        
        return True, None
    
    @staticmethod
    def calcular_edad(fecha_nacimiento: date) -> int:
        """Calcula edad en años a partir de fecha de nacimiento"""
        hoy = date.today()
        edad = hoy.year - fecha_nacimiento.year
        
        # Ajustar si aún no ha cumplido años este año
        if (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day):
            edad -= 1
        
        return edad
    
    @staticmethod
    def validar_contacto_jsonb(contacto: Optional[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        Valida estructura del JSONB de contacto
        
        Estructura esperada:
        {
            "telefono_principal": "12345678",
            "email": "correo@ejemplo.com",
            "direccion": {
                "linea1": "Calle 123",
                "municipio_id": 1,
                "departamento_id": 1
            }
        }
        """
        if not contacto:
            return True, []  # Contacto es opcional
        
        errores = []
        
        if not isinstance(contacto, dict):
            return False, ["Contacto debe ser un objeto JSON"]
        
        # Validar teléfono
        telefono = contacto.get("telefono_principal")
        if telefono:
            if len(str(telefono)) > ValidadorPaciente.TELEFONO_MAX_LENGTH:
                errores.append(f"Teléfono muy largo (máx {ValidadorPaciente.TELEFONO_MAX_LENGTH})")
        
        # Validar email
        email = contacto.get("email")
        if email:
            if not ValidadorPaciente.REGEX_EMAIL.match(email):
                errores.append("Formato de email inválido")
        
        # Validar dirección
        direccion = contacto.get("direccion")
        if direccion and isinstance(direccion, dict):
            if not direccion.get("linea1"):
                errores.append("Dirección debe incluir al menos linea1")
        
        return len(errores) == 0, errores
    
    @staticmethod
    def validar_estado(estado: str) -> Tuple[bool, Optional[str]]:
        """Valida estado del paciente"""
        estados_validos = ['V', 'F']  # Vivo, Fallecido
        
        if estado not in estados_validos:
            return False, f"Estado debe ser uno de: {', '.join(estados_validos)}"
        
        return True, None
    
    @staticmethod
    def validar_referencias_jsonb(
        referencias: Optional[Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """
        Valida estructura del JSONB de referencias
        
        Estructura esperada:
        {
            "padre": "Nombre Padre",
            "madre": "Nombre Madre",
            "expediente_madre": 12345,
            "responsable": {
                "nombre": "Nombre Responsable",
                "parentesco_id": 1,
                "cui": 1234567890123,
                "telefono": 12345678,
                "expediente": 67890
            },
            "conyugue": "Nombre Conyugue",
            "es_gemelo": false
        }
        """
        if not referencias:
            return True, []  # Referencias son opcionales
        
        errores = []
        
        if not isinstance(referencias, dict):
            return False, ["Referencias debe ser un objeto JSON"]
        
        # Validar CUI del responsable si existe
        responsable = referencias.get("responsable")
        if responsable and isinstance(responsable, dict):
            cui_resp = responsable.get("cui")
            if cui_resp:
                valido, error = ValidadorPaciente.validar_cui(cui_resp)
                if not valido:
                    errores.append(f"CUI del responsable: {error}")
        
        # Validar tipo de es_gemelo
        es_gemelo = referencias.get("es_gemelo")
        if es_gemelo is not None and not isinstance(es_gemelo, bool):
            errores.append("es_gemelo debe ser true o false")
        
        return len(errores) == 0, errores
    
    @staticmethod
    def validar_datos_extra_jsonb(
        datos_extra: Optional[Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """
        Valida estructura del JSONB de datos_extra
        
        Estructura esperada:
        {
            "demograficos": {
                "nacionalidad_id": 1,
                "departamento_nacimiento_id": 1,
                "lugar_nacimiento_id": 1,
                "estado_civil_id": 1,
                "pueblo_id": 1,
                "idioma_id": 1
            },
            "socioeconomicos": {
                "educacion_id": 1,
                "ocupacion": "Ingeniero"
            },
            "defuncion": {
                "fecha_hora": "2024-01-15T10:30:00"
            }
        }
        """
        if not datos_extra:
            return True, []  # Datos extra son opcionales
        
        errores = []
        
        if not isinstance(datos_extra, dict):
            return False, ["datos_extra debe ser un objeto JSON"]
        
        # Validar fecha de defunción si existe
        defuncion = datos_extra.get("defuncion")
        if defuncion and isinstance(defuncion, dict):
            fecha_hora = defuncion.get("fecha_hora")
            if fecha_hora:
                try:
                    fecha_def = datetime.fromisoformat(fecha_hora)
                    
                    # No puede ser fecha futura
                    if fecha_def > datetime.now():
                        errores.append("Fecha de defunción no puede ser futura")
                        
                except ValueError:
                    errores.append("Formato de fecha_hora de defunción inválido")
        
        return len(errores) == 0, errores
    
    @staticmethod
    def validar_paciente_completo(
        expediente: Optional[str],
        cui: Optional[int],
        pasaporte: Optional[str],
        nombre: Dict[str, Any],
        sexo: str,
        fecha_nacimiento: Optional[date],
        contacto: Optional[Dict[str, Any]] = None,
        referencias: Optional[Dict[str, Any]] = None,
        datos_extra: Optional[Dict[str, Any]] = None,
        estado: str = "V"
    ) -> Tuple[bool, Dict[str, List[str]]]:
        """
        Validación completa de un paciente
        
        Returns:
            (es_valido, diccionario_de_errores_por_campo)
        """
        errores_por_campo = {}
        
        # Validar identificadores
        valido_ids, errores_ids = ValidadorPaciente.validar_identificadores(
            expediente, cui, pasaporte
        )
        if not valido_ids:
            errores_por_campo["identificadores"] = errores_ids
        
        # Validar nombre
        valido_nombre, errores_nombre = ValidadorPaciente.validar_nombre_jsonb(nombre)
        if not valido_nombre:
            errores_por_campo["nombre"] = errores_nombre
        
        # Validar sexo
        valido_sexo, error_sexo = ValidadorPaciente.validar_sexo(sexo)
        if not valido_sexo:
            errores_por_campo["sexo"] = [error_sexo]
        
        # Validar fecha de nacimiento
        valido_fecha, error_fecha = ValidadorPaciente.validar_fecha_nacimiento(
            fecha_nacimiento
        )
        if not valido_fecha:
            errores_por_campo["fecha_nacimiento"] = [error_fecha]
        
        # Validar contacto
        valido_contacto, errores_contacto = ValidadorPaciente.validar_contacto_jsonb(
            contacto
        )
        if not valido_contacto:
            errores_por_campo["contacto"] = errores_contacto
        
        # Validar referencias
        valido_refs, errores_refs = ValidadorPaciente.validar_referencias_jsonb(
            referencias
        )
        if not valido_refs:
            errores_por_campo["referencias"] = errores_refs
        
        # Validar datos extra
        valido_extra, errores_extra = ValidadorPaciente.validar_datos_extra_jsonb(
            datos_extra
        )
        if not valido_extra:
            errores_por_campo["datos_extra"] = errores_extra
        
        # Validar estado
        valido_estado, error_estado = ValidadorPaciente.validar_estado(estado)
        if not valido_estado:
            errores_por_campo["estado"] = [error_estado]
        
        # Validación de reglas de negocio
        if estado == "F" and not (datos_extra and datos_extra.get("defuncion")):
            errores_por_campo["estado"] = ["Paciente fallecido debe tener fecha de defunción"]
        
        es_valido = len(errores_por_campo) == 0
        return es_valido, errores_por_campo


class ValidadorMigracion:
    """Validador específico para el proceso de migración"""
    
    @staticmethod
    def validar_datos_mysql(datos_mysql: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Valida que los datos de MySQL sean coherentes antes de migrar"""
        errores = []
        
        # Validar que exista al menos nombre o apellido
        if not datos_mysql.get("nombre") and not datos_mysql.get("apellido"):
            errores.append("Debe tener al menos nombre o apellido")
        
        # Validar que la fecha de creación no sea futura
        created_at = datos_mysql.get("created_at")
        if created_at and isinstance(created_at, datetime):
            if created_at > datetime.now():
                errores.append("Fecha de creación no puede ser futura")
        
        # Validar coherencia de datos de defunción
        tiene_fecha_def = bool(datos_mysql.get("fechaDefuncion"))
        estado_fallecido = datos_mysql.get("estado") in ("F", "FALLECIDO")
        
        if tiene_fecha_def != estado_fallecido:
            errores.append(
                "Inconsistencia: fecha de defunción no coincide con estado"
            )
        
        return len(errores) == 0, errores
    
    @staticmethod
    def validar_integridad_referencial(
        exp_madre: Optional[int],
        exp_ref: Optional[int],
        expedientes_existentes: set
    ) -> Tuple[bool, List[str]]:
        """Valida que las referencias a otros expedientes existan"""
        errores = []
        
        if exp_madre and exp_madre not in expedientes_existentes:
            errores.append(f"Expediente de madre {exp_madre} no existe")
        
        if exp_ref and exp_ref not in expedientes_existentes:
            errores.append(f"Expediente de referencia {exp_ref} no existe")
        
        return len(errores) == 0, errores


# Funciones de utilidad para validación rápida

def es_cui_valido(cui: Optional[int]) -> bool:
    """Validación rápida de CUI"""
    valido, _ = ValidadorPaciente.validar_cui(cui)
    return valido


def es_mayor_de_edad(fecha_nacimiento: date) -> bool:
    """Determina si es mayor de 18 años"""
    edad = ValidadorPaciente.calcular_edad(fecha_nacimiento)
    return edad >= 18


def es_menor_de_edad(fecha_nacimiento: date) -> bool:
    """Determina si es menor de 18 años"""
    return not es_mayor_de_edad(fecha_nacimiento)