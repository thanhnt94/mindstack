# File: flashcard-telegram-bot/ui/stats_ui.py
"""
Module chứa các hàm xây dựng giao diện người dùng cho chức năng
hiển thị bảng xếp hạng (leaderboard) và menu thống kê.
(Sửa lần 1: Cấu trúc lại menu thống kê, thêm các hàm build keyboard mới,
             xóa build_leaderboard_period_menu)
"""

import logging
import html
import asyncio
import re 

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode 

from utils.helpers import get_chat_display_name
from config import LEADERBOARD_LIMIT 

logger = logging.getLogger(__name__)

def build_new_stats_menu_keyboard():
    """
    Sửa lần 1: Tạo bàn phím cho menu thống kê chính mới.
    """
    log_prefix = "[UI_BUILD_NEW_STATS_MENU]"
    logger.debug(f"{log_prefix} Tạo keyboard cho menu thống kê chính mới.")
    keyboard = [
        [InlineKeyboardButton("📊 Thống kê Cá nhân", callback_data="stats:show_personal_stats")], # Callback mới
        [InlineKeyboardButton("🏆 Bảng Xếp hạng", callback_data="stats:show_leaderboard_options")], # Callback mới
        [InlineKeyboardButton("🔙 Menu chính", callback_data="handle_callback_back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_leaderboard_direct_options_keyboard():
    """
    Sửa lần 1: Tạo bàn phím hiển thị trực tiếp các lựa chọn kỳ bảng xếp hạng.
    """
    log_prefix = "[UI_BUILD_LB_DIRECT_OPTIONS]"
    logger.debug(f"{log_prefix} Tạo keyboard chọn kỳ BXH trực tiếp.")
    keyboard = [
        [InlineKeyboardButton("📅 BXH Hôm Nay", callback_data="leaderboard:daily")],
        [InlineKeyboardButton("🗓️ BXH Tuần Này", callback_data="leaderboard:weekly")],
        [InlineKeyboardButton("🈷️ BXH Tháng Này", callback_data="leaderboard:monthly")],
        [InlineKeyboardButton("⏳ BXH Mọi Lúc", callback_data="leaderboard:all_time")],
        [InlineKeyboardButton("📊 Quay lại Menu Thống kê", callback_data="stats:main")] # Quay lại menu thống kê mới
    ]
    return InlineKeyboardMarkup(keyboard)

# Sửa lần 1: Xóa hàm build_leaderboard_period_menu() vì không còn dùng menu trung gian
# def build_leaderboard_period_menu():
#     # ... (code cũ) ...
#     pass

async def format_leaderboard_display(leaderboard_data, title, context, period_key='period_score', is_all_time=False):
    """
    Định dạng văn bản hiển thị bảng xếp hạng Top N.
    Sử dụng HTML, hiển thị thêm stats và ghi chú.
    (Hàm này giữ nguyên logic hiển thị chi tiết của một bảng xếp hạng)
    """
    log_prefix = f"[UI_FORMAT_LEADERBOARD|Title:{title}|AllTime:{is_all_time}]"
    logger.debug(f"{log_prefix} Định dạng hiển thị leaderboard với key điểm '{period_key}'.")

    if not leaderboard_data:
        return "ℹ️ Chưa có ai trên bảng xếp hạng này!"

    top_users_data = leaderboard_data
    actual_top_n = len(top_users_data)
    logger.debug(f"{log_prefix} Hiển thị top {actual_top_n} users.")

    bot_instance = None
    if hasattr(context, 'bot'): bot_instance = context.bot
    elif context.application and hasattr(context.application, 'bot'): bot_instance = context.application.bot

    if not bot_instance:
         logger.error(f"{log_prefix} Không thể lấy bot instance.")
         return "Lỗi: Không thể tải tên người dùng."

    telegram_ids_to_fetch = [user_row.get('telegram_id') for user_row in top_users_data if user_row.get('telegram_id')]
    display_names_map = {}
    if telegram_ids_to_fetch:
        tasks = [get_chat_display_name(bot_instance, tg_id) for tg_id in telegram_ids_to_fetch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, tg_id in enumerate(telegram_ids_to_fetch):
            if isinstance(results[i], Exception): display_names_map[tg_id] = str(tg_id)
            else: display_names_map[tg_id] = results[i]
        logger.debug(f"{log_prefix} Đã lấy xong tên hiển thị.")

    dynamic_title = title.replace(f"(Top 5)", f"(Top {actual_top_n})").replace(f"(Top {LEADERBOARD_LIMIT})", f"(Top {actual_top_n})")
    message_lines = [f"<b>{html.escape(dynamic_title)}</b>"]

    if is_all_time:
        legend = "[Tổng số bộ đã học / Tổng số thẻ đã học]"
    else:
        legend = "[Tổng số bộ đã học / Thẻ mới trong kỳ / Lượt ôn trong kỳ]"
    message_lines.append(f"<i>{html.escape(legend)}</i>\n")
    
    rank_display_map = {0: "🥇", 1: "🥈", 2: "🥉"}
    for i in range(3, LEADERBOARD_LIMIT):
        rank_display_map[i] = f"{i+1}."

    for rank, user_row in enumerate(top_users_data):
        telegram_id = user_row.get('telegram_id')
        score = user_row.get(period_key, 0)
        extra_stats = ""
        if is_all_time:
            total_sets = user_row.get('total_learned_sets', 'N/A')
            total_cards = user_row.get('total_learned_cards', 0)
            extra_stats = f"[{total_sets}/{total_cards}]"
        else:
            total_sets = user_row.get('learned_sets', 'N/A') 
            new_cards = user_row.get('new_cards_period', 0)
            reviews = user_row.get('reviews_period', 0)
            extra_stats = f"[{total_sets}/{new_cards}/{reviews}]"
        
        if telegram_id is None: continue

        display_name = display_names_map.get(telegram_id, str(telegram_id))
        escaped_name = html.escape(display_name)
        mention_html = f'<a href="tg://user?id={telegram_id}">{escaped_name}</a>'
        rank_display = rank_display_map.get(rank, f"{rank + 1}.")
        message_lines.append(f"{rank_display} {mention_html}: <b>{score}</b> điểm {html.escape(extra_stats)}")

    final_message = "\n".join(message_lines)
    return final_message
