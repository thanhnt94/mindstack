# Path: flashcard_v2/utils/helpers.py
"""
Module chứa các hàm tiện ích chung và decorator kiểm tra quyền.
Một số hàm có thể phụ thuộc vào Telegram API.
Các câu lệnh đã được tách dòng để đảm bảo tường minh.
Đã thêm hàm escape_md_v2 và loại bỏ type hint.
"""
import logging
import functools
import re # <<< Thêm import re
from datetime import datetime, time as dt_time, timedelta, timezone
# Bỏ import Bot, Message, Update, ContextTypes nếu không dùng trong type hint
# from telegram import Bot, Message, Update
# from telegram.ext import ContextTypes
from telegram import Bot # Giữ lại Bot vì cần để kiểm tra instance
from telegram.error import TelegramError, BadRequest, Forbidden
from database.query_user import get_user_by_telegram_id
from services.auth_service import check_permission

logger = logging.getLogger(__name__)

# --- HÀM MỚI: Escape MarkdownV2 ---
def escape_md_v2(text):
    """Hàm helper để escape các ký tự đặc biệt trong MarkdownV2."""
    if text is None:
        return ''
    # Danh sách các ký tự cần escape theo tài liệu của Telegram Bot API
    # Bao gồm: _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r'_*[]()~`>#+=-|{}.!'
    # Sử dụng regex để thêm dấu \ vào trước mỗi ký tự cần escape
    # Dùng str(text) để đảm bảo đầu vào là string
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', str(text))
# --- KẾT THÚC HÀM MỚI ---

def convert_unix_to_local(unix_timestamp, tz_offset_hours=7):
    """Chuyển đổi Unix timestamp sang chuỗi ngày giờ theo múi giờ địa phương."""
    if unix_timestamp is None:
        return ""
    try:
        tz = timezone(timedelta(hours=tz_offset_hours))
        dt = datetime.fromtimestamp(unix_timestamp, tz)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError) as e:
        logger.error(f"Lỗi convert timestamp {unix_timestamp}: {e}")
        return ""

def get_current_unix_timestamp(tz_offset_hours=7):
    """Lấy Unix timestamp hiện tại theo múi giờ."""
    try:
        tz = timezone(timedelta(hours=tz_offset_hours))
        now = datetime.now(tz)
        return int(now.timestamp())
    except Exception as e:
        logger.error(f"Lỗi lấy current timestamp: {e}")
        return int(datetime.now(timezone.utc).timestamp())

def get_midnight_timestamp(current_timestamp, tz_offset_hours=7):
    """Tính Unix timestamp của 0h ngày hôm sau."""
    try:
        tz = timezone(timedelta(hours=tz_offset_hours))
        dt_now = datetime.fromtimestamp(current_timestamp, tz)
        next_day = dt_now.date() + timedelta(days=1)
        dt_midnight_next_day = datetime.combine(next_day, dt_time.min, tzinfo=tz)
        return int(dt_midnight_next_day.timestamp())
    except Exception as e:
        logger.error(f"Lỗi tính midnight timestamp: {e}")
        # Fallback đơn giản là cộng thêm 1 ngày giây
        return current_timestamp + 86400

async def get_chat_display_name(bot_instance, user_id):
    """
    Lấy tên hiển thị (username hoặc first name) của người dùng từ Telegram API.
    """
    # Kiểm tra bot_instance là cần thiết
    if not isinstance(bot_instance, Bot):
        logger.error(f"Invalid bot_instance for get_username {user_id}.")
        return str(user_id)
    try:
        chat = await bot_instance.get_chat(user_id)
        display_name = None
        # Ưu tiên username nếu có
        if chat.username:
            display_name = chat.username
        else:
            display_name = chat.first_name
        # Trả về ID nếu không lấy được tên nào
        return display_name if display_name else str(user_id)
    except (BadRequest, Forbidden) as e:
        # Lỗi thường gặp khi user không tồn tại hoặc bot bị chặn
        logger.warning(f"Lỗi Telegram ({type(e).__name__}) khi get_chat {user_id}: {e}")
        return str(user_id)
    except TelegramError as e:
        # Các lỗi Telegram API khác
        logger.error(f"Lỗi Telegram khác khi get_chat {user_id}: {e}")
        return str(user_id)
    except Exception as e:
        # Các lỗi không mong muốn khác
        logger.error(f"Lỗi không mong muốn khi get_username {user_id}: {e}", exc_info=True)
        return str(user_id)

async def send_or_edit_message(context, chat_id, text, reply_markup=None, parse_mode=None, message_to_edit=None):
    """
    Gửi tin nhắn mới hoặc sửa tin nhắn đã có. Đã loại bỏ type hint.
    """
    log_prefix = f"[HELPER_SEND_OR_EDIT|Chat:{chat_id}]"
    sent_or_edited_message = None
    edit_failed = False
    # Chỉ thử sửa nếu message_to_edit là một đối tượng Message hợp lệ
    # Bỏ kiểm tra isinstance(message_to_edit, Message) vì đã xóa import
    if message_to_edit and hasattr(message_to_edit, 'message_id') and hasattr(message_to_edit, 'chat_id'):
        logger.debug(f"{log_prefix} Có message_to_edit ID: {message_to_edit.message_id}. Thử sửa...")
        try:
            # Không cần await message_to_edit.edit_text nữa, dùng context.bot
            await context.bot.edit_message_text(
                text=text,
                chat_id=message_to_edit.chat_id, # Dùng chat_id từ message cũ
                message_id=int(message_to_edit.message_id), # Đảm bảo là int
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            sent_or_edited_message = message_to_edit # Trả về message gốc nếu sửa thành công
            logger.debug(f"{log_prefix} Sửa message ID: {message_to_edit.message_id} thành công.")
        except BadRequest as e:
            error_message = str(e)
            if "Message is not modified" in error_message:
                # Coi như thành công nếu nội dung không đổi
                logger.info(f"{log_prefix} Message {message_to_edit.message_id} không thay đổi.")
                sent_or_edited_message = message_to_edit
            else:
                # Lỗi BadRequest khác (vd: parse_mode sai, tin nhắn quá cũ...)
                logger.error(f"{log_prefix} Lỗi BadRequest khi sửa message {message_to_edit.message_id}: {e}")
                edit_failed = True # Đánh dấu sửa lỗi để thử gửi mới
        except Exception as e:
             # Các lỗi khác khi sửa (vd: mạng, quyền...)
             logger.error(f"{log_prefix} Lỗi Exception khác khi sửa message {message_to_edit.message_id}: {e}", exc_info=True)
             edit_failed = True # Đánh dấu sửa lỗi
    else:
        # Không có message để sửa hoặc message không hợp lệ
        logger.debug(f"{log_prefix} Không có message_to_edit hợp lệ.")
        edit_failed = True # Chuyển sang gửi mới

    # Nếu sửa thất bại (hoặc không có gì để sửa), thử gửi tin nhắn mới
    if edit_failed:
        logger.debug(f"{log_prefix} Sửa lỗi hoặc không có message_to_edit. Thử gửi mới...")
        try:
            sent_or_edited_message = await context.bot.send_message(
                chat_id=chat_id, # Dùng chat_id được truyền vào
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            logger.info(f"{log_prefix} Gửi tin nhắn mới thành công. ID: {sent_or_edited_message.message_id}")
        except Exception as e_send:
            # Lỗi khi gửi tin nhắn mới
            logger.error(f"{log_prefix} Lỗi khi gửi tin nhắn mới: {e_send}", exc_info=True)
            sent_or_edited_message = None # Đặt lại thành None nếu gửi lỗi

    logger.debug(f"{log_prefix} Hàm kết thúc. Trả về message: {'Có' if sent_or_edited_message else 'None'}")
    return sent_or_edited_message

def require_permission(permission_name):
    """
    Decorator để kiểm tra quyền hạn của người dùng. Đã loại bỏ type hint.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            # Bỏ type hint khỏi update và context
            if not update or not update.effective_user:
                logger.warning(f"Decorator: Không tìm thấy user trong update cho {func.__name__}.")
                return None # Hoặc có thể raise lỗi tùy logic mong muốn
            user_id = update.effective_user.id
            log_prefix = f"[PERM_CHECK|User:{user_id}|Perm:{permission_name}|Func:{func.__name__}]"
            logger.debug(f"{log_prefix} Check quyền...")
            try:
                # Lấy thông tin user
                user_info = get_user_by_telegram_id(user_id)
                # Kiểm tra quyền
                has_perm = check_permission(user_info, permission_name)

                if has_perm:
                    logger.debug(f"{log_prefix} Cho phép.")
                    # Gọi hàm handler gốc nếu có quyền
                    return await func(update, context, *args, **kwargs)
                else:
                    # Thông báo từ chối nếu không có quyền
                    user_role = user_info.get('user_role', 'user') if user_info else 'unknown'
                    logger.warning(f"{log_prefix} Từ chối. Role '{user_role}' không có quyền '{permission_name}'.")
                    chat_id = update.effective_chat.id if update.effective_chat else user_id
                    permission_denied_text = "❌ Bạn không có quyền thực hiện hành động này."
                    message_to_edit_perm = None
                    # Nếu là callback query, cố gắng sửa tin nhắn gốc
                    if update.callback_query:
                        message_to_edit_perm = update.callback_query.message
                        try:
                            # Trả lời callback một cách nhẹ nhàng
                            await update.callback_query.answer("Bạn không có quyền.", show_alert=False)
                        except Exception as e_ans:
                             logger.warning(f"{log_prefix} Lỗi answer callback từ chối quyền: {e_ans}")

                    await send_or_edit_message(
                        context=context,
                        chat_id=chat_id,
                        text=permission_denied_text,
                        message_to_edit=message_to_edit_perm,
                        reply_markup=None # Không cần bàn phím
                    )
                    return None # Kết thúc xử lý handler
            except Exception as e_perm_check:
                 # Xử lý lỗi nếu có vấn đề khi kiểm tra quyền (vd: lỗi DB)
                 logger.error(f"{log_prefix} Lỗi khi kiểm tra quyền: {e_perm_check}", exc_info=True)
                 chat_id = update.effective_chat.id if update.effective_chat else user_id
                 message_to_edit_err = update.callback_query.message if update.callback_query else None
                 await send_or_edit_message(
                    context=context,
                    chat_id=chat_id,
                    text="❌ Lỗi khi kiểm tra quyền.",
                    message_to_edit=message_to_edit_err,
                    reply_markup=None
                 )
                 return None # Kết thúc xử lý handler
        return wrapper
    return decorator