# Path: flashcard_v2/ui/reporting_ui.py
"""
Module chứa các hàm xây dựng giao diện người dùng cho chức năng
xem và quản lý báo cáo lỗi thẻ.
Đã sửa lỗi ImportError (self-import) và SyntaxWarning (escape sequences).
Các thay đổi trước đó (async, context, time format, reporter name, ...) vẫn được giữ.
"""
import logging
import html
import re
import asyncio
import math
from datetime import datetime, timezone, timedelta

# Import từ thư viện telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
# from telegram.ext import ContextTypes # Bỏ import
from telegram.constants import ParseMode

# Import helpers và config
from utils.helpers import get_chat_display_name
from config import DEFAULT_TIMEZONE_OFFSET, REPORTS_PER_PAGE
from ui.core_ui import build_pagination_keyboard

logger = logging.getLogger(__name__)

# --- HÀM HELPER ESCAPE MARKDOWN V2 ---
def escape_md_v2(text):
    """Hàm helper để escape các ký tự đặc biệt trong MarkdownV2."""
    if text is None:
        return ''
    escape_chars = r'_*[]()~`>#+=-|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', str(text))

# --- Hàm build_sets_with_reports_keyboard ---
def build_sets_with_reports_keyboard(reportable_sets_summary):
    """
    Xây dựng tin nhắn và bàn phím hiển thị danh sách các bộ từ có báo cáo lỗi đang chờ.
    """
    log_prefix = "[UI_BUILD_REPORT_SETS]"
    logger.debug(f"{log_prefix} Tạo keyboard chọn bộ có báo cáo lỗi.")
    text = "📊 **Các bộ thẻ có báo cáo lỗi đang chờ xử lý:**\nChọn một bộ để xem chi tiết:"
    keyboard = []
    if not reportable_sets_summary:
        text = "🎉 Không có báo cáo lỗi nào đang chờ xử lý cho các bộ thẻ của bạn."
        keyboard.append([InlineKeyboardButton("🔙 Quay lại Menu Quản lý", callback_data="show_set_management")])
        return text, InlineKeyboardMarkup(keyboard)

    for set_info in reportable_sets_summary:
        set_id = set_info.get('set_id')
        title = set_info.get('title', f"Bộ ID {set_id}")
        count = set_info.get('pending_count', 0)
        if set_id is None: continue
        button_text = f"📚 {html.escape(title)} ({count} lỗi)"
        callback_data = f"view_set_reports:{set_id}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("🔙 Quay lại Menu Quản lý", callback_data="show_set_management")])
    return text, InlineKeyboardMarkup(keyboard)

# --- Hàm build_reported_card_selection_keyboard ---
def build_reported_card_selection_keyboard(set_id, card_report_summary, current_page=1):
    """
    Xây dựng bàn phím hiển thị danh sách các ID thẻ có báo cáo lỗi đang chờ trong một bộ.
    Hỗ trợ phân trang và hiển thị theo hàng dọc.
    """
    log_prefix = f"[UI_BUILD_REPORTED_CARD_SELECT|Set:{set_id}|Page:{current_page}]"
    logger.debug(f"{log_prefix} Tạo keyboard chọn flashcard_id bị lỗi.")

    kb_back_to_sets = [[InlineKeyboardButton("🔙 Chọn bộ khác", callback_data="view_reports_menu")]]
    markup_back_to_sets = InlineKeyboardMarkup(kb_back_to_sets)

    if not card_report_summary:
        # Sửa escape sequence
        text = "Không có thẻ nào trong bộ này có báo cáo lỗi đang chờ xử lý\\."
        return text, markup_back_to_sets

    # --- Logic phân trang ---
    items_per_page = REPORTS_PER_PAGE
    total_items = len(card_report_summary)
    total_pages = math.ceil(total_items / items_per_page)
    current_page = max(1, min(current_page, total_pages))
    start_index = (current_page - 1) * items_per_page
    end_index = start_index + items_per_page
    items_on_page = card_report_summary[start_index:end_index]
    # ------------------------

    # Sửa escape sequence cho dấu ngoặc đơn
    text = (f"🗂️ **Các thẻ có báo cáo lỗi trong bộ ID {set_id}:** "
            f"\\(Trang {current_page}/{total_pages}\\)\n"
            f"Chọn ID thẻ để xem chi tiết lỗi:")
    keyboard = []

    # --- Tạo nút theo hàng dọc ---
    if not items_on_page:
         text = f"🗂️ **Các thẻ có báo cáo lỗi trong bộ ID {set_id}:**\nKhông có thẻ nào trên trang này."
    else:
        for summary in items_on_page:
            card_id = summary.get('flashcard_id')
            count = summary.get('report_count', 0)
            if card_id is None: continue
            button_text = f"ID: {card_id} ({count})"
            callback_data = f"view_card_reports:{card_id}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    # --------------------------

    # --- Thêm nút phân trang ---
    pagination_row = build_pagination_keyboard(current_page, total_pages, f"report_card_page:{set_id}")
    if pagination_row:
        keyboard.append(pagination_row)
    # -------------------------

    keyboard.extend(kb_back_to_sets) # Thêm nút quay lại cuối

    final_markup = InlineKeyboardMarkup(keyboard)
    logger.debug(f"{log_prefix} Đã tạo keyboard chọn thẻ với {len(items_on_page)} thẻ trên trang {current_page}/{total_pages}.")
    return text, final_markup

# --- Hàm build_card_report_detail_display ---
async def build_card_report_detail_display(card_info, reports_list, context):
    """
    Xây dựng tin nhắn và bàn phím hiển thị chi tiết thẻ và danh sách báo cáo lỗi
    cho thẻ đó. Đã sửa lỗi định dạng và escape, loại bỏ type hint.
    """
    if not card_info or not isinstance(card_info, dict) or 'flashcard_id' not in card_info:
        logger.error("[UI_BUILD_CARD_REPORT_DETAIL] Thiếu thông tin thẻ.")
        return None, None
    if not context:
        logger.error("[UI_BUILD_CARD_REPORT_DETAIL] Thiếu context.")
        return None, None

    flashcard_id = card_info['flashcard_id']
    set_id = card_info.get('set_id')
    log_prefix = f"[UI_BUILD_CARD_REPORT_DETAIL|Card:{flashcard_id}]"
    logger.debug(f"{log_prefix} Tạo hiển thị chi tiết thẻ và báo cáo.")

    # --- Nút quay lại ---
    kb_back_to_cards = []
    if set_id is not None:
        kb_back_to_cards = [[InlineKeyboardButton("🔙 Quay lại DS thẻ lỗi", callback_data=f"view_set_reports:{set_id}")]]
    else:
        kb_back_to_cards = [[InlineKeyboardButton("🔙 Quay lại Chọn bộ", callback_data="view_reports_menu")]]
    # markup_back_to_cards dùng ở cuối

    # --- Hiển thị thông tin thẻ ---
    card_front_raw = card_info.get('front', '(Trống)')
    card_back_raw = card_info.get('back', '(Trống)')
    # Chỉ escape markdown, không escape html
    escaped_front = escape_md_v2(card_front_raw)
    escaped_back = escape_md_v2(card_back_raw)

    text_lines = [
        f"🔖 **Chi tiết thẻ ID `{flashcard_id}`**",
        f"▶️ Mặt trước:\n{escaped_front}",
        f"◀️ Mặt sau:\n{escaped_back}",
        "\n\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-", # Sửa escape sequence
        f"🚨 **Các báo cáo lỗi đang chờ xử lý cho thẻ này:**\n"
    ]

    keyboard = []

    if not reports_list:
        text_lines.append("\\_Không có báo cáo nào\\.\\_") # Sửa escape sequence
        keyboard.extend(kb_back_to_cards)
        return "\n".join(text_lines), InlineKeyboardMarkup(keyboard)

    # --- Lấy tên người báo cáo ---
    bot_instance = context.bot
    reporter_telegram_ids = [r.get('reporter_telegram_id') for r in reports_list if r.get('reporter_telegram_id')]
    reporter_display_names = {}
    if reporter_telegram_ids:
        tasks = [get_chat_display_name(bot_instance, tg_id) for tg_id in reporter_telegram_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, tg_id in enumerate(reporter_telegram_ids):
            if isinstance(results[i], Exception):
                reporter_display_names[tg_id] = f"ID: {tg_id}"
            else:
                reporter_display_names[tg_id] = results[i]

    # --- Liệt kê các báo cáo ---
    report_count = 0
    for report in reports_list:
        report_id = report.get('report_id')
        reporter_user_id = report.get('reporter_user_id')
        reporter_telegram_id = report.get('reporter_telegram_id')
        report_text = report.get('report_text', '')
        reported_at_val = report.get('reported_at')

        if report_id is None: continue
        report_count += 1

        # Định dạng thời gian + Áp dụng Timezone
        reported_time_str = "Không rõ"
        if reported_at_val:
            dt_object_utc = None
            try:
                dt_object_utc = datetime.fromtimestamp(float(reported_at_val), tz=timezone.utc)
            except (ValueError, TypeError):
                try:
                    dt_object_utc = datetime.strptime(str(reported_at_val).split('.')[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                except ValueError:
                    reported_time_str = str(reported_at_val)
            if dt_object_utc:
                try:
                    system_tz = timezone(timedelta(hours=DEFAULT_TIMEZONE_OFFSET))
                    dt_object_local = dt_object_utc.astimezone(system_tz)
                    reported_time_str = dt_object_local.strftime("%d/%m/%Y %H:%M")
                except Exception as tz_err:
                    reported_time_str = dt_object_utc.strftime("%d/%m/%Y %H:%M (UTC)")

        # Lấy tên hiển thị và tạo mention
        reporter_display_str = f"`UID {reporter_user_id}`" # Fallback
        if reporter_telegram_id:
            display_name = reporter_display_names.get(reporter_telegram_id, f"ID: {reporter_telegram_id}")
            # Escape tên cho link MarkdownV2
            escaped_display_name = escape_md_v2(display_name).replace('[', '\\[').replace(']', '\\]')
            reporter_display_str = f"[{escaped_display_name}](tg://user?id={reporter_telegram_id})"

        # Escape nội dung báo cáo và thời gian
        report_escaped_html = html.escape(report_text) # Vẫn escape html cho nội dung nhập tự do
        report_truncated = (report_escaped_html[:100] + '...') if len(report_escaped_html) > 100 else report_escaped_html
        escaped_report_truncated_md = escape_md_v2(report_truncated)
        escaped_reported_time_str_md = escape_md_v2(reported_time_str)

        # Thêm thông tin báo cáo (sửa escape sequence)
        text_lines.append(f"*{report_count}\\.* Báo cáo bởi {reporter_display_str}") # Escape .
        text_lines.append(f"   🕒 Thời gian: {escaped_reported_time_str_md}")
        text_lines.append(f"   💬 Nội dung: {escaped_report_truncated_md}\n")

    # --- Tạo nút bấm ---
    if report_count > 0:
        resolve_button_text = f"✅ Đã sửa xong ({report_count} báo cáo)"
        resolve_callback_data = f"resolve_card_reports:{flashcard_id}"
        keyboard.append([InlineKeyboardButton(resolve_button_text, callback_data=resolve_callback_data)])

    keyboard.extend(kb_back_to_cards)

    final_text = "\n".join(text_lines)
    final_markup = InlineKeyboardMarkup(keyboard)
    logger.debug(f"{log_prefix} Đã tạo xong hiển thị chi tiết thẻ và báo cáo (đã sửa escape).")

    return final_text, final_markup