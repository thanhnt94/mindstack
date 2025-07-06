# File: flashcard-telegram-bot/ui/notifications_ui.py
"""
Module chứa các hàm xây dựng giao diện người dùng cho cài đặt thông báo.
(Sửa lần 3: Sửa lỗi import NOTIFY_TARGET_SET_PAGE)
(Sửa lần 4: Đổi tên "Lời chào buổi sáng" thành "Morning Brief",
             đặt nút bật/tắt Morning Brief và nút Quay lại chung hàng,
             đặt enable_morning_brief mặc định là False khi hiển thị nếu chưa có trong user_info)
"""
import logging
import math 
import html 

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    NOTIFY_TOGGLE_PERIODIC, 
    NOTIFY_INTERVAL_MENU,
    NOTIFY_INTERVAL_SET,
    NOTIFY_CALLBACK_PREFIX, 
    NOTIFY_CHOOSE_TARGET_SET_MENU, 
    NOTIFY_SELECT_TARGET_SET_ACTION, 
    NOTIFY_CLEAR_TARGET_SET_ACTION, 
    NOTIFY_TOGGLE_MORNING_BRIEF_ACTION, 
    SETS_PER_PAGE,
    NOTIFY_TARGET_SET_PAGE 
)
from database.query_user import get_user_by_telegram_id 
from database.query_set import get_sets 
from ui.core_ui import build_pagination_keyboard 

logger = logging.getLogger(__name__)

def build_notification_settings_menu(user_info, success_message=None):
    """
    Xây dựng nội dung tin nhắn và bàn phím cho giao diện cài đặt thông báo.
    Sửa lần 4: Đổi tên "Lời chào buổi sáng" thành "Morning Brief" và điều chỉnh layout nút.
    """
    log_prefix = "[UI_BUILD_NOTIFY_SETTINGS]"
    if not user_info or not isinstance(user_info, dict):
        logger.error(f"{log_prefix} Dữ liệu user_info không hợp lệ.")
        return None, None
    
    user_id_tg = user_info.get('telegram_id', 'N/A') 
    log_prefix = f"[UI_BUILD_NOTIFY_SETTINGS|UserTG:{user_id_tg}]"
    logger.debug(f"{log_prefix} Đang tạo giao diện cài đặt thông báo (v4).")

    is_periodic_enabled = user_info.get('is_notification_enabled', 0) == 1
    periodic_status_text = "🟢 Bật" if is_periodic_enabled else "🔴 Tắt"
    periodic_toggle_button_text = "🔴 Tắt TB ôn tập bộ" if is_periodic_enabled else "🟢 Bật TB ôn tập bộ"
    periodic_interval = user_info.get('notification_interval_minutes', 60)
    
    target_set_id = user_info.get('notification_target_set_id')
    target_set_display = "Chưa chọn bộ"
    if target_set_id:
        try:
            set_info_list, _ = get_sets(set_id=target_set_id, columns=['title'])
            if set_info_list and set_info_list[0]:
                target_set_display = html.escape(set_info_list[0].get('title', f"ID: {target_set_id}"))
            else:
                target_set_display = f"ID: {target_set_id} (không tìm thấy)"
        except Exception as e_get_set:
            logger.error(f"{log_prefix} Lỗi khi lấy tên bộ thẻ {target_set_id}: {e_get_set}")
            target_set_display = f"ID: {target_set_id} (lỗi tải)"

    # Sửa lần 4: enable_morning_brief mặc định là False (0) nếu không có trong user_info
    is_morning_brief_enabled = user_info.get('enable_morning_brief', 0) == 1 
    morning_brief_status_text = "☀️ Bật" if is_morning_brief_enabled else "🌑 Tắt"
    morning_brief_toggle_button_text = "🌑 Tắt Morning Brief" if is_morning_brief_enabled else "☀️ Bật Morning Brief"

    message_lines = []
    if success_message:
        message_lines.append(f"{success_message}\n")
    
    message_lines.append(f"🔔 **Cài đặt Thông báo & Nhắc nhở**\n")
    
    message_lines.append(f"--- Thông báo Ôn tập từ Bộ thẻ ---")
    message_lines.append(f"  Trạng thái: **{periodic_status_text}**")
    message_lines.append(f"  Bộ thẻ mục tiêu: **{target_set_display}**")
    message_lines.append(f"  Khoảng cách TB: `{periodic_interval}` phút\n")

    # Sửa lần 4: Đổi tên thành "Morning Brief"
    message_lines.append(f"--- Morning Brief ---") 
    message_lines.append(f"  Trạng thái: **{morning_brief_status_text}**\n")
    
    message_lines.append("Chọn hành động:")
    message_text = "\n".join(message_lines)

    keyboard = [
        [
            InlineKeyboardButton(periodic_toggle_button_text, callback_data=NOTIFY_TOGGLE_PERIODIC),
            InlineKeyboardButton("⏰ Khoảng cách TB bộ", callback_data=NOTIFY_INTERVAL_MENU)
        ],
        [
            InlineKeyboardButton("📚 Chọn/Đổi bộ", callback_data=NOTIFY_CHOOSE_TARGET_SET_MENU),
        ],
        # Sửa lần 4: Gom nút Morning Brief và nút Quay lại vào hàng 3
        [
            InlineKeyboardButton(morning_brief_toggle_button_text, callback_data=NOTIFY_TOGGLE_MORNING_BRIEF_ACTION),
            InlineKeyboardButton("🔙 Quay lại ", callback_data="settings:back_to_unified")
        ]
    ]
    if target_set_id:
        keyboard[1].append(InlineKeyboardButton("🗑️ Xóa chọn bộ", callback_data=NOTIFY_CLEAR_TARGET_SET_ACTION))

    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug(f"{log_prefix} Đã tạo xong text và keyboard (v4).")
    return message_text, reply_markup

# Các hàm build_notification_set_selection_keyboard và build_interval_selection_keyboard giữ nguyên
def build_notification_set_selection_keyboard(user_id_db, all_user_sets_info, current_page=1):
    log_prefix = f"[UI_BUILD_NOTIFY_SET_SELECT|UserDBID:{user_id_db}|Page:{current_page}]"
    logger.debug(f"{log_prefix} Đang tạo keyboard chọn bộ cho thông báo.")

    if not all_user_sets_info:
        text = "Bạn chưa học bộ thẻ nào để có thể chọn nhận thông báo."
        keyboard_empty = [[InlineKeyboardButton("🔙 Quay lại Cài đặt Thông báo", callback_data=f"{NOTIFY_CALLBACK_PREFIX}:back_to_notify_menu")]] 
        return text, InlineKeyboardMarkup(keyboard_empty)

    items_per_page = SETS_PER_PAGE 
    total_items = len(all_user_sets_info)
    total_pages = math.ceil(total_items / items_per_page)
    current_page = max(1, min(current_page, total_pages)) 
    
    start_index = (current_page - 1) * items_per_page
    end_index = start_index + items_per_page
    sets_on_page = all_user_sets_info[start_index:end_index]

    text = f"📚 Chọn một bộ thẻ để nhận thông báo ôn tập (Trang {current_page}/{total_pages}):"
    keyboard = []

    if not sets_on_page:
        text = f"Không có bộ thẻ nào trên trang {current_page}."
    else:
        for set_info in sets_on_page:
            set_id = set_info.get('set_id')
            title = set_info.get('title', f"ID: {set_id}")
            if set_id is None:
                continue
            button_text = f"📌 {html.escape(title)}"
            callback_data = f"{NOTIFY_SELECT_TARGET_SET_ACTION}{set_id}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    pagination_row = build_pagination_keyboard(current_page, total_pages, NOTIFY_TARGET_SET_PAGE)
    if pagination_row:
        keyboard.append(pagination_row)
    
    keyboard.append([InlineKeyboardButton("🔙 Quay lại Cài đặt Thông báo", callback_data=f"{NOTIFY_CALLBACK_PREFIX}:back_to_notify_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    return text, reply_markup


def build_interval_selection_keyboard(): 
    log_prefix = "[UI_BUILD_INTERVAL_MENU]"
    interval_options = [5, 10, 15, 30, 45, 60, 120, 180, 240] 
    keyboard = []
    row = []
    for interval in interval_options:
        button_text = f"🕒 {interval} phút"
        callback_data = f"{NOTIFY_INTERVAL_SET}{interval}"
        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Quay lại Cài đặt Thông báo", callback_data=f"{NOTIFY_CALLBACK_PREFIX}:back_to_notify_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup
