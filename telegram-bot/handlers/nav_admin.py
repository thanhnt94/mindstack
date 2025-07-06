"""
Module chứa các handlers để truy cập menu admin chính.
Bao gồm lệnh /flashcard_admin và callback 'flashcard_admin'.
"""
import logging
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackQueryHandler 
from config import CAN_ACCESS_ADMIN_MENU 
from ui.admin_ui import build_admin_main_menu 
from utils.helpers import send_or_edit_message, require_permission 
logger = logging.getLogger(__name__)
@require_permission(CAN_ACCESS_ADMIN_MENU)
async def handle_command_admin_menu(update, context):
    """Handler cho lệnh /flashcard_admin."""
    if not update:
        logger.warning("handle_command_admin_menu: update lỗi.")
        return
    if not update.effective_user:
        logger.warning("handle_command_admin_menu: user lỗi.")
        return
    if not update.message:
        logger.warning("handle_command_admin_menu: message lỗi.")
        return
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    log_prefix = f"[NAV_ADMIN_CMD|User:{user_id}]" 
    logger.info(f"{log_prefix} Lệnh /flashcard_admin.")
    reply_markup = build_admin_main_menu()
    sent_message = await send_or_edit_message(
        context=context,
        chat_id=chat_id,
        text="🛠️ Chức năng Admin:",
        reply_markup=reply_markup
    )
    if not sent_message:
        logger.error(f"{log_prefix} Lỗi gửi menu admin.")
@require_permission(CAN_ACCESS_ADMIN_MENU)
async def handle_callback_show_admin_menu(update, context):
    """Handler cho callback 'flashcard_admin'."""
    query = update.callback_query
    if not query:
        logger.warning("handle_callback_show_admin_menu: Không tìm thấy query.")
        return
    if not query.from_user:
        logger.warning("handle_callback_show_admin_menu: Không tìm thấy user.")
        return
    try:
        await query.answer() 
    except Exception as e_ans:
        logger.warning(f"Lỗi answer callback show admin menu: {e_ans}")
    user_id = query.from_user.id
    log_prefix = f"[NAV_ADMIN_CB|User:{user_id}]" 
    logger.info(f"{log_prefix} Hiển thị menu admin chính từ callback.")
    chat_id = user_id 
    message_to_edit = query.message 
    reply_markup = build_admin_main_menu()
    sent_msg = await send_or_edit_message(
        context=context,
        chat_id=chat_id,
        text="🛠️ Chức năng Admin:",
        reply_markup=reply_markup,
        message_to_edit=message_to_edit
    )
    if not sent_msg:
        logger.error(f"{log_prefix} Lỗi hiển thị menu admin.")
def register_handlers(app: Application):
    """Đăng ký các handler để vào menu admin."""
    app.add_handler(CommandHandler("flashcard_admin", handle_command_admin_menu))
    app.add_handler(CallbackQueryHandler(handle_callback_show_admin_menu, pattern=r"^flashcard_admin$"))
    logger.info("Đã đăng ký các handler cho module Nav Admin.")
