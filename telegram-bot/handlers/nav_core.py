# Path: flashcard_v2/handlers/nav_core.py
"""
Module chứa các handlers cốt lõi cho việc điều hướng chính và xử lý lỗi.
Bao gồm lệnh /start, /help và các callback quay về menu chính, hiển thị trợ giúp.
Đã thêm cập nhật last_seen cho người dùng khi tương tác.
"""

import logging
import time # Thêm import time để lấy timestamp
import functools # Import functools nếu dùng decorator (đã có sẵn)

# Import từ thư viện telegram
from telegram import Update
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import Bot # Cần cho get_chat_display_name
from telegram import BotCommand
from telegram.ext import Application
from telegram.ext import ContextTypes
from telegram.ext import CommandHandler
from telegram.ext import CallbackQueryHandler
from telegram.error import Forbidden
from telegram.error import TelegramError # Thêm import TelegramError

# Import từ các module khác (tuyệt đối)
from database.query_user import get_user_by_telegram_id
from database.query_user import update_user_by_id # Thêm import update_user_by_id
from ui.core_ui import build_main_menu
from utils.helpers import send_or_edit_message
from utils.helpers import get_chat_display_name # Giả sử hàm này cần Bot instance
from utils.exceptions import DatabaseError
from utils.exceptions import UserNotFoundError

# Khởi tạo logger
logger = logging.getLogger(__name__)

async def handle_command_start(update, context):
    """
    Handler cho lệnh /flashcard và /start.
    Cập nhật last_seen và hiển thị giao diện chính.
    """
    # Kiểm tra đầu vào
    if not update or not update.effective_user or not update.message:
        logger.warning("handle_command_start: update/user/message không hợp lệ.")
        return

    telegram_id = update.effective_user.id
    log_prefix = "[NAV_CORE_START|UserTG:{}]".format(telegram_id)
    logger.info("{} Lệnh /flashcard hoặc /start.".format(log_prefix))
    chat_id = update.message.chat_id

    # --- Cập nhật last_seen ---
    try:
        user_info_for_update = get_user_by_telegram_id(telegram_id)
        user_db_id = user_info_for_update.get('user_id')
        if user_db_id:
            current_timestamp = int(time.time()) # Lấy Unix timestamp
            update_user_by_id(user_db_id, last_seen=current_timestamp)
            logger.debug("{}: Đã cập nhật last_seen cho user_id {}".format(log_prefix, user_db_id))
        else:
             logger.warning("{}: Không tìm thấy user_id để cập nhật last_seen.".format(log_prefix))
    except Exception as e_update_seen:
        logger.error("{}: Lỗi khi cập nhật last_seen: {}".format(log_prefix, e_update_seen))
    # --- Kết thúc cập nhật last_seen ---

    # --- Kiểm tra user có bị ban không và hiển thị menu chính ---
    try:
        # Lấy bot instance từ context
        bot_instance = None
        if hasattr(context, 'bot'):
            bot_instance = context.bot
        elif context.application and hasattr(context.application, 'bot'):
            bot_instance = context.application.bot

        if not bot_instance:
             logger.error("{} Không thể lấy bot instance từ context.".format(log_prefix))
             await update.message.reply_text(text="Lỗi: Không thể khởi tạo bot.")
             return

        # Gọi hàm build_main_menu (hàm này đã có logic kiểm tra 'banned')
        text, reply_markup = await build_main_menu(telegram_id, bot_instance)

        # Gửi tin nhắn trả về (menu hoặc thông báo lỗi/banned)
        if text: # Luôn có text trả về (hoặc menu hoặc thông báo)
            await update.message.reply_text(
                text=text,
                reply_markup=reply_markup, # Sẽ là None nếu user bị banned hoặc lỗi
                parse_mode='Markdown' if reply_markup else None # Chỉ dùng Markdown nếu có menu
            )
            if reply_markup:
                logger.debug("{} Đã gửi giao diện chính.".format(log_prefix))
            else:
                logger.info("{} Đã gửi thông báo (có thể là lỗi hoặc banned).".format(log_prefix))
        else:
            # Trường hợp rất hiếm: build_main_menu trả về (None, None)
            logger.error("{} Lỗi không xác định từ build_main_menu.".format(log_prefix))
            await update.message.reply_text(text="Lỗi tải giao diện.")

    # Không cần bắt UserNotFoundError ở đây vì build_main_menu đã xử lý
    # Không cần bắt DatabaseError ở đây vì build_main_menu đã xử lý
    except Exception as e:
        # Bắt các lỗi không mong muốn khác
        logger.error("{} Lỗi không mong muốn khi gửi giao diện chính: {}".format(log_prefix, e), exc_info=True)
        await update.message.reply_text(text="❌ Đã có lỗi xảy ra, vui lòng thử lại.")

async def handle_callback_back_to_main(update, context):
    """
    Handler cho callback 'handle_callback_back_to_main'.
    Cập nhật last_seen và hiển thị lại menu chính.
    """
    query = update.callback_query
    # Kiểm tra callback và user
    if not query or not query.from_user:
        logger.warning("handle_callback_back_to_main: query/user không hợp lệ.")
        return

    telegram_id = query.from_user.id
    log_prefix = "[NAV_CORE_BACK_MAIN|UserTG:{}]".format(telegram_id)
    logger.info("{} Quay lại menu chính.".format(log_prefix))
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message

    # --- Cập nhật last_seen ---
    try:
        user_info_for_update = get_user_by_telegram_id(telegram_id)
        user_db_id = user_info_for_update.get('user_id')
        if user_db_id:
            current_timestamp = int(time.time())
            update_user_by_id(user_db_id, last_seen=current_timestamp)
            logger.debug("{}: Đã cập nhật last_seen cho user_id {}".format(log_prefix, user_db_id))
        else:
            logger.warning("{}: Không tìm thấy user_id để cập nhật last_seen.".format(log_prefix))
    except Exception as e_update_seen:
        logger.error("{}: Lỗi khi cập nhật last_seen: {}".format(log_prefix, e_update_seen))
    # --- Kết thúc cập nhật last_seen ---

    try:
        # Xóa các state đặc biệt (nếu có) khi quay về menu chính
        removed_session_mode = context.user_data.pop('session_mode', None)
        if removed_session_mode:
            logger.debug("{} Đã xóa session_mode: '{}' khi quay về menu chính.".format(log_prefix, removed_session_mode))
        # Có thể xóa thêm các state khác nếu cần

        # Trả lời callback
        await query.answer()

        # Lấy bot instance
        bot_instance = None
        if hasattr(context, 'bot'):
            bot_instance = context.bot
        elif context.application and hasattr(context.application, 'bot'):
            bot_instance = context.application.bot

        if not bot_instance:
             logger.error("{} Không thể lấy bot instance từ context.".format(log_prefix))
             await send_or_edit_message(context=context, chat_id=chat_id, text="Lỗi: Không thể khởi tạo bot.", message_to_edit=message_to_edit)
             return

        # Gọi hàm build_main_menu (đã có kiểm tra banned)
        text, reply_markup = await build_main_menu(telegram_id, bot_instance)

        # Gửi hoặc sửa tin nhắn
        if text: # Luôn có text trả về
            sent_message = await send_or_edit_message(
                context=context,
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup, # None nếu bị banned/lỗi
                parse_mode='Markdown' if reply_markup else None,
                message_to_edit=message_to_edit
            )
            if not sent_message:
                 logger.error("{} Lỗi gửi/sửa menu chính.".format(log_prefix))
        else:
             logger.error("{} Lỗi không xác định từ build_main_menu.".format(log_prefix))
             await send_or_edit_message(context=context, chat_id=chat_id, text="Lỗi quay lại menu.", message_to_edit=message_to_edit)

    # Không cần bắt UserNotFoundError/DatabaseError vì build_main_menu đã xử lý
    except Exception as e:
        logger.error("{} Lỗi không mong muốn khi quay lại menu chính: {}".format(log_prefix, e), exc_info=True)
        # Cố gắng gửi tin nhắn lỗi mới nếu không sửa được
        try:
            await context.bot.send_message(chat_id=chat_id, text="❌ Có lỗi xảy ra.")
        except Exception as e_send:
            logger.error("{}: Lỗi gửi tin nhắn lỗi cuối cùng: {}".format(log_prefix, e_send))


async def handle_callback_show_help(update, context):
    """Handler cho callback 'show_help' hoặc lệnh /help."""
    query = None
    user_id_tg = -1
    chat_id = -1
    message_to_edit = None
    is_command = False

    # Xác định thông tin từ update
    if update.callback_query and update.callback_query.from_user:
        query = update.callback_query
        user_id_tg = query.from_user.id
        if query.message:
            chat_id = query.message.chat_id
            message_to_edit = query.message
        else:
            chat_id = user_id_tg # Fallback nếu callback không có message gốc
        try:
            await query.answer()
        except Exception as e_ans:
            logger.warning("Lỗi answer callback show help: {}".format(e_ans))
    elif update.message and update.effective_user:
        user_id_tg = update.effective_user.id
        chat_id = update.message.chat_id
        message_to_edit = None # Lệnh thì không sửa tin nhắn
        is_command = True
    else:
        logger.warning("handle_callback_show_help: update không hợp lệ hoặc thiếu user.")
        return

    log_prefix = "[NAV_CORE_HELP|UserTG:{}]".format(user_id_tg)
    logger.info("{} Yêu cầu trợ giúp (Command: {}).".format(log_prefix, is_command))

    try:
        # Nội dung trợ giúp (giữ nguyên)
        help_text = """
❓ **Trợ giúp & Hướng dẫn sử dụng Flashcard Bot** ❓
Chào mừng bạn đến với Flashcard Bot! Dưới đây là các chức năng chính:
📚 **Học & Ôn tập:**
  - Nhấn "▶️ **Tiếp tục học**" ở menu chính để bắt đầu học theo bộ và chế độ đã chọn.
  - Nhấn "🔄 **Thay đổi bộ**" để chọn bộ từ vựng khác.
  - Nhấn "⚡ **Thay đổi chế độ**" để chọn cách học/ôn tập (Chi tiết xem trong menu chọn chế độ).
  - Khi thẻ hiện ra (mặt trước): Nhấn "🔄 **Flip**" để xem mặt sau.
  - Khi mặt sau hiện ra: Đánh giá mức độ nhớ bằng các nút: ✅ (Nhớ), 🤔 (Mơ hồ), ❌ (Chưa nhớ).
  - Màn hình thông số sẽ hiện ra (nếu bật) hoặc thẻ tiếp theo sẽ hiển thị.
  - Nhấn "➕/✏️ **Ghi chú**" để quản lý ghi chú riêng cho thẻ.
  - Nhấn "🔙 **Menu chính**" để quay về menu chính.
🗂️ **Quản lý bộ thẻ:** (Truy cập từ Menu chính -> Quản lý bộ)
  - `Upload`: Gửi file Excel (.xlsx) để tạo bộ mới.
  - `Cập nhật`: Chọn bộ bạn tạo và gửi file Excel để sửa/thêm thẻ.
  - `Xoá`: Xóa bộ từ do bạn tạo.
  - `Export`: Tải về file Excel chứa dữ liệu bộ từ bạn tạo.
📈 **Thống kê:** (Truy cập từ Menu chính)
  - Xem tiến độ học tập hàng ngày, theo từng bộ, hoặc bảng xếp hạng.
⚙️ **Cài đặt:** (Truy cập từ Menu chính)
  - Bật/tắt âm thanh, hình ảnh cho mặt trước/sau.
  - Bật/tắt và cài đặt khoảng thời gian nhận thông báo nhắc nhở.
  - Bật/tắt hiển thị thông số sau khi ôn tập (dành cho Lite trở lên).
🎤 **Ôn tập Audio:** (Truy cập từ Menu chính)
  - Tạo file MP3 chứa audio các thẻ bạn chọn để nghe ôn tập.
📊 **Xuất dữ liệu:** (Truy cập từ Menu chính)
  - Tải về toàn bộ dữ liệu học tập của bạn ra file Excel.
🔔 **Thông báo:**
  - Bot sẽ tự động gửi nhắc nhở nếu bạn có thẻ đến hạn.
  - Bot cũng sẽ gửi thông báo nếu vai trò của bạn được Admin thay đổi.
💡 **Mẹo:**
  - Sử dụng ghi chú để lưu ví dụ, cách dùng, hoặc mẹo nhớ từ.
  - Duy trì việc ôn tập đều đặn để đạt hiệu quả tốt nhất!
Chúc bạn học tốt! 😊
        """
        # Nút quay lại menu chính
        keyboard = [[InlineKeyboardButton("🔙 Menu chính", callback_data="handle_callback_back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Gửi hoặc sửa tin nhắn trợ giúp
        sent_message = await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text=help_text.strip(), # Xóa khoảng trắng thừa
            reply_markup=reply_markup,
            parse_mode='Markdown', # Dùng Markdown cho định dạng
            message_to_edit=message_to_edit # Chỉ sửa nếu là callback
        )
        if not sent_message:
            logger.error("{} Lỗi gửi/sửa tin nhắn trợ giúp.".format(log_prefix))

    except Exception as e:
        logger.error("{} Lỗi không mong muốn khi hiển thị trợ giúp: {}".format(log_prefix, e), exc_info=True)
        await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text="❌ Có lỗi khi hiển thị trợ giúp.",
            message_to_edit=message_to_edit
        )

async def error_handler(update, context):
    """Log lỗi và thông báo cho người dùng nếu cần."""
    err = None
    # Lấy lỗi từ context
    if context and hasattr(context, 'error'):
        err = context.error
    else:
        logger.error("Lỗi không xác định hoặc update/context không đúng cấu trúc: update={}".format(update))
        return # Không có lỗi để xử lý

    # Ghi log chi tiết lỗi
    update_details = update if isinstance(update, Update) else str(update)
    logger.error("Lỗi trong quá trình xử lý update: {}".format(err), exc_info=context.error, extra={'update_details': update_details})

    # Thông báo lỗi cho người dùng (nếu có thể và cần thiết)
    user_id_err = -1
    chat_id_err = -1
    # Cố gắng lấy user_id và chat_id từ update
    if isinstance(update, Update) and update.effective_user:
        user_id_err = update.effective_user.id
        chat_id_err = update.effective_chat.id if update.effective_chat else user_id_err

    if chat_id_err != -1: # Chỉ gửi nếu xác định được chat_id
        try:
            err_str = str(err).lower() # Chuyển lỗi sang chữ thường để kiểm tra
            # Danh sách các lỗi thường gặp không cần thông báo cho người dùng
            ignore_errors = [
                "message is not modified",
                "query is too old",
                "chat not found",
                "bot was blocked by the user"
            ]
            should_notify_user = True
            # Kiểm tra xem lỗi có nằm trong danh sách bỏ qua không
            for ignore_msg in ignore_errors:
                if ignore_msg in err_str:
                    logger.info("Bỏ qua thông báo lỗi cho user {} do lỗi: {}".format(user_id_err, ignore_msg))
                    should_notify_user = False
                    break
            # Không thông báo nếu bot bị chặn
            if isinstance(err, Forbidden):
                should_notify_user = False
                logger.warning("Bot bị chặn bởi user {}.".format(user_id_err))

            # Nếu cần thông báo lỗi
            if should_notify_user:
                error_message_user = "⚠️ Đã có lỗi xảy ra trong quá trình xử lý yêu cầu của bạn. Vui lòng thử lại sau hoặc liên hệ quản trị viên nếu lỗi tiếp diễn."
                # Lấy bot instance
                bot_instance = None
                if hasattr(context, 'bot'):
                    bot_instance = context.bot
                elif context.application and hasattr(context.application, 'bot'):
                    bot_instance = context.application.bot

                # Gửi tin nhắn lỗi
                if bot_instance:
                     await bot_instance.send_message(chat_id=chat_id_err, text=error_message_user)
                     logger.info("Đã gửi thông báo lỗi tới chat_id {} cho user {}.".format(chat_id_err, user_id_err))
                else:
                     logger.error("Không thể lấy bot instance để gửi thông báo lỗi cho user {}.".format(user_id_err))
        except Forbidden:
            # Ghi log nếu bot bị chặn khi đang cố gửi thông báo lỗi
            logger.warning("Bot bị chặn bởi user {} khi gửi thông báo lỗi.".format(user_id_err))
        except Exception as e_send_err:
            # Ghi log nếu có lỗi khác khi gửi thông báo lỗi
            logger.error("Lỗi khi gửi thông báo lỗi tới chat_id {} cho user {}: {}".format(chat_id_err, user_id_err, e_send_err))

def register_handlers(app: Application):
    """Đăng ký các handler điều hướng cốt lõi và trợ giúp."""
    # Lệnh bắt đầu/menu chính
    app.add_handler(CommandHandler("start", handle_command_start))
    app.add_handler(CommandHandler("flashcard", handle_command_start))
    # Lệnh trợ giúp
    app.add_handler(CommandHandler("help", handle_callback_show_help))
    # Callback quay về menu chính
    app.add_handler(CallbackQueryHandler(handle_callback_back_to_main, pattern=r"^handle_callback_back_to_main$"))
    # Callback hiển thị trợ giúp
    app.add_handler(CallbackQueryHandler(handle_callback_show_help, pattern=r"^show_help$"))
    logger.info("Đã đăng ký các handler cho module Nav Core.")