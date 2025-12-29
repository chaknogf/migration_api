from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Verificar conexiones
    await verify_postgres_connection()
    await verify_mysql_connection()
    yield
    # Shutdown: Cerrar conexiones
    await close_connections()

app = FastAPI(lifespan=lifespan)