"""
Modelos SQLAlchemy para MySQL (base de datos legacy)
SOLO LECTURA - Exclusivamente para migración
"""

from app.models.mysql.paciente import PacienteMysql

__all__ = ["PacienteMysql"]