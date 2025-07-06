# File: flashcard-telegram-bot/jobs.py
"""
Module chứa các hàm callback được thực thi bởi JobQueue của bot.
(Sửa lần 4: Trong run_periodic_reminders_job, thêm kiểm tra last_seen của user.)
(Sửa lần 5: Sử dụng hằng số NOTIFICATION_MIN_INACTIVITY_MIN từ config 
             cho kiểm tra last_seen trong run_periodic_reminders_job.)
"""
import logging
import asyncio
import time
import html
import sqlite3 
from datetime import datetime 
from datetime import timedelta
from datetime import timezone
from datetime import time as dt_time 

from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram.ext import Application
from telegram.ext import CallbackContext 
from telegram.error import Forbidden
from telegram.error import BadRequest
from telegram.error import TelegramError

from services.notification_service import (
    get_targeted_set_reminder_card, 
    get_inactive_users_data,
    get_morning_brief_stats 
)
from database.query_user import get_user_by_telegram_id, update_user_by_telegram_id 
from database.connection import database_connect
from utils.exceptions import DatabaseError
from utils.exceptions import UserNotFoundError
import config # Import config để sử dụng hằng số

logger = logging.getLogger(__name__)


async def run_periodic_reminders_job(context):
    """
    Hàm chạy định kỳ, gửi thông báo ôn tập thẻ ngẫu nhiên từ bộ thẻ người dùng đã chọn.
    Sửa lần 5: Sử dụng config.NOTIFICATION_MIN_INACTIVITY_MIN.
    """
    log_prefix = "[JOB_RUNNER_PERIODIC_TARGETED]"
    logger.info("{} Bắt đầu chạy job gửi thông báo ôn tập theo bộ.".format(log_prefix))
    if not context or not isinstance(context, CallbackContext):
        logger.error("{} Context không hợp lệ.".format(log_prefix))
        return
    
    app = context.bot_data.get('application')
    if not app or not isinstance(app, Application):
        logger.error("{} Không tìm thấy application trong bot_data.".format(log_prefix))
        return
    bot = app.bot
    application_user_data = app.user_data 
    if bot is None or application_user_data is None:
         logger.error("{} Không thể lấy bot hoặc application_user_data.".format(log_prefix))
         return

    conn = None
    eligible_users_for_targeted_reminder = [] 
    
    try:
        conn = database_connect()
        if conn is None:
            raise DatabaseError("Không thể kết nối DB lấy user cho periodic targeted.")
        conn.row_factory = sqlite3.Row 
        cursor_users = conn.cursor()
        current_timestamp = int(time.time())
        
        query_enabled_users = """
            SELECT user_id, telegram_id, notification_interval_minutes,
                   last_notification_sent_time, notification_target_set_id, 
                   timezone_offset, last_seen 
            FROM Users 
            WHERE is_notification_enabled = 1 AND notification_target_set_id IS NOT NULL
        """
        cursor_users.execute(query_enabled_users)
        all_qualifying_users = [dict(row) for row in cursor_users.fetchall()]
        logger.info("{} Tìm thấy {} user đã bật TB và chọn bộ.".format(log_prefix, len(all_qualifying_users)))

        # Sửa lần 5: Sử dụng hằng số từ config
        inactivity_threshold_seconds = config.NOTIFICATION_MIN_INACTIVITY_MIN * 60

        for user_row in all_qualifying_users:
            user_id_db = user_row.get('user_id')
            telegram_id_db = user_row.get('telegram_id')
            interval_minutes = user_row.get('notification_interval_minutes')
            last_sent_ts = user_row.get('last_notification_sent_time')
            target_set_id_db = user_row.get('notification_target_set_id')
            tz_offset = user_row.get('timezone_offset', config.DEFAULT_TIMEZONE_OFFSET)
            last_seen_ts = user_row.get('last_seen') 

            user_log_prefix_check = "{}[CheckUserUID:{},TG:{},Set:{}]".format(log_prefix, user_id_db, telegram_id_db, target_set_id_db)

            if not all([user_id_db, telegram_id_db, interval_minutes, target_set_id_db]):
                logger.warning(f"{user_log_prefix_check} Thiếu thông tin cần thiết, bỏ qua.")
                continue
            if interval_minutes <= 0:
                logger.debug(f"{user_log_prefix_check} Khoảng cách không hợp lệ ({interval_minutes}), bỏ qua.")
                continue
            
            if last_seen_ts is not None:
                time_since_last_seen = current_timestamp - last_seen_ts
                if time_since_last_seen < inactivity_threshold_seconds:
                    logger.info(f"{user_log_prefix_check} Người dùng đang hoạt động (last_seen {time_since_last_seen}s < {inactivity_threshold_seconds}s). Bỏ qua thông báo.")
                    continue 
            else: 
                logger.debug(f"{user_log_prefix_check} last_seen là NULL, tiếp tục kiểm tra các điều kiện khác.")

            try:
                user_local_tz = timezone(timedelta(hours=tz_offset))
                now_user_local_time = datetime.now(user_local_tz)
                current_user_hour = now_user_local_time.hour
                is_user_sleep_time = False
                if config.SLEEP_START_HOUR > config.SLEEP_END_HOUR: 
                    if current_user_hour >= config.SLEEP_START_HOUR or current_user_hour < config.SLEEP_END_HOUR:
                        is_user_sleep_time = True
                else: 
                    if config.SLEEP_START_HOUR <= current_user_hour < config.SLEEP_END_HOUR:
                        is_user_sleep_time = True
                if is_user_sleep_time:
                    logger.debug(f"{user_log_prefix_check} Đang trong giờ ngủ của user (Local Hour: {current_user_hour}). Bỏ qua.")
                    continue
            except Exception as e_sleep_check:
                logger.error(f"{user_log_prefix_check} Lỗi kiểm tra giờ ngủ user: {e_sleep_check}. Tiếp tục gửi.")

            is_time_to_send = True 
            if last_sent_ts is not None:
                time_since_last = current_timestamp - last_sent_ts
                required_interval_seconds = interval_minutes * 60
                if time_since_last < required_interval_seconds:
                    is_time_to_send = False 
            
            if is_time_to_send:
                eligible_users_for_targeted_reminder.append({
                    'user_id': user_id_db,
                    'telegram_id': telegram_id_db,
                    'target_set_id': target_set_id_db
                })
                logger.debug(f"{user_log_prefix_check} Đủ điều kiện gửi thông báo cho bộ.")
        
        logger.info("{} Có {} người dùng đủ điều kiện nhận TB theo bộ (sau khi check last_seen và sleep).".format(log_prefix, len(eligible_users_for_targeted_reminder)))

    except (sqlite3.Error, DatabaseError) as e:
        logger.error("{} Lỗi DB/User khi lấy danh sách user cho TB theo bộ: {}".format(log_prefix, e), exc_info=True)
        if conn: conn.close()
        return 
    finally:
        if conn: conn.close()

    if not eligible_users_for_targeted_reminder:
        logger.info("{} Không có người dùng nào cần gửi thông báo theo bộ.".format(log_prefix))
        return

    # Phần gửi thông báo giữ nguyên logic ...
    successful_sends = 0; failed_sends = 0
    current_timestamp_for_update = int(time.time()) 
    for user_to_notify in eligible_users_for_targeted_reminder:
        user_id = user_to_notify.get('user_id'); telegram_id = user_to_notify.get('telegram_id'); target_set_id = user_to_notify.get('target_set_id')
        user_job_log_prefix = "{}[NotifyUserUID:{},TG:{},Set:{}]".format(log_prefix, user_id, telegram_id, target_set_id)
        user_specific_data = application_user_data.get(telegram_id, {}); history_key = f'notified_in_set_{target_set_id}'
        recently_notified_in_set = user_specific_data.get(history_key, [])
        if not isinstance(recently_notified_in_set, list): recently_notified_in_set = []
        reminder_card_data = None
        try: reminder_card_data = get_targeted_set_reminder_card(user_id, target_set_id, recently_notified_in_set)
        except Exception as e_get_card: logger.error(f"{user_job_log_prefix} Lỗi get_targeted_set_reminder_card: {e_get_card}", exc_info=True); failed_sends += 1; continue 
        if not reminder_card_data: logger.info(f"{user_job_log_prefix} Không có thẻ phù hợp."); continue
        selected_card_id = reminder_card_data.get('selected_card_id'); notification_content_raw = reminder_card_data.get('notification_content')
        if not selected_card_id or not notification_content_raw: logger.warning(f"{user_job_log_prefix} Dữ liệu thẻ lỗi: {reminder_card_data}"); failed_sends += 1; continue
        message_sent_successfully = False; text_to_send = ""; parse_mode = 'Markdown' 
        try: content_processed = html.unescape(notification_content_raw); text_to_send = "💡 **{}**".format(content_processed) 
        except Exception as e_format: text_to_send = "💡 {}".format(notification_content_raw); parse_mode = None 
        try:
            await bot.send_message(chat_id=telegram_id, text=text_to_send, parse_mode=parse_mode)
            logger.info("{} Đã gửi TB thẻ {} bộ {}.".format(user_job_log_prefix, selected_card_id, target_set_id)); successful_sends += 1; message_sent_successfully = True
        except Forbidden: failed_sends += 1; logger.warning("{} Bot bị chặn.".format(user_job_log_prefix))
        except BadRequest as e_br: failed_sends += 1; logger.error("{} Lỗi BadRequest gửi: {} (Nội dung: '{}', Mode: {})".format(user_job_log_prefix, e_br, text_to_send, parse_mode))
        except TelegramError as e_tg: failed_sends += 1; logger.error("{} Lỗi Telegram khác: {}".format(user_job_log_prefix, e_tg))
        except Exception as e_send_unknown: failed_sends += 1; logger.error("{} Lỗi gửi TB: {}".format(user_job_log_prefix, e_send_unknown), exc_info=True)
        if message_sent_successfully:
            try: update_user_by_telegram_id(telegram_id, last_notification_sent_time=current_timestamp_for_update); logger.info("{} Đã cập nhật last_notification_sent_time.".format(user_job_log_prefix))
            except Exception as e_db_update: logger.error("{} Lỗi DB cập nhật last_sent_time: {}".format(user_job_log_prefix, e_db_update))
            try:
                 if not isinstance(application_user_data.get(telegram_id), dict): application_user_data[telegram_id] = {} 
                 user_specific_data_for_history = application_user_data[telegram_id]
                 current_history_for_set = user_specific_data_for_history.get(history_key, [])
                 if not isinstance(current_history_for_set, list): current_history_for_set = []
                 current_history_for_set.insert(0, selected_card_id)
                 current_history_for_set = current_history_for_set[:config.NOTIFICATION_SET_REMINDER_MEMORY] 
                 user_specific_data_for_history[history_key] = current_history_for_set
                 logger.debug("{} Đã cập nhật user_data history cho bộ {}: {}".format(user_job_log_prefix, target_set_id, current_history_for_set))
            except Exception as e_user_data_hist: logger.error("{} Lỗi cập nhật user_data history cho bộ: {}".format(user_job_log_prefix, e_user_data_hist), exc_info=True)
        await asyncio.sleep(config.BROADCAST_SEND_DELAY) 
    logger.info("{} Kết thúc job TB theo bộ. Thành công: {}, Thất bại: {}.".format(log_prefix, successful_sends, failed_sends))

async def run_morning_brief_job(context):
    # Giữ nguyên logic
    log_prefix = "[JOB_RUNNER_MORNING_BRIEF]"; logger.info("{} Bắt đầu job gửi Lời chào buổi sáng.".format(log_prefix))
    if not context or not isinstance(context, CallbackContext): logger.error("{} Context không hợp lệ.".format(log_prefix)); return
    app = context.bot_data.get('application')
    if not app or not isinstance(app, Application): logger.error("{} Không tìm thấy application trong bot_data.".format(log_prefix)); return
    bot = app.bot
    if bot is None: logger.error("{} Không thể lấy bot từ application.".format(log_prefix)); return
    conn = None; users_to_greet = []
    try:
        conn = database_connect();
        if conn is None: raise DatabaseError("Không thể kết nối DB lấy user cho morning brief.")
        conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        query_users = "SELECT user_id, telegram_id, timezone_offset, last_morning_brief_sent_date FROM Users WHERE enable_morning_brief = 1 AND user_role != 'banned'"
        cursor.execute(query_users); all_eligible_users = [dict(row) for row in cursor.fetchall()]
        logger.info("{} Tìm thấy {} user đã bật Lời chào buổi sáng.".format(log_prefix, len(all_eligible_users)))
        today_date_str_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        for user_row in all_eligible_users:
            user_id_db = user_row.get('user_id'); telegram_id_db = user_row.get('telegram_id'); tz_offset = user_row.get('timezone_offset', config.DEFAULT_TIMEZONE_OFFSET); last_sent_date_db = user_row.get('last_morning_brief_sent_date')
            user_log_prefix_check = "{}[CheckUserUID:{},TG:{}]".format(log_prefix, user_id_db, telegram_id_db)
            if not user_id_db or not telegram_id_db: logger.warning(f"{user_log_prefix_check} Thiếu user_id hoặc telegram_id, bỏ qua."); continue
            if last_sent_date_db == today_date_str_utc: logger.debug(f"{user_log_prefix_check} Đã gửi lời chào hôm nay ({last_sent_date_db}), bỏ qua."); continue
            try:
                user_local_tz = timezone(timedelta(hours=tz_offset)); now_user_local_time = datetime.now(user_local_tz); current_user_hour = now_user_local_time.hour
                if not (config.MORNING_BRIEF_LOCAL_START_HOUR <= current_user_hour < config.MORNING_BRIEF_LOCAL_END_HOUR):
                    logger.debug(f"{user_log_prefix_check} Giờ địa phương ({current_user_hour}h) không trong khoảng ({config.MORNING_BRIEF_LOCAL_START_HOUR}h-{config.MORNING_BRIEF_LOCAL_END_HOUR}h)."); continue
            except Exception as e_time_check: logger.error(f"{user_log_prefix_check} Lỗi kiểm tra giờ địa phương: {e_time_check}. Bỏ qua."); continue
            users_to_greet.append({'user_id': user_id_db, 'telegram_id': telegram_id_db})
            logger.debug(f"{user_log_prefix_check} Đủ điều kiện nhận lời chào.")
        logger.info("{} Có {} người dùng đủ điều kiện nhận Lời chào buổi sáng.".format(log_prefix, len(users_to_greet)))
    except (sqlite3.Error, DatabaseError) as e_db_greet: logger.error("{} Lỗi DB khi lấy danh sách user cho lời chào: {}".format(log_prefix, e_db_greet), exc_info=True);
    finally:
        if conn: conn.close()
    if not users_to_greet: logger.info("{} Không có ai để gửi Lời chào buổi sáng.".format(log_prefix)); return
    successful_sends = 0; failed_sends = 0
    for user_data in users_to_greet:
        user_id = user_data.get('user_id'); telegram_id = user_data.get('telegram_id'); user_job_log_prefix = "{}[GreetUserUID:{},TG:{}]".format(log_prefix, user_id, telegram_id)
        greeting_text = "Chào buổi sáng tốt lành! ☀️\n"; stats_text_parts = []
        try:
            brief_stats = get_morning_brief_stats(user_id)
            due_today = brief_stats.get('due_today_srs', 0)
            if due_today > 0: stats_text_parts.append(f"Hôm nay bạn có **{due_today}** thẻ cần ôn tập.")
            else: stats_text_parts.append("Bạn không có thẻ nào đến hạn ôn tập hôm nay. Tuyệt vời!")
        except Exception as e_get_stats: stats_text_parts.append("Không thể tải thông tin học tập của bạn lúc này.")
        final_message = greeting_text + "\n".join(stats_text_parts) + "\n\nChúc bạn một ngày học tập hiệu quả! 💪"
        keyboard = [[InlineKeyboardButton("📚 Bắt đầu học ngay!", callback_data="handle_callback_back_to_main")]]; reply_markup = InlineKeyboardMarkup(keyboard)
        message_sent_successfully = False
        try:
            await bot.send_message(chat_id=telegram_id, text=final_message, reply_markup=reply_markup, parse_mode='Markdown')
            successful_sends += 1; message_sent_successfully = True
        except Forbidden: failed_sends += 1; logger.warning(f"{user_job_log_prefix} Bot bị chặn.")
        except BadRequest as e_br_greet: failed_sends += 1; logger.error(f"{user_job_log_prefix} Lỗi BadRequest: {e_br_greet}")
        except TelegramError as e_tg_greet: failed_sends += 1; logger.error(f"{user_job_log_prefix} Lỗi Telegram: {e_tg_greet}")
        except Exception as e_send_greet_unknown: failed_sends += 1; logger.error(f"{user_job_log_prefix} Lỗi gửi lời chào: {e_send_greet_unknown}", exc_info=True)
        if message_sent_successfully:
            try: update_user_by_telegram_id(telegram_id, last_morning_brief_sent_date=today_date_str_utc) 
            except Exception as e_db_update_greet: logger.error(f"{user_job_log_prefix} Lỗi DB cập nhật last_morning_brief_sent_date: {e_db_update_greet}")
        await asyncio.sleep(config.BROADCAST_SEND_DELAY)
    logger.info("{} Kết thúc job Lời chào buổi sáng. Thành công: {}, Thất bại: {}.".format(log_prefix, successful_sends, failed_sends))

async def run_inactivity_reminder_job(context):
    # Giữ nguyên logic
    log_prefix = "[JOB_RUNNER_INACTIVE]"; logger.info("{} Bắt đầu job nhắc nhở không hoạt động.".format(log_prefix))
    if not context or not isinstance(context, CallbackContext): return
    app = context.bot_data.get('application')
    if not app or not isinstance(app, Application): return
    bot = app.bot
    if bot is None: return
    inactive_users_data = []
    try: inactive_users_data = get_inactive_users_data() 
    except Exception as e_get: return 
    if not inactive_users_data: return
    successful_sends = 0; failed_sends = 0; inactive_days_config = config.INACTIVITY_REMINDER_DAYS
    for user_data in inactive_users_data:
        telegram_id = user_data.get('telegram_id'); user_id = user_data.get('user_id') 
        if not telegram_id: failed_sends += 1; continue
        user_job_log_prefix = "{}[UserUID:{},TG:{}]".format(log_prefix, user_id, telegram_id)
        reminder_text = "👋 Đã {} ngày rồi bạn chưa ôn bài trên Flashcard Bot. Hãy quay lại luyện tập để không quên kiến thức nhé!".format(inactive_days_config)
        keyboard = [[InlineKeyboardButton("📚 Học bài ngay!", callback_data="handle_callback_back_to_main")]]; reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await bot.send_message(chat_id=telegram_id, text=reminder_text, reply_markup=reply_markup)
            successful_sends += 1
        except Forbidden: failed_sends += 1
        except (BadRequest, TelegramError): failed_sends += 1
        except Exception: failed_sends += 1
        await asyncio.sleep(config.BROADCAST_SEND_DELAY) 
    logger.info("{} Kết thúc job nhắc nhở không hoạt động. Thành công: {}, Thất bại: {}.".format(log_prefix, successful_sends, failed_sends))

