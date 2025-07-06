"""
Module chứa các hàm truy vấn và cập nhật dữ liệu liên quan đến
bảng UserFlashcardProgress và DailyReviewLog, cũng như logic lấy thẻ tiếp theo.
Các hàm đã được cập nhật để sử dụng user_id (khóa chính) thay vì telegram_id.
"""
import sqlite3
import logging
import time
import random
from datetime import datetime, time as dt_time, timedelta, timezone
from database.connection import database_connect
from database.query_card import get_card_by_id
from config import (
    ROLE_PERMISSIONS, HAS_UNLIMITED_NEW_CARDS, DAILY_LIMIT_USER,
    DEFAULT_TIMEZONE_OFFSET,
    RETRY_INTERVAL_NEW_MIN,
    DEFAULT_LEARNING_MODE,
    MODE_SEQ_INTERSPERSED, MODE_SEQ_RANDOM_NEW, MODE_NEW_SEQUENTIAL,
    MODE_DUE_ONLY_RANDOM, MODE_REVIEW_ALL_DUE, MODE_REVIEW_HARDEST,
    MODE_CRAM_SET, MODE_CRAM_ALL, MODE_NEW_RANDOM
)
from utils.exceptions import (
    DatabaseError, ProgressNotFoundError, CardNotFoundError,
    UserNotFoundError, ValidationError, DuplicateError
)
logger = logging.getLogger(__name__)
def get_progress_with_card_info(progress_id, conn=None):
    """
    Lấy thông tin chi tiết của bản ghi tiến trình và thẻ flashcard tương ứng.
    Args:
        progress_id (int): ID của bản ghi tiến trình (UserFlashcardProgress PK).
        conn (sqlite3.Connection): Kết nối DB có sẵn (tùy chọn).
    Returns:
        dict: Dictionary chứa thông tin kết hợp của progress và card.
    Raises:
        DatabaseError: Nếu có lỗi DB.
        ProgressNotFoundError: Nếu không tìm thấy progress_id.
        CardNotFoundError: Nếu không tìm thấy flashcard_id tương ứng.
    """
    log_prefix = f"[GET_CARD_BY_PROG_ID|ProgID:{progress_id}]"
    internal_conn = None
    should_close_conn = False
    combined_info = None
    original_factory = None
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối DB nội bộ.")
            conn = internal_conn
            should_close_conn = True
            conn.row_factory = sqlite3.Row
        else:
            original_factory = conn.row_factory
            conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        logger.debug(f"{log_prefix} Lấy progress...")
        cursor.execute("SELECT * FROM UserFlashcardProgress WHERE progress_id = ?", (progress_id,))
        progress_row = cursor.fetchone()
        if not progress_row:
            raise ProgressNotFoundError(progress_id=progress_id)
        progress_info = dict(progress_row)
        flashcard_id = progress_info.get("flashcard_id")
        if flashcard_id is None:
            raise DatabaseError(f"Bản ghi progress ID {progress_id} thiếu flashcard_id.")
        logger.debug(f"{log_prefix} Lấy flashcard ID: {flashcard_id}...")
        card_info = get_card_by_id(flashcard_id, conn=conn)
        combined_info = {**progress_info, **card_info}
        logger.debug(f"{log_prefix} Kết hợp info thành công.")
    except sqlite3.Error as e:
        logger.exception(f"{log_prefix} Lỗi SQLite: {e}")
        raise DatabaseError("Lỗi SQLite khi lấy progress/card info.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm: {e}")
        if isinstance(e, (DatabaseError, ProgressNotFoundError, CardNotFoundError)):
            raise e 
        raise DatabaseError("Lỗi không mong muốn khi lấy progress/card info.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
            try: conn.execute("SELECT 1"); conn.row_factory = original_factory
            except Exception: pass
        if should_close_conn and internal_conn:
            try: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối nội bộ.")
            except Exception as e_close: logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")
    return combined_info
def update_progress_by_id(progress_id, conn=None, **kwargs):
    """
    Cập nhật một bản ghi tiến trình học (UserFlashcardProgress) dựa trên progress_id.
    Args:
        progress_id (int): ID của bản ghi tiến trình cần cập nhật.
        conn (sqlite3.Connection): Kết nối DB có sẵn (tùy chọn).
        **kwargs: Các trường và giá trị cần cập nhật.
    Returns:
        int: Số hàng bị ảnh hưởng.
    Raises:
        DatabaseError: Nếu có lỗi DB.
        ValidationError: Nếu kwargs rỗng hoặc chứa trường không hợp lệ.
                         (Lưu ý: Hàm này không kiểm tra tên cột chặt chẽ,
                          nên lỗi OperationalError có thể xảy ra nếu cột sai).
    """
    log_prefix = f"[UPDATE_PROGRESS|ProgID:{progress_id}]"
    internal_conn = None
    should_close_conn = False
    should_commit = False
    rows_affected = 0
    if not kwargs:
        logger.warning(f"{log_prefix} Không có trường để cập nhật.")
        raise ValidationError("Không có trường để cập nhật progress.")
    update_clauses = []
    parameters = []
    for key, value in kwargs.items():
        update_clauses.append(f'"{key}" = ?')
        parameters.append(value)
    parameters.append(progress_id) 
    set_clause = ", ".join(update_clauses)
    query = f'UPDATE "UserFlashcardProgress" SET {set_clause} WHERE "progress_id" = ?'
    logger.debug(f"{log_prefix} Executing query: {query} with params: {parameters}")
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối DB nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True
        cursor = conn.cursor()
        cursor.execute(query, parameters)
        rows_affected = cursor.rowcount
        if should_commit:
            conn.commit()
            logger.debug(f"{log_prefix} Đã commit.")
        if rows_affected > 0:
            logger.info(f"{log_prefix} Cập nhật hoàn tất. Rows affected: {rows_affected}.")
        else:
            logger.warning(f"{log_prefix} Không tìm thấy progress hoặc dữ liệu không đổi (0 hàng).")
    except sqlite3.Error as e:
        logger.error(f"{log_prefix} Lỗi database: {e}", exc_info=True)
        if should_commit and conn:
            try: conn.rollback(); logger.warning(f"{log_prefix} Đã rollback thay đổi do lỗi.")
            except Exception as rb_err: logger.error(f"{log_prefix} Lỗi khi rollback: {rb_err}")
        raise DatabaseError("Lỗi SQLite khi cập nhật progress.", original_exception=e)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi khác: {e}", exc_info=True)
        if should_commit and conn:
            try: conn.rollback(); logger.warning(f"{log_prefix} Đã rollback thay đổi do lỗi không mong muốn.")
            except Exception as rb_err: logger.error(f"{log_prefix} Lỗi khi rollback: {rb_err}")
        if isinstance(e, (DatabaseError, ValidationError)):
            raise e 
        raise DatabaseError("Lỗi không mong muốn khi cập nhật progress.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            try: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")
            except Exception as e_close: logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")
    return rows_affected
def get_progress_id_by_card(user_id, flashcard_id, conn=None):
    """
    Lấy progress_id của một bản ghi tiến trình cụ thể dựa trên user_id và flashcard_id.
    Args:
        user_id (int): ID (khóa chính) của người dùng.
        flashcard_id (int): ID của flashcard.
        conn (sqlite3.Connection): Kết nối DB có sẵn (tùy chọn).
    Returns:
        int: progress_id nếu tìm thấy.
        None: Nếu không tìm thấy bản ghi progress.
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
    """
    log_prefix = f"[GET_PROGRESS_ID|UserUID:{user_id}|Card:{flashcard_id}]" 
    internal_conn = None
    should_close_conn = False
    progress_id_result = None
    original_factory = None
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối DB nội bộ.")
            conn = internal_conn
            should_close_conn = True
            conn.row_factory = sqlite3.Row
        else:
            original_factory = conn.row_factory
            conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = 'SELECT "progress_id" FROM "UserFlashcardProgress" WHERE "user_id" = ? AND "flashcard_id" = ?'
        logger.debug(f"{log_prefix} Executing: {query.strip()} with ({user_id}, {flashcard_id})")
        cursor.execute(query, (user_id, flashcard_id))
        row = cursor.fetchone()
        if row:
            progress_id_result = row["progress_id"]
            logger.debug(f"{log_prefix} Tìm thấy progress_id: {progress_id_result}")
        else:
            logger.debug(f"{log_prefix} Không tìm thấy bản ghi progress.")
            progress_id_result = None 
        if original_factory is not None:
            conn.row_factory = original_factory
    except sqlite3.Error as e:
        logger.exception(f"{log_prefix} Lỗi SQLite: {e}")
        raise DatabaseError("Lỗi SQLite khi lấy progress ID.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm: {e}")
        if isinstance(e, DatabaseError):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi lấy progress ID.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
            try: conn.execute("SELECT 1"); conn.row_factory = original_factory
            except Exception: pass
        if should_close_conn and internal_conn:
            try: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối nội bộ.")
            except Exception as e_close: logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")
    return progress_id_result
def update_progress_by_card_id(user_id, flashcard_id, conn=None, **kwargs):
    """
    Cập nhật bản ghi tiến trình dựa trên user_id và flashcard_id.
    Args:
        user_id (int): ID (khóa chính) của người dùng.
        flashcard_id (int): ID của flashcard.
        conn (sqlite3.Connection): Kết nối DB có sẵn (tùy chọn).
        **kwargs: Các trường và giá trị cần cập nhật.
    Returns:
        int: Số hàng bị ảnh hưởng.
    Raises:
        ProgressNotFoundError: Nếu không tìm thấy bản ghi progress tương ứng.
        DatabaseError: Nếu có lỗi DB trong quá trình tìm hoặc cập nhật.
        ValidationError: Nếu kwargs rỗng hoặc giá trị không hợp lệ.
    """
    log_prefix = f"[UPDATE_PROG_BY_CARD|UserUID:{user_id}|Card:{flashcard_id}]" 
    logger.debug(f"{log_prefix} Tìm progress_id. Update data: {kwargs}")
    progress_id_to_update = get_progress_id_by_card(user_id, flashcard_id, conn=conn) 
    if progress_id_to_update is None:
        logger.warning(f"{log_prefix} Không tìm thấy progress để cập nhật.")
        raise ProgressNotFoundError(message=f"Không tìm thấy progress cho user ID {user_id} và card ID {flashcard_id}.")
    logger.debug(f"{log_prefix} Tìm thấy progress_id: {progress_id_to_update}. Gọi hàm cập nhật...")
    update_result = update_progress_by_id(progress_id_to_update, conn=conn, **kwargs)
    return update_result
def insert_new_progress(user_id, flashcard_id, current_timestamp=None, tz_offset_hours=DEFAULT_TIMEZONE_OFFSET, conn=None):
    """
    Chèn một bản ghi tiến trình học mới cho người dùng và flashcard cụ thể.
    Args:
        user_id (int): ID (khóa chính) của người dùng.
        flashcard_id (int): ID của flashcard.
        current_timestamp (int): Unix timestamp hiện tại (tùy chọn).
        tz_offset_hours (int): Độ lệch múi giờ để tính learned_date (tùy chọn).
        conn (sqlite3.Connection): Đối tượng kết nối DB có sẵn (tùy chọn).
    Returns:
        int: progress_id mới được tạo.
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
        DuplicateError: Nếu có lỗi ràng buộc dữ liệu khi chèn.
    """
    log_prefix = f"[INSERT_PROGRESS|UserUID:{user_id}|Card:{flashcard_id}]" 
    logger.debug(f"{log_prefix} Chèn progress mới...")
    internal_conn = None
    should_close_conn = False
    progress_id = None
    should_commit = False
    if current_timestamp is None:
        current_timestamp = int(time.time())
    today_ts = None
    try:
        user_tz = timezone(timedelta(hours=tz_offset_hours))
        now_dt = datetime.fromtimestamp(current_timestamp, user_tz)
        midnight_dt = datetime.combine(now_dt.date(), dt_time.min, tzinfo=user_tz)
        today_ts = int(midnight_dt.timestamp())
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi tính timestamp nửa đêm: {e}. Dùng current_timestamp.")
        today_ts = current_timestamp
    initial_due_time = current_timestamp + RETRY_INTERVAL_NEW_MIN * 60
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối DB nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True
        cursor = conn.cursor()
        insert_progress_query = """
            INSERT INTO "UserFlashcardProgress"
            ("user_id", "flashcard_id", "last_reviewed", "due_time", "review_count", "learned_date",
             "correct_streak", "correct_count", "incorrect_count", "lapse_count", "is_skipped")
            VALUES (?, ?, ?, ?, 0, ?, 0, 0, 0, 0, 0)
        """
        values = (user_id, flashcard_id, None, initial_due_time, today_ts) 
        logger.debug(f"{log_prefix} Executing INSERT progress: {values}")
        cursor.execute(insert_progress_query, values)
        progress_id = cursor.lastrowid
        if progress_id is None or progress_id <= 0:
            if should_commit and conn: conn.rollback()
            raise DatabaseError("Lỗi không xác định: Không nhận được lastrowid hợp lệ sau khi INSERT progress.")
        if should_commit:
            conn.commit()
            logger.info(f"{log_prefix} Đã chèn và commit progress ID: {progress_id}.")
        else:
            logger.info(f"{log_prefix} Đã chèn progress ID: {progress_id} trên conn ngoài.")
        return int(progress_id)
    except sqlite3.IntegrityError as e:
        logger.exception(f"{log_prefix} Lỗi Integrity khi insert progress: {e}")
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        raise DuplicateError("Lỗi ràng buộc dữ liệu khi chèn progress.", original_exception=e)
    except sqlite3.Error as e:
        logger.exception(f"{log_prefix} Lỗi SQLite khi insert progress: {e}")
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        raise DatabaseError("Lỗi SQLite khi chèn progress.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm insert progress: {e}")
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        if isinstance(e, (DatabaseError, DuplicateError)):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi chèn progress.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            try: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")
            except Exception as e_close: logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")
def get_daily_review_counts(user_id, set_id=None, tz_offset_hours=DEFAULT_TIMEZONE_OFFSET, conn=None):
    """
    Lấy số lượt ôn tập và số thẻ mới đã học trong ngày hôm nay cho người dùng.
    Args:
        user_id (int): ID (khóa chính) của người dùng.
        set_id (int): ID của bộ từ cụ thể để lọc (tùy chọn).
        tz_offset_hours (int): Độ lệch múi giờ của người dùng (tùy chọn).
        conn (sqlite3.Connection): Kết nối DB có sẵn (tùy chọn).
    Returns:
        tuple: (reviewed_count, learned_count)
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
    """
    log_prefix = f"[DAILY_COUNTS|UserUID:{user_id}|Set:{set_id}]" 
    internal_conn = None
    should_close_conn = False
    reviewed_count = 0
    learned_count = 0
    original_factory = None
    try:
        user_tz = timezone(timedelta(hours=tz_offset_hours))
        now_local = datetime.now(user_tz)
        today_start_dt = datetime.combine(now_local.date(), dt_time.min, tzinfo=user_tz)
        today_ts = int(today_start_dt.timestamp())
        logger.debug(f"{log_prefix} Timestamp bắt đầu ngày (TZ={tz_offset_hours}): {today_ts}")
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                 raise DatabaseError("Không thể tạo kết nối database.")
            conn = internal_conn
            should_close_conn = True
            conn.row_factory = sqlite3.Row
        else:
             original_factory = conn.row_factory
             conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        if set_id is None:
            review_query = 'SELECT COUNT(*) as count FROM "DailyReviewLog" WHERE "user_id" = ? AND "review_timestamp" >= ?'
            review_params = (user_id, today_ts)
        else:
            review_query = 'SELECT COUNT(*) as count FROM "DailyReviewLog" WHERE "user_id" = ? AND "review_timestamp" >= ? AND "set_id" = ?'
            review_params = (user_id, today_ts, set_id)
        cursor.execute(review_query, review_params)
        reviewed_row = cursor.fetchone()
        if reviewed_row:
            reviewed_count = reviewed_row['count']
        logger.debug(f"{log_prefix} Reviewed today: {reviewed_count}")
        if set_id is None:
            learn_query = 'SELECT COUNT(*) as count FROM "UserFlashcardProgress" WHERE "user_id" = ? AND "learned_date" = ?'
            learn_params = (user_id, today_ts)
        else:
            learn_query = 'SELECT COUNT(ufp.progress_id) as count FROM "UserFlashcardProgress" ufp JOIN "Flashcards" f ON ufp.flashcard_id = f.flashcard_id WHERE ufp."user_id" = ? AND ufp."learned_date" = ? AND f."set_id" = ?'
            learn_params = (user_id, today_ts, set_id)
        cursor.execute(learn_query, learn_params)
        learned_row = cursor.fetchone()
        if learned_row:
            learned_count = learned_row['count']
        logger.debug(f"{log_prefix} Learned today: {learned_count}")
        if original_factory is not None:
             conn.row_factory = original_factory
    except sqlite3.Error as e:
        logger.error(f"{log_prefix} Lỗi DB khi đếm review/learned: {e}", exc_info=True)
        raise DatabaseError("Lỗi SQLite khi đếm review/learned.", original_exception=e)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi khác khi đếm: {e}", exc_info=True)
        if isinstance(e, DatabaseError):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi đếm review/learned.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
            try: conn.execute("SELECT 1"); conn.row_factory = original_factory
            except Exception: pass
        if should_close_conn and internal_conn:
            try: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối nội bộ.")
            except Exception as e_close: logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")
    return reviewed_count, learned_count
def get_next_card_id_for_review(user_id, mode=DEFAULT_LEARNING_MODE, conn=None):
    """
    Xác định flashcard_id tiếp theo để ôn tập hoặc học mới dựa trên user_id và mode.
    Args:
        user_id (int): ID (khóa chính) của người dùng.
        mode (str): Chế độ học/ôn tập.
        conn (sqlite3.Connection): Kết nối DB có sẵn (tùy chọn).
    Returns:
        int: flashcard_id nếu tìm thấy thẻ phù hợp.
             Số âm của Unix timestamp lần có thẻ tiếp theo nếu không tìm thấy thẻ nào bây giờ.
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite khác xảy ra.
        UserNotFoundError: Nếu không tìm thấy user với user_id cung cấp.
        ValidationError: Nếu mode yêu cầu set_id nhưng không có set nào được chọn cho user.
    """
    now_timestamp = int(time.time())
    now_str = datetime.fromtimestamp(now_timestamp).strftime('%Y-%m-%d %H:%M:%S')
    log_prefix = f"[GET_NEXT_ID|UserUID:{user_id}|Mode:{mode}]" 
    logger.info(f"{log_prefix} [{now_str}] Bắt đầu tìm thẻ tiếp theo (bỏ qua skipped).")
    internal_conn = None
    should_close_conn = False
    next_card_id_or_ts = -now_timestamp 
    user_settings = {}
    original_factory = None
    modes_requiring_set = [
        MODE_SEQ_INTERSPERSED, MODE_SEQ_RANDOM_NEW, MODE_NEW_SEQUENTIAL,
        MODE_DUE_ONLY_RANDOM, MODE_REVIEW_HARDEST, MODE_CRAM_SET, MODE_NEW_RANDOM
    ]
    check_due_modes = [
        MODE_SEQ_INTERSPERSED, MODE_SEQ_RANDOM_NEW,
        MODE_DUE_ONLY_RANDOM, MODE_REVIEW_ALL_DUE
    ]
    check_new_modes = [
        MODE_SEQ_INTERSPERSED, MODE_SEQ_RANDOM_NEW,
        MODE_NEW_SEQUENTIAL, MODE_NEW_RANDOM
    ]
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể kết nối DB.")
            conn = internal_conn
            should_close_conn = True
        original_factory = conn.row_factory
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query_user_settings = """
            SELECT timezone_offset, current_set_id, daily_new_limit, user_role
            FROM Users WHERE user_id = ?
        """
        logger.debug(f"{log_prefix} Lấy cài đặt cho user_id: {user_id}")
        cursor.execute(query_user_settings, (user_id,))
        user_settings_row = cursor.fetchone()
        if not user_settings_row:
            raise UserNotFoundError(identifier=user_id) 
        user_settings = dict(user_settings_row)
        tz_offset_hours = user_settings.get("timezone_offset", DEFAULT_TIMEZONE_OFFSET)
        logger.debug(f"{log_prefix} Tìm thấy cài đặt user: TZ={tz_offset_hours}, SetID={user_settings.get('current_set_id')}, Limit={user_settings.get('daily_new_limit')}, Role={user_settings.get('user_role')}")
        target_set_id = None
        if mode in modes_requiring_set:
            target_set_id = user_settings.get("current_set_id")
            logger.debug(f"{log_prefix} Dùng current_set_id: {target_set_id}")
            if target_set_id is None:
                raise ValidationError(f"Chế độ '{mode}' yêu cầu chọn bộ từ.")
        due_flashcards = []
        next_due_time_overall = None
        if mode in check_due_modes:
            logger.debug(f"{log_prefix} Đang kiểm tra thẻ đến hạn (bỏ qua skipped)...")
            where_clause_due = 'ufp."user_id" = ? AND ufp."is_skipped" = 0 AND ufp."due_time" IS NOT NULL AND ufp."due_time" <= ?'
            params_due = [user_id, now_timestamp]
            if mode == MODE_REVIEW_ALL_DUE:
                query_due = f'SELECT ufp."flashcard_id", ufp."due_time" FROM "UserFlashcardProgress" ufp WHERE {where_clause_due}'
                logger.debug(f"{log_prefix} Lấy thẻ đến hạn TẤT CẢ bộ.")
            else:
                if target_set_id is None: raise ValidationError(f"Mode {mode} yêu cầu target_set_id.")
                query_due = f"""
                    SELECT ufp."flashcard_id", ufp."due_time"
                    FROM "UserFlashcardProgress" ufp JOIN "Flashcards" f ON ufp.flashcard_id = f.flashcard_id
                    WHERE {where_clause_due} AND f."set_id" = ?
                """
                params_due.append(target_set_id)
                logger.debug(f"{log_prefix} Lấy thẻ đến hạn từ bộ {target_set_id}.")
            cursor.execute(query_due, tuple(params_due))
            rows = cursor.fetchall()
            logger.debug(f"{log_prefix} Tìm thấy {len(rows)} thẻ đến hạn (chưa skip).")
            due_flashcards = [(row['flashcard_id'], row['due_time']) for row in rows]
            where_next_due = 'ufp."user_id" = ? AND ufp."is_skipped" = 0 AND ufp."due_time" IS NOT NULL'
            params_next_due = [user_id]
            if mode != MODE_REVIEW_ALL_DUE and target_set_id is not None:
                where_next_due += ' AND f."set_id" = ?'
                params_next_due.append(target_set_id)
                query_next_due = f'SELECT MIN(ufp."due_time") FROM "UserFlashcardProgress" ufp JOIN "Flashcards" f ON ufp.flashcard_id = f.flashcard_id WHERE {where_next_due}'
            else:
                query_next_due = f'SELECT MIN(ufp."due_time") FROM "UserFlashcardProgress" ufp WHERE {where_next_due}'
            cursor.execute(query_next_due, tuple(params_next_due))
            next_due_result = cursor.fetchone()
            next_due_time_overall = next_due_result[0] if next_due_result and next_due_result[0] is not None else None
            logger.debug(f"{log_prefix} Due time gần nhất (chưa skip): {next_due_time_overall}")
            if due_flashcards:
                chosen_card_id, _ = random.choice(due_flashcards)
                logger.info(f"{log_prefix} Chọn thẻ đến hạn ngẫu nhiên (chưa skip): {chosen_card_id}")
                next_card_id_or_ts = chosen_card_id
        if next_card_id_or_ts < 0 and mode in check_new_modes:
            logger.debug(f"{log_prefix} Không có thẻ đến hạn, kiểm tra thẻ mới...")
            if target_set_id is None: raise ValidationError(f"Mode {mode} yêu cầu target_set_id.")
            limit_reached = False
            user_role = user_settings.get('user_role', 'user')
            allowed_permissions = ROLE_PERMISSIONS.get(user_role, set())
            if HAS_UNLIMITED_NEW_CARDS not in allowed_permissions:
                logger.debug(f"{log_prefix} User '{user_role}' không có quyền học không giới hạn. Kiểm tra giới hạn...")
                daily_limit = user_settings.get("daily_new_limit", DAILY_LIMIT_USER)
                logger.debug(f"{log_prefix} Giới hạn hàng ngày: {daily_limit}")
                today_start_ts = None
                try:
                    user_tz_new = timezone(timedelta(hours=tz_offset_hours))
                    today_start_dt_new = datetime.combine(datetime.now(user_tz_new).date(), dt_time.min, tzinfo=user_tz_new)
                    today_start_ts = int(today_start_dt_new.timestamp())
                except Exception as tz_err:
                    logger.error(f"{log_prefix} Lỗi tính today_start_ts: {tz_err}. Dùng ước lượng.")
                    today_start_ts = now_timestamp - (now_timestamp % 86400) 
                if today_start_ts is not None:
                    query_new_count = 'SELECT COUNT(*) as count FROM "UserFlashcardProgress" WHERE "user_id" = ? AND "learned_date" = ?'
                    cursor.execute(query_new_count, (user_id, today_start_ts)) 
                    new_count_today_result = cursor.fetchone()
                    new_count_today = new_count_today_result['count'] if new_count_today_result else 0
                    logger.debug(f"{log_prefix} Thẻ mới đã học hôm nay: {new_count_today}")
                    if new_count_today >= daily_limit:
                        limit_reached = True
                        logger.info(f"{log_prefix} Đã đạt giới hạn thẻ mới ({new_count_today}/{daily_limit}).")
            if not limit_reached:
                order_by_new = 'ORDER BY f."flashcard_id" ASC' 
                if mode == MODE_SEQ_RANDOM_NEW or mode == MODE_NEW_RANDOM:
                    order_by_new = "ORDER BY RANDOM()"
                logger.debug(f"{log_prefix} Tìm thẻ mới ({'Tuần tự' if 'ASC' in order_by_new else 'Ngẫu nhiên'})...")
                query_new_card = f"""
                    SELECT f."flashcard_id" FROM "Flashcards" f
                    LEFT JOIN "UserFlashcardProgress" ufp ON f."flashcard_id" = ufp."flashcard_id" AND ufp."user_id" = ?
                    WHERE f."set_id" = ? AND ufp."progress_id" IS NULL
                    {order_by_new} LIMIT 1
                """
                cursor.execute(query_new_card, (user_id, target_set_id)) 
                new_card = cursor.fetchone()
                if new_card:
                    new_card_id = new_card['flashcard_id']
                    logger.info(f"{log_prefix} Tìm thấy thẻ mới: {new_card_id}")
                    next_card_id_or_ts = new_card_id
                else:
                    logger.info(f"{log_prefix} Không còn thẻ mới trong bộ {target_set_id}.")
        elif next_card_id_or_ts < 0 and mode == MODE_REVIEW_HARDEST:
            logger.debug(f"{log_prefix} Tìm thẻ khó nhất trong bộ {target_set_id}...")
            if target_set_id is None: raise ValidationError(f"Mode {mode} yêu cầu target_set_id.")
            query_hardest = """
                SELECT ufp.flashcard_id FROM UserFlashcardProgress ufp
                JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id
                WHERE ufp.user_id = ? AND f.set_id = ? AND ufp.is_skipped = 0
                ORDER BY ufp.incorrect_count DESC, RANDOM()
                LIMIT 1
            """
            cursor.execute(query_hardest, (user_id, target_set_id)) 
            hardest_card = cursor.fetchone()
            if hardest_card:
                next_card_id_or_ts = hardest_card['flashcard_id']
                logger.info(f"{log_prefix} Tìm thấy thẻ khó: {next_card_id_or_ts}")
            else:
                logger.info(f"{log_prefix} Không tìm thấy thẻ khó nào trong bộ {target_set_id}.")
        elif next_card_id_or_ts < 0 and mode == MODE_CRAM_SET:
            logger.debug(f"{log_prefix} Lấy thẻ ngẫu nhiên đã học trong bộ {target_set_id} (Cram)...")
            if target_set_id is None: raise ValidationError(f"Mode {mode} yêu cầu target_set_id.")
            query_cram_set = """
                SELECT ufp.flashcard_id FROM UserFlashcardProgress ufp
                JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id
                WHERE ufp.user_id = ? AND f.set_id = ? AND ufp.is_skipped = 0
                ORDER BY RANDOM()
                LIMIT 1
            """
            cursor.execute(query_cram_set, (user_id, target_set_id)) 
            cram_card = cursor.fetchone()
            if cram_card:
                next_card_id_or_ts = cram_card['flashcard_id']
                logger.info(f"{log_prefix} Tìm thấy thẻ cram theo bộ: {next_card_id_or_ts}")
            else:
                logger.info(f"{log_prefix} Không tìm thấy thẻ nào đã học trong bộ {target_set_id} để cram.")
        elif next_card_id_or_ts < 0 and mode == MODE_CRAM_ALL:
            logger.debug(f"{log_prefix} Lấy thẻ ngẫu nhiên đã học từ TẤT CẢ bộ (Cram)...")
            query_cram_all = """
                SELECT flashcard_id FROM UserFlashcardProgress
                WHERE user_id = ? AND is_skipped = 0
                ORDER BY RANDOM()
                LIMIT 1
            """
            cursor.execute(query_cram_all, (user_id,)) 
            cram_card_all = cursor.fetchone()
            if cram_card_all:
                next_card_id_or_ts = cram_card_all['flashcard_id']
                logger.info(f"{log_prefix} Tìm thấy thẻ cram tổng hợp: {next_card_id_or_ts}")
            else:
                logger.info(f"{log_prefix} Không tìm thấy thẻ nào đã học để cram tổng hợp.")
        if next_card_id_or_ts < 0:
            logger.info(f"{log_prefix} Không tìm thấy thẻ phù hợp cho mode '{mode}'. Tính toán thời gian chờ...")
            user_tz_wait = timezone(timedelta(hours=tz_offset_hours))
            now_local_wait = datetime.now(user_tz_wait)
            midnight_next_day_dt = datetime.combine( (now_local_wait + timedelta(days=1)).date(), dt_time.min, tzinfo=user_tz_wait)
            midnight_next_day_ts = int(midnight_next_day_dt.timestamp())
            wait_until_ts = next_due_time_overall if next_due_time_overall and next_due_time_overall > now_timestamp else midnight_next_day_ts
            wait_until_ts = max(wait_until_ts, now_timestamp + 60) 
            next_card_id_or_ts = -wait_until_ts
            logger.info(f"{log_prefix} Hết thẻ phù hợp. Thời gian chờ đến timestamp (âm): {next_card_id_or_ts}")
        if original_factory is not None:
            conn.row_factory = original_factory
    except (ValidationError, UserNotFoundError) as e_known: 
        logger.exception(f"{log_prefix} Lỗi Logic/Validation/UserNotFound: {e_known}")
        raise e_known 
    except sqlite3.Error as e_sql:
        logger.exception(f"{log_prefix} Lỗi SQLite không mong muốn: {e_sql}")
        raise DatabaseError("Lỗi SQLite khi tìm thẻ tiếp theo.", original_exception=e_sql)
    except Exception as e_unknown:
        logger.exception(f"{log_prefix} Lỗi không mong muốn: {e_unknown}")
        raise DatabaseError("Lỗi không mong muốn khi tìm thẻ tiếp theo.", original_exception=e_unknown)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
            try: conn.execute("SELECT 1"); conn.row_factory = original_factory
            except Exception: pass
        if should_close_conn and internal_conn:
            try: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")
            except Exception as e_close: logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")
    logger.info(f"{log_prefix} Kết quả cuối cùng trả về: {next_card_id_or_ts}")
    return next_card_id_or_ts