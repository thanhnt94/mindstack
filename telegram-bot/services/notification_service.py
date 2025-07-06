# File: flashcard-telegram-bot/services/notification_service.py
"""
Module chứa business logic cho việc lấy dữ liệu cần thiết để gửi
thông báo và nhắc nhở ôn tập định kỳ, bao gồm cả nhắc nhở không hoạt động.
(Sửa lần 2: Thêm hàm get_targeted_set_reminder_card cho thông báo ôn tập theo bộ tùy chọn,
             thêm hàm get_morning_brief_stats)
(Sửa lần 3: Sửa lỗi typo 'recently_not_notified_card_ids_in_set' thành 
             'recently_notified_card_ids_in_set' trong log message.)
(Sửa lần 4: Xóa bỏ hàm get_due_reminders_data.)
"""

import logging
import time
import random
from datetime import datetime 
from datetime import time as dt_time 
from datetime import timedelta
from datetime import timezone
import sqlite3

# Import từ các module khác (tuyệt đối)
from database.connection import database_connect
from database.query_stats import get_review_stats 
from utils.exceptions import DatabaseError
import config 
from config import (
    DEFAULT_TIMEZONE_OFFSET,
    # DUE_REMINDER_THRESHOLD, # <<< SỬA LẦN 4: XÓA IMPORT KHÔNG DÙNG
    SLEEP_START_HOUR,
    SLEEP_END_HOUR,
    NOTIFICATION_SET_REMINDER_MEMORY 
)

logger = logging.getLogger(__name__)

def _get_start_of_day(now_dt, tz_info):
    start_dt = datetime.combine(now_dt.date(), dt_time.min, tzinfo=tz_info)
    return int(start_dt.timestamp())

# <<< SỬA LẦN 4: XÓA BỎ HÀM get_due_reminders_data >>>
# def get_due_reminders_data():
#    # ... (logic cũ của hàm này) ...
#    pass
# <<< KẾT THÚC SỬA LẦN 4 >>>

def get_targeted_set_reminder_card(user_id, target_set_id, recently_notified_card_ids_in_set):
    """
    Lấy một thẻ ngẫu nhiên từ bộ thẻ mục tiêu của người dùng để gửi thông báo,
    cố gắng tránh lặp lại các thẻ đã thông báo gần đây cho bộ đó.
    """
    log_prefix = f"[SERVICE_GET_TARGETED_REMINDER|UserUID:{user_id}|Set:{target_set_id}]"
    logger.info(f"{log_prefix} Bắt đầu tìm thẻ từ bộ mục tiêu.")
    
    if not target_set_id:
        logger.warning(f"{log_prefix} Không có target_set_id.")
        return None

    conn = None
    try:
        conn = database_connect()
        if conn is None:
            raise DatabaseError("Không thể kết nối DB.")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query_learned_cards_in_set = """
            SELECT DISTINCT ufp.flashcard_id
            FROM UserFlashcardProgress ufp
            JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id
            WHERE ufp.user_id = ? AND f.set_id = ?
        """
        cursor.execute(query_learned_cards_in_set, (user_id, target_set_id))
        all_learned_in_set_rows = cursor.fetchall()
        
        if not all_learned_in_set_rows:
            logger.info(f"{log_prefix} Người dùng chưa học thẻ nào trong bộ {target_set_id}.")
            return None
        
        all_learned_ids_in_set = {row['flashcard_id'] for row in all_learned_in_set_rows if row and row['flashcard_id'] is not None}
        logger.debug(f"{log_prefix} Tổng số thẻ đã học trong bộ: {len(all_learned_ids_in_set)}")

        if not all_learned_ids_in_set: 
            return None

        candidate_ids_list = list(all_learned_ids_in_set) 
        if recently_notified_card_ids_in_set and isinstance(recently_notified_card_ids_in_set, list):
            candidate_ids_after_filter = list(all_learned_ids_in_set - set(recently_notified_card_ids_in_set))
            if candidate_ids_after_filter: 
                candidate_ids_list = candidate_ids_after_filter
                logger.debug(f"{log_prefix} Số thẻ ứng viên sau khi loại trừ ({len(recently_notified_card_ids_in_set)} thẻ gần đây): {len(candidate_ids_list)}")
            else:
                logger.debug(f"{log_prefix} Tất cả thẻ đã học trong bộ đều đã thông báo gần đây. Chọn từ pool gốc.")
        
        if not candidate_ids_list: 
             logger.warning(f"{log_prefix} Không có thẻ ứng viên nào để chọn.")
             return None

        selected_card_id = random.choice(candidate_ids_list)
        logger.info(f"{log_prefix} Chọn thẻ ID {selected_card_id} từ {len(candidate_ids_list)} ứng viên.")
        
        query_content = 'SELECT "notification_text", "back" FROM "Flashcards" WHERE "flashcard_id" = ?'
        cursor.execute(query_content, (selected_card_id,))
        card_content_row = cursor.fetchone()
        
        notification_content = None
        if card_content_row:
            notify_text_db = card_content_row['notification_text']
            back_text_db = card_content_row['back']
            if notify_text_db and notify_text_db.strip():
                notification_content = notify_text_db
            elif back_text_db and back_text_db.strip(): 
                notification_content = back_text_db
        
        if notification_content:
            logger.info(f"{log_prefix} Đã lấy nội dung cho thẻ {selected_card_id}.")
            return {'selected_card_id': selected_card_id, 'notification_content': notification_content}
        else:
            logger.warning(f"{log_prefix} Thẻ {selected_card_id} thiếu nội dung thông báo.")
            return None

    except sqlite3.Error as e_db:
        logger.error(f"{log_prefix} Lỗi SQLite: {e_db}", exc_info=True)
        raise DatabaseError("Lỗi SQLite khi lấy thẻ thông báo theo bộ.", original_exception=e_db)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        raise DatabaseError("Lỗi không mong muốn khi lấy thẻ thông báo theo bộ.", original_exception=e)
    finally:
        if conn:
            conn.close()

def get_morning_brief_stats(user_id):
    log_prefix = f"[SERVICE_GET_MORNING_STATS|UserUID:{user_id}]"
    logger.info(f"{log_prefix} Lấy thông số cho lời chào buổi sáng.")
    stats_for_brief = {}
    try:
        overall_stats = get_review_stats(user_id=user_id, set_id=None) 
        stats_for_brief['due_today_srs'] = overall_stats.get('course_due_total', 0)
        logger.debug(f"{log_prefix} Số thẻ SRS đến hạn hôm nay: {stats_for_brief['due_today_srs']}")
    except DatabaseError as e_db:
        logger.error(f"{log_prefix} Lỗi DB khi lấy stats: {e_db}")
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
    
    return stats_for_brief


def get_inactive_users_data():
    log_prefix = "[SERVICE_GET_INACTIVE]"
    inactive_users = []
    try:
        inactive_days = config.INACTIVITY_REMINDER_DAYS
        if not isinstance(inactive_days, int) or inactive_days <= 0:
            inactive_days = 3 
    except AttributeError:
         inactive_days = 3
    current_ts = int(time.time())
    threshold_ts = current_ts - (inactive_days * 86400) 
    logger.info("{} Tìm user không hoạt động kể từ timestamp: {} ({} ngày trước)".format(log_prefix, threshold_ts, inactive_days))
    conn = None
    try:
        conn = database_connect()
        if conn is None: raise DatabaseError("Không thể kết nối DB.")
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        query = """
            SELECT user_id, telegram_id, last_seen
            FROM Users
            WHERE last_seen IS NOT NULL
              AND last_seen < ?
              AND user_role != 'banned'
        """
        cursor.execute(query, (threshold_ts,))
        rows = cursor.fetchall()
        for row in rows:
            if row['telegram_id'] is not None:
                inactive_users.append({
                    'user_id': row['user_id'],
                    'telegram_id': row['telegram_id'],
                    'last_seen_ts': row['last_seen']
                })
        logger.info("{} Tìm thấy {} người dùng không hoạt động.".format(log_prefix, len(inactive_users)))
    except (sqlite3.Error, DatabaseError) as e_db:
        logger.error("{} Lỗi DB khi tìm người dùng không hoạt động: {}".format(log_prefix, e_db), exc_info=True)
        return [] 
    except Exception as e:
        logger.error("{} Lỗi không mong muốn: {}".format(log_prefix, e), exc_info=True)
        return [] 
    finally:
        if conn: conn.close()
    return inactive_users
