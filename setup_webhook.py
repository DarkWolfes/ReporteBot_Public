# setup_webhook.py
import os
import asyncio
from telegram.ext import ApplicationBuilder
import logging

# Configuración de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configura tu Token y Webhook URL aquí
TOKEN = "7625899075:AAGVcYR16FVc_IwXKLy--EPOyXnHmmkiw9k"
WEBHOOK_URL = "https://reportebot-public.onrender.com"

async def main():
    if not TOKEN or not WEBHOOK_URL:
        logger.error("TOKEN o WEBHOOK_URL no están configurados. No se puede establecer el webhook.")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    logger.info(f"Estableciendo webhook en: {WEBHOOK_URL}")
    await application.bot.set_webhook(url=WEBHOOK_URL)
    logger.info("Webhook establecido correctamente.")

if __name__ == "__main__":
    asyncio.run(main())
