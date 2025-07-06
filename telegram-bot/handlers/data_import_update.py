# File: flashcard-telegram-bot/handlers/data_import_update.py
"""
Module chứa handlers và conversation handler cho chức năng
cập nhật bộ từ vựng đã có từ file Excel.
(Sửa lần 1: Điều chỉnh handle_command_update_set để xử lý callback query,
             gửi tin nhắn với parse_mode=None.)
"""
import logging
import os
import time
import asyncio
import html
import re 

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters
)
from telegram.error import BadRequest, TelegramError
from telegram.constants import ChatAction, ParseMode

from config import TEMP_UPDATE_DIR, UPDATE_SET_CALLBACK_PREFIX, WAITING_FOR_UPDATE_FILE, CAN_UPLOAD_SET
from database.query_set import get_sets
from database.query_user import get_user_by_telegram_id
from services.excel_service import process_set_update_from_excel
from utils.helpers import send_or_edit_message, require_permission, escape_md_v2
from utils.exceptions import (
    DatabaseError, SetNotFoundError, UserNotFoundError, FileProcessingError,
    ExcelImportError, PermissionsError, InvalidFileFormatError
)
from ui.core_ui import build_set_management_keyboard # Không dùng trực tiếp nhưng có thể cần cho cancel

logger = logging.getLogger(__name__)

@require_permission(CAN_UPLOAD_SET) # Quyền này có thể cần xem lại, có thể là CAN_MANAGE_OWN_SETS
async def handle_command_update_set(update, context):
    """
    Sửa lần 1: Handler này giờ được gọi từ callback của menu "Quản lý bộ thẻ".
    Hiển thị danh sách các bộ từ do người dùng tạo để chọn cập nhật.
    """
    query = None
    if update.callback_query: # Được gọi từ callback
        query = update.callback_query
        try: await query.answer()
        except Exception: pass
        telegram_id = query.from_user.id
        chat_id = query.message.chat_id
        message_to_edit = query.message # Tin nhắn menu "Quản lý bộ thẻ" để sửa
        log_prefix = f"[DATA_UPDATE_CB_SELECT_SET|UserTG:{telegram_id}]"
        logger.info(f"{log_prefix} Yêu cầu chọn bộ để cập nhật từ callback.")
    elif update.message and update.effective_user : # Được gọi từ lệnh (giữ lại phòng trường hợp dùng lệnh)
        telegram_id = update.effective_user.id
        chat_id = update.message.chat_id
        message_to_edit = None 
        log_prefix = f"[DATA_UPDATE_CMD|UserTG:{telegram_id}]"
        logger.info(f"{log_prefix} Lệnh /flashcard_update_set.")
    else:
        logger.warning("handle_command_update_set: update không hợp lệ.")
        return ConversationHandler.END # Hoặc giá trị phù hợp nếu không trong conversation

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
            await send_or_edit_message(context=context, chat_id=chat_id, text="Bạn chưa tạo bộ thẻ nào để có thể cập nhật.", message_to_edit=message_to_edit)
            return ConversationHandler.END # Kết thúc nếu không có bộ nào

        keyboard = []
        for s_item in user_sets: # Đổi tên biến lặp
            set_id = s_item.get('set_id'); title = s_item.get('title', f"Bộ không tên {set_id}")
            if set_id is None: continue
            callback_data = f"{UPDATE_SET_CALLBACK_PREFIX}{set_id}"
            keyboard.append([InlineKeyboardButton(f"📚 {html.escape(title)}", callback_data=callback_data)])

        # Nút quay lại menu quản lý bộ thẻ
        keyboard.append([InlineKeyboardButton("🔙 Quay lại Menu Quản lý", callback_data="show_set_management")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Sửa lần 1: Gửi text thuần, không dùng MarkdownV2 ở đây
        text_to_send = "Chọn bộ thẻ bạn muốn cập nhật dữ liệu:"
        sent_msg = await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text=text_to_send,
            reply_markup=reply_markup,
            message_to_edit=message_to_edit, # Sửa tin nhắn menu "Quản lý bộ thẻ"
            parse_mode=None # Gửi text thuần
        )
        if not sent_msg:
            logger.error(f"{log_prefix} Lỗi gửi/sửa bàn phím chọn bộ update.")
        # Không trả về state của conversation ở đây nếu đây chỉ là bước chọn bộ
        # Logic bắt đầu conversation sẽ nằm ở handle_callback_update_set_select
        return # Kết thúc hàm này, chờ người dùng chọn bộ

    except (UserNotFoundError, DatabaseError) as e:
        logger.error(f"{log_prefix} Lỗi DB/User khi lấy list set: {e}")
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải danh sách bộ thẻ của bạn.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)
    return ConversationHandler.END # Đảm bảo trả về END nếu có lỗi không mong muốn

# Các hàm còn lại của Conversation (handle_callback_update_set_select, _handle_state_update_set_file, etc.)
# giữ nguyên logic, chỉ cần đảm bảo chúng được gọi đúng cách và xử lý message_to_edit phù hợp.

async def handle_callback_update_set_select(update, context):
    # Giữ nguyên logic
    query = update.callback_query;
    if not query or not query.data or not query.from_user: return ConversationHandler.END
    user_id_tg = query.from_user.id; log_prefix = f"[DATA_UPDATE_SELECT|UserTG:{user_id_tg}]"
    target_set_id = None; chat_id_to_reply = query.message.chat_id if query.message else user_id_tg
    message_to_edit = query.message
    if chat_id_to_reply: 
        try: await context.bot.send_chat_action(chat_id=chat_id_to_reply, action=ChatAction.TYPING)
        except Exception : pass
    try: await query.answer()
    except Exception : pass
    try:
        if not query.data.startswith(UPDATE_SET_CALLBACK_PREFIX): raise ValueError("Prefix callback không khớp.")
        set_id_str = query.data[len(UPDATE_SET_CALLBACK_PREFIX):]; target_set_id = int(set_id_str)
        logger.info(f"{log_prefix} User chọn update Set ID: {target_set_id}")
        set_info_tuple = get_sets(columns=["title"], set_id=target_set_id); set_info = set_info_tuple[0][0] if set_info_tuple and set_info_tuple[0] else None
        if not set_info: raise SetNotFoundError(set_id=target_set_id)
        set_title = set_info.get('title', f"Bộ {target_set_id}")
        escaped_title = escape_md_v2(set_title)
        context.user_data['target_set_id_for_update'] = target_set_id
        cancel_button = InlineKeyboardButton("🚫 Hủy Cập Nhật", callback_data="cancel_update_set"); cancel_keyboard = InlineKeyboardMarkup([[cancel_button]])
        request_message = (f"✅ Đã chọn bộ: **{escaped_title}** \\(ID: {target_set_id}\\)\\.\n\n"
                           f"Bây giờ, hãy gửi file Excel \\(\\.xlsx\\) chứa dữ liệu cập nhật\\.\n"
                           f"\\_\\(File nên có cột 'flashcard\\_id' để xác định thẻ cần sửa, các thẻ không có ID hoặc ID không tồn tại/không thuộc bộ này sẽ được thêm mới nếu hợp lệ\\)\\_\\_\n\n"
                           f"\\(Nhấn Hủy hoặc gõ /cancel để hủy\\)")
        sent_msg = await send_or_edit_message(context=context, chat_id=chat_id_to_reply, text=request_message, reply_markup=cancel_keyboard, parse_mode=ParseMode.MARKDOWN_V2, message_to_edit=message_to_edit)
        if sent_msg: return WAITING_FOR_UPDATE_FILE
        else: context.user_data.pop('target_set_id_for_update', None); return ConversationHandler.END
    except (ValueError, IndexError, AttributeError) as e_parse: logger.error(f"{log_prefix} Lỗi parse callback data '{query.data}': {e_parse}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id_to_reply, text="❌ Lỗi: Dữ liệu callback không hợp lệ.", message_to_edit=message_to_edit); return ConversationHandler.END
    except SetNotFoundError: logger.warning(f"{log_prefix} Không tìm thấy set ID {target_set_id}."); await send_or_edit_message(context=context, chat_id=chat_id_to_reply, text=f"❌ Không tìm thấy bộ thẻ ID {target_set_id}.", message_to_edit=message_to_edit); return ConversationHandler.END
    except DatabaseError as e_db: logger.error(f"{log_prefix} Lỗi DB: {e_db}"); await send_or_edit_message(context=context, chat_id=chat_id_to_reply, text="❌ Lỗi tải thông tin bộ thẻ.", message_to_edit=message_to_edit); return ConversationHandler.END
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); context.user_data.pop('target_set_id_for_update', None); await send_or_edit_message(context=context, chat_id=chat_id_to_reply, text="❌ Đã có lỗi xảy ra.", message_to_edit=message_to_edit); return ConversationHandler.END

async def _handle_state_update_set_file(update, context):
    # Giữ nguyên logic
    if not update or not update.message or not update.effective_user or not update.message.document: return WAITING_FOR_UPDATE_FILE
    telegram_id = update.effective_user.id; chat_id = update.message.chat_id; log_prefix = f"[DATA_UPDATE_PROCESS|UserTG:{telegram_id}]"; logger.info(f"{log_prefix} Nhận file document để update.")
    document = update.message.document; loop = asyncio.get_running_loop(); file_path = None; processing_message = None; actual_updater_user_id = None
    if document.mime_type not in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",): await send_or_edit_message(context=context, chat_id=chat_id, text="⚠️ Chỉ chấp nhận file Excel (.xlsx). Vui lòng gửi lại hoặc gõ /cancel."); return WAITING_FOR_UPDATE_FILE
    target_set_id = context.user_data.get('target_set_id_for_update')
    if not target_set_id: await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi: Thiếu thông tin bộ thẻ cần cập nhật. Vui lòng thử lại từ đầu."); return ConversationHandler.END
    try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception : pass
    temp_dir = TEMP_UPDATE_DIR; results = {'updated': 0, 'added': 0, 'skipped': 0, 'errors': []}
    try:
        user_info = get_user_by_telegram_id(telegram_id); actual_updater_user_id = user_info['user_id']
        file = await document.get_file(); timestamp = int(time.time()); original_filename = document.file_name or f"update_set_{target_set_id}"
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in ['.','_','-']).strip() or f"update_set_{target_set_id}.xlsx"
        os.makedirs(temp_dir, exist_ok=True); file_path = os.path.join(temp_dir, f"update_{telegram_id}_{target_set_id}_{timestamp}_{safe_filename}"); await file.download_to_drive(custom_path=file_path)
    except (UserNotFoundError, DatabaseError) as e_user_db: await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải thông tin người dùng. Đã hủy cập nhật."); context.user_data.pop('target_set_id_for_update', None); return ConversationHandler.END
    except (BadRequest, TelegramError) as e_telegram: await send_or_edit_message(context=context, chat_id=chat_id, text=f"❌ Lỗi Telegram khi tải file: {e_telegram}"); return WAITING_FOR_UPDATE_FILE
    except OSError as e_os: await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hệ thống khi lưu file tạm."); context.user_data.pop('target_set_id_for_update', None); return ConversationHandler.END
    except Exception as e_download:
        if file_path and os.path.exists(file_path): 
            try: await loop.run_in_executor(None, os.remove, file_path)
            except Exception : pass
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi không mong muốn khi tải file update."); context.user_data.pop('target_set_id_for_update', None); return ConversationHandler.END
    processing_message = await send_or_edit_message(context=context, chat_id=chat_id, text=f"⏳ Đang xử lý file và cập nhật bộ thẻ (ID: {target_set_id})...")
    try: results = await loop.run_in_executor(None, process_set_update_from_excel, actual_updater_user_id, target_set_id, file_path)
    except (FileProcessingError, InvalidFileFormatError, ExcelImportError, DatabaseError, PermissionsError, SetNotFoundError) as e_service: results['errors'].append({'line': 'Service', 'reason': f'Lỗi service: {e_service}', 'card_info': ''})
    except Exception as e_service_unk: results['errors'].append({'line': 'Service', 'reason': f'Lỗi service không xác định: {e_service_unk}', 'card_info': ''})
    final_report = "";
    try:
        report_lines = [f"✅ **Kết quả cập nhật bộ thẻ (ID: {target_set_id}):**\n"]
        report_lines.append(f"🔄 Cập nhật thành công: **{results.get('updated', 0)}** thẻ"); report_lines.append(f"➕ Thêm mới thành công: **{results.get('added', 0)}** thẻ")
        total_skipped_errors = results.get('skipped', 0) + len(results.get('errors', [])); report_lines.append(f"⏭️ Bỏ qua / Lỗi dòng: **{total_skipped_errors}** dòng")
        errors = results.get('errors', [])
        if errors: report_lines.append("\n📄 Chi tiết lỗi / bỏ qua (tối đa 10 dòng):"); count_err = 0
        for err_info in errors:
            if count_err >= 10: report_lines.append("  ... (và các lỗi khác nếu có)"); break
            if isinstance(err_info, dict): line_num = err_info.get('line', '?'); reason = err_info.get('reason', 'Không rõ lý do'); card_inf = err_info.get('card_info', ''); report_lines.append(f" - Dòng {line_num}: {html.escape(str(reason))} {html.escape(str(card_inf))}"); count_err +=1
            else: report_lines.append(f" - Lỗi không rõ định dạng: {html.escape(str(err_info))}"); count_err += 1
        final_report = "\n".join(report_lines)
        kb_back_manage = [[InlineKeyboardButton("🗂️ Menu Quản lý", callback_data="show_set_management")]]; reply_markup_report = InlineKeyboardMarkup(kb_back_manage)
        await send_or_edit_message(context=context, chat_id=chat_id, text=final_report, parse_mode='Markdown', message_to_edit=processing_message, reply_markup=reply_markup_report)
    except Exception as report_err: plain_report = final_report.replace('*','').replace('_','').replace('`','') if final_report else "Xử lý xong, nhưng có lỗi khi tạo báo cáo chi tiết."; await send_or_edit_message(context=context, chat_id=chat_id, text=plain_report, message_to_edit=processing_message)
    finally:
        if file_path and os.path.exists(file_path): 
            try: await loop.run_in_executor(None, os.remove, file_path)
            except Exception : pass
        context.user_data.pop('target_set_id_for_update', None)
    return ConversationHandler.END

async def _handle_state_update_set_unexpected(update, context):
    # Giữ nguyên logic
    if not update or not update.message: return WAITING_FOR_UPDATE_FILE
    await send_or_edit_message(context=context, chat_id=update.message.chat_id, text="⚠️ Đang chờ file Excel (.xlsx) để cập nhật.\nVui lòng gửi file hoặc nhấn Hủy / gõ /cancel.")
    return WAITING_FOR_UPDATE_FILE

async def _handle_cancel_update_set(update, context):
    # Giữ nguyên logic
    if not update or not update.effective_user: return ConversationHandler.END
    user_id_tg = update.effective_user.id; log_prefix = f"[DATA_UPDATE_CANCEL|UserTG:{user_id_tg}]"; logger.info(f"{log_prefix} Hủy cập nhật bộ từ.")
    context.user_data.pop("target_set_id_for_update", None); message_to_edit_cancel = None; chat_id_cancel = user_id_tg; parse_mode_cancel = None
    if update.callback_query: 
        query = update.callback_query
        try: 
            await query.answer()
        except Exception: pass
        if query.message: 
            message_to_edit_cancel = query.message; chat_id_cancel = query.message.chat_id 
    elif update.message: 
        chat_id_cancel = update.message.chat_id
    try:
        reply_markup_cancel = build_set_management_keyboard(); cancel_message_text = "Đã hủy thao tác cập nhật bộ từ. Quay lại Menu Quản lý:"; parse_mode_cancel = 'Markdown'
    except Exception : reply_markup_cancel = None; cancel_message_text = "Đã hủy thao tác cập nhật bộ từ."
    try: await send_or_edit_message(context=context, chat_id=chat_id_cancel, text=cancel_message_text, message_to_edit=message_to_edit_cancel, reply_markup=reply_markup_cancel, parse_mode=parse_mode_cancel)
    except Exception : pass
    return ConversationHandler.END

update_set_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(handle_callback_update_set_select, pattern="^{}".format(UPDATE_SET_CALLBACK_PREFIX))],
    states={WAITING_FOR_UPDATE_FILE: [MessageHandler(filters.Document.FileExtension("xlsx"), _handle_state_update_set_file), MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_state_update_set_unexpected), MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT & ~filters.Document.FileExtension("xlsx"), _handle_state_update_set_unexpected)]},
    fallbacks=[CommandHandler("cancel", _handle_cancel_update_set), CallbackQueryHandler(_handle_cancel_update_set, pattern='^cancel_update_set$')],
    name="update_set_conversation", persistent=False, per_message=False
)

def register_handlers(app):
    app.add_handler(update_set_conv)
    # Sửa lần 1: Không đăng ký handle_command_update_set ở đây nữa vì nó được gọi từ set_management
    # app.add_handler(CommandHandler("flashcard_update_set", handle_command_update_set)) 
    logger.info("Đã đăng ký các handler cho module Data Import Update.")

