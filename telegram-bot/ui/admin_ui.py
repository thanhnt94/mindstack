# Path: flashcard_v2/ui/admin_ui.py
"""
Module chứa các hàm xây dựng giao diện người dùng cho các chức năng quản trị (admin),
như menu admin, danh sách người dùng, thông tin chi tiết người dùng, v.v.
Đã thêm hiển thị icon vai trò trong danh sách người dùng.
"""
import logging
import html
import asyncio

# Sử dụng import tuyệt đối
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from config import ROLE_PERMISSIONS # Dùng để lấy danh sách roles
from config import ROLE_DISPLAY_CONFIG # <<< Import cấu hình hiển thị vai trò
from utils.helpers import get_chat_display_name

# Khởi tạo logger
logger = logging.getLogger(__name__)

def build_admin_main_menu():
    """
    Xây dựng bàn phím inline cho menu chức năng admin chính.
    Bao gồm Quản lý Thành viên và Quản lý Cache.
    """
    log_prefix = "[UI_BUILD_ADMIN_MENU]"
    logger.debug("{} Đang tạo menu admin chính.".format(log_prefix))
    keyboard = [
        [InlineKeyboardButton("👥 Quản lý Thành viên", callback_data="manage_users")],
        [InlineKeyboardButton("🧹 Quản lý Cache Audio", callback_data="admin_cache:show_menu")],
        [InlineKeyboardButton("🔙 Quay lại Menu Chính", callback_data="handle_callback_back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug("{} Đã tạo xong keyboard menu admin.".format(log_prefix))
    return reply_markup

def build_admin_cache_menu():
    """
    Xây dựng bàn phím inline cho menu con quản lý cache audio.
    """
    log_prefix = "[UI_BUILD_ADMIN_CACHE_MENU]"
    logger.debug("{} Đang tạo menu con quản lý cache.".format(log_prefix))
    keyboard = [
        [
            InlineKeyboardButton("🗑️ Dọn Cache", callback_data="admin_cache:ask_clear"),
            InlineKeyboardButton("▶️ B.đầu Tạo Cache", callback_data="admin_cache:start_job"),
        ],
        [
            InlineKeyboardButton("⏹️ Dừng Tạo Cache", callback_data="admin_cache:stop_job"),
            InlineKeyboardButton("🔙 Quay lại Menu Admin", callback_data="flashcard_admin"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug("{} Đã tạo xong keyboard menu con quản lý cache.".format(log_prefix))
    return reply_markup

async def build_user_management_keyboard(users_list, bot_instance):
    """
    Xây dựng bàn phím inline hiển thị danh sách người dùng để quản lý.
    Đã thêm icon vai trò vào trước tên người dùng.

    Args:
        users_list (list): Danh sách các dictionary chứa thông tin user (từ get_all_users).
        bot_instance (telegram.Bot): Instance của bot để lấy tên hiển thị.

    Returns:
        InlineKeyboardMarkup: Bàn phím inline hoặc None nếu danh sách rỗng.
    """
    log_prefix = "[UI_BUILD_USER_LIST]"
    logger.debug("{} Đang tạo keyboard danh sách user.".format(log_prefix))
    if not users_list:
        logger.warning("{} Danh sách user rỗng.".format(log_prefix))
        return None

    keyboard = []
    tasks = []
    user_telegram_ids_in_list = []
    # Lấy danh sách telegram_id và tạo task lấy tên
    for user in users_list:
        telegram_id = user.get('telegram_id')
        if telegram_id:
            user_telegram_ids_in_list.append(telegram_id)
            # Tạo coroutine lấy tên cho mỗi ID
            tasks.append(get_chat_display_name(bot_instance, telegram_id))
        else:
            logger.warning("{} Bỏ qua user không có telegram_id: {}".format(log_prefix, user))

    # Lấy tên hiển thị bất đồng bộ
    logger.debug("{} Chuẩn bị lấy username cho {} user...".format(log_prefix, len(tasks)))
    usernames_results = await asyncio.gather(*tasks, return_exceptions=True)
    logger.debug("{} Đã lấy xong usernames.".format(log_prefix))

    # Tạo map telegram_id -> username
    username_map = {}
    for i, tg_id in enumerate(user_telegram_ids_in_list):
        if i < len(usernames_results):
             # Kiểm tra xem kết quả có phải là Exception không
             if not isinstance(usernames_results[i], Exception):
                 username_map[tg_id] = usernames_results[i]
             else:
                 # Log lỗi và dùng ID làm tên thay thế
                 logger.warning("{} Lỗi lấy tên cho TG ID {}: {}".format(log_prefix, tg_id, usernames_results[i]))
                 username_map[tg_id] = str(tg_id) # Dùng ID nếu lỗi
        else:
             # Trường hợp hiếm gặp: số kết quả ít hơn số ID
             username_map[tg_id] = str(tg_id)

    # Tạo các nút bấm với icon vai trò
    default_icon = "❔" # Icon mặc định nếu không tìm thấy vai trò trong config
    for user in users_list:
        telegram_id = user.get('telegram_id')
        if not telegram_id:
            continue # Bỏ qua nếu vẫn còn user thiếu ID

        username = username_map.get(telegram_id, str(telegram_id)) # Lấy tên từ map
        user_role = user.get('user_role', 'user') # Lấy vai trò của user

        # === LẤY ICON VAI TRÒ TỪ CONFIG ===
        role_icon, _ = ROLE_DISPLAY_CONFIG.get(user_role, (default_icon, ""))
        # ====================================

        callback_data = "user_info:{}".format(telegram_id)
        # Thêm icon vào đầu button_text
        button_text = "{} {} (ID: {})".format(role_icon, username, telegram_id)
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Thêm nút quay lại
    keyboard.append([InlineKeyboardButton("🔙 Quay lại Menu Admin", callback_data="flashcard_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug("{} Đã tạo xong keyboard danh sách user với icon vai trò.".format(log_prefix))
    return reply_markup

def build_user_info_display(target_user_info, username):
    """
    Xây dựng nội dung tin nhắn và bàn phím hiển thị thông tin chi tiết của người dùng.

    Args:
        target_user_info (dict): Dictionary chứa thông tin user từ DB.
        username (str): Tên hiển thị của người dùng.

    Returns:
        tuple: (text, reply_markup) hoặc (None, None) nếu dữ liệu không hợp lệ.
    """
    log_prefix = "[UI_BUILD_USER_INFO]"
    if not target_user_info or not isinstance(target_user_info, dict):
        logger.error("{} Dữ liệu target_user_info không hợp lệ.".format(log_prefix))
        return None, None

    target_telegram_id = target_user_info.get('telegram_id', 'N/A')
    log_prefix = "[UI_BUILD_USER_INFO|UserTG:{}]".format(target_telegram_id)
    logger.debug("{} Tạo hiển thị thông tin chi tiết.".format(log_prefix))

    # Lấy thông tin từ dict
    user_role = target_user_info.get('user_role', 'user')
    daily_limit = target_user_info.get('daily_new_limit', 'N/A')
    score = target_user_info.get('score', 0)
    front_audio_status = "Bật" if target_user_info.get('front_audio', 1) == 1 else "Tắt"
    back_audio_status = "Bật" if target_user_info.get('back_audio', 1) == 1 else "Tắt"
    notify_status = "Bật" if target_user_info.get('is_notification_enabled', 0) == 1 else "Tắt"
    notify_interval = target_user_info.get('notification_interval_minutes', 'N/A')

    # Lấy icon vai trò từ config
    role_icon, _ = ROLE_DISPLAY_CONFIG.get(user_role, ("👤","")) # Lấy icon, bỏ qua tên

    # Tạo nội dung tin nhắn
    message = (
        "{} **Thông tin Thành viên**\n\n" # Thêm icon vào tiêu đề
        "- ID Telegram: `{}`\n"
        "- Tên hiển thị: {}\n"
        "- Vai trò: `{}`\n"
        "- Giới hạn thẻ mới/ngày: `{}`\n"
        "- Điểm số: `{}`\n"
        "- Audio Trước: `{}`\n"
        "- Audio Sau: `{}`\n"
        "- Thông báo: `{}` (Mỗi `{}` phút)\n"
    ).format(role_icon, target_telegram_id, html.escape(username), user_role, daily_limit, score, front_audio_status, back_audio_status, notify_status, notify_interval)

    # Tạo bàn phím
    keyboard = [
        [InlineKeyboardButton("👑 Thay đổi Vai trò", callback_data="set_role:{}".format(target_telegram_id))],
        [InlineKeyboardButton("⚙️ Sửa Giới hạn thẻ mới", callback_data="edit_limit:{}".format(target_telegram_id))],
        [InlineKeyboardButton("🔙 Quay lại Danh sách", callback_data="manage_users")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug("{} Đã tạo xong text và keyboard thông tin user.".format(log_prefix))
    return message, reply_markup

def build_set_role_keyboard(target_telegram_id):
    """
    Xây dựng bàn phím inline để chọn vai trò mới cho người dùng.
    Tự động lấy danh sách vai trò từ config.ROLE_PERMISSIONS.

    Args:
        target_telegram_id (int): ID Telegram của người dùng cần đặt vai trò.

    Returns:
        InlineKeyboardMarkup: Bàn phím inline hoặc None nếu lỗi.
    """
    log_prefix = "[UI_BUILD_SET_ROLE|TargetTG:{}]".format(target_telegram_id)
    logger.debug("{} Đang tạo keyboard chọn role.".format(log_prefix))

    # Lấy danh sách các role hợp lệ từ config
    # ROLE_PERMISSIONS là dict {role_name: set_of_permissions}
    # Lấy keys() sẽ ra list các role_name ('user', 'lite', 'vip', 'admin', 'banned')
    valid_roles = list(ROLE_PERMISSIONS.keys()) # Chuyển sang list để sắp xếp nếu cần

    if not valid_roles:
        logger.error("{} Không tìm thấy định nghĩa vai trò trong ROLE_PERMISSIONS.".format(log_prefix))
        return None

    # Sắp xếp vai trò theo thứ tự mong muốn (ví dụ: admin -> vip -> lite -> user -> banned)
    role_order = ['admin', 'vip', 'lite', 'user', 'banned']
    # Chỉ giữ lại các vai trò có trong config và sắp xếp
    sorted_roles = [role for role in role_order if role in valid_roles]
    # Thêm các vai trò khác (nếu có) chưa được liệt kê vào cuối
    for role in valid_roles:
        if role not in sorted_roles:
            sorted_roles.append(role)

    keyboard = []
    # Tạo nút cho mỗi vai trò đã sắp xếp
    for role_name in sorted_roles:
        # Lấy icon và tên hiển thị từ config
        role_icon, display_name = ROLE_DISPLAY_CONFIG.get(role_name, (None, role_name.capitalize()))
        button_text = "{} {}".format(role_icon, display_name) if role_icon else display_name
        callback_data = "set_role_confirm:{}:{}".format(target_telegram_id, role_name)
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Thêm nút quay lại
    keyboard.append([InlineKeyboardButton("🔙 Quay lại Thông tin User", callback_data="user_info:{}".format(target_telegram_id))])
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug("{} Đã tạo xong keyboard chọn role.".format(log_prefix))
    return reply_markup