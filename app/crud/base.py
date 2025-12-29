# CRUD genérico (opcional)
# app/crud/base.py

"""
Clase base genérica para operaciones CRUD
Implementa operaciones comunes que pueden ser reutilizadas
"""

from typing import Generic, TypeVar, Type, Optional, List, Any, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel

# Type variables para genericidad
ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Clase base CRUD con operaciones genéricas
    
    Args:
        model: Modelo SQLAlchemy
    """
    
    def __init__(self, model: Type[ModelType]):
        """
        CRUD base con métodos por defecto
        
        Args:
            model: Clase del modelo SQLAlchemy
        """
        self.model = model
    
    def get(self, db: Session, id: int) -> Optional[ModelType]:
        """
        Obtiene un registro por ID
        
        Args:
            db: Sesión de base de datos
            id: ID del registro
            
        Returns:
            Registro encontrado o None
        """
        return db.query(self.model).filter(self.model.id == id).first()
    
    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100
    ) -> List[ModelType]:
        """
        Obtiene múltiples registros con paginación
        
        Args:
            db: Sesión de base de datos
            skip: Registros a saltar (offset)
            limit: Máximo de registros a retornar
            
        Returns:
            Lista de registros
        """
        return db.query(self.model).offset(skip).limit(limit).all()
    
    def get_count(self, db: Session) -> int:
        """
        Obtiene el conteo total de registros
        
        Args:
            db: Sesión de base de datos
            
        Returns:
            Número total de registros
        """
        return db.query(func.count(self.model.id)).scalar()
    
    def create(self, db: Session, *, obj_in: CreateSchemaType) -> ModelType:
        """
        Crea un nuevo registro
        
        Args:
            db: Sesión de base de datos
            obj_in: Schema con datos para crear
            
        Returns:
            Registro creado
        """
        obj_in_data = obj_in.model_dump()
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self,
        db: Session,
        *,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | Dict[str, Any]
    ) -> ModelType:
        """
        Actualiza un registro existente
        
        Args:
            db: Sesión de base de datos
            db_obj: Objeto de base de datos a actualizar
            obj_in: Schema o dict con datos a actualizar
            
        Returns:
            Registro actualizado
        """
        obj_data = db_obj.__dict__.copy()
        
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
        
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, *, id: int) -> Optional[ModelType]:
        """
        Elimina un registro por ID
        
        Args:
            db: Sesión de base de datos
            id: ID del registro a eliminar
            
        Returns:
            Registro eliminado o None
        """
        obj = db.query(self.model).get(id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj
    
    def exists(self, db: Session, id: int) -> bool:
        """
        Verifica si un registro existe
        
        Args:
            db: Sesión de base de datos
            id: ID del registro
            
        Returns:
            True si existe, False si no
        """
        return db.query(
            db.query(self.model).filter(self.model.id == id).exists()
        ).scalar()
