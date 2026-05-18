# routes.py
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request
from analyzer_services.app.models.schemas import AnalysisRequest
from analyzer_services.app.process.Tasks_analyzer import run_oracle_analysis, active_threads
from analyzer_services.app.process.ConnectionManager import manager
import uuid
import asyncio

from schemas.schemas import ERPState
from analyzer_services.app.state import pending_responses

router = APIRouter(prefix="/impact", tags=["Impact"])

@router.post("/resume/{thread_id}")
async def resume_flow(thread_id: str, data: ERPState):
    print(f"📥 Endpoint /resume/{thread_id} llamado con: {data}")
    pending_responses[thread_id] = data.erp_module
    print(f"💾 pending_responses[{thread_id}] = {data.erp_module}")
    print(f"📋 Estado actual de pending_responses: {list(pending_responses.keys())}")
    return {"status": "ok", "thread_id": thread_id}


@router.post("/analyze")
async def start_analysis(request: AnalysisRequest, http_request: Request):
    oracle_app = http_request.app.state.oracle_graph

    # Si el frontend envía un thread_id y hay una tarea activa → reinyectar mensaje
    if request.thread_id and request.thread_id in active_threads:
        pending_responses[request.thread_id] = request.query
        return {"thread_id": request.thread_id, "message": "Mensaje enviado al flujo activo"}

        # Crear nuevo thread_id o reusar el del request
    thread_id = request.thread_id or f"oracle_project_{uuid.uuid4().hex[:8]}"
    print(f"🆔 /analyze creó thread_id: {thread_id}")

    asyncio.create_task(run_oracle_analysis(thread_id, request.query, oracle_app))
    return {"thread_id": thread_id, "message": "Análisis en curso..."}


@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    await manager.connect(websocket, thread_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data and data.strip():
                # Mensajes del usuario enviados por WebSocket → reinyectar al flujo
                pending_responses[thread_id] = data.strip()
    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)

