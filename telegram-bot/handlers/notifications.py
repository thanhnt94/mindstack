# File: flashcard-telegram-bot/handlers/notifications.py
"""
Module chứa các handlers cho chức năng cài đặt thông báo nhắc nhở ôn tập.
Các handler đã được cập nhật để lấy user_id từ telegram_id và sử dụng user_id
khi gọi các hàm database để cập nhật cài đặt.
(Sửa lần 2: Thêm handlers cho việc chọn/xóa bộ thẻ nhận thông báo và bật/tắt morning brief.
             Sửa lại logic điều phối callback.)
"""
import logging
import sqlite3 # Cần thiết khi gọi hàm DB với connection
import html # Cần cho html.escape

from telegram import Update 
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackQueryHandler 
from telegram.error import BadRequest
from telegram.constants import ChatAction # Thêm ChatAction

# Sử dụng import tuyệt đối
from config import ( 
    NOTIFY_TOGGLE_PERIODIC, # Đã đổi tên
    NOTIFY_INTERVAL_MENU, 
    NOTIFY_INTERVAL_SET, 
    NOTIFY_CALLBACK_PREFIX, # Dùng prefix chung
    NOTIFY_CHOOSE_TARGET_SET_MENU, # Callback mới
    NOTIFY_SELECT_TARGET_SET_ACTION, # Callback mới
    NOTIFY_CLEAR_TARGET_SET_ACTION, # Callback mới
    NOTIFY_TOGGLE_MORNING_BRIEF_ACTION, # Callback mới
    NOTIFY_TARGET_SET_PAGE # Callback mới cho phân trang
)
from database.connection import database_connect # Cần cho hàm lấy danh sách bộ
from database.query_user import get_user_by_telegram_id, update_user_by_id 
from database.query_set import get_sets # Để lấy danh sách bộ của user
from ui.settings_ui import build_main_settings_menu 
from ui.notifications_ui import ( 
    build_notification_settings_menu,
    build_interval_selection_keyboard,
    build_notification_set_selection_keyboard # UI mới
)
from utils.helpers import send_or_edit_message 
from utils.exceptions import ( 
    DatabaseError,
    UserNotFoundError,
    ValidationError,
    DuplicateError
)
logger = logging.getLogger(__name__)

async def handle_command_reminders(update, context):
    """Handler cho lệnh /flashcard_remind hoặc callback 'settings:show_notifications'."""
    telegram_id = None
    chat_id = None
    message_to_edit = None
    source = "Unknown"

    if update.effective_user:
        telegram_id = update.effective_user.id
    else:
        logger.warning("handle_command_reminders: Không tìm thấy effective_user.")
        return

    log_prefix = f"[NOTIFY_CMD_OR_CB_MENU|UserTG:{telegram_id}]"

    if update.callback_query:
        source = "Callback(settings:show_notifications)"
        query = update.callback_query
        if query.message:
            chat_id = query.message.chat_id
            message_to_edit = query.message
        else:
            chat_id = telegram_id
            message_to_edit = None
            logger.warning(f"{log_prefix} Callback query không có message gốc.")
        try:
            await query.answer()
        except Exception as e_ans:
            logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    elif update.message:
        source = "Command(/flashcard_remind)"
        chat_id = update.message.chat_id
        message_to_edit = None
    else:
        logger.warning(f"{log_prefix} Update không hợp lệ.")
        return
    
    logger.info(f"{log_prefix} Được gọi từ {source}. Hiển thị menu cài đặt thông báo.")
    
    if chat_id:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action:
            logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")

    try:
        user_info = get_user_by_telegram_id(telegram_id) 
        text, reply_markup = build_notification_settings_menu(user_info) # Hàm UI đã cập nhật
        if text and reply_markup:
            sent_msg = await send_or_edit_message(
                context=context,
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown',
                message_to_edit=message_to_edit
            )
            if not sent_msg:
                 logger.error(f"{log_prefix} Lỗi khi gửi/sửa menu cài đặt thông báo.")
        else:
            logger.error(f"{log_prefix} Lỗi khi tạo giao diện cài đặt thông báo.")
            await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Đã xảy ra lỗi khi tải cài đặt của bạn.", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError) as e:
        logger.error(f"{log_prefix} Lỗi DB/User khi lấy thông tin: {e}")
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Không thể lấy thông tin cài đặt của bạn.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Đã có lỗi xảy ra.", message_to_edit=message_to_edit)

async def handle_callback_notification_menu(update, context):
    """
    Hàm điều phối chính cho các callback query bắt đầu bằng prefix NOTIFY_CALLBACK_PREFIX.
    """
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        logger.warning("handle_callback_notification_menu nhận callback query không hợp lệ.")
        return
    
    user_id_tg = query.from_user.id
    data = query.data 
    log_prefix = f"[NOTIFY_CB_DISPATCH|UserTG:{user_id_tg}|Data:{data}]" 
    logger.info(f"{log_prefix} Nhận được callback thông báo.")

    # Điều phối dựa trên action cụ thể (phần sau prefix)
    action = data.split(":")[1] if ":" in data else data # Lấy phần action
    
    # Các action không cần payload (set_id, interval_value)
    if data == NOTIFY_TOGGLE_PERIODIC:
        await _handle_notification_toggle_periodic(query, context)
    elif data == NOTIFY_INTERVAL_MENU:
        await _handle_notification_interval_menu(query, context)
    elif data == NOTIFY_CHOOSE_TARGET_SET_MENU: # Hiển thị menu chọn bộ
        await handle_callback_choose_notification_set_menu(query, context)
    elif data == NOTIFY_CLEAR_TARGET_SET_ACTION: # Xóa chọn bộ
        await handle_callback_clear_notification_target_set(query, context)
    elif data == NOTIFY_TOGGLE_MORNING_BRIEF_ACTION: # Bật/tắt morning brief
        await _handle_notification_toggle_morning_brief(query, context)
    elif data == f"{NOTIFY_CALLBACK_PREFIX}:back_to_notify_menu": # Quay lại menu cài đặt thông báo
        # Gọi lại hàm hiển thị menu chính của notifications
        await handle_command_reminders(update, context) # Tái sử dụng hàm này
    elif data.startswith(NOTIFY_INTERVAL_SET): # Đặt khoảng cách
        await _handle_notification_set_interval_value(query, context)
    elif data.startswith(NOTIFY_SELECT_TARGET_SET_ACTION): # Chọn một bộ cụ thể
        await handle_callback_select_notification_target_set(query, context)
    elif data.startswith(NOTIFY_TARGET_SET_PAGE): # Phân trang chọn bộ
        await handle_callback_notification_target_set_page(query, context)
    # Callback quay về menu settings tổng hợp (từ config.py)
    elif data == "settings:back_to_unified": 
        from handlers.settings import handle_command_settings as show_unified_settings_handler
        await show_unified_settings_handler(update, context)
    else:
        logger.warning(f"{log_prefix} Callback data không xác định hoặc chưa được xử lý: {data}")
        try:
            await query.answer("Hành động này chưa được hỗ trợ.") 
        except Exception:
            pass 

async def _handle_notification_toggle_periodic(query, context):
    """Hàm nội bộ: Xử lý callback bật/tắt thông báo ôn tập định kỳ."""
    if not query or not query.from_user: return
    telegram_id = query.from_user.id
    log_prefix = f"[NOTIFY_TOGGLE_PERIODIC|UserTG:{telegram_id}]"; 
    logger.info(f"{log_prefix} Yêu cầu bật/tắt thông báo ôn tập định kỳ.")
    chat_id = query.message.chat_id if query.message else telegram_id; 
    message_to_edit = query.message
    try: await query.answer()
    except BadRequest as e_ans:
        if "Query is too old" in str(e_ans): logger.warning(f"{log_prefix} Callback query cũ.")
        else: logger.error(f"{log_prefix} Lỗi answer callback: {e_ans}")
    except Exception as e_ans_unk: logger.error(f"{log_prefix} Lỗi không mong muốn answer callback: {e_ans_unk}")
    
    updated_user_info = None; actual_user_id = None
    try:
        user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']
        current_status = user_info.get('is_notification_enabled', 0)
        new_status_value = 1 - current_status
        
        update_result = update_user_by_id(actual_user_id, is_notification_enabled=new_status_value)
        logger.info(f"{log_prefix} Đã cập nhật is_notification_enabled (Rows: {update_result}).")
        updated_user_info = get_user_by_telegram_id(telegram_id) # Lấy lại thông tin mới
    except (UserNotFoundError, DatabaseError, ValidationError, DuplicateError) as e:
        logger.error(f"{log_prefix} Lỗi DB/User/Validation: {e}"); 
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi khi thay đổi cài đặt.", message_to_edit=message_to_edit); return
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi không mong muốn: {e}"); 
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi không mong muốn.", message_to_edit=message_to_edit); return
    
    try:
        text, reply_markup = build_notification_settings_menu(updated_user_info)
        if text and reply_markup:
            await send_or_edit_message(context=context, chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='Markdown', message_to_edit=message_to_edit)
    except Exception as e_display:
         logger.error(f"{log_prefix} Lỗi hiển thị lại giao diện: {e_display}", exc_info=True); 
         await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hiển thị cài đặt mới.", message_to_edit=message_to_edit)

async def _handle_notification_toggle_morning_brief(query, context):
    """Hàm nội bộ: Xử lý callback bật/tắt Lời chào buổi sáng."""
    if not query or not query.from_user: return
    telegram_id = query.from_user.id
    log_prefix = f"[NOTIFY_TOGGLE_MORNING|UserTG:{telegram_id}]";
    logger.info(f"{log_prefix} Yêu cầu bật/tắt Lời chào buổi sáng.")
    chat_id = query.message.chat_id if query.message else telegram_id;
    message_to_edit = query.message
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer: {e_ans}")

    updated_user_info = None; actual_user_id = None
    try:
        user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']
        current_status = user_info.get('enable_morning_brief', 1) # Mặc định là bật
        new_status_value = 1 - current_status
        
        update_result = update_user_by_id(actual_user_id, enable_morning_brief=new_status_value)
        logger.info(f"{log_prefix} Đã cập nhật enable_morning_brief (Rows: {update_result}).")
        updated_user_info = get_user_by_telegram_id(telegram_id)
    except (UserNotFoundError, DatabaseError, ValidationError, DuplicateError) as e:
        logger.error(f"{log_prefix} Lỗi DB/User/Validation: {e}");
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi khi thay đổi cài đặt Lời chào buổi sáng.", message_to_edit=message_to_edit); return
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi không mong muốn: {e}");
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi không mong muốn.", message_to_edit=message_to_edit); return
    
    try:
        text, reply_markup = build_notification_settings_menu(updated_user_info)
        if text and reply_markup:
            await send_or_edit_message(context=context, chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='Markdown', message_to_edit=message_to_edit)
    except Exception as e_display:
         logger.error(f"{log_prefix} Lỗi hiển thị lại giao diện: {e_display}", exc_info=True);
         await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hiển thị cài đặt mới.", message_to_edit=message_to_edit)


async def _handle_notification_interval_menu(query, context):
    # Giữ nguyên logic, chỉ đảm bảo callback nút Back đúng
    if not query or not query.from_user: return
    telegram_id = query.from_user.id
    log_prefix = f"[NOTIFY_INTERVAL_MENU|UserTG:{telegram_id}]"; 
    logger.info(f"{log_prefix} Yêu cầu hiển thị menu chọn khoảng cách.")
    chat_id = query.message.chat_id if query.message else telegram_id; 
    message_to_edit = query.message
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    
    reply_markup = build_interval_selection_keyboard() # Hàm UI này đã có nút back đúng
    if reply_markup:
        await send_or_edit_message(context=context, chat_id=chat_id, text="⏰ Chọn khoảng thời gian (phút) bạn muốn nhận thông báo nhắc nhở:", reply_markup=reply_markup, message_to_edit=message_to_edit)
    else:
         logger.error(f"{log_prefix} Lỗi khi tạo keyboard chọn khoảng cách."); 
         await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi khi hiển thị các lựa chọn.", message_to_edit=message_to_edit)

async def _handle_notification_set_interval_value(query, context):
    # Giữ nguyên logic
    if not query or not query.from_user or not query.data: return
    telegram_id = query.from_user.id
    log_prefix = f"[NOTIFY_SET_INTERVAL|UserTG:{telegram_id}]"; 
    logger.info(f"{log_prefix} Yêu cầu đặt khoảng cách thông báo.")
    chat_id = query.message.chat_id if query.message else telegram_id; 
    message_to_edit = query.message
    selected_interval = -1; updated_user_info = None; actual_user_id = None
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    
    try:
        # NOTIFY_INTERVAL_SET là "notify_settings:interval_set:"
        interval_str = query.data.split(NOTIFY_INTERVAL_SET)[1]; 
        selected_interval = int(interval_str)
        if selected_interval <= 0: raise ValueError("Khoảng cách phải là số dương.")
        
        user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']
        update_result = update_user_by_id(actual_user_id, notification_interval_minutes=selected_interval)
        logger.info(f"{log_prefix} Đã cập nhật interval (Rows: {update_result}).")
        updated_user_info = get_user_by_telegram_id(telegram_id)
    except (ValueError, IndexError, TypeError) as e_parse:
        logger.error(f"{log_prefix} Lỗi parse interval từ callback '{query.data}': {e_parse}"); 
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lựa chọn khoảng cách không hợp lệ.", message_to_edit=message_to_edit); return
    except (UserNotFoundError, DatabaseError, ValidationError, DuplicateError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User/Validation khi set interval: {e_db}"); 
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi khi lưu khoảng cách mới.", message_to_edit=message_to_edit); return
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi không mong muốn: {e}"); 
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi không mong muốn.", message_to_edit=message_to_edit); return
    
    try:
        success_msg = f"✅ Đã cập nhật khoảng cách nhận thông báo thành **{selected_interval} phút**."
        text, reply_markup = build_notification_settings_menu(updated_user_info, success_message=success_msg)
        if text and reply_markup:
            await send_or_edit_message(context=context, chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='Markdown', message_to_edit=message_to_edit)
    except Exception as e_display:
         logger.error(f"{log_prefix} Lỗi hiển thị lại giao diện: {e_display}", exc_info=True); 
         await send_or_edit_message(context=context, chat_id=chat_id, text=f"✅ Đã cập nhật khoảng cách thành {selected_interval} phút, nhưng lỗi hiển thị lại menu.", message_to_edit=message_to_edit)

async def handle_callback_choose_notification_set_menu(query, context):
    """Hiển thị danh sách các bộ thẻ người dùng đã học để chọn làm mục tiêu thông báo."""
    if not query or not query.from_user: return
    telegram_id = query.from_user.id
    log_prefix = f"[NOTIFY_CHOOSE_SET_MENU_CB|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Yêu cầu hiển thị menu chọn bộ cho thông báo.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer: {e_ans}")

    actual_user_id = None
    all_learned_sets = []
    try:
        user_info_db = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info_db['user_id']
        
        # Lấy tất cả các bộ người dùng đã có tiến trình học (tương tự audio_review)
        conn = None
        try:
            conn = database_connect()
            if conn is None: raise DatabaseError("Không thể kết nối DB.")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query_learned = """
                SELECT DISTINCT vs.set_id, vs.title
                FROM UserFlashcardProgress ufp
                JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id
                JOIN VocabularySets vs ON f.set_id = vs.set_id
                WHERE ufp.user_id = ? ORDER BY vs.title COLLATE NOCASE
            """
            cursor.execute(query_learned, (actual_user_id,))
            all_learned_sets = [dict(row) for row in cursor.fetchall()]
        finally:
            if conn: conn.close()

        text, reply_markup = build_notification_set_selection_keyboard(actual_user_id, all_learned_sets, current_page=1)
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode='Markdown')

    except (UserNotFoundError, DatabaseError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User: {e_db}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi tải danh sách bộ thẻ.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

async def handle_callback_notification_target_set_page(query, context):
    """Xử lý phân trang cho việc chọn bộ thẻ thông báo."""
    if not query or not query.data or not query.from_user: return
    telegram_id = query.from_user.id
    log_prefix = f"[NOTIFY_TARGET_SET_PAGE_CB|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Phân trang chọn bộ thông báo: {query.data}")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer: {e_ans}")

    try:
        # Pattern: notify_settings:target_set_page:<prev|next>:<current_page>
        parts = query.data.split(":")
        if len(parts) != 4: raise ValueError("Callback data phân trang sai định dạng")
        
        action = parts[2] # prev hoặc next
        current_page = int(parts[3])
        new_page = current_page
        if action == "next": new_page += 1
        elif action == "prev": new_page = max(1, current_page - 1)
        else: raise ValueError("Hành động phân trang không hợp lệ")

        user_info_db = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info_db['user_id']
        
        conn = None
        all_learned_sets_page = []
        try:
            conn = database_connect(); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
            query_learned_page = """ SELECT DISTINCT vs.set_id, vs.title FROM UserFlashcardProgress ufp JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id JOIN VocabularySets vs ON f.set_id = vs.set_id WHERE ufp.user_id = ? ORDER BY vs.title COLLATE NOCASE """
            cursor.execute(query_learned_page, (actual_user_id,)); all_learned_sets_page = [dict(row) for row in cursor.fetchall()]
        finally:
            if conn: conn.close()

        text, reply_markup = build_notification_set_selection_keyboard(actual_user_id, all_learned_sets_page, current_page=new_page)
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode='Markdown')

    except (ValueError, IndexError, TypeError) as e_parse:
        logger.error(f"{log_prefix} Lỗi parse callback: {e_parse}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu phân trang.", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User: {e_db}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi tải lại danh sách bộ.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi chuyển trang.", message_to_edit=message_to_edit)

async def handle_callback_select_notification_target_set(query, context):
    """Xử lý khi người dùng chọn một bộ thẻ cụ thể để nhận thông báo."""
    if not query or not query.data or not query.from_user: return
    telegram_id = query.from_user.id
    log_prefix = f"[NOTIFY_SELECT_TARGET_SET_CB|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Chọn bộ thẻ cho thông báo: {query.data}")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer: {e_ans}")

    actual_user_id = None
    selected_set_id = None
    try:
        # Pattern: notify_settings:select_target_set_action:<set_id>
        parts = query.data.split(":")
        if len(parts) != 3: raise ValueError("Callback data chọn bộ sai định dạng")
        selected_set_id = int(parts[2])

        user_info_db = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info_db['user_id']
        
        update_result = update_user_by_id(actual_user_id, notification_target_set_id=selected_set_id)
        logger.info(f"{log_prefix} Đã cập nhật notification_target_set_id={selected_set_id} (Rows: {update_result}).")
        
        # Hiển thị lại menu cài đặt thông báo
        updated_user_info_display = get_user_by_telegram_id(telegram_id)
        set_name_display = f"ID {selected_set_id}"
        try:
            set_info_list_disp, _ = get_sets(set_id=selected_set_id, columns=['title'])
            if set_info_list_disp and set_info_list_disp[0]: set_name_display = html.escape(set_info_list_disp[0].get('title', set_name_display))
        except: pass
        
        success_msg = f"✅ Đã chọn bộ '**{set_name_display}**' để nhận thông báo ôn tập."
        text, reply_markup = build_notification_settings_menu(updated_user_info_display, success_message=success_msg)
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode='Markdown')

    except (ValueError, IndexError, TypeError) as e_parse:
        logger.error(f"{log_prefix} Lỗi parse callback: {e_parse}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu chọn bộ.", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User: {e_db}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi lưu lựa chọn bộ thẻ.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi chọn bộ.", message_to_edit=message_to_edit)

async def handle_callback_clear_notification_target_set(query, context):
    """Xử lý khi người dùng xóa chọn bộ thẻ nhận thông báo."""
    if not query or not query.from_user: return
    telegram_id = query.from_user.id
    log_prefix = f"[NOTIFY_CLEAR_TARGET_SET_CB|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Xóa chọn bộ thẻ cho thông báo.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer: {e_ans}")

    actual_user_id = None
    try:
        user_info_db = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info_db['user_id']
        
        update_result = update_user_by_id(actual_user_id, notification_target_set_id=None) # Đặt thành NULL
        logger.info(f"{log_prefix} Đã xóa notification_target_set_id (Rows: {update_result}).")
        
        updated_user_info_display = get_user_by_telegram_id(telegram_id)
        success_msg = "🗑️ Đã xóa chọn bộ thẻ nhận thông báo."
        text, reply_markup = build_notification_settings_menu(updated_user_info_display, success_message=success_msg)
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode='Markdown')

    except (UserNotFoundError, DatabaseError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User: {e_db}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi xóa lựa chọn bộ thẻ.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi xóa chọn bộ.", message_to_edit=message_to_edit)


def register_handlers(app: Application):
    """Đăng ký các handler liên quan đến cài đặt thông báo."""
    # Lệnh chính để vào menu cài đặt thông báo
    app.add_handler(CommandHandler("flashcard_remind", handle_command_reminders))
    
    # Callback để vào menu cài đặt thông báo từ menu settings chính
    app.add_handler(CallbackQueryHandler(handle_command_reminders, pattern=r"^settings:show_notifications$"))

    # Handler điều phối chung cho các action trong menu thông báo
    # Pattern này sẽ bắt tất cả callback bắt đầu bằng NOTIFY_CALLBACK_PREFIX
    # và cả callback "settings:back_to_unified"
    app.add_handler(CallbackQueryHandler(handle_callback_notification_menu, pattern=f"^(?:{NOTIFY_CALLBACK_PREFIX.split(':')[0]}:|settings:back_to_unified$)"))
    
    logger.info("Đã đăng ký các handler cho module Notifications (có chọn bộ và morning brief).")

