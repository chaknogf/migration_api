"""
Modelos SQLAlchemy para PostgreSQL y MySQL
"""

from app.models.postgres.paciente import Paciente as PacientePostgres
from app.models.mysql.paciente import PacienteMysql

__all__ = [
    "PacientePostgres",
    "PacienteMysql"
]

# Ejemplo de uso (comentado para evitar ejecución directa)
# # Leer de MySQL
# paciente_mysql = session_mysql.query(PacienteMysql).first()

# # Transformar datos
# datos_transformados = transformar_paciente(paciente_mysql)

# # Crear en PostgreSQL
# paciente_postgres = Paciente(**datos_transformados)
# session_postgres.add(paciente_postgres)