# Path: flashcard/ui/flashcard_ui.py
"""
Module chứa các hàm xây dựng giao diện người dùng liên quan đến quá trình ôn tập flashcard.
(Đã sửa vị trí nút Báo lỗi sang màn hình metric theo yêu cầu).
(Cập nhật build_rating_keyboard để hiển thị nút Note khi show_review_summary=False).
"""

import logging
import html
from datetime import datetime
from datetime import timedelta
from datetime import time as dt_time # Đổi tên để tránh xung đột

from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup

# Sử dụng import tuyệt đối cho các module trong project
from config import SKIP_STREAK_THRESHOLD
from config import MODE_REVIEW_ALL_DUE

# Khởi tạo logger
logger = logging.getLogger(__name__)

# --- Hàm build_rating_keyboard ---
def build_rating_keyboard(progress_id, flashcard_id, user_info, is_new_card, note_exists, note_id, correct_count):
    """
    Tạo bàn phím inline cho mặt sau của flashcard.
    Nếu show_review_summary tắt, sẽ hiển thị nút Thêm/Sửa Note ở hàng 1,
    các nút đánh giá ở hàng 2.
    Nếu show_review_summary bật, chỉ hiển thị các nút đánh giá.

    Args:
        progress_id (int): ID của bản ghi tiến trình.
        flashcard_id (int): ID của flashcard.
        user_info (dict): Dictionary chứa thông tin người dùng (để lấy show_review_summary).
        is_new_card (bool): True nếu đây là thẻ mới học lần đầu.
        note_exists (bool): True nếu ghi chú đã tồn tại cho thẻ này của người dùng này.
        note_id (int, optional): ID của ghi chú nếu đã tồn tại.
        correct_count (int): Số lần trả lời đúng thẻ này.

    Returns:
        InlineKeyboardMarkup: Bàn phím inline được tạo.
    """
    log_prefix = "[UI_BUILD_BACKSIDE_KB|ProgID:{}]".format(progress_id)
    logger.debug(
        "{}: Bắt đầu xây dựng keyboard. FlashcardID: {}, NewCard: {}, NoteExists: {}, NoteID: {}, CorrectCount: {}"
        .format(log_prefix, flashcard_id, is_new_card, note_exists, note_id, correct_count)
    )

    keyboard = []
    rating_button_row = []

    # Kiểm tra cài đặt show_review_summary
    show_summary_enabled = True # Mặc định là True nếu không có thông tin
    if user_info and isinstance(user_info, dict):
        show_summary_enabled = user_info.get('show_review_summary', 1) == 1
    logger.debug("{}: Trạng thái show_review_summary: {}".format(log_prefix, show_summary_enabled))

    # Hàng 1: Nút Ghi chú (nếu show_summary_enabled là False)
    if not show_summary_enabled:
        note_button_row = []
        if note_exists:
            if note_id:
                note_button_text = "✏️ Sửa ghi chú"
                note_callback_data = "update_note_by_id:{}".format(note_id)
                logger.debug("{}: Tạo nút 'Sửa ghi chú' với note_id: {}".format(log_prefix, note_id))
            else:
                # Fallback nếu note_exists là True nhưng không có note_id (trường hợp hiếm)
                note_button_text = "➕ Thêm ghi chú"
                note_callback_data = "add_note_for_user:{}".format(flashcard_id)
                logger.warning("{}: note_exists=True nhưng note_id không có. Tạo nút 'Thêm ghi chú'.".format(log_prefix))
        else:
            note_button_text = "➕ Thêm ghi chú"
            note_callback_data = "add_note_for_user:{}".format(flashcard_id)
            logger.debug("{}: Tạo nút 'Thêm ghi chú' cho flashcard_id: {}".format(log_prefix, flashcard_id))

        note_button = InlineKeyboardButton(note_button_text, callback_data=note_callback_data)
        note_button_row.append(note_button)
        keyboard.append(note_button_row)
        logger.debug("{}: Đã thêm hàng nút ghi chú.".format(log_prefix))

    # Hàng 2 (hoặc hàng 1 nếu show_summary_enabled là True): Nút đánh giá/tiếp tục
    if is_new_card:
        logger.debug("{}: Tạo nút 'Tiếp tục' cho thẻ mới.".format(log_prefix))
        button_continue_text = "▶️ Tiếp tục"
        button_continue_callback = "rate:{}:2".format(progress_id) # response = 2 cho thẻ mới
        button_continue = InlineKeyboardButton(button_continue_text, callback_data=button_continue_callback)
        rating_button_row.append(button_continue)
    else:
        logger.debug("{}: Tạo các nút đánh giá (Nhớ/Mơ hồ/Chưa nhớ).".format(log_prefix))
        button_wrong_text = "❌ Chưa nhớ"
        button_wrong_callback = "rate:{}:-1".format(progress_id) # response = -1
        button_wrong = InlineKeyboardButton(button_wrong_text, callback_data=button_wrong_callback)

        button_hard_text = "🤔 Mơ hồ"
        button_hard_callback = "rate:{}:0".format(progress_id) # response = 0
        button_hard = InlineKeyboardButton(button_hard_text, callback_data=button_hard_callback)

        button_good_text = "✅ Nhớ"
        button_good_callback = "rate:{}:1".format(progress_id) # response = 1
        button_good = InlineKeyboardButton(button_good_text, callback_data=button_good_callback)

        rating_button_row.append(button_wrong)
        rating_button_row.append(button_hard)
        rating_button_row.append(button_good)

    keyboard.append(rating_button_row)
    logger.debug("{}: Đã thêm hàng nút đánh giá/tiếp tục.".format(log_prefix))

    logger.debug("{}: Đã tạo xong keyboard cho mặt sau. Tổng số hàng: {}".format(log_prefix, len(keyboard)))
    return InlineKeyboardMarkup(keyboard)

# --- Hàm build_review_summary_display ---
def build_review_summary_display(flashcard_data, progress_data, stats_data, next_review_str, review_mode, card_status_text, note_exists, note_id, correct_count):
    """
    Xây dựng nội dung tin nhắn và bàn phím hiển thị thống kê sau khi ôn tập.
    Bố cục nút bấm: (Bỏ qua & Report) / (Ghi chú | Menu) / Tiếp tục.
    """
    log_prefix = "[UI_BUILD_METRIC|Card:{}]".format(flashcard_data.get('flashcard_id', 'N/A'))
    correct_streak = flashcard_data.get('correct_streak', 0)
    logger.debug(
        "{}: Bắt đầu xây dựng metric. Mode: {}, Status: {}, NoteExists: {}, NoteID: {}, CorrectCount: {}, CorrectStreak: {}"
        .format(log_prefix, review_mode, card_status_text, note_exists, note_id, correct_count, correct_streak)
    )

    # Kiểm tra dữ liệu đầu vào
    required_keys = ['flashcard_id', 'progress_id', 'correct_streak']
    if not flashcard_data or not progress_data or not stats_data or next_review_str is None or not card_status_text:
        logger.error("{}: Thiếu dữ liệu đầu vào cơ bản.".format(log_prefix))
        return None, None
    if not all(key in flashcard_data for key in required_keys):
        logger.error("{}: Thiếu key bắt buộc trong flashcard_data: {}".format(log_prefix, required_keys))
        return None, None
    if not isinstance(note_exists, bool) or not isinstance(correct_count, int) or not isinstance(correct_streak, int): # Thêm kiểm tra correct_streak
        logger.error("{}: Kiểu dữ liệu không đúng cho note_exists/correct_count/correct_streak.".format(log_prefix))
        return None, None

    # Lấy thông tin
    flashcard_id = flashcard_data.get('flashcard_id')
    progress_id = flashcard_data.get('progress_id')
    set_id_value = flashcard_data.get("set_id")
    set_title = flashcard_data.get("title", "Bộ ID {}".format(set_id_value) if set_id_value else "Không rõ bộ")

    # Tạo nội dung Text
    flashcard_info_text_lines = [
        "📌 ID Thẻ: {}".format(flashcard_id),
        "📊 Trạng thái: **{}**".format(card_status_text),
        "✅ Chuỗi đúng: {}".format(correct_streak), # Sử dụng correct_streak đã lấy
        "👍 Tổng lần đúng: {}".format(correct_count), # Sử dụng correct_count đã lấy
        "🔄 Lượt ôn: {}".format(progress_data.get('review_count', 'N/A')),
        "⏰ Lần tới: {}".format(next_review_str)
    ]
    flashcard_info_text = "\n".join(flashcard_info_text_lines)

    set_info_text_lines = ["📊 THỐNG KÊ BỘ: **{}**".format(html.escape(set_title))]
    total_count_in_set = stats_data.get('total_count', 0)
    learned_total_in_set = stats_data.get('learned_total', 0)
    due_total_in_set = stats_data.get('due_total', 0)
    percent_learned = 0.0
    if total_count_in_set > 0:
        percent_learned = (float(learned_total_in_set) / total_count_in_set * 100.0)
    learned_str = "{}/{} ({:.0f}%)".format(learned_total_in_set, total_count_in_set, percent_learned)
    set_info_text_lines.append("📚 Đã học trong bộ: {}".format(learned_str))
    set_info_text_lines.append("❗ Cần ôn trong bộ: {}".format(due_total_in_set))
    set_info_text = "\n".join(set_info_text_lines)

    course_info_text_lines = ["📈 THỐNG KÊ CHUNG"]
    course_info_text_lines.append("📘 Tổng từ đã học: {}".format(stats_data.get('learned_distinct', 'N/A')))
    course_info_text_lines.append("⏳ Tổng từ cần ôn: {}".format(stats_data.get('course_due_total', 'N/A')))
    course_info_text_lines.append("🗂️ Số bộ đã học: {}".format(stats_data.get('learned_sets', 'N/A')))
    course_info_text_lines.append("💯 Tổng điểm: {}".format(stats_data.get('user_score', 'N/A')))
    course_info_text = "\n".join(course_info_text_lines)

    separator_set = "-" * 25
    separator_course = "=" * 15
    details = "{}\n{}\n{}\n{}\n{}".format(flashcard_info_text, separator_set, set_info_text, separator_course, course_info_text)

    # --- Tạo Keyboard với bố cục nút Report mới ---
    keyboard = []

    # Hàng 1: Nút Bỏ qua và/hoặc Nút Report
    first_row = []
    # Tạo nút Report trước (luôn có)
    report_button_text = "🚩 Báo lỗi"
    report_callback_data = "report_card:{}".format(flashcard_id)
    report_button = InlineKeyboardButton(report_button_text, callback_data=report_callback_data)

    # Kiểm tra xem có nút Bỏ qua không
    if correct_streak >= SKIP_STREAK_THRESHOLD: # Sử dụng correct_streak
        # Nếu có, thêm nút Bỏ qua và Report vào cùng hàng
        skip_button_text = "⏩ Bỏ qua" # Text ngắn hơn
        skip_callback_data = "skip:{}".format(progress_id)
        skip_button = InlineKeyboardButton(skip_button_text, callback_data=skip_callback_data)
        first_row.append(skip_button) # Thêm nút Bỏ qua trước
        first_row.append(report_button) # Thêm nút Report sau
        logger.debug("{}: Đã thêm hàng nút Bỏ qua & Report.".format(log_prefix))
    else:
        # Nếu không có nút Bỏ qua, hàng đầu chỉ có nút Report
        first_row.append(report_button)
        logger.debug("{}: Đã thêm hàng nút Report (không có Bỏ qua).".format(log_prefix))

    # Thêm hàng đầu tiên vào keyboard
    keyboard.append(first_row)

    # Hàng 2: Nút Ghi chú và Nút Menu
    action_row = []
    note_button_text = ""
    note_callback_data = ""
    if note_exists:
        note_button_text = "✏️ Sửa ghi chú"
        if note_id:
            note_callback_data = "update_note_by_id:{}".format(note_id)
        else:
            # Fallback nếu note_exists là True nhưng không có note_id
            logger.error("{}: Lỗi: note_exists=True nhưng note_id=None.".format(log_prefix))
            note_button_text = "➕ Thêm ghi chú"
            note_callback_data = "add_note_for_user:{}".format(flashcard_id)
    else:
        note_button_text = "➕ Thêm ghi chú"
        note_callback_data = "add_note_for_user:{}".format(flashcard_id)
    note_button = InlineKeyboardButton(note_button_text, callback_data=note_callback_data)
    action_row.append(note_button)

    back_button_text = "🔙 Menu"
    back_callback = "handle_callback_back_to_main"
    back_button = InlineKeyboardButton(back_button_text, callback_data=back_callback)
    action_row.append(back_button)
    keyboard.append(action_row)

    # Hàng 3: Nút Tiếp tục học
    continue_row = []
    continue_callback_data = "review_all" if review_mode == MODE_REVIEW_ALL_DUE else "continue"
    logger.debug("{}: Dùng callback tiếp tục: '{}' cho mode '{}'".format(log_prefix, continue_callback_data, review_mode))
    continue_button_text = "▶️ Tiếp tục học"
    continue_button = InlineKeyboardButton(continue_button_text, callback_data=continue_callback_data)
    continue_row.append(continue_button)
    keyboard.append(continue_row)
    # --- Kết thúc tạo Keyboard ---

    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug("{}: Đã tạo xong text và keyboard cho metric display (có nút Report).".format(log_prefix))
    return details, reply_markup

# Hàm build_no_card_display và build_note_display giữ nguyên
def build_no_card_display(wait_time_ts, review_mode='set'):
    """
    Xây dựng nội dung và bàn phím hiển thị khi không còn thẻ nào để ôn tập/học mới.
    """
    log_prefix = "[UI_BUILD_NO_CARD|Mode:{}]".format(review_mode)
    logger.debug("{}: Xây dựng hiển thị không có thẻ. Wait_ts (âm): {}".format(log_prefix, wait_time_ts))

    if wait_time_ts > 0:
        logger.error("{}: wait_time_ts phải là giá trị âm!".format(log_prefix))
        wait_time_ts = -wait_time_ts # Đảm bảo là âm

    actual_wait_ts = abs(wait_time_ts)
    now = datetime.now()
    now_ts = int(now.timestamp())
    wait_dt = datetime.fromtimestamp(actual_wait_ts)
    wait_minutes = 1

    if actual_wait_ts > now_ts:
        wait_minutes = max(1, int((actual_wait_ts - now_ts + 59) / 60)) # Làm tròn lên

    # Kiểm tra xem thời gian chờ có phải là nửa đêm ngày mai không
    # Cần tzinfo=None để so sánh với datetime.combine không có tzinfo
    midnight_next_day_check = datetime.combine((now + timedelta(days=1)).date(), dt_time.min, tzinfo=None)
    wait_dt_naive = wait_dt.replace(tzinfo=None) # Bỏ tzinfo để so sánh
    is_midnight_tomorrow = abs(wait_dt_naive - midnight_next_day_check) < timedelta(minutes=1)

    text = ""
    if is_midnight_tomorrow:
        text = (
            "🎉 Tuyệt vời! Bạn đã hoàn thành tất cả các thẻ cần ôn tập hoặc thẻ mới cho hôm nay.\n"
            "📅 Hãy quay lại vào ngày mai để tiếp tục học nhé!"
        )
        logger.debug("{}: Chờ đến nửa đêm mai.".format(log_prefix))
    elif actual_wait_ts > now_ts:
        try:
            wait_time_str = wait_dt.strftime('%H:%M %d/%m/%Y')
            text = (
                "👍 Bạn đã ôn hết các thẻ đến hạn hiện tại.\n"
                "⌛️ Thẻ tiếp theo sẽ đến hạn vào khoảng **{} phút** nữa (lúc {}).\n"
                "Bạn có thể chờ hoặc nhấn 'Tiếp tục' để thử lại."
            ).format(wait_minutes, wait_time_str)
            logger.debug("{}: Chờ {} phút.".format(log_prefix, wait_minutes))
        except Exception as e_time:
            logger.error("{}: Lỗi định dạng thời gian chờ: {}".format(log_prefix, e_time))
            text = (
                "✅ Hiện tại không có thẻ nào cần ôn tập ngay.\n"
                "Bạn có thể thử lại bằng nút 'Tiếp tục'."
            )
    else:
        # Thời gian chờ đã qua hoặc không xác định
        logger.warning("{}: Trạng thái không xác định hoặc thời gian chờ đã qua (wait_ts={}).".format(log_prefix, wait_time_ts))
        text = (
            "✅ Hiện tại không có thẻ nào cần ôn tập ngay.\n"
            "Bạn có thể thử lại bằng nút 'Tiếp tục'."
        )

    keyboard = []
    # Xác định callback cho nút "Tiếp tục"
    continue_callback = "review_all" if review_mode == MODE_REVIEW_ALL_DUE else "continue"
    logger.debug("{}: Callback 'Tiếp tục': '{}' cho mode '{}'".format(log_prefix, continue_callback, review_mode))
    continue_button = InlineKeyboardButton("▶️ Tiếp tục", callback_data=continue_callback)
    keyboard.append([continue_button])

    back_button = InlineKeyboardButton("🔙 Menu chính", callback_data="handle_callback_back_to_main")
    keyboard.append([back_button])

    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.debug("{}: Đã tạo text và keyboard cho trạng thái không có thẻ.".format(log_prefix))
    return text, reply_markup

def build_note_display(note_data, flashcard_id):
    """
    Xây dựng nội dung tin nhắn và bàn phím hiển thị/thêm/sửa ghi chú.
    (Hàm này hiện tại không được gọi trực tiếp từ luồng chính nếu show_summary_enabled=False,
     nhưng vẫn giữ lại để tham khảo hoặc sử dụng ở nơi khác nếu cần).
    """
    log_prefix = "[UI_BUILD_NOTE|Card:{}]".format(flashcard_id)
    keyboard = []
    text = ""

    if note_data and isinstance(note_data, dict):
        note_id = note_data.get('note_id')
        note_content = note_data.get('note', '')
        created_at_ts = note_data.get('created_at')
        created_at_str = ""
        if created_at_ts:
            try:
                created_at_dt = datetime.fromtimestamp(created_at_ts)
                created_at_str = " ({})".format(created_at_dt.strftime("%d/%m/%Y %H:%M"))
            except Exception as e_time:
                logger.warning("{}: Lỗi định dạng timestamp {} cho note {}: {}".format(log_prefix, created_at_ts, note_id, e_time))
                created_at_str = ""

        logger.debug("{}: Hiển thị ghi chú ID: {}".format(log_prefix, note_id))
        escaped_note = html.escape(note_content)
        text = "📝 **Ghi chú của bạn**{}:\n\n{}".format(created_at_str, escaped_note)
        edit_button_text = "✏️ Sửa ghi chú"
        edit_callback = "update_note_by_id:{}".format(note_id) if note_id else "error_note_id" # Tránh callback lỗi
        edit_button = InlineKeyboardButton(edit_button_text, callback_data=edit_callback)
        keyboard.append([edit_button])
    else:
        logger.debug("{}: Chưa có ghi chú. Hiển thị nút thêm.".format(log_prefix))
        text = "Bạn chưa có ghi chú nào cho thẻ này."
        add_button_text = "➕ Thêm ghi chú"
        add_callback = "add_note_for_user:{}".format(flashcard_id)
        add_button = InlineKeyboardButton(add_button_text, callback_data=add_callback)
        keyboard.append([add_button])

    # Có thể thêm nút quay lại màn hình trước đó nếu cần
    # Ví dụ: keyboard.append([InlineKeyboardButton("🔙 Quay lại", callback_data="back_to_card_face")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    return text, reply_markup