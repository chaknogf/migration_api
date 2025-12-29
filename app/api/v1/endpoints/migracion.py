"""
Endpoints para el proceso de migración MySQL → PostgreSQL
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.api.deps import get_db, get_mysql
from app.schemas.paciente import MigracionResponse, MigracionStats
from app.services.migracion_pacientes import MigracionPacientesService
from app.database import mysql

router = APIRouter()


@router.get(
    "/check",
    summary="Verificar estado de MySQL",
    description="Verifica la conexión y estado de la base de datos MySQL"
)
def check_mysql_status():
    """
    Verifica el estado de la base de datos MySQL
    
    Returns:
        Información sobre MySQL y la tabla de pacientes
    """
    try:
        health = mysql.health_check()
        
        if health["status"] != "healthy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MySQL no está disponible"
            )
        
        # Obtener información de la tabla
        table_info = mysql.get_table_info("pacientes")
        
        # Obtener información de duplicados
        duplicados_info = mysql.get_duplicate_expedientes()
        
        # CUI inválidos
        cui_invalidos = mysql.get_invalid_cui_count()
        
        return {
            "mysql_status": health,
            "tabla_pacientes": {
                "total_registros": table_info["total_records"],
                "total_columnas": len(table_info["columns"])
            },
            "calidad_datos": {
                "expedientes_nulos": duplicados_info["expedientes_nulos"],
                "expedientes_duplicados": duplicados_info["expedientes_duplicados"],
                "cui_invalidos": cui_invalidos
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al verificar MySQL: {str(e)}"
        )


@router.post(
    "/migrate",
    response_model=MigracionResponse,
    summary="Iniciar migración completa",
    description="Migra todos los pacientes de MySQL a PostgreSQL"
)
async def migrate_all_pacientes(
    background_tasks: BackgroundTasks,
    batch_size: int = 100,
    db: Session = Depends(get_db)
):
    """
    Inicia el proceso de migración completo
    
    - **batch_size**: Tamaño del lote para procesamiento (default: 100)
    
    ⚠️ Este proceso puede tardar varios minutos dependiendo del volumen de datos
    """
    try:
        # Crear servicio de migración
        servicio = MigracionPacientesService(batch_size=batch_size)
        
        # Ejecutar migración
        resultado = await servicio.migrar_todo()
        
        # Generar reporte
        reporte = servicio.generar_reporte()
        print(reporte)
        
        return MigracionResponse(
            mensaje="Migración completada",
            stats=MigracionStats(**resultado),
            errores=resultado.get("errores", []),
            advertencias=resultado.get("advertencias", [])
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante la migración: {str(e)}"
        )


@router.post(
    "/migrate/batch",
    response_model=Dict[str, Any],
    summary="Migrar un lote",
    description="Migra un lote específico de pacientes"
)
async def migrate_batch(
    offset: int = 0,
    batch_size: int = 100,
    db: Session = Depends(get_db)
):
    """
    Migra un lote específico de pacientes
    
    - **offset**: Desde qué registro comenzar
    - **batch_size**: Cantidad de registros a procesar
    
    Útil para migración controlada o recuperación de errores
    """
    try:
        servicio = MigracionPacientesService(batch_size=batch_size)
        resultado = await servicio.migrar_batch(offset=offset)
        
        return {
            "mensaje": f"Lote migrado (offset: {offset})",
            "resultado": resultado
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error migrando lote: {str(e)}"
        )


@router.get(
    "/status",
    summary="Estado de la migración",
    description="Obtiene el estado actual del proceso de migración"
)
def get_migration_status(
    db: Session = Depends(get_db)
):
    """
    Obtiene estadísticas del estado de migración
    
    Compara registros en MySQL vs PostgreSQL
    """
    try:
        # Contar en MySQL
        mysql_count = mysql.get_table_count("pacientes")
        
        # Contar en PostgreSQL
        from app.crud.paciente import crud_paciente
        postgres_count = crud_paciente.get_count(db)
        
        # Contar migrados
        from app.models.postgres.paciente import Paciente
        from sqlalchemy import func
        migrados_count = db.query(func.count(Paciente.id)).filter(
            Paciente.metadatos['sistema_origen'].astext == 'mysql_legacy'
        ).scalar()
        
        porcentaje = (migrados_count / mysql_count * 100) if mysql_count > 0 else 0
        
        return {
            "mysql": {
                "total_registros": mysql_count
            },
            "postgresql": {
                "total_registros": postgres_count,
                "registros_migrados": migrados_count,
                "registros_nuevos": postgres_count - migrados_count
            },
            "progreso": {
                "porcentaje_migrado": round(porcentaje, 2),
                "pendientes": mysql_count - migrados_count,
                "completado": migrados_count >= mysql_count
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo estado: {str(e)}"
        )