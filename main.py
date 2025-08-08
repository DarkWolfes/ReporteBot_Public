# main.py
import os
import logging
from flask import Flask, request, abort
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    CallbackContext,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# --- Configuración y Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Variables de Entorno (o constantes) ---
# Se recomienda usar variables de entorno para los tokens.
TOKEN = os.getenv("TOKEN", "TU_TOKEN_AQUI")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://reportebot-public.onrender.com")

# --- Lógica de la Aplicación ---
# Define tus estados de conversación (si los tienes)
REPORTE, TIPO_REPORTE, UBICACION_REPORTE, DETALLES_REPORTE = range(4)

# Tus funciones de handlers aquí. Todas deben ser asíncronas.
async def start(update: Update, context: CallbackContext) -> int:
    """Inicia la conversación y saluda al usuario."""
    await update.message.reply_text("¡Hola! Soy un bot de reportes. ¿En qué puedo ayudarte?")
    return ConversationHandler.END

# Agrega aquí el resto de tus funciones de handlers. Por ejemplo:
async def handle_text(update: Update, context: CallbackContext) -> None:
    """Maneja los mensajes de texto genéricos."""
    await update.message.reply_text("No entiendo ese comando.")

# --- Inicialización de la Aplicación ---
# Crea la aplicación de Flask y de Telegram
app = Flask(__name__)
application = ApplicationBuilder().token(TOKEN).build()

# Agrega todos tus handlers.
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# --- Handlers de Flask para el Webhook ---
@app.post("/")
async def webhook_handler():
    """Maneja las actualizaciones de Telegram."""
    if not TOKEN:
        logger.error("Token de Telegram no configurado.")
        abort(400)
    
    try:
        data = request.get_json(force=True)
        # La forma asíncrona correcta de procesar la actualización
        await application.process_update(Update.de_json(data, application.bot))
        return "ok"
    except Exception as e:
        logger.error(f"Error en el handler de webhook: {e}")
        abort(500)

@app.get("/")
def health_check():
    """Verifica si el servicio está activo."""
    return "OK"

# --- BLOQUE DE INICIALIZACIÓN ASÍNCRONA ---
# Esta es la forma correcta de integrar una tarea de inicio asíncrona
# con un servidor ASGI como Uvicorn. Se registra una tarea al arranque del servidor.
async def startup_task():
    """Configura el webhook de Telegram de forma asíncrona."""
    if TOKEN and WEBHOOK_URL:
        logger.info("Configurando webhook...")
        try:
            await application.bot.set_webhook(url=WEBHOOK_URL)
            logger.info("Webhook configurado correctamente.")
        except Exception as e:
            logger.error(f"Error al configurar el webhook: {e}")
    else:
        logger.error("No se pudo configurar el webhook: TOKEN o WEBHOOK_URL no definidos.")

# Registramos la tarea de inicio en la aplicación de Flask
# Esta es la forma más compatible con Uvicorn para ejecutar una corrutina al inicio
@app.before_request
async def before_first_request_setup():
    if not hasattr(app, 'initialized'):
        await startup_task()
        app.initialized = True
