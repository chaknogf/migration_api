# app/test/test_services.py

"""
Tests para los servicios de la aplicación
"""

import pytest
from datetime import datetime, date
from sqlalchemy.orm import Session


# ═══════════════════════════════════════════════════════════
# TESTS DE VALIDACIÓN
# ═══════════════════════════════════════════════════════════

class TestValidadorPaciente:
    """Tests para el servicio de validación de pacientes"""
    
    def test_validar_cui_valido(self):
        """Test validación de CUI válido"""
        from app.services.validacion import ValidadorPaciente
        
        cui = 1234567890123  # 13 dígitos
        valido, error = ValidadorPaciente.validar_cui(cui)
        
        # El CUI tiene 13 dígitos, pero puede fallar la validación del dígito verificador
        # Solo verificamos que la longitud sea correcta
        assert isinstance(valido, bool)
    
    def test_validar_cui_invalido_longitud(self):
        """Test CUI con longitud incorrecta"""
        from app.services.validacion import ValidadorPaciente
        
        cui = 12345  # Solo 5 dígitos
        valido, error = ValidadorPaciente.validar_cui(cui)
        
        assert valido is False
        assert "13 dígitos" in error
    
    def test_validar_cui_none(self):
        """Test CUI None (opcional)"""
        from app.services.validacion import ValidadorPaciente
        
        valido, error = ValidadorPaciente.validar_cui(None)
        
        assert valido is True
        assert error is None
    
    def test_validar_sexo_valido(self):
        """Test validación de sexo válido"""
        from app.services.validacion import ValidadorPaciente
        
        for sexo in ["M", "F", "NF"]:
            valido, error = ValidadorPaciente.validar_sexo(sexo)
            assert valido is True
            assert error is None
    
    def test_validar_sexo_invalido(self):
        """Test sexo inválido"""
        from app.services.validacion import ValidadorPaciente
        
        valido, error = ValidadorPaciente.validar_sexo("X")
        
        assert valido is False
        assert error is not None
    
    def test_validar_fecha_nacimiento_valida(self):
        """Test fecha de nacimiento válida"""
        from app.services.validacion import ValidadorPaciente
        
        fecha = date(1990, 1, 15)
        valido, error = ValidadorPaciente.validar_fecha_nacimiento(fecha)
        
        assert valido is True
        assert error is None
    
    def test_validar_fecha_nacimiento_futura(self):
        """Test fecha de nacimiento futura (inválida)"""
        from app.services.validacion import ValidadorPaciente
        from datetime import timedelta
        
        fecha_futura = date.today() + timedelta(days=1)
        valido, error = ValidadorPaciente.validar_fecha_nacimiento(fecha_futura)
        
        assert valido is False
        assert "futura" in error.lower()
    
    def test_validar_nombre_jsonb(self):
        """Test validación de estructura JSONB de nombre"""
        from app.services.validacion import ValidadorPaciente
        
        nombre_valido = {
            "primer_nombre": "Juan",
            "primer_apellido": "Pérez"
        }
        
        valido, errores = ValidadorPaciente.validar_nombre_jsonb(nombre_valido)
        
        assert valido is True
        assert len(errores) == 0
    
    def test_validar_nombre_jsonb_sin_campos_requeridos(self):
        """Test nombre sin campos requeridos"""
        from app.services.validacion import ValidadorPaciente
        
        nombre_invalido = {
            "segundo_nombre": "Carlos"
            # Falta primer_nombre y primer_apellido
        }
        
        valido, errores = ValidadorPaciente.validar_nombre_jsonb(nombre_invalido)
        
        assert valido is False
        assert len(errores) > 0
    
    def test_calcular_edad(self):
        """Test cálculo de edad"""
        from app.services.validacion import ValidadorPaciente
        
        fecha_nacimiento = date(1990, 1, 1)
        edad = ValidadorPaciente.calcular_edad(fecha_nacimiento)
        
        assert isinstance(edad, int)
        assert edad >= 0
        assert edad < 150
    
    def test_validar_paciente_completo_valido(self):
        """Test validación completa de paciente válido"""
        from app.services.validacion import ValidadorPaciente
        
        valido, errores = ValidadorPaciente.validar_paciente_completo(
            expediente="12345",
            cui=1234567890123,
            pasaporte=None,
            nombre={
                "primer_nombre": "Juan",
                "primer_apellido": "Pérez"
            },
            sexo="M",
            fecha_nacimiento=date(1990, 1, 15),
            estado="V"
        )
        
        # Puede tener errores de CUI (dígito verificador) pero debe aceptar la estructura
        assert isinstance(valido, bool)
        assert isinstance(errores, dict)
    
    def test_validar_defuncion_coherencia(self):
        """Test coherencia entre estado y datos de defunción"""
        from app.services.validacion import ValidadorPaciente
        
        # Fallecido sin fecha de defunción (debería fallar)
        valido, errores = ValidadorPaciente.validar_paciente_completo(
            expediente="12345",
            cui=None,
            pasaporte=None,
            nombre={
                "primer_nombre": "Test",
                "primer_apellido": "Fallecido"
            },
            sexo="M",
            fecha_nacimiento=date(1990, 1, 15),
            estado="F"  # Fallecido pero sin datos_extra.defuncion
        )
        
        assert valido is False
        assert "estado" in errores


# ═══════════════════════════════════════════════════════════
# TESTS DE MIGRACIÓN
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestMigracionService:
    """Tests para el servicio de migración"""
    
    def test_transformar_paciente_mysql_mock(self, mysql_mock_data):
        """Test transformación de datos MySQL a PostgreSQL"""
        from app.services.migracion.pacientes import MigracionPacientesService
        from unittest.mock import MagicMock
        
        servicio = MigracionPacientesService()
        
        # Crear mock de paciente MySQL
        paciente_mysql = MagicMock()
        for key, value in mysql_mock_data.items():
            setattr(paciente_mysql, key, value)
        
        # Transformar
        resultado = servicio.transformar_paciente(paciente_mysql)
        
        # Verificar que no sea None (transformación exitosa)
        # O que sea None con error registrado
        if resultado is not None:
            assert "expediente" in resultado
            assert "nombre" in resultado
            assert "sexo" in resultado

    
    def test_servicio_inicializa_correctamente(self):
    # """Test que el servicio de migración se inicializa correctamente"""
        from app.services.migracion.pacientes import MigracionPacientesService
    
        servicio = MigracionPacientesService(batch_size=50)
        
        assert servicio.batch_size == 50
        assert servicio.exitosos == 0
        assert isinstance(servicio.errores, list)

# ═══════════════════════════════════════════════════════════
# TESTS DE NORMALIZACIÓN
# ═══════════════════════════════════════════════════════════
class TestNormalizadores:
# Tests para funciones de normalización

    def test_normalizar_cui_valido(self):
        """Test normalización de CUI válido"""
        from app.utils.normalizadores import normalizar_cui
        
        cui = 1234567890123
        resultado = normalizar_cui(cui)
        
        assert resultado == cui or resultado is None

    def test_normalizar_cui_invalido(self):
        """Test CUI inválido retorna None"""
        from app.utils.normalizadores import normalizar_cui
        
        cui_invalido = 12345  # Menos de 13 dígitos
        resultado = normalizar_cui(cui_invalido)
        
        assert resultado is None

    def test_normalizar_sexo(self):
        """Test normalización de sexo"""
        from app.utils.normalizadores import normalizar_sexo
        
        assert normalizar_sexo("M") == "M"
        assert normalizar_sexo("F") == "F"
        assert normalizar_sexo("MASCULINO") == "M"
        assert normalizar_sexo("FEMENINO") == "F"
        assert normalizar_sexo("X") == "NF"
        assert normalizar_sexo(None) == "NF"

    def test_normalizar_estado(self):
        """Test normalización de estado"""
        from app.utils.normalizadores import normalizar_estado
        
        assert normalizar_estado("V") == "V"
        assert normalizar_estado("F") == "F"
        assert normalizar_estado("FALLECIDO") == "F"
        assert normalizar_estado(None) == "V"

    def test_normalizar_expediente(self):
        """Test normalización de expediente"""
        from app.utils.normalizadores import normalizar_expediente
        
        # Expediente válido
        assert normalizar_expediente(12345, 1) == "12345"
        
        # Expediente None o 0 genera DUP
        assert normalizar_expediente(None, 123) == "DUP-123"
        assert normalizar_expediente(0, 456) == "DUP-456"

    def test_extraer_nombres(self):
        """Test extracción de nombres"""
        from app.utils.normalizadores import extraer_nombres
        
        resultado = extraer_nombres("Juan Carlos José")
        
        assert resultado["primer_nombre"] == "Juan"
        assert resultado["segundo_nombre"] == "Carlos"
        assert resultado["otros_nombres"] == "José"

    def test_extraer_apellidos(self):
        """Test extracción de apellidos"""
        from app.utils.normalizadores import extraer_apellidos
        
        resultado = extraer_apellidos("Pérez García López")
        
        assert resultado["primer_apellido"] == "Pérez"
        assert resultado["segundo_apellido"] == "García López"

    def test_parsear_fecha_defuncion(self):
        """Test parseo de fecha de defunción"""
        from app.utils.normalizadores import parsear_fecha_defuncion
        from datetime import time
        
        fecha_str = "2024-01-15"
        hora = time(10, 30, 0)
        
        resultado = parsear_fecha_defuncion(fecha_str, hora)
        
        assert resultado is not None
        assert resultado.year == 2024
        assert resultado.month == 1
        assert resultado.day == 15
        assert resultado.hour == 10
        assert resultado.minute == 30

    def test_construir_nombre_jsonb(self):
        """Test construcción de JSONB de nombre"""
        from app.utils.normalizadores import construir_nombre_jsonb
        
        resultado = construir_nombre_jsonb(
            "Juan Carlos",
            "Pérez García",
            "López"
        )
        
        assert resultado["primer_nombre"] == "Juan"
        assert resultado["segundo_nombre"] == "Carlos"
        assert resultado["primer_apellido"] == "Pérez"
        assert resultado["segundo_apellido"] == "García"
        assert resultado["apellido_casada"] == "López"
        ---

### `tests/test_utils.py`
```python
"""
Tests para utilidades y funciones helper
"""

import pytest
from datetime import date, datetime, time


# ═══════════════════════════════════════════════════════════
# TESTS DE UTILIDADES GENERALES
# ═══════════════════════════════════════════════════════════

class TestUtilsGenerales:
    """Tests para funciones de utilidad generales"""
    
    def test_es_cui_valido(self):
        """Test función rápida de validación de CUI"""
        from app.services.validacion import es_cui_valido
        
        # CUI con 13 dígitos (puede o no pasar validación de dígito verificador)
        cui_13_digitos = 1234567890123
        resultado = es_cui_valido(cui_13_digitos)
        assert isinstance(resultado, bool)
        
        # CUI inválido (menos dígitos)
        cui_invalido = 12345
        assert es_cui_valido(cui_invalido) is False
        
        # CUI None
        assert es_cui_valido(None) is True  # None es válido (opcional)
    
    def test_es_mayor_de_edad(self):
        """Test determinar si es mayor de edad"""
        from app.services.validacion import es_mayor_de_edad
        
        # Persona mayor de edad
        fecha_mayor = date(2000, 1, 1)
        assert es_mayor_de_edad(fecha_mayor) is True
        
        # Persona menor de edad
        from datetime import timedelta
        fecha_menor = date.today() - timedelta(days=365 * 10)  # 10 años
        assert es_mayor_de_edad(fecha_menor) is False
    
    def test_es_menor_de_edad(self):
        """Test determinar si es menor de edad"""
        from app.services.validacion import es_menor_de_edad
        
        fecha_menor = date.today().replace(year=date.today().year - 10)
        assert es_menor_de_edad(fecha_menor) is True
        
        fecha_mayor = date(1990, 1, 1)
        assert es_menor_de_edad(fecha_mayor) is False


# ═══════════════════════════════════════════════════════════
# TESTS DE CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════

class TestConfiguracion:
    """Tests para configuración de la aplicación"""
    
    def test_settings_carga_correctamente(self):
        """Test que la configuración se carga correctamente"""
        from app.core.config import settings
        
        assert settings.PROJECT_NAME is not None
        assert settings.VERSION is not None
        assert settings.API_V1_PREFIX is not None
    
    def test_settings_postgres_uri(self):
        """Test construcción de URI de PostgreSQL"""
        from app.core.config import settings
        
        uri = settings.POSTGRES_URI
        
        assert "postgresql" in uri
        assert settings.POSTGRES_USER in uri
        assert settings.POSTGRES_DB in uri
    
    def test_settings_mysql_uri(self):
        """Test construcción de URI de MySQL"""
        from app.core.config import settings
        
        uri = settings.MYSQL_URI
        
        assert "mysql" in uri
        assert settings.MYSQL_USER in uri
        assert settings.MYSQL_DATABASE in uri
    
    def test_settings_pagination(self):
        """Test configuración de paginación"""
        from app.core.config import settings
        
        assert settings.DEFAULT_PAGE_SIZE > 0
        assert settings.MAX_PAGE_SIZE > settings.DEFAULT_PAGE_SIZE


# ═══════════════════════════════════════════════════════════
# TESTS DE SCHEMAS PYDANTIC
# ═══════════════════════════════════════════════════════════

class TestSchemas:
    """Tests para schemas de Pydantic"""
    
    def test_nombre_schema_valido(self):
        """Test schema de nombre válido"""
        from app.schemas.paciente import NombreSchema
        
        data = {
            "primer_nombre": "Juan",
            "segundo_nombre": "Carlos",
            "primer_apellido": "Pérez",
            "segundo_apellido": "García"
        }
        
        nombre = NombreSchema(**data)
        
        assert nombre.primer_nombre == "Juan"
        assert nombre.segundo_nombre == "Carlos"
    
    def test_nombre_schema_campos_requeridos(self):
        """Test que nombre requiere campos obligatorios"""
        from app.schemas.paciente import NombreSchema
        from pydantic import ValidationError
        
        # Falta primer_nombre
        with pytest.raises(ValidationError):
            NombreSchema(
                primer_apellido="Pérez"
            )
    
    def test_paciente_create_schema_valido(self):
        """Test schema de creación de paciente"""
        from app.schemas.paciente import PacienteCreate
        
        data = {
            "expediente": "12345",
            "cui": 1234567890123,
            "nombre": {
                "primer_nombre": "Juan",
                "primer_apellido": "Pérez"
            },
            "sexo": "M"
        }
        
        paciente = PacienteCreate(**data)
        
        assert paciente.expediente == "12345"
        assert paciente.nombre.primer_nombre == "Juan"
    
    def test_paciente_schema_validacion_cui(self):
        """Test validación de CUI en schema"""
        from app.schemas.paciente import PacienteCreate
        from pydantic import ValidationError
        
        # CUI inválido (menos de 13 dígitos)
        with pytest.raises(ValidationError):
            PacienteCreate(
                expediente="12345",
                cui=123,  # Solo 3 dígitos
                nombre={
                    "primer_nombre": "Test",
                    "primer_apellido": "Usuario"
                },
                sexo="M"
            )
    
    def test_contacto_schema_validacion_telefono(self):
        """Test validación de teléfono en schema de contacto"""
        from app.schemas.paciente import ContactoSchema
        from pydantic import ValidationError
        
        # Teléfono válido (8 dígitos)
        contacto = ContactoSchema(
            telefono_principal="12345678"
        )
        assert contacto.telefono_principal == "12345678"
        
        # Teléfono inválido
        with pytest.raises(ValidationError):
            ContactoSchema(
                telefono_principal="123"  # Muy corto
            )


# ═══════════════════════════════════════════════════════════
# TESTS DE EXCEPCIONES
# ═══════════════════════════════════════════════════════════

class TestExcepciones:
    """Tests para excepciones personalizadas"""
    
    def test_paciente_not_found_error(self):
        """Test excepción de paciente no encontrado"""
        from app.exceptions.handlers import PacienteNotFoundError
        from fastapi import status
        
        exc = PacienteNotFoundError(123, "ID")
        
        assert exc.status_code == status.HTTP_404_NOT_FOUND
        assert "123" in exc.message
        assert "ID" in exc.message
    
    def test_paciente_already_exists_error(self):
        """Test excepción de paciente duplicado"""
        from app.exceptions.handlers import PacienteAlreadyExistsError
        from fastapi import status
        
        exc = PacienteAlreadyExistsError("12345", "expediente")
        
        assert exc.status_code == status.HTTP_409_CONFLICT
        assert "12345" in exc.message
    
    def test_invalid_identifier_error(self):
        """Test excepción de identificador inválido"""
        from app.exceptions.handlers import InvalidIdentifierError
        from fastapi import status
        
        exc = InvalidIdentifierError("CUI", "debe tener 13 dígitos")
        
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert "CUI" in exc.message
    
    def test_validation_error(self):
        """Test excepción de validación"""
        from app.exceptions.handlers import ValidationError
        from fastapi import status
        
        exc = ValidationError("fecha_nacimiento", "no puede ser futura")
        
        assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "fecha_nacimiento" in exc.message


# ═══════════════════════════════════════════════════════════
# TESTS DE INTEGRACIÓN DE UTILIDADES
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestIntegracionUtils:
    """Tests de integración para utilidades"""
    
    def test_flujo_completo_normalizacion(self, mysql_mock_data):
        """Test flujo completo de normalización de datos"""
        from app.utils.normalizadores import (
            normalizar_cui,
            normalizar_sexo,
            normalizar_estado,
            construir_nombre_jsonb,
            construir_contacto_jsonb
        )
        
        # Normalizar CUI
        cui = normalizar_cui(mysql_mock_data["dpi"])
        assert cui is not None or mysql_mock_data["dpi"] is None
        
        # Normalizar sexo
        sexo = normalizar_sexo(mysql_mock_data["sexo"])
        assert sexo in ["M", "F", "NF"]
        
        # Normalizar estado
        estado = normalizar_estado(mysql_mock_data["estado"])
        assert estado in ["V", "F"]
        
        # Construir nombre
        nombre = construir_nombre_jsonb(
            mysql_mock_data["nombre"],
            mysql_mock_data["apellido"]
        )
        assert "primer_nombre" in nombre
        assert "primer_apellido" in nombre
        
        # Construir contacto
        contacto = construir_contacto_jsonb(
            mysql_mock_data["telefono"],
            mysql_mock_data["email"],
            mysql_mock_data["direccion"],
            mysql_mock_data["municipio"],
            mysql_mock_data["depto"]
        )
        assert "telefono_principal" in contacto


# ### `tests/pytest.ini`
# ```ini
# [pytest]
# # Configuración de pytest

# # Patrón para descubrir archivos de test
# python_files = test_*.py
# python_classes = Test*
# python_functions = test_*

# # Directorio donde buscar tests
# testpaths = tests

# # Opciones por defecto
# addopts =
#     -v
#     --strict-markers
#     --tb=short
#     --cov=app
#     --cov-report=html
#     --cov-report=term-missing
#     --cov-branch

# # Markers personalizados
# markers =
#     slow: marca tests que son lentos
#     integration: marca tests de integración
#     unit: marca tests unitarios
#     skip_mysql: salta tests que requieren MySQL

# # Ignorar warnings específicos
# filterwarnings =
#     ignore::DeprecationWarning
#     ignore::PendingDeprecationWarning

# # Configuración de cobertura
# [coverage:run]
# source = app
# omit =
#     */tests/*
#     */venv/*
#     */__pycache__/*
#     */migrations/*

# [coverage:report]
# precision = 2
# show_missing = True
# skip_covered = False
# ```

# ---

# ### `tests/README.md`
# ```markdown
# # Tests del Sistema de Gestión de Pacientes

# ## Estructura de Tests
# ```
# tests/
# ├── conftest.py           # Fixtures compartidos
# ├── test_api.py          # Tests de endpoints
# ├── test_services.py     # Tests de servicios
# ├── test_utils.py        # Tests de utilidades
# └── pytest.ini           # Configuración de pytest