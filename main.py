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

# Tu Token de Telegram
TOKEN = "7625899075:AAGVcYR16FVc_IwXKLy--EPOyXnHmmkiw9k"

# --- Lógica de la Aplicación (tu código) ---
REPORTE, TIPO_REPORTE, UBICACION_REPORTE, DETALLES_REPORTE = range(4)

async def start(update: Update, context: CallbackContext) -> int:
    """Inicia la conversación y saluda al usuario."""
    await update.message.reply_text("¡Hola! Soy un bot de reportes. ¿En qué puedo ayudarte?")
    return ConversationHandler.END

async def handle_text(update: Update, context: CallbackContext) -> None:
    """Maneja los mensajes de texto genéricos."""
    await update.message.reply_text("No entiendo ese comando.")

# --- Inicialización de la Aplicación ---
app = Flask(__name__)
application = ApplicationBuilder().token(TOKEN).build()

# Agrega todos tus handlers aquí.
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# --- Handlers de Flask para el Webhook ---
@app.post(f"/")
async def webhook_handler():
    """Maneja las actualizaciones de Telegram."""
    if not TOKEN:
        abort(400)
    
    try:
        data = request.get_json(force=True)
        await application.process_update(Update.de_json(data, application.bot))
        return "ok"
    except Exception as e:
        logger.error(f"Error en el handler de webhook: {e}")
        abort(500)

@app.get("/")
def health_check():
    """Verifica si el servicio está activo."""
    return "OK"
