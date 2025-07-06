"""
Module chứa business logic cốt lõi liên quan đến ôn tập flashcard (SRS).
Bao gồm tính toán lịch ôn tập và xử lý kết quả đánh giá của người dùng.
Các hàm đã được cập nhật để sử dụng user_id (khóa chính).
"""
import math
import logging
import time
import sqlite3
from datetime import datetime, time as dt_time, timedelta, timezone
from utils.helpers import get_current_unix_timestamp
from database.query_progress import (
    get_progress_with_card_info, 
    update_progress_by_id      
)
from database.query_user import update_user_by_id
from database.connection import database_connect
from config import (
    DEFAULT_TIMEZONE_OFFSET,
    SRS_INITIAL_INTERVAL_HOURS, SRS_MAX_INTERVAL_DAYS,
    RETRY_INTERVAL_WRONG_MIN, RETRY_INTERVAL_HARD_MIN, RETRY_INTERVAL_NEW_MIN,
    SCORE_INCREASE_CORRECT, SCORE_INCREASE_HARD,
    SCORE_INCREASE_QUICK_REVIEW_CORRECT, SCORE_INCREASE_QUICK_REVIEW_HARD,
    DEFAULT_LEARNING_MODE,
    MODE_REVIEW_HARDEST, MODE_CRAM_SET, MODE_CRAM_ALL
)
from utils.exceptions import (
    UserNotFoundError, DatabaseError,
    ValidationError, DuplicateError
)
logger = logging.getLogger(__name__)
def calculate_next_review_time(streak_correct=0, total_correct=0, current_timestamp=None, tz_offset_hours=DEFAULT_TIMEZONE_OFFSET):
    """
    Tính toán Unix timestamp cho lần ôn tập tiếp theo.
    Args:
        streak_correct (int): Chuỗi trả lời đúng liên tiếp hiện tại.
        total_correct (int): Tổng số lần trả lời đúng.
        current_timestamp (int): Timestamp hiện tại (tùy chọn).
        tz_offset_hours (int): Múi giờ của người dùng (tùy chọn).
    Returns:
        int: Unix timestamp của lần ôn tập tiếp theo.
    """
    log_prefix = "[CALC_SRS_TIME]"
    if current_timestamp is None:
        current_timestamp = get_current_unix_timestamp(tz_offset_hours)
    delay_minutes = 60 
    logger.debug(f"{log_prefix} Input: streak={streak_correct}, total={total_correct}, current_ts={current_timestamp}, tz_offset={tz_offset_hours}")
    try:
        streak_correct = max(0, int(streak_correct or 0))
        total_correct = max(0, int(total_correct or 0))
        base_interval_hours = SRS_INITIAL_INTERVAL_HOURS
        if streak_correct > 0:
            base_interval_hours = (2 ** (streak_correct - 1)) * 2
        max_interval_hours = SRS_MAX_INTERVAL_DAYS * 24
        final_interval_hours = min(base_interval_hours, max_interval_hours)
        delay_minutes = final_interval_hours * 60
        logger.debug(f"{log_prefix} Calculated base interval: {base_interval_hours}h, final: {final_interval_hours}h, delay_minutes: {delay_minutes:.2f}")
    except OverflowError:
        logger.warning(f"{log_prefix} OverflowError khi tính delay. Sử dụng max interval.")
        max_delay_minutes = SRS_MAX_INTERVAL_DAYS * 24 * 60
        delay_minutes = max_delay_minutes
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi khi tính delay_minutes: {e}. Dùng delay mặc định 60 phút.", exc_info=True)
        delay_minutes = 60 
    delay_seconds = int(round(delay_minutes * 60))
    next_review_timestamp = current_timestamp + delay_seconds
    min_next_ts = current_timestamp + 60 
    next_review_timestamp = max(next_review_timestamp, min_next_ts)
    logger.info(f"{log_prefix} Kết quả: streak={streak_correct}, total={total_correct} -> delay={delay_minutes:.2f}m, next_ts={next_review_timestamp}")
    return next_review_timestamp
def process_review_response(user_id, progress_id, response):
    """
    Xử lý kết quả đánh giá flashcard của người dùng (logic nghiệp vụ).
    Cập nhật tiến trình học, điểm số, và ghi log.
    Args:
        user_id (int): ID (khóa chính) của người dùng.
        progress_id (int): ID bản ghi progress (UserFlashcardProgress PK).
        response (int): Kết quả đánh giá (-1: Sai, 0: Mơ hồ, 1: Đúng, 2: Thẻ mới - Tiếp tục).
    Returns:
        tuple: (flashcard_info_updated, update_data_dict, next_review_ts) nếu thành công.
               (None, None, None) nếu lỗi nghiêm trọng.
    Raises:
        DatabaseError, UserNotFoundError, ProgressNotFoundError, ValidationError, DuplicateError
        (Các lỗi này sẽ được ném lên để tầng handler xử lý)
    """
    log_prefix = f"[PROCESS_ANSWER|UserUID:{user_id}|ProgID:{progress_id}|Resp:{response}]" 
    logger.debug(f"{log_prefix} Bắt đầu xử lý đánh giá.")
    flashcard = None
    user_info = None
    current_mode = DEFAULT_LEARNING_MODE
    tz_offset_hours = DEFAULT_TIMEZONE_OFFSET
    flashcard = get_progress_with_card_info(progress_id)
    logger.debug(f"{log_prefix} Lấy thông tin progress/card thành công.")
    current_streak_correct = flashcard.get("correct_streak", 0)
    current_total_correct = flashcard.get("correct_count", 0)
    current_incorrect_count = flashcard.get("incorrect_count", 0)
    current_lapse_count = flashcard.get("lapse_count", 0)
    current_review_count = flashcard.get("review_count", 0)
    logger.debug(f"{log_prefix} Trạng thái hiện tại: streak={current_streak_correct}, total_correct={current_total_correct}, reviews={current_review_count}, incorrect={current_incorrect_count}, lapses={current_lapse_count}")
    conn_user = None
    try:
        conn_user = database_connect()
        if conn_user is None:
             raise DatabaseError("Không thể kết nối DB để lấy thông tin user.")
        conn_user.row_factory = sqlite3.Row 
        cursor_user = conn_user.cursor()
        query_user = 'SELECT timezone_offset, current_mode, score FROM Users WHERE user_id = ?'
        cursor_user.execute(query_user, (user_id,))
        user_row = cursor_user.fetchone()
        if user_row:
            user_info = dict(user_row) 
            tz_offset_hours = user_info.get('timezone_offset', DEFAULT_TIMEZONE_OFFSET)
            current_mode = user_info.get('current_mode', DEFAULT_LEARNING_MODE)
            logger.debug(f"{log_prefix} Lấy được user info: tz_offset={tz_offset_hours}, mode={current_mode}, score={user_info.get('score')}")
        else:
             raise UserNotFoundError(identifier=user_id)
    except sqlite3.Error as e_db_user:
         logger.error(f"{log_prefix} Lỗi SQLite khi lấy user info: {e_db_user}")
         raise DatabaseError("Lỗi SQLite khi lấy thông tin người dùng.", original_exception=e_db_user)
    finally:
         if conn_user: conn_user.close()
    quick_review_modes = {MODE_REVIEW_HARDEST, MODE_CRAM_SET, MODE_CRAM_ALL}
    is_quick_review = (current_mode in quick_review_modes)
    logger.debug(f"{log_prefix} Chế độ ôn tập nhanh: {is_quick_review}")
    new_streak_correct = current_streak_correct
    new_total_correct = current_total_correct
    new_incorrect_count = current_incorrect_count
    new_lapse_count = current_lapse_count
    new_review_count = current_review_count + 1 if response in [-1, 0, 1] else current_review_count
    current_ts = int(time.time())
    score_to_add = 0
    next_review_time = flashcard.get("due_time", current_ts + 60) 
    if is_quick_review:
        if response == 1: score_to_add = SCORE_INCREASE_QUICK_REVIEW_CORRECT
        elif response == 0: score_to_add = SCORE_INCREASE_QUICK_REVIEW_HARD
    else:
        if response == 1: score_to_add = SCORE_INCREASE_CORRECT
        elif response == 0: score_to_add = SCORE_INCREASE_HARD
    logger.debug(f"{log_prefix} Điểm cần cộng: {score_to_add}")
    if not is_quick_review:
        if response == 1:
            new_streak_correct = current_streak_correct + 1
            new_total_correct = current_total_correct + 1
            next_review_time = calculate_next_review_time(new_streak_correct, new_total_correct, current_ts, tz_offset_hours)
            logger.debug(f"{log_prefix} Đánh giá: Nhớ (thường). Next review: {next_review_time}")
        elif response == -1:
            if current_streak_correct > 0: new_lapse_count = current_lapse_count + 1
            new_streak_correct = 0
            new_incorrect_count = current_incorrect_count + 1
            next_review_time = current_ts + RETRY_INTERVAL_WRONG_MIN * 60
            logger.debug(f"{log_prefix} Đánh giá: Chưa nhớ (thường). Next review: {next_review_time}")
        elif response == 0:
            new_streak_correct = 0 
            next_review_time = current_ts + RETRY_INTERVAL_HARD_MIN * 60
            logger.debug(f"{log_prefix} Đánh giá: Mơ hồ (thường). Next review: {next_review_time}")
        elif response == 2: 
            next_review_time = current_ts + RETRY_INTERVAL_NEW_MIN * 60
            logger.debug(f"{log_prefix} Đánh giá: Tiếp tục (thẻ mới). Next review: {next_review_time}")
        else:
            logger.error(f"{log_prefix} Response không hợp lệ: {response}")
            raise ValidationError(f"Response không hợp lệ: {response}")
    else:
        logger.debug(f"{log_prefix} Mode ôn nhanh, không cập nhật lịch SRS.")
    update_data = {"last_reviewed": current_ts, "review_count": new_review_count}
    if not is_quick_review:
        update_data["due_time"] = next_review_time
        update_data["correct_streak"] = new_streak_correct
        update_data["correct_count"] = new_total_correct
        update_data["incorrect_count"] = new_incorrect_count
        update_data["lapse_count"] = new_lapse_count
        if response == 2 and flashcard.get("learned_date") is None:
            try:
                user_tz = timezone(timedelta(hours=tz_offset_hours))
                today_start_dt = datetime.combine(datetime.now(user_tz).date(), dt_time.min, tzinfo=user_tz)
                today_start_ts = int(today_start_dt.timestamp())
                update_data["learned_date"] = today_start_ts
                logger.debug(f"{log_prefix} Thẻ mới (mode thường), set learned_date = {today_start_ts}")
            except Exception as date_err:
                logger.error(f"{log_prefix} Lỗi khi tính learned_date: {date_err}.")
    logger.debug(f"{log_prefix} Đang cập nhật progress với dữ liệu: {update_data}")
    update_result = update_progress_by_id(progress_id, **update_data)
    logger.info(f"{log_prefix} Cập nhật progress thành công (Rows: {update_result}).")
    if score_to_add != 0 and user_info is not None:
        try:
            current_score = user_info.get('score', 0)
            new_score = current_score + score_to_add
            logger.debug(f"{log_prefix} Chuẩn bị cập nhật điểm: user_id={user_id}, score_to_add={score_to_add}, current_score={current_score}, new_score={new_score}")
            score_update_result = update_user_by_id(user_id, score=new_score)
            logger.info(f"{log_prefix} Cập nhật điểm thành công (Rows: {score_update_result}).")
        except (DatabaseError, DuplicateError, ValidationError) as e_score:
            logger.error(f"{log_prefix} Cập nhật điểm thất bại: {e_score}")
    elif score_to_add != 0:
        logger.warning(f"{log_prefix} Không cập nhật được điểm do user_info là None.")
    if response in [-1, 0, 1]:
        log_conn = None
        try:
            log_conn = database_connect()
            if log_conn:
                log_cursor = log_conn.cursor()
                current_set_id = flashcard.get('set_id')
                flashcard_id_log = flashcard.get('flashcard_id')
                if flashcard_id_log is not None:
                    log_query = "INSERT INTO DailyReviewLog (user_id, flashcard_id, set_id, review_timestamp, response, score_change) VALUES (?, ?, ?, ?, ?, ?)"
                    log_values = (user_id, flashcard_id_log, current_set_id, current_ts, response, score_to_add) 
                    logger.debug(f"{log_prefix} Đang ghi DailyReviewLog: {log_values}")
                    log_cursor.execute(log_query, log_values)
                    log_conn.commit()
                    logger.info(f"{log_prefix} Đã ghi DailyReviewLog.")
                else:
                    logger.warning(f"{log_prefix} Thiếu flashcard_id để ghi DailyReviewLog.")
            else:
                logger.error(f"{log_prefix} Không thể kết nối DB để ghi DailyReviewLog.")
        except sqlite3.Error as e_log_db:
            logger.error(f"{log_prefix} Lỗi DB khi ghi DailyReviewLog: {e_log_db}", exc_info=True)
        except Exception as e_log_unk:
            logger.error(f"{log_prefix} Lỗi không mong muốn khi ghi DailyReviewLog: {e_log_unk}", exc_info=True)
        finally:
            if log_conn: log_conn.close()
    else: 
        logger.debug(f"{log_prefix} Bỏ qua ghi DailyReviewLog cho thẻ mới (response=2).")
    updated_flashcard_info = {**flashcard, **update_data}
    final_next_review_ts = update_data.get("due_time", next_review_time) 
    return updated_flashcard_info, update_data, final_next_review_ts