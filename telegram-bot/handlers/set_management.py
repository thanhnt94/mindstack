# File: flashcard-telegram-bot/handlers/set_management.py
"""
Module chứa các handlers liên quan đến quản lý bộ từ (Set Management).
(Sửa lần 4: Sửa lỗi MarkdownV2 parsing cho dấu ngoặc đơn trong _display_set_deletion_menu
             và các tin nhắn xác nhận khác.)
(Sửa lần 5: Sửa lỗi MarkdownV2 cho tiêu đề menu "Quản lý bộ thẻ".)
"""
import logging
import html 
import math 

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CallbackQueryHandler 
from telegram.constants import ParseMode 

from config import (
    CAN_MANAGE_OWN_SETS,
    SET_MGMT_DELETE_MENU_PFX,
    SET_MGMT_ASK_CONFIRM_DELETE_PFX,
    SET_MGMT_CONFIRM_DELETE_ACTION_PFX,
    SETS_PER_PAGE 
)
from database.query_user import get_user_by_telegram_id
from database.query_set import get_sets, delete_set_by_id_and_owner 
from ui.core_ui import build_set_management_keyboard, build_pagination_keyboard 
from utils.helpers import send_or_edit_message, require_permission, escape_md_v2 
from utils.exceptions import DatabaseError, UserNotFoundError, SetNotFoundError, PermissionsError

from handlers.data_import_update import handle_command_update_set as trigger_update_set_handler
from handlers.data_export import handle_export_all_data_set_command as trigger_export_set_handler


logger = logging.getLogger(__name__)

DELETION_MENU_MSG_ID_KEY = 'set_mgmt_delete_menu_msg_id'

@require_permission(CAN_MANAGE_OWN_SETS)
async def show_set_management(update, context):
    query = update.callback_query
    if not query or not query.from_user: logger.warning("show_set_management: Callback/User không hợp lệ."); return
    user_id_tg = query.from_user.id
    log_prefix = f"[SET_MGMT_MENU|UserTG:{user_id_tg}]"; logger.info(f"{log_prefix} Hiển thị menu quản lý bộ từ.")
    chat_id = query.message.chat_id if query.message else user_id_tg; message_to_edit = query.message
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    try:
        creator_user_id = None
        try:
            user_info = get_user_by_telegram_id(user_id_tg)
            if not user_info or 'user_id' not in user_info: raise UserNotFoundError(identifier=user_id_tg)
            creator_user_id = user_info['user_id']
        except (UserNotFoundError, DatabaseError) as e_user:
            await send_or_edit_message(context, chat_id, "❌ Lỗi tải thông tin người dùng.", message_to_edit=message_to_edit); return
        
        reply_markup = build_set_management_keyboard(has_pending_reports=False) 
        if reply_markup:
            # Sửa lần 5: Sửa định dạng MarkdownV2 cho tiêu đề
            text_to_send = "🗂️ *Quản lý bộ thẻ\\:*" 
            sent_msg = await send_or_edit_message(context=context, chat_id=chat_id, text=text_to_send, reply_markup=reply_markup, message_to_edit=message_to_edit, parse_mode=ParseMode.MARKDOWN_V2)
            if sent_msg and hasattr(sent_msg, 'message_id'): 
                 context.user_data['set_management_menu_message_id'] = sent_msg.message_id
        else: await send_or_edit_message(context, chat_id, "❌ Lỗi hiển thị menu quản lý.", message_to_edit=message_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

@require_permission(CAN_MANAGE_OWN_SETS)
async def _display_set_deletion_menu(update, context, page=1):
    query = update.callback_query
    if not query or not query.from_user: return
    
    creator_telegram_id = query.from_user.id
    log_prefix = f"[SET_MGMT_DELETE_MENU|UserTG:{creator_telegram_id}|Page:{page}]"
    logger.info(f"{log_prefix} Hiển thị danh sách bộ để xóa.")
    chat_id = query.message.chat_id if query.message else creator_telegram_id
    message_to_edit = query.message

    try: await query.answer()
    except Exception: pass

    try:
        user_info = get_user_by_telegram_id(creator_telegram_id)
        if not user_info or 'user_id' not in user_info: raise UserNotFoundError(identifier=creator_telegram_id)
        creator_user_id = user_info['user_id']

        user_sets, total_sets = get_sets(
            columns=['set_id', 'title'], 
            creator_user_id=creator_user_id, 
            limit=SETS_PER_PAGE, 
            offset=(page - 1) * SETS_PER_PAGE
        )

        keyboard = []
        total_pages_calc = max(1, (total_sets + SETS_PER_PAGE - 1) // SETS_PER_PAGE)
        text = f"🗑️ **Chọn bộ từ bạn muốn xóa** \\(Trang {page}/{total_pages_calc}\\):\n" 
        
        if not user_sets:
            text = "Bạn không có bộ từ nào để xóa\\." 
        else:
            for s_item in user_sets: 
                set_id = s_item.get('set_id'); title = s_item.get('title', f"Bộ không tên {set_id}")
                if set_id is None: continue
                callback_data = f"{SET_MGMT_ASK_CONFIRM_DELETE_PFX}{set_id}"
                keyboard.append([InlineKeyboardButton(f"📚 {html.escape(title)}", callback_data=callback_data)])
        
        pagination_row = build_pagination_keyboard(page, total_pages_calc, f"{SET_MGMT_DELETE_MENU_PFX}_page") 
        if pagination_row:
            keyboard.append(pagination_row)
        
        keyboard.append([InlineKeyboardButton("🔙 Quay lại Menu Quản lý", callback_data="show_set_management")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        sent_msg = await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode=ParseMode.MARKDOWN_V2)
        if sent_msg:
            context.user_data[DELETION_MENU_MSG_ID_KEY] = sent_msg.message_id

    except (UserNotFoundError, DatabaseError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User: {e_db}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi tải danh sách bộ thẻ.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

async def handle_callback_delete_set_page(update, context):
    query = update.callback_query
    if not query or not query.data or not query.from_user: return
    try:
        parts = query.data.split(':'); action_page = parts[2]; current_page = int(parts[3])
        new_page = current_page + 1 if action_page == "next" else max(1, current_page - 1)
        await _display_set_deletion_menu(update, context, page=new_page)
    except (IndexError, ValueError) as e: logger.error(f"Lỗi parse callback phân trang xóa bộ: {query.data} - {e}"); await query.answer("Lỗi dữ liệu phân trang.", show_alert=True)

@require_permission(CAN_MANAGE_OWN_SETS)
async def handle_callback_ask_confirm_delete_set(update, context):
    query = update.callback_query
    if not query or not query.data or not query.from_user: return
    deleter_telegram_id = query.from_user.id; log_prefix = f"[SET_MGMT_ASK_CONFIRM_DELETE|UserTG:{deleter_telegram_id}]"
    chat_id = query.message.chat_id if query.message else deleter_telegram_id; message_to_edit = query.message; set_id = None
    try: await query.answer()
    except Exception: pass
    try:
        set_id = int(query.data.split(SET_MGMT_ASK_CONFIRM_DELETE_PFX)[1]); logger.info(f"{log_prefix} Yêu cầu xác nhận xóa Set ID: {set_id}")
        set_info_list, _ = get_sets(set_id=set_id, columns=['title']);
        if not set_info_list: raise SetNotFoundError(set_id=set_id)
        set_title = set_info_list[0].get('title', f"ID {set_id}")
        text = (f"⚠️ **XÁC NHẬN XÓA BỘ THẺ** ⚠️\n\n"
                f"Bạn có chắc chắn muốn xóa vĩnh viễn bộ thẻ:\n"
                f"**{escape_md_v2(set_title)}** \\(ID: `{set_id}`\\)?\n\n" 
                f"❗️ Hành động này **KHÔNG THỂ HOÀN TÁC**\\. Tất cả thẻ, ghi chú, và tiến trình học liên quan đến bộ này sẽ bị xóa hoàn toàn\\.") 
        keyboard = [[InlineKeyboardButton(f"✅ Có, xóa bộ ID {set_id}!", callback_data=f"{SET_MGMT_CONFIRM_DELETE_ACTION_PFX}{set_id}")], [InlineKeyboardButton("🚫 Không, hủy bỏ", callback_data="show_set_management")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode=ParseMode.MARKDOWN_V2)
    except (IndexError, ValueError): logger.error(f"{log_prefix} Callback data lỗi: {query.data}"); await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu callback.", message_to_edit=message_to_edit)
    except SetNotFoundError: logger.warning(f"{log_prefix} Không tìm thấy set {set_id}."); await send_or_edit_message(context, chat_id, "❌ Bộ thẻ không còn tồn tại.", message_to_edit=message_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

@require_permission(CAN_MANAGE_OWN_SETS)
async def confirm_delete_set_callback(update, context):
    query = update.callback_query
    if not query or not query.data or not query.from_user: return
    deleter_telegram_id = query.from_user.id; log_prefix = f"[SET_MGMT_CONFIRM_DELETE|UserTG:{deleter_telegram_id}]"
    chat_id = query.message.chat_id if query.message else deleter_telegram_id; message_to_edit = query.message; set_id_to_delete = None
    try: await query.answer("Đang xử lý yêu cầu xóa...")
    except Exception: pass
    try:
        set_id_to_delete = int(query.data.split(SET_MGMT_CONFIRM_DELETE_ACTION_PFX)[1]); logger.info(f"{log_prefix} Xác nhận xóa Set ID: {set_id_to_delete}")
        user_info = get_user_by_telegram_id(deleter_telegram_id)
        if not user_info or 'user_id' not in user_info: raise UserNotFoundError(identifier=deleter_telegram_id)
        deleter_user_id = user_info['user_id']
        set_info_before_delete_list, _ = get_sets(set_id=set_id_to_delete, columns=['title']); set_title_deleted = set_info_before_delete_list[0].get('title', f"ID {set_id_to_delete}") if set_info_before_delete_list else f"ID {set_id_to_delete}"
        affected_users_telegram_ids = delete_set_by_id_and_owner(set_id_to_delete, deleter_user_id)
        success_message = f"✅ Đã xóa thành công bộ thẻ '**{escape_md_v2(set_title_deleted)}**' \\(ID: `{set_id_to_delete}`\\)\\." 
        logger.info(f"{log_prefix} {success_message}")
        if affected_users_telegram_ids:
            logger.info(f"{log_prefix} Sẽ thông báo cho {len(affected_users_telegram_ids)} người dùng bị reset current_set_id.")
            notification_text = f"ℹ️ Bộ thẻ '**{escape_md_v2(set_title_deleted)}**' mà bạn đang học đã bị người tạo xóa bỏ\\. Lựa chọn bộ hiện tại của bạn đã được xóa\\." 
            for tg_id in affected_users_telegram_ids:
                if tg_id != deleter_telegram_id: 
                    try: await context.bot.send_message(chat_id=tg_id, text=notification_text, parse_mode=ParseMode.MARKDOWN_V2)
                    except Exception as e_notify: logger.error(f"{log_prefix} Lỗi gửi thông báo cho TG ID {tg_id}: {e_notify}")
        reply_markup_back = build_set_management_keyboard(has_pending_reports=False) 
        await send_or_edit_message(context, chat_id, success_message + "\n\n🗂️ *Quản lý bộ thẻ\\:*", reply_markup_back, message_to_edit=message_to_edit, parse_mode=ParseMode.MARKDOWN_V2) # Sửa: parse_mode
    except (IndexError, ValueError): logger.error(f"{log_prefix} Callback data lỗi: {query.data}"); await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu callback.", message_to_edit=message_to_edit)
    except SetNotFoundError: logger.warning(f"{log_prefix} Không tìm thấy set {set_id_to_delete} để xóa."); await send_or_edit_message(context, chat_id, "❌ Bộ thẻ không còn tồn tại hoặc đã được xóa.", message_to_edit=message_to_edit)
    except PermissionsError as e_perm: logger.warning(f"{log_prefix} Lỗi quyền khi xóa set {set_id_to_delete}: {e_perm}"); await send_or_edit_message(context, chat_id, f"❌ {e_perm}", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError) as e_db: logger.error(f"{log_prefix} Lỗi DB/User khi xóa set: {e_db}"); await send_or_edit_message(context, chat_id, "❌ Lỗi khi thực hiện xóa bộ thẻ.", message_to_edit=message_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi nghiêm trọng xảy ra.", message_to_edit=message_to_edit)

def register_handlers(app: Application):
    app.add_handler(CallbackQueryHandler(show_set_management, pattern=r"^show_set_management$"))
    app.add_handler(CallbackQueryHandler(_display_set_deletion_menu, pattern=f"^{SET_MGMT_DELETE_MENU_PFX}$")) 
    app.add_handler(CallbackQueryHandler(handle_callback_delete_set_page, pattern=f"^{SET_MGMT_DELETE_MENU_PFX}_page:")) 
    app.add_handler(CallbackQueryHandler(handle_callback_ask_confirm_delete_set, pattern=f"^{SET_MGMT_ASK_CONFIRM_DELETE_PFX}")) 
    app.add_handler(CallbackQueryHandler(confirm_delete_set_callback, pattern=f"^{SET_MGMT_CONFIRM_DELETE_ACTION_PFX}")) 
    app.add_handler(CallbackQueryHandler(trigger_update_set_handler, pattern=r"^trigger_update_set$"))
    app.add_handler(CallbackQueryHandler(trigger_export_set_handler, pattern=r"^trigger_export_set$"))
    logger.info("Đã đăng ký các handler cho module Set Management (Bao gồm luồng xóa, update, export).")

