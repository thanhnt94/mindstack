"""
Module chứa các handlers liên quan đến việc người dùng chọn và lưu
chế độ học/ôn tập mặc định thông qua giao diện menu.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CallbackQueryHandler 
from database.query_user import get_user_by_telegram_id, update_user_by_id
from ui.core_ui import ( 
    build_mode_category_keyboard,
    build_srs_mode_submenu,
    build_new_only_submenu,
    build_review_submenu
)
from handlers import nav_core 
from utils.helpers import send_or_edit_message 
from utils.exceptions import ( 
    DatabaseError,
    UserNotFoundError,
    ValidationError,
    DuplicateError
)
from config import (
    DEFAULT_LEARNING_MODE,
    LEARNING_MODE_DISPLAY_NAMES
)
logger = logging.getLogger(__name__)
async def handle_callback_show_mode_selection(update, context):
    """Handler cho callback 'show_mode_selection'."""
    query = update.callback_query
    if not query:
        logger.warning("handle_callback_show_mode_selection: callback query không tồn tại.")
        return
    if not query.from_user:
        logger.warning("handle_callback_show_mode_selection: callback query không có thông tin user.")
        return
    try:
        await query.answer() 
    except Exception as e_ans:
        logger.warning(f"Lỗi answer callback show mode selection: {e_ans}")
    user_id_tg = query.from_user.id
    log_prefix = f"[MODE_SELECTION_SHOW|UserTG:{user_id_tg}]" 
    logger.info(f"{log_prefix} Hiển thị menu chọn danh mục mode.")
    chat_id = -1
    if query.message:
        chat_id = query.message.chat_id
    else:
        chat_id = user_id_tg 
    message_to_edit = query.message
    reply_markup = build_mode_category_keyboard()
    text = "⚡ Chọn danh mục chế độ học:"
    if reply_markup:
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit)
    else:
        logger.error(f"{log_prefix} Lỗi build keyboard danh mục.")
        await send_or_edit_message(context, chat_id, "Lỗi hiển thị menu.", message_to_edit=message_to_edit)
async def handle_callback_select_mode_category(update, context):
    """Handler cho callback 'mode_category:<category>'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_select_mode_category: callback query không tồn tại."); return
    if not query.from_user: logger.warning("handle_callback_select_mode_category: user không hợp lệ."); return
    if not query.data: logger.warning("handle_callback_select_mode_category: data không hợp lệ."); return
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning(f"Lỗi answer callback select mode category: {e_ans}")
    user_id_tg = query.from_user.id
    log_prefix = f"[MODE_SELECTION_CATEGORY|UserTG:{user_id_tg}]" 
    chat_id = -1
    if query.message:
        chat_id = query.message.chat_id
    else:
        chat_id = user_id_tg
    message_to_edit = query.message
    submenu_builder = None 
    text = "⚡ Vui lòng chọn chế độ cụ thể:" 
    try:
        parts = query.data.split(":", 1)
        if len(parts) < 2:
            logger.error(f"{log_prefix} Callback data sai định dạng: {query.data}")
            await send_or_edit_message(context, chat_id, "Lỗi dữ liệu lựa chọn.", message_to_edit=message_to_edit)
            return
        category = parts[1]
        logger.info(f"{log_prefix} Chọn danh mục: '{category}'")
        if category == "srs":
            submenu_builder = build_srs_mode_submenu
            text = "🎓 Chọn chế độ Ghi nhớ sâu:"
        elif category == "new":
            submenu_builder = build_new_only_submenu
            text = "➕ Chọn chế độ Học mới:"
        elif category == "review":
            submenu_builder = build_review_submenu
            text = "🎯 Chọn chế độ Ôn tập:"
        else:
            logger.warning(f"{log_prefix} Danh mục không xác định: {category}")
            await send_or_edit_message(context, chat_id, "Lựa chọn không hợp lệ.", message_to_edit=message_to_edit)
            return
        if submenu_builder:
            reply_markup = submenu_builder()
            if reply_markup:
                 await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit)
            else:
                 logger.error(f"{log_prefix} Lỗi tạo submenu cho '{category}'.")
                 await send_or_edit_message(context, chat_id, "Lỗi hiển thị các chế độ con.", message_to_edit=message_to_edit)
        else:
            logger.error(f"{log_prefix} Không tìm thấy hàm tạo submenu cho '{category}'.")
            await send_or_edit_message(context, chat_id, "Lỗi nội bộ khi chọn danh mục.", message_to_edit=message_to_edit)
    except (IndexError, ValueError):
        logger.error(f"{log_prefix} Lỗi parse callback data: {query.data}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu lựa chọn danh mục.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi hiển thị chế độ.", message_to_edit=message_to_edit)
async def handle_callback_select_mode(update, context):
    """Handler cho callback 'select_mode:<mode_code>'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_select_mode: callback query không tồn tại."); return
    if not query.from_user: logger.warning("handle_callback_select_mode: user không hợp lệ."); return
    if not query.data: logger.warning("handle_callback_select_mode: data không hợp lệ."); return
    telegram_id = query.from_user.id
    log_prefix = f"[MODE_SELECTION_SELECT|UserTG:{telegram_id}]" 
    chat_id = -1
    if query.message:
        chat_id = query.message.chat_id
    else:
        chat_id = telegram_id
    message_to_edit = query.message
    mode_code = None
    actual_user_id = None
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    try:
        parts = query.data.split(":", 1)
        if len(parts) < 2:
            logger.error(f"{log_prefix} Callback data sai định dạng: {query.data}")
            await send_or_edit_message(context, chat_id, "Lỗi dữ liệu lựa chọn.", message_to_edit=message_to_edit)
            return
        mode_code = parts[1]
        logger.info(f"{log_prefix} Chọn mode cuối cùng: '{mode_code}'")
        if mode_code not in LEARNING_MODE_DISPLAY_NAMES.keys():
            raise ValidationError(f"Chế độ không hợp lệ: {mode_code}")
        logger.debug(f"{log_prefix} Lấy user_id...")
        user_info = get_user_by_telegram_id(telegram_id) 
        actual_user_id = user_info['user_id']
        logger.debug(f"{log_prefix} Lấy được user_id: {actual_user_id}")
        logger.debug(f"{log_prefix} Cập nhật current_mode='{mode_code}' cho user_id={actual_user_id}")
        update_result = update_user_by_id(actual_user_id, current_mode=mode_code)
        if update_result >= 0: 
            logger.info(f"{log_prefix} Update mode DB OK (Rows affected: {update_result}).")
            await nav_core.handle_callback_back_to_main(update, context)
        else:
             logger.error(f"{log_prefix} Lỗi không xác định khi cập nhật mode (update_result < 0).")
             await send_or_edit_message(context, chat_id, "❌ Lỗi không xác định khi lưu chế độ.", message_to_edit=message_to_edit)
    except (IndexError, ValueError):
        logger.error(f"{log_prefix} Callback data lỗi: {query.data}.")
        await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu lựa chọn.", message_to_edit=message_to_edit)
    except ValidationError as e: 
        logger.error(f"{log_prefix} Lỗi Validation: {e}")
        await send_or_edit_message(context, chat_id, f"❌ {e}", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError, DuplicateError) as e: 
        logger.error(f"{log_prefix} Lỗi DB/User khi cập nhật mode='{mode_code}': {e}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi lưu chế độ học.", message_to_edit=message_to_edit)
    except Exception as e: 
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi chọn chế độ.", message_to_edit=message_to_edit)
def register_handlers(app: Application):
    """Đăng ký các handler cho việc chọn chế độ học qua menu."""
    app.add_handler(CallbackQueryHandler(handle_callback_show_mode_selection, pattern=r"^show_mode_selection$"))
    app.add_handler(CallbackQueryHandler(handle_callback_select_mode_category, pattern=r"^mode_category:"))
    app.add_handler(CallbackQueryHandler(handle_callback_select_mode, pattern=r"^select_mode:"))
    logger.info("Đã đăng ký các handler cho module Mode Selection.")
