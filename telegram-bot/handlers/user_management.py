# Path: flashcard_v2/handlers/user_management.py
"""
Module chứa các handlers cho chức năng quản lý người dùng trong phần admin.
Bao gồm xem danh sách, xem chi tiết, thay đổi vai trò, thay đổi giới hạn.
Đã sửa logic đặt giới hạn về 0 khi ban user.
"""
import logging
import asyncio

# Import từ thư viện telegram
from telegram import Update
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram.ext import Application
from telegram.ext import ContextTypes
from telegram.ext import ConversationHandler
from telegram.ext import CallbackQueryHandler
from telegram.ext import MessageHandler
from telegram.ext import CommandHandler
from telegram.ext import filters

# Import từ các module khác (tuyệt đối)
from config import SET_DAILY_LIMIT # State ConversationHandler
from config import CAN_MANAGE_USERS
from config import CAN_SET_ROLES
from config import CAN_SET_LIMITS
from config import DAILY_LIMIT_USER
from config import DAILY_LIMIT_LITE
from config import DAILY_LIMIT_VIP
# ROLE_PERMISSIONS không cần import trực tiếp ở đây vì đã dùng trong decorator
from database.query_user import get_user_by_telegram_id
from database.query_user import get_all_users
from database.query_user import update_user_role
from database.query_user import update_user_daily_limit
from ui.admin_ui import build_user_management_keyboard
from ui.admin_ui import build_user_info_display
from ui.admin_ui import build_set_role_keyboard
from utils.helpers import get_chat_display_name
from utils.helpers import send_or_edit_message
from utils.helpers import require_permission # Decorator kiểm tra quyền
from utils.exceptions import DatabaseError
from utils.exceptions import UserNotFoundError
from utils.exceptions import ValidationError
from utils.exceptions import DuplicateError

# Khởi tạo logger
logger = logging.getLogger(__name__)

@require_permission(CAN_MANAGE_USERS)
async def handle_callback_manage_users(update, context):
    """
    Handler cho callback 'manage_users'.
    Hiển thị danh sách người dùng để admin chọn.
    """
    query = update.callback_query
    if not query or not query.from_user:
        logger.warning("handle_callback_manage_users: Callback/User không hợp lệ.")
        return # Thoát nếu callback hoặc user không hợp lệ

    # Trả lời callback
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning("Lỗi answer callback manage users: {}".format(e_ans))

    admin_user_id = query.from_user.id
    log_prefix = "[USER_MGMT_LIST|Admin:{}]".format(admin_user_id)
    logger.info("{} Yêu cầu quản lý TV.".format(log_prefix))
    chat_id = admin_user_id # Phản hồi lại cho admin
    message_to_edit = query.message # Tin nhắn gốc để sửa

    try:
        # Lấy danh sách tất cả user từ DB
        users = get_all_users()

        # Nếu không có user nào
        if not users:
            logger.warning("{} Không có user.".format(log_prefix))
            kb_back = [[InlineKeyboardButton("🔙 Quay lại Menu Admin", callback_data="flashcard_admin")]]
            reply_markup = InlineKeyboardMarkup(kb_back)
            await send_or_edit_message(
                context=context,
                chat_id=chat_id,
                text="Không có thành viên nào trong hệ thống.",
                reply_markup=reply_markup,
                message_to_edit=message_to_edit
            )
            return # Kết thúc hàm

        logger.debug("{} Tìm thấy {} user.".format(log_prefix, len(users)))

        # Lấy bot instance để lấy tên hiển thị
        bot_instance = None
        if hasattr(context, 'bot'):
            bot_instance = context.bot
        elif context.application and hasattr(context.application, 'bot'):
            bot_instance = context.application.bot

        if not bot_instance:
            logger.error("{} Không thể lấy bot instance.".format(log_prefix))
            await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi khởi tạo bot.", message_to_edit=message_to_edit)
            return

        # Tạo bàn phím danh sách user (hàm này đã được sửa để có icon)
        reply_markup = await build_user_management_keyboard(users, bot_instance)

        # Gửi hoặc sửa tin nhắn với danh sách user
        if reply_markup:
            sent_msg = await send_or_edit_message(
                context=context,
                chat_id=chat_id,
                text="Chọn thành viên để xem/quản lý:",
                reply_markup=reply_markup,
                message_to_edit=message_to_edit
            )
            if not sent_msg:
                 logger.error("{} Lỗi gửi danh sách TV.".format(log_prefix))
        else:
            # Lỗi nếu không tạo được bàn phím
            logger.error("{} Lỗi tạo keyboard danh sách user.".format(log_prefix))
            await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hiển thị danh sách thành viên.", message_to_edit=message_to_edit)

    except DatabaseError as e:
        logger.error("{} Lỗi DB khi lấy danh sách user: {}".format(log_prefix, e))
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải danh sách thành viên.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error("{} Lỗi không mong muốn khi quản lý user: {}".format(log_prefix, e), exc_info=True)
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

@require_permission(CAN_MANAGE_USERS)
async def handle_callback_show_user_info(update, context):
    """
    Handler cho callback 'user_info:<target_telegram_id>'.
    Hiển thị thông tin chi tiết của người dùng được chọn.
    """
    query = update.callback_query
    # Kiểm tra callback hợp lệ
    if not query or not query.from_user or not query.data:
        logger.warning("handle_callback_show_user_info: Callback/User/Data không hợp lệ.")
        return

    # Trả lời callback
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning("Lỗi answer callback show user info: {}".format(e_ans))

    admin_user_id = query.from_user.id
    log_prefix = "[USER_MGMT_INFO|Admin:{}]".format(admin_user_id)
    target_telegram_id = None
    chat_id = admin_user_id # Phản hồi cho admin
    message_to_edit = query.message

    try:
        # Parse target_telegram_id từ callback data
        parts = query.data.split(":")
        if len(parts) < 2:
            raise ValueError("Callback data không đúng định dạng")
        target_telegram_id_str = parts[1]
        target_telegram_id = int(target_telegram_id_str)
        logger.info("{} Xem info user TG ID: {}.".format(log_prefix, target_telegram_id))

        # Lấy thông tin user từ DB
        target_user_info = get_user_by_telegram_id(target_telegram_id)

        # Lấy tên hiển thị
        bot_instance_info = context.bot if hasattr(context, 'bot') else (context.application.bot if context.application and hasattr(context.application, 'bot') else None)
        username = str(target_telegram_id) # Mặc định là ID nếu không lấy được tên
        if bot_instance_info:
            try:
                # Gọi hàm helper để lấy tên
                username = await get_chat_display_name(bot_instance_info, target_telegram_id)
            except Exception as e_get_name:
                 logger.warning("{} Lỗi lấy tên hiển thị cho {}: {}".format(log_prefix, target_telegram_id, e_get_name))
        else:
            logger.warning("{} Không có bot instance để lấy username.".format(log_prefix))

        logger.debug("{} Lấy info OK.".format(log_prefix))

        # Tạo nội dung và bàn phím hiển thị thông tin
        text, reply_markup = build_user_info_display(target_user_info, username)

        # Gửi hoặc sửa tin nhắn
        if text and reply_markup:
            sent_msg = await send_or_edit_message(
                context=context,
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown', # Dùng Markdown vì có định dạng ** và `
                message_to_edit=message_to_edit
            )
            if not sent_msg:
                 logger.error("{} Lỗi hiển thị thông tin user.".format(log_prefix))
        else:
            # Lỗi nếu không tạo được UI
            logger.error("{} Lỗi tạo UI thông tin user.".format(log_prefix))
            await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hiển thị thông tin.", message_to_edit=message_to_edit)

    except (ValueError, IndexError):
        logger.error("{} Callback data lỗi: {}".format(log_prefix, query.data))
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi: Dữ liệu ID không hợp lệ.", message_to_edit=message_to_edit)
    except UserNotFoundError:
        # Xử lý trường hợp user không tồn tại trong DB
        logger.warning("{} Không tìm thấy user TG ID {}.".format(log_prefix, target_telegram_id))
        kb_back = [[InlineKeyboardButton("🔙 Quay lại Danh sách", callback_data="manage_users")]]
        reply_markup = InlineKeyboardMarkup(kb_back)
        await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text="❌ Không tìm thấy thành viên ID {}.".format(target_telegram_id),
            reply_markup=reply_markup,
            message_to_edit=message_to_edit
        )
    except DatabaseError as e:
        logger.error("{} Lỗi DB lấy info user {}: {}".format(log_prefix, target_telegram_id, e))
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải thông tin TV ID {}.".format(target_telegram_id), message_to_edit=message_to_edit)
    except Exception as e:
        logger.error("{} Lỗi khác khi xem info user: {}".format(log_prefix, e), exc_info=True)
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

@require_permission(CAN_SET_ROLES)
async def update_user_role_callback(update, context):
    """
    Handler cho callback 'set_role:<target_telegram_id>'.
    Hiển thị các nút chọn vai trò mới cho người dùng.
    """
    query = update.callback_query
    # Kiểm tra callback hợp lệ
    if not query or not query.from_user or not query.data:
        logger.warning("update_user_role_callback: Callback/User/Data không hợp lệ.")
        return

    # Trả lời callback
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning("Lỗi answer callback set role: {}".format(e_ans))

    admin_user_id = query.from_user.id
    log_prefix = "[USER_MGMT_SET_ROLE|Admin:{}]".format(admin_user_id)
    chat_id = admin_user_id # Phản hồi cho admin
    message_to_edit = query.message

    try:
        # Parse target_telegram_id
        parts = query.data.split(":")
        if len(parts) < 2:
            raise ValueError("Callback data không đúng định dạng")
        target_telegram_id_str = parts[1]
        target_telegram_id = int(target_telegram_id_str)
        logger.info("{} Yêu cầu đổi role user TG ID: {}.".format(log_prefix, target_telegram_id))

        # Tạo bàn phím chọn vai trò (hàm này đã được cập nhật để tự lấy roles)
        reply_markup = build_set_role_keyboard(target_telegram_id)

        # Gửi hoặc sửa tin nhắn
        if reply_markup:
            sent_msg = await send_or_edit_message(
                context=context,
                chat_id=chat_id,
                text="Chọn vai trò mới cho người dùng:",
                reply_markup=reply_markup,
                message_to_edit=message_to_edit
            )
            if not sent_msg:
                 logger.error("{} Lỗi gửi menu chọn role.".format(log_prefix))
        else:
            # Lỗi nếu không tạo được bàn phím
            logger.error("{} Lỗi tạo keyboard chọn role.".format(log_prefix))
            await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hiển thị lựa chọn vai trò.", message_to_edit=message_to_edit)

    except (ValueError, IndexError):
        logger.error("{} Callback data lỗi: {}".format(log_prefix, query.data))
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi: Dữ liệu ID không hợp lệ.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error("{} Lỗi khác khi hiển thị menu chọn role: {}".format(log_prefix, e), exc_info=True)
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

@require_permission(CAN_SET_ROLES)
async def update_user_role_confirm_callback(update, context):
    """
    Handler cho callback 'set_role_confirm:<target_telegram_id>:<new_role>'.
    Xác nhận và thực hiện thay đổi vai trò, cập nhật giới hạn thẻ mới tương ứng.
    Đã sửa để đặt giới hạn = 0 khi vai trò là 'banned'.
    """
    query = update.callback_query
    # Kiểm tra callback hợp lệ
    if not query or not query.from_user or not query.data:
        logger.warning("update_user_role_confirm_callback: Callback/User/Data không hợp lệ.")
        return

    # Trả lời callback
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning("Lỗi answer callback confirm role: {}".format(e_ans))

    admin_user_id = query.from_user.id
    log_prefix = "[USER_MGMT_CONFIRM_ROLE|Admin:{}]".format(admin_user_id)
    chat_id = admin_user_id # Phản hồi cho admin
    message_to_edit = query.message
    target_telegram_id = None
    new_role = None
    old_role = None # Lưu vai trò cũ để gửi thông báo nếu thay đổi
    message = "Lỗi không xác định khi cập nhật vai trò." # Tin nhắn phản hồi mặc định
    reply_markup = None # Bàn phím quay lại (nếu có)
    role_update_success = False # Cờ đánh dấu cập nhật vai trò thành công

    try:
        # Parse dữ liệu từ callback
        parts = query.data.split(":")
        if len(parts) != 3:
            raise ValueError("Callback data không đúng định dạng (cần 3 phần)")
        target_telegram_id_str = parts[1]
        target_telegram_id = int(target_telegram_id_str)
        new_role = parts[2] # Tên vai trò mới ('user', 'lite', 'vip', 'admin', 'banned')
        logger.info("{} Xác nhận đổi role user {} -> '{}'.".format(log_prefix, target_telegram_id, new_role))

        # Lấy vai trò cũ (không bắt buộc, chỉ để gửi thông báo)
        try:
            user_info_before_update = get_user_by_telegram_id(target_telegram_id)
            old_role = user_info_before_update.get('user_role')
            logger.debug("{} Vai trò cũ của user {}: '{}'.".format(log_prefix, target_telegram_id, old_role))
        except (UserNotFoundError, DatabaseError) as e_get_old:
             # Nếu không lấy được vai trò cũ, vẫn tiếp tục
             logger.warning("{} Không thể lấy vai trò cũ của user {}: {}.".format(log_prefix, target_telegram_id, e_get_old))
             old_role = None

        # Cập nhật vai trò mới vào DB
        role_update_success = update_user_role(target_telegram_id, new_role)

        # Nếu cập nhật vai trò thành công
        if role_update_success:
            logger.info("{} Update role OK.".format(log_prefix))

            # === SỬA LỖI: Xác định giới hạn mới dựa trên vai trò mới ===
            new_limit = DAILY_LIMIT_USER # Mặc định cho 'user'
            if new_role == 'banned':
                new_limit = 0 # Đặt giới hạn về 0 nếu bị ban
            elif new_role == 'lite':
                new_limit = DAILY_LIMIT_LITE
            elif new_role == 'vip' or new_role == 'admin':
                new_limit = DAILY_LIMIT_VIP
            # ==========================================================

            logger.info("{} Cập nhật limit theo role mới -> {}.".format(log_prefix, new_limit))
            try:
                 # Cập nhật giới hạn mới vào DB
                 limit_update_success = update_user_daily_limit(target_telegram_id, new_limit)
                 # Tạo tin nhắn phản hồi dựa trên kết quả cập nhật limit
                 if limit_update_success:
                      # Sửa tin nhắn để phản ánh đúng limit khi banned
                      if new_role == 'banned':
                          message = "✅ Đã đổi vai trò user `{}` thành **{}** và cập nhật giới hạn thẻ mới thành **0**.".format(target_telegram_id, new_role)
                      else:
                          message = "✅ Đã đổi vai trò user `{}` thành **{}** và cập nhật giới hạn thẻ mới thành **{}**.".format(target_telegram_id, new_role, new_limit)
                 else:
                      # Thông báo nếu chỉ cập nhật được role mà không cập nhật được limit
                      message = "✅ Đã đổi vai trò `{}` thành **{}**. Không cập nhật giới hạn (có thể do lỗi hoặc không cần thiết).".format(target_telegram_id, new_role)
                      logger.warning("{} Cập nhật limit không thành công hoặc không thay đổi.".format(log_prefix))
            except (ValidationError, DatabaseError, UserNotFoundError) as e_limit:
                 # Thông báo nếu cập nhật role thành công nhưng lỗi khi cập nhật limit
                 message = "✅ Đã đổi vai trò `{}` thành **{}**, nhưng **lỗi** cập nhật giới hạn: {}".format(target_telegram_id, new_role, e_limit)
                 logger.error("{} Lỗi cập nhật limit: {}".format(log_prefix, e_limit))
        else:
            # Thông báo nếu cập nhật vai trò thất bại
            message = "⚠️ Không thể cập nhật vai trò cho user `{}` (có thể user không tồn tại hoặc vai trò không đổi).".format(target_telegram_id)
            logger.warning("{} update_user_role trả về False.".format(log_prefix))
            role_update_success = False # Đảm bảo cờ là False

    # Xử lý lỗi parse callback data
    except (ValueError, IndexError) as e_parse:
        logger.error("{} Callback data lỗi: {}. Lỗi: {}".format(log_prefix, query.data, e_parse))
        message = "❌ Lỗi: Dữ liệu callback không hợp lệ."
        role_update_success = False
    # Xử lý lỗi validation (ví dụ: role không hợp lệ)
    except ValidationError as e_role:
        logger.error("{} Lỗi Validation khi cập nhật role: {}".format(log_prefix, e_role))
        message = "❌ {}".format(e_role)
        role_update_success = False
    # Xử lý lỗi DB hoặc không tìm thấy user
    except (DatabaseError, DuplicateError, UserNotFoundError) as e_db:
        logger.error("{} Lỗi DB/User/Duplicate khi cập nhật role: {}".format(log_prefix, e_db))
        message = "❌ Lỗi database khi cập nhật vai trò: {}".format(e_db)
        role_update_success = False
    # Xử lý lỗi không mong muốn khác
    except Exception as e_unknown:
        logger.error("{} Lỗi không mong muốn khác: {}".format(log_prefix, e_unknown), exc_info=True)
        message = "❌ Có lỗi không mong muốn xảy ra trong quá trình cập nhật."
        role_update_success = False

    # Tạo nút quay lại thông tin user nếu có target_telegram_id
    if target_telegram_id:
        kb_back = [[InlineKeyboardButton("🔙 Quay lại Info User", callback_data="user_info:{}".format(target_telegram_id))]]
        reply_markup = InlineKeyboardMarkup(kb_back)

    # Gửi tin nhắn phản hồi cho admin
    await send_or_edit_message(
        context=context,
        chat_id=chat_id,
        text=message,
        reply_markup=reply_markup,
        parse_mode='Markdown',
        message_to_edit=message_to_edit
    )

    # Gửi thông báo cho người dùng nếu vai trò thực sự thay đổi
    if role_update_success and old_role is not None and old_role != new_role and target_telegram_id:
        logger.info("{} Vai trò đã thay đổi từ '{}' -> '{}'. Gửi thông báo tới user {}.".format(log_prefix, old_role, new_role, target_telegram_id))
        # Tạo nội dung thông báo dựa trên vai trò mới
        notification_message = "🔔 Thông báo: Vai trò của bạn đã được quản trị viên cập nhật thành **{}**.".format(new_role.upper())
        # Có thể thêm các tin nhắn đặc biệt cho việc nâng cấp hoặc bị ban
        role_levels = {'banned': 0, 'user': 1, 'lite': 2, 'vip': 3, 'admin': 4}
        if new_role == 'banned':
            notification_message = "🚫 Tài khoản của bạn đã bị khóa bởi quản trị viên."
        elif role_levels.get(new_role, 0) > role_levels.get(old_role, 0): # Nếu được nâng cấp
            notification_message = "🎉 Chúc mừng! Vai trò của bạn đã được nâng cấp thành **{}**.".format(new_role.upper())

        try:
            # Gửi thông báo bất đồng bộ tới người dùng
            # Không cần await trực tiếp ở đây, để không chặn admin
            asyncio.create_task(
                 context.bot.send_message(chat_id=target_telegram_id, text=notification_message, parse_mode='Markdown')
            )
            logger.info("{} Đã lên lịch gửi thông báo thay đổi role.".format(log_prefix))
        except Exception as e_notify:
            logger.error("{} Lỗi gửi thông báo role cho {}: {}".format(log_prefix, target_telegram_id, e_notify), exc_info=False)

@require_permission(CAN_SET_LIMITS)
async def handle_callback_start_edit_limit(update, context):
    """
    Entry Point: Bắt đầu conversation sửa giới hạn thẻ mới.
    Kích hoạt bởi callback 'edit_limit:<target_telegram_id>'.
    """
    query = update.callback_query
    # Kiểm tra callback hợp lệ
    if not query or not query.from_user or not query.data:
        logger.warning("handle_callback_start_edit_limit: Callback/User/Data không hợp lệ.")
        return ConversationHandler.END # Kết thúc nếu không hợp lệ

    # Trả lời callback
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning("Lỗi answer callback start edit limit: {}".format(e_ans))

    admin_user_id = query.from_user.id
    log_prefix = "[USER_MGMT_START_LIMIT_CONV|Admin:{}]".format(admin_user_id)
    chat_id = admin_user_id # Phản hồi cho admin
    message_to_edit = query.message

    try:
        # Parse target_telegram_id
        parts = query.data.split(":")
        if len(parts) < 2:
            raise ValueError("Callback data không đúng định dạng")
        target_telegram_id_str = parts[1]
        target_telegram_id = int(target_telegram_id_str)
        logger.info("{} Bắt đầu conv sửa limit user TG: {}.".format(log_prefix, target_telegram_id))

        # Lưu target_telegram_id vào user_data để state sau sử dụng
        context.user_data["target_user_id_for_limit"] = target_telegram_id

        # Gửi yêu cầu nhập giới hạn mới
        sent_msg = await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text="Nhập giới hạn thẻ mới/ngày cho user `{}` (số nguyên >= 0).\n\nGõ /cancel để hủy.".format(target_telegram_id),
            parse_mode='Markdown',
            message_to_edit=message_to_edit,
            reply_markup=None # Xóa bàn phím cũ
        )

        # Nếu gửi yêu cầu thành công, chuyển state
        if not sent_msg:
            logger.error("{} Lỗi gửi yêu cầu nhập limit.".format(log_prefix))
            context.user_data.pop("target_user_id_for_limit", None) # Dọn dẹp nếu lỗi
            return ConversationHandler.END

        return SET_DAILY_LIMIT # Chuyển sang state chờ nhập limit

    except (ValueError, IndexError):
        logger.error("{} Callback data lỗi: {}".format(log_prefix, query.data))
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi: Dữ liệu ID không hợp lệ.", message_to_edit=message_to_edit)
        return ConversationHandler.END
    except Exception as e:
        logger.error("{} Lỗi không mong muốn: {}".format(log_prefix, e), exc_info=True)
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)
        return ConversationHandler.END

async def _handle_state_set_limit_input(update, context):
    """
    Handler cho state SET_DAILY_LIMIT, xử lý input giới hạn từ admin.
    """
    # Kiểm tra đầu vào
    if not update or not update.effective_user or not update.message:
        logger.warning("_handle_state_set_limit_input: update/user/message không hợp lệ.")
        return SET_DAILY_LIMIT # Giữ state nếu update không hợp lệ
    if not update.message.text:
        logger.warning("_handle_state_set_limit_input: message không chứa text.")
        await update.message.reply_text("Vui lòng nhập giới hạn là một con số hoặc gõ /cancel.")
        return SET_DAILY_LIMIT # Giữ state chờ input đúng

    admin_user_id = update.effective_user.id
    chat_id = update.message.chat_id
    log_prefix = "[USER_MGMT_LIMIT_INPUT|Admin:{}]".format(admin_user_id)
    message_text = update.message.text # Giới hạn admin nhập

    # Lấy target_telegram_id đã lưu
    target_telegram_id = context.user_data.get("target_user_id_for_limit")
    if not target_telegram_id:
        logger.error("{} Thiếu target_user_id_for_limit trong user_data.".format(log_prefix))
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi: Không xác định được người dùng cần sửa limit. Vui lòng thử lại từ đầu.")
        return ConversationHandler.END # Kết thúc nếu mất context

    logger.info("{} Admin nhập limit '{}' cho user TG {}.".format(log_prefix, message_text, target_telegram_id))
    response_message = ""
    should_end_conversation = True # Mặc định là kết thúc sau khi xử lý
    reply_markup_limit = None # Bàn phím trả về

    try:
        # Chuyển input thành số nguyên
        new_limit = int(message_text)
        # Gọi hàm cập nhật limit trong DB (hàm này có kiểm tra >= 0)
        limit_update_success = update_user_daily_limit(target_telegram_id, new_limit)
        if limit_update_success:
            response_message = "✅ Đã cập nhật giới hạn thẻ mới/ngày cho user `{}` thành **{}**.".format(target_telegram_id, new_limit)
            logger.info("{} Cập nhật limit OK.".format(log_prefix))
        else:
            # Có thể do user không tồn tại hoặc limit không đổi
            response_message = "⚠️ Không tìm thấy user `{}` hoặc giới hạn không thay đổi.".format(target_telegram_id)
            logger.warning("{} update_user_daily_limit trả về False.".format(log_prefix))
        # Tạo nút quay lại Info User
        kb_back_info = [[InlineKeyboardButton("🔙 Quay lại Info User", callback_data="user_info:{}".format(target_telegram_id))]]
        reply_markup_limit = InlineKeyboardMarkup(kb_back_info)

    # Xử lý lỗi nếu input không phải số
    except ValueError:
        logger.warning("{} Input không phải số nguyên: {}.".format(log_prefix, message_text))
        response_message = "❌ '{}' không phải là số. Vui lòng nhập số nguyên >= 0 hoặc gõ /cancel.".format(message_text)
        should_end_conversation = False # Không kết thúc, chờ nhập lại
        # Gửi thông báo lỗi và giữ state
        await send_or_edit_message(context=context, chat_id=chat_id, text=response_message)
        return SET_DAILY_LIMIT
    # Xử lý lỗi validation từ hàm DB (ví dụ: limit < 0)
    except ValidationError as e:
        logger.warning("{} Lỗi Validation khi cập nhật limit: {}".format(log_prefix, e))
        response_message = "❌ {}\nVui lòng nhập lại hoặc gõ /cancel.".format(e)
        should_end_conversation = False # Không kết thúc, chờ nhập lại
        # Gửi thông báo lỗi và giữ state
        await send_or_edit_message(context=context, chat_id=chat_id, text=response_message)
        return SET_DAILY_LIMIT
    # Xử lý lỗi DB hoặc không tìm thấy user
    except (DatabaseError, UserNotFoundError) as e:
        logger.error("{} Lỗi DB/User khi cập nhật limit: {}".format(log_prefix, e))
        response_message = "❌ Lỗi khi cập nhật limit cho user `{}`.".format(target_telegram_id)
        should_end_conversation = True # Kết thúc vì lỗi DB
    # Xử lý lỗi không mong muốn khác
    except Exception as e:
        logger.exception("{} Lỗi khác khi cập nhật limit: {}".format(log_prefix, e))
        response_message = "❌ Có lỗi không mong muốn xảy ra."
        should_end_conversation = True # Kết thúc vì lỗi

    # Gửi tin nhắn phản hồi cuối cùng
    await send_or_edit_message(context=context, chat_id=chat_id, text=response_message, parse_mode='Markdown', reply_markup=reply_markup_limit)

    # Nếu xử lý xong (thành công hoặc lỗi không thể thử lại) thì kết thúc conversation
    if should_end_conversation:
        context.user_data.pop("target_user_id_for_limit", None) # Dọn dẹp context
        logger.debug("{} Kết thúc conversation sửa limit.".format(log_prefix))
        return ConversationHandler.END
    else:
        # Nếu cần nhập lại, giữ state
        return SET_DAILY_LIMIT

async def _handle_cancel_edit_limit(update, context):
    """Fallback handler để hủy conversation sửa giới hạn."""
    # Kiểm tra đầu vào
    if not update or not update.effective_user:
        return ConversationHandler.END

    user_id = update.effective_user.id
    log_prefix = "[USER_MGMT_CANCEL_LIMIT|User:{}]".format(user_id)
    logger.info("{} Hủy thao tác sửa limit.".format(log_prefix))

    # Lấy target_telegram_id để tạo nút quay lại đúng user
    target_telegram_id = context.user_data.pop("target_user_id_for_limit", None)

    # Chuẩn bị tin nhắn và bàn phím hủy
    cancel_message_text = "Đã hủy thao tác sửa giới hạn."
    message_to_edit_cancel = None
    chat_id_cancel = user_id # Mặc định gửi về cho admin

    # Xác định tin nhắn cần sửa và chat_id
    if update.callback_query:
        query = update.callback_query
        try:
            await query.answer()
        except Exception:
            pass
        if query.message:
            message_to_edit_cancel = query.message
            chat_id_cancel = query.message.chat_id
    elif update.message:
        chat_id_cancel = update.message.chat_id

    # Tạo bàn phím quay lại
    reply_markup_cancel = None
    if target_telegram_id:
        # Nếu biết user nào đang sửa, quay lại info user đó
        kb_back_info_cancel = [[InlineKeyboardButton("🔙 Quay lại Info User", callback_data="user_info:{}".format(target_telegram_id))]]
        reply_markup_cancel = InlineKeyboardMarkup(kb_back_info_cancel)
    else:
        # Nếu không rõ, quay về menu admin chính
        kb_back_admin = [[InlineKeyboardButton("🔙 Quay lại Menu Admin", callback_data="flashcard_admin")]]
        reply_markup_cancel = InlineKeyboardMarkup(kb_back_admin)

    # Gửi tin nhắn hủy
    try:
        await send_or_edit_message(
            context=context,
            chat_id=chat_id_cancel,
            text=cancel_message_text,
            message_to_edit=message_to_edit_cancel,
            reply_markup=reply_markup_cancel
        )
        logger.debug("{} Đã gửi/sửa xác nhận hủy.".format(log_prefix))
    except Exception as e_send_final:
         logger.error("{} Lỗi gửi tin nhắn hủy cuối cùng: {}".format(log_prefix, e_send_final))

    # Kết thúc conversation
    return ConversationHandler.END

# Tạo ConversationHandler cho luồng sửa limit
admin_set_limit_conv = ConversationHandler(
    entry_points=[
        # Bắt đầu khi nhấn nút "Sửa Giới hạn thẻ mới"
        CallbackQueryHandler(handle_callback_start_edit_limit, pattern=r"^edit_limit:")
    ],
    states={
        # Chờ admin nhập số giới hạn mới
        SET_DAILY_LIMIT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_state_set_limit_input)
        ],
    },
    fallbacks=[
        # Xử lý khi admin gõ /cancel hoặc nhấn nút Hủy (nếu có)
        CommandHandler("cancel", _handle_cancel_edit_limit)
        # Có thể thêm CallbackQueryHandler cho nút Hủy nếu cần
    ],
    name="admin_edit_limit_conversation", # Tên để debug
    persistent=False, # Không lưu state qua các lần khởi động lại
    per_message=True # Xử lý độc lập cho mỗi tin nhắn
)

@require_permission(CAN_SET_LIMITS)
async def handle_command_set_limit(update, context):
    """
    Handler cho lệnh /set_daily_limit <user_id> <limit>.
    Cho phép admin đặt giới hạn nhanh qua lệnh.
    """
    # Kiểm tra đầu vào
    if not update or not update.effective_user or not update.message:
        return

    admin_user_id = update.effective_user.id
    chat_id = update.message.chat_id
    log_prefix = "[USER_MGMT_SET_LIMIT_CMD|Admin:{}]".format(admin_user_id)
    logger.info("{} Lệnh /set_daily_limit.".format(log_prefix))
    response_message = "Lỗi không xác định."
    target_telegram_id_cmd = None

    try:
        # Kiểm tra cú pháp lệnh
        if not context.args or len(context.args) != 2:
            await send_or_edit_message(context=context, chat_id=chat_id, text="⚠️ Sai cú pháp.\nVí dụ: `/set_daily_limit 123456789 50`", parse_mode='Markdown')
            return

        # Parse tham số
        target_telegram_id_cmd_str = context.args[0]
        new_limit_str = context.args[1]
        target_telegram_id_cmd = int(target_telegram_id_cmd_str)
        new_limit = int(new_limit_str)
        logger.info("{} Tham số: target={}, limit={}".format(log_prefix, target_telegram_id_cmd, new_limit))

        # Gọi hàm cập nhật DB
        limit_update_success = update_user_daily_limit(target_telegram_id_cmd, new_limit)
        if limit_update_success:
            response_message = "✅ Đã cập nhật giới hạn thẻ mới/ngày cho user `{}` thành **{}**.".format(target_telegram_id_cmd, new_limit)
            logger.info("{} Cập nhật limit OK.".format(log_prefix))
        else:
            response_message = "⚠️ Không tìm thấy user `{}` hoặc giới hạn không thay đổi.".format(target_telegram_id_cmd)
            logger.warning("{} update_user_daily_limit trả về False.".format(log_prefix))

    # Xử lý lỗi
    except ValueError:
        logger.warning("{} Tham số không phải số nguyên: {}.".format(log_prefix, context.args))
        response_message = "❌ Lỗi: User ID và giới hạn phải là số nguyên."
    except ValidationError as e:
        logger.warning("{} Lỗi Validation: {}".format(log_prefix, e))
        response_message = "❌ {}".format(e)
    except (DatabaseError, UserNotFoundError) as e:
        logger.error("{} Lỗi DB/User: {}".format(log_prefix, e))
        response_message = "❌ Lỗi khi cập nhật limit cho user `{}`.".format(target_telegram_id_cmd)
    except Exception as e:
        logger.error("{} Lỗi khác khi chạy lệnh set_limit: {}".format(log_prefix, e), exc_info=True)
        response_message = "❌ Có lỗi không mong muốn xảy ra."

    # Gửi phản hồi
    await send_or_edit_message(context=context, chat_id=chat_id, text=response_message, parse_mode='Markdown')

def register_handlers(app: Application):
    """Đăng ký các handler liên quan đến quản lý người dùng (admin)."""
    # Đăng ký ConversationHandler cho việc sửa limit
    app.add_handler(admin_set_limit_conv)
    # Đăng ký CommandHandler cho lệnh /set_daily_limit
    app.add_handler(CommandHandler("set_daily_limit", handle_command_set_limit))
    # Đăng ký các CallbackQueryHandler khác
    app.add_handler(CallbackQueryHandler(handle_callback_manage_users, pattern=r"^manage_users$"))
    app.add_handler(CallbackQueryHandler(handle_callback_show_user_info, pattern=r"^user_info:"))
    app.add_handler(CallbackQueryHandler(update_user_role_callback, pattern=r"^set_role:"))
    app.add_handler(CallbackQueryHandler(update_user_role_confirm_callback, pattern=r"^set_role_confirm:"))
    logger.info("Đã đăng ký các handler cho module User Management (Admin).")