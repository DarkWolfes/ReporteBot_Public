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
# Render las cargará automáticamente si las configuras en su dashboard.
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
# Asegúrate de que los handlers coinciden con los que definiste arriba.
application.add_handler(CommandHandler("start", start))
# Aquí puedes agregar el resto de tus handlers, como ConversationHandler, etc.
# application.add_handler(ConversationHandler(...))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# --- Handlers de Flask para el Webhook ---
# El decorador '@app.post' es una forma moderna de '@app.route(methods=["POST"])'
@app.post("/")
async def webhook_handler():
    """Maneja las actualizaciones de Telegram."""
    if not TOKEN:
        logger.error("Token de Telegram no configurado.")
        abort(400)
    
    try:
        data = request.get_json(force=True)
        await application.update_queue.put(Update.de_json(data, application.bot))
        return "ok"
    except Exception as e:
        logger.error(f"Error en el handler de webhook: {e}")
        abort(500)

# El decorador '@app.get' es una forma moderna de '@app.route(methods=["GET"])'
@app.get("/")
def health_check():
    """Verifica si el servicio está activo."""
    return "OK"

# --- Lógica de arranque con Uvicorn ---
# Esta es la forma correcta de ejecutar código asíncrono una sola vez al arrancar.
# Uvicorn detectará esta función si se llama 'startup_event'
# o si se registra a través de un decorador. Esta es la forma más compatible.
async def startup_event():
    """Configura el webhook de Telegram."""
    if TOKEN and WEBHOOK_URL:
        logger.info("Configurando webhook...")
        await application.bot.set_webhook(url=WEBHOOK_URL)
        logger.info("Webhook configurado correctamente.")
    else:
        logger.error("No se pudo configurar el webhook: TOKEN o WEBHOOK_URL no definidos.")
        
# Registramos la función de inicio con Flask.
# Aunque el decorador "@app.before_serving" no funciona, puedes usar esto.
app.before_first_request(startup_event)

# El bloque if __name__ == "__main__": es para cuando ejecutas el archivo localmente
if __name__ == "__main__":
    # La mejor manera de ejecutar es usando el comando de inicio de Render
    # 'uvicorn main:app --host 0.0.0.0 --port 8000'
    # Por lo tanto, no es necesario un bloque de ejecución local complejo aquí
    logger.info("Ejecutando el script localmente. Usa el comando de Render para el despliegue.")
