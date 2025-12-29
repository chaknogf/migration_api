# app/crud/paciente.py

"""
Operaciones CRUD específicas para Pacientes
Extiende la clase base con métodos especializados
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, cast, String
from datetime import date

from app.crud.base import CRUDBase
from app.models.postgres.paciente import Paciente
from app.schemas.paciente import (
    PacienteCreate,
    PacienteUpdate,
    PacienteSearchParams,
    EstadoEnum,
    SexoEnum
)


class CRUDPaciente(CRUDBase[Paciente, PacienteCreate, PacienteUpdate]):
    """
    Operaciones CRUD para el modelo Paciente
    Incluye búsquedas especializadas y validaciones
    """
    
    def __init__(self):
        super().__init__(Paciente)
    
    # ═══════════════════════════════════════════════════════════
    # BÚSQUEDAS POR IDENTIFICADORES
    # ═══════════════════════════════════════════════════════════
    
    def get_by_expediente(
        self,
        db: Session,
        expediente: str
    ) -> Optional[Paciente]:
        """
        Busca un paciente por número de expediente
        
        Args:
            db: Sesión de base de datos
            expediente: Número de expediente
            
        Returns:
            Paciente encontrado o None
        """
        return db.query(Paciente).filter(
            Paciente.expediente == expediente
        ).first()
    
    def get_by_cui(
        self,
        db: Session,
        cui: int
    ) -> Optional[Paciente]:
        """
        Busca un paciente por CUI/DPI
        
        Args:
            db: Sesión de base de datos
            cui: Número de CUI
            
        Returns:
            Paciente encontrado o None
        """
        return db.query(Paciente).filter(
            Paciente.cui == cui
        ).first()
    
    def get_by_pasaporte(
        self,
        db: Session,
        pasaporte: str
    ) -> Optional[Paciente]:
        """
        Busca un paciente por número de pasaporte
        
        Args:
            db: Sesión de base de datos
            pasaporte: Número de pasaporte
            
        Returns:
            Paciente encontrado o None
        """
        return db.query(Paciente).filter(
            Paciente.pasaporte == pasaporte
        ).first()
    
    def exists_by_identifier(
        self,
        db: Session,
        *,
        expediente: Optional[str] = None,
        cui: Optional[int] = None,
        pasaporte: Optional[str] = None
    ) -> bool:
        """
        Verifica si ya existe un paciente con alguno de los identificadores
        
        Args:
            db: Sesión de base de datos
            expediente: Número de expediente (opcional)
            cui: CUI/DPI (opcional)
            pasaporte: Pasaporte (opcional)
            
        Returns:
            True si existe, False si no
        """
        conditions = []
        
        if expediente:
            conditions.append(Paciente.expediente == expediente)
        if cui:
            conditions.append(Paciente.cui == cui)
        if pasaporte:
            conditions.append(Paciente.pasaporte == pasaporte)
        
        if not conditions:
            return False
        
        return db.query(
            db.query(Paciente).filter(or_(*conditions)).exists()
        ).scalar()
    
    # ═══════════════════════════════════════════════════════════
    # BÚSQUEDA AVANZADA
    # ═══════════════════════════════════════════════════════════
    
    def search(
        self,
        db: Session,
        *,
        params: PacienteSearchParams
    ) -> tuple[List[Paciente], int]:
        """
        Búsqueda avanzada de pacientes con filtros múltiples
        
        Args:
            db: Sesión de base de datos
            params: Parámetros de búsqueda
            
        Returns:
            Tupla con (lista de pacientes, total de resultados)
        """
        query = db.query(Paciente)
        
        # Filtro por expediente
        if params.expediente:
            query = query.filter(
                Paciente.expediente.ilike(f"%{params.expediente}%")
            )
        
        # Filtro por CUI
        if params.cui:
            query = query.filter(Paciente.cui == params.cui)
        
        # Filtro por pasaporte
        if params.pasaporte:
            query = query.filter(
                Paciente.pasaporte.ilike(f"%{params.pasaporte}%")
            )
        
        # Filtro por nombre (búsqueda en JSONB)
        if params.nombre:
            query = query.filter(
                or_(
                    Paciente.nombre['primer_nombre'].astext.ilike(f"%{params.nombre}%"),
                    Paciente.nombre['segundo_nombre'].astext.ilike(f"%{params.nombre}%"),
                    Paciente.nombre['otros_nombres'].astext.ilike(f"%{params.nombre}%")
                )
            )
        
        # Filtro por apellido (búsqueda en JSONB)
        if params.apellido:
            query = query.filter(
                or_(
                    Paciente.nombre['primer_apellido'].astext.ilike(f"%{params.apellido}%"),
                    Paciente.nombre['segundo_apellido'].astext.ilike(f"%{params.apellido}%")
                )
            )
        
        # Filtro por sexo
        if params.sexo:
            query = query.filter(Paciente.sexo == params.sexo.value)
        
        # Filtro por estado
        if params.estado:
            query = query.filter(Paciente.estado == params.estado.value)
        
        # Filtro por rango de fechas de nacimiento
        if params.fecha_nacimiento_desde:
            query = query.filter(
                Paciente.fecha_nacimiento >= params.fecha_nacimiento_desde
            )
        
        if params.fecha_nacimiento_hasta:
            query = query.filter(
                Paciente.fecha_nacimiento <= params.fecha_nacimiento_hasta
            )
        
        # Contar total antes de paginar
        total = query.count()
        
        # Paginación
        skip = (params.page - 1) * params.page_size
        pacientes = query.offset(skip).limit(params.page_size).all()
        
        return pacientes, total
    
    def search_by_nombre_completo(
        self,
        db: Session,
        texto: str,
        limit: int = 20
    ) -> List[Paciente]:
        """
        Búsqueda de texto libre en nombre completo
        Útil para autocompletado
        
        Args:
            db: Sesión de base de datos
            texto: Texto a buscar
            limit: Máximo de resultados
            
        Returns:
            Lista de pacientes que coinciden
        """
        # Buscar en todos los campos de nombre
        query = db.query(Paciente).filter(
            or_(
                Paciente.nombre['primer_nombre'].astext.ilike(f"%{texto}%"),
                Paciente.nombre['segundo_nombre'].astext.ilike(f"%{texto}%"),
                Paciente.nombre['primer_apellido'].astext.ilike(f"%{texto}%"),
                Paciente.nombre['segundo_apellido'].astext.ilike(f"%{texto}%")
            )
        ).limit(limit)
        
        return query.all()
    
    # ═══════════════════════════════════════════════════════════
    # OPERACIONES ESPECIALIZADAS
    # ═══════════════════════════════════════════════════════════
    
    def get_pacientes_fallecidos(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[Paciente]:
        """
        Obtiene todos los pacientes fallecidos
        
        Args:
            db: Sesión de base de datos
            skip: Registros a saltar
            limit: Máximo de registros
            
        Returns:
            Lista de pacientes fallecidos
        """
        return db.query(Paciente).filter(
            Paciente.estado == EstadoEnum.FALLECIDO.value
        ).offset(skip).limit(limit).all()
    
    def get_pacientes_por_sexo(
        self,
        db: Session,
        sexo: SexoEnum,
        skip: int = 0,
        limit: int = 100
    ) -> List[Paciente]:
        """
        Obtiene pacientes filtrados por sexo
        
        Args:
            db: Sesión de base de datos
            sexo: Sexo a filtrar
            skip: Registros a saltar
            limit: Máximo de registros
            
        Returns:
            Lista de pacientes
        """
        return db.query(Paciente).filter(
            Paciente.sexo == sexo.value
        ).offset(skip).limit(limit).all()
    
    def get_pacientes_por_rango_edad(
        self,
        db: Session,
        edad_min: int,
        edad_max: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[Paciente]:
        """
        Obtiene pacientes en un rango de edad
        
        Args:
            db: Sesión de base de datos
            edad_min: Edad mínima
            edad_max: Edad máxima
            skip: Registros a saltar
            limit: Máximo de registros
            
        Returns:
            Lista de pacientes
        """
        from datetime import date
        hoy = date.today()
        
        # Calcular fechas de nacimiento correspondientes
        fecha_max = date(hoy.year - edad_min, hoy.month, hoy.day)
        fecha_min = date(hoy.year - edad_max - 1, hoy.month, hoy.day)
        
        return db.query(Paciente).filter(
            and_(
                Paciente.fecha_nacimiento >= fecha_min,
                Paciente.fecha_nacimiento <= fecha_max
            )
        ).offset(skip).limit(limit).all()
    
    def get_menores_de_edad(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[Paciente]:
        """
        Obtiene pacientes menores de 18 años
        
        Args:
            db: Sesión de base de datos
            skip: Registros a saltar
            limit: Máximo de registros
            
        Returns:
            Lista de pacientes menores de edad
        """
        return self.get_pacientes_por_rango_edad(db, 0, 17, skip, limit)
    
    def get_expedientes_duplicados(
        self,
        db: Session
    ) -> List[Paciente]:
        """
        Obtiene pacientes con expedientes marcados como duplicados
        
        Args:
            db: Sesión de base de datos
            
        Returns:
            Lista de pacientes con expedientes duplicados
        """
        return db.query(Paciente).filter(
            Paciente.metadatos['expediente_duplicado'].astext == 'true'
        ).all()
    
    def get_pacientes_sin_cui(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[Paciente]:
        """
        Obtiene pacientes sin CUI registrado
        
        Args:
            db: Sesión de base de datos
            skip: Registros a saltar
            limit: Máximo de registros
            
        Returns:
            Lista de pacientes sin CUI
        """
        return db.query(Paciente).filter(
            Paciente.cui.is_(None)
        ).offset(skip).limit(limit).all()
    
    def get_pacientes_migrados(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[Paciente]:
        """
        Obtiene pacientes que fueron migrados desde MySQL
        
        Args:
            db: Sesión de base de datos
            skip: Registros a saltar
            limit: Máximo de registros
            
        Returns:
            Lista de pacientes migrados
        """
        return db.query(Paciente).filter(
            Paciente.metadatos['sistema_origen'].astext == 'mysql_legacy'
        ).offset(skip).limit(limit).all()
    
    # ═══════════════════════════════════════════════════════════
    # ESTADÍSTICAS
    # ═══════════════════════════════════════════════════════════
    
    def get_estadisticas(self, db: Session) -> Dict[str, Any]:
        """
        Obtiene estadísticas generales de pacientes
        
        Args:
            db: Sesión de base de datos
            
        Returns:
            Diccionario con estadísticas
        """
        total = self.get_count(db)
        
        # Contar por sexo
        masculinos = db.query(func.count(Paciente.id)).filter(
            Paciente.sexo == SexoEnum.MASCULINO.value
        ).scalar()
        
        femeninos = db.query(func.count(Paciente.id)).filter(
            Paciente.sexo == SexoEnum.FEMENINO.value
        ).scalar()
        
        # Contar fallecidos
        fallecidos = db.query(func.count(Paciente.id)).filter(
            Paciente.estado == EstadoEnum.FALLECIDO.value
        ).scalar()
        
        # Contar sin CUI
        sin_cui = db.query(func.count(Paciente.id)).filter(
            Paciente.cui.is_(None)
        ).scalar()
        
        # Contar duplicados
        duplicados = db.query(func.count(Paciente.id)).filter(
            Paciente.metadatos['expediente_duplicado'].astext == 'true'
        ).scalar()
        
        # Contar migrados
        migrados = db.query(func.count(Paciente.id)).filter(
            Paciente.metadatos['sistema_origen'].astext == 'mysql_legacy'
        ).scalar()
        
        return {
            "total_pacientes": total,
            "por_sexo": {
                "masculino": masculinos,
                "femenino": femeninos,
                "no_especificado": total - masculinos - femeninos
            },
            "por_estado": {
                "vivos": total - fallecidos,
                "fallecidos": fallecidos
            },
            "calidad_datos": {
                "sin_cui": sin_cui,
                "expedientes_duplicados": duplicados
            },
            "migracion": {
                "registros_migrados": migrados,
                "registros_nuevos": total - migrados
            }
        }
    
    # ═══════════════════════════════════════════════════════════
    # VALIDACIONES
    # ═══════════════════════════════════════════════════════════
    
    def validate_unique_identifiers(
        self,
        db: Session,
        *,
        expediente: Optional[str] = None,
        cui: Optional[int] = None,
        pasaporte: Optional[str] = None,
        exclude_id: Optional[int] = None
    ) -> Dict[str, bool]:
        """
        Valida que los identificadores sean únicos
        
        Args:
            db: Sesión de base de datos
            expediente: Expediente a validar
            cui: CUI a validar
            pasaporte: Pasaporte a validar
            exclude_id: ID a excluir de la validación (para updates)
            
        Returns:
            Diccionario con resultados de validación
        """
        results = {
            "expediente_disponible": True,
            "cui_disponible": True,
            "pasaporte_disponible": True
        }
        
        # Validar expediente
        if expediente:
            query = db.query(Paciente).filter(Paciente.expediente == expediente)
            if exclude_id:
                query = query.filter(Paciente.id != exclude_id)
            results["expediente_disponible"] = query.first() is None
        
        # Validar CUI
        if cui:
            query = db.query(Paciente).filter(Paciente.cui == cui)
            if exclude_id:
                query = query.filter(Paciente.id != exclude_id)
            results["cui_disponible"] = query.first() is None
        
        # Validar pasaporte
        if pasaporte:
            query = db.query(Paciente).filter(Paciente.pasaporte == pasaporte)
            if exclude_id:
                query = query.filter(Paciente.id != exclude_id)
            results["pasaporte_disponible"] = query.first() is None
        
        return results