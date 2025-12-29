# app/test/test_api.py

"""
Tests para los endpoints de la API
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


# ═══════════════════════════════════════════════════════════
# TESTS DE HEALTH CHECK
# ═══════════════════════════════════════════════════════════

class TestHealthCheck:
    """Tests para endpoints de health check"""
    
    def test_health_check_basic(self, client: TestClient):
        """Test del health check básico"""
        response = client.get("/api/v1/health/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data
    
    def test_database_health_check(self, client: TestClient):
        """Test del health check de base de datos"""
        response = client.get("/api/v1/health/database")
        
        assert response.status_code == 200
        data = response.json()
        assert "postgresql" in data


# ═══════════════════════════════════════════════════════════
# TESTS DE CRUD DE PACIENTES
# ═══════════════════════════════════════════════════════════

class TestPacientesCRUD:
    """Tests para operaciones CRUD de pacientes"""
    
    def test_create_paciente_success(self, client: TestClient, paciente_data):
        """Test crear paciente exitosamente"""
        response = client.post("/api/v1/pacientes/", json=paciente_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["expediente"] == paciente_data["expediente"]
        assert data["cui"] == paciente_data["cui"]
        assert data["nombre"]["primer_nombre"] == paciente_data["nombre"]["primer_nombre"]
        assert "id" in data
        assert "creado_en" in data
    
    def test_create_paciente_minimal(self, client: TestClient, paciente_data_minimal):
        """Test crear paciente con datos mínimos"""
        response = client.post("/api/v1/pacientes/", json=paciente_data_minimal)
        
        assert response.status_code == 201
        data = response.json()
        assert data["expediente"] == paciente_data_minimal["expediente"]
    
    def test_create_paciente_duplicate_expediente(
        self, 
        client: TestClient, 
        paciente_data
    ):
        """Test error al crear paciente con expediente duplicado"""
        # Crear primer paciente
        client.post("/api/v1/pacientes/", json=paciente_data)
        
        # Intentar crear otro con mismo expediente
        response = client.post("/api/v1/pacientes/", json=paciente_data)
        
        assert response.status_code == 400
        assert "error" in response.json()
    
    def test_create_paciente_invalid_cui(
        self, 
        client: TestClient, 
        paciente_data_invalid_cui
    ):
        """Test error con CUI inválido"""
        response = client.post("/api/v1/pacientes/", json=paciente_data_invalid_cui)
        
        assert response.status_code == 422
        data = response.json()
        assert "validation_errors" in data or "error" in data
    
    def test_get_paciente_by_id(self, client: TestClient, create_test_paciente):
        """Test obtener paciente por ID"""
        # Crear paciente
        paciente = create_test_paciente()
        
        # Obtener por ID
        response = client.get(f"/api/v1/pacientes/{paciente.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == paciente.id
        assert data["expediente"] == paciente.expediente
    
    def test_get_paciente_not_found(self, client: TestClient):
        """Test error al buscar paciente inexistente"""
        response = client.get("/api/v1/pacientes/99999")
        
        assert response.status_code == 404
        assert "error" in response.json()
    
    def test_update_paciente(
        self, 
        client: TestClient, 
        create_test_paciente
    ):
        """Test actualizar paciente"""
        paciente = create_test_paciente()
        
        update_data = {
            "contacto": {
                "telefono_principal": "99998888"
            }
        }
        
        response = client.put(
            f"/api/v1/pacientes/{paciente.id}",
            json=update_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["contacto"]["telefono_principal"] == "99998888"
    
    def test_delete_paciente(self, client: TestClient, create_test_paciente):
        """Test eliminar paciente"""
        paciente = create_test_paciente()
        
        response = client.delete(f"/api/v1/pacientes/{paciente.id}")
        
        assert response.status_code == 204
        
        # Verificar que ya no existe
        response = client.get(f"/api/v1/pacientes/{paciente.id}")
        assert response.status_code == 404
    
    def test_list_pacientes_pagination(
        self, 
        client: TestClient, 
        multiple_test_pacientes
    ):
        """Test listar pacientes con paginación"""
        response = client.get("/api/v1/pacientes/?page=1&page_size=3")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 3
        assert len(data["items"]) == 3
        assert data["total_pages"] == 2


# ═══════════════════════════════════════════════════════════
# TESTS DE BÚSQUEDA
# ═══════════════════════════════════════════════════════════

class TestPacientesBusqueda:
    """Tests para funcionalidades de búsqueda"""
    
    def test_search_by_expediente(
        self, 
        client: TestClient, 
        create_test_paciente
    ):
        """Test buscar por expediente"""
        paciente = create_test_paciente(expediente="SEARCH001")
        
        response = client.get("/api/v1/pacientes/expediente/SEARCH001")
        
        assert response.status_code == 200
        data = response.json()
        assert data["expediente"] == "SEARCH001"
    
    def test_search_by_cui(self, client: TestClient, create_test_paciente):
        """Test buscar por CUI"""
        cui = 9876543210987
        paciente = create_test_paciente(cui=cui)
        
        response = client.get(f"/api/v1/pacientes/cui/{cui}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["cui"] == cui
    
    def test_search_advanced(
        self, 
        client: TestClient, 
        multiple_test_pacientes
    ):
        """Test búsqueda avanzada con filtros"""
        search_params = {
            "sexo": "M",
            "estado": "V",
            "page": 1,
            "page_size": 10
        }
        
        response = client.post("/api/v1/pacientes/search", json=search_params)
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 0
        assert all(item["sexo"] == "M" for item in data["items"])
    
    def test_search_by_nombre(
        self, 
        client: TestClient, 
        create_test_paciente
    ):
        """Test buscar por nombre"""
        paciente = create_test_paciente(
            nombre={
                "primer_nombre": "Búsqueda",
                "primer_apellido": "Test"
            }
        )
        
        search_params = {
            "nombre": "Búsqueda",
            "page": 1,
            "page_size": 10
        }
        
        response = client.post("/api/v1/pacientes/search", json=search_params)
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1


# ═══════════════════════════════════════════════════════════
# TESTS DE CONSULTAS ESPECIALES
# ═══════════════════════════════════════════════════════════

class TestPacientesEspeciales:
    """Tests para consultas especializadas"""
    
    def test_get_fallecidos(self, client: TestClient, create_test_paciente):
        """Test obtener pacientes fallecidos"""
        # Crear paciente fallecido
        from datetime import datetime
        create_test_paciente(
            estado="F",
            datos_extra={
                "defuncion": {
                    "fecha_hora": datetime.now().isoformat()
                }
            }
        )
        
        response = client.get("/api/v1/pacientes/especial/fallecidos")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(item["estado"] == "F" for item in data["items"])
    
    def test_get_sin_cui(self, client: TestClient, create_test_paciente):
        """Test obtener pacientes sin CUI"""
        create_test_paciente(cui=None)
        
        response = client.get("/api/v1/pacientes/especial/sin-cui")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
    
    def test_get_stats(
        self, 
        client: TestClient, 
        multiple_test_pacientes
    ):
        """Test obtener estadísticas"""
        response = client.get("/api/v1/pacientes/stats/general")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "total_pacientes" in data
        assert "por_sexo" in data
        assert "por_estado" in data
        assert data["total_pacientes"] >= 5


# ═══════════════════════════════════════════════════════════
# TESTS DE VALIDACIÓN
# ═══════════════════════════════════════════════════════════

class TestValidacionAPI:
    """Tests de validación de datos en la API"""
    
    def test_invalid_page_number(self, client: TestClient):
        """Test error con número de página inválido"""
        response = client.get("/api/v1/pacientes/?page=0")
        
        assert response.status_code == 400
    
    def test_invalid_page_size(self, client: TestClient):
        """Test error con tamaño de página inválido"""
        response = client.get("/api/v1/pacientes/?page=1&page_size=200")
        
        assert response.status_code == 400
    
    def test_missing_required_fields(self, client: TestClient):
        """Test error al faltar campos requeridos"""
        invalid_data = {
            "expediente": "TEST999"
            # Falta nombre (requerido)
        }
        
        response = client.post("/api/v1/pacientes/", json=invalid_data)
        
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════
# TESTS DE MIGRACIÓN
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestMigracionAPI:
    """Tests para endpoints de migración"""
    
    def test_check_mysql_status(self, client: TestClient):
        """Test verificar estado de MySQL"""
        # Este test puede fallar si MySQL no está disponible
        response = client.get("/api/v1/migracion/check")
        
        # Aceptar tanto éxito como error de conexión
        assert response.status_code in [200, 503]
    
    def test_migration_status(self, client: TestClient):
        """Test obtener estado de migración"""
        response = client.get("/api/v1/migracion/status")
        
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "mysql" in data
            assert "postgresql" in data