from analyzer_services.app.process.ConnectionManager import manager
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.errors import GraphInterrupt
from analyzer_services.app.state import pending_responses
from tools.Tools import tool_pdf_a_excel_base64, tool_obtener_config_bot
from analyzer_services.app.auth.auth_service import auth_service
import httpx
from common.common_utl import get_embeddings_model
import asyncio
import logging
import os

active_threads: set = set()

# ===============================
# LOGGING
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

##memory = MemorySaver()
##oracle_app = team.compile(checkpointer=checkpointer)
get_embeddings_model()


# --- Función de Ejecución del Grafo (Lógica Pesada) ---
async def run_oracle_analysis(thread_id: str, query: str, oracle_app):
    active_threads.add(thread_id)

    await asyncio.sleep(2)
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [HumanMessage(content=query)]}
    print(f"🚀 run_oracle_analysis iniciado con thread_id: {thread_id}")

    try:
        step_agent = 1
        await manager.send_update(thread_id, {
            "step": step_agent,
            "agent": "supervisor",
            "status": "active",
            "log": "Iniciando orquestación..."
        })

        while True:
            try:
                async for event in oracle_app.astream(inputs, config=config, stream_mode="values"):
                    if "messages" in event:
                        last_msg = event["messages"][-1]
                        if hasattr(last_msg, 'content') and "ERROR_VERSION" in str(last_msg.content):
                            await manager.send_update(thread_id, {
                                "type": "error",  # error para el frontend
                                "agent": "investigador",
                                "content": last_msg.content
                            })
                        if hasattr(last_msg, 'name') and last_msg.name:
                            agent_name = last_msg.name.lower()
                            logger.info(f"Detección de agente: {agent_name}")
                            steps = {"transfer_back_to_supervisor": 1, "transfer_to_investigador": 2,
                                     "transfer_to_analista": 3, "transfer_to_redactor": 4}
                            current_step = steps.get(agent_name, 1)
                            await manager.send_update(thread_id, {
                                "step": current_step,
                                "agent": agent_name,
                                "status": "active",
                                "content": last_msg.content,
                                "log": f"Ejecutando tareas de {agent_name}..."
                            })

                            if agent_name == "transfer_to_investigador":
                                await manager.send_update(thread_id, {
                                    "type": "info",
                                    "agent": "investigador",
                                    "content": "Esta versión no se encuentra en la base de datos. El Investigador está obteniendo la información desde Oracle Cloud Readiness. Este proceso puede tardar varios minutos..."
                                })

                        if hasattr(last_msg, 'content') and "ESPERAR_COLA" in str(last_msg.content):
                            await manager.send_update(thread_id, {
                                "type": "info",
                                "agent": "analista",
                                "content": "Esta versión ya está siendo investigada en este momento. Por favor espera mientras se obtiene la información..."
                            })

                state = await oracle_app.aget_state(config)

                # ── Grafo pausado esperando input del usuario ──
                if state.next:
                    mensajes = state.values.get("messages", [])
                    pregunta = next(
                        (msg.content for msg in reversed(mensajes) if isinstance(msg, AIMessage)),
                        "Por favor responde para continuar."
                    )
                    logger.info(f"Interrupción genérica del supervisor: {pregunta}")
                    await manager.send_update(thread_id, {
                        "type": "interrupt",
                        "agent": "supervisor",
                        "content": pregunta
                    })
                    while thread_id not in pending_responses:
                        await asyncio.sleep(0.5)
                    respuesta = pending_responses.pop(thread_id)
                    print(f"📤 Recuperado de pending_responses[{thread_id}]: {respuesta}")

                    # Reinyectar como HumanMessage — sin asumir qué campo actualizar
                    inputs = {"messages": [HumanMessage(content=respuesta)]}
                    continue

                    # ── Verificar si terminó ─────
                if not state.next:

                    filename = f"reporte_{thread_id}.pdf"
                    pdf_path = f"./reports/{filename}"

                    if os.path.exists(pdf_path):
                        # ── 1. Enviar el PDF al frontend ──────────────────────────
                        await manager.send_update(thread_id, {
                            "step": 4,
                            "agent": "redactor",
                            "status": "completed",
                            "pdf_ready": True,
                            "pdf_url": f"/static/reports/{filename}"
                        })

                        # ── 2. Interrupt: preguntar sobre pruebas de regresión ────
                        await manager.send_update(thread_id, {
                            "type": "interrupt",
                            "agent": "system",
                            "content": "¿Deseas generar un plan de pruebas de regresión para los impactos detectados? (Sí / No)"
                        })

                        # ── 3. Esperar respuesta del usuario ──────────────────────
                        while thread_id not in pending_responses:
                            await asyncio.sleep(0.5)
                        respuesta_regresion = pending_responses.pop(thread_id)
                        logger.info(f"📋 Respuesta pruebas de regresión: {respuesta_regresion}")

                        # ── 4. Procesar respuesta y notificar al frontend ─────────
                        if respuesta_regresion.strip().lower() in ("sí", "si", "s", "yes", "y"):

                            try:
                                # 1. Convertir PDF a Excel en base64
                                excel_data = tool_pdf_a_excel_base64.invoke({"thread_id": thread_id})

                                # 2. Obtener config del bot
                                nombre_bot = pending_responses.get(f"{thread_id}_bot", "Envio de correo Marco")
                                config_bot = tool_obtener_config_bot.invoke({"nombre_bot": nombre_bot})

                                # 3. body
                                body = {
                                    "bot_name": config_bot["nombre_bot"],
                                    "execute_bot": config_bot["execute_bot"],
                                    "agent_name": config_bot["nombre_agente"],
                                    "execution_variables": {
                                        "vArchivoBase64": excel_data["content"],
                                        "vTipoArchivo": excel_data["tipo"]
                                    }
                                }

                                # 4. Obtener token JWT y hacer POST
                                token = await auth_service.get_token()
                                endpoint = config_bot["endpoint"]

                                async with httpx.AsyncClient() as client:
                                    resp = await client.post(
                                        endpoint,
                                        json=body,
                                        headers={
                                            "Content-Type": "application/json",
                                            "Authorization": f"Bearer {token}"
                                        }
                                    )

                                if resp.status_code == 200:
                                    await manager.send_update(thread_id, {
                                        "type": "info",
                                        "agent": "system",
                                        "content": f"Pruebas de regresión iniciadas correctamente en {config_bot['nombre_bot']}."
                                    })
                                else:
                                    await manager.send_update(thread_id, {
                                        "type": "info",
                                        "agent": "system",
                                        "content": f"Error al iniciar pruebas: {resp.status_code} - {resp.text}"
                                    })
                            except Exception as e:
                                logger.error(f"Error ejecutando pruebas de regresión: {e}")
                                await manager.send_update(thread_id, {
                                    "type": "info",
                                    "agent": "system",
                                    "content": f"Error técnico al ejecutar pruebas: {str(e)}"
                                })
                        else:
                            await manager.send_update(thread_id, {
                                "type": "info",
                                "agent": "system",
                                "content": "De acuerdo. El reporte está listo para su revisión."
                            })

                else:
                    # ── Respuesta conversacional → NO cerrar, esperar siguiente mensaje ──
                    mensajes = state.values.get("messages", [])
                    ultimo_msg = next((msg.content for msg in reversed(mensajes) if isinstance(msg, AIMessage)), None)

                    if ultimo_msg:
                        await manager.send_update(thread_id, {

                            "type": "chat",

                            "agent": "supervisor",

                            "content": ultimo_msg

                        })

                    # Esperar el siguiente mensaje del usuario
                    while thread_id not in pending_responses:
                        await asyncio.sleep(0.5)

                    respuesta = pending_responses.pop(thread_id)

                    inputs = {"messages": [HumanMessage(content=respuesta)]}

                    continue

            except GraphInterrupt as gi:

                try:

                    pregunta = gi.args[0].value

                except Exception:

                    pregunta = str(gi)

                await manager.send_update(thread_id, {

                    "type": "interrupt",

                    "agent": "system",

                    "content": pregunta

                })

            while thread_id not in pending_responses:
                await asyncio.sleep(0.5)

            respuesta = pending_responses.pop(thread_id)

            inputs = {"messages": [HumanMessage(content=respuesta)]}

            continue

    except Exception as e:
        logger.error(f"Error en el flujo de trabajo: {str(e)}")
        await manager.send_update(thread_id, {"error": str(e)})

    finally:
        active_threads.discard(thread_id)