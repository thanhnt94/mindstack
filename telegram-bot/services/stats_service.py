# File: flashcard-telegram-bot/services/stats_service.py
"""
Module chứa business logic liên quan đến việc lấy và xử lý dữ liệu thống kê.
(Sửa lần 3: Cập nhật get_personal_stats_summary để tính toán "Tổng kết về thẻ"
             và đảm bảo "Tổng điểm" được lấy đúng, thêm các thông số thẻ theo kỳ.)
"""
import logging
import sqlite3
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from collections import defaultdict
import numpy as np 

from database.connection import database_connect
from database.query_stats import (
    get_review_stats,
    get_period_leaderboard,
    count_new_cards_in_period, 
    count_reviews_in_period,
    get_daily_activity_history_by_user,
    get_total_reviews_all_time 
)
from database.query_user import get_user_by_telegram_id, get_user_by_id 
from config import DEFAULT_TIMEZONE_OFFSET, LEADERBOARD_LIMIT
from utils.exceptions import DatabaseError, UserNotFoundError

logger = logging.getLogger(__name__)

def _get_start_of_day(now_dt, tz_info):
    start_dt = datetime.combine(now_dt.date(), dt_time.min, tzinfo=tz_info)
    return int(start_dt.timestamp())

def _get_start_of_week(now_dt, tz_info):
    start_of_day = datetime.combine(now_dt.date(), dt_time.min, tzinfo=tz_info)
    start_of_week_dt = start_of_day - timedelta(days=now_dt.isoweekday() - 1) 
    return int(start_of_week_dt.timestamp())

def _get_start_of_month(now_dt, tz_info):
    start_of_month_dt = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(start_of_month_dt.timestamp())

def get_daily_stats(user_id_db): 
    log_prefix = f"[SERVICE_GET_TODAY_STATS|UserDBID:{user_id_db}]"
    logger.info(f"{log_prefix} Bắt đầu lấy dữ liệu thống kê hôm nay.")
    stats_result = { 
        'learned_today': 0, 'reviews_today': 0, 'score_today': 0, 
        'total_score': 0, 
        'total_learned_distinct': 0, 'total_due': 0, 
        'today_start_dt': None, 'error': None, 'learned_sets': 0 
    }
    conn = None; user_info = {}
    try:
        conn = database_connect();
        if conn is None: raise DatabaseError("Không thể kết nối DB.")
        conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        
        user_info_from_db = get_user_by_id(user_id_db, conn=conn) 
        if not user_info_from_db: raise UserNotFoundError(identifier=user_id_db)
        user_info = user_info_from_db
            
        stats_result['total_score'] = user_info.get('score', 0) 
        tz_offset_hours = user_info.get('timezone_offset', DEFAULT_TIMEZONE_OFFSET); 
        user_tz = timezone(timedelta(hours=tz_offset_hours))
        now_local = datetime.now(user_tz); today_start_ts = _get_start_of_day(now_local, user_tz)
        stats_result['today_start_dt'] = datetime.fromtimestamp(today_start_ts, user_tz)
        
        cursor.execute("SELECT COUNT(*) as count FROM UserFlashcardProgress WHERE user_id = ? AND learned_date = ?", (user_id_db, today_start_ts)); 
        learned_today_result = cursor.fetchone(); 
        stats_result['learned_today'] = learned_today_result['count'] if learned_today_result else 0
        
        cursor.execute("SELECT COUNT(*) as count, SUM(score_change) as total_score_change FROM DailyReviewLog WHERE user_id = ? AND review_timestamp >= ?", (user_id_db, today_start_ts)); 
        review_score_today_result = cursor.fetchone()
        stats_result['reviews_today'] = review_score_today_result['count'] if review_score_today_result else 0
        stats_result['score_today'] = review_score_today_result['total_score_change'] if review_score_today_result and review_score_today_result['total_score_change'] is not None else 0
        
        overall_stats = get_review_stats(user_id_db, conn=conn); 
        stats_result['total_learned_distinct'] = overall_stats.get('learned_distinct', 0); 
        stats_result['total_due'] = overall_stats.get('course_due_total', 0); 
        stats_result['learned_sets'] = overall_stats.get('learned_sets', 0)
        
        return stats_result
    except sqlite3.Error as e_sql: logger.exception(f"{log_prefix} Lỗi SQLite: {e_sql}"); raise DatabaseError("Lỗi SQLite khi lấy thống kê ngày.", original_exception=e_sql)
    except UserNotFoundError as e_user: logger.error(f"{log_prefix} Lỗi UserNotFound: {e_user}"); raise e_user
    except Exception as e: logger.exception(f"{log_prefix} Lỗi không mong muốn: {e}"); raise DatabaseError("Lỗi không mong muốn khi lấy thống kê ngày.", original_exception=e)
    finally:
        if conn: conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB.")

def get_stats_per_set(user_id):
    # Giữ nguyên logic
    log_prefix = f"[SERVICE_GET_PER_SET_STATS|UserUID:{user_id}]"
    logger.info(f"{log_prefix} Bắt đầu lấy dữ liệu thống kê theo bộ.")
    conn = None; per_set_results = []
    try:
        conn = database_connect();
        if conn is None: raise DatabaseError("Không thể kết nối DB.")
        conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        query_learned_sets = "SELECT DISTINCT vs.set_id, vs.title FROM UserFlashcardProgress ufp JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id JOIN VocabularySets vs ON f.set_id = vs.set_id WHERE ufp.user_id = ? ORDER BY vs.title COLLATE NOCASE"
        cursor.execute(query_learned_sets, (user_id,)); learned_sets_info = [dict(row) for row in cursor.fetchall()]
        if not learned_sets_info: return []
        learned_set_ids = [s['set_id'] for s in learned_sets_info]; set_stats_map = {s['set_id']: {'title': s['title'], 'total_count': 0, 'learned_count': 0} for s in learned_sets_info}
        if not learned_set_ids : return [] 
        placeholders_sets = ','.join('?' * len(learned_set_ids))
        cursor.execute(f"SELECT set_id, COUNT(*) as total_count FROM Flashcards WHERE set_id IN ({placeholders_sets}) GROUP BY set_id", learned_set_ids)
        for row in cursor.fetchall():
            if row['set_id'] in set_stats_map: set_stats_map[row['set_id']]['total_count'] = row['total_count']
        query_learned_count = f"SELECT f.set_id, COUNT(DISTINCT ufp.flashcard_id) as learned_count FROM UserFlashcardProgress ufp JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id WHERE ufp.user_id = ? AND f.set_id IN ({placeholders_sets}) GROUP BY f.set_id"
        cursor.execute(query_learned_count, (user_id, *learned_set_ids)) 
        for row in cursor.fetchall():
            if row['set_id'] in set_stats_map: set_stats_map[row['set_id']]['learned_count'] = row['learned_count']
        per_set_results = [{'set_id': sid, **sdata} for sid, sdata in set_stats_map.items()]
        return per_set_results
    except sqlite3.Error as db_err: logger.exception(f"{log_prefix} Lỗi SQLite: {db_err}"); raise DatabaseError("Lỗi SQLite khi lấy thống kê theo bộ.", original_exception=db_err)
    except Exception as e: logger.exception(f"{log_prefix} Lỗi trong hàm: {e}"); raise DatabaseError("Lỗi không mong muốn khi lấy thống kê theo bộ.", original_exception=e)
    finally:
        if conn: conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB.")

def get_personal_stats_summary(user_id_db, user_timezone_offset):
    """
    Tổng hợp các thông tin thống kê cá nhân cho người dùng.
    Sửa lần 3: Thêm "Tổng kết về thẻ" và đảm bảo "Tổng điểm" đúng.
    """
    log_prefix = f"[SERVICE_GET_PERSONAL_SUMMARY|UserDBID:{user_id_db}]"
    logger.info(f"{log_prefix} Bắt đầu tổng hợp thống kê cá nhân.")
    
    summary = {
        'today_stats': {}, 'set_progress': [], 'daily_activity_history': {}, 
        'score_this_week': 0, 'score_this_month': 0, 'error': None,
        'avg_score_per_day': 0.0, 'avg_new_cards_per_day': 0.0, 'avg_reviews_per_day': 0.0,
        'total_active_days': 0,
        'cards_learned_total_all_time': 0, 'cards_reviewed_total_all_time': 0,
        'cards_learned_this_month': 0, 'cards_reviewed_this_month': 0,
        'cards_learned_this_week': 0, 'cards_reviewed_this_week': 0,
        'cards_learned_today': 0, 'cards_reviewed_today': 0,
        'overall_total_score': 0,
        'cards_remaining_in_started_sets': 0,
        'total_cards_in_started_sets': 0
    }
    conn_main = None 
    try:
        today_stats_data = get_daily_stats(user_id_db) 
        summary['today_stats'] = today_stats_data
        summary['overall_total_score'] = today_stats_data.get('total_score', 0)
        summary['cards_learned_today'] = today_stats_data.get('learned_today', 0)
        summary['cards_reviewed_today'] = today_stats_data.get('reviews_today', 0)
        summary['cards_learned_total_all_time'] = today_stats_data.get('total_learned_distinct',0) 
        summary['learned_sets_count'] = today_stats_data.get('learned_sets', 0) # Số bộ đã học

        set_progress_raw = get_stats_per_set(user_id_db)
        summary['set_progress'] = set_progress_raw
        
        total_cards_in_started_sets = 0
        if isinstance(set_progress_raw, list):
            for s_prog in set_progress_raw:
                total_cards_in_started_sets += s_prog.get('total_count', 0)
        summary['total_cards_in_started_sets'] = total_cards_in_started_sets
        summary['cards_remaining_in_started_sets'] = max(0, total_cards_in_started_sets - summary['cards_learned_total_all_time'])


        daily_activity_raw = get_daily_activity_history_by_user(user_id_db, user_timezone_offset)
        summary['daily_activity_history'] = daily_activity_raw 
        
        conn_main = database_connect(); 
        if conn_main is None: raise DatabaseError("Không thể kết nối DB cho personal summary.")
        conn_main.row_factory = sqlite3.Row; cursor = conn_main.cursor()
        
        user_tz = timezone(timedelta(hours=user_timezone_offset)); now_local = datetime.now(user_tz)
        
        start_of_this_week_ts = _get_start_of_week(now_local, user_tz); end_of_this_week_ts = int(now_local.timestamp()) 
        cursor.execute("SELECT SUM(score_change) FROM DailyReviewLog WHERE user_id = ? AND review_timestamp >= ? AND review_timestamp < ?", (user_id_db, start_of_this_week_ts, end_of_this_week_ts + 1)); # Sửa: < end + 1 để bao gồm cả end
        score_week_row = cursor.fetchone()
        summary['score_this_week'] = score_week_row[0] if score_week_row and score_week_row[0] is not None else 0
        summary['cards_learned_this_week'] = count_new_cards_in_period(user_id_db, start_of_this_week_ts, end_of_this_week_ts + 1, conn=conn_main)
        summary['cards_reviewed_this_week'] = count_reviews_in_period(user_id_db, start_of_this_week_ts, end_of_this_week_ts + 1, conn=conn_main)
        
        start_of_this_month_ts = _get_start_of_month(now_local, user_tz); end_of_this_month_ts = int(now_local.timestamp())
        cursor.execute("SELECT SUM(score_change) FROM DailyReviewLog WHERE user_id = ? AND review_timestamp >= ? AND review_timestamp < ?", (user_id_db, start_of_this_month_ts, end_of_this_month_ts + 1)); 
        score_month_row = cursor.fetchone()
        summary['score_this_month'] = score_month_row[0] if score_month_row and score_month_row[0] is not None else 0
        summary['cards_learned_this_month'] = count_new_cards_in_period(user_id_db, start_of_this_month_ts, end_of_this_month_ts + 1, conn=conn_main)
        summary['cards_reviewed_this_month'] = count_reviews_in_period(user_id_db, start_of_this_month_ts, end_of_this_month_ts + 1, conn=conn_main)

        summary['cards_reviewed_total_all_time'] = get_total_reviews_all_time(user_id_db, conn=conn_main)

        if daily_activity_raw and not daily_activity_raw.get('error'):
            total_active_days = len(daily_activity_raw)
            summary['total_active_days'] = total_active_days
            if total_active_days > 0:
                total_score_hist = sum(stats.get('score', 0) for stats in daily_activity_raw.values())
                total_new_hist = sum(stats.get('new', 0) for stats in daily_activity_raw.values())
                total_reviewed_hist = sum(stats.get('reviewed', 0) for stats in daily_activity_raw.values())
                summary['avg_score_per_day'] = round(total_score_hist / total_active_days, 1)
                summary['avg_new_cards_per_day'] = round(total_new_hist / total_active_days, 1)
                summary['avg_reviews_per_day'] = round(total_reviewed_hist / total_active_days, 1)
        logger.info(f"{log_prefix} Trung bình: Điểm {summary['avg_score_per_day']}, Mới {summary['avg_new_cards_per_day']}, Ôn {summary['avg_reviews_per_day']} / {summary['total_active_days']} ngày.")

    except DatabaseError as e_db: logger.error(f"{log_prefix} Lỗi DatabaseError chính: {e_db}"); summary['error'] = str(e_db)
    except sqlite3.Error as e_sql: logger.error(f"{log_prefix} Lỗi SQLite chính: {e_sql}", exc_info=True); summary['error'] = f"Lỗi SQLite: {e_sql}"
    except Exception as e_main: logger.error(f"{log_prefix} Lỗi không mong muốn chính: {e_main}", exc_info=True); summary['error'] = f"Lỗi không mong muốn: {e_main}"
    finally:
        if conn_main: conn_main.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB chính.")
            
    logger.info(f"{log_prefix} Hoàn tất tổng hợp thống kê cá nhân: {summary}") # Log toàn bộ summary để kiểm tra
    return summary

def get_daily_leaderboard(limit=LEADERBOARD_LIMIT):
    # Giữ nguyên
    log_prefix = "[SERVICE_LB_DAILY]"; logger.info(f"{log_prefix} Lấy leaderboard ngày (limit={limit}).")
    enriched_leaderboard = []; conn = None
    try:
        tz_info = timezone(timedelta(hours=DEFAULT_TIMEZONE_OFFSET)); now_dt = datetime.now(tz_info)
        start_ts = _get_start_of_day(now_dt, tz_info); end_ts = int(now_dt.timestamp())
        conn = database_connect(); conn.row_factory = sqlite3.Row
        base_leaderboard = get_period_leaderboard(start_ts, end_ts + 1, limit, conn=conn) # Sửa: end_ts + 1
        for user_data in base_leaderboard:
            user_id = user_data.get('user_id')
            if not user_id: continue
            enriched_data = dict(user_data)
            try: stats = get_review_stats(user_id, conn=conn); enriched_data['learned_sets'] = stats.get('learned_sets', 0)
            except Exception: enriched_data['learned_sets'] = 'Lỗi'
            enriched_data['new_cards_period'] = count_new_cards_in_period(user_id, start_ts, end_ts + 1, conn=conn) # Sửa: end_ts + 1
            enriched_data['reviews_period'] = count_reviews_in_period(user_id, start_ts, end_ts + 1, conn=conn) # Sửa: end_ts + 1
            enriched_leaderboard.append(enriched_data)
        return enriched_leaderboard
    except Exception as e: logger.error(f"{log_prefix} Lỗi: {e}", exc_info=True); return []
    finally:
        if conn: conn.close()

def get_weekly_leaderboard(limit=LEADERBOARD_LIMIT):
    # Giữ nguyên
    log_prefix = "[SERVICE_LB_WEEKLY]"; logger.info(f"{log_prefix} Lấy leaderboard tuần (limit={limit}).")
    enriched_leaderboard = []; conn = None
    try:
        tz_info = timezone(timedelta(hours=DEFAULT_TIMEZONE_OFFSET)); now_dt = datetime.now(tz_info)
        start_ts = _get_start_of_week(now_dt, tz_info); end_ts = int(now_dt.timestamp())
        conn = database_connect(); conn.row_factory = sqlite3.Row
        base_leaderboard = get_period_leaderboard(start_ts, end_ts + 1, limit, conn=conn) # Sửa
        for user_data in base_leaderboard:
            user_id = user_data.get('user_id')
            if not user_id: continue
            enriched_data = dict(user_data)
            try: stats = get_review_stats(user_id, conn=conn); enriched_data['learned_sets'] = stats.get('learned_sets', 0)
            except Exception: enriched_data['learned_sets'] = 'Lỗi'
            enriched_data['new_cards_period'] = count_new_cards_in_period(user_id, start_ts, end_ts + 1, conn=conn) # Sửa
            enriched_data['reviews_period'] = count_reviews_in_period(user_id, start_ts, end_ts + 1, conn=conn) # Sửa
            enriched_leaderboard.append(enriched_data)
        return enriched_leaderboard
    except Exception as e: logger.error(f"{log_prefix} Lỗi: {e}", exc_info=True); return []
    finally:
        if conn: conn.close()

def get_monthly_leaderboard(limit=LEADERBOARD_LIMIT):
    # Giữ nguyên
    log_prefix = "[SERVICE_LB_MONTHLY]"; logger.info(f"{log_prefix} Lấy leaderboard tháng (limit={limit}).")
    enriched_leaderboard = []; conn = None
    try:
        tz_info = timezone(timedelta(hours=DEFAULT_TIMEZONE_OFFSET)); now_dt = datetime.now(tz_info)
        start_ts = _get_start_of_month(now_dt, tz_info); end_ts = int(now_dt.timestamp())
        conn = database_connect(); conn.row_factory = sqlite3.Row
        base_leaderboard = get_period_leaderboard(start_ts, end_ts + 1, limit, conn=conn) # Sửa
        for user_data in base_leaderboard:
            user_id = user_data.get('user_id')
            if not user_id: continue
            enriched_data = dict(user_data)
            try: stats = get_review_stats(user_id, conn=conn); enriched_data['learned_sets'] = stats.get('learned_sets', 0)
            except Exception: enriched_data['learned_sets'] = 'Lỗi'
            enriched_data['new_cards_period'] = count_new_cards_in_period(user_id, start_ts, end_ts + 1, conn=conn) # Sửa
            enriched_data['reviews_period'] = count_reviews_in_period(user_id, start_ts, end_ts + 1, conn=conn) # Sửa
            enriched_leaderboard.append(enriched_data)
        return enriched_leaderboard
    except Exception as e: logger.error(f"{log_prefix} Lỗi: {e}", exc_info=True); return []
    finally:
        if conn: conn.close()

