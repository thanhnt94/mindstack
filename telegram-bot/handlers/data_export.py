# File: flashcard-telegram-bot/handlers/data_export.py
"""
Module chứa các handlers cho chức năng xuất dữ liệu (export) ra file Excel.
(Sửa lần 1: Điều chỉnh handle_export_all_data_set_command để xử lý callback query,
             gửi tin nhắn với parse_mode=None.)
"""
import logging
import os
import asyncio
import time
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackQueryHandler 
from telegram.error import TelegramError, BadRequest, Forbidden
from telegram.constants import ChatAction

from config import EXPORT_SET_CALLBACK_PREFIX, TEMP_EXPORT_DIR, CAN_EXPORT_SET 
from database.query_set import get_sets 
from database.query_user import get_user_by_telegram_id 
from services.excel_service import export_user_data_excel, export_set_data_excel 
from utils.helpers import send_or_edit_message, require_permission 
from utils.exceptions import ( 
    DatabaseError, UserNotFoundError, SetNotFoundError, PermissionsError
)
logger = logging.getLogger(__name__)

@require_permission(CAN_EXPORT_SET) 
async def handle_export_all_data(update, context):
    # Giữ nguyên logic
    telegram_id = None; chat_id = None; log_prefix_base = "[DATA_EXPORT_ALL]"; is_callback = False; message_to_edit = None; output_filepath = None; loop = asyncio.get_running_loop(); status_message_obj = None; actual_user_id = None
    if update.callback_query and update.callback_query.from_user: 
        query = update.callback_query; telegram_id = query.from_user.id; message_to_edit = query.message; chat_id = query.message.chat_id if query.message else telegram_id; is_callback = True
        try: 
            await query.answer("Đang chuẩn bị file export...") 
        except Exception : pass
    elif update.message and update.effective_user: telegram_id = update.effective_user.id; chat_id = update.message.chat_id; message_to_edit = None; is_callback = False
    else: logger.error(f"{log_prefix_base} Không thể xác định user_id/chat_id."); return 
    log_prefix = f"{log_prefix_base}[UserTG:{telegram_id}]"; logger.info(f"{log_prefix} Yêu cầu export all (Callback: {is_callback}).")
    if chat_id: 
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        except Exception : pass
    try:
        wait_message = f"⏳ Đang xuất toàn bộ dữ liệu học tập của bạn... Việc này có thể mất một chút thời gian. Xin chờ..."
        status_message_obj = await send_or_edit_message(context=context, chat_id=chat_id, text=wait_message, message_to_edit=message_to_edit, reply_markup=None )
        user_info = get_user_by_telegram_id(telegram_id); actual_user_id = user_info['user_id']
        username = str(telegram_id); user_tg_username = user_info.get("username")
        if user_tg_username: 
            safe_username = "".join(c for c in user_tg_username if c.isalnum() or c in ('_', '-')).strip();
            if safe_username: username = safe_username
        temp_export_dir = TEMP_EXPORT_DIR; os.makedirs(temp_export_dir, exist_ok=True) 
        output_filename = f"flashcard_data_{username}_{int(time.time())}.xlsx"; output_filepath = os.path.join(temp_export_dir, output_filename)
        success = await loop.run_in_executor(None, export_user_data_excel, actual_user_id, output_filepath)
        final_status_text = ""; file_sent = False 
        if success:
            file_exists = await loop.run_in_executor(None, os.path.exists, output_filepath)
            if file_exists:
                try:
                    with open(output_filepath, "rb") as file_to_send_obj: await context.bot.send_document(chat_id=chat_id, document=file_to_send_obj, filename=f"DuLieuHocTap_{username}.xlsx" )
                    file_sent = True
                    if status_message_obj: 
                        try: await context.bot.delete_message(chat_id=status_message_obj.chat.id, message_id=status_message_obj.message_id)
                        except Exception : pass
                except (Forbidden, BadRequest, TelegramError) as send_err_tg: final_status_text = f"❌ Xuất dữ liệu thành công nhưng có lỗi khi gửi file: {send_err_tg}"
                except Exception as send_err:  final_status_text = f"❌ Xuất dữ liệu thành công nhưng có lỗi khi gửi file: {send_err}"
            else: final_status_text = "❌ Lỗi: File kết quả không được tạo ra sau khi export."
        else: final_status_text = "ℹ️ Không có dữ liệu để xuất hoặc đã có lỗi xảy ra trong quá trình tạo file."
        if final_status_text and status_message_obj: await send_or_edit_message(context=context, chat_id=chat_id, text=final_status_text, message_to_edit=status_message_obj, reply_markup=None)
        elif final_status_text: await send_or_edit_message(context=context, chat_id=chat_id, text=final_status_text)
    except (UserNotFoundError, DatabaseError) as e_user_db: await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải thông tin người dùng.", message_to_edit=status_message_obj)
    except OSError as e_os: await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hệ thống: Không thể tạo file tạm thời.", message_to_edit=status_message_obj)
    except Exception as e: error_msg = "❌ Lỗi không mong muốn khi xuất dữ liệu."; await send_or_edit_message(context=context, chat_id=chat_id, text=error_msg, message_to_edit=status_message_obj)
    finally:
        if output_filepath and os.path.exists(output_filepath): 
            try: await loop.run_in_executor(None, os.remove, output_filepath)
            except Exception : pass

@require_permission(CAN_EXPORT_SET) 
async def handle_export_all_data_set_command(update, context):
    """
    Sửa lần 1: Handler này giờ được gọi từ callback của menu "Quản lý bộ thẻ".
    Hiển thị danh sách các bộ từ do người dùng tạo để chọn export.
    """
    query = None
    if update.callback_query: # Được gọi từ callback
        query = update.callback_query
        try: await query.answer()
        except Exception: pass
        telegram_id = query.from_user.id
        chat_id = query.message.chat_id
        message_to_edit = query.message # Tin nhắn menu "Quản lý bộ thẻ" để sửa
        log_prefix = f"[DATA_EXPORT_SET_CB_SELECT|UserTG:{telegram_id}]"
        logger.info(f"{log_prefix} Yêu cầu chọn bộ để export từ callback.")
    elif update.message and update.effective_user : # Được gọi từ lệnh (giữ lại)
        telegram_id = update.effective_user.id
        chat_id = update.message.chat_id
        message_to_edit = None 
        log_prefix = f"[DATA_EXPORT_SET_CMD|UserTG:{telegram_id}]"
        logger.info(f"{log_prefix} Lệnh /handle_export_all_data_set.")
    else:
        logger.warning("handle_export_all_data_set_command: update không hợp lệ.")
        return

    actual_user_id = None
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception as e_action:
        logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")
    try:
        user_info = get_user_by_telegram_id(telegram_id)
        if not user_info or 'user_id' not in user_info: raise UserNotFoundError(identifier=telegram_id)
        actual_user_id = user_info['user_id']
        
        user_sets, total_sets = get_sets(columns=['set_id', 'title'], creator_user_id=actual_user_id)
        if not user_sets:
            await send_or_edit_message(context=context, chat_id=chat_id, text="Bạn chưa tạo bộ thẻ nào để có thể export.", message_to_edit=message_to_edit)
            return

        keyboard = []
        for s_item in user_sets: # Đổi tên biến lặp
            set_id_val = s_item.get('set_id'); set_title_val = s_item.get('title', f'Bộ {set_id_val}')
            if set_id_val is not None:
                 callback_data = f"{EXPORT_SET_CALLBACK_PREFIX}{set_id_val}"
                 keyboard.append([InlineKeyboardButton(f"📋 {html.escape(set_title_val)}", callback_data=callback_data)])
        
        # Nút quay lại menu quản lý bộ thẻ
        keyboard.append([InlineKeyboardButton("🔙 Quay lại Menu Quản lý", callback_data="show_set_management")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Sửa lần 1: Gửi text thuần
        text_to_send = "Chọn bộ thẻ bạn muốn xuất dữ liệu:"
        sent_msg = await send_or_edit_message(
            context=context, chat_id=chat_id, text=text_to_send, reply_markup=reply_markup,
            message_to_edit=message_to_edit, parse_mode=None 
        )
        if not sent_msg:
            logger.error(f"{log_prefix} Lỗi gửi/sửa bàn phím chọn bộ export.")
            
    except (UserNotFoundError, DatabaseError) as e:
        logger.error(f"{log_prefix} Lỗi DB/User khi lấy list set: {e}")
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải danh sách bộ thẻ của bạn.", message_to_edit=message_to_edit)
    except Exception as e:
         logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
         await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

async def handle_callback_export_set_select(update, context):
    # Giữ nguyên logic
    query = update.callback_query
    if not query or not query.data or not query.from_user: return
    telegram_id = query.from_user.id; chat_id = query.message.chat_id if query.message else telegram_id
    log_prefix = f"[DATA_EXPORT_SET_CB|UserTG:{telegram_id}]"; loop = asyncio.get_running_loop()
    output_filepath = None; status_message_obj = None; set_id = None; set_title = "Không xác định"; actual_exporter_user_id = None
    try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
    except Exception : pass
    try: await query.answer("Chuẩn bị file export...")
    except Exception : pass
    try:
        if not query.data.startswith(EXPORT_SET_CALLBACK_PREFIX): raise ValueError("Callback data prefix không khớp")
        set_id_str = query.data[len(EXPORT_SET_CALLBACK_PREFIX):]; set_id = int(set_id_str)
        user_info = get_user_by_telegram_id(telegram_id); actual_exporter_user_id = user_info['user_id']
        set_info_tuple = get_sets(columns=["title", "creator_user_id"], set_id=set_id); set_info = set_info_tuple[0][0] if set_info_tuple and set_info_tuple[0] else None
        if not set_info: raise SetNotFoundError(set_id=set_id) 
        set_creator_id = set_info.get('creator_user_id')
        if set_creator_id != actual_exporter_user_id: raise PermissionsError(message=f"Bạn không phải người tạo bộ thẻ này.")
        set_title = set_info.get('title', f"Bộ {set_id}"); escaped_set_title = html.escape(set_title)
        processing_text = f"⏳ Đang chuẩn bị xuất bộ thẻ '**{escaped_set_title}**'... Xin chờ một lát..."
        status_message_obj = await send_or_edit_message(context=context, chat_id=chat_id, text=processing_text, parse_mode='Markdown', reply_markup=None, message_to_edit=query.message )
        temp_export_dir = TEMP_EXPORT_DIR; os.makedirs(temp_export_dir, exist_ok=True)
        safe_title = "".join(c for c in set_title if c.isalnum() or c in ('_', '-')).strip() or f"set_{set_id}"
        output_filename = f"export_{safe_title}_{telegram_id}_{int(time.time())}.xlsx"; output_filepath = os.path.join(temp_export_dir, output_filename)
        export_success = await loop.run_in_executor(None, export_set_data_excel, actual_exporter_user_id, set_id, output_filepath)
        final_status_text = f"❌ Lỗi không xác định khi xuất bộ thẻ '**{escaped_set_title}**'."; file_sent_successfully = False
        if export_success:
            file_exists = await loop.run_in_executor(None, os.path.exists, output_filepath)
            if file_exists:
                try:
                    with open(output_filepath, 'rb') as file_to_send_obj: await context.bot.send_document(chat_id=chat_id, document=file_to_send_obj, filename=f"{safe_title}_export.xlsx" )
                    final_status_text = ""; file_sent_successfully = True
                    if status_message_obj: 
                        try: await context.bot.delete_message(chat_id=status_message_obj.chat.id, message_id=status_message_obj.message_id)
                        except Exception : pass
                except (Forbidden, BadRequest, TelegramError) as send_err_tg: final_status_text = f"❌ Xuất thành công nhưng lỗi gửi file: {send_err_tg}"
                except Exception as send_err:  final_status_text = f"❌ Xuất thành công nhưng lỗi gửi file: {send_err}"
            else: final_status_text = "❌ Lỗi: File kết quả không được tạo ra."
        else:
            if not final_status_text: final_status_text = f"❌ Không thể xuất bộ thẻ '**{escaped_set_title}**' (kiểm tra log service)."
    except (ValueError, IndexError, TypeError) as e_parse: final_status_text = "❌ Lỗi: Dữ liệu callback không hợp lệ."
    except (UserNotFoundError, SetNotFoundError, PermissionsError, DatabaseError) as e_known: error_msg = f"❌ Lỗi: {e_known.message}" if hasattr(e_known, 'message') and e_known.message else f"❌ Có lỗi xảy ra ({type(e_known).__name__})."; final_status_text = error_msg 
    except OSError as e_os: final_status_text = "❌ Lỗi hệ thống: Không thể tạo file tạm thời."
    except Exception as e: escaped_title_err = html.escape(set_title); final_status_text = f"❌ Lỗi nghiêm trọng khi xuất '**{escaped_title_err}**'."
    finally:
        if final_status_text and not file_sent_successfully:
            kb_back_manage = [[InlineKeyboardButton("🔙 Menu Quản lý", callback_data="show_set_management")]]; markup_final = InlineKeyboardMarkup(kb_back_manage)
            await send_or_edit_message(context=context, chat_id=chat_id, text=final_status_text, reply_markup=markup_final, parse_mode='Markdown', message_to_edit=status_message_obj )
        if output_filepath and os.path.exists(output_filepath): 
            try: await loop.run_in_executor(None, os.remove, output_filepath)
            except Exception : pass

def register_handlers(app: Application):
    app.add_handler(CommandHandler("handle_export_all_data_set", handle_export_all_data_set_command)) # Giữ lại lệnh nếu cần
    app.add_handler(CallbackQueryHandler(handle_callback_export_set_select, pattern=f"^{EXPORT_SET_CALLBACK_PREFIX}"))
    app.add_handler(CommandHandler("handle_export_all_data", handle_export_all_data))
    app.add_handler(CallbackQueryHandler(handle_export_all_data, pattern=r"^do_export$")) 
    logger.info("Đã đăng ký các handler cho module Data Export.")

