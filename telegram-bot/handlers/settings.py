"""
Module chứa các handlers cho chức năng cài đặt người dùng.
Các handler đã được cập nhật để lấy user_id từ telegram_id và sử dụng user_id
khi gọi hàm database để cập nhật. Đã thêm send_chat_action.
"""
import logging
from telegram import Update 
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackQueryHandler 
from telegram.error import BadRequest
from telegram.constants import ChatAction
from database.query_user import get_user_by_telegram_id, update_user_by_id 
from ui.settings_ui import build_audio_image_settings_menu, build_main_settings_menu 
from ui.notifications_ui import build_notification_settings_menu
from utils.helpers import send_or_edit_message 
from utils.exceptions import ( 
    DatabaseError,
    UserNotFoundError,
    ValidationError,
    DuplicateError
)
from config import CAN_TOGGLE_SUMMARY, ROLE_PERMISSIONS
logger = logging.getLogger(__name__)
async def handle_command_settings(update, context):
    """Handler cho lệnh /flashcard_settings hoặc callback 'show_unified_settings'."""
    telegram_id = None
    chat_id = None
    message_to_edit = None
    source = "Unknown" 
    if update.effective_user:
        telegram_id = update.effective_user.id
    else:
        logger.warning("handle_command_settings: Không tìm thấy effective_user.")
        return 
    log_prefix = f"[SETTINGS_MAIN|UserTG:{telegram_id}]"
    if update.callback_query:
        source = "Callback" 
        query = update.callback_query
        if query.message:
            chat_id = query.message.chat_id
            message_to_edit = query.message 
        else:
            chat_id = telegram_id 
            message_to_edit = None
            logger.warning(f"{log_prefix} Callback query không có message gốc.")
    elif update.message: 
        source = "Command(/flashcard_settings)"
        chat_id = update.message.chat_id
        message_to_edit = None 
    else:
        logger.warning(f"{log_prefix} Update không hợp lệ (không phải message hay callback).")
        return 
    logger.info(f"{log_prefix} Được gọi từ {source}. Hiển thị menu cài đặt chính.")
    if chat_id:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action:
            logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")
    try:
        text, reply_markup = await build_main_settings_menu(telegram_id) 
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
                logger.error(f"{log_prefix} Lỗi khi gửi/sửa giao diện cài đặt tổng hợp.")
        elif text: 
             logger.error(f"{log_prefix} Lỗi từ build_main_settings_menu: {text}")
             await send_or_edit_message(context=context, chat_id=chat_id, text=text, message_to_edit=message_to_edit)
        else: 
            logger.error(f"{log_prefix} Lỗi không xác định khi tạo giao diện cài đặt tổng hợp.")
            await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Đã xảy ra lỗi khi lấy cài đặt của bạn.", message_to_edit=message_to_edit)
    except (DatabaseError, UserNotFoundError) as e:
         logger.error(f"{log_prefix} Lỗi DB/User khi build menu cài đặt: {e}")
         await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải cài đặt người dùng.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)
async def _handle_toggle_audio(update, context):
    """Hàm nội bộ: Xử lý callback 'toggle_audio:<front|back>'."""
    query = update.callback_query
    if not query: logger.warning("_handle_toggle_audio: callback query không hợp lệ."); return
    if not query.data: logger.warning("_handle_toggle_audio: callback data không hợp lệ."); return
    if not query.from_user: logger.warning("_handle_toggle_audio: user không hợp lệ."); return
    telegram_id = query.from_user.id
    log_prefix = f"[SETTINGS_TOGGLE_AUDIO|UserTG:{telegram_id}]"
    callback_data = query.data; logger.info(f"{log_prefix} Nhận được callback: {callback_data}")
    chat_id = query.message.chat_id if query.message else telegram_id; message_to_edit = query.message
    try: await query.answer()
    except BadRequest as e_ans:
        if "Query is too old" in str(e_ans): logger.warning(f"{log_prefix} Callback query cũ.")
        else: logger.error(f"{log_prefix} Lỗi answer callback: {e_ans}")
    except Exception as e_ans_unk: logger.error(f"{log_prefix} Lỗi không mong muốn answer callback: {e_ans_unk}")
    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action: logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")
    setting_type = ""; user_info = None; actual_user_id = None; column_to_update = ""; new_value = 0
    try:
        parts = callback_data.split(":");
        if len(parts) != 2 or parts[0] != "toggle_audio": raise ValueError("Invalid callback data format")
        setting_type = parts[1];
        if setting_type not in ['front', 'back']: raise ValueError("Invalid setting type")
        logger.debug(f"{log_prefix} Loại cài đặt cần thay đổi: {setting_type}")
        logger.debug(f"{log_prefix} Lấy user info..."); user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']; logger.debug(f"{log_prefix} Lấy được user_id: {actual_user_id}")
        column_to_update = f"{setting_type}_audio"; current_value = user_info.get(column_to_update, 1)
        new_value = 1 - current_value; logger.debug(f"{log_prefix} Cột: {column_to_update}, Hiện tại: {current_value}, Mới: {new_value}")
        logger.debug(f"{log_prefix} Gọi update_user_by_id với user_id={actual_user_id}...")
        update_result = update_user_by_id(actual_user_id, **{column_to_update: new_value})
        if update_result > 0: logger.info(f"{log_prefix} Đã cập nhật thành công {column_to_update}.")
        else: logger.warning(f"{log_prefix} Cập nhật không ảnh hưởng hàng nào.")
    except ValueError as e_parse:
        logger.error(f"{log_prefix} Lỗi parse callback data '{callback_data}': {e_parse}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi dữ liệu callback.", message_to_edit=message_to_edit); return
    except (UserNotFoundError, DatabaseError, DuplicateError, ValidationError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User khi xử lý toggle audio: {e_db}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Đã xảy ra lỗi khi cập nhật cài đặt.", message_to_edit=message_to_edit); return
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi xử lý toggle audio: {e}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit); return
    try:
        logger.debug(f"{log_prefix} Đang tạo lại giao diện cài đặt Audio/Ảnh...")
        new_text, new_reply_markup = await build_audio_image_settings_menu(telegram_id)
        if new_text and new_reply_markup:
            logger.debug(f"{log_prefix} Giao diện mới sẵn sàng. Đang sửa tin nhắn...")
            sent_msg = await send_or_edit_message(context=context, chat_id=chat_id, text=new_text, reply_markup=new_reply_markup, parse_mode='Markdown', message_to_edit=message_to_edit)
            if not sent_msg: logger.error(f"{log_prefix} Lỗi khi cập nhật giao diện cài đặt chi tiết.")
        else:
            logger.error(f"{log_prefix} Lỗi khi tạo lại giao diện cài đặt chi tiết."); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hiển thị cài đặt mới.", message_to_edit=message_to_edit)
    except (DatabaseError, UserNotFoundError) as e_ui:
         logger.error(f"{log_prefix} Lỗi DB/User khi build lại menu: {e_ui}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải lại giao diện cài đặt.", message_to_edit=message_to_edit)
    except Exception as e_ui_unk:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi hiển thị lại cài đặt: {e_ui_unk}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra khi hiển thị cài đặt.", message_to_edit=message_to_edit)
async def _handle_toggle_image(update, context):
    """Hàm nội bộ: Xử lý callback 'toggle_image:<front|back>'."""
    query = update.callback_query
    if not query: logger.warning("_handle_toggle_image: callback query không hợp lệ."); return
    if not query.data: logger.warning("_handle_toggle_image: callback data không hợp lệ."); return
    if not query.from_user: logger.warning("_handle_toggle_image: user không hợp lệ."); return
    telegram_id = query.from_user.id
    log_prefix = f"[SETTINGS_TOGGLE_IMAGE|UserTG:{telegram_id}]"
    callback_data = query.data; logger.info(f"{log_prefix} Nhận được callback: {callback_data}")
    chat_id = query.message.chat_id if query.message else telegram_id; message_to_edit = query.message
    try: await query.answer()
    except BadRequest as e_ans:
        if "Query is too old" in str(e_ans): logger.warning(f"{log_prefix} Callback query cũ.")
        else: logger.error(f"{log_prefix} Lỗi answer callback: {e_ans}")
    except Exception as e_ans_unk: logger.error(f"{log_prefix} Lỗi không mong muốn answer callback: {e_ans_unk}")
    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action: logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")
    setting_type = ""; user_info = None; actual_user_id = None; column_to_update = ""; new_value = 0
    try:
        parts = callback_data.split(":");
        if len(parts) != 2 or parts[0] != "toggle_image": raise ValueError("Invalid callback data format")
        setting_type = parts[1];
        if setting_type not in ['front', 'back']: raise ValueError("Invalid setting type")
        logger.debug(f"{log_prefix} Loại cài đặt cần thay đổi: {setting_type}")
        logger.debug(f"{log_prefix} Lấy user info..."); user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']; logger.debug(f"{log_prefix} Lấy được user_id: {actual_user_id}")
        column_to_update = f"{setting_type}_image_enabled"; current_value = user_info.get(column_to_update, 1)
        new_value = 1 - current_value; logger.debug(f"{log_prefix} Cột: {column_to_update}, Hiện tại: {current_value}, Mới: {new_value}")
        logger.debug(f"{log_prefix} Gọi update_user_by_id với user_id={actual_user_id}...")
        update_result = update_user_by_id(actual_user_id, **{column_to_update: new_value})
        if update_result > 0: logger.info(f"{log_prefix} Đã cập nhật thành công {column_to_update}.")
        else: logger.warning(f"{log_prefix} Cập nhật không ảnh hưởng hàng nào.")
    except ValueError as e_parse:
        logger.error(f"{log_prefix} Lỗi parse callback data '{callback_data}': {e_parse}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi dữ liệu callback.", message_to_edit=message_to_edit); return
    except (UserNotFoundError, DatabaseError, DuplicateError, ValidationError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User khi xử lý toggle image: {e_db}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Đã xảy ra lỗi khi cập nhật cài đặt.", message_to_edit=message_to_edit); return
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi xử lý toggle image: {e}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit); return
    try:
        logger.debug(f"{log_prefix} Đang tạo lại giao diện cài đặt Audio/Ảnh...")
        new_text, new_reply_markup = await build_audio_image_settings_menu(telegram_id)
        if new_text and new_reply_markup:
            logger.debug(f"{log_prefix} Giao diện mới sẵn sàng. Đang sửa tin nhắn...")
            sent_msg = await send_or_edit_message(context=context, chat_id=chat_id, text=new_text, reply_markup=new_reply_markup, parse_mode='Markdown', message_to_edit=message_to_edit)
            if not sent_msg: logger.error(f"{log_prefix} Lỗi khi cập nhật giao diện cài đặt chi tiết.")
        else:
            logger.error(f"{log_prefix} Lỗi khi tạo lại giao diện cài đặt chi tiết."); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hiển thị cài đặt mới.", message_to_edit=message_to_edit)
    except (DatabaseError, UserNotFoundError) as e_ui:
         logger.error(f"{log_prefix} Lỗi DB/User khi build lại menu: {e_ui}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải lại giao diện cài đặt.", message_to_edit=message_to_edit)
    except Exception as e_ui_unk:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi hiển thị lại cài đặt: {e_ui_unk}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra khi hiển thị cài đặt.", message_to_edit=message_to_edit)
async def _handle_toggle_summary(update, context):
    """Hàm nội bộ: Xử lý callback 'settings:toggle_summary'."""
    query = update.callback_query
    if not query: logger.warning("_handle_toggle_summary: callback query không hợp lệ."); return
    if not query.data: logger.warning("_handle_toggle_summary: callback data không hợp lệ."); return
    if not query.from_user: logger.warning("_handle_toggle_summary: user không hợp lệ."); return
    telegram_id = query.from_user.id
    log_prefix = f"[SETTINGS_TOGGLE_SUMMARY|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Nhận được callback: {query.data}")
    chat_id = query.message.chat_id if query.message else telegram_id; message_to_edit = query.message
    try: await query.answer()
    except BadRequest as e_ans:
        if "Query is too old" in str(e_ans): logger.warning(f"{log_prefix} Callback query cũ.")
        else: logger.error(f"{log_prefix} Lỗi answer callback: {e_ans}")
    except Exception as e_ans_unk: logger.error(f"{log_prefix} Lỗi không mong muốn answer callback: {e_ans_unk}")
    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action: logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")
    user_info = None; actual_user_id = None; column_to_update = "show_review_summary"; new_value = 0
    try:
        logger.debug(f"{log_prefix} Lấy user info..."); user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']; logger.debug(f"{log_prefix} Lấy được user_id: {actual_user_id}")
        user_role = user_info.get('user_role', 'user'); user_permissions = ROLE_PERMISSIONS.get(user_role, set())
        if CAN_TOGGLE_SUMMARY not in user_permissions:
             logger.warning(f"{log_prefix} User role '{user_role}' không có quyền toggle summary.")
             await send_or_edit_message(context=context, chat_id=chat_id, text="🔒 Tính năng này yêu cầu nâng cấp tài khoản.", message_to_edit=message_to_edit); return
        current_value = user_info.get(column_to_update, 1); new_value = 1 - current_value
        logger.debug(f"{log_prefix} Cột: {column_to_update}, Hiện tại: {current_value}, Mới: {new_value}")
        logger.debug(f"{log_prefix} Gọi update_user_by_id với user_id={actual_user_id}...")
        update_result = update_user_by_id(actual_user_id, **{column_to_update: new_value})
        if update_result > 0: logger.info(f"{log_prefix} Đã cập nhật thành công {column_to_update} thành {new_value}.")
        else: logger.warning(f"{log_prefix} Cập nhật không ảnh hưởng hàng nào.")
    except (UserNotFoundError, DatabaseError, DuplicateError, ValidationError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User khi xử lý toggle summary: {e_db}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Đã xảy ra lỗi khi cập nhật cài đặt.", message_to_edit=message_to_edit); return
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi xử lý toggle summary: {e}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit); return
    try:
        logger.debug(f"{log_prefix} Đang tạo lại giao diện cài đặt tổng hợp...")
        new_text, new_reply_markup = await build_main_settings_menu(telegram_id)
        if new_text and new_reply_markup:
            logger.debug(f"{log_prefix} Giao diện mới sẵn sàng. Đang sửa tin nhắn...")
            sent_msg = await send_or_edit_message(context=context, chat_id=chat_id, text=new_text, reply_markup=new_reply_markup, parse_mode='Markdown', message_to_edit=message_to_edit)
            if not sent_msg: logger.error(f"{log_prefix} Lỗi khi cập nhật giao diện cài đặt tổng hợp.")
        elif new_text:
            logger.error(f"{log_prefix} Lỗi từ build_main_settings_menu: {new_text}"); await send_or_edit_message(context=context, chat_id=chat_id, text=new_text, message_to_edit=message_to_edit)
        else:
            logger.error(f"{log_prefix} Lỗi khi tạo lại giao diện cài đặt tổng hợp."); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hiển thị cài đặt mới.", message_to_edit=message_to_edit)
    except (DatabaseError, UserNotFoundError) as e_ui:
         logger.error(f"{log_prefix} Lỗi DB/User khi build lại menu: {e_ui}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải lại giao diện cài đặt.", message_to_edit=message_to_edit)
    except Exception as e_ui_unk:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi hiển thị lại cài đặt: {e_ui_unk}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra khi hiển thị cài đặt.", message_to_edit=message_to_edit)
async def handle_callback_settings_menu(update, context):
    """Hàm điều phối chính cho các callback cài đặt (bắt đầu bằng 'settings:' hoặc 'toggle_')."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_settings_menu nhận callback không hợp lệ."); return
    if not query.data: logger.warning("handle_callback_settings_menu nhận data không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_settings_menu nhận user không hợp lệ."); return
    data = query.data
    telegram_id = query.from_user.id
    log_prefix = f"[SETTINGS_DISPATCH|UserTG:{telegram_id}|Data:{data}]" 
    logger.info(f"{log_prefix} Điều phối callback cài đặt.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    if data.startswith("toggle_audio:"):
        await _handle_toggle_audio(update, context)
    elif data.startswith("toggle_image:"):
        await _handle_toggle_image(update, context)
    elif data == "settings:toggle_summary":
        await _handle_toggle_summary(update, context)
    elif data.startswith("settings:"): 
        action_sent = False
        if chat_id != -1:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING); action_sent = True
            except Exception as e_action: logger.warning(f"{log_prefix} Lỗi gửi chat action cho '{data}': {e_action}")
        try: await query.answer()
        except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback cho '{data}': {e_ans}")
        try:
            if data == "settings:show_audio_image":
                logger.debug(f"{log_prefix} Chuyển đến cài đặt Audio/Ảnh.")
                text, reply_markup = await build_audio_image_settings_menu(telegram_id)
                if text and reply_markup:
                     await send_or_edit_message(context=context, chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='Markdown', message_to_edit=message_to_edit)
                else:
                     logger.error(f"{log_prefix} Lỗi tạo giao diện cài đặt chi tiết."); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải giao diện.", message_to_edit=message_to_edit)
            elif data == "settings:show_notifications":
                logger.debug(f"{log_prefix} Chuyển đến cài đặt Thông báo.")
                user_info_notify = get_user_by_telegram_id(telegram_id)
                text_notify, reply_markup_notify = build_notification_settings_menu(user_info_notify)
                if text_notify and reply_markup_notify:
                     await send_or_edit_message(context=context, chat_id=chat_id, text=text_notify, reply_markup=reply_markup_notify, parse_mode='Markdown', message_to_edit=message_to_edit)
                else:
                     logger.error(f"{log_prefix} Lỗi tạo giao diện cài đặt thông báo."); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải giao diện thông báo.", message_to_edit=message_to_edit)
            elif data == "settings:back_to_unified":
                logger.debug(f"{log_prefix} Quay lại menu cài đặt tổng hợp.")
                text_unified, reply_markup_unified = await build_main_settings_menu(telegram_id)
                if text_unified and reply_markup_unified:
                     await send_or_edit_message(context=context, chat_id=chat_id, text=text_unified, reply_markup=reply_markup_unified, parse_mode='Markdown', message_to_edit=message_to_edit)
                else:
                     logger.error(f"{log_prefix} Lỗi tạo lại menu cài đặt tổng hợp."); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi quay lại menu.", message_to_edit=message_to_edit)
        except (DatabaseError, UserNotFoundError) as e:
            logger.error(f"{log_prefix} Lỗi DB/User khi xử lý callback điều hướng '{data}': {e}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải dữ liệu hoặc giao diện.", message_to_edit=message_to_edit)
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi không mong muốn khi xử lý callback điều hướng '{data}': {e}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)
    else:
        logger.warning(f"{log_prefix} Callback không được xử lý bởi module settings: {data}")
        try: await query.answer("Hành động không được hỗ trợ trong menu này.")
        except Exception: pass
def register_handlers(app: Application):
    """Đăng ký các handler liên quan đến cài đặt người dùng."""
    app.add_handler(CommandHandler("flashcard_settings", handle_command_settings))
    app.add_handler(CallbackQueryHandler(handle_callback_settings_menu, pattern=r"^(settings:|toggle_)"))
    app.add_handler(CallbackQueryHandler(handle_command_settings, pattern=r"^show_unified_settings$"))
    logger.info("Đã đăng ký các handler cho module Settings.")
