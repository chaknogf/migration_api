from abc import ABC, abstractmethod

class MigracionBase(ABC):
    @abstractmethod
    async def validar_origen(self):
        pass
    
    @abstractmethod
    async def transformar_datos(self, data):
        pass
    
    @abstractmethod
    async def migrar_batch(self, batch_size: int):
        pass

### 3. **Agregar pruebas**

# tests/
# ├── __init__.py
# ├── conftest.py
# ├── test_api/
# ├── test_services/
# └── test_utils/