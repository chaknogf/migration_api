"""
Script para ejecutar la aplicación
Útil para diferentes entornos y configuraciones
"""

import uvicorn
import sys
import os

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.core.logging import setup_logging

# Configurar logging
setup_logging()


def run_development():
    """Ejecutar en modo desarrollo"""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug",
        access_log=True
    )


def run_production():
    """Ejecutar en modo producción"""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=4,  # Múltiples workers
        log_level="info",
        access_log=True
    )


def run_test():
    """Ejecutar servidor de test"""
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        log_level="debug"
    )


if __name__ == "__main__":
    # Determinar modo según argumentos o variable de entorno
    mode = sys.argv[1] if len(sys.argv) > 1 else settings.ENVIRONMENT
    
    print(f"🚀 Iniciando servidor en modo: {mode}")
    
    if mode == "production":
        run_production()
    elif mode == "test":
        run_test()
    else:
        run_development()