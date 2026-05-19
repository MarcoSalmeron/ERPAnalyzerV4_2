from analyzer_services.app.process.ConnectionManager import manager
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.errors import GraphInterrupt
from analyzer_services.app.state import pending_responses
from tools.Tools import tool_xlsx_a_base64, tool_obtener_config_bot
from analyzer_services.app.auth.auth_service import auth_service
import httpx
from common.common_utl import get_embeddings_model
import asyncio
import logging
import base64
from pathlib import Path
import uuid
import os
from PIL import Image
import io

# ===============================
# LOGGING
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path(__file__).parent.parent.parent.parent / "static" / "reports"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

##memory = MemorySaver()
##oracle_app = team.compile(checkpointer=checkpointer)
get_embeddings_model()


# --- Función de Ejecución del Grafo (Lógica Pesada) ---
async def run_oracle_analysis(thread_id: str, query: str, oracle_app):
    await asyncio.sleep(2)
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [HumanMessage(content=query)]}
    print(f"🚀 run_oracle_analysis iniciado con thread_id: {thread_id}")

    #Flag para la bienvenida
    welcome_done = False
    # Flag para la selección del módulo
    module_selected = False

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
                # ── NUEVO: Bienvenida (HITL #1) ──────────────────────────
                if not welcome_done:
                    await manager.send_update(thread_id, {
                        "type": "interrupt",
                        "agent": "supervisor",
                        "content": "¡Hola! Soy el Director de Consultoría de Oracle Cloud. ¿Qué deseas realizar?\n\n1. Análisis de Impacto\n2. Pruebas de Regresión"
                    })
                    while thread_id not in pending_responses:
                        await asyncio.sleep(0.5)
                    eleccion = pending_responses.pop(thread_id).strip().lower()

                    if any(x in eleccion for x in ("2", "regresion", "regresión", "prueba", "pruebas")):
                        await manager.send_update(thread_id, {
                            "type": "info",
                            "agent": "supervisor",
                            "content": "Para ejecutar pruebas de regresión, descarga las plantillas (en el panel derecho) y adjúntalas usando el botón 📎 al lado del input del chat."
                        })
                        await manager.send_update(thread_id, {
                            "type": "interrupt",
                            "agent": "supervisor",
                            "content": "Cuando tengas el archivo listo, adjúntalo y presiona enviar."
                        })
                        # Esperar el archivo del usuario (mismo thread_id)
                        while thread_id not in pending_responses:
                            await asyncio.sleep(0.5)

                        # Procesar archivo
                        try:
                            # 1. Convertir Xlsx en base64
                            file_path = pending_responses.pop(f"{thread_id}_file_path", None)
                            if not file_path:
                                await manager.send_update(thread_id, {
                                    "type": "info", "agent": "system",
                                    "content": "No se recibió ningún archivo adjunto. Por favor adjunta el archivo xlsx."
                                })
                                break

                            excel_data = tool_xlsx_a_base64.invoke({"file_path": file_path})

                            # 2. Obtener config del bot
                            nombre_bot = pending_responses.get(f"{thread_id}_bot", "Bot Facturas")
                            config_bot = tool_obtener_config_bot.invoke({"nombre_bot": nombre_bot})

                            # 3. Body con nuevo formato
                            body = {
                                "bot_name": config_bot["nombre_bot"],
                                "execute_bot": config_bot["execute_bot"],
                                "agent_name": config_bot["nombre_agente"],
                                "execution_variables": {
                                    "vExcelBase64": excel_data["content"],  # ← clave nueva
                                    "vTipoArchivo": "xlsx"  # ← siempre xlsx
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

                                # 1. Capturar execution_id
                                bot_response = resp.json()
                                execution_id = bot_response.get("execution_id")

                                await manager.send_update(thread_id, {
                                    "type": "info",
                                    "agent": "system",
                                    "content": "Bot iniciado. Esperando 5 minutos para verificar resultados..."
                                })

                                # 2. Esperar 5 minutos
                                await asyncio.sleep(300)

                                # 3. Polling hasta status == "completed"
                                screenshots_endpoint = f"https://boot-app.i-condor.com/api/executions/{execution_id}/screenshots"
                                screenshots = []
                                max_retries = 20  # máximo ~10 minutos adicionales con 30s de intervalo

                                for _ in range(max_retries):
                                    async with httpx.AsyncClient() as poll_client:
                                        poll_resp = await poll_client.get(
                                            screenshots_endpoint,
                                            headers={"Authorization": f"Bearer {token}"}
                                        )
                                    poll_data = poll_resp.json()
                                    status = poll_data.get("execution", {}).get("status", "").lower()

                                    if status == "completed":
                                        screenshots = poll_data.get("screenshots", [])
                                        break

                                    await asyncio.sleep(30)  # reintentar cada 30 segundos

                                if screenshots:
                                    screenshot_urls = []
                                    for screenshot in screenshots:
                                        b64_str = screenshot.get("data")  # ← campo correcto del dict
                                        if not b64_str:
                                            continue

                                        filename = screenshot.get(
                                            "filename") or f"screenshot_{execution_id}_{uuid.uuid4().hex[:8]}.png"
                                        filepath = SCREENSHOTS_DIR / filename
                                        img_bytes = base64.b64decode(b64_str)
                                        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

                                        # Forzar extensión .jpg
                                        filename = (screenshot.get(
                                            "filename") or f"screenshot_{execution_id}_{uuid.uuid4().hex[:8]}").rsplit(
                                            ".", 1)[0] + ".jpg"
                                        img.save(filepath, "JPEG", quality=85)
                                        screenshot_urls.append(f"/static/reports/{filename}")

                                    await manager.send_update(thread_id, {
                                        "type": "screenshots",
                                        "agent": "system",
                                        "content": f"Ejecución completada. {len(screenshot_urls)} captura(s) disponible(s).",
                                        "screenshots": screenshot_urls
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
                        finally:
                            await manager.close_connection(thread_id)
                            break

                    welcome_done = True
                    continue  # vuelve al inicio del while → ahora entra al astream

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

                # ── Pedir módulo si no se seleccionó (HITL #2)──
                if not module_selected:
                    mensajes = state.values.get("messages", [])
                    pregunta = None
                    for msg in reversed(mensajes):
                        if isinstance(msg, AIMessage):
                            pregunta = msg.content
                            break
                    if pregunta is None:
                        pregunta = "Por favor selecciona el módulo ERP que deseas analizar."

                    logger.info(f"Pregunta inicial del supervisor: {pregunta}")
                    await manager.send_update(thread_id, {
                        "type": "interrupt",
                        "agent": "supervisor",
                        "content": pregunta
                    })
                    # Esperar respuesta en pending_responses...
                    while thread_id not in pending_responses:
                        await asyncio.sleep(0.5)
                    respuesta = pending_responses.pop(thread_id)
                    print(f"📤 Recuperado de pending_responses[{thread_id}]: {respuesta}")

                    await oracle_app.aupdate_state(config, {"erp_module": respuesta})
                    inputs = {"messages": [HumanMessage(content=respuesta)]}
                    module_selected = True

                    continue

                # ── Verificar si terminó ─────
                if not state.next:
                    # ── 1. Enviar el PDF al frontend ──────────────────────────
                    filename = f"reporte_{thread_id}.pdf"
                    await manager.send_update(thread_id, {
                        "step": 4,
                        "agent": "redactor",
                        "status": "completed",
                        "pdf_ready": True,
                        "pdf_url": f"/static/reports/{filename}"
                    })

                    # ── 2. Interrupt: preguntar sobre pruebas de regresión (HITL #3)────
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
                            # 1. Convertir Xlsx en base64
                            file_path = pending_responses.pop(f"{thread_id}_file_path", None)
                            if not file_path:
                                await manager.send_update(thread_id, {
                                    "type": "info", "agent": "system",
                                    "content": "No se recibió ningún archivo adjunto. Por favor adjunta el archivo xlsx."
                                })
                                break

                            excel_data = tool_xlsx_a_base64.invoke({"file_path": file_path})

                            # 2. Obtener config del bot
                            nombre_bot = pending_responses.get(f"{thread_id}_bot", "Bot Facturas")
                            config_bot = tool_obtener_config_bot.invoke({"nombre_bot": nombre_bot})

                            # 3. Body con nuevo formato
                            body = {
                                "bot_name": config_bot["nombre_bot"],
                                "execute_bot": config_bot["execute_bot"],
                                "agent_name": config_bot["nombre_agente"],
                                "execution_variables": {
                                    "vExcelBase64": excel_data["content"],  # ← clave nueva
                                    "vTipoArchivo": "xlsx"  # ← siempre xlsx
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

                        # ── 5. Cerrar conexión ────────────────────────────────────
                    await manager.close_connection(thread_id)
                    break

                continue

            except GraphInterrupt as gi:
                # Manejo de interrupciones provenientes del grafo
                try:
                    pregunta = gi.args[0].value
                except Exception:
                    pregunta = str(gi)
                logger.info(f"🤖 Interrupción capturada: {pregunta}")
                await manager.send_update(thread_id, {
                    "type": "interrupt",
                    "agent": "system",
                    "content": pregunta
                })
                while thread_id not in pending_responses:
                    await asyncio.sleep(0.5)
                respuesta = pending_responses.pop(thread_id)
                print(f"📤 Recuperado de pending_responses[{thread_id}]: {respuesta}")
                await oracle_app.aupdate_state(config, {"erp_module": respuesta})
                new_state = await oracle_app.aget_state(config)
                logger.info(f"📊 Estado actualizado: {new_state.values}")
                inputs = {"messages": [HumanMessage(content=respuesta)]}
                # Si la interrupción provino del sistema y aún no se había seleccionado módulo, marcarlo
                if not module_selected:
                    module_selected = True
                # Volver a procesar astream con la nueva entrada
                continue

    except Exception as e:
        logger.error(f"Error en el flujo de trabajo: {str(e)}")
        await manager.send_update(thread_id, {"error": str(e)})
