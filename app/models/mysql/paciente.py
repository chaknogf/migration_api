# app/models/mysql/paciente.py
"""
Modelo SQLAlchemy para tabla pacientes en MySQL
LEGACY DATABASE - SOLO LECTURA
"""

from sqlalchemy import (
    Column, Integer, String, BigInteger, Date, Time, 
    TIMESTAMP, text
)
from sqlalchemy.orm import declarative_base
from datetime import datetime, date, time

BaseMysql = declarative_base()


class PacienteMysql(BaseMysql):
    """
    Modelo de Paciente para MySQL (Legacy)
    
    ⚠️ IMPORTANTE: Este modelo es SOLO LECTURA
    Se usa exclusivamente para migración de datos
    """
    
    __tablename__ = "pacientes"
    
    # ═══════════════════════════════════════════════════════════
    # CAMPOS DE MYSQL (estructura original)
    # ═══════════════════════════════════════════════════════════
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identificadores
    expediente = Column(Integer, unique=True, nullable=True)
    dpi = Column(BigInteger, nullable=True, comment="CUI/DPI guatemalteco")
    pasaporte = Column(String(50), nullable=True)
    
    # Nombre (separado en columnas)
    nombre = Column(String(50), nullable=True)
    apellido = Column(String(50), nullable=True)
    
    # Datos básicos
    sexo = Column(String(2), nullable=True)
    nacimiento = Column(Date, nullable=True, comment="Fecha de nacimiento")
    
    # Datos demográficos (IDs a catálogos)
    nacionalidad = Column(Integer, nullable=True)
    depto_nac = Column(Integer, nullable=True, comment="Departamento de nacimiento")
    lugar_nacimiento = Column(Integer, nullable=True)
    estado_civil = Column(Integer, nullable=True)
    educacion = Column(Integer, nullable=True)
    pueblo = Column(Integer, nullable=True, comment="Pueblo/Etnia")
    idioma = Column(Integer, nullable=True)
    
    # Datos socioeconómicos
    ocupacion = Column(String(50), nullable=True)
    
    # Contacto
    direccion = Column(String(100), nullable=True)
    municipio = Column(Integer, nullable=True)
    depto = Column(Integer, nullable=True, comment="Departamento de residencia")
    telefono = Column(String(50), nullable=True)
    email = Column(String(100), nullable=True)
    
    # Referencias familiares
    padre = Column(String(50), nullable=True)
    madre = Column(String(50), nullable=True)
    exp_madre = Column(Integer, nullable=True, comment="Expediente de la madre")
    
    responsable = Column(String(50), nullable=True)
    parentesco = Column(Integer, nullable=True)
    dpi_responsable = Column(BigInteger, nullable=True)
    telefono_responsable = Column(Integer, nullable=True)
    exp_ref = Column(Integer, nullable=True, comment="Expediente de referencia")
    
    conyugue = Column(String(100), nullable=True)
    gemelo = Column(String(2), nullable=True, comment="SI/NO")
    
    # Estado y defunción
    estado = Column(String(2), nullable=True)
    fechaDefuncion = Column(String(10), nullable=True, comment="VARCHAR fecha defunción")
    hora_defuncion = Column(Time, nullable=True)
    
    # Sistema
    created_by = Column(String(8), nullable=True)
    created_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text('CURRENT_TIMESTAMP')
    )
    update_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')
    )
    
    # ═══════════════════════════════════════════════════════════
    # MÉTODOS DE UTILIDAD
    # ═══════════════════════════════════════════════════════════
    
    def __repr__(self) -> str:
        """Representación legible del paciente MySQL"""
        return (
            f"<PacienteMysql(id={self.id}, "
            f"expediente={self.expediente}, "
            f"nombre='{self.nombre} {self.apellido}')>"
        )
    
    def get_nombre_completo(self) -> str:
        """Obtiene el nombre completo concatenado"""
        partes = []
        if self.nombre:
            partes.append(self.nombre)
        if self.apellido:
            partes.append(self.apellido)
        return " ".join(partes) if partes else "Sin nombre"
    
    def tiene_cui_valido(self) -> bool:
        """Verifica si el DPI/CUI tiene formato válido (13 dígitos)"""
        if not self.dpi:
            return False
        return len(str(self.dpi)) == 13
    
    def tiene_expediente(self) -> bool:
        """Verifica si tiene expediente válido"""
        return self.expediente is not None and self.expediente > 0
    
    def esta_fallecido(self) -> bool:
        """Verifica si está marcado como fallecido"""
        if not self.estado:
            return False
        return self.estado.upper() in ('F', 'FALLECIDO')
    
    def tiene_datos_defuncion(self) -> bool:
        """Verifica si tiene datos de defunción"""
        return bool(self.fechaDefuncion)
    
    def es_gemelo(self) -> bool:
        """Verifica si está marcado como gemelo"""
        if not self.gemelo:
            return False
        return self.gemelo.upper() in ('SI', 'S', 'YES', 'Y', '1')
    
    def to_dict(self) -> dict:
        """
        Convierte el modelo MySQL a diccionario
        Útil para debugging y logging
        
        Returns:
            Diccionario con todos los campos
        """
        return {
            "id": self.id,
            "expediente": self.expediente,
            "dpi": self.dpi,
            "pasaporte": self.pasaporte,
            "nombre": self.nombre,
            "apellido": self.apellido,
            "sexo": self.sexo,
            "nacimiento": self.nacimiento.isoformat() if self.nacimiento else None,
            "nacionalidad": self.nacionalidad,
            "depto_nac": self.depto_nac,
            "lugar_nacimiento": self.lugar_nacimiento,
            "estado_civil": self.estado_civil,
            "educacion": self.educacion,
            "pueblo": self.pueblo,
            "idioma": self.idioma,
            "ocupacion": self.ocupacion,
            "direccion": self.direccion,
            "municipio": self.municipio,
            "depto": self.depto,
            "telefono": self.telefono,
            "email": self.email,
            "padre": self.padre,
            "madre": self.madre,
            "exp_madre": self.exp_madre,
            "responsable": self.responsable,
            "parentesco": self.parentesco,
            "dpi_responsable": self.dpi_responsable,
            "telefono_responsable": self.telefono_responsable,
            "exp_ref": self.exp_ref,
            "conyugue": self.conyugue,
            "gemelo": self.gemelo,
            "estado": self.estado,
            "fechaDefuncion": self.fechaDefuncion,
            "hora_defuncion": str(self.hora_defuncion) if self.hora_defuncion else None,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "update_at": self.update_at.isoformat() if self.update_at else None,
            # Campos calculados
            "nombre_completo": self.get_nombre_completo(),
            "cui_valido": self.tiene_cui_valido(),
            "fallecido": self.esta_fallecido(),
            "es_gemelo_flag": self.es_gemelo()
        }