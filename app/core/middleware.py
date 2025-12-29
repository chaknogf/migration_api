# app/core/middleware.py
"""
Middlewares personalizados de la aplicación
"""

import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware para logging de todas las requests
    Registra método, path, tiempo de respuesta y status code
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable
    ) -> Response:
        # Timestamp de inicio
        start_time = time.time()
        
        # Obtener información de la request
        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"
        
        # Log de request
        logger.info(f"→ {method} {path} from {client_host}")
        
        # Procesar request
        try:
            response = await call_next(request)
            
            # Calcular tiempo de procesamiento
            process_time = time.time() - start_time
            
            # Agregar header con tiempo de procesamiento
            response.headers["X-Process-Time"] = str(process_time)
            
            # Log de response
            logger.info(
                f"← {method} {path} - Status: {response.status_code} - "
                f"Time: {process_time:.3f}s"
            )
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"✗ {method} {path} - Error: {str(e)} - "
                f"Time: {process_time:.3f}s"
            )
            raise


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware que agrega un ID único a cada request
    Útil para tracking y debugging
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable
    ) -> Response:
        import uuid
        
        # Generar ID único para la request
        request_id = str(uuid.uuid4())
        
        # Agregar a request state
        request.state.request_id = request_id
        
        # Procesar request
        response = await call_next(request)
        
        # Agregar header con request ID
        response.headers["X-Request-ID"] = request_id
        
        return response


class CORSHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware adicional para headers CORS personalizados
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable
    ) -> Response:
        response = await call_next(request)
        
        # Headers adicionales de seguridad
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        return response