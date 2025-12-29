"""
Schemas Pydantic para Pacientes
Validación, serialización y documentación de API
"""

from pydantic import (
    BaseModel, Field, EmailStr, field_validator, model_validator,
    ConfigDict
)
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from enum import Enum


# ═══════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════

class SexoEnum(str, Enum):
    """Opciones de sexo"""
    MASCULINO = "M"
    FEMENINO = "F"
    NO_ESPECIFICADO = "NF"


class EstadoEnum(str, Enum):
    """Estado del paciente"""
    VIVO = "V"
    FALLECIDO = "F"


# ═══════════════════════════════════════════════════════════
# SCHEMAS JSONB (Sub-estructuras)
# ═══════════════════════════════════════════════════════════

class NombreSchema(BaseModel):
    """Schema para el JSONB de nombre"""
    
    primer_nombre: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Primer nombre del paciente",
        examples=["Juan"]
    )
    segundo_nombre: Optional[str] = Field(
        None,
        max_length=100,
        description="Segundo nombre del paciente",
        examples=["Carlos"]
    )
    otros_nombres: Optional[str] = Field(
        None,
        max_length=100,
        description="Otros nombres adicionales",
        examples=["José María"]
    )
    primer_apellido: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Primer apellido del paciente",
        examples=["Pérez"]
    )
    segundo_apellido: Optional[str] = Field(
        None,
        max_length=100,
        description="Segundo apellido del paciente",
        examples=["García"]
    )
    apellido_casada: Optional[str] = Field(
        None,
        max_length=100,
        description="Apellido de casada (si aplica)",
        examples=["López"]
    )
    
    @field_validator('primer_nombre', 'segundo_nombre', 'otros_nombres', 
                     'primer_apellido', 'segundo_apellido', 'apellido_casada')
    @classmethod
    def validar_solo_letras(cls, v: Optional[str]) -> Optional[str]:
        """Valida que solo contenga letras, espacios y caracteres válidos"""
        if v is None:
            return v
        
        import re
        if not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s\'-]+$', v):
            raise ValueError('Debe contener solo letras, espacios, guiones y apóstrofes')
        
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "primer_nombre": "Juan",
                "segundo_nombre": "Carlos",
                "otros_nombres": None,
                "primer_apellido": "Pérez",
                "segundo_apellido": "García",
                "apellido_casada": None
            }
        }
    )


class DireccionSchema(BaseModel):
    """Schema para dirección dentro de contacto"""
    
    linea1: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Dirección principal",
        examples=["5ta Avenida 10-50, Zona 1"]
    )
    linea2: Optional[str] = Field(
        None,
        max_length=200,
        description="Dirección adicional (edificio, apartamento, etc.)",
        examples=["Edificio Plaza, Oficina 301"]
    )
    municipio_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID del municipio (catálogo)",
        examples=[1]
    )
    departamento_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID del departamento (catálogo)",
        examples=[1]
    )


class ContactoSchema(BaseModel):
    """Schema para el JSONB de contacto"""
    
    telefono_principal: Optional[str] = Field(
        None,
        min_length=8,
        max_length=20,
        description="Teléfono principal del paciente",
        examples=["12345678"]
    )
    telefono_secundario: Optional[str] = Field(
        None,
        min_length=8,
        max_length=20,
        description="Teléfono secundario",
        examples=["87654321"]
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Correo electrónico",
        examples=["paciente@ejemplo.com"]
    )
    direccion: Optional[DireccionSchema] = Field(
        None,
        description="Dirección del paciente"
    )
    
    @field_validator('telefono_principal', 'telefono_secundario')
    @classmethod
    def validar_telefono(cls, v: Optional[str]) -> Optional[str]:
        """Valida formato de teléfono guatemalteco"""
        if v is None:
            return v
        
        # Limpiar caracteres no numéricos
        import re
        telefono_limpio = re.sub(r'[^\d]', '', v)
        
        # Validar longitud (8 dígitos para Guatemala)
        if len(telefono_limpio) != 8:
            raise ValueError('Teléfono debe tener 8 dígitos')
        
        return telefono_limpio
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "telefono_principal": "12345678",
                "telefono_secundario": "87654321",
                "email": "paciente@ejemplo.com",
                "direccion": {
                    "linea1": "5ta Avenida 10-50, Zona 1",
                    "municipio_id": 1,
                    "departamento_id": 1
                }
            }
        }
    )


class ResponsableSchema(BaseModel):
    """Schema para datos del responsable dentro de referencias"""
    
    nombre: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Nombre completo del responsable",
        examples=["María García"]
    )
    parentesco_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID del parentesco (catálogo)",
        examples=[1]
    )
    cui: Optional[int] = Field(
        None,
        description="CUI/DPI del responsable (13 dígitos)",
        examples=[1234567890123]
    )
    telefono: Optional[str] = Field(
        None,
        min_length=8,
        max_length=20,
        description="Teléfono del responsable",
        examples=["12345678"]
    )
    expediente: Optional[int] = Field(
        None,
        ge=1,
        description="Número de expediente del responsable (si es paciente)",
        examples=[12345]
    )
    
    @field_validator('cui')
    @classmethod
    def validar_cui(cls, v: Optional[int]) -> Optional[int]:
        """Valida que el CUI tenga 13 dígitos"""
        if v is None:
            return v
        
        cui_str = str(v)
        if len(cui_str) != 13:
            raise ValueError('CUI debe tener 13 dígitos')
        
        return v


class ReferenciasSchema(BaseModel):
    """Schema para el JSONB de referencias familiares"""
    
    padre: Optional[str] = Field(
        None,
        max_length=100,
        description="Nombre del padre",
        examples=["Pedro Pérez"]
    )
    madre: Optional[str] = Field(
        None,
        max_length=100,
        description="Nombre de la madre",
        examples=["Ana García"]
    )
    expediente_madre: Optional[int] = Field(
        None,
        ge=1,
        description="Expediente de la madre (si es paciente)",
        examples=[12345]
    )
    responsable: Optional[ResponsableSchema] = Field(
        None,
        description="Datos del responsable del paciente"
    )
    conyugue: Optional[str] = Field(
        None,
        max_length=100,
        description="Nombre del conyugue",
        examples=["María López"]
    )
    es_gemelo: bool = Field(
        default=False,
        description="Indica si el paciente es gemelo",
        examples=[False]
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "padre": "Pedro Pérez",
                "madre": "Ana García",
                "expediente_madre": 12345,
                "responsable": {
                    "nombre": "María García",
                    "parentesco_id": 1,
                    "cui": 1234567890123,
                    "telefono": "12345678"
                },
                "conyugue": "María López",
                "es_gemelo": False
            }
        }
    )


class DemograficosSchema(BaseModel):
    """Schema para datos demográficos dentro de datos_extra"""
    
    nacionalidad_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID de nacionalidad (catálogo)",
        examples=[1]
    )
    departamento_nacimiento_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID del departamento de nacimiento (catálogo)",
        examples=[1]
    )
    lugar_nacimiento_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID del lugar de nacimiento (catálogo)",
        examples=[1]
    )
    estado_civil_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID del estado civil (catálogo)",
        examples=[1]
    )
    pueblo_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID del pueblo/etnia (catálogo)",
        examples=[1]
    )
    idioma_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID del idioma (catálogo)",
        examples=[1]
    )


class SocioeconomicosSchema(BaseModel):
    """Schema para datos socioeconómicos dentro de datos_extra"""
    
    educacion_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID del nivel educativo (catálogo)",
        examples=[1]
    )
    ocupacion: Optional[str] = Field(
        None,
        max_length=100,
        description="Ocupación del paciente",
        examples=["Ingeniero"]
    )


class DefuncionSchema(BaseModel):
    """Schema para datos de defunción dentro de datos_extra"""
    
    fecha_hora: datetime = Field(
        ...,
        description="Fecha y hora de defunción",
        examples=["2024-01-15T10:30:00"]
    )
    lugar: Optional[str] = Field(
        None,
        max_length=200,
        description="Lugar de defunción",
        examples=["Hospital General"]
    )
    causa: Optional[str] = Field(
        None,
        max_length=500,
        description="Causa de defunción",
        examples=["Paro cardiorrespiratorio"]
    )
    
    @field_validator('fecha_hora')
    @classmethod
    def validar_fecha_no_futura(cls, v: datetime) -> datetime:
        """Valida que la fecha de defunción no sea futura"""
        if v > datetime.now():
            raise ValueError('Fecha de defunción no puede ser futura')
        return v


class DatosExtraSchema(BaseModel):
    """Schema para el JSONB de datos_extra"""
    
    demograficos: Optional[DemograficosSchema] = Field(
        None,
        description="Datos demográficos del paciente"
    )
    socioeconomicos: Optional[SocioeconomicosSchema] = Field(
        None,
        description="Datos socioeconómicos del paciente"
    )
    defuncion: Optional[DefuncionSchema] = Field(
        None,
        description="Datos de defunción (solo si está fallecido)"
    )
    notas_clinicas: Optional[str] = Field(
        None,
        max_length=1000,
        description="Notas clínicas adicionales",
        examples=["Alérgico a la penicilina"]
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
                "defuncion": None,
                "notas_clinicas": "Sin alergias conocidas"
            }
        }
    )


class MetadatosSchema(BaseModel):
    """Schema para el JSONB de metadatos del sistema"""
    
    sistema_origen: Optional[str] = Field(
        None,
        max_length=50,
        description="Sistema de origen de los datos",
        examples=["mysql_legacy"]
    )
    id_origen: Optional[int] = Field(
        None,
        description="ID en el sistema de origen",
        examples=[123]
    )
    creado_por: Optional[str] = Field(
        None,
        max_length=50,
        description="Usuario que creó el registro",
        examples=["admin"]
    )
    migrado_en: Optional[datetime] = Field(
        None,
        description="Fecha y hora de migración",
        examples=["2024-01-15T10:30:00"]
    )
    version_migracion: Optional[str] = Field(
        None,
        max_length=20,
        description="Versión del proceso de migración",
        examples=["1.0"]
    )
    expediente_duplicado: bool = Field(
        default=False,
        description="Indica si el expediente es duplicado",
        examples=[False]
    )
    notas: Optional[str] = Field(
        None,
        max_length=500,
        description="Notas adicionales del sistema",
        examples=["Migrado desde MySQL"]
    )


# ═══════════════════════════════════════════════════════════
# SCHEMAS PRINCIPALES
# ═══════════════════════════════════════════════════════════

class PacienteBase(BaseModel):
    """Schema base de Paciente (campos comunes)"""
    
    expediente: Optional[str] = Field(
        None,
        max_length=20,
        description="Número de expediente único",
        examples=["12345"]
    )
    cui: Optional[int] = Field(
        None,
        description="CUI/DPI guatemalteco (13 dígitos)",
        examples=[1234567890123]
    )
    pasaporte: Optional[str] = Field(
        None,
        max_length=50,
        description="Número de pasaporte",
        examples=["GT123456"]
    )
    nombre: NombreSchema = Field(
        ...,
        description="Nombre completo del paciente"
    )
    sexo: SexoEnum = Field(
        ...,
        description="Sexo del paciente"
    )
    fecha_nacimiento: Optional[date] = Field(
        None,
        description="Fecha de nacimiento",
        examples=["1990-01-15"]
    )
    contacto: Optional[ContactoSchema] = Field(
        None,
        description="Información de contacto"
    )
    referencias: Optional[ReferenciasSchema] = Field(
        None,
        description="Referencias familiares"
    )
    datos_extra: Optional[DatosExtraSchema] = Field(
        None,
        description="Datos adicionales del paciente"
    )
    estado: EstadoEnum = Field(
        default=EstadoEnum.VIVO,
        description="Estado del paciente"
    )
    
    @field_validator('cui')
    @classmethod
    def validar_cui(cls, v: Optional[int]) -> Optional[int]:
        """Valida formato de CUI"""
        if v is None:
            return v
        
        cui_str = str(v)
        if len(cui_str) != 13:
            raise ValueError('CUI debe tener 13 dígitos')
        
        if not cui_str.isdigit():
            raise ValueError('CUI debe contener solo números')
        
        return v
    
    @field_validator('fecha_nacimiento')
    @classmethod
    def validar_fecha_nacimiento(cls, v: Optional[date]) -> Optional[date]:
        """Valida que la fecha de nacimiento no sea futura"""
        if v is None:
            return v
        
        from datetime import date as date_class
        if v > date_class.today():
            raise ValueError('Fecha de nacimiento no puede ser futura')
        
        # Validar edad máxima razonable (150 años)
        edad_maxima = 150
        fecha_minima = date_class(
            date_class.today().year - edad_maxima,
            date_class.today().month,
            date_class.today().day
        )
        
        if v < fecha_minima:
            raise ValueError(f'Fecha de nacimiento muy antigua (máx {edad_maxima} años)')
        
        return v
    
    @model_validator(mode='after')
    def validar_identificadores(self):
        """Valida que exista al menos un identificador"""
        if not (self.expediente or self.cui or self.pasaporte):
            raise ValueError('Debe proporcionar al menos un identificador (expediente, CUI o pasaporte)')
        return self
    
    @model_validator(mode='after')
    def validar_defuncion(self):
        """Valida coherencia de datos de defunción"""
        if self.estado == EstadoEnum.FALLECIDO:
            # Si está fallecido, debe tener datos de defunción
            if not (self.datos_extra and self.datos_extra.defuncion):
                raise ValueError('Paciente fallecido debe tener datos de defunción')
        else:
            # Si está vivo, no debe tener datos de defunción
            if self.datos_extra and self.datos_extra.defuncion:
                raise ValueError('Paciente vivo no puede tener datos de defunción')
        
        return self


class PacienteCreate(PacienteBase):
    """Schema para crear un paciente"""
    
    metadatos: Optional[MetadatosSchema] = Field(
        None,
        description="Metadatos del sistema (generalmente automático)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "expediente": "12345",
                "cui": 1234567890123,
                "pasaporte": None,
                "nombre": {
                    "primer_nombre": "Juan",
                    "segundo_nombre": "Carlos",
                    "primer_apellido": "Pérez",
                    "segundo_apellido": "García"
                },
                "sexo": "M",
                "fecha_nacimiento": "1990-01-15",
                "contacto": {
                    "telefono_principal": "12345678",
                    "email": "juan.perez@ejemplo.com",
                    "direccion": {
                        "linea1": "5ta Avenida 10-50, Zona 1",
                        "municipio_id": 1,
                        "departamento_id": 1
                    }
                },
                "referencias": {
                    "padre": "Pedro Pérez",
                    "madre": "Ana García"
                },
                "estado": "V"
            }
        }
    )


class PacienteUpdate(BaseModel):
    """Schema para actualizar un paciente (todos los campos opcionales)"""
    
    expediente: Optional[str] = Field(None, max_length=20)
    cui: Optional[int] = None
    pasaporte: Optional[str] = Field(None, max_length=50)
    nombre: Optional[NombreSchema] = None
    sexo: Optional[SexoEnum] = None
    fecha_nacimiento: Optional[date] = None
    contacto: Optional[ContactoSchema] = None
    referencias: Optional[ReferenciasSchema] = None
    datos_extra: Optional[DatosExtraSchema] = None
    estado: Optional[EstadoEnum] = None
    
    @field_validator('cui')
    @classmethod
    def validar_cui(cls, v: Optional[int]) -> Optional[int]:
        """Valida formato de CUI si se proporciona"""
        if v is None:
            return v
        
        cui_str = str(v)
        if len(cui_str) != 13:
            raise ValueError('CUI debe tener 13 dígitos')
        
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "contacto": {
                    "telefono_principal": "87654321",
                    "email": "nuevo.email@ejemplo.com"
                },
                "estado": "V"
            }
        }
    )


class PacienteResponse(PacienteBase):
    """Schema para respuesta de API (incluye campos del sistema)"""
    
    id: int = Field(..., description="ID único del paciente")
    metadatos: Optional[MetadatosSchema] = None
    creado_en: datetime = Field(..., description="Fecha de creación")
    actualizado_en: datetime = Field(..., description="Fecha de última actualización")
    
    # Campos calculados
    nombre_completo: Optional[str] = Field(None, description="Nombre completo formateado")
    edad: Optional[int] = Field(None, description="Edad calculada en años")
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "expediente": "12345",
                "cui": 1234567890123,
                "nombre": {
                    "primer_nombre": "Juan",
                    "primer_apellido": "Pérez"
                },
                "sexo": "M",
                "fecha_nacimiento": "1990-01-15",
                "estado": "V",
                "creado_en": "2024-01-15T10:30:00",
                "actualizado_en": "2024-01-15T10:30:00",
                "nombre_completo": "Juan Pérez",
                "edad": 34
            }
        }
    )


class PacienteListResponse(BaseModel):
    """Schema para lista de pacientes con paginación"""
    
    total: int = Field(..., description="Total de registros")
    page: int = Field(..., description="Página actual")
    page_size: int = Field(..., description="Tamaño de página")
    total_pages: int = Field(..., description="Total de páginas")
    items: List[PacienteResponse] = Field(..., description="Lista de pacientes")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 100,
                "page": 1,
                "page_size": 10,
                "total_pages": 10,
                "items": []
            }
        }
    )


# ═══════════════════════════════════════════════════════════
# SCHEMAS DE BÚSQUEDA
# ═══════════════════════════════════════════════════════════

class PacienteSearchParams(BaseModel):
    """Parámetros de búsqueda de pacientes"""
    
    expediente: Optional[str] = Field(None, description="Buscar por expediente")
    cui: Optional[int] = Field(None, description="Buscar por CUI")
    pasaporte: Optional[str] = Field(None, description="Buscar por pasaporte")
    nombre: Optional[str] = Field(None, description="Buscar en nombre (texto)")
    apellido: Optional[str] = Field(None, description="Buscar en apellido (texto)")
    sexo: Optional[SexoEnum] = Field(None, description="Filtrar por sexo")
    estado: Optional[EstadoEnum] = Field(None, description="Filtrar por estado")
    fecha_nacimiento_desde: Optional[date] = Field(None, description="Fecha nacimiento desde")
    fecha_nacimiento_hasta: Optional[date] = Field(None, description="Fecha nacimiento hasta")
    
    # Paginación
    page: int = Field(default=1, ge=1, description="Número de página")
    page_size: int = Field(default=10, ge=1, le=100, description="Tamaño de página")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "nombre": "Juan",
                "sexo": "M",
                "estado": "V",
                "page": 1,
                "page_size": 10
            }
        }
    )


# ═══════════════════════════════════════════════════════════
# SCHEMAS DE MIGRACIÓN
# ═══════════════════════════════════════════════════════════

class MigracionStats(BaseModel):
    """Estadísticas de migración"""
    
    total_procesados: int = Field(..., description="Total de registros procesados")
    total_exitosos: int = Field(..., description="Total de registros migrados exitosamente")
    total_errores: int = Field(..., description="Total de errores")
    total_advertencias: int = Field(..., description="Total de advertencias")
    expedientes_duplicados: int = Field(..., description="Total de expedientes duplicados")
    cui_invalidos: int = Field(..., description="Total de CUI inválidos")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_procesados": 1000,
                "total_exitosos": 950,
                "total_errores": 30,
                "total_advertencias": 20,
                "expedientes_duplicados": 15,
                "cui_invalidos": 10
            }
        }
    )


class MigracionResponse(BaseModel):
    """Respuesta del proceso de migración"""
    
    mensaje: str = Field(..., description="Mensaje del resultado")
    stats: MigracionStats = Field(..., description="Estadísticas de la migración")
    errores: List[Dict[str, Any]] = Field(default=[], description="Lista de errores detallados")
    advertencias: List[Dict[str, Any]] = Field(default=[], description="Lista de advertencias")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mensaje": "Migración completada",
                "stats": {
                    "total_procesados": 1000,
                    "total_exitosos": 950,
                    "total_errores": 30,
                    "total_advertencias": 20,
                    "expedientes_duplicados": 15,
                    "cui_invalidos": 10
                },
                "errores": [],
                "advertencias": []
            }
        }
    )