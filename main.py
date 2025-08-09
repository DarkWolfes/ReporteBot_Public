# -*- coding: utf-8 -*-

import os
import sys
import logging
import asyncio
from dotenv import load_dotenv
from google.cloud import firestore
from firebase_admin import credentials, initialize_app
from telegram import (
    Update,
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    MenuButtonWebApp,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    Updater,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram import LabeledPrice, ShippingOption, ShippingQuery, ChosenInlineResult

from datetime import datetime, time, date, timedelta
import pytz
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
import random
import re
from typing import Dict, List
import string
import json

from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager

# Constantes de los estados del ConversationHandler
REGISTER_NAME, REGISTER_EMAIL, REGISTER_BIRTHDAY, REGISTER_GENDER = range(4)
REPORT_ISSUE, REPORT_DETAILS, REPORT_PHOTO, REPORT_LOCATION, REPORT_FINAL = range(5)
REPORT_TYPE, REPORT_DATE, REPORT_TIME, REPORT_DESCRIPTION = range(4)
MAIN_MENU, REPORT_MENU = range(2)
ASK_LOCATION, GET_LOCATION = range(2)
# Constantes del estado de la conversación para la creación de eventos
EVENT_NAME, EVENT_DATE, EVENT_TIME, EVENT_LOCATION, EVENT_DESCRIPTION = range(5)
# Estado del ConversationHandler para la encuesta
POLL_QUESTION, POLL_OPTIONS = range(2)
# Estado para la conversación de enviar un mensaje a todos los usuarios
BROADCAST_MESSAGE = range(1)
# Estado para el menú de administrador
ADMIN_MENU, ADMIN_BROADCAST = range(2)
# Estado para la conversación de feedback
FEEDBACK_TEXT, FEEDBACK_CONFIRMATION = range(2)
# Estado para la conversación de reporte de errores
BUG_DESCRIPTION, BUG_REPRODUCE, BUG_CONTACT, BUG_CONFIRMATION = range(4)
# Estado para la conversación de contacto
CONTACT_NAME, CONTACT_EMAIL, CONTACT_MESSAGE, CONTACT_CONFIRMATION = range(4)
# Estado para la conversación de suscripción
SUBSCRIBE_CONFIRMATION = range(1)
# Estado para la conversación de desuscripción
UNSUBSCRIBE_CONFIRMATION = range(1)
# Estado para la conversación de consulta de estado de reportes
CHECK_STATUS_ID, CHECK_STATUS_CONFIRMATION = range(2)
# Estado para la conversación de creación de eventos
CREATE_EVENT_NAME, CREATE_EVENT_DATE, CREATE_EVENT_TIME, CREATE_EVENT_LOCATION, CREATE_EVENT_DESCRIPTION = range(5)
# Estado para la conversación de encuestas
POLL_QUESTION, POLL_OPTIONS_INPUT = range(2)
# Estado para la conversación de recordatorios
REMINDER_TEXT, REMINDER_DATE, REMINDER_TIME = range(3)
# Estado para la conversación de webapps
WEBAPP_START = range(1)

# Cargar variables de entorno
load_dotenv()

# Configura las variables de entorno para FastAPI y PTB
TOKEN = os.environ.get("TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# Habilitar el registro
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Instancia global de la aplicación de Telegram
application = None

# --- CONFIGURACIÓN DE FIRESTORE ---

try:
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        cred = credentials.Certificate(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    else:
        cred = None
        logger.info("Usando credenciales predeterminadas de la aplicación de Google.")

    if not cred:
        initialize_app()
    else:
        initialize_app(cred)

    db = firestore.Client()
    logger.info("Cliente de Firestore inicializado correctamente.")
except Exception as e:
    logger.error(f"Error al inicializar Firestore: {e}")
    sys.exit(1)


# --- FUNCIONES DE GESTIÓN DE USUARIOS Y REPORTES ---

async def get_user_data(user_id: int) -> Dict:
    user_ref = db.collection('users').document(str(user_id))
    user_doc = await asyncio.to_thread(user_ref.get)
    return user_doc.to_dict() if user_doc.exists else None

async def is_admin(user_id: int) -> bool:
    user_data = await get_user_data(user_id)
    return user_data and user_data.get('is_admin', False)

async def check_user_registered(user_id: int) -> bool:
    user_ref = db.collection('users').document(str(user_id))
    user_doc = await asyncio.to_thread(user_ref.get)
    return user_doc.exists

async def add_report_to_db(report_data: Dict, user_id: int):
    reports_ref = db.collection('reports')
    report_data['user_id'] = user_id
    report_data['timestamp'] = datetime.now(pytz.timezone('Europe/Madrid'))
    await asyncio.to_thread(reports_ref.add, report_data)

# --- HANDLERS DEL BOT Y LÓGICA DE CONVERSACIÓN ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data = await get_user_data(user_id)

    if user_data:
        await update.message.reply_text(
            f"¡Hola de nuevo, {user_data.get('name')}! ¿En qué puedo ayudarte hoy?"
        )
    else:
        keyboard = [
            [InlineKeyboardButton("Registrarme", callback_data="register")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "¡Hola! Bienvenido al bot de gestión de informes. Para usar todas las funciones, por favor, regístrate.",
            reply_markup=reply_markup
        )
    return MAIN_MENU

async def register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Genial, ¡vamos a registrarte! ¿Cuál es tu nombre?")
    return REGISTER_NAME

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text
    context.user_data['name'] = name
    await update.message.reply_text(f"¡Hola, {name}! Por favor, dime tu correo electrónico.")
    return REGISTER_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text
    context.user_data['email'] = email
    
    await asyncio.to_thread(db.collection('users').document(str(update.effective_user.id)).set, context.user_data)

    await update.message.reply_text("¡Gracias! Tus datos han sido guardados.")
    return ConversationHandler.END

async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para reportar un problema."""
    await update.message.reply_text("Por favor, describe brevemente el problema que quieres reportar.")
    return REPORT_DETAILS

async def report_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda los detalles del reporte y finaliza."""
    report = update.message.text
    
    report_data = {'report_text': report}
    await add_report_to_db(report_data, update.effective_user.id)
    
    await update.message.reply_text("Gracias por tu reporte. Lo revisaremos pronto.")
    return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela cualquier conversación en curso."""
    await update.message.reply_text("Operación cancelada.")
    return ConversationHandler.END

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await is_admin(update.effective_user.id):
        await update.message.reply_text("No tienes permisos de administrador.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Enviar mensaje a todos", callback_data="broadcast")],
        [InlineKeyboardButton("Ver reportes", callback_data="view_reports")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Menú de administrador:", reply_markup=reply_markup)
    return ADMIN_MENU

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Por favor, escribe el mensaje que quieres enviar a todos los usuarios.")
    return ADMIN_BROADCAST

async def admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_to_send = update.message.text
    users_ref = db.collection('users')
    users_docs = await asyncio.to_thread(users_ref.stream)
    
    for user_doc in users_docs:
        try:
            await context.bot.send_message(chat_id=user_doc.id, text=message_to_send)
        except Exception as e:
            logger.error(f"Error al enviar mensaje a {user_doc.id}: {e}")

    await update.message.reply_text("Mensaje enviado a todos los usuarios.")
    return ConversationHandler.END

async def ask_location_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_user_registered(update.effective_user.id):
        await update.message.reply_text("Por favor, regístrate primero usando /start.")
        return ConversationHandler.END

    keyboard = [[KeyboardButton("Compartir mi ubicación", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Por favor, comparte tu ubicación para que pueda ayudarte a encontrar servicios cercanos.",
        reply_markup=reply_markup
    )
    return GET_LOCATION

async def get_location_and_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    location = update.message.location
    latitud = location.latitude
    longitud = location.longitude

    await update.message.reply_text(
        f"Tu ubicación es: Latitud {latitud}, Longitud {longitud}. Estoy buscando servicios cercanos...",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def event_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Por favor, introduce el nombre del evento:")
    return EVENT_NAME

async def event_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_name_text = update.message.text
    context.user_data['event_name'] = event_name_text
    await update.message.reply_text("¿Cuál es la fecha del evento? (Ej: 2025-10-27)")
    return EVENT_DATE

async def event_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_date_text = update.message.text
    context.user_data['event_date'] = event_date_text
    await update.message.reply_text("¿A qué hora será el evento? (Ej: 18:30)")
    return EVENT_TIME

async def event_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_time_text = update.message.text
    context.user_data['event_time'] = event_time_text
    await update.message.reply_text("¿Dónde se celebrará el evento?")
    return EVENT_LOCATION

async def event_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_location_text = update.message.text
    context.user_data['event_location'] = event_location_text
    await update.message.reply_text("Por último, introduce una descripción del evento:")
    return EVENT_DESCRIPTION

async def create_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text
    context.user_data['event_description'] = description
    
    event_data = context.user_data
    event_data['created_by'] = update.effective_user.id
    await asyncio.to_thread(db.collection('events').add, event_data)
    
    await update.message.reply_text(
        f"Evento '{event_data['event_name']}' creado con éxito. ¡Gracias!"
    )
    return ConversationHandler.END

async def start_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("¿Cuál es la pregunta de la encuesta?")
    return POLL_QUESTION

async def poll_options_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    question = update.message.text
    context.user_data['poll_question'] = question
    await update.message.reply_text("Ahora, introduce las opciones de la encuesta separadas por comas.")
    return POLL_OPTIONS_INPUT

async def create_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    options_text = update.message.text
    options = [opt.strip() for opt in options_text.split(',')]
    
    await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=context.user_data['poll_question'],
        options=options,
        is_anonymous=False
    )
    await update.message.reply_text("Encuesta creada con éxito.")
    return ConversationHandler.END

async def send_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Por favor, escribe el mensaje que quieres enviar a todos los usuarios:")
    return BROADCAST_MESSAGE

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_to_send = update.message.text
    users_ref = db.collection('users')
    users_docs = await asyncio.to_thread(users_ref.stream)
    
    for user_doc in users_docs:
        try:
            await context.bot.send_message(chat_id=user_doc.id, text=message_to_send)
        except Exception as e:
            logger.error(f"Error al enviar mensaje a {user_doc.id}: {e}")
            
    await update.message.reply_text("Mensaje enviado a todos los usuarios.")
    return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    is_registered = await check_user_registered(user_id)
    
    if not is_registered:
        keyboard = [[InlineKeyboardButton("Registrarme", callback_data="register")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Por favor, regístrate para acceder a las funciones.", reply_markup=reply_markup)
        return MAIN_MENU

    keyboard = [
        [InlineKeyboardButton("Reportar Incidencia", callback_data="report_menu")],
        [InlineKeyboardButton("Consultar Estado", callback_data="check_status")],
    ]
    if await is_admin(user_id):
        keyboard.append([InlineKeyboardButton("Panel de Administrador", callback_data="admin_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Elige una opción del menú principal:", reply_markup=reply_markup)
    return MAIN_MENU

async def report_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Describir Incidencia", callback_data="start_report")],
        [InlineKeyboardButton("Adjuntar Foto", callback_data="attach_photo")],
        [InlineKeyboardButton("Compartir Ubicación", callback_data="share_location")],
        [InlineKeyboardButton("Volver al Menú Principal", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Elige una opción para tu reporte:", reply_markup=reply_markup)
    return REPORT_MENU

# --- CONFIGURACIÓN DE FASTAPI Y LIFESPAN ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Función de lifespan para FastAPI. Se ejecuta al iniciar la app.
    Aquí inicializamos el bot y configuramos el webhook.
    """
    global application
    logger.info("Iniciando aplicación FastAPI...")
    try:
        application = ApplicationBuilder().token(TOKEN).updater(None).build()

        # Carga todos los manejadores del bot
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(register_callback, pattern='^register$'))
        
        # Handlers de conversación
        register_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(register_callback, pattern='^register$')],
            states={
                REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
                REGISTER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(register_handler)

        report_handler = ConversationHandler(
            entry_points=[CommandHandler('report', report_start)],
            states={
                REPORT_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_details)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(report_handler)

        admin_handler = ConversationHandler(
            entry_points=[CommandHandler('admin', admin_start)],
            states={
                ADMIN_MENU: [CallbackQueryHandler(admin_broadcast_callback, pattern='^broadcast$')],
                ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_message)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(admin_handler)

        location_handler = ConversationHandler(
            entry_points=[CommandHandler('location', ask_location_start)],
            states={
                GET_LOCATION: [MessageHandler(filters.LOCATION, get_location_and_search)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(location_handler)

        event_handler = ConversationHandler(
            entry_points=[CommandHandler('create_event', event_name)],
            states={
                EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_date)],
                EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_time)],
                EVENT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_location)],
                EVENT_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_description)],
                EVENT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_event)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(event_handler)

        poll_handler = ConversationHandler(
            entry_points=[CommandHandler('poll', start_poll)],
            states={
                POLL_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, poll_options_input)],
                POLL_OPTIONS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_poll)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(poll_handler)

        logger.info("Manejadores del bot cargados.")

        # Establece la URL del webhook en Telegram
        await application.bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook configurado en la URL: {WEBHOOK_URL}")

        yield
    except Exception as e:
        logger.error(f"Error durante la inicialización de la aplicación: {e}")
        sys.exit(1)
    finally:
        logger.info("Apagando aplicación FastAPI...")

app = FastAPI(lifespan=lifespan)

@app.post("/")
async def webhook_handler(request: Request):
    global application
    if application is None:
        logger.error("La aplicación de Telegram no se ha inicializado.")
        raise HTTPException(status_code=500, detail="Bot application not initialized.")
        
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error al procesar la actualización: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    logger.info("Servidor FastAPI iniciado.")
    # El webhook se configura en el lifespan, no es necesario aquí

@app.on_event("shutdown")
async def shutdown_event():
    if application and application.running:
        await application.stop()
        logger.info("Aplicación del bot de Telegram detenida.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

# Aquí empieza el resto del código que faltaba
# --- Funciones de soporte para el bot ---

def generate_random_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

# --- Handlers adicionales ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Aquí tienes una lista de comandos y funciones que puedo realizar:\n\n"
                                    "/start - Iniciar el bot y ver el menú principal.\n"
                                    "/register - Iniciar el proceso de registro.\n"
                                    "/report - Iniciar el proceso de reporte de una incidencia.\n"
                                    "/location - Compartir tu ubicación.\n"
                                    "/create_event - Crear un evento.\n"
                                    "/poll - Crear una encuesta.\n"
                                    "/feedback - Enviar feedback.\n"
                                    "/bug - Reportar un error.\n"
                                    "/contact - Contactar con el soporte.\n"
                                    "/subscribe - Suscribirse a notificaciones.\n"
                                    "/unsubscribe - Darse de baja de notificaciones.\n"
                                    "/check_status - Consultar el estado de un reporte.\n"
                                    "/admin - Acceder al panel de administrador (solo para administradores).\n"
                                    "/help - Mostrar esta ayuda.")
    logger.info(f"Comando /help recibido de {update.effective_user.id}")

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_user_registered(update.effective_user.id):
        await update.message.reply_text("Por favor, regístrate primero usando /start.")
        return ConversationHandler.END

    await update.message.reply_text("Por favor, escribe tu feedback o sugerencia.")
    return FEEDBACK_TEXT

async def feedback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    feedback = update.message.text
    context.user_data['feedback_text'] = feedback
    
    keyboard = [[InlineKeyboardButton("Confirmar", callback_data="confirm_feedback")],
                [InlineKeyboardButton("Cancelar", callback_data="cancel_feedback")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Tu feedback es: \n\n'{feedback}'\n\n¿Quieres enviarlo?",
        reply_markup=reply_markup
    )
    return FEEDBACK_CONFIRMATION

async def confirm_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    feedback_data = {
        'user_id': query.from_user.id,
        'feedback': context.user_data['feedback_text'],
        'timestamp': datetime.now(pytz.timezone('Europe/Madrid'))
    }
    await asyncio.to_thread(db.collection('feedback').add, feedback_data)
    
    await query.edit_message_text("¡Gracias por tu feedback! Ha sido enviado con éxito.")
    return ConversationHandler.END

async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Envío de feedback cancelado.")
    return ConversationHandler.END

async def bug_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_user_registered(update.effective_user.id):
        await update.message.reply_text("Por favor, regístrate primero usando /start.")
        return ConversationHandler.END

    await update.message.reply_text("Por favor, describe el error que has encontrado.")
    return BUG_DESCRIPTION

async def bug_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text
    context.user_data['bug_description'] = description
    await update.message.reply_text("¿Cómo podemos reproducir este error?")
    return BUG_REPRODUCE

async def bug_reproduce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reproduce = update.message.text
    context.user_data['bug_reproduce'] = reproduce
    await update.message.reply_text("¿Podrías proporcionar un correo electrónico para que podamos contactarte si es necesario?")
    return BUG_CONTACT

async def bug_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact_email = update.message.text
    context.user_data['bug_contact'] = contact_email
    
    bug_data = context.user_data
    bug_data['user_id'] = update.effective_user.id
    bug_data['timestamp'] = datetime.now(pytz.timezone('Europe/Madrid'))

    keyboard = [[InlineKeyboardButton("Confirmar", callback_data="confirm_bug")],
                [InlineKeyboardButton("Cancelar", callback_data="cancel_bug")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"¿Quieres enviar este reporte de error?\n\nDescripción: {bug_data['bug_description']}\nReproducción: {bug_data['bug_reproduce']}\nContacto: {bug_data['bug_contact']}",
        reply_markup=reply_markup
    )
    return BUG_CONFIRMATION

async def confirm_bug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    bug_data = context.user_data
    bug_data['user_id'] = query.from_user.id
    bug_data['timestamp'] = datetime.now(pytz.timezone('Europe/Madrid'))
    
    await asyncio.to_thread(db.collection('bugs').add, bug_data)
    
    await query.edit_message_text("¡Gracias por tu reporte de error! Ha sido enviado con éxito.")
    return ConversationHandler.END

async def cancel_bug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Reporte de error cancelado.")
    return ConversationHandler.END

async def contact_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_user_registered(update.effective_user.id):
        await update.message.reply_text("Por favor, regístrate primero usando /start.")
        return ConversationHandler.END

    await update.message.reply_text("Por favor, introduce tu nombre completo.")
    return CONTACT_NAME

async def contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text
    context.user_data['contact_name'] = name
    await update.message.reply_text("Ahora, tu correo electrónico.")
    return CONTACT_EMAIL

async def contact_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text
    context.user_data['contact_email'] = email
    await update.message.reply_text("Por último, escribe el mensaje que quieres enviar.")
    return CONTACT_MESSAGE

async def contact_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message.text
    context.user_data['contact_message'] = message
    
    contact_data = context.user_data
    contact_data['user_id'] = update.effective_user.id
    contact_data['timestamp'] = datetime.now(pytz.timezone('Europe/Madrid'))

    keyboard = [[InlineKeyboardButton("Confirmar", callback_data="confirm_contact")],
                [InlineKeyboardButton("Cancelar", callback_data="cancel_contact")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"¿Quieres enviar este mensaje de contacto?\n\nNombre: {contact_data['contact_name']}\nEmail: {contact_data['contact_email']}\nMensaje: {contact_data['contact_message']}",
        reply_markup=reply_markup
    )
    return CONTACT_CONFIRMATION

async def confirm_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    contact_data = context.user_data
    contact_data['user_id'] = query.from_user.id
    contact_data['timestamp'] = datetime.now(pytz.timezone('Europe/Madrid'))
    
    await asyncio.to_thread(db.collection('contact_messages').add, contact_data)
    
    await query.edit_message_text("¡Gracias por contactarnos! Tu mensaje ha sido enviado con éxito.")
    return ConversationHandler.END

async def cancel_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Envío de contacto cancelado.")
    return ConversationHandler.END

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_ref = db.collection('users').document(str(user_id))
    user_doc = await asyncio.to_thread(user_ref.get)
    
    if user_doc.exists:
        if user_doc.get('subscribed', False):
            await update.message.reply_text("Ya estás suscrito a las notificaciones.")
            return ConversationHandler.END
        else:
            keyboard = [[InlineKeyboardButton("Sí", callback_data="confirm_subscribe")],
                        [InlineKeyboardButton("No", callback_data="cancel_subscribe")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("¿Quieres suscribirte a las notificaciones?", reply_markup=reply_markup)
            return SUBSCRIBE_CONFIRMATION
    else:
        await update.message.reply_text("Por favor, regístrate primero usando /start.")
        return ConversationHandler.END

async def confirm_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_ref = db.collection('users').document(str(query.from_user.id))
    await asyncio.to_thread(user_ref.update, {'subscribed': True})
    
    await query.edit_message_text("¡Te has suscrito a las notificaciones con éxito!")
    return ConversationHandler.END

async def cancel_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Suscripción cancelada.")
    return ConversationHandler.END

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_ref = db.collection('users').document(str(user_id))
    user_doc = await asyncio.to_thread(user_ref.get)
    
    if user_doc.exists:
        if not user_doc.get('subscribed', False):
            await update.message.reply_text("No estás suscrito a las notificaciones.")
            return ConversationHandler.END
        else:
            keyboard = [[InlineKeyboardButton("Sí", callback_data="confirm_unsubscribe")],
                        [InlineKeyboardButton("No", callback_data="cancel_unsubscribe")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("¿Quieres darte de baja de las notificaciones?", reply_markup=reply_markup)
            return UNSUBSCRIBE_CONFIRMATION
    else:
        await update.message.reply_text("Por favor, regístrate primero usando /start.")
        return ConversationHandler.END

async def confirm_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_ref = db.collection('users').document(str(query.from_user.id))
    await asyncio.to_thread(user_ref.update, {'subscribed': False})
    
    await query.edit_message_text("Te has dado de baja de las notificaciones con éxito.")
    return ConversationHandler.END

async def cancel_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Desuscripción cancelada.")
    return ConversationHandler.END

async def check_status_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_user_registered(update.effective_user.id):
        await update.message.reply_text("Por favor, regístrate primero usando /start.")
        return ConversationHandler.END

    await update.message.reply_text("Por favor, introduce el ID del reporte que quieres consultar.")
    return CHECK_STATUS_ID

async def check_status_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    report_id = update.message.text
    report_ref = db.collection('reports').document(report_id)
    report_doc = await asyncio.to_thread(report_ref.get)
    
    if report_doc.exists and report_doc.get('user_id') == update.effective_user.id:
        report_data = report_doc.to_dict()
        status = report_data.get('status', 'Pendiente')
        await update.message.reply_text(f"El estado de tu reporte con ID '{report_id}' es: {status}")
    else:
        await update.message.reply_text("No se encontró ningún reporte con ese ID o no tienes permisos para consultarlo.")
        
    return ConversationHandler.END

async def webapp_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_user_registered(update.effective_user.id):
        await update.message.reply_text("Por favor, regístrate primero usando /start.")
        return
    
    keyboard = [[KeyboardButton("Abrir Web App", web_app=WebAppInfo(url="https://ejemplo.com"))]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Haz clic en el botón para abrir la Web App.", reply_markup=reply_markup)

# --- CONFIGURACIÓN DE FASTAPI Y HANDLERS ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Función de lifespan para FastAPI. Se ejecuta al iniciar la app.
    Aquí inicializamos el bot y configuramos el webhook.
    """
    global application
    logger.info("Iniciando aplicación FastAPI...")
    try:
        application = ApplicationBuilder().token(TOKEN).updater(None).build()
        
        # Carga todos los manejadores del bot
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(register_callback, pattern='^register$'))
        
        # Handlers de conversación
        register_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(register_callback, pattern='^register$')],
            states={
                REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
                REGISTER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(register_handler)

        report_handler = ConversationHandler(
            entry_points=[CommandHandler('report', report_start)],
            states={
                REPORT_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_details)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(report_handler)

        admin_handler = ConversationHandler(
            entry_points=[CommandHandler('admin', admin_start)],
            states={
                ADMIN_MENU: [CallbackQueryHandler(admin_broadcast_callback, pattern='^broadcast$')],
                ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_message)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(admin_handler)

        location_handler = ConversationHandler(
            entry_points=[CommandHandler('location', ask_location_start)],
            states={
                GET_LOCATION: [MessageHandler(filters.LOCATION, get_location_and_search)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(location_handler)

        event_handler = ConversationHandler(
            entry_points=[CommandHandler('create_event', event_name)],
            states={
                EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_date)],
                EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_time)],
                EVENT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_location)],
                EVENT_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_description)],
                EVENT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_event)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(event_handler)

        poll_handler = ConversationHandler(
            entry_points=[CommandHandler('poll', start_poll)],
            states={
                POLL_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, poll_options_input)],
                POLL_OPTIONS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_poll)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(poll_handler)

        feedback_handler = ConversationHandler(
            entry_points=[CommandHandler('feedback', feedback_start)],
            states={
                FEEDBACK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_text)],
                FEEDBACK_CONFIRMATION: [CallbackQueryHandler(confirm_feedback, pattern='^confirm_feedback$'),
                                         CallbackQueryHandler(cancel_feedback, pattern='^cancel_feedback$')],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(feedback_handler)

        bug_handler = ConversationHandler(
            entry_points=[CommandHandler('bug', bug_start)],
            states={
                BUG_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, bug_description)],
                BUG_REPRODUCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bug_reproduce)],
                BUG_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bug_contact)],
                BUG_CONFIRMATION: [CallbackQueryHandler(confirm_bug, pattern='^confirm_bug$'),
                                   CallbackQueryHandler(cancel_bug, pattern='^cancel_bug$')],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(bug_handler)

        contact_handler = ConversationHandler(
            entry_points=[CommandHandler('contact', contact_start)],
            states={
                CONTACT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_name)],
                CONTACT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_email)],
                CONTACT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_message)],
                CONTACT_CONFIRMATION: [CallbackQueryHandler(confirm_contact, pattern='^confirm_contact$'),
                                       CallbackQueryHandler(cancel_contact, pattern='^cancel_contact$')],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(contact_handler)

        subscribe_handler = ConversationHandler(
            entry_points=[CommandHandler('subscribe', subscribe_command)],
            states={
                SUBSCRIBE_CONFIRMATION: [CallbackQueryHandler(confirm_subscribe, pattern='^confirm_subscribe$'),
                                         CallbackQueryHandler(cancel_subscribe, pattern='^cancel_subscribe$')],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(subscribe_handler)

        unsubscribe_handler = ConversationHandler(
            entry_points=[CommandHandler('unsubscribe', unsubscribe_command)],
            states={
                UNSUBSCRIBE_CONFIRMATION: [CallbackQueryHandler(confirm_unsubscribe, pattern='^confirm_unsubscribe$'),
                                           CallbackQueryHandler(cancel_unsubscribe, pattern='^cancel_unsubscribe$')],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(unsubscribe_handler)

        check_status_handler = ConversationHandler(
            entry_points=[CommandHandler('check_status', check_status_start)],
            states={
                CHECK_STATUS_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_status_id)],
            },
            fallbacks=[CommandHandler('cancel', cancel_command)],
        )
        application.add_handler(check_status_handler)

        webapp_handler = CommandHandler('webapp', webapp_start)
        application.add_handler(webapp_handler)
        application.add_handler(CommandHandler('help', help_command))

        logger.info("Manejadores del bot cargados.")

        # Establece la URL del webhook en Telegram
        await application.bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook configurado en la URL: {WEBHOOK_URL}")

        yield
    except Exception as e:
        logger.error(f"Error durante la inicialización de la aplicación: {e}")
        sys.exit(1)
    finally:
        logger.info("Apagando aplicación FastAPI...")

app = FastAPI(lifespan=lifespan)

@app.post("/")
async def webhook_handler(request: Request):
    global application
    if application is None:
        logger.error("La aplicación de Telegram no se ha inicializado.")
        raise HTTPException(status_code=500, detail="Bot application not initialized.")
        
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error al procesar la actualización: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    logger.info("Servidor FastAPI iniciado.")

@app.on_event("shutdown")
async def shutdown_event():
    if application and application.running:
        await application.stop()
        logger.info("Aplicación del bot de Telegram detenida.")
