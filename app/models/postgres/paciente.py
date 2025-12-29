# app/models/postgres/paciente.py
"""
Modelo SQLAlchemy para tabla pacientes en PostgreSQL
Base de datos principal del sistema
"""

from sqlalchemy import (
    Column, Integer, String, BigInteger, CHAR, Date, 
    CheckConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Paciente(Base):
    """
    Modelo de Paciente para PostgreSQL
    
    Representa la estructura normalizada con JSONB para datos complejos
    """
    
    __tablename__ = "pacientes"
    
    # ═══════════════════════════════════════════════════════════
    # CAMPOS PRINCIPALES
    # ═══════════════════════════════════════════════════════════
    
    id = Column(
        Integer, 
        primary_key=True, 
        autoincrement=True,
        comment="ID único del paciente"
    )
    
    # 🔐 Identificadores principales
    expediente = Column(
        String(20),
        unique=True,
        nullable=True,
        index=True,
        comment="Número de expediente único (puede ser DUP-{id} para duplicados)"
    )
    
    cui = Column(
        BigInteger,
        unique=True,
        nullable=True,
        index=True,
        comment="CUI/DPI guatemalteco (13 dígitos)"
    )
    
    pasaporte = Column(
        String(50),
        unique=True,
        nullable=True,
        comment="Número de pasaporte"
    )
    
    # 🧍‍♂️ Identificación personal
    nombre = Column(
        JSONB,
        nullable=False,
        comment="""
        Estructura:
        {
            "primer_nombre": "Juan",
            "segundo_nombre": "Carlos",
            "otros_nombres": null,
            "primer_apellido": "Pérez",
            "segundo_apellido": "García",
            "apellido_casada": null
        }
        """
    )
    
    sexo = Column(
        CHAR(2),
        CheckConstraint("sexo IN ('M', 'F', 'NF')", name='check_sexo'),
        nullable=True,
        index=True,
        comment="M=Masculino, F=Femenino, NF=No especificado"
    )
    
    fecha_nacimiento = Column(
        Date,
        nullable=True,
        index=True,
        comment="Fecha de nacimiento del paciente"
    )
    
    # ☎️ Contacto
    contacto = Column(
        JSONB,
        nullable=True,
        comment="""
        Estructura:
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
    )
    
    # 👪 Referencias familiares
    referencias = Column(
        JSONB,
        nullable=True,
        comment="""
        Estructura:
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
    )
    
    # 🌍 Otros datos históricos y clínicos
    datos_extra = Column(
        JSONB,
        nullable=True,
        comment="""
        Estructura:
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
    )
    
    # ⚙️ Estado del paciente
    estado = Column(
        CHAR(1),
        CheckConstraint("estado IN ('V', 'F')", name='check_estado'),
        nullable=False,
        default='V',
        index=True,
        comment="V=Vivo, F=Fallecido"
    )
    
    # 🧾 Metadatos del sistema
    metadatos = Column(
        JSONB,
        nullable=True,
        comment="""
        Estructura:
        {
            "sistema_origen": "mysql_legacy",
            "id_origen": 123,
            "creado_por": "admin",
            "migrado_en": "2024-01-15T10:30:00",
            "version_migracion": "1.0",
            "expediente_duplicado": false,
            "notas": "Observaciones adicionales"
        }
        """
    )
    
    # ⏱️ Tiempos del sistema
    creado_en = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text('NOW()'),
        comment="Fecha y hora de creación del registro"
    )
    
    actualizado_en = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text('NOW()'),
        onupdate=datetime.now,
        comment="Fecha y hora de última actualización"
    )
    
    # ═══════════════════════════════════════════════════════════
    # ÍNDICES
    # ═══════════════════════════════════════════════════════════
    
    __table_args__ = (
        # Índices GIN para JSONB (búsquedas eficientes en JSON)
        Index('idx_pacientes_nombre_gin', 'nombre', postgresql_using='gin'),
        Index('idx_pacientes_contacto_gin', 'contacto', postgresql_using='gin'),
        Index('idx_pacientes_referencias_gin', 'referencias', postgresql_using='gin'),
        Index('idx_pacientes_datos_extra_gin', 'datos_extra', postgresql_using='gin'),
        Index('idx_pacientes_metadatos_gin', 'metadatos', postgresql_using='gin'),
        
        # Índices B-Tree ya definidos en las columnas con index=True
        # - expediente (UNIQUE + INDEX)
        # - cui (UNIQUE + INDEX)
        # - sexo (INDEX)
        # - fecha_nacimiento (INDEX)
        # - estado (INDEX)
    )
    
    # ═══════════════════════════════════════════════════════════
    # MÉTODOS DE UTILIDAD
    # ═══════════════════════════════════════════════════════════
    
    def __repr__(self) -> str:
        """Representación legible del paciente"""
        nombre_completo = self.get_nombre_completo()
        return f"<Paciente(id={self.id}, expediente='{self.expediente}', nombre='{nombre_completo}')>"
    
    def get_nombre_completo(self) -> str:
        """
        Obtiene el nombre completo del paciente desde el JSONB
        
        Returns:
            Nombre completo formateado
        """
        if not self.nombre:
            return "Sin nombre"
        
        partes = []
        
        # Nombres
        if self.nombre.get("primer_nombre"):
            partes.append(self.nombre["primer_nombre"])
        if self.nombre.get("segundo_nombre"):
            partes.append(self.nombre["segundo_nombre"])
        if self.nombre.get("otros_nombres"):
            partes.append(self.nombre["otros_nombres"])
        
        # Apellidos
        if self.nombre.get("primer_apellido"):
            partes.append(self.nombre["primer_apellido"])
        if self.nombre.get("segundo_apellido"):
            partes.append(self.nombre["segundo_apellido"])
        
        # Apellido de casada
        if self.nombre.get("apellido_casada"):
            partes.append(f"de {self.nombre['apellido_casada']}")
        
        return " ".join(partes) if partes else "Sin nombre"
    
    def get_edad(self) -> int | None:
        """
        Calcula la edad del paciente
        
        Returns:
            Edad en años o None si no tiene fecha de nacimiento
        """
        if not self.fecha_nacimiento:
            return None
        
        from datetime import date
        hoy = date.today()
        edad = hoy.year - self.fecha_nacimiento.year
        
        # Ajustar si no ha cumplido años este año
        if (hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day):
            edad -= 1
        
        return edad
    
    def es_mayor_de_edad(self) -> bool | None:
        """
        Determina si el paciente es mayor de 18 años
        
        Returns:
            True si es mayor de edad, False si es menor, None si no tiene fecha
        """
        edad = self.get_edad()
        if edad is None:
            return None
        return edad >= 18
    
    def esta_fallecido(self) -> bool:
        """Verifica si el paciente está fallecido"""
        return self.estado == 'F'
    
    def get_telefono_principal(self) -> str | None:
        """Obtiene el teléfono principal del contacto"""
        if not self.contacto:
            return None
        return self.contacto.get("telefono_principal")
    
    def get_email(self) -> str | None:
        """Obtiene el email del contacto"""
        if not self.contacto:
            return None
        return self.contacto.get("email")
    
    def get_direccion(self) -> str | None:
        """Obtiene la dirección completa"""
        if not self.contacto or not self.contacto.get("direccion"):
            return None
        return self.contacto["direccion"].get("linea1")
    
    def es_expediente_duplicado(self) -> bool:
        """Verifica si el expediente es marcado como duplicado"""
        if not self.metadatos:
            return False
        return self.metadatos.get("expediente_duplicado", False)
    
    def get_id_origen(self) -> int | None:
        """Obtiene el ID original de MySQL"""
        if not self.metadatos:
            return None
        return self.metadatos.get("id_origen")
    
    def to_dict(self) -> dict:
        """
        Convierte el modelo a diccionario
        
        Returns:
            Diccionario con todos los campos
        """
        return {
            "id": self.id,
            "expediente": self.expediente,
            "cui": self.cui,
            "pasaporte": self.pasaporte,
            "nombre": self.nombre,
            "sexo": self.sexo,
            "fecha_nacimiento": self.fecha_nacimiento.isoformat() if self.fecha_nacimiento else None,
            "contacto": self.contacto,
            "referencias": self.referencias,
            "datos_extra": self.datos_extra,
            "estado": self.estado,
            "metadatos": self.metadatos,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
            "actualizado_en": self.actualizado_en.isoformat() if self.actualizado_en else None,
            # Campos calculados
            "nombre_completo": self.get_nombre_completo(),
            "edad": self.get_edad(),
            "mayor_de_edad": self.es_mayor_de_edad(),
            "fallecido": self.esta_fallecido()
        }