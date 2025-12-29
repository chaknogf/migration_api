"""
Excepciones personalizadas y manejadores de errores
"""

from app.exceptions.handlers import (
    # Excepciones personalizadas
    PacienteNotFoundError,
    PacienteAlreadyExistsError,
    InvalidIdentifierError,
    MigrationError,
    DatabaseConnectionError,
    ValidationError,
    
    # Manejadores de excepciones
    add_exception_handlers
)

__all__ = [
    "PacienteNotFoundError",
    "PacienteAlreadyExistsError",
    "InvalidIdentifierError",
    "MigrationError",
    "DatabaseConnectionError",
    "ValidationError",
    "add_exception_handlers"
]

# En app/api/v1/endpoints/pacientes.py

# from app.exceptions.handlers import (
#     PacienteNotFoundError,
#     PacienteAlreadyExistsError,
#     InvalidIdentifierError
# )

# @router.get("/{paciente_id}")
# def get_paciente(paciente_id: int, db: Session = Depends(get_db)):
#     paciente = crud_paciente.get(db, id=paciente_id)
    
#     if not paciente:
#         # Esto será capturado automáticamente por el manejador
#         raise PacienteNotFoundError(paciente_id, "ID")
    
#     return paciente


# @router.post("/")
# def create_paciente(paciente_in: PacienteCreate, db: Session = Depends(get_db)):
#     # Validar que no exista
#     if crud_paciente.get_by_expediente(db, paciente_in.expediente):
#         raise PacienteAlreadyExistsError(paciente_in.expediente, "expediente")
    
#     # Validar CUI
#     if paciente_in.cui:
#         valido, error = ValidadorPaciente.validar_cui(paciente_in.cui)
#         if not valido:
#             raise InvalidIdentifierError("CUI", error)
    
#     return crud_paciente.create(db, obj_in=paciente_in)