# main.py
import os
import logging
import asyncio
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

# Tus funciones de handlers aquí. Todas las funciones de PTB deben ser asíncronas.
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
# Aquí puedes agregar el resto de tus handlers, como ConversationHandler, etc.
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

# --- BLOQUE DE INICIALIZACIÓN SÍNCRONA ---
# Esta función se ejecutará una sola vez cuando el servidor se inicie.
# Al ser síncrona, no entra en conflicto con el bucle de eventos de Uvicorn.
def initialize_app():
    """Configura el webhook de Telegram de forma síncrona."""
    if TOKEN and WEBHOOK_URL:
        logger.info("Configurando webhook...")
        
        # Ejecuta la corrutina de forma síncrona
        async def setup_webhook():
            try:
                await application.bot.set_webhook(url=WEBHOOK_URL)
                logger.info("Webhook configurado correctamente.")
            except Exception as e:
                logger.error(f"Error al configurar el webhook: {e}")
        
        # Crea y ejecuta un bucle de eventos temporal para esta única tarea
        try:
            asyncio.run(setup_webhook())
        except RuntimeError as e:
            logger.warning(f"Bucle de eventos ya en ejecución. Intentando la configuración de otra forma: {e}")
            loop = asyncio.get_event_loop()
            loop.run_until_complete(setup_webhook())
    else:
        logger.error("No se pudo configurar el webhook: TOKEN o WEBHOOK_URL no definidos.")

# Llamamos a la función de inicialización aquí mismo.
# Esto se ejecuta una vez al cargar el módulo.
initialize_app()
