"""
Module chứa các hàm xây dựng giao diện người dùng liên quan đến phần cài đặt.
(Đã thêm hàm xây dựng menu cài đặt tổng hợp và thêm tùy chọn show_review_summary).
"""
import logging
import html 
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database.query_user import get_user_by_telegram_id
from config import CAN_TOGGLE_SUMMARY, ROLE_PERMISSIONS
logger = logging.getLogger(__name__)
async def build_audio_image_settings_menu(user_id):
    """
    Xây dựng nội dung tin nhắn và bàn phím cho giao diện cài đặt âm thanh và ảnh CHI TIẾT.
    (Hàm này giờ sẽ được gọi từ menu cài đặt tổng hợp).
    Args:
        user_id (int): ID Telegram của người dùng.
    Returns:
        tuple: (text, reply_markup) nếu thành công, (None, None) nếu lỗi.
    """
    log_prefix = f"[UI_BUILD_SETTINGS_DETAIL|User:{user_id}]" 
    logger.debug(f"{log_prefix} Bắt đầu xây dựng giao diện cài đặt chi tiết (âm thanh/ảnh).")
    user_info = get_user_by_telegram_id(user_id)
    if not user_info:
        logger.error(f"{log_prefix} Không thể lấy thông tin user.")
        return None, None
    is_front_audio_on = user_info.get('front_audio', 1) == 1
    front_audio_status = "🟢 Bật" if is_front_audio_on else "🔴 Tắt"
    front_audio_toggle_text = "Tắt âm thanh mặt trước" if is_front_audio_on else "Bật âm thanh mặt trước"
    front_audio_callback = "toggle_audio:front"
    is_back_audio_on = user_info.get('back_audio', 1) == 1
    back_audio_status = "🟢 Bật" if is_back_audio_on else "🔴 Tắt"
    back_audio_toggle_text = "Tắt âm thanh mặt sau" if is_back_audio_on else "Bật âm thanh mặt sau"
    back_audio_callback = "toggle_audio:back"
    is_front_image_on = user_info.get('front_image_enabled', 1) == 1
    front_image_status = "🟢 Bật" if is_front_image_on else "🔴 Tắt"
    front_image_toggle_text = "Tắt ảnh mặt trước" if is_front_image_on else "Bật ảnh mặt trước"
    front_image_callback = "toggle_image:front"
    is_back_image_on = user_info.get('back_image_enabled', 1) == 1
    back_image_status = "🟢 Bật" if is_back_image_on else "🔴 Tắt"
    back_image_toggle_text = "Tắt ảnh mặt sau" if is_back_image_on else "Bật ảnh mặt sau"
    back_image_callback = "toggle_image:back"
    logger.debug(f"{log_prefix} Trạng thái: AudioF={is_front_audio_on}, AudioB={is_back_audio_on}, ImageF={is_front_image_on}, ImageB={is_back_image_on}")
    text = (
        f"🎧 **Cài đặt Âm thanh & Hình ảnh** 🖼️\n\n" 
        f"🔊 Âm thanh mặt trước: **{front_audio_status}**\n"
        f"🔉 Âm thanh mặt sau: **{back_audio_status}**\n\n"
        f"🖼️ Ảnh mặt trước: **{front_image_status}**\n"
        f"🏞️ Ảnh mặt sau: **{back_image_status}**\n\n"
        f"Chọn để thay đổi:"
    )
    keyboard = [
        [
            InlineKeyboardButton(f"{'❌' if is_front_audio_on else '✅'} {front_audio_toggle_text}", callback_data=front_audio_callback),
            InlineKeyboardButton(f"{'❌' if is_back_audio_on else '✅'} {back_audio_toggle_text}", callback_data=back_audio_callback)
        ],
        [
            InlineKeyboardButton(f"{'❌' if is_front_image_on else '✅'} {front_image_toggle_text}", callback_data=front_image_callback),
            InlineKeyboardButton(f"{'❌' if is_back_image_on else '✅'} {back_image_toggle_text}", callback_data=back_image_callback)
        ],
        [InlineKeyboardButton("🔙 Quay lại Cài đặt chung", callback_data="settings:back_to_unified")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug(f"{log_prefix} Đã tạo xong text và keyboard cho giao diện cài đặt chi tiết.")
    return text, reply_markup
async def build_main_settings_menu(user_id):
    """
    Xây dựng nội dung tin nhắn và bàn phím cho menu cài đặt tổng hợp.
    (Đã thêm hiển thị và nút bật/tắt "Hiển thị thông số" dựa trên quyền).
    Args:
        user_id (int): ID Telegram của người dùng.
    Returns:
        tuple: (text, reply_markup) nếu thành công, (str, None) nếu lỗi.
    """
    log_prefix = f"[UI_BUILD_UNIFIED_SETTINGS|User:{user_id}]"
    logger.debug(f"{log_prefix} Bắt đầu xây dựng menu cài đặt tổng hợp.")
    try:
        user_info = get_user_by_telegram_id(user_id) 
    except Exception as e: 
         logger.error(f"{log_prefix} Lỗi lấy thông tin user: {e}", exc_info=True)
         return "Lỗi: Không thể tải cài đặt của bạn.", None
    is_front_audio_on = user_info.get('front_audio', 1) == 1
    front_audio_status = "Bật" if is_front_audio_on else "Tắt"
    is_back_audio_on = user_info.get('back_audio', 1) == 1
    back_audio_status = "Bật" if is_back_audio_on else "Tắt"
    is_front_image_on = user_info.get('front_image_enabled', 1) == 1
    front_image_status = "Bật" if is_front_image_on else "Tắt"
    is_back_image_on = user_info.get('back_image_enabled', 1) == 1
    back_image_status = "Bật" if is_back_image_on else "Tắt"
    is_notification_enabled = user_info.get('is_notification_enabled', 0) == 1
    notification_status = "Bật" if is_notification_enabled else "Tắt"
    notification_interval = user_info.get('notification_interval_minutes', 60)
    is_summary_shown = user_info.get('show_review_summary', 1) == 1
    summary_status = "Bật" if is_summary_shown else "Tắt"
    text = (
        f"⚙️ **Cài đặt Người dùng**\n\n"
        f"--- Hiển thị ---\n"
        f"  🔊 Âm thanh: Trước=`{front_audio_status}`, Sau=`{back_audio_status}`\n"
        f"  🖼️ Hình ảnh: Trước=`{front_image_status}`, Sau=`{back_image_status}`\n"
        f"  📊 Hiển thị thông số sau ôn tập: **{summary_status}**\n\n" 
        f"--- Thông báo ---\n"
        f"  🔔 Trạng thái: **{notification_status}**\n"
        f"  ⏰ Khoảng cách: `{notification_interval}` phút\n\n"
        f"Chọn mục bạn muốn thay đổi:"
    )
    keyboard = [
        [InlineKeyboardButton("🎧 Âm thanh & Ảnh", callback_data="settings:show_audio_image")], 
        [InlineKeyboardButton("🔔 Thông báo", callback_data="settings:show_notifications")], 
    ]
    user_role = user_info.get('user_role', 'user')
    user_permissions = ROLE_PERMISSIONS.get(user_role, set())
    if CAN_TOGGLE_SUMMARY in user_permissions:
        toggle_summary_text = "🔴 Tắt Thông số" if is_summary_shown else "🟢 Bật Thông số"
        toggle_summary_callback = "settings:toggle_summary" 
        keyboard.append([InlineKeyboardButton(toggle_summary_text, callback_data=toggle_summary_callback)])
        logger.debug(f"{log_prefix} User role '{user_role}' có quyền CAN_TOGGLE_SUMMARY. Thêm nút.")
    else:
        logger.debug(f"{log_prefix} User role '{user_role}' không có quyền CAN_TOGGLE_SUMMARY. Bỏ qua nút.")
    keyboard.append([InlineKeyboardButton("🔙 Menu chính", callback_data="handle_callback_back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug(f"{log_prefix} Đã tạo xong text và keyboard cho menu cài đặt tổng hợp.")
    return text, reply_markup