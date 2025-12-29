"""
Operaciones CRUD para el sistema
"""

from app.crud.paciente import CRUDPaciente

crud_paciente = CRUDPaciente()

__all__ = ["crud_paciente"]