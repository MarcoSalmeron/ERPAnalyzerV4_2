from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from analyzer_services.app.api.routes import router
from analyzer_services.app.auth.google_auth import router as auth_router
import os
from fastapi.staticfiles import StaticFiles
import asyncio
import sys
from contextlib import asynccontextmanager
from agents.supervisor import team
from langgraph.checkpoint.memory import MemorySaver
import os
from pathlib import Path
from analyzer_services.app.auth.auth_service import auth_service


PLANTILLAS_DIR = Path(__file__).parent.parent.parent / "static" / "plantillas"
if not os.path.exists(PLANTILLAS_DIR):
    os.makedirs(PLANTILLAS_DIR)

REPORTS_DIR = Path(__file__).parent.parent.parent / "static" / "reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"
if not os.path.exists(REPORTS_DIR):
    os.makedirs(REPORTS_DIR)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---

    print("🚀 Inicializando LangGraph")
    memory = MemorySaver()
    app.state.oracle_graph = team.compile(checkpointer=memory)
    print("✅ LangGraph inicializado")

    # Login inicial JWT
    success = await auth_service.login()
    if success:
        print("✅ Autenticación JWT inicializada")
    else:
        print("⚠️ Advertencia: No se pudo autenticar con el servicio externo")
    yield
    # --- SHUTDOWN ---
    print("🛑 Cerrando aplicación")


services = FastAPI(
    title="Oracle Cloud InsightReadinesss API",
    description="API para el análisis de Oracle Cloud Readiness",
    version="1.0.0",
    lifespan=lifespan,
)

services.mount("/static/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
services.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])
# Incluir rutas de la API
services.include_router(router)
services.include_router(auth_router, prefix="/api")
services.mount("/static/plantillas", StaticFiles(directory=PLANTILLAS_DIR), name="plantillas")
@services.get("/api/plantillas")
def list_plantillas():
    """Lista todos los archivos en el directorio de plantillas"""
    try:
        files = [f.name for f in PLANTILLAS_DIR.iterdir() if f.is_file()]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@services.get("/")
def read_root():
    return {"message": "API de Oracle Cloud Readiness"}
