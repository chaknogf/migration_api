# app/test/conftest.py
"""
Configuración de fixtures para pytest
Define fixtures compartidos entre todos los tests
"""

import pytest
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

from app.main import app
from app.database.postgres import Base, get_db
from app.models.postgres.paciente import Paciente
from app.core.config import settings


# ═══════════════════════════════════════════════════════════
# CONFIGURACIÓN DE BASE DE DATOS DE TESTS
# ═══════════════════════════════════════════════════════════

# URL de base de datos de test (SQLite en memoria para velocidad)
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"

# Crear engine de test
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}  # Solo para SQLite
)

# SessionLocal para tests
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine
)


# ═══════════════════════════════════════════════════════════
# FIXTURES DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def db_engine():
    """
    Crea el engine de base de datos para toda la sesión de tests
    """
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """
    Crea una sesión de base de datos para cada test
    Se hace rollback después de cada test
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Crea un cliente de test de FastAPI con la DB de test
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════
# FIXTURES DE DATOS DE PRUEBA
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def paciente_data():
    """
    Datos básicos para crear un paciente de prueba
    """
    return {
        "expediente": "12345",
        "cui": 1234567890123,
        "pasaporte": None,
        "nombre": {
            "primer_nombre": "Juan",
            "segundo_nombre": "Carlos",
            "otros_nombres": None,
            "primer_apellido": "Pérez",
            "segundo_apellido": "García",
            "apellido_casada": None
        },
        "sexo": "M",
        "fecha_nacimiento": "1990-01-15",
        "contacto": {
            "telefono_principal": "12345678",
            "email": "juan.perez@test.com",
            "direccion": {
                "linea1": "5ta Avenida 10-50, Zona 1",
                "municipio_id": 1,
                "departamento_id": 1
            }
        },
        "referencias": {
            "padre": "Pedro Pérez",
            "madre": "Ana García",
            "expediente_madre": None,
            "responsable": None,
            "conyugue": None,
            "es_gemelo": False
        },
        "estado": "V"
    }


@pytest.fixture
def paciente_data_minimal():
    """
    Datos mínimos requeridos para crear un paciente
    """
    return {
        "expediente": "99999",
        "nombre": {
            "primer_nombre": "Test",
            "primer_apellido": "Usuario"
        },
        "sexo": "NF"
    }


@pytest.fixture
def paciente_data_invalid_cui():
    """
    Datos con CUI inválido (menos de 13 dígitos)
    """
    return {
        "expediente": "88888",
        "cui": 123456789,  # Solo 9 dígitos (inválido)
        "nombre": {
            "primer_nombre": "Invalid",
            "primer_apellido": "CUI"
        },
        "sexo": "M"
    }


@pytest.fixture
def create_test_paciente(db_session: Session):
    """
    Factory fixture para crear pacientes de prueba en la DB
    """
    def _create_paciente(**kwargs):
        from app.models.postgres.paciente import Paciente
        
        default_data = {
            "expediente": "TEST123",
            "cui": 1111111111111,
            "nombre": {
                "primer_nombre": "Test",
                "primer_apellido": "Paciente"
            },
            "sexo": "M",
            "estado": "V"
        }
        
        # Merge con datos proporcionados
        data = {**default_data, **kwargs}
        
        paciente = Paciente(**data)
        db_session.add(paciente)
        db_session.commit()
        db_session.refresh(paciente)
        
        return paciente
    
    return _create_paciente


@pytest.fixture
def multiple_test_pacientes(db_session: Session, create_test_paciente):
    """
    Crea múltiples pacientes de prueba
    """
    pacientes = []
    
    for i in range(5):
        paciente = create_test_paciente(
            expediente=f"TEST{i+1}",
            cui=1000000000000 + i,
            nombre={
                "primer_nombre": f"Paciente{i+1}",
                "primer_apellido": f"Test{i+1}"
            },
            sexo="M" if i % 2 == 0 else "F"
        )
        pacientes.append(paciente)
    
    return pacientes


# ═══════════════════════════════════════════════════════════
# FIXTURES DE MIGRACIÓN
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def mysql_mock_data():
    """
    Datos simulados de MySQL para tests de migración
    """
    return {
        "id": 1,
        "expediente": 54321,
        "nombre": "María",
        "apellido": "López García",
        "dpi": 2987654321098,
        "pasaporte": None,
        "sexo": "F",
        "nacimiento": "1985-05-20",
        "nacionalidad": 1,
        "depto_nac": 1,
        "lugar_nacimiento": 1,
        "estado_civil": 2,
        "educacion": 3,
        "pueblo": 1,
        "idioma": 1,
        "ocupacion": "Doctora",
        "direccion": "10 Calle 5-10, Zona 10",
        "municipio": 1,
        "depto": 1,
        "telefono": "55556666",
        "email": "maria.lopez@test.com",
        "padre": "José López",
        "madre": "Carmen García",
        "exp_madre": None,
        "responsable": None,
        "parentesco": None,
        "dpi_responsable": None,
        "telefono_responsable": None,
        "exp_ref": None,
        "conyugue": None,
        "gemelo": "NO",
        "estado": "V",
        "fechaDefuncion": None,
        "hora_defuncion": None,
        "created_by": "admin",
        "created_at": "2024-01-01 10:00:00",
        "update_at": "2024-01-01 10:00:00"
    }


# ═══════════════════════════════════════════════════════════
# FIXTURES DE UTILIDAD
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def auth_headers():
    """
    Headers de autenticación para tests (para cuando se implemente auth)
    """
    return {
        "Authorization": "Bearer test_token"
    }


@pytest.fixture(autouse=True)
def reset_database(db_session):
    """
    Limpia la base de datos después de cada test
    autouse=True hace que se ejecute automáticamente
    """
    yield
    # El rollback en db_session fixture ya limpia los datos


@pytest.fixture
def mock_logger(monkeypatch):
    """
    Mock del logger para verificar logs en tests
    """
    import logging
    
    class MockLogger:
        def __init__(self):
            self.logs = {
                "debug": [],
                "info": [],
                "warning": [],
                "error": [],
                "critical": []
            }
        
        def debug(self, msg, *args, **kwargs):
            self.logs["debug"].append(msg)
        
        def info(self, msg, *args, **kwargs):
            self.logs["info"].append(msg)
        
        def warning(self, msg, *args, **kwargs):
            self.logs["warning"].append(msg)
        
        def error(self, msg, *args, **kwargs):
            self.logs["error"].append(msg)
        
        def critical(self, msg, *args, **kwargs):
            self.logs["critical"].append(msg)
    
    mock = MockLogger()
    monkeypatch.setattr("logging.getLogger", lambda name: mock)
    
    return mock


# ═══════════════════════════════════════════════════════════
# CONFIGURACIÓN DE PYTEST
# ═══════════════════════════════════════════════════════════

def pytest_configure(config):
    """
    Configuración global de pytest
    """
    config.addinivalue_line(
        "markers", "slow: marca tests que son lentos"
    )
    config.addinivalue_line(
        "markers", "integration: marca tests de integración"
    )
    config.addinivalue_line(
        "markers", "unit: marca tests unitarios"
    )


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Configuración del entorno de test antes de ejecutar todos los tests
    """
    import os
    
    # Configurar variables de entorno para tests
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["DEBUG"] = "True"
    
    yield
    
    # Cleanup después de todos los tests
    pass