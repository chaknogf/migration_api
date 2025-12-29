# app/core/config.py
"""
Configuración centralizada de la aplicación
Carga variables de entorno y define configuraciones globales
"""

from pydantic_settings import BaseSettings
from typing import List, Optional
import os
from pathlib import Path


class Settings(BaseSettings):
    """
    Configuración de la aplicación usando Pydantic Settings
    Lee automáticamente desde variables de entorno y archivo .env
    """
    
    # ═══════════════════════════════════════════════════════════
    # INFORMACIÓN DE LA APLICACIÓN
    # ═══════════════════════════════════════════════════════════
    
    PROJECT_NAME: str = "Sistema de Gestión de Pacientes"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "API para gestión de pacientes con migración MySQL → PostgreSQL"
    API_V1_PREFIX: str = "/api/v1"
    
    # ═══════════════════════════════════════════════════════════
    # ENTORNO
    # ═══════════════════════════════════════════════════════════
    
    ENVIRONMENT: str = "development"  # development, staging, production
    DEBUG: bool = True
    
    # ═══════════════════════════════════════════════════════════
    # POSTGRESQL (Base de datos principal)
    # ═══════════════════════════════════════════════════════════
    
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "secreto123"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "hospital"
    
    @property
    def POSTGRES_URI(self) -> str:
        """URL de conexión a PostgreSQL"""
        from urllib.parse import quote_plus
        password_encoded = quote_plus(self.POSTGRES_PASSWORD)
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:"
            f"{password_encoded}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    # ═══════════════════════════════════════════════════════════
    # MYSQL (Base de datos legacy - solo lectura)
    # ═══════════════════════════════════════════════════════════
    
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: str = "3306"
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "Prometeus.0"
    MYSQL_DATABASE: str = "test_api"
    
    @property
    def MYSQL_URI(self) -> str:
        """URL de conexión a MySQL"""
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )
    
    # ═══════════════════════════════════════════════════════════
    # CORS (Cross-Origin Resource Sharing)
    # ═══════════════════════════════════════════════════════════
    
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:5173"  # Vite default
    ]
    
    # ═══════════════════════════════════════════════════════════
    # SEGURIDAD
    # ═══════════════════════════════════════════════════════════
    
    SECRET_KEY: str = "tu-clave-secreta-super-segura-cambiar-en-produccion"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # ═══════════════════════════════════════════════════════════
    # LOGGING
    # ═══════════════════════════════════════════════════════════
    
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FILE: str = "logs/app.log"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # ═══════════════════════════════════════════════════════════
    # MIGRACIÓN
    # ═══════════════════════════════════════════════════════════
    
    MIGRATION_BATCH_SIZE: int = 100
    MIGRATION_LOG_FILE: str = "logs/migracion.log"
    
    # ═══════════════════════════════════════════════════════════
    # PAGINACIÓN
    # ═══════════════════════════════════════════════════════════
    
    DEFAULT_PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 100
    
    # ═══════════════════════════════════════════════════════════
    # RUTAS
    # ═══════════════════════════════════════════════════════════
    
    @property
    def BASE_DIR(self) -> Path:
        """Directorio base de la aplicación"""
        return Path(__file__).resolve().parent.parent.parent
    
    @property
    def LOGS_DIR(self) -> Path:
        """Directorio de logs"""
        logs_dir = self.BASE_DIR / "logs"
        logs_dir.mkdir(exist_ok=True)
        return logs_dir
    
    # ═══════════════════════════════════════════════════════════
    # DOCUMENTACIÓN DE LA API
    # ═══════════════════════════════════════════════════════════
    
    DOCS_URL: str = "/docs"
    REDOC_URL: str = "/redoc"
    OPENAPI_URL: str = "/openapi.json"
    
    # Deshabilitar docs en producción
    @property
    def docs_url(self) -> Optional[str]:
        return self.DOCS_URL if self.ENVIRONMENT != "production" else None
    
    @property
    def redoc_url(self) -> Optional[str]:
        return self.REDOC_URL if self.ENVIRONMENT != "production" else None
    
    @property
    def openapi_url(self) -> Optional[str]:
        return self.OPENAPI_URL if self.ENVIRONMENT != "production" else None
    
    # ═══════════════════════════════════════════════════════════
    # CONFIGURACIÓN DE PYDANTIC
    # ═══════════════════════════════════════════════════════════
    
    class Config:
        env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
        env_file_encoding = 'utf-8'
        case_sensitive = True


# Instancia global de configuración
settings = Settings()


# ═══════════════════════════════════════════════════════════
# FUNCIONES DE UTILIDAD
# ═══════════════════════════════════════════════════════════

def get_settings() -> Settings:
    """
    Función para obtener la configuración
    Útil para inyección de dependencias en FastAPI
    """
    return settings


def print_settings():
    """Imprime la configuración actual (sin datos sensibles)"""
    print("=" * 60)
    print(f"🚀 {settings.PROJECT_NAME} v{settings.VERSION}")
    print("=" * 60)
    print(f"Entorno: {settings.ENVIRONMENT}")
    print(f"Debug: {settings.DEBUG}")
    print(f"API Prefix: {settings.API_V1_PREFIX}")
    print(f"\n📊 PostgreSQL:")
    print(f"  Host: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
    print(f"  Database: {settings.POSTGRES_DB}")
    print(f"  User: {settings.POSTGRES_USER}")
    print(f"\n📊 MySQL (Legacy):")
    print(f"  Host: {settings.MYSQL_HOST}:{settings.MYSQL_PORT}")
    print(f"  Database: {settings.MYSQL_DATABASE}")
    print(f"  User: {settings.MYSQL_USER}")
    print(f"\n📝 Logs:")
    print(f"  Level: {settings.LOG_LEVEL}")
    print(f"  File: {settings.LOG_FILE}")
    print(f"\n🔄 Migración:")
    print(f"  Batch Size: {settings.MIGRATION_BATCH_SIZE}")
    print("=" * 60)