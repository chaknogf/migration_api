from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.database.mysql import get_mysql_session
from app.database.postgres import get_postgres_session
from app.models.mysql.paciente import PacienteMysql
from app.models.postgres.paciente import PacientePostgres
from app.utils.normalizadores import (
    normalizar_cui,
    normalizar_expediente,
    validar_expediente_duplicado,
    normalizar_sexo,
    normalizar_estado,
    construir_nombre_jsonb,
    construir_contacto_jsonb,
    construir_referencias_jsonb,
    construir_datos_extra_jsonb,
    construir_metadatos_jsonb,
    limpiar_telefono
)


class MigracionPacientesService:
    """Servicio para migrar pacientes de MySQL a PostgreSQL"""
    
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self.errores: List[Dict[str, Any]] = []
        self.advertencias: List[Dict[str, Any]] = []
        self.exitosos = 0
        self.duplicados = 0
        self.cui_invalidos = 0
        
    async def transformar_paciente(
        self, 
        paciente_mysql: PacienteMysql
    ) -> Optional[Dict[str, Any]]:
        """
        Transforma un paciente de MySQL al formato PostgreSQL
        
        Returns:
            Dict con los datos transformados o None si hay error crítico
        """
        try:
            # 1. IDENTIFICADORES
            cui = normalizar_cui(paciente_mysql.dpi)
            if cui is None and paciente_mysql.dpi is not None:
                self.cui_invalidos += 1
                self.advertencias.append({
                    "id_mysql": paciente_mysql.id,
                    "expediente": paciente_mysql.expediente,
                    "tipo": "CUI_INVALIDO",
                    "mensaje": f"CUI/DPI inválido: {paciente_mysql.dpi}",
                    "timestamp": datetime.now().isoformat()
                })
            
            # Validar si expediente es duplicado
            es_duplicado = validar_expediente_duplicado(paciente_mysql.expediente)
            if es_duplicado:
                self.duplicados += 1
            
            expediente_normalizado = normalizar_expediente(
                paciente_mysql.expediente,
                paciente_mysql.id
            )
            
            # 2. CONSTRUIR DATOS TRANSFORMADOS
            datos_postgres = {
                # Identificadores
                "expediente": expediente_normalizado,
                "cui": cui,  # Puede ser None
                "pasaporte": paciente_mysql.pasaporte,
                
                # Nombre (JSONB)
                "nombre": construir_nombre_jsonb(
                    paciente_mysql.nombre,
                    paciente_mysql.apellido,
                    paciente_mysql.conyugue
                ),
                
                # Datos básicos
                "sexo": normalizar_sexo(paciente_mysql.sexo),
                "fecha_nacimiento": paciente_mysql.nacimiento,
                
                # Contacto (JSONB) - email siempre será None
                "contacto": construir_contacto_jsonb(
                    limpiar_telefono(paciente_mysql.telefono),
                    paciente_mysql.email,  # Se limpiará internamente a None
                    paciente_mysql.direccion,
                    paciente_mysql.municipio,
                    paciente_mysql.depto
                ),
                
                # Referencias (JSONB)
                "referencias": construir_referencias_jsonb(
                    paciente_mysql.padre,
                    paciente_mysql.madre,
                    paciente_mysql.exp_madre,
                    paciente_mysql.responsable,
                    paciente_mysql.parentesco,
                    paciente_mysql.dpi_responsable,
                    paciente_mysql.telefono_responsable,
                    paciente_mysql.exp_ref,
                    paciente_mysql.conyugue,
                    paciente_mysql.gemelo
                ),
                
                # Datos extra (JSONB) - con fecha_hora combinada
                "datos_extra": construir_datos_extra_jsonb(
                    paciente_mysql.nacionalidad,
                    paciente_mysql.depto_nac,
                    paciente_mysql.lugar_nacimiento,
                    paciente_mysql.estado_civil,
                    paciente_mysql.educacion,
                    paciente_mysql.pueblo,
                    paciente_mysql.idioma,
                    paciente_mysql.ocupacion,
                    paciente_mysql.fechaDefuncion,
                    paciente_mysql.hora_defuncion
                ),
                
                # Estado
                "estado": normalizar_estado(paciente_mysql.estado),
                
                # Metadatos (JSONB) - con flag de duplicado
                "metadatos": construir_metadatos_jsonb(
                    paciente_mysql.id,
                    paciente_mysql.created_by,
                    es_duplicado
                ),
                
                # Timestamps
                "creado_en": paciente_mysql.created_at,
                "actualizado_en": paciente_mysql.update_at
            }
            
            return datos_postgres
            
        except Exception as e:
            self.errores.append({
                "id_mysql": paciente_mysql.id,
                "expediente": paciente_mysql.expediente,
                "error": str(e),
                "tipo": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            })
            return None
    
    async def migrar_batch(
        self,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Migra un lote de pacientes"""
        
        batch_exitosos = 0
        batch_errores = 0
        
        async with get_mysql_session() as mysql_session:
            async with get_postgres_session() as postgres_session:
                # Leer de MySQL
                query = (
                    select(PacienteMysql)
                    .offset(offset)
                    .limit(self.batch_size)
                    .order_by(PacienteMysql.id)
                )
                
                result = await mysql_session.execute(query)
                pacientes_mysql = result.scalars().all()
                
                if not pacientes_mysql:
                    return {
                        "procesados": 0,
                        "exitosos": 0,
                        "errores": 0,
                        "mensaje": "No hay más registros"
                    }
                
                # Transformar y guardar
                for paciente_mysql in pacientes_mysql:
                    datos_transformados = await self.transformar_paciente(paciente_mysql)
                    
                    if datos_transformados:
                        try:
                            paciente_postgres = PacientePostgres(**datos_transformados)
                            postgres_session.add(paciente_postgres)
                            batch_exitosos += 1
                            self.exitosos += 1
                        except Exception as e:
                            batch_errores += 1
                            self.errores.append({
                                "id_mysql": paciente_mysql.id,
                                "expediente": paciente_mysql.expediente,
                                "error": f"Error al insertar en PostgreSQL: {str(e)}",
                                "tipo": "INSERT_ERROR",
                                "timestamp": datetime.now().isoformat()
                            })
                    else:
                        batch_errores += 1
                
                # Commit del batch
                try:
                    await postgres_session.commit()
                except Exception as e:
                    await postgres_session.rollback()
                    self.errores.append({
                        "batch": offset,
                        "error": f"Error en commit del batch: {str(e)}",
                        "tipo": "COMMIT_ERROR",
                        "timestamp": datetime.now().isoformat()
                    })
                    return {
                        "procesados": len(pacientes_mysql),
                        "exitosos": 0,
                        "errores": len(pacientes_mysql),
                        "offset_siguiente": offset + self.batch_size
                    }
                
                return {
                    "procesados": len(pacientes_mysql),
                    "exitosos": batch_exitosos,
                    "errores": batch_errores,
                    "offset_siguiente": offset + self.batch_size
                }
    
    async def migrar_todo(self) -> Dict[str, Any]:
        """Migra todos los pacientes en batches"""
        offset = 0
        total_procesados = 0
        
        print("🚀 Iniciando migración completa...")
        
        while True:
            resultado = await self.migrar_batch(offset)
            
            if resultado["procesados"] == 0:
                break
            
            total_procesados += resultado["procesados"]
            offset = resultado["offset_siguiente"]
            
            print(f"📦 Batch {offset // self.batch_size}: "
                  f"{resultado['exitosos']} exitosos, "
                  f"{resultado['errores']} errores")
        
        print(f"\n✅ Migración completada!")
        print(f"   Total procesados: {total_procesados}")
        print(f"   Exitosos: {self.exitosos}")
        print(f"   Errores: {len(self.errores)}")
        print(f"   Duplicados: {self.duplicados}")
        print(f"   CUI inválidos: {self.cui_invalidos}")
        
        return {
            "total_procesados": total_procesados,
            "total_exitosos": self.exitosos,
            "total_errores": len(self.errores),
            "total_advertencias": len(self.advertencias),
            "expedientes_duplicados": self.duplicados,
            "cui_invalidos": self.cui_invalidos,
            "errores": self.errores,
            "advertencias": self.advertencias
        }
    
    def generar_reporte(self) -> str:
        """Genera un reporte legible de la migración"""
        reporte = f"""
╔════════════════════════════════════════════════════════════╗
║           REPORTE DE MIGRACIÓN - PACIENTES                 ║
╚════════════════════════════════════════════════════════════╝

📊 RESUMEN:
   • Total exitosos:           {self.exitosos}
   • Total errores:            {len(self.errores)}
   • Total advertencias:       {len(self.advertencias)}
   • Expedientes duplicados:   {self.duplicados}
   • CUI inválidos:            {self.cui_invalidos}

"""
        
        if self.errores:
            reporte += "\n❌ ERRORES:\n"
            for error in self.errores[:10]:  # Primeros 10
                reporte += f"   • ID {error.get('id_mysql')}: {error.get('error')}\n"
            
            if len(self.errores) > 10:
                reporte += f"   ... y {len(self.errores) - 10} errores más\n"
        
        if self.advertencias:
            reporte += "\n⚠️  ADVERTENCIAS:\n"
            for adv in self.advertencias[:10]:
                reporte += f"   • {adv.get('tipo')}: ID {adv.get('id_mysql')}\n"
        
        return reporte