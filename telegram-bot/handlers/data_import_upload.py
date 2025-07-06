# Path: flashcard_v2/handlers/data_import_upload.py
"""
Module chứa handlers và conversation handler cho chức năng
upload (import) bộ từ vựng mới từ file Excel.
Đã sửa lỗi parse Markdown cho tên bộ từ trong tin nhắn xác nhận.
Đã thay đổi per_message=False để chẩn đoán lỗi state.
"""

import logging
import os
import time
import asyncio
import html
import re # Import re để escape markdown

# Import từ thư viện telegram
from telegram import Update
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram.ext import Application
from telegram.ext import ContextTypes
from telegram.ext import ConversationHandler
from telegram.ext import MessageHandler
from telegram.ext import CommandHandler
from telegram.ext import CallbackQueryHandler
from telegram.ext import filters
from telegram.error import BadRequest
from telegram.error import TelegramError
from telegram.constants import ChatAction

# Import từ các module khác (tuyệt đối)
from config import TEMP_UPLOAD_DIR
from config import WAITING_NEW_SET_UPLOAD # State
from config import CAN_UPLOAD_SET # Quyền
from database.query_user import get_user_by_telegram_id
from services.excel_service import import_new_set_from_excel # Service xử lý excel
from utils.helpers import send_or_edit_message
from utils.helpers import require_permission # Decorator kiểm tra quyền
from utils.exceptions import DatabaseError
from utils.exceptions import UserNotFoundError
from utils.exceptions import FileProcessingError
from utils.exceptions import ExcelImportError
from utils.exceptions import InvalidFileFormatError
from ui.core_ui import build_main_menu # Dùng cho nút quay lại khi hủy

# Khởi tạo logger
logger = logging.getLogger(__name__)

@require_permission(CAN_UPLOAD_SET)
async def handle_start_upload_set(update, context):
    """
    Entry Point: Bắt đầu conversation để upload bộ từ mới.
    Có thể được gọi từ lệnh /flashcard_upload hoặc callback trigger_upload.
    """
    # Code giữ nguyên như trước
    if not update or not update.effective_user: logger.warning("handle_start_upload_set: update/user không hợp lệ."); return ConversationHandler.END
    user_id_tg = update.effective_user.id; log_prefix = "[UPLOAD_START|UserTG:{}]".format(user_id_tg); chat_id_to_reply = -1; message_to_edit = None; source = "Unknown"
    if update.callback_query:
        source = "Callback(trigger_upload)"; query = update.callback_query
        try: await query.answer()
        except Exception as e_ans: logger.warning("{} Lỗi answer callback: {}".format(log_prefix, e_ans))
        if query.message: chat_id_to_reply = query.message.chat_id; message_to_edit = query.message
        else: chat_id_to_reply = user_id_tg
    elif update.message: source = "Command(/flashcard_upload)"; chat_id_to_reply = update.message.chat_id; message_to_edit = None
    else: logger.warning("{} Nguồn kích hoạt không xác định.".format(log_prefix)); return ConversationHandler.END
    logger.info("{} Bắt đầu conversation upload từ {}.".format(log_prefix, source)); cancel_button = InlineKeyboardButton("🚫 Hủy Upload", callback_data="cancel_new_set_upload"); cancel_keyboard = InlineKeyboardMarkup([[cancel_button]])
    sent_msg = await send_or_edit_message( context=context, chat_id=chat_id_to_reply, text="📤 Vui lòng gửi file Excel (.xlsx) chứa bộ từ vựng mới của bạn.\n\n(Nhấn Hủy hoặc gõ /cancel để hủy)", reply_markup=cancel_keyboard, message_to_edit=message_to_edit)
    if sent_msg: logger.debug("{} Đã gửi yêu cầu file, chuyển state WAITING_NEW_SET_UPLOAD.".format(log_prefix)); return WAITING_NEW_SET_UPLOAD
    else: logger.error("{} Lỗi gửi/sửa tin nhắn yêu cầu file.".format(log_prefix)); return ConversationHandler.END

async def _state_handle_new_set_file(update, context):
    """
    Handler cho state WAITING_NEW_SET_UPLOAD khi nhận được file Excel hợp lệ.
    Đã sửa lỗi escape Markdown cho tên bộ từ trong tin nhắn xác nhận.
    """
    # Code kiểm tra đầu vào, tải file giữ nguyên như trước
    if not update or not update.message or not update.effective_user or not update.message.document: logger.warning("_state_handle_new_set_file: update/message/user/document không hợp lệ."); return WAITING_NEW_SET_UPLOAD
    telegram_id = update.effective_user.id; chat_id = update.message.chat_id; log_prefix = "[UPLOAD_PROCESS_FILE|UserTG:{}]".format(telegram_id); logger.info("{} Nhận file document.".format(log_prefix)); document = update.message.document; actual_creator_user_id = None; file_path = None; upload_dir = TEMP_UPLOAD_DIR; loop = asyncio.get_running_loop(); processing_message = None
    if document.mime_type not in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",): logger.warning("{} File type không hợp lệ: {}".format(log_prefix, document.mime_type)); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ File không hợp lệ. Vui lòng upload file Excel (.xlsx) hoặc /cancel."); return WAITING_NEW_SET_UPLOAD
    try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception as e_action: logger.warning("{} Lỗi gửi chat action: {}".format(log_prefix, e_action))
    try:
        logger.debug("{} Lấy user_id...".format(log_prefix)); user_info = get_user_by_telegram_id(telegram_id); actual_creator_user_id = user_info['user_id']; logger.debug("{} Lấy được creator_user_id: {}".format(log_prefix, actual_creator_user_id))
        file = await document.get_file(); timestamp = int(time.time()); original_filename = document.file_name or "new_set"; safe_original_filename = "".join(c for c in original_filename if c.isalnum() or c in ['.','_','-']).strip()
        if not safe_original_filename: safe_original_filename = "new_set.xlsx"
        os.makedirs(upload_dir, exist_ok=True); file_path = os.path.join(upload_dir, "upload_{}_{}_{}".format(telegram_id, timestamp, safe_original_filename)); await file.download_to_drive(custom_path=file_path); logger.info("{} Đã tải file về: {}".format(log_prefix, file_path))
    except (UserNotFoundError, DatabaseError) as e_user_db: logger.error("{} Lỗi DB/User khi lấy user_id: {}".format(log_prefix, e_user_db)); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải thông tin người dùng. Đã hủy upload."); return ConversationHandler.END
    except (BadRequest, TelegramError) as e_telegram: logger.error("{} Lỗi Telegram khi tải file: {}".format(log_prefix, e_telegram)); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi Telegram khi tải file: {}\nVui lòng thử lại hoặc /cancel.".format(e_telegram)); return WAITING_NEW_SET_UPLOAD
    except OSError as e_os: logger.error("{} Lỗi OS khi tạo thư mục/ghi file: {}".format(log_prefix, e_os)); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hệ thống khi lưu file tạm. Đã hủy upload."); return ConversationHandler.END
    except Exception as e_download:
        logger.error("{} Lỗi tải file khác: {}".format(log_prefix, e_download), exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi không mong muốn khi tải file về server. Đã hủy upload.");
        if file_path and os.path.exists(file_path):
            try: await loop.run_in_executor(None, os.remove, file_path)
            except Exception as e_remove_err: logger.error("{} Lỗi xóa file tạm (lỗi tải): {}".format(log_prefix, e_remove_err))
        return ConversationHandler.END
    processing_message = await send_or_edit_message(context=context, chat_id=chat_id, text="⏳ Đang xử lý file Excel và import bộ từ...")
    if not processing_message: logger.error("{} Lỗi gửi tin nhắn chờ.".format(log_prefix)); processing_message = None
    set_id = None; dict_title = "Không xác định"; count = 0; error_msg_svc = None
    try:
        logger.debug("{} Gọi service import_new_set_from_excel với creator_user_id={}...".format(log_prefix, actual_creator_user_id))
        result_tuple = await loop.run_in_executor(None, import_new_set_from_excel, file_path, actual_creator_user_id)
        set_id, dict_title, count = result_tuple
        logger.debug("{} Service trả về: id={}, title='{}', count={}".format(log_prefix, set_id, dict_title, count))
        if set_id is not None:
            logger.info("{} Import thành công set_id {}.".format(log_prefix, set_id))
            markdown_v2_chars_to_escape = r"[_*\[\]()~`>#\+\-=|{}.!]"
            escaped_title = re.sub(r'([{}])'.format(re.escape(markdown_v2_chars_to_escape)), r'\\\1', dict_title)
            logger.debug("{}: Tiêu đề gốc: '{}', Tiêu đề đã escape Markdown: '{}'".format(log_prefix, dict_title, escaped_title))
            # Escape ký tự cố định trong text
            result_message = (
                f"✅ Đã thêm thành công bộ từ '**{escaped_title}**' với **{count}** thẻ\.\n" # Escape .
                f"📚 Dùng lệnh /flashcard để bắt đầu học\!" # Escape !
            )
            await send_or_edit_message(context=context, chat_id=chat_id, text=result_message, parse_mode='MarkdownV2', message_to_edit=processing_message)
        else:
            error_msg_svc = dict_title; logger.error("{} Import thất bại: {}".format(log_prefix, error_msg_svc)); escaped_error = html.escape(str(error_msg_svc)); error_message = "⚠️ Lỗi khi xử lý file:\n`{}`".format(escaped_error)
            await send_or_edit_message(context=context, chat_id=chat_id, text=error_message, parse_mode='Markdown', message_to_edit=processing_message)
    except (FileProcessingError, InvalidFileFormatError, ExcelImportError, DatabaseError) as e_service: logger.exception("{} Lỗi khi gọi/xử lý service import: {}".format(log_prefix, e_service)); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi xử lý file: {}".format(e_service), message_to_edit=processing_message)
    except Exception as e_service_unk: logger.exception("{} Lỗi không mong muốn khi gọi service import: {}".format(log_prefix, e_service_unk)); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hệ thống nghiêm trọng khi import.", message_to_edit=processing_message)
    finally:
        if file_path:
            try:
                 def remove_if_exists_sync(path_to_remove):
                     if os.path.exists(path_to_remove): os.remove(path_to_remove); return True
                     return False
                 removed = await loop.run_in_executor(None, remove_if_exists_sync, file_path)
                 if removed: logger.info("{} Đã xóa file tạm upload: {}".format(log_prefix, file_path))
            except Exception as e_remove: logger.error("{} Lỗi xóa file tạm upload {}: {}".format(log_prefix, file_path, e_remove))
    return ConversationHandler.END

# Các hàm _state_handle_new_set_unexpected và _handle_cancel_new_set_upload giữ nguyên
async def _state_handle_new_set_unexpected(update, context):
    # Giữ nguyên code
    if not update or not update.message: return WAITING_NEW_SET_UPLOAD
    user_id_tg = update.effective_user.id if update.effective_user else -1; chat_id = update.message.chat_id; log_prefix = "[UPLOAD_UNEXPECTED|UserTG:{}]".format(user_id_tg)
    input_type = "văn bản";
    if update.message.effective_attachment: input_type = "file không phải Excel"
    logger.warning("{} Nhận input không mong muốn: {}".format(log_prefix, input_type)); await send_or_edit_message(context=context, chat_id=chat_id, text="⚠️ Đang chờ file Excel (.xlsx).\nVui lòng gửi đúng định dạng file hoặc nhấn Hủy / gõ /cancel."); return WAITING_NEW_SET_UPLOAD

async def _handle_cancel_new_set_upload(update, context):
    # Giữ nguyên code
    if not update or not update.effective_user: return ConversationHandler.END
    user_id_tg = update.effective_user.id; log_prefix = "[UPLOAD_CANCEL|UserTG:{}]".format(user_id_tg); logger.info("{} Hủy upload bộ từ mới.".format(log_prefix)); context.user_data.pop("target_set_id_for_update", None); message_to_edit_cancel = None; chat_id_cancel = user_id_tg; parse_mode_cancel = None
    if update.callback_query:
        query = update.callback_query;
        try: await query.answer()
        except Exception: pass
        if query.message: message_to_edit_cancel = query.message; chat_id_cancel = query.message.chat_id
    elif update.message: chat_id_cancel = update.message.chat_id
    logger.debug("{} Đang build và hiển thị menu chính...".format(log_prefix))
    try:
        bot_instance_cancel = context.bot if hasattr(context, 'bot') else (context.application.bot if context.application and hasattr(context.application, 'bot') else None)
        text = "Đã hủy thao tác upload."; reply_markup = None
        if bot_instance_cancel:
            text_menu, reply_markup_menu = await build_main_menu(user_id_tg, bot_instance_cancel)
            if text_menu and reply_markup_menu: text = text_menu; reply_markup = reply_markup_menu; parse_mode_cancel = 'Markdown'
            else: logger.warning("{} Lỗi build menu chính khi hủy.".format(log_prefix)); text = "Đã hủy. Có lỗi khi tải menu chính."
        else: logger.error("{} Không có bot instance để build menu chính.".format(log_prefix)); text = "Đã hủy. Lỗi hệ thống."
        await send_or_edit_message( context=context, chat_id=chat_id_cancel, text=text, reply_markup=reply_markup, parse_mode=parse_mode_cancel, message_to_edit=message_to_edit_cancel )
        logger.info("{} Đã hiển thị menu chính sau khi hủy upload.".format(log_prefix))
    except Exception as e_menu: logger.error("{} Lỗi khi hiển thị menu chính sau khi hủy: {}".format(log_prefix, e_menu), exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id_cancel, text="Đã hủy. Lỗi hiển thị menu.", message_to_edit=message_to_edit_cancel, reply_markup=None)
    return ConversationHandler.END

# === SỬA LỖI: Thay đổi per_message thành False ===
upload_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("flashcard_upload", handle_start_upload_set),
        CallbackQueryHandler(handle_start_upload_set, pattern='^trigger_upload$')
    ],
    states={
        WAITING_NEW_SET_UPLOAD: [
            MessageHandler(filters.Document.FileExtension("xlsx"), _state_handle_new_set_file),
            MessageHandler(filters.TEXT & ~filters.COMMAND, _state_handle_new_set_unexpected),
            MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT & ~filters.Document.FileExtension("xlsx"), _state_handle_new_set_unexpected)
        ],
    },
    fallbacks=[
        CommandHandler("cancel", _handle_cancel_new_set_upload),
        CallbackQueryHandler(_handle_cancel_new_set_upload, pattern='^cancel_new_set_upload$')
    ],
    name="new_set_upload_conversation",
    persistent=False,
    per_message=False # <<< THAY ĐỔI Ở ĐÂY
)
# ===========================================

def register_handlers(app: Application):
    """Đăng ký Conversation Handler cho chức năng upload bộ từ mới."""
    app.add_handler(upload_conv_handler)
    logger.info("Đã đăng ký các handler cho module Data Import Upload.")