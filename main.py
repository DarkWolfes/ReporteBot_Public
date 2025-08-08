import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    CallbackContext,
    MessageHandler,
    filters,
)
import asyncio

# --- Configuración y Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Obtener variables de entorno (la forma segura)
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# --- Lógica del Bot y Handlers ---
# Define tus estados de conversación
REPORTE, TIPO_REPORTE, UBICACION_REPORTE, DETALLES_REPORTE = range(4)

async def start(update: Update, context: CallbackContext) -> int:
    """Inicia la conversación y saluda al usuario."""
    await update.message.reply_text("¡Hola! Soy un bot de reportes. ¿En qué puedo ayudarte?")
    return ConversationHandler.END

async def reportar(update: Update, context: CallbackContext) -> int:
    """Inicia la conversación de reporte."""
    await update.message.reply_text("Vamos a iniciar un reporte. Por favor, dime el tipo de reporte.")
    return TIPO_REPORTE

async def tipo_reporte(update: Update, context: CallbackContext) -> int:
    """Guarda el tipo de reporte y pide la ubicación."""
    tipo = update.message.text
    context.user_data['tipo_reporte'] = tipo
    await update.message.reply_text(f"Has seleccionado el tipo de reporte: {tipo}. Ahora, por favor, dime la ubicación.")
    return UBICACION_REPORTE

async def ubicacion_reporte(update: Update, context: CallbackContext) -> int:
    """Guarda la ubicación y pide los detalles."""
    ubicacion = update.message.text
    context.user_data['ubicacion_reporte'] = ubicacion
    await update.message.reply_text(f"Ubicación guardada: {ubicacion}. Por último, dime los detalles del reporte.")
    return DETALLES_REPORTE

async def detalles_reporte(update: Update, context: CallbackContext) -> int:
    """Guarda los detalles y finaliza la conversación."""
    detalles = update.message.text
    context.user_data['detalles_reporte'] = detalles
    
    # Aquí puedes procesar el reporte (ej. guardarlo en una base de datos, enviarlo a un canal, etc.)
    await update.message.reply_text(
        f"¡Reporte completado! Gracias por tu ayuda. Aquí está el resumen:\n"
        f"Tipo: {context.user_data['tipo_reporte']}\n"
        f"Ubicación: {context.user_data['ubicacion_reporte']}\n"
        f"Detalles: {detalles}"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancela la conversación de reporte."""
    await update.message.reply_text("El reporte ha sido cancelado.")
    return ConversationHandler.END

# --- Inicialización de la Aplicación ---
app = FastAPI()
application = ApplicationBuilder().token(TOKEN).build()

# Añade los handlers al bot
conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("reportar", reportar)],
    states={
        TIPO_REPORTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tipo_reporte)],
        UBICACION_REPORTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ubicacion_reporte)],
        DETALLES_REPORTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, detalles_reporte)],
    },
    fallbacks=[CommandHandler("cancelar", cancel)],
)

application.add_handler(CommandHandler("start", start))
application.add_handler(conversation_handler)

# --- Función para configurar el webhook al iniciar la aplicación ---
@app.on_event("startup")
async def startup_event():
    """Configura el webhook de Telegram de forma asíncrona al iniciar."""
    if TOKEN and WEBHOOK_URL:
        logger.info(f"Configurando webhook en: {WEBHOOK_URL}")
        try:
            # Aseguramos que la URL del webhook incluye el token
            await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
            logger.info("Webhook configurado correctamente.")
        except Exception as e:
            logger.error(f"Error al configurar el webhook: {e}")
    else:
        logger.error("No se pudo configurar el webhook: TOKEN o WEBHOOK_URL no definidos.")

# --- Ruta para el webhook de Telegram ---
@app.post(f"/{TOKEN}")
async def webhook_handler(request: Request):
    """Maneja las actualizaciones de Telegram."""
    if not TOKEN:
        return {"status": "error", "message": "Token de Telegram no configurado"}, 400

    try:
        data = await request.json()
        await application.process_update(Update.de_json(data, application.bot))
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error en el handler de webhook: {e}")
        return {"status": "error", "message": str(e)}, 500

# --- Ruta de "Health Check" ---
@app.get("/")
def health_check():
    """Verifica si el servicio está activo."""
    return "OK"
