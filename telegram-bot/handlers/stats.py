# File: flashcard-telegram-bot/handlers/stats.py
"""
Module chứa các handlers cho chức năng xem thống kê và bảng xếp hạng.
(Sửa lần 16: Hoàn thiện luồng UX cho Thống kê Cá nhân theo yêu cầu cuối cùng.)
(Sửa lần 17: Cập nhật import và gọi hàm vẽ biểu đồ để chỉ sử dụng 
             generate_combined_daily_activity_chart từ chart_service.)
"""
import sqlite3
import logging
import asyncio
import html
import re 
import os 
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest 

from database.connection import database_connect 
from database.query_stats import get_leaderboard 
from database.query_stats import get_daily_activity_history_by_user 
from database.query_stats import get_review_stats 
from database.query_user import get_user_by_telegram_id
from services.stats_service import (
    get_personal_stats_summary, 
    get_stats_per_set, 
    get_daily_leaderboard,  
    get_weekly_leaderboard, 
    get_monthly_leaderboard 
)
# Sửa lần 17: Chỉ import hàm biểu đồ kết hợp
from services.chart_service import generate_combined_daily_activity_chart 

from ui.stats_ui import (
    build_new_stats_menu_keyboard, 
    build_leaderboard_direct_options_keyboard,
    format_leaderboard_display
)

from utils.helpers import get_chat_display_name, send_or_edit_message, escape_md_v2
from utils.exceptions import DatabaseError, UserNotFoundError
from config import DEFAULT_TIMEZONE_OFFSET, LEADERBOARD_LIMIT, DAILY_HISTORY_MAX_DAYS, SETS_PER_PAGE 

logger = logging.getLogger(__name__)

PERSONAL_STATS_ACTIVE_MSG_ID_KEY = 'personal_stats_active_message_id' 
STATS_MENU_MSG_ID_KEY = 'stats_menu_message_id' 


async def handle_command_stats_menu(update, context):
    if not update or not update.effective_user or not update.message: return
    user_id_tg = update.effective_user.id; log_prefix = f"[STATS_CMD_MENU|UserTG:{user_id_tg}]"
    logger.info(f"{log_prefix} Lệnh /flashcard_stats.")
    chat_id = update.message.chat_id
    try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception : pass
    reply_markup = build_new_stats_menu_keyboard(); text = "📊 Thống kê & Bảng xếp hạng:\nChọn một mục để xem:"
    sent_message = await send_or_edit_message(context=context, chat_id=chat_id, text=text, reply_markup=reply_markup)
    if sent_message: 
        context.user_data[STATS_MENU_MSG_ID_KEY] = sent_message.message_id

async def handle_callback_stats_main_menu(update, context):
    query = update.callback_query;
    if not query or not query.from_user: return
    try: await query.answer()
    except Exception : pass
    user_id_tg = query.from_user.id; log_prefix = f"[STATS_CB_MAIN_MENU|UserTG:{user_id_tg}]"
    logger.info(f"{log_prefix} Quay lại menu thống kê chính.")
    chat_id = query.message.chat_id if query.message else user_id_tg; 
    message_to_edit = query.message 
    
    if chat_id: 
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action_main_menu: logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action_main_menu}")
    
    reply_markup = build_new_stats_menu_keyboard(); text = "📊 Thống kê & Bảng xếp hạng:\nChọn một mục để xem:"
    sent_message = await send_or_edit_message(context=context, chat_id=chat_id, text=text, reply_markup=reply_markup, message_to_edit=message_to_edit)
    if sent_message: 
        context.user_data[STATS_MENU_MSG_ID_KEY] = sent_message.message_id
        context.user_data.pop(PERSONAL_STATS_ACTIVE_MSG_ID_KEY, None) 

async def handle_callback_show_personal_stats(update, context):
    query = update.callback_query
    if not query or not query.from_user: return
    
    telegram_id = query.from_user.id
    log_prefix = f"[STATS_CB_PERSONAL_SUMMARY|UserTG:{telegram_id}]" 
    logger.info(f"{log_prefix} Yêu cầu xem Tóm tắt Thống kê Cá nhân.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message 
    
    try: await query.answer("Đang tải tóm tắt thống kê...")
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")

    if chat_id: 
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action_personal_stats: logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action_personal_stats}")
    
    user_info_db = None; user_id_db = None; user_timezone_offset = DEFAULT_TIMEZONE_OFFSET
    try:
        user_info_db = get_user_by_telegram_id(telegram_id)
        if not user_info_db or 'user_id' not in user_info_db: raise UserNotFoundError(identifier=telegram_id)
        user_id_db = user_info_db['user_id']
        user_timezone_offset = user_info_db.get('timezone_offset', DEFAULT_TIMEZONE_OFFSET)
        personal_summary = get_personal_stats_summary(user_id_db, user_timezone_offset)
        if personal_summary.get('error'):
            await send_or_edit_message(context, chat_id, f"❌ Lỗi tải dữ liệu thống kê: {personal_summary['error']}", message_to_edit=message_to_edit); return
        
        message_lines = ["📊 **Thống kê Cá nhân của bạn**\n"]
        today_s = personal_summary.get('today_stats', {})
        if today_s and not today_s.get('error'):
            today_str_display = "hôm nay"
            if today_s.get('today_start_dt') and isinstance(today_s.get('today_start_dt'), datetime):
                try: today_str_display = today_s['today_start_dt'].strftime("%d/%m/%Y")
                except: pass
            message_lines.append(f"**Ngày {escape_md_v2(today_str_display)}**")
            message_lines.append(f"  ✨ Điểm kiếm được: `{today_s.get('score_today', 0):+}`")
            message_lines.append(f"  ⭐ Thẻ mới học: `{today_s.get('learned_today', 0)}`")
            message_lines.append(f"  🔄 Lượt ôn tập: `{today_s.get('reviews_today', 0)}`")
        
        message_lines.append(f"\n**Tổng kết về thẻ** \\(đã học/ôn tập\\)")
        message_lines.append(f"  Tổng cộng: `{personal_summary.get('cards_learned_total_all_time', 0)}` / `{personal_summary.get('cards_reviewed_total_all_time', 0)}`")
        message_lines.append(f"  Tháng này: `{personal_summary.get('cards_learned_this_month', 0)}` / `{personal_summary.get('cards_reviewed_this_month', 0)}`")
        message_lines.append(f"  Tuần này: `{personal_summary.get('cards_learned_this_week', 0)}` / `{personal_summary.get('cards_reviewed_this_week', 0)}`")
        message_lines.append(f"  Hôm nay: `{personal_summary.get('cards_learned_today', 0)}` / `{personal_summary.get('cards_reviewed_today', 0)}`")

        message_lines.append(f"\n**Tổng kết Điểm**")
        message_lines.append(f"  💯 Tổng cộng: `{personal_summary.get('overall_total_score', 0)}`")
        message_lines.append(f"  📅 Tuần này: `{personal_summary.get('score_this_week', 0):+}` điểm")
        message_lines.append(f"  🈷️ Tháng này: `{personal_summary.get('score_this_month', 0):+}` điểm")
        message_lines.append(f"  ✨ Hôm nay: `{today_s.get('score_today', 0):+}` điểm")
        
        message_lines.append(f"\n**Trung bình Hàng ngày** \\(Toàn bộ LS / {personal_summary.get('total_active_days',0)} ngày HĐ\\)")
        message_lines.append(f"  📊 Điểm/ngày: `{personal_summary.get('avg_score_per_day', 0.0)}`")
        message_lines.append(f"  💡 Thẻ mới/ngày: `{personal_summary.get('avg_new_cards_per_day', 0.0)}`")
        message_lines.append(f"  🗓️ Lượt ôn/ngày: `{personal_summary.get('avg_reviews_per_day', 0.0)}`")
        final_text = "\n".join(message_lines)
        
        keyboard = [
            [
                InlineKeyboardButton("🔍 Chi tiết", callback_data="stats:show_personal_detail_options"),
                InlineKeyboardButton("📊 Menu TK", callback_data="stats:main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_message = await send_or_edit_message(context, chat_id, final_text, reply_markup, parse_mode=ParseMode.MARKDOWN_V2, message_to_edit=message_to_edit)
        if sent_message: 
            context.user_data[PERSONAL_STATS_ACTIVE_MSG_ID_KEY] = sent_message.message_id 
            
    except UserNotFoundError: logger.error(f"{log_prefix} Không tìm thấy người dùng {telegram_id}."); await send_or_edit_message(context, chat_id, "❌ Lỗi: Không tìm thấy thông tin người dùng.", message_to_edit=message_to_edit)
    except DatabaseError as e_db: logger.error(f"{log_prefix} Lỗi DB: {e_db}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Lỗi tải dữ liệu thống kê cá nhân.", message_to_edit=message_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi hiển thị thống kê cá nhân.", message_to_edit=message_to_edit)

async def handle_callback_show_personal_detail_options(update, context):
    query = update.callback_query
    if not query or not query.from_user: return
    telegram_id = query.from_user.id
    log_prefix = f"[STATS_CB_PERSONAL_DETAIL_OPTIONS|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Yêu cầu menu chi tiết Thống kê Cá nhân.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message 
    try: await query.answer()
    except Exception: pass
    text = "🔍 Chọn mục bạn muốn xem chi tiết hơn:"
    keyboard = [
        [InlineKeyboardButton("📚 Thống kê theo bộ", callback_data="stats:show_set_progress_detail")],
        [InlineKeyboardButton("📜 Lịch sử hoạt động", callback_data="stats:show_activity_history_detail")],
        [InlineKeyboardButton("📈 Xem Biểu đồ", callback_data="stats:show_all_charts_options")],
        [InlineKeyboardButton("📊 Quay lại Tóm tắt", callback_data="stats:show_personal_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    edited_message = await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit)
    if edited_message: 
        context.user_data[PERSONAL_STATS_ACTIVE_MSG_ID_KEY] = edited_message.message_id

async def handle_callback_show_set_progress_detail(update, context):
    query = update.callback_query;
    if not query or not query.from_user: return
    telegram_id = query.from_user.id
    user_info = get_user_by_telegram_id(telegram_id)
    if not user_info or 'user_id' not in user_info: await query.answer("Lỗi người dùng.", show_alert=True); return
    target_user_id_db = user_info['user_id']
    log_prefix = f"[STATS_CB_SET_DETAIL|UserTG:{telegram_id}|TargetDBID:{target_user_id_db}]"; logger.info(f"{log_prefix} Yêu cầu xem chi tiết Thống kê theo bộ.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_obj_to_edit = query.message 
    try: await query.answer("Đang tải Thống kê theo bộ...")
    except Exception: pass
    if chat_id: 
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action_set_detail: logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action_set_detail}")
    try:
        set_progress_list = get_stats_per_set(target_user_id_db) 
        if not set_progress_list or (isinstance(set_progress_list, list) and len(set_progress_list) == 1 and set_progress_list[0].get('error')):
            await send_or_edit_message(context, chat_id, "Bạn chưa học bộ thẻ nào hoặc có lỗi khi tải dữ liệu.", message_to_edit=message_obj_to_edit); return
        max_sets_to_display = 30 
        message_lines = [f"📚 **Thống kê Chi tiết theo Bộ** \\(tối đa {max_sets_to_display} bộ được liệt kê\\):\n"] 
        sorted_set_prog = sorted(set_progress_list, key=lambda x: x.get('title', '').lower())
        for i, sp in enumerate(sorted_set_prog[:max_sets_to_display]): 
            title = sp.get('title', 'N/A'); learned = sp.get('learned_count', 0); total = sp.get('total_count', 0)
            perc = (learned / total * 100) if total > 0 else 0
            message_lines.append(f"  • {escape_md_v2(title)}: `{learned}/{total}` \\({perc:.0f}%\\)")
        if len(sorted_set_prog) > max_sets_to_display: message_lines.append(f"  \\.\\.\\. và {len(sorted_set_prog) - max_sets_to_display} bộ khác\\.")
        final_text = "\n".join(message_lines)
        keyboard = [[InlineKeyboardButton("📊 Quay lại Tóm tắt", callback_data="stats:show_personal_stats")]] 
        reply_markup = InlineKeyboardMarkup(keyboard)
        edited_message = await send_or_edit_message(context, chat_id, final_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2, message_to_edit=message_obj_to_edit)
        if edited_message: context.user_data[PERSONAL_STATS_ACTIVE_MSG_ID_KEY] = edited_message.message_id
    except DatabaseError as e_db: logger.error(f"{log_prefix} Lỗi DB: {e_db}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Lỗi tải dữ liệu Thống kê theo bộ.", message_to_edit=message_obj_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi hiển thị Thống kê theo bộ.", message_to_edit=message_obj_to_edit)

async def handle_callback_show_activity_history_detail(update, context):
    query = update.callback_query;
    if not query or not query.from_user: return
    telegram_id = query.from_user.id
    user_info = get_user_by_telegram_id(telegram_id)
    if not user_info or 'user_id' not in user_info: await query.answer("Lỗi người dùng.", show_alert=True); return
    target_user_id_db = user_info['user_id']
    user_timezone_offset = user_info.get('timezone_offset', DEFAULT_TIMEZONE_OFFSET)
    log_prefix = f"[STATS_CB_HISTORY_DETAIL|UserTG:{telegram_id}|TargetDBID:{target_user_id_db}]"; logger.info(f"{log_prefix} Yêu cầu xem chi tiết Lịch sử hoạt động.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_obj_to_edit = query.message 
    try: await query.answer("Đang tải Lịch sử hoạt động...")
    except Exception: pass
    if chat_id: 
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action_hist_detail: logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action_hist_detail}")
    try:
        daily_hist_data = get_daily_activity_history_by_user(target_user_id_db, user_timezone_offset)
        if not daily_hist_data or (isinstance(daily_hist_data, dict) and daily_hist_data.get('error')):
            await send_or_edit_message(context, chat_id, "📊 Chưa có lịch sử hoạt động nào được ghi nhận hoặc có lỗi khi tải.", message_to_edit=message_obj_to_edit); return
        sorted_hist_items = sorted(daily_hist_data.items()); items_to_show_hist = sorted_hist_items[-DAILY_HISTORY_MAX_DAYS:]
        if not items_to_show_hist: await send_or_edit_message(context, chat_id, "📊 Không có dữ liệu lịch sử trong 30 ngày gần nhất.", message_to_edit=message_obj_to_edit); return
        message_lines = [f"📜 **Lịch sử Hoạt động Chi tiết** ({len(items_to_show_hist)} ngày gần nhất):\n"]; message_lines.append("`Ngày: Điểm / Mới / Ôn`")
        for date_str, stats_item in items_to_show_hist: 
            score_h = stats_item.get('score',0); new_h = stats_item.get('new',0); rev_h = stats_item.get('reviewed',0)
            try: display_date_h = datetime.strptime(date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
            except: display_date_h = date_str
            message_lines.append(f"`{escape_md_v2(display_date_h)}: {score_h:+} / {new_h} / {rev_h}`")
        final_text = "\n".join(message_lines)
        keyboard = [[InlineKeyboardButton("📊 Quay lại Tóm tắt", callback_data="stats:show_personal_stats")]] 
        reply_markup = InlineKeyboardMarkup(keyboard)
        edited_message = await send_or_edit_message(context, chat_id, final_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2, message_to_edit=message_obj_to_edit)
        if edited_message: context.user_data[PERSONAL_STATS_ACTIVE_MSG_ID_KEY] = edited_message.message_id
    except (UserNotFoundError, DatabaseError) as e_db: logger.error(f"{log_prefix} Lỗi DB/User: {e_db}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Lỗi tải dữ liệu Lịch sử hoạt động.", message_to_edit=message_obj_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi hiển thị Lịch sử hoạt động.", message_to_edit=message_obj_to_edit)

async def handle_callback_show_all_charts_options(update, context):
    query = update.callback_query;
    if not query or not query.from_user: return 
    telegram_id = query.from_user.id
    user_info = get_user_by_telegram_id(telegram_id)
    if not user_info or 'user_id' not in user_info:
        await query.answer("Lỗi: Không tìm thấy thông tin người dùng.", show_alert=True); return
    target_user_id_db = user_info['user_id']
    user_timezone_offset = user_info.get('timezone_offset', DEFAULT_TIMEZONE_OFFSET)
    log_prefix = f"[STATS_CB_ALL_CHARTS|UserTG:{telegram_id}|TargetDBID:{target_user_id_db}]"; logger.info(f"{log_prefix} Yêu cầu xem biểu đồ.")
    chat_id = query.message.chat_id if query.message else telegram_id
    original_message_id = query.message.message_id if query.message else None
    await query.answer("Đang chuẩn bị biểu đồ...") 
    if original_message_id and chat_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=original_message_id)
            logger.info(f"{log_prefix} Đã xóa tin nhắn menu chi tiết ID: {original_message_id}")
            context.user_data.pop(PERSONAL_STATS_ACTIVE_MSG_ID_KEY, None) 
        except BadRequest as e_del: logger.warning(f"{log_prefix} Lỗi khi xóa tin nhắn cũ ID {original_message_id}: {e_del}")
        except Exception as e_del_unk: logger.error(f"{log_prefix} Lỗi không mong muốn khi xóa tin nhắn cũ ID {original_message_id}: {e_del_unk}")
    loading_message_sent = None
    if chat_id:
        try: 
            loading_message_sent = await context.bot.send_message(chat_id=chat_id, text="⏳ Đang tạo biểu đồ, vui lòng chờ giây lát...")
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
        except Exception as e_load_msg: logger.warning(f"{log_prefix} Lỗi gửi tin nhắn chờ hoặc chat action: {e_load_msg}")
    
    # Sửa lần 17: Chỉ gửi biểu đồ kết hợp
    chart_image_path_combined = None
    try:
        logger.info(f"{log_prefix} Đang tạo biểu đồ kết hợp hoạt động hàng ngày.")
        chart_image_path_combined = generate_combined_daily_activity_chart(target_user_id_db, user_timezone_offset, num_days=None)
        if chart_image_path_combined and os.path.exists(chart_image_path_combined): 
            with open(chart_image_path_combined, 'rb') as photo:
                await context.bot.send_photo(chat_id=chat_id, photo=photo, caption="Biểu đồ Hoạt động Hàng ngày Kết hợp (Toàn bộ LS)")
            logger.info(f"{log_prefix} Đã gửi biểu đồ kết hợp.")
        else:
            logger.warning(f"{log_prefix} Không thể tạo biểu đồ kết hợp.")
            if chat_id: await context.bot.send_message(chat_id=chat_id, text="Không thể tạo biểu đồ hoạt động (thiếu dữ liệu).")
    except Exception as e_chart:
        logger.error(f"{log_prefix} Lỗi khi tạo/gửi biểu đồ kết hợp: {e_chart}", exc_info=True)
        if chat_id: await context.bot.send_message(chat_id=chat_id, text="Lỗi khi hiển thị biểu đồ hoạt động.")
    finally:
        if chart_image_path_combined and os.path.exists(chart_image_path_combined):
            try: os.remove(chart_image_path_combined)
            except Exception as e_remove: logger.error(f"{log_prefix} Lỗi xóa file tạm biểu đồ kết hợp: {e_remove}")
    
    if loading_message_sent:
        try: await context.bot.delete_message(chat_id=loading_message_sent.chat.id, message_id=loading_message_sent.message_id)
        except Exception as e_del_loading: logger.warning(f"{log_prefix} Lỗi xóa tin nhắn loading: {e_del_loading}")

    if chat_id: 
        kb_back_to_summary = [[InlineKeyboardButton("📊 Quay lại Tóm tắt", callback_data="stats:show_personal_stats")]]
        reply_markup_back = InlineKeyboardMarkup(kb_back_to_summary)
        new_back_message = await context.bot.send_message(chat_id=chat_id, text="Biểu đồ đã được hiển thị.", reply_markup=reply_markup_back)
        if new_back_message: 
            context.user_data[PERSONAL_STATS_ACTIVE_MSG_ID_KEY] = new_back_message.message_id

# Các hàm handler khác và register_handlers giữ nguyên
async def handle_callback_show_leaderboard_direct_options(update, context):
    query = update.callback_query;
    if not query or not query.from_user: return
    try: await query.answer()
    except Exception : pass
    user_id_tg = query.from_user.id; log_prefix = f"[STATS_CB_LB_OPTIONS|UserTG:{user_id_tg}]"
    logger.info(f"{log_prefix} Yêu cầu menu chọn kỳ BXH trực tiếp.")
    chat_id = query.message.chat_id if query.message else user_id_tg; message_to_edit = query.message
    if chat_id: 
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception : pass
    reply_markup = build_leaderboard_direct_options_keyboard(); text = "🏆 Chọn loại Bảng Xếp Hạng bạn muốn xem:"
    await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit)

async def handle_command_leaderboard(update, context):
    if not update or not update.effective_user or not update.message: return
    user_id_tg = update.effective_user.id; chat_id = update.message.chat_id
    log_prefix = f"[STATS_CMD_LEADERBOARD|UserTG:{user_id_tg}]"
    logger.info(f"{log_prefix} Lệnh /flashcard_leaderboard.")
    try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception : pass
    try:
        reply_markup = build_leaderboard_direct_options_keyboard()
        text = "🏆 Chọn loại Bảng Xếp Hạng bạn muốn xem:"
        await send_or_edit_message(context, chat_id, text, reply_markup)
    except Exception as e: logger.error(f"{log_prefix} Lỗi: {e}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.")

async def handle_callback_leaderboard_show_ranking(update, context):
    query = update.callback_query
    if not query or not query.from_user or not query.data: return
    telegram_id = query.from_user.id; log_prefix = f"[STATS_CB_LB_SHOW|UserTG:{telegram_id}]"
    chat_id = query.message.chat_id if query.message else telegram_id; message_to_edit = query.message
    period = None; leaderboard_data = []; title = f"🏆 Bảng Xếp Hạng (Top {LEADERBOARD_LIMIT})"; score_key = 'score'; is_all_time_flag = False
    if chat_id: 
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception : pass
    try:
        await query.answer(); parts = query.data.split(":"); period = parts[1]
        if period == "daily": leaderboard_data = get_daily_leaderboard(limit=LEADERBOARD_LIMIT); title = f"🏆 BXH Hôm Nay (Top {len(leaderboard_data)})"; score_key = 'period_score'
        elif period == "weekly": leaderboard_data = get_weekly_leaderboard(limit=LEADERBOARD_LIMIT); title = f"🏆 BXH Tuần Này (Top {len(leaderboard_data)})"; score_key = 'period_score'
        elif period == "monthly": leaderboard_data = get_monthly_leaderboard(limit=LEADERBOARD_LIMIT); title = f"🏆 BXH Tháng Này (Top {len(leaderboard_data)})"; score_key = 'period_score'
        elif period == "all_time":
            is_all_time_flag = True; score_key = 'score'; base_leaderboard = get_leaderboard(limit=LEADERBOARD_LIMIT); enriched_data_all_time = []
            conn_stats_ranking = None 
            try:
                conn_stats_ranking = database_connect(); conn_stats_ranking.row_factory = sqlite3.Row 
                for user_data_db in base_leaderboard: 
                    user_id = user_data_db.get('user_id'); enriched_user = dict(user_data_db)
                    if not user_id: continue
                    try:
                        stats_info = get_review_stats(user_id, conn=conn_stats_ranking) 
                        enriched_user['total_learned_sets'] = stats_info.get('learned_sets', 0)
                        enriched_user['total_learned_cards'] = stats_info.get('learned_distinct', 0)
                    except Exception: enriched_user['total_learned_sets'] = 'Lỗi'; enriched_user['total_learned_cards'] = 'Lỗi'
                    enriched_data_all_time.append(enriched_user)
                leaderboard_data = enriched_data_all_time
            finally:
                if conn_stats_ranking: conn_stats_ranking.close()
            title = f"🏆 BXH Mọi Lúc (Top {len(leaderboard_data)})"
        else: raise ValueError(f"Kỳ leaderboard không hợp lệ: {period}")
        formatted_text = await format_leaderboard_display(leaderboard_data, title, context, score_key, is_all_time=is_all_time_flag)
        keyboard = [[InlineKeyboardButton("🏆 Chọn kỳ BXH khác", callback_data="stats:show_leaderboard_options")]]; reply_markup = InlineKeyboardMarkup(keyboard)
        await send_or_edit_message(context, chat_id, formatted_text, reply_markup, parse_mode=ParseMode.HTML, message_to_edit=message_to_edit)
    except (ValueError, IndexError): logger.error(f"{log_prefix} Callback data lỗi: {query.data}"); await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu lựa chọn kỳ.", message_to_edit=message_to_edit)
    except DatabaseError as e: logger.error(f"{log_prefix} Lỗi DB: {e}"); await send_or_edit_message(context, chat_id, f"❌ Lỗi tải dữ liệu BXH kỳ '{period}'.", message_to_edit=message_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Lỗi hiển thị BXH.", message_to_edit=message_to_edit)

async def handle_command_daily_history(update, context):
    if not update or not update.effective_user or not update.message: return
    telegram_id = update.effective_user.id; chat_id = update.message.chat_id
    log_prefix = f"[STATS_CMD_HISTORY|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Lệnh /flashcard_daily_score_history.")
    if chat_id : 
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception : pass
    try:
        user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']; tz_offset = user_info.get('timezone_offset', DEFAULT_TIMEZONE_OFFSET)
        daily_stats_dict = get_daily_activity_history_by_user(actual_user_id, tz_offset)
        if not daily_stats_dict or not isinstance(daily_stats_dict, dict): 
            await send_or_edit_message(context=context, chat_id=chat_id, text="📊 Chưa có lịch sử hoạt động."); return
        sorted_items = sorted(daily_stats_dict.items()); max_days_to_show = DAILY_HISTORY_MAX_DAYS; items_to_show = sorted_items[-max_days_to_show:]
        message_lines = [f"📅 **Lịch sử hoạt động hàng ngày** ({len(items_to_show)} ngày gần nhất):\n"]; message_lines.append("`(Điểm kiếm được / Từ mới học / Lượt ôn tập)`\n")
        for date_str, stats_item in items_to_show: 
            if not isinstance(stats_item, dict): continue
            score_change = stats_item.get('score', 0); new_cards = stats_item.get('new', 0); reviews = stats_item.get('reviewed', 0); score_str = f"{score_change:+}"
            try: display_date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError: display_date = date_str
            message_lines.append(f"`{escape_md_v2(display_date)}`: **{score_str}** / `{new_cards}` / `{reviews}`") 
        final_message = "\n".join(message_lines)
        await send_or_edit_message(context=context, chat_id=chat_id, text=final_message, parse_mode='MarkdownV2') 
    except (UserNotFoundError, DatabaseError) as e: logger.error(f"{log_prefix} Lỗi DB/User: {e}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi tải dữ liệu lịch sử.")
    except Exception as e: logger.exception(f"{log_prefix} Lỗi: {e}"); await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi xử lý dữ liệu lịch sử.")

def register_handlers(app):
    app.add_handler(CommandHandler("flashcard_stats", handle_command_stats_menu))
    app.add_handler(CommandHandler("flashcard_leaderboard", handle_command_leaderboard))
    app.add_handler(CommandHandler("flashcard_daily_score_history", handle_command_daily_history))

    app.add_handler(CallbackQueryHandler(handle_callback_stats_main_menu, pattern=r"^stats:main$"))
    app.add_handler(CallbackQueryHandler(handle_callback_show_personal_stats, pattern=r"^stats:show_personal_stats$")) 
    app.add_handler(CallbackQueryHandler(handle_callback_show_personal_detail_options, pattern=r"^stats:show_personal_detail_options$"))

    app.add_handler(CallbackQueryHandler(handle_callback_show_leaderboard_direct_options, pattern=r"^stats:show_leaderboard_options$"))
    
    app.add_handler(CallbackQueryHandler(handle_callback_show_set_progress_detail, pattern=r"^stats:show_set_progress_detail$"))
    app.add_handler(CallbackQueryHandler(handle_callback_show_activity_history_detail, pattern=r"^stats:show_activity_history_detail$"))
    app.add_handler(CallbackQueryHandler(handle_callback_show_all_charts_options, pattern=r"^stats:show_all_charts_options$"))
    
    app.add_handler(CallbackQueryHandler(handle_callback_leaderboard_show_ranking, pattern=r"^leaderboard:(daily|weekly|monthly|all_time)$"))
    
    logger.info("Đã đăng ký các handler cho module Stats (cập nhật luồng UX Thống kê Cá nhân).")

