# File: flashcard-telegram-bot/database/query_stats.py
"""
Module chứa các hàm truy vấn dữ liệu thống kê, lịch sử học tập và bảng xếp hạng.
(Sửa lần 1: Thêm hàm get_cumulative_score_history)
(Sửa lần 2: Thêm hàm get_total_reviews_all_time)
"""
import sqlite3
import logging
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from collections import defaultdict

from database.connection import database_connect
from config import (
    DEFAULT_TIMEZONE_OFFSET,
    LEADERBOARD_LIMIT
)
from utils.exceptions import DatabaseError, UserNotFoundError

logger = logging.getLogger(__name__)

def get_review_stats(user_id, flashcard_id=None, set_id=None, conn=None):
    # Giữ nguyên logic
    log_prefix = f"[get_review_stats|UserUID:{user_id}|Card:{flashcard_id}|Set:{set_id}]"
    internal_conn = None; should_close_conn = False; original_factory = None
    stats = {
        'reviewed_count': 0, 'correct_total': 0, 'correct_streak': 0,
        'total_count': 0, 'learned_total': 0, 'due_total': 0,
        'learned_distinct': 0, 'learned_sets': 0, 'course_total_count': 0,
        'course_due_total': 0,
    }
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None: raise DatabaseError("Không thể tạo kết nối DB nội bộ.")
            conn = internal_conn; should_close_conn = True
            conn.row_factory = sqlite3.Row
        else:
             original_factory = conn.row_factory; conn.row_factory = sqlite3.Row
        cursor = conn.cursor(); now_ts = int(time.time())
        if flashcard_id is not None:
            query_card = "SELECT review_count, correct_count, correct_streak FROM UserFlashcardProgress WHERE user_id = ? AND flashcard_id = ?"
            cursor.execute(query_card, (user_id, flashcard_id))
            row_card = cursor.fetchone()
            if row_card: stats['reviewed_count']=row_card['review_count'] or 0; stats['correct_total']=row_card['correct_count'] or 0; stats['correct_streak']=row_card['correct_streak'] or 0
        if set_id is not None:
            cursor.execute("SELECT COUNT(flashcard_id) as count FROM Flashcards WHERE set_id = ?", (set_id,))
            row_set_total = cursor.fetchone(); stats['total_count'] = row_set_total['count'] if row_set_total else 0
            query_user_set_stats = """
                SELECT COUNT(CASE WHEN ufp.user_id = ? THEN ufp.flashcard_id END) as learned_in_set,
                       COUNT(CASE WHEN ufp.user_id = ? AND ufp.due_time IS NOT NULL AND ufp.due_time <= ? THEN ufp.flashcard_id END) as due_in_set
                FROM Flashcards f LEFT JOIN UserFlashcardProgress ufp ON f.flashcard_id = ufp.flashcard_id AND ufp.user_id = ?
                WHERE f.set_id = ?"""
            cursor.execute(query_user_set_stats, (user_id, user_id, now_ts, user_id, set_id))
            row_user_set = cursor.fetchone()
            if row_user_set: stats['learned_total'] = row_user_set['learned_in_set'] or 0; stats['due_total'] = row_user_set['due_in_set'] or 0
        cursor.execute("SELECT COUNT(flashcard_id) as total_system_cards FROM Flashcards")
        row_system_cards = cursor.fetchone(); stats['course_total_count'] = row_system_cards['total_system_cards'] if row_system_cards else 0
        query_user_overall = """
            SELECT COUNT(DISTINCT ufp.flashcard_id) AS distinct_learned_cards,
                   COUNT(CASE WHEN ufp.due_time IS NOT NULL AND ufp.due_time <= ? THEN 1 END) AS total_due_cards_for_user,
                   COUNT(DISTINCT f.set_id) AS distinct_learned_sets
            FROM UserFlashcardProgress ufp JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id
            WHERE ufp.user_id = ?"""
        cursor.execute(query_user_overall, (now_ts, user_id))
        row_overall = cursor.fetchone()
        if row_overall: 
            stats['learned_distinct'] = row_overall['distinct_learned_cards'] or 0
            stats['course_due_total'] = row_overall['total_due_cards_for_user'] or 0
            stats['learned_sets'] = row_overall['distinct_learned_sets'] or 0
        if original_factory is not None and conn.row_factory != original_factory : conn.row_factory = original_factory
        return stats
    except sqlite3.Error as e: logger.exception(f"{log_prefix} Lỗi DB: {e}"); raise DatabaseError("Lỗi SQLite khi lấy thống kê.", original_exception=e)
    except Exception as e: logger.exception(f"{log_prefix} Lỗi khác: {e}"); raise DatabaseError("Lỗi không mong muốn khi lấy thống kê.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn and conn.row_factory != original_factory:
             try: conn.row_factory = original_factory
             except Exception: pass
        if should_close_conn and internal_conn:
            try: internal_conn.close()
            except Exception as e_close: logger.error(f"{log_prefix} Lỗi đóng kết nối: {e_close}")

def get_daily_activity_history_by_user(user_id, tz_offset_hours=DEFAULT_TIMEZONE_OFFSET):
    # Giữ nguyên logic
    log_prefix = f"[DAILY_STATS_HISTORY|UserUID:{user_id}]"
    daily_stats = defaultdict(lambda: {'score': 0, 'new': 0, 'reviewed': 0}); conn = None
    try:
        user_tz = timezone(timedelta(hours=tz_offset_hours)); conn = database_connect()
        if conn is None: raise DatabaseError("Không thể tạo kết nối DB.")
        conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        query_new = "SELECT learned_date FROM UserFlashcardProgress WHERE user_id = ? AND learned_date IS NOT NULL"
        cursor.execute(query_new, (user_id,)); new_card_logs = cursor.fetchall()
        for log_row in new_card_logs:
            try:
                learned_timestamp = log_row['learned_date']
                if learned_timestamp: learned_dt_local = datetime.fromtimestamp(learned_timestamp, user_tz); date_str = learned_dt_local.strftime('%Y-%m-%d'); daily_stats[date_str]['new'] += 1
            except Exception as e_lc: logger.error(f"{log_prefix} Lỗi xử lý learned_date {learned_timestamp}: {e_lc}", exc_info=False); continue
        query_review = "SELECT review_timestamp, score_change FROM DailyReviewLog WHERE user_id = ? ORDER BY review_timestamp ASC"
        cursor.execute(query_review, (user_id,)); review_logs = cursor.fetchall()
        for log_row in review_logs:
            try:
                review_timestamp = log_row['review_timestamp']; score_change = log_row['score_change'] if log_row['score_change'] is not None else 0
                if review_timestamp: review_dt_local = datetime.fromtimestamp(review_timestamp, user_tz); date_str = review_dt_local.strftime('%Y-%m-%d'); daily_stats[date_str]['score'] += int(score_change); daily_stats[date_str]['reviewed'] += 1
            except Exception as e_rc: logger.error(f"{log_prefix} Lỗi xử lý review_timestamp {review_timestamp}: {e_rc}", exc_info=False); continue
        return dict(daily_stats)
    except sqlite3.Error as e_sql: logger.exception(f"{log_prefix} Lỗi DB: {e_sql}"); raise DatabaseError("Lỗi SQLite khi lấy lịch sử hoạt động.", original_exception=e_sql)
    except Exception as e_other: logger.exception(f"{log_prefix} Lỗi khác: {e_other}"); raise DatabaseError("Lỗi không mong muốn khi lấy lịch sử hoạt động.", original_exception=e_other)
    finally:
        if conn: conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối.")

def get_cumulative_score_history(user_id_db, tz_offset_hours=DEFAULT_TIMEZONE_OFFSET):
    # Giữ nguyên logic
    log_prefix = f"[CUMULATIVE_SCORE_HISTORY|UserDBID:{user_id_db}]"
    logger.info(f"{log_prefix} Bắt đầu lấy lịch sử điểm tích lũy.")
    daily_score_changes = defaultdict(int); cumulative_scores_by_date = {}; conn = None
    try:
        conn = database_connect();
        if conn is None: raise DatabaseError("Không thể kết nối DB.")
        conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        query_log = "SELECT review_timestamp, score_change FROM DailyReviewLog WHERE user_id = ? ORDER BY review_timestamp ASC"
        cursor.execute(query_log, (user_id_db,)); logs = cursor.fetchall()
        if not logs: return {}
        user_tz = timezone(timedelta(hours=tz_offset_hours))
        for log_entry in logs:
            timestamp = log_entry['review_timestamp']; score_change = log_entry['score_change'] if log_entry['score_change'] is not None else 0
            if timestamp is None: continue
            try:
                local_dt = datetime.fromtimestamp(timestamp, user_tz); date_str = local_dt.strftime('%Y-%m-%d')
                daily_score_changes[date_str] += int(score_change)
            except Exception as e_time: logger.warning(f"{log_prefix} Lỗi chuyển đổi timestamp {timestamp}: {e_time}"); continue
        if not daily_score_changes: return {}
        sorted_dates = sorted(daily_score_changes.keys())
        cursor.execute("SELECT score FROM Users WHERE user_id = ?", (user_id_db,)); user_score_row = cursor.fetchone()
        final_actual_score = user_score_row['score'] if user_score_row and user_score_row['score'] is not None else 0
        temp_cumulative_from_log = 0
        for date_str in sorted_dates:
            temp_cumulative_from_log += daily_score_changes[date_str]
            cumulative_scores_by_date[date_str] = temp_cumulative_from_log 
        if cumulative_scores_by_date: 
            last_logged_date = sorted_dates[-1]
            score_offset = final_actual_score - cumulative_scores_by_date[last_logged_date]
            adjusted_cumulative_scores = {date_str: cum_score + score_offset for date_str, cum_score in cumulative_scores_by_date.items()}
            return adjusted_cumulative_scores
        else: return {}
    except sqlite3.Error as e_sql: logger.error(f"{log_prefix} Lỗi SQLite: {e_sql}", exc_info=True); return {}
    except DatabaseError as e_db: logger.error(f"{log_prefix} Lỗi Database: {e_db}", exc_info=True); return {}
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); return {}
    finally:
        if conn: conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB.")

# Sửa lần 2: Thêm hàm get_total_reviews_all_time
def get_total_reviews_all_time(user_id_db, conn=None):
    """
    Lấy tổng số lượt ôn tập từ trước đến nay của người dùng.
    """
    log_prefix = f"[GET_TOTAL_REVIEWS|UserDBID:{user_id_db}]"
    internal_conn = None; should_close_conn = False; total_reviews = 0
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None: raise DatabaseError("Không thể tạo kết nối DB nội bộ.")
            conn = internal_conn; should_close_conn = True
        
        cursor = conn.cursor() # Không cần row_factory vì chỉ lấy COUNT
        query = "SELECT COUNT(log_id) FROM DailyReviewLog WHERE user_id = ?"
        cursor.execute(query, (user_id_db,))
        result = cursor.fetchone()
        total_reviews = result[0] if result and result[0] is not None else 0
        logger.debug(f"{log_prefix} Tổng lượt ôn tập: {total_reviews}")
        return total_reviews
    except sqlite3.Error as e_sql:
        logger.error(f"{log_prefix} Lỗi SQLite: {e_sql}", exc_info=True)
        raise DatabaseError("Lỗi SQLite khi lấy tổng lượt ôn tập.", original_exception=e_sql)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        raise DatabaseError("Lỗi không mong muốn khi lấy tổng lượt ôn tập.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            try: internal_conn.close()
            except Exception: pass


# Các hàm leaderboard giữ nguyên
def get_leaderboard(limit=LEADERBOARD_LIMIT, conn=None):
    log_prefix = f"[GET_LEADERBOARD|Limit:{limit}]"; logger.info(f"{log_prefix} Lấy leaderboard mọi lúc.")
    internal_conn = None; should_close_conn = False; leaderboard_data = []; original_factory = None
    try:
        if conn is None:
            internal_conn = database_connect();
            if internal_conn is None: raise DatabaseError("Không thể tạo kết nối DB nội bộ.")
            conn = internal_conn; should_close_conn = True; conn.row_factory = sqlite3.Row
        else:
             original_factory = conn.row_factory; conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = 'SELECT user_id, telegram_id, score FROM Users WHERE score > 0 ORDER BY score DESC LIMIT ?'
        cursor.execute(query, (limit,))
        top_users_rows = cursor.fetchall()
        leaderboard_data = [dict(row) for row in top_users_rows] 
        if original_factory is not None and conn.row_factory != original_factory: conn.row_factory = original_factory
        return leaderboard_data
    except sqlite3.Error as e: logger.exception(f"{log_prefix} Lỗi DB: {e}"); raise DatabaseError("Lỗi SQLite khi lấy bảng xếp hạng.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm: {e}")
        if isinstance(e, DatabaseError): raise e
        raise DatabaseError("Lỗi không mong muốn khi lấy bảng xếp hạng.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn and conn.row_factory != original_factory:
             try: conn.row_factory = original_factory
             except Exception: pass
        if should_close_conn and internal_conn:
             try: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối nội bộ.")
             except Exception as e_close: logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")

def get_period_leaderboard(start_timestamp, end_timestamp, limit=LEADERBOARD_LIMIT, conn=None):
    log_prefix = f"[GET_PERIOD_LEADERBOARD|Start:{start_timestamp}|End:{end_timestamp}|Limit:{limit}]"
    logger.info(f"{log_prefix} Bắt đầu lấy leaderboard theo kỳ.")
    leaderboard_data = []; internal_conn = None; should_close_conn = False; original_factory = None
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None: raise DatabaseError("Không thể tạo kết nối DB nội bộ.")
            conn = internal_conn; should_close_conn = True; conn.row_factory = sqlite3.Row
        else:
            original_factory = conn.row_factory; conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = """
            SELECT l.user_id, u.telegram_id, SUM(l.score_change) as period_score
            FROM DailyReviewLog l JOIN Users u ON l.user_id = u.user_id
            WHERE l.review_timestamp >= ? AND l.review_timestamp < ? AND l.score_change != 0
            GROUP BY l.user_id, u.telegram_id HAVING period_score > 0
            ORDER BY period_score DESC LIMIT ?;
        """
        params = (start_timestamp, end_timestamp, limit) 
        cursor.execute(query, params)
        rows = cursor.fetchall()
        leaderboard_data = [dict(row) for row in rows] 
        logger.info(f"{log_prefix} Tìm thấy {len(leaderboard_data)} users trong leaderboard kỳ này.")
        if original_factory is not None and conn.row_factory != original_factory: conn.row_factory = original_factory
        return leaderboard_data
    except sqlite3.Error as e_sql: logger.exception(f"{log_prefix} Lỗi SQLite: {e_sql}"); raise DatabaseError("Lỗi SQLite khi lấy leaderboard theo kỳ.", original_exception=e_sql)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi không mong muốn: {e}")
        if isinstance(e, DatabaseError): raise e
        raise DatabaseError("Lỗi không mong muốn khi lấy leaderboard theo kỳ.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn and conn.row_factory != original_factory:
            try: conn.row_factory = original_factory
            except Exception: pass
        if should_close_conn and internal_conn:
            try: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")
            except Exception as e_close: logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")

def count_new_cards_in_period(user_id, start_ts, end_ts, conn=None):
    log_prefix = f"[COUNT_NEW_CARDS|UID:{user_id}|{start_ts}-{end_ts}]"
    internal_conn = None; should_close_conn = False; count = 0
    try:
        if conn is None:
            internal_conn = database_connect();
            if internal_conn is None: raise DatabaseError("Không thể tạo kết nối DB.")
            conn = internal_conn; should_close_conn = True
        cursor = conn.cursor()
        query = "SELECT COUNT(progress_id) FROM UserFlashcardProgress WHERE user_id = ? AND learned_date >= ? AND learned_date < ?"
        cursor.execute(query, (user_id, start_ts, end_ts))
        result = cursor.fetchone(); count = result[0] if result else 0
        logger.debug(f"{log_prefix} Số thẻ mới: {count}")
        return count
    except sqlite3.Error as e_sql: logger.error(f"{log_prefix} Lỗi SQLite: {e_sql}", exc_info=True); return 0 
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); return 0
    finally:
        if should_close_conn and internal_conn:
            try: internal_conn.close()
            except Exception: pass

def count_reviews_in_period(user_id, start_ts, end_ts, conn=None):
    log_prefix = f"[COUNT_REVIEWS|UID:{user_id}|{start_ts}-{end_ts}]"
    internal_conn = None; should_close_conn = False; count = 0
    try:
        if conn is None:
            internal_conn = database_connect();
            if internal_conn is None: raise DatabaseError("Không thể tạo kết nối DB.")
            conn = internal_conn; should_close_conn = True
        cursor = conn.cursor()
        query = "SELECT COUNT(log_id) FROM DailyReviewLog WHERE user_id = ? AND review_timestamp >= ? AND review_timestamp < ?"
        cursor.execute(query, (user_id, start_ts, end_ts))
        result = cursor.fetchone(); count = result[0] if result else 0
        logger.debug(f"{log_prefix} Số lượt review: {count}")
        return count
    except sqlite3.Error as e_sql: logger.error(f"{log_prefix} Lỗi SQLite: {e_sql}", exc_info=True); return 0
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); return 0
    finally:
        if should_close_conn and internal_conn:
            try: internal_conn.close()
            except Exception: pass
