# File: flashcard-telegram-bot/ui/core_ui.py
"""
Module chứa các hàm xây dựng giao diện người dùng cốt lõi, ví dụ menu chính,
menu chọn chế độ học, menu quản lý bộ từ, phân trang.
(Sửa lần 1: Cập nhật callback data cho nút "Xoá bộ từ" trong build_set_management_keyboard)
"""
import logging
import html

from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import Bot 
from database.query_user import get_user_by_telegram_id
from database.query_set import get_sets
from utils.helpers import get_chat_display_name
from config import (
    DEFAULT_LEARNING_MODE, LEARNING_MODE_DISPLAY_NAMES, MODE_REVIEW_ALL_DUE,
    MODE_CRAM_ALL, MODE_REVIEW_HARDEST, MODE_SEQ_INTERSPERSED, MODE_SEQ_RANDOM_NEW,
    MODE_NEW_SEQUENTIAL, MODE_NEW_RANDOM, MODE_DUE_ONLY_RANDOM, CAN_ACCESS_ADMIN_MENU,
    AUDIO_REVIEW_CALLBACK_PREFIX, ROLE_PERMISSIONS, AUDIO_N_OPTIONS, MODE_CRAM_SET,
    ROLE_DISPLAY_CONFIG,
    SET_MGMT_DELETE_MENU_PFX # <<< SỬA LẦN 1: THÊM IMPORT
)

logger = logging.getLogger(__name__)

async def build_main_menu(telegram_id, bot_instance):
    # Giữ nguyên logic
    log_prefix = f"[UI_BUILD_MAIN|UserTG:{telegram_id}]"
    logger.debug(f"{log_prefix} Bắt đầu xây dựng giao diện chính.")
    try:
        user = get_user_by_telegram_id(telegram_id)
        user_role = user.get('user_role', 'user')
        if user_role == 'banned':
            logger.warning(f"{log_prefix} Người dùng ID {telegram_id} có vai trò 'banned'. Chặn truy cập.")
            ban_icon, ban_message_base = ROLE_DISPLAY_CONFIG.get('banned', ("🚫", "Bị khóa"))
            ban_message = f"{ban_icon} Tài khoản của bạn đã {ban_message_base.lower()}\. Vui lòng liên hệ quản trị viên\." 
            return ban_message, None 

        current_set_id = user.get("current_set_id")
        current_mode = user.get("current_mode", DEFAULT_LEARNING_MODE)
        score = user.get('score', 0)
        username = await get_chat_display_name(bot_instance, telegram_id)
        logger.debug(f"{log_prefix} Info: username='{username}', current_set_id={current_set_id}, current_mode='{current_mode}', role='{user_role}', score={score}")
        default_display = ("👤", user_role.capitalize())
        role_icon, role_name = ROLE_DISPLAY_CONFIG.get(user_role, default_display)
        greeting = f"👋 Xin chào {role_icon} {username}!"
        mode_display_name = LEARNING_MODE_DISPLAY_NAMES.get(current_mode, current_mode)
        text_lines = [greeting]
        modes_hiding_set = {MODE_REVIEW_ALL_DUE, MODE_CRAM_ALL, MODE_REVIEW_HARDEST}
        if current_mode not in modes_hiding_set:
            set_title_display = "**Chưa chọn bộ nào**"
            if current_set_id:
                logger.debug(f"{log_prefix} Đang học bộ: {current_set_id}. Lấy thông tin bộ...")
                try:
                    set_info_tuple = get_sets(set_id=current_set_id)
                    set_data = set_info_tuple[0][0] if set_info_tuple and set_info_tuple[0] else None
                    if set_data:
                         set_title = set_data.get("title")
                         if set_title: set_title_display = f"**{html.escape(set_title)}**"
                         else: logger.warning(f"{log_prefix} Set ID {current_set_id} không có title."); set_title_display = f"**ID không tên ({current_set_id})**"
                    else: logger.warning(f"{log_prefix} Không tìm thấy thông tin cho set_id {current_set_id}."); set_title_display = f"**ID không hợp lệ ({current_set_id})**"
                except Exception as e_set: logger.error(f"{log_prefix} Lỗi lấy thông tin bộ {current_set_id}: {e_set}"); set_title_display = f"**Lỗi tải tên bộ ({current_set_id})**"
            text_lines.append(f"\n📚 Bộ hiện tại: {set_title_display}")
        else: logger.debug(f"{log_prefix} Chế độ '{current_mode}', ẩn thông tin bộ hiện tại."); text_lines.append("")
        text_lines.append(f"⚡ Chế độ: **{mode_display_name}**")
        text_lines.append(f"💯 Điểm số: **{score}**")
        text_lines.append("---"); text_lines.append("Chọn một hành động:")
        text = "\n".join(text_lines)
        keyboard = [
            [InlineKeyboardButton("🔄 Thay đổi bộ", callback_data="_display_set_selection"), InlineKeyboardButton("⚡ Thay đổi chế độ", callback_data="show_mode_selection")],
            [InlineKeyboardButton("🗂️ Quản lý bộ", callback_data="show_set_management"), InlineKeyboardButton("📈 Thống kê", callback_data="stats:main")],
            [InlineKeyboardButton("🎧 Ôn tập Audio", callback_data=f"{AUDIO_REVIEW_CALLBACK_PREFIX}:choose_set"), InlineKeyboardButton("📊 Xuất dữ liệu", callback_data="do_export")],
            [InlineKeyboardButton("⚙️ Cài đặt", callback_data="show_unified_settings"), InlineKeyboardButton("❓ Trợ giúp", callback_data="show_help")]
        ]
        user_permissions = ROLE_PERMISSIONS.get(user_role, set())
        if CAN_ACCESS_ADMIN_MENU in user_permissions:
            logger.debug(f"{log_prefix} User là admin, thêm hàng nút admin.")
            keyboard.append( [InlineKeyboardButton("🛠️ Menu Admin", callback_data="flashcard_admin"), InlineKeyboardButton("📢 Gửi TB", callback_data="start_broadcast")] )
        else: logger.debug(f"{log_prefix} User không phải admin.")
        keyboard.append( [InlineKeyboardButton("▶️ Tiếp tục học", callback_data="continue")] )
        reply_markup = InlineKeyboardMarkup(keyboard); logger.debug(f"{log_prefix} Đã tạo xong text và keyboard layout cuối cùng."); return text, reply_markup
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi build menu chính: {e}", exc_info=True)
        return "❌ Đã xảy ra lỗi khi tải menu chính.", None

def build_mode_category_keyboard():
    # Giữ nguyên logic
    log_prefix = "[UI_BUILD_MODE_CATEGORY]"
    logger.debug(f"{log_prefix} Đang tạo keyboard chọn danh mục chế độ học.")
    keyboard = [
        [InlineKeyboardButton("🎓 Ghi nhớ sâu (SRS)", callback_data="mode_category:srs")],
        [InlineKeyboardButton("➕ Chỉ học mới", callback_data="mode_category:new")],
        [InlineKeyboardButton("🎯 Chỉ ôn tập", callback_data="mode_category:review")],
        [InlineKeyboardButton("🔙 Quay lại Menu chính", callback_data="handle_callback_back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug(f"{log_prefix} Đã tạo xong keyboard chọn danh mục chế độ.")
    return reply_markup

def _build_mode_submenu(category_modes):
    # Giữ nguyên logic
    log_prefix = "[UI_BUILD_MODE_SUBMENU]"
    keyboard = []
    for mode_code in category_modes:
        mode_name = LEARNING_MODE_DISPLAY_NAMES.get(mode_code, mode_code)
        callback_data = f"select_mode:{mode_code}"
        keyboard.append([InlineKeyboardButton(mode_name, callback_data=callback_data)])
        logger.debug(f"{log_prefix} Thêm nút: '{mode_name}' (Code: {mode_code})")
    keyboard.append([InlineKeyboardButton("🔙 Quay lại Chọn danh mục", callback_data="show_mode_selection")])
    return InlineKeyboardMarkup(keyboard)

def build_srs_mode_submenu():
    # Giữ nguyên logic
    srs_modes = [MODE_SEQ_INTERSPERSED, MODE_SEQ_RANDOM_NEW]
    return _build_mode_submenu(srs_modes)

def build_new_only_submenu():
    # Giữ nguyên logic
    new_only_modes = [MODE_NEW_SEQUENTIAL, MODE_NEW_RANDOM]
    return _build_mode_submenu(new_only_modes)

def build_review_submenu():
    # Giữ nguyên logic
    review_modes = [MODE_DUE_ONLY_RANDOM, MODE_REVIEW_ALL_DUE, MODE_REVIEW_HARDEST, MODE_CRAM_SET, MODE_CRAM_ALL]
    return _build_mode_submenu(review_modes)

def build_pagination_keyboard(current_page, total_pages, base_callback_prefix):
    # Giữ nguyên logic
    log_prefix = "[UI_BUILD_PAGINATION_KB]"
    nav_row = []
    if total_pages <= 1: logger.debug(f"{log_prefix} Chỉ có {total_pages} trang, không cần nút."); return nav_row
    if current_page > 1:
        prev_callback = f"{base_callback_prefix}:prev:{current_page}"; nav_row.append(InlineKeyboardButton("⬅️ Trước", callback_data=prev_callback)); logger.debug(f"{log_prefix} Thêm nút Trước (Callback: {prev_callback})")
    if current_page < total_pages:
        next_callback = f"{base_callback_prefix}:next:{current_page}"; nav_row.append(InlineKeyboardButton("Sau ➡️", callback_data=next_callback)); logger.debug(f"{log_prefix} Thêm nút Sau (Callback: {next_callback})")
    logger.debug(f"{log_prefix} Đã tạo hàng nút điều hướng: {len(nav_row)} nút."); return nav_row

def build_set_management_keyboard(has_pending_reports=False):
    """
    Xây dựng bàn phím inline cho menu quản lý bộ từ.
    Sửa lần 1: Sử dụng SET_MGMT_DELETE_MENU_PFX cho nút Xóa bộ từ.
    """
    log_prefix = "[UI_BUILD_SET_MGMT]"
    logger.debug(f"{log_prefix} Đang tạo keyboard quản lý bộ (has_pending_reports={has_pending_reports}).")
    keyboard = [
        [ 
            InlineKeyboardButton("📤 Upload bộ từ mới", callback_data="trigger_upload"),
            InlineKeyboardButton("🔃 Cập nhật bộ từ", callback_data="trigger_update_set")
        ],
        [ 
            # Sửa lần 1: Sử dụng hằng số callback đúng
            InlineKeyboardButton("🗑️ Xoá bộ từ", callback_data=SET_MGMT_DELETE_MENU_PFX), 
            InlineKeyboardButton("📋 Export bộ từ", callback_data="trigger_export_set")
        ]
    ]
    last_row = []
    if has_pending_reports:
        view_reports_button = InlineKeyboardButton("📊 Xem Báo cáo Lỗi", callback_data="view_reports_menu")
        last_row.append(view_reports_button)
        logger.debug(f"{log_prefix} Đã thêm nút Xem Báo cáo Lỗi.")
    back_button = InlineKeyboardButton("🔙 Menu chính", callback_data="handle_callback_back_to_main")
    last_row.append(back_button)
    keyboard.append(last_row)
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug(f"{log_prefix} Đã tạo xong keyboard quản lý bộ.")
    return reply_markup

def build_audio_n_selection_keyboard(mode, set_id):
    # Giữ nguyên logic
    log_prefix = f"[UI_BUILD_AUDIO_N_SELECT|Mode:{mode}|Set:{set_id}]"; logger.debug(f"{log_prefix} Đang tạo keyboard chọn N.")
    if not mode or not set_id: logger.error(f"{log_prefix} Thiếu mode hoặc set_id."); return None
    if not AUDIO_N_OPTIONS or not isinstance(AUDIO_N_OPTIONS, list): logger.error(f"{log_prefix} AUDIO_N_OPTIONS không hợp lệ trong config."); return None
    keyboard = []; row = []
    for n_value in AUDIO_N_OPTIONS:
        if not isinstance(n_value, int) or n_value <= 0: logger.warning(f"{log_prefix} Bỏ qua giá trị N không hợp lệ: {n_value}"); continue
        button_text = f"🎧 {n_value} thẻ"; callback_data = f"{AUDIO_REVIEW_CALLBACK_PREFIX}:trigger:{mode}:{set_id}:{n_value}"; row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        if len(row) == 3: keyboard.append(row); row = []
    if row: keyboard.append(row)
    back_callback_data = f"{AUDIO_REVIEW_CALLBACK_PREFIX}:show_options:{set_id}"; keyboard.append([InlineKeyboardButton("🔙 Quay lại", callback_data=back_callback_data)])
    if not keyboard: logger.warning(f"{log_prefix} Không tạo được nút chọn N nào."); return None
    reply_markup = InlineKeyboardMarkup(keyboard); logger.debug(f"{log_prefix} Đã tạo xong keyboard chọn N."); return reply_markup
