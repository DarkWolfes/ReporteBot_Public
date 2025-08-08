import sqlite3
import logging
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler
)
from flask import Flask, request
import re
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Chat

# Configuración del logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# TU TOKEN DEL BOT, ahora se obtiene de las variables de entorno de Render
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# --- CONFIGURACIÓN DE ESTADOS DEL CONVERSATIONHANDLER ---
MENU_STATE = 0
ADMIN_MENU_STATE = 1
GET_CHANNEL_ID_FROM_FORWARD = 2
GET_ADMINS_IDS = 3
GET_SPAMMER_USERNAME = 4
GET_REPORT_DESCRIPTION = 5
GET_REPORT_PHOTO = 6
AWAITING_RECONFIG_CONFIRMATION = 8

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('bot_config.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users_config (
            user_id INTEGER PRIMARY KEY,
            channel_id TEXT,
            admin_ids TEXT,
            is_configured BOOLEAN
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_to_channel_map (
            group_id INTEGER PRIMARY KEY,
            channel_id TEXT,
            group_name TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_user_config(user_id):
    conn = sqlite3.connect('bot_config.db')
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id, admin_ids, is_configured FROM users_config WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        channel_id, admin_ids_str, is_configured = result
        return {
            'channel_id': channel_id,
            'admin_ids': [int(id) for id in admin_ids_str.split(',')] if admin_ids_str else [],
            'is_configured': bool(is_configured)
        }
    return None

def save_user_config(user_id, channel_id, admin_ids, is_configured=True):
    conn = sqlite3.connect('bot_config.db')
    cursor = conn.cursor()
    admin_ids_str = ','.join(map(str, admin_ids))
    cursor.execute('''
        INSERT OR REPLACE INTO users_config (user_id, channel_id, admin_ids, is_configured) 
        VALUES (?, ?, ?, ?)
    ''', (user_id, channel_id, admin_ids_str, is_configured))
    conn.commit()
    conn.close()

def delete_user_config(user_id):
    conn = sqlite3.connect('bot_config.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users_config WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def save_group_to_channel_map(group_id, channel_id, group_name):
    conn = sqlite3.connect('bot_config.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO group_to_channel_map (group_id, channel_id, group_name) 
        VALUES (?, ?, ?)
    ''', (group_id, channel_id, group_name))
    conn.commit()
    conn.close()

def delete_group_from_channel_map(group_id):
    conn = sqlite3.connect('bot_config.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM group_to_channel_map WHERE group_id = ?', (group_id,))
    conn.commit()
    conn.close()

def delete_groups_for_channel_id(channel_id):
    conn = sqlite3.connect('bot_config.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM group_to_channel_map WHERE channel_id = ?', (channel_id,))
    conn.commit()
    conn.close()

def get_channel_id_from_group_id(group_id):
    conn = sqlite3.connect('bot_config.db')
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id FROM group_to_channel_map WHERE group_id = ?', (group_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_groups_for_channel_id(channel_id):
    conn = sqlite3.connect('bot_config.db')
    cursor = conn.cursor()
    cursor.execute('SELECT group_id, group_name FROM group_to_channel_map WHERE channel_id = ?', (channel_id,))
    result = cursor.fetchall()
    conn.close()
    return result

def is_admin(user_id):
    config = get_user_config(user_id)
    return config and user_id in config['admin_ids']

# --- MANEJADORES DEL FLUJO PRINCIPAL Y MENÚS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user:
        return ConversationHandler.END
        
    chat = update.effective_chat
    if chat and chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        await context.bot.send_message(chat_id=chat.id, text="❌ Este comando solo puede ser usado en un chat privado. Por favor, habla conmigo en privado.")
        return ConversationHandler.END

    mensaje = (
        "¡Hola! 👋\n\n"
        "Este bot te ayuda a reportar usuarios molestos o a configurar tu propio sistema de reportes.\n\n"
        "Para hacer un reporte, por favor, ve al grupo donde ocurrió el incidente y usa el comando <code>/reportar</code>."
    )
    
    menu_opciones = [['¿Para qué sirve este bot?']]
    menu_opciones.append(['Configurar mi bot']) 

    if is_admin(user.id):
        menu_opciones.append(['Herramientas de Administrador'])
    
    reply_markup = ReplyKeyboardMarkup(menu_opciones, resize_keyboard=True)
    await update.message.reply_text(mensaje, reply_markup=reply_markup, parse_mode="HTML")
    return MENU_STATE

async def handle_about_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "ℹ️ El objetivo de este bot es que los usuarios puedan reportar de manera eficiente y centralizada a "
        "aquellos que envían spam, mensajes ofensivos o tienen un comportamiento inadecuado en los grupos. "
        "Con este bot, los reportes se envían a un canal específico para que tú y otros administradores puedan "
        "revisarlos y tomar las medidas oportunas.",
        parse_mode="HTML"
    )
    return MENU_STATE

async def handle_admin_tools_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    if not is_admin(user.id):
        await update.message.reply_text("❌ Esta función es solo para administradores.")
        return MENU_STATE
    
    menu_opciones = [['Bot Info', 'Check Reports'], ['Volver']]
    reply_markup = ReplyKeyboardMarkup(menu_opciones, resize_keyboard=True)
    await update.message.reply_text(
        "🛠️ **Menú de Herramientas de Administrador**\n\n"
        "Elige una opción para gestionar la configuración y los reportes:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ADMIN_MENU_STATE

async def handle_config_bot_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user:
        return ConversationHandler.END
        
    config = get_user_config(user.id)
    if config and config['is_configured']:
        keyboard = [[
            InlineKeyboardButton("Sí, quiero reconfigurar", callback_data="reconfig_yes"),
            InlineKeyboardButton("No, volver al menú", callback_data="reconfig_no")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ ¡Atención! Ya tienes un bot configurado. Si continúas, la configuración actual se sobrescribirá. ¿Estás seguro de que quieres hacerlo?",
            reply_markup=reply_markup
        )
        return AWAITING_RECONFIG_CONFIRMATION

    context.user_data['config_user_id'] = user.id

    mensaje = (
        "<b>Paso 1: Configurar canal de reportes</b>\n\n"
        "Crea un canal de Telegram (público o privado) y añade este bot como **administrador**.\n"
        "Luego, en el canal, reenvía cualquier mensaje del bot y pégalo aquí para que pueda obtener la ID del canal."
    )
    await update.message.reply_text(mensaje, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    return GET_CHANNEL_ID_FROM_FORWARD

async def handle_reconfig_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "reconfig_yes":
        user_id = update.effective_user.id
        current_config = get_user_config(user_id)
        if current_config:
            delete_groups_for_channel_id(current_config['channel_id'])
        
        delete_user_config(user_id)  
        await query.edit_message_text(text="✅ Entendido. Iniciando la nueva configuración.")
        
        context.user_data['config_user_id'] = user_id
        mensaje = (
            "<b>Paso 1: Configurar canal de reportes</b>\n\n"
            "Crea un canal de Telegram (público o privado) y añade este bot como **administrador**.\n"
            "Luego, en el canal, reenvía cualquier mensaje del bot y pégalo aquí para que pueda obtener la ID del canal."
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=mensaje, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        return GET_CHANNEL_ID_FROM_FORWARD
    elif query.data == "reconfig_no":
        await query.edit_message_text(text="❌ Cancelado. Volviendo al menú principal.")
        return await start_command(update, context)

    return ConversationHandler.END

async def get_channel_id_from_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    channel_id = None
    text = update.message.text
    if text:
        match = re.search(r"c\/(-?\d+)\/(\d+)", text)
        if match:
            channel_id_str = match.group(1)
            channel_id = int(f"-100{channel_id_str}")
        elif re.match(r"^-?\d+$", text):
            channel_id = int(text)

    if not channel_id:
        await update.message.reply_text(
            "❌ ¡Error! Por favor, asegúrate de que el mensaje que envías contiene un enlace de tu canal o el ID numérico."
        )
        return GET_CHANNEL_ID_FROM_FORWARD

    config_user_id = context.user_data.get('config_user_id')
    if not config_user_id:
        await update.message.reply_text("❌ Ha ocurrido un error. Vuelve a empezar con el comando /start.")
        return ConversationHandler.END

    context.user_data['channel_id'] = channel_id

    await context.bot.send_message(chat_id=config_user_id, text=
        "✅ ¡Canal configurado correctamente!\n\n"
        "<b>Paso 2: Definir administradores</b>\n\n"
        "Ahora, por favor, dime quiénes son los administradores. Envía los IDs de usuario de cada administrador separados por comas.\n"
        "Si no quieres añadir más administradores, escribe 'ninguno'. **Recuerda que tú, como creador, ya eres administrador.**"
    )
    return GET_ADMINS_IDS

async def get_admins_ids(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = context.user_data.get('config_user_id')
    if not user_id:
        return ConversationHandler.END
        
    channel_id = context.user_data['channel_id']
    
    if update.message.text.lower() == 'ninguno':
        admin_ids = [user_id]
    else:
        try:
            admin_ids = [int(id.strip()) for id in update.message.text.split(',') if id.strip().isdigit()]
            if user_id not in admin_ids:
                admin_ids.append(user_id)
        except ValueError:
            await update.message.reply_text("❌ Formato de IDs incorrecto. Por favor, envía los IDs separados por comas (ejemplo: 12345, 67890). O escribe 'ninguno'.")
            return GET_ADMINS_IDS

    save_user_config(user_id, str(channel_id), admin_ids)
    
    await update.message.reply_text(
        "🎉 ¡El bot ha sido configurado! Ahora, el **último paso** es enlazarlo a un grupo.\n\n"
        "<b>Paso 3: Enlazar a un grupo</b>\n\n"
        "Añade este bot a tu grupo y usa el comando <code>/configurar_aqui</code>. Cuando lo hagas, te enviaré una confirmación por aquí. ¡Te espero!",
        parse_mode="HTML"
    )
    return MENU_STATE

async def handle_bot_info_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user:
        return ADMIN_MENU_STATE

    if not is_admin(user.id):
        await update.message.reply_text("❌ Este comando solo puede ser usado por los administradores.")
        return ADMIN_MENU_STATE
        
    config = get_user_config(user.id)
    if not config or not config['is_configured']:
        await update.message.reply_text("⚠️ El bot no está configurado. Por favor, usa /start para iniciar la configuración.")
        return ADMIN_MENU_STATE

    admin_list_str = ', '.join([str(admin_id) for admin_id in config['admin_ids']])
    
    groups = get_groups_for_channel_id(config['channel_id'])
    if groups:
        groups_list = "\n".join([f"- {name} (ID: <code>{gid}</code>)" for gid, name in groups])
    else:
        groups_list = "No hay grupos asociados a este canal de reportes."
    
    mensaje = (
        "<b>Bot Info (Solo para administradores)</b>\n\n"
        f"<b>ID del canal de reportes:</b> <code>{config['channel_id']}</code>\n"
        f"<b>IDs de administradores:</b> <code>{admin_list_str}</code>\n\n"
        "<b>Grupos enlazados a este canal:</b>\n"
        f"{groups_list}\n\n"
        "<b>Para enlazar un grupo:</b>\n"
        "1. Añade este bot al grupo.\n"
        "2. En el grupo, usa el comando <code>/configurar_aqui</code>.\n\n"
        "<b>Para desvincular un grupo:</b>\n"
        "1. Ve al grupo que quieres desvincular.\n"
        "2. Usa el comando <code>/desconfigurar_aqui</code>."
    )
    await update.message.reply_text(mensaje, parse_mode="HTML")
    return ADMIN_MENU_STATE

async def handle_check_reports_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user:
        return ADMIN_MENU_STATE

    if not is_admin(user.id):
        await update.message.reply_text("❌ Este comando solo puede ser usado por los administradores.")
        return ADMIN_MENU_STATE

    await update.message.reply_text("✅ No hay reportes nuevos que requieran tu atención en este momento.")
    return ADMIN_MENU_STATE

async def handle_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start_command(update, context)

async def cancel_any_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Proceso cancelado.", reply_markup=ReplyKeyboardRemove())
    if 'report_data' in context.user_data:
        del context.user_data['report_data']
    return ConversationHandler.END

async def start_report_from_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    
    if not user or not chat or chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        return ConversationHandler.END

    group_id = chat.id
    group_name = chat.title
    channel_id = get_channel_id_from_group_id(group_id)
    
    if not channel_id:
        await context.bot.send_message(chat_id=chat.id, text=f"❌ El grupo '{group_name}' no está enlazado a ningún canal de reportes. Por favor, pide a un administrador que use el comando /configurar_aqui.")
        return ConversationHandler.END

    try:
        await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception as e:
        logging.info(f"No se pudo borrar el mensaje del comando /reportar. Posiblemente no tenga los permisos: {e}")

    context.user_data['report_data'] = {'group_name': group_name, 'group_id': group_id, 'channel_id': channel_id}
    
    keyboard = [[InlineKeyboardButton("Iniciar Reporte", callback_data="start_report")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=user.id, 
        text=f"✅ He detectado que quieres hacer un reporte desde el grupo **{group_name}**.\n\n"
             f"Presiona el botón de abajo para continuar con el proceso de reporte.", 
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def start_private_report_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if 'report_data' not in context.user_data:
        await query.edit_message_text("❌ No he detectado un reporte activo. Por favor, usa el comando /reportar en el grupo para iniciar el proceso.")
        return ConversationHandler.END
        
    await query.edit_message_text("Ahora, por favor, introduce el nombre de usuario de la persona que quieres reportar (ej: @usuario_spam o simplemente un nombre).")
    return GET_SPAMMER_USERNAME

async def get_spammer_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = update.message.text
    
    if not username:
        await update.message.reply_text("❌ El nombre de usuario no puede estar vacío. Por favor, escribe un nombre de usuario.")
        return GET_SPAMMER_USERNAME
    
    report_data = context.user_data.get('report_data', {})
    report_data['spammer_username'] = username
    context.user_data['report_data'] = report_data
    
    await update.message.reply_text("Ahora, escribe una breve descripción de lo sucedido.")
    return GET_REPORT_DESCRIPTION

async def get_report_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text
    if not description:
        await update.message.reply_text("❌ La descripción no puede estar vacía. Por favor, escribe una breve descripción.")
        return GET_REPORT_DESCRIPTION

    report_data = context.user_data.get('report_data', {})
    report_data['description'] = description
    context.user_data['report_data'] = report_data

    await update.message.reply_text("Por último, por favor, envía una captura de pantalla del incidente. Debe ser una foto, no un archivo.")
    return GET_REPORT_PHOTO

async def process_guided_report_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    report_data = context.user_data.get('report_data')

    if update.message.photo and report_data:
        spammer_username = report_data.get('spammer_username', 'desconocido')
        description = report_data.get('description', 'sin descripción')
        group_name = report_data.get('group_name', 'desconocido')
        channel_id = report_data.get('channel_id')
        group_id = report_data.get('group_id')
        
        photo = update.message.photo[-1]

        reporter_username = user.username or "sin nombre de usuario"
        reporter_fullname = user.full_name or "sin nombre"
        
        caption = (
            f"📣 <b>Nuevo reporte recibido:</b>\n\n"
            f"<b>Reporte enviado por:</b> @{reporter_username} (ID: <code>{user.id}</code>)\n"
            f"<b>Nombre:</b> {reporter_fullname}\n\n"
            f"<b>Usuario reportado:</b> {spammer_username}\n"
            f"<b>Grupo de origen:</b> {group_name} (ID: <code>{group_id}</code>)\n\n"
            f"<b>Descripción:</b>\n{description}"
        )
        
        await send_report_with_buttons(
            context,
            channel_id,
            photo.file_id,
            caption,
            group_id,
            spammer_username,
            user.id
        )

        await update.message.reply_text("✅ Tu reporte ha sido registrado correctamente. Gracias por tu colaboración.")
    else:
        await update.message.reply_text("❌ Hubo un error en el reporte. Por favor, inténtalo de nuevo con el comando /reportar en el grupo.")
    
    if 'report_data' in context.user_data:
        del context.user_data['report_data']
    return ConversationHandler.END

async def send_report_with_buttons(context: ContextTypes.DEFAULT_TYPE, channel_id: str, photo_file_id: str, caption: str, group_id: int, spammer_username: str, reporter_id: int):
    """Envía el reporte a los administradores con el botón de adjudicar."""
    keyboard = [[InlineKeyboardButton("Adjudicar ✅", callback_data=f"adjudicar|{group_id}|{spammer_username}|{reporter_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_photo(
        chat_id=channel_id,
        photo=photo_file_id,
        caption=caption,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def handle_report_action_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja las acciones del botón de adjudicar en el mensaje de reporte."""
    query = update.callback_query
    await query.answer()

    action, group_id_str, spammer_username, reporter_id_str = query.data.split('|')
    reporter_id = int(reporter_id_str)
    admin_user = update.effective_user
    
    if not is_admin(admin_user.id):
        await query.message.reply_text("❌ Solo un administrador puede tomar acciones sobre este reporte.")
        return

    original_caption = query.message.caption
    
    if action == 'adjudicar':
        new_caption = f"{original_caption}\n\n<b>Adjudicado por:</b> @{admin_user.username} ✅"
        try:
            await query.edit_message_caption(caption=new_caption, parse_mode="HTML", reply_markup=None)
            
            await context.bot.send_message(
                chat_id=reporter_id,
                text="✅ Tu reporte está siendo tratado por un administrador. Si lo consideran necesario, uno de los administradores se pondrá en contacto contigo."
            )
            
        except Exception as e:
            logging.error(f"Error al editar el mensaje de reporte: {e}")

async def configure_group_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    try:
        await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception as e:
        logging.info(f"No se pudo borrar el mensaje del comando /configurar_aqui: {e}")

    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await context.bot.send_message(chat_id=chat.id, text="❌ Este comando solo puede ser usado en un grupo.")
        return

    if not is_admin(user.id):
        await context.bot.send_message(chat_id=chat.id, text="❌ Solo un administrador puede usar este comando.")
        return

    user_config = get_user_config(user.id)
    if not user_config or not user_config['is_configured']:
        await context.bot.send_message(chat_id=chat.id, text="❌ Tu bot no está configurado. Por favor, usa /start en privado para configurarlo primero.")
        return
    
    save_group_to_channel_map(chat.id, user_config['channel_id'], chat.title)
    
    await context.bot.send_message(chat_id=chat.id, text=
        f"✅ ¡Grupo '{chat.title}' configurado! Los reportes de este grupo se enviarán al canal de reportes asociado a tu cuenta."
    )
    await context.bot.send_message(chat_id=user.id, text=
        f"🎉 **¡Configuración completa!**\n\n"
        f"El grupo '{chat.title}' (ID: <code>{chat.id}</code>) ha sido enlazado a tu canal de reportes.\n\n"
        "Ahora los miembros de ese grupo pueden usar el bot para reportar incidentes.",
        parse_mode="HTML"
    )

async def unconfigure_group_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    try:
        await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
    except Exception as e:
        logging.info(f"No se pudo borrar el mensaje del comando /desconfigurar_aqui: {e}")
    
    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await context.bot.send_message(chat_id=chat.id, text="❌ Este comando solo puede ser usado en un grupo.")
        return

    if not is_admin(user.id):
        await context.bot.send_message(chat_id=chat.id, text="❌ Solo un administrador puede usar este comando.")
        return

    if not get_channel_id_from_group_id(chat.id):
        await context.bot.send_message(chat_id=chat.id, text=f"⚠️ El grupo '{chat.title}' no está configurado, no hay nada que desvincular.")
        return
        
    delete_group_from_channel_map(chat.id)

    await context.bot.send_message(chat_id=chat.id, text=
        f"✅ ¡Grupo '{chat.title}' desvinculado! Los reportes de este grupo ya no se enviarán a tu canal."
    )
    await context.bot.send_message(chat_id=user.id, text=
        f"❌ El grupo '{chat.title}' (ID: <code>{chat.id}</code>) ha sido desvinculado de tu canal de reportes.",
        parse_mode="HTML"
    )

async def ayuda_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
        except Exception as e:
            logging.info(f"No se pudo borrar el mensaje del comando /ayuda: {e}")

    help_text = (
        "<b>Comandos disponibles</b>\n\n"
        " • <code>/start</code> - Inicia una conversación con el bot en privado.\n"
        " • <code>/reportar</code> - Inicia el proceso para reportar a un usuario.\n"
        " • <code>/ayuda</code> - Muestra esta lista de comandos.\n\n"
        "<b>Comandos de administración (Solo admins)</b>\n\n"
        " • <code>/configurar_aqui</code> - Enlaza este grupo a tu canal de reportes.\n"
        " • <code>/desconfigurar_aqui</code> - Desvincula este grupo de tu canal de reportes."
    )

    if chat.type == Chat.PRIVATE:
        await update.message.reply_text(help_text, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat.id, text=help_text, parse_mode="HTML")

async def handle_unhandled_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    
    if update.effective_chat.type == Chat.PRIVATE:
        mensaje = (
            "❌ Lo siento, no te entiendo. Si quieres hacer un reporte, ve al grupo donde ocurrió el problema y usa el comando <code>/reportar</code>."
            "Si necesitas ayuda con otra cosa, usa el comando /start."
        )
        await update.message.reply_text(mensaje, parse_mode="HTML")

# --- BLOQUE DEL WEBHOOK (CORREGIDO) ---
app = Flask(__name__)
application = ApplicationBuilder().token(BOT_TOKEN).build()

async def webhook_handler_wrapper():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return 'ok'

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
async def webhook():
    if request.method == "POST":
        await webhook_handler_wrapper()
    return "ok"

def add_handlers():
    main_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command, filters.ChatType.PRIVATE),
        ],
        states={
            MENU_STATE: [
                MessageHandler(filters.Regex('^¿Para qué sirve este bot?.*$'), handle_about_button),
                MessageHandler(filters.Regex('^Configurar mi bot$'), handle_config_bot_button),
                MessageHandler(filters.Regex('^Herramientas de Administrador$'), handle_admin_tools_button),
            ],
            ADMIN_MENU_STATE: [
                MessageHandler(filters.Regex('^Bot Info$'), handle_bot_info_button),
                MessageHandler(filters.Regex('^Check Reports$'), handle_check_reports_button),
                MessageHandler(filters.Regex('^Volver$'), handle_back_button),
            ],
            GET_CHANNEL_ID_FROM_FORWARD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_channel_id_from_forward)
            ],
            GET_ADMINS_IDS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_admins_ids)
            ],
            AWAITING_RECONFIG_CONFIRMATION: [
                CallbackQueryHandler(handle_reconfig_confirmation),
                MessageHandler(filters.Regex('^¿Para qué sirve este bot?.*$'), handle_about_button),
                MessageHandler(filters.Regex('^Herramientas de Administrador$'), handle_admin_tools_button),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_any_flow)],
        allow_reentry=True,
    )

    report_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_private_report_from_button, pattern="^start_report$")
        ],
        states={
            GET_SPAMMER_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_spammer_username)
            ],
            GET_REPORT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_report_description)
            ],
            GET_REPORT_PHOTO: [
                MessageHandler(filters.PHOTO, process_guided_report_photo)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_any_flow)],
        allow_reentry=True,
    )

    application.add_handler(main_handler)
    application.add_handler(report_handler)

    application.add_handler(CallbackQueryHandler(handle_report_action_button))
    application.add_handler(CommandHandler('configurar_aqui', configure_group_in_group))
    application.add_handler(CommandHandler('desconfigurar_aqui', unconfigure_group_in_group))
    application.add_handler(CommandHandler('reportar', start_report_from_group_command, filters.ChatType.GROUPS))
    application.add_handler(CommandHandler('ayuda', ayuda_command))

    application.add_handler(MessageHandler(filters.ALL, handle_unhandled_messages))

if __name__ == '__main__':
    init_db()
    add_handlers()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
