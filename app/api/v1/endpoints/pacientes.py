# app/api/v1/endpoints/pacientes.py

"""
Endpoints CRUD para Pacientes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from app.api.deps import get_db, common_pagination_params
from app.crud.paciente import crud_paciente
from app.schemas.paciente import (
    PacienteCreate,
    PacienteUpdate,
    PacienteResponse,
    PacienteListResponse,
    PacienteSearchParams,
    SexoEnum,
    EstadoEnum
)
from app.services.validacion import ValidadorPaciente

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# ENDPOINTS CRUD BÁSICOS
# ═══════════════════════════════════════════════════════════

@router.post(
    "/",
    response_model=PacienteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear paciente",
    description="Crea un nuevo paciente en el sistema"
)
def create_paciente(
    *,
    db: Session = Depends(get_db),
    paciente_in: PacienteCreate
):
    """
    Crea un nuevo paciente
    
    - **expediente**: Número de expediente único
    - **cui**: CUI/DPI de 13 dígitos
    - **nombre**: Nombre completo estructurado en JSONB
    - **sexo**: M, F, o NF
    - **fecha_nacimiento**: Fecha de nacimiento
    """
    # Validar identificadores únicos
    if crud_paciente.exists_by_identifier(
        db,
        expediente=paciente_in.expediente,
        cui=paciente_in.cui,
        pasaporte=paciente_in.pasaporte
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un paciente con alguno de estos identificadores"
        )
    
    # Crear paciente
    paciente = crud_paciente.create(db, obj_in=paciente_in)
    
    # Agregar campos calculados
    response_data = PacienteResponse.model_validate(paciente)
    response_data.nombre_completo = paciente.get_nombre_completo()
    response_data.edad = paciente.get_edad()
    
    return response_data


@router.get(
    "/{paciente_id}",
    response_model=PacienteResponse,
    summary="Obtener paciente por ID",
    description="Obtiene un paciente específico por su ID"
)
def get_paciente(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene un paciente por ID
    
    - **paciente_id**: ID único del paciente
    """
    paciente = crud_paciente.get(db, id=paciente_id)
    
    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paciente con ID {paciente_id} no encontrado"
        )
    
    # Agregar campos calculados
    response_data = PacienteResponse.model_validate(paciente)
    response_data.nombre_completo = paciente.get_nombre_completo()
    response_data.edad = paciente.get_edad()
    
    return response_data


@router.put(
    "/{paciente_id}",
    response_model=PacienteResponse,
    summary="Actualizar paciente",
    description="Actualiza un paciente existente"
)
def update_paciente(
    *,
    db: Session = Depends(get_db),
    paciente_id: int,
    paciente_in: PacienteUpdate
):
    """
    Actualiza un paciente existente
    
    - **paciente_id**: ID del paciente a actualizar
    - Solo se actualizan los campos proporcionados
    """
    paciente = crud_paciente.get(db, id=paciente_id)
    
    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paciente con ID {paciente_id} no encontrado"
        )
    
    # Validar identificadores únicos si se están actualizando
    update_data = paciente_in.model_dump(exclude_unset=True)
    if any(key in update_data for key in ['expediente', 'cui', 'pasaporte']):
        validation = crud_paciente.validate_unique_identifiers(
            db,
            expediente=update_data.get('expediente'),
            cui=update_data.get('cui'),
            pasaporte=update_data.get('pasaporte'),
            exclude_id=paciente_id
        )
        
        if not all(validation.values()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Identificadores no disponibles: {validation}"
            )
    
    # Actualizar
    paciente = crud_paciente.update(db, db_obj=paciente, obj_in=paciente_in)
    
    # Agregar campos calculados
    response_data = PacienteResponse.model_validate(paciente)
    response_data.nombre_completo = paciente.get_nombre_completo()
    response_data.edad = paciente.get_edad()
    
    return response_data


@router.delete(
    "/{paciente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar paciente",
    description="Elimina un paciente del sistema"
)
def delete_paciente(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    """
    Elimina un paciente
    
    ⚠️ Esta acción no se puede deshacer
    
    - **paciente_id**: ID del paciente a eliminar
    """
    paciente = crud_paciente.get(db, id=paciente_id)
    
    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paciente con ID {paciente_id} no encontrado"
        )
    
    crud_paciente.delete(db, id=paciente_id)
    return None


# ═══════════════════════════════════════════════════════════
# BÚSQUEDA Y LISTADO
# ═══════════════════════════════════════════════════════════

@router.get(
    "/",
    response_model=PacienteListResponse,
    summary="Listar pacientes",
    description="Lista todos los pacientes con paginación"
)
def list_pacientes(
    db: Session = Depends(get_db),
    pagination: dict = Depends(common_pagination_params)
):
    """
    Lista todos los pacientes con paginación
    
    - **page**: Número de página (default: 1)
    - **page_size**: Tamaño de página (default: 10, max: 100)
    """
    pacientes = crud_paciente.get_multi(
        db,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )
    
    total = crud_paciente.get_count(db)
    total_pages = (total + pagination["page_size"] - 1) // pagination["page_size"]
    
    # Agregar campos calculados a cada paciente
    items = []
    for paciente in pacientes:
        response_data = PacienteResponse.model_validate(paciente)
        response_data.nombre_completo = paciente.get_nombre_completo()
        response_data.edad = paciente.get_edad()
        items.append(response_data)
    
    return PacienteListResponse(
        total=total,
        page=pagination["page"],
        page_size=pagination["page_size"],
        total_pages=total_pages,
        items=items
    )


@router.post(
    "/search",
    response_model=PacienteListResponse,
    summary="Búsqueda avanzada de pacientes",
    description="Busca pacientes con múltiples filtros"
)
def search_pacientes(
    *,
    db: Session = Depends(get_db),
    params: PacienteSearchParams
):
    """
    Búsqueda avanzada de pacientes
    
    Permite filtrar por:
    - Expediente
    - CUI
    - Pasaporte
    - Nombre
    - Apellido
    - Sexo
    - Estado
    - Rango de fechas de nacimiento
    """
    pacientes, total = crud_paciente.search(db, params=params)
    
    total_pages = (total + params.page_size - 1) // params.page_size
    
    # Agregar campos calculados
    items = []
    for paciente in pacientes:
        response_data = PacienteResponse.model_validate(paciente)
        response_data.nombre_completo = paciente.get_nombre_completo()
        response_data.edad = paciente.get_edad()
        items.append(response_data)
    
    return PacienteListResponse(
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
        items=items
    )


# ═══════════════════════════════════════════════════════════
# BÚSQUEDA POR IDENTIFICADORES
# ═══════════════════════════════════════════════════════════

@router.get(
    "/expediente/{expediente}",
    response_model=PacienteResponse,
    summary="Buscar por expediente",
    description="Busca un paciente por número de expediente"
)
def get_by_expediente(
    expediente: str,
    db: Session = Depends(get_db)
):
    """
    Busca un paciente por expediente
    
    - **expediente**: Número de expediente
    """
    paciente = crud_paciente.get_by_expediente(db, expediente=expediente)
    
    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paciente con expediente {expediente} no encontrado"
        )
    
    response_data = PacienteResponse.model_validate(paciente)
    response_data.nombre_completo = paciente.get_nombre_completo()
    response_data.edad = paciente.get_edad()
    
    return response_data


@router.get(
    "/cui/{cui}",
    response_model=PacienteResponse,
    summary="Buscar por CUI",
    description="Busca un paciente por CUI/DPI"
)
def get_by_cui(
    cui: int,
    db: Session = Depends(get_db)
):
    """
    Busca un paciente por CUI/DPI
    
    - **cui**: Número de CUI (13 dígitos)
    """
    # Validar formato de CUI
    valido, error = ValidadorPaciente.validar_cui(cui)
    if not valido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    paciente = crud_paciente.get_by_cui(db, cui=cui)
    
    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paciente con CUI {cui} no encontrado"
        )
    
    response_data = PacienteResponse.model_validate(paciente)
    response_data.nombre_completo = paciente.get_nombre_completo()
    response_data.edad = paciente.get_edad()
    
    return response_data


@router.get(
    "/pasaporte/{pasaporte}",
    response_model=PacienteResponse,
    summary="Buscar por pasaporte",
    description="Busca un paciente por número de pasaporte"
)
def get_by_pasaporte(
    pasaporte: str,
    db: Session = Depends(get_db)
):
    """
    Busca un paciente por pasaporte
    
    - **pasaporte**: Número de pasaporte
    """
    paciente = crud_paciente.get_by_pasaporte(db, pasaporte=pasaporte)
    
    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paciente con pasaporte {pasaporte} no encontrado"
        )
    
    response_data = PacienteResponse.model_validate(paciente)
    response_data.nombre_completo = paciente.get_nombre_completo()
    response_data.edad = paciente.get_edad()
    
    return response_data


# ═══════════════════════════════════════════════════════════
# CONSULTAS ESPECIALIZADAS
# ═══════════════════════════════════════════════════════════

@router.get(
    "/especial/fallecidos",
    response_model=PacienteListResponse,
    summary="Listar pacientes fallecidos",
    description="Lista todos los pacientes fallecidos"
)
def list_fallecidos(
    db: Session = Depends(get_db),
    pagination: dict = Depends(common_pagination_params)
):
    """Lista pacientes fallecidos con paginación"""
    pacientes = crud_paciente.get_pacientes_fallecidos(
        db,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )
    
    # Contar total de fallecidos
    from app.models.postgres.paciente import Paciente
    from sqlalchemy import func
    total = db.query(func.count(Paciente.id)).filter(
        Paciente.estado == EstadoEnum.FALLECIDO.value
    ).scalar()
    
    total_pages = (total + pagination["page_size"] - 1) // pagination["page_size"]
    
    items = []
    for paciente in pacientes:
        response_data = PacienteResponse.model_validate(paciente)
        response_data.nombre_completo = paciente.get_nombre_completo()
        response_data.edad = paciente.get_edad()
        items.append(response_data)
    
    return PacienteListResponse(
        total=total,
        page=pagination["page"],
        page_size=pagination["page_size"],
        total_pages=total_pages,
        items=items
    )


@router.get(
    "/especial/menores",
    response_model=PacienteListResponse,
    summary="Listar menores de edad",
    description="Lista todos los pacientes menores de 18 años"
)
def list_menores(
    db: Session = Depends(get_db),
    pagination: dict = Depends(common_pagination_params)
):
    """Lista pacientes menores de 18 años"""
    pacientes = crud_paciente.get_menores_de_edad(
        db,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )
    
    # Contar menores
    from datetime import date
    hoy = date.today()
    fecha_limite = date(hoy.year - 18, hoy.month, hoy.day)
    
    from app.models.postgres.paciente import Paciente
    from sqlalchemy import func
    total = db.query(func.count(Paciente.id)).filter(
        Paciente.fecha_nacimiento > fecha_limite
    ).scalar()
    
    total_pages = (total + pagination["page_size"] - 1) // pagination["page_size"]
    
    items = []
    for paciente in pacientes:
        response_data = PacienteResponse.model_validate(paciente)
        response_data.nombre_completo = paciente.get_nombre_completo()
        response_data.edad = paciente.get_edad()
        items.append(response_data)
    
    return PacienteListResponse(
        total=total,
        page=pagination["page"],
        page_size=pagination["page_size"],
        total_pages=total_pages,
        items=items
    )


@router.get(
    "/especial/sin-cui",
    response_model=PacienteListResponse,
    summary="Listar pacientes sin CUI",
    description="Lista pacientes que no tienen CUI registrado"
)
def list_sin_cui(
    db: Session = Depends(get_db),
    pagination: dict = Depends(common_pagination_params)
):
    """Lista pacientes sin CUI"""
    pacientes = crud_paciente.get_pacientes_sin_cui(
        db,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )
    
    from app.models.postgres.paciente import Paciente
    from sqlalchemy import func
    total = db.query(func.count(Paciente.id)).filter(
        Paciente.cui.is_(None)
    ).scalar()
    
    total_pages = (total + pagination["page_size"] - 1) // pagination["page_size"]
    
    items = []
    for paciente in pacientes:
        response_data = PacienteResponse.model_validate(paciente)
        response_data.nombre_completo = paciente.get_nombre_completo()
        response_data.edad = paciente.get_edad()
        items.append(response_data)
    
    return PacienteListResponse(
        total=total,
        page=pagination["page"],
        page_size=pagination["page_size"],
        total_pages=total_pages,
        items=items
    )


# ═══════════════════════════════════════════════════════════
# ESTADÍSTICAS
# ═══════════════════════════════════════════════════════════

@router.get(
    "/stats/general",
    summary="Estadísticas generales",
    description="Obtiene estadísticas generales de pacientes"
)
def get_stats(db: Session = Depends(get_db)):
    """
    Obtiene estadísticas generales del sistema
    
    Incluye:
    - Total de pacientes
    - Distribución por sexo
    - Distribución por estado
    - Calidad de datos
    - Información de migración
    """
    return crud_paciente.get_estadisticas(db)