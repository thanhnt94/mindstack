# File: flashcard-telegram-bot/main.py
"""
Điểm khởi chạy chính (Entry Point) cho Telegram Flashcard Bot.
Khởi tạo ứng dụng, đăng ký các handlers và chạy bot bất đồng bộ.
Sử dụng hệ thống đăng ký handler module hóa.
Đã cập nhật danh sách lệnh bot.
(Sửa lần 2: Thêm lên lịch cho run_morning_brief_job)
(Sửa lần 3: Xóa bỏ run_due_reminders_job)
"""
import logging
import asyncio
from datetime import datetime, timedelta, timezone 
from datetime import time as dt_time 
import sys
import os

# Sử dụng import tuyệt đối
from telegram import Update
from telegram import Bot
from telegram import BotCommand
from telegram.ext import Application
from telegram.ext import ApplicationBuilder

import config
from config import BOT_TOKEN

# Import các module handlers
from handlers import nav_core
from handlers import learning_session
from handlers import mode_selection
from handlers import set_management
from handlers import data_import_upload
from handlers import data_import_update
from handlers import data_export
from handlers import notes
from handlers import audio_review
from handlers import settings
from handlers import notifications
from handlers import stats
from handlers import nav_admin
from handlers import user_management
from handlers import cache
from handlers import broadcast
from handlers import reporting
# Import các hàm job
from jobs import (
    run_periodic_reminders_job,
    # run_due_reminders_job, # <<< SỬA LẦN 3: XÓA IMPORT
    run_inactivity_reminder_job,
    run_morning_brief_job 
)

logger = logging.getLogger(__name__)

def register_all_handlers(app): 
    """
    Đăng ký tất cả các handlers từ các module handler con.
    Sửa lần 3: Xóa bỏ lên lịch cho run_due_reminders_job.
    """
    logger.info("Đăng ký handlers từ các module (ưu tiên ConversationHandlers)...")

    # --- Handlers Cốt lõi và ConversationHandlers ---
    if hasattr(nav_core, 'register_handlers'): nav_core.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong nav_core")
    if hasattr(notes, 'register_handlers'): notes.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong notes")
    if hasattr(data_import_upload, 'register_handlers'): data_import_upload.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong data_import_upload")
    if hasattr(data_import_update, 'register_handlers'): data_import_update.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong data_import_update")
    if hasattr(user_management, 'register_handlers'): user_management.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong user_management")
    if hasattr(broadcast, 'register_handlers'): broadcast.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong broadcast")
    if hasattr(cache, 'register_handlers'): cache.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong cache")
    if hasattr(reporting, 'register_handlers'): reporting.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong reporting")

    # --- Các Handlers Chức năng khác ---
    if hasattr(learning_session, 'register_handlers'): learning_session.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong learning_session")
    if hasattr(mode_selection, 'register_handlers'): mode_selection.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong mode_selection")
    if hasattr(set_management, 'register_handlers'): set_management.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong set_management")
    if hasattr(data_export, 'register_handlers'): data_export.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong data_export")
    if hasattr(audio_review, 'register_handlers'): audio_review.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong audio_review")
    if hasattr(settings, 'register_handlers'): settings.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong settings")
    if hasattr(notifications, 'register_handlers'): notifications.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong notifications")
    if hasattr(stats, 'register_handlers'): stats.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong stats")
    if hasattr(nav_admin, 'register_handlers'): nav_admin.register_handlers(app)
    else: logger.error("!!! Thiếu register_handlers trong nav_admin")

    # --- Error Handler ---
    if hasattr(nav_core, 'error_handler'):
        app.add_error_handler(nav_core.error_handler)
        logger.info("Đã đăng ký error_handler.")
    else:
        logger.error("!!! Không tìm thấy hàm error_handler trong module nav_core!")

    # --- Lên lịch Jobs ---
    job_queue = app.job_queue
    if job_queue:
        # Job thông báo thẻ ôn tập theo bộ (Periodic Targeted Reminder)
        job_queue.run_repeating(
            run_periodic_reminders_job, 
            interval=timedelta(minutes=config.PERIODIC_REMINDER_INTERVAL_MIN), 
            first=timedelta(seconds=20), 
            name="FlashcardPeriodicTargetedReminderJob" 
        )
        logger.info(f"Đã lên lịch chạy job gửi thông báo thẻ theo bộ ({config.PERIODIC_REMINDER_INTERVAL_MIN} phút/lần).")

        # <<< SỬA LẦN 3: XÓA BỎ LÊN LỊCH CHO run_due_reminders_job >>>
        # # Job nhắc nhở thẻ đến hạn (Due Card Reminder)
        # try:
        #     run_hour_utc_due = config.DUE_REMINDER_DAILY_HOUR_UTC
        #     # ... (logic cũ của due reminder job) ...
        # except Exception as e_schedule_due:
        #     # ... (log lỗi cũ) ...
        logger.info("Đã xóa bỏ việc lên lịch cho Due Reminder Job (thay bằng Morning Brief).")
        # <<< KẾT THÚC SỬA LẦN 3 >>>

        # Lên lịch cho Morning Brief Job
        try:
            run_hour_utc_morning = config.MORNING_BRIEF_JOB_HOUR_UTC
            if not (0 <= run_hour_utc_morning <= 23):
                logger.error(f"Giá trị MORNING_BRIEF_JOB_HOUR_UTC ({run_hour_utc_morning}) không hợp lệ. Dùng 1 giờ UTC.")
                run_hour_utc_morning = 1
            
            time_to_run_morning = dt_time(hour=run_hour_utc_morning, minute=1, second=0, tzinfo=timezone.utc) 
            job_queue.run_daily(
                run_morning_brief_job,
                time=time_to_run_morning,
                name="FlashcardMorningBriefJob"
            )
            try:
                now_server_local_morning = datetime.now().astimezone()
                today_server_local_morning = now_server_local_morning.date()
                potential_run_utc_morning = datetime(today_server_local_morning.year, today_server_local_morning.month, today_server_local_morning.day, run_hour_utc_morning, 1, 0, tzinfo=timezone.utc)
                if potential_run_utc_morning < datetime.now(timezone.utc): 
                    potential_run_utc_morning += timedelta(days=1)
                first_run_local_display_morning = potential_run_utc_morning.astimezone(now_server_local_morning.tzinfo)
                logger.info(f"Đã lên lịch Morning Brief Job chạy HÀNG NGÀY vào {run_hour_utc_morning}:01:00 UTC. Lần chạy tiếp theo dự kiến (giờ server): {first_run_local_display_morning.strftime('%Y-%m-%d %H:%M:%S %Z')}.")
            except Exception as e_log_time_morning:
                 logger.warning(f"Không thể tính toán thời gian hiển thị local cho Morning Brief Job: {e_log_time_morning}. Job vẫn được lên lịch vào {run_hour_utc_morning}:01:00 UTC hàng ngày.")
        except Exception as e_schedule_morning:
            logger.error(f"Lỗi khi lên lịch Morning Brief Job hàng ngày: {e_schedule_morning}", exc_info=True)
        
        # Job nhắc nhở không hoạt động
        try:
            check_interval_hours = max(1, config.INACTIVITY_CHECK_INTERVAL_HOURS)
            job_queue.run_repeating(
                run_inactivity_reminder_job,
                interval=timedelta(hours=check_interval_hours),
                first=timedelta(minutes=10), 
                name="FlashcardInactivityReminderJob"
            )
            logger.info(f"Đã lên lịch chạy job nhắc nhở không hoạt động mỗi {check_interval_hours} giờ.")
        except Exception as e_schedule_inactive:
            logger.error(f"Lỗi khi lên lịch Inactivity Reminder Job: {e_schedule_inactive}", exc_info=True)
    else:
         logger.warning("JobQueue không khả dụng. Không thể lên lịch các tác vụ định kỳ.")

    logger.info("Đăng ký handlers và jobs hoàn tất.")

async def set_commands():
    """Thiết lập danh sách lệnh gợi ý hiển thị trên Telegram."""
    logger.info("⏳ Đang thiết lập danh sách lệnh bot...")
    bot_instance = None
    try:
        bot_instance = Bot(token=BOT_TOKEN)
        commands = [
            BotCommand("flashcard", "📚 Mở menu chính"),
            BotCommand("flashcard_stats", "📈 Thống kê"),
            BotCommand("flashcard_learn", "🎓 Chế độ học tuần tự"),
            BotCommand("flashcard_review_all", "🔁 Chế độ ôn toàn bộ"),
            BotCommand("flashcard_cram_set", "🚀 Chế độ ôn tập nhanh bộ hiện tại"),
            BotCommand("flashcard_settings", "⚙️ Cài đặt"),
            BotCommand("flashcard_remind", "🔔 Cài đặt Thông báo"), 
            BotCommand("help", "❓ Hướng dẫn sử dụng")
        ]
        await bot_instance.set_my_commands(commands)
        logger.info(f"✅ Lệnh bot đã được thiết lập thành công ({len(commands)} lệnh).")
        return True
    except Exception as e:
        logger.error(f"❌ Lỗi khi thiết lập lệnh bot: {e}", exc_info=True)
        return False

async def main():
    """Khởi tạo và chạy ứng dụng Telegram bot."""
    logger.info("--- Khởi tạo Flashcard Bot ---")
    if not BOT_TOKEN:
        logger.critical("LỖI NGHIÊM TRỌNG: BOT_TOKEN chưa được thiết lập.")
        print("LỖI: Không tìm thấy BOT_TOKEN.", file=sys.stderr)
        sys.exit(1)

    app = None
    try:
        app_builder = ApplicationBuilder().token(BOT_TOKEN)
        app = app_builder.build()
        logger.info("Application được tạo thành công.")

        app.bot_data['application'] = app

        if 'cache_job_running' not in app.bot_data: app.bot_data['cache_job_running'] = False
        if 'cache_job_task' not in app.bot_data: app.bot_data['cache_job_task'] = None
        logger.debug(f"Trạng thái bot_data ban đầu: {app.bot_data}")

        await set_commands()
        register_all_handlers(app)

        logger.info(">>> Bot chuẩn bị chạy (async)...")
        await app.initialize()
        await app.start()

        if app.updater:
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            logger.info(">>> Bot đang chạy (async)... Nhấn Ctrl+C để dừng.")
            stop_event = asyncio.Event()
            await stop_event.wait() 
        else:
            logger.error("Updater không được khởi tạo.")
            return

    except (KeyboardInterrupt, SystemExit):
        logger.info("Nhận tín hiệu dừng...")
    except Exception as e:
        logger.critical(f"Lỗi nghiêm trọng khi chạy bot: {e}", exc_info=True)
    finally:
        if app is not None:
            logger.info("--- Bắt đầu quá trình tắt bot ---")
            try:
                if app.updater and app.updater.running: await app.updater.stop()
                if app.running: await app.stop()
                await app.shutdown()
                logger.info("--- Bot đã tắt hoàn toàn ---")
            except Exception as e_shutdown:
                logger.error(f"Lỗi khi tắt bot: {e_shutdown}", exc_info=True)
        else:
            logger.info("--- Bot không khởi tạo thành công để tắt ---")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
         if "Cannot run the event loop while another loop is running" in str(e):
             logger.warning("Bỏ qua lỗi RuntimeError loop khi dừng.")
         else:
             logger.critical(f"Lỗi RuntimeError khi chạy asyncio: {e}.")
    except Exception as e:
        logger.critical(f"Lỗi không xác định cấp cao nhất: {e}", exc_info=True)

