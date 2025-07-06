# File: flashcard-telegram-bot/handlers/learning_session.py
"""
Module chứa các handlers cho luồng học và ôn tập flashcard chính.
(Sửa lần 1: Tích hợp hiển thị ghi chú (ảnh và text) vào màn hình mặt sau thẻ.
             Cập nhật _delete_previous_messages.
             _display_card_backside tự xây dựng toàn bộ keyboard.)
(Sửa lần 2: Điều chỉnh thứ tự hiển thị mặt sau theo yêu cầu: Ảnh Note+Caption -> Ảnh Thẻ -> Audio Thẻ -> Text Thẻ+Keyboard.
             Bỏ nút "Menu chính" khỏi keyboard mặt sau.)
(Sửa lần 3: Cập nhật hiển thị context message ở mặt trước thẻ theo yêu cầu mới,
             thêm thông tin chi tiết cho bộ và nhãn cho các thông số thẻ.
             Đảm bảo thứ tự Ảnh -> Audio cho mặt trước.)
"""

from collections import defaultdict
import logging
import asyncio
import time
import html
import os
import sqlite3 # Cần cho get_review_stats nếu gọi với conn
import re

from telegram import Update
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import CallbackQuery
from telegram.ext import Application
from telegram.ext import ContextTypes
from telegram.ext import CommandHandler
from telegram.ext import CallbackQueryHandler
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError, BadRequest, Forbidden, RetryAfter

# Import từ các module khác (tuyệt đối)
from database.connection import database_connect
from database.query_progress import get_next_card_id_for_review, get_progress_id_by_card, insert_new_progress, get_progress_with_card_info, update_progress_by_id as update_progress_record_by_id
from database.query_stats import get_review_stats # <<< THÊM IMPORT
from database.query_user import get_user_by_telegram_id, update_user_by_id
from database.query_set import get_sets
from database.query_note import get_note_by_card_and_user
from services.audio_service import get_cached_or_generate_audio
from services.review_logic import process_review_response
from ui.flashcard_ui import build_no_card_display
from utils.helpers import convert_unix_to_local, send_or_edit_message, escape_md_v2
from utils.exceptions import DatabaseError, UserNotFoundError, ProgressNotFoundError, CardNotFoundError, SetNotFoundError, ValidationError, DuplicateError
from config import (
    AD_INTERVAL, IMAGES_DIR, NOTE_IMAGES_DIR,
    DEFAULT_LEARNING_MODE,
    MODE_SEQ_INTERSPERSED, MODE_DUE_ONLY_RANDOM, MODE_NEW_SEQUENTIAL,
    MODE_SEQ_RANDOM_NEW, MODE_REVIEW_ALL_DUE, MODE_REVIEW_HARDEST,
    MODE_CRAM_SET, MODE_CRAM_ALL, MODE_NEW_RANDOM,
    LEARNING_MODE_DISPLAY_NAMES, SCORE_INCREASE_NEW_CARD, DEFAULT_TIMEZONE_OFFSET,
    SKIP_STREAK_THRESHOLD,
    FLIP_DELAY_MEDIA, FLIP_DELAY_TEXT
)

logger = logging.getLogger(__name__)

async def _delete_previous_messages(context, chat_id, user_data_key_prefix="last_"):
    # Hàm này giữ nguyên logic từ phiên bản trước
    keys_to_delete = [
        "{}front_audio_id".format(user_data_key_prefix),
        "{}back_audio_id".format(user_data_key_prefix),
        "{}context_id".format(user_data_key_prefix),
        "{}card_id".format(user_data_key_prefix),
        "{}note_id".format(user_data_key_prefix),
        "{}metric_id".format(user_data_key_prefix),
        "{}front_image_id".format(user_data_key_prefix),
        "{}back_image_id".format(user_data_key_prefix),
        "{}note_photo_caption_id".format(user_data_key_prefix),
    ]
    delete_tasks = []
    deleted_keys_info = []
    bot = context.bot if hasattr(context, 'bot') else (context.application.bot if context.application and hasattr(context.application, 'bot') else None)
    if not bot:
        logger.error(f"[_delete_previous_messages|Chat:{chat_id}]: Không thể lấy bot instance.")
        return

    for key in keys_to_delete:
        message_id = context.user_data.pop(key, None)
        if message_id:
            deleted_keys_info.append(f"{key}={message_id}")
            logger.debug(f"[_delete_previous_messages|Chat:{chat_id}]: Chuẩn bị xóa message ID: {message_id} (Key: {key})")
            delete_tasks.append(bot.delete_message(chat_id=chat_id, message_id=message_id))

    if delete_tasks:
        logger.info(f"[_delete_previous_messages|Chat:{chat_id}]: Đang xóa {len(delete_tasks)} tin nhắn: {', '.join(deleted_keys_info)}")
        results = await asyncio.gather(*delete_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                if isinstance(result, BadRequest) and "message to delete not found" in str(result).lower():
                    logger.info(f"[_delete_previous_messages|Chat:{chat_id}]: Tin nhắn đã bị xóa trước đó (index {i}, Key: {deleted_keys_info[i]}): {result}")
                else:
                    logger.warning(f"[_delete_previous_messages|Chat:{chat_id}]: Lỗi khi xóa tin nhắn (index {i}, Key: {deleted_keys_info[i]}): {result}")
        logger.info(f"[_delete_previous_messages|Chat:{chat_id}]: Hoàn thành xóa.")
    else:
        logger.debug(f"[_delete_previous_messages|Chat:{chat_id}]: Không có tin nhắn cũ để xóa.")


async def display_next_card(update_or_query, context, user_info, mode=None):
    """
    Hiển thị mặt trước của thẻ tiếp theo cho người dùng.
    Đã cập nhật cách hiển thị context message và đảm bảo thứ tự Ảnh -> Audio.
    """
    telegram_id = None
    actual_user_id = None
    chat_id = None

    if user_info and isinstance(user_info, dict):
        actual_user_id = user_info.get('user_id')
        telegram_id = user_info.get('telegram_id')
    else:
        temp_tg_id = None
        if update_or_query and hasattr(update_or_query, 'effective_user') and update_or_query.effective_user:
            temp_tg_id = update_or_query.effective_user.id
        elif update_or_query and hasattr(update_or_query, 'from_user') and update_or_query.from_user:
            temp_tg_id = update_or_query.from_user.id
        logger.error(f"[display_next_card|UserTG:{temp_tg_id}]: user_info không hợp lệ hoặc bị thiếu.")
        if temp_tg_id:
            try:
                await context.bot.send_message(temp_tg_id, "Lỗi nghiêm trọng: Thiếu thông tin người dùng khi hiển thị thẻ.")
            except Exception as e_send_err:
                logger.error(f"[display_next_card|UserTG:{temp_tg_id}]: Lỗi gửi tin nhắn lỗi user_info: {e_send_err}")
        return

    if not actual_user_id or not telegram_id:
        logger.error(f"[display_next_card|UserTG:{telegram_id}]: Thiếu user_id ({actual_user_id}) hoặc telegram_id ({telegram_id}).")
        try:
            await context.bot.send_message(telegram_id, "Lỗi nghiêm trọng: Không xác định được ID người dùng.")
        except Exception as e_send_err:
            logger.error(f"[display_next_card|UserTG:{telegram_id}]: Lỗi gửi tin nhắn lỗi ID: {e_send_err}")
        return

    if mode is None:
        mode = user_info.get('current_mode', DEFAULT_LEARNING_MODE)

    log_prefix_base = f"[DISPLAY_NEXT|Mode:{mode}]"
    log_prefix = f"{log_prefix_base}[UserUID:{actual_user_id}, TG:{telegram_id}]"

    try:
        current_timestamp = int(time.time())
        update_user_by_id(actual_user_id, last_seen=current_timestamp)
        logger.debug(f"{log_prefix}: Đã cập nhật last_seen cho user_id {actual_user_id}")
    except Exception as e_update_seen:
        logger.error(f"{log_prefix}: Lỗi khi cập nhật last_seen: {e_update_seen}")

    source = "Unknown"
    chat_id = telegram_id
    message_to_edit_for_no_card = None

    if update_or_query and hasattr(update_or_query, 'effective_user'):
        source = "Update (Command)"
        logger.info(f"{log_prefix}: Gọi từ {source}.")
        if hasattr(update_or_query, 'effective_chat') and update_or_query.effective_chat:
            chat_id = update_or_query.effective_chat.id
    elif update_or_query and hasattr(update_or_query, 'from_user'):
        source = "CallbackQuery"
        query_obj = update_or_query
        logger.info(f"{log_prefix}: Gọi từ {source} (Callback: {query_obj.data}).")
        if query_obj.message:
            chat_id = query_obj.message.chat_id
            message_to_edit_for_no_card = query_obj.message
    elif update_or_query is None:
        source = "InternalCall (No Update)"
        logger.info(f"{log_prefix}: Gọi từ nội bộ.")
    else:
        logger.error(f"{log_prefix}: Nguồn gọi không hợp lệ: {type(update_or_query)}.")
        return

    if not chat_id:
        chat_id = telegram_id
        logger.warning(f"{log_prefix}: Không lấy được chat_id, dùng telegram_id.")

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception as e_action:
        logger.warning(f"{log_prefix}: Lỗi gửi chat action: {e_action}")

    logger.info(f"{log_prefix}: Bắt đầu lấy và hiển thị thẻ mặt trước.")
    await _delete_previous_messages(context, chat_id)

    flashcard = None
    progress_id = None
    flashcard_id = None
    flashcard_id_or_ts = -int(time.time())
    text_no_card = None
    reply_markup_no_card = None

    try:
        logger.debug(f"{log_prefix}: Gọi get_next_card_id_for_review...")
        flashcard_id_or_ts = get_next_card_id_for_review(actual_user_id, mode=mode)
        logger.info(f"{log_prefix}: get_next_card_id_for_review trả về: {flashcard_id_or_ts}")

        if flashcard_id_or_ts <= 0:
            wait_time_ts = flashcard_id_or_ts
            text_no_card, reply_markup_no_card = build_no_card_display(wait_time_ts, mode)
            if text_no_card and reply_markup_no_card:
                await send_or_edit_message(context, chat_id, text_no_card, reply_markup_no_card, parse_mode='Markdown', message_to_edit=message_to_edit_for_no_card)
                logger.info(f"{log_prefix}: Đã hiển thị thông báo hết thẻ.")
            else:
                logger.error(f"{log_prefix}: Lỗi tạo giao diện hết thẻ (build_no_card_display trả về None).")
            return

        flashcard_id = flashcard_id_or_ts
        logger.debug(f"{log_prefix}: Có thẻ ID: {flashcard_id}.")

        progress_id = get_progress_id_by_card(actual_user_id, flashcard_id)
        if not progress_id:
            logger.debug(f"{log_prefix}: Thẻ chưa có progress. Tạo mới...")
            tz_offset = user_info.get('timezone_offset', DEFAULT_TIMEZONE_OFFSET)
            progress_id = insert_new_progress(actual_user_id, flashcard_id, tz_offset_hours=tz_offset)
            logger.info(f"{log_prefix}: Đã tạo progress ID: {progress_id}")
            quick_review_modes_score = {MODE_REVIEW_HARDEST, MODE_CRAM_SET, MODE_CRAM_ALL}
            if mode not in quick_review_modes_score:
                current_score = user_info.get('score', 0)
                new_score = current_score + SCORE_INCREASE_NEW_CARD
                logger.debug(f"{log_prefix}: Cộng điểm thẻ mới (+{SCORE_INCREASE_NEW_CARD} -> {new_score}) cho user_id {actual_user_id}")
                try:
                    update_user_by_id(actual_user_id, score=new_score)
                except Exception as e_score:
                    logger.error(f"{log_prefix}: Lỗi cập nhật điểm thẻ mới: {e_score}")
            else:
                logger.debug(f"{log_prefix}: Bỏ qua cộng điểm thẻ mới do đang ở mode ôn tập nhanh ({mode}).")

        flashcard = get_progress_with_card_info(progress_id) # Lấy thông tin thẻ và progress
        if flashcard:
            flashcard['progress_id'] = progress_id # Đảm bảo progress_id có trong dict flashcard

    except (DatabaseError, UserNotFoundError, ValidationError, ProgressNotFoundError, CardNotFoundError, SetNotFoundError, DuplicateError) as e_db:
        logger.exception(f"{log_prefix}: Lỗi DB/Logic khi chuẩn bị thẻ: {e_db}")
        await send_or_edit_message(context, chat_id, f"❌ Lỗi tải thẻ tiếp theo ({type(e_db).__name__}). Vui lòng thử lại sau.", message_to_edit=message_to_edit_for_no_card)
        return
    except Exception as e_main:
        logger.exception(f"{log_prefix}: Lỗi nghiêm trọng khi chuẩn bị thẻ: {e_main}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi hệ thống, không thể tải thẻ.", message_to_edit=message_to_edit_for_no_card)
        return

    try:
        if not flashcard:
            logger.error(f"{log_prefix}: Không thể lấy thông tin flashcard cuối cùng cho progress_id {progress_id}.")
            await send_or_edit_message(context, chat_id, "❌ Lỗi tải chi tiết thẻ.", message_to_edit=message_to_edit_for_no_card)
            return

        # --- Bắt đầu xây dựng context_text mới ---
        streak = flashcard.get("correct_streak", 0)
        correct = flashcard.get("correct_count", 0)
        reviews = flashcard.get("review_count", 0)
        
        set_id_current = flashcard.get('set_id')
        set_title_current = "Không rõ bộ"
        due_in_set_str = "N/A"
        learned_in_set_str = "N/A"
        total_in_set_str = "N/A"
        percentage_learned_str = "N/A"

        if set_id_current:
            set_info_tuple = get_sets(set_id=set_id_current) # Hàm này tự quản lý connection
            set_data = set_info_tuple[0][0] if set_info_tuple and set_info_tuple[0] else None
            if set_data:
                set_title_current = set_data.get("title", f"ID không tên ({set_id_current})")
            else:
                set_title_current = f"ID không hợp lệ ({set_id_current})"
            
            # Lấy stats cho bộ hiện tại
            # get_review_stats sẽ tự quản lý connection nếu không truyền conn
            stats_for_set = get_review_stats(user_id=actual_user_id, set_id=set_id_current)
            due_in_set = stats_for_set.get('due_total', 0)
            learned_in_set = stats_for_set.get('learned_total', 0)
            total_in_set = stats_for_set.get('total_count', 0)
            percentage_learned = (learned_in_set / total_in_set * 100) if total_in_set > 0 else 0
            
            due_in_set_str = str(due_in_set)
            learned_in_set_str = str(learned_in_set)
            total_in_set_str = str(total_in_set)
            percentage_learned_str = f"{percentage_learned:.0f}%"

        escaped_set_title = escape_md_v2(set_title_current)
        mode_display_name = LEARNING_MODE_DISPLAY_NAMES.get(mode, mode)
        escaped_mode_name = escape_md_v2(mode_display_name)

        # Định dạng context_text
        line1_card_stats = f"📌 ID: `{flashcard_id}` \\[Chuỗi: `{streak}` / Đúng: `{correct}` / Lần ôn: `{reviews}`\\]"
        line2_set_info = f"📚 Bộ: **{escaped_set_title}** \n \\[Cần ôn: `{due_in_set_str}` / Đã học: `{learned_in_set_str}` / Tổng: `{total_in_set_str}` \\(`{percentage_learned_str}`\\)\\]"
        line3_mode_info = f"⚡ Chế độ: `{escaped_mode_name}`"
        
        context_text = f"{line1_card_stats}\n{line2_set_info}\n{line3_mode_info}"
        # --- Kết thúc xây dựng context_text mới ---

        logger.debug(f"{log_prefix}: Gửi context message:\n{context_text}")
        context_info_message = await context.bot.send_message(chat_id=chat_id, text=context_text, parse_mode=ParseMode.MARKDOWN_V2)
        if context_info_message:
            context.user_data['last_context_id'] = context_info_message.message_id
            logger.info(f"{log_prefix}: Gửi context ID: {context_info_message.message_id}")

        # --- Thứ tự hiển thị: Ảnh -> Audio -> Text + Nút ---
        play_front_image = user_info.get('front_image_enabled', 1) == 1
        if play_front_image:
            front_img_path_relative = flashcard.get("front_img")
            if front_img_path_relative:
                full_image_path = os.path.abspath(os.path.join(IMAGES_DIR, front_img_path_relative))
                if os.path.exists(full_image_path):
                    try:
                        with open(full_image_path, 'rb') as photo_file:
                            sent_front_image_msg = await context.bot.send_photo(chat_id=chat_id, photo=photo_file)
                        context.user_data["last_front_image_id"] = sent_front_image_msg.message_id
                        logger.info(f"{log_prefix}: Gửi ảnh mặt trước OK ID: {sent_front_image_msg.message_id}")
                    except Exception as e_send_img:
                        logger.error(f"{log_prefix}: Lỗi gửi ảnh mặt trước: {e_send_img}")
                else:
                    logger.warning(f"{log_prefix}: File ảnh mặt trước '{full_image_path}' không tồn tại.")

        front_audio_content = flashcard.get("front_audio_content")
        play_front_audio = user_info.get('front_audio', 1) == 1
        if play_front_audio and front_audio_content:
            audio_path_front = await get_cached_or_generate_audio(front_audio_content, "mp3")
            if audio_path_front:
                try:
                    with open(audio_path_front, "rb") as audio_file:
                        sent_front_audio_msg = await context.bot.send_audio(chat_id=chat_id, audio=audio_file)
                    context.user_data["last_front_audio_id"] = sent_front_audio_msg.message_id
                    logger.info(f"{log_prefix}: Gửi audio mặt trước OK ID: {sent_front_audio_msg.message_id}")
                except Exception as e_send_audio:
                    logger.error(f"{log_prefix}: Lỗi gửi audio mặt trước: {e_send_audio}")
            else:
                logger.warning(f"{log_prefix}: Không thể tạo/lấy cache audio mặt trước cho: '{front_audio_content[:30]}...'")

        text_front_raw = flashcard.get("front", "Lỗi: Nội dung mặt trước rỗng")
        text_front_display = html.unescape(text_front_raw) # Hiển thị HTML entities đúng
        keyboard_front = [[InlineKeyboardButton("🔄 Flip", callback_data=f"flip:{progress_id}")]]
        reply_markup_front = InlineKeyboardMarkup(keyboard_front)
        logger.debug(f"{log_prefix}: Gửi card mặt trước (text + flip button)...")
        sent_message_front = await context.bot.send_message(chat_id=chat_id, text=text_front_display, reply_markup=reply_markup_front, parse_mode=None) # parse_mode=None để tránh lỗi với text thuần
        if sent_message_front:
            context.user_data['last_card_id'] = sent_message_front.message_id
            logger.info(f"{log_prefix}: Đã gửi card mặt trước ID: {sent_message_front.message_id}")
        else:
            logger.error(f"{log_prefix}: Lỗi gửi card mặt trước.")
    except Exception as e_send:
        logger.exception(f"{log_prefix}: Lỗi khi gửi các thành phần mặt trước: {e_send}")
        await context.bot.send_message(chat_id, "❌ Lỗi hiển thị thẻ.")

# Các hàm _display_card_backside, handle_callback_flip_card, 
# process_review_response_handler, handle_callback_skip_card, 
# handle_callback_review_set, _handle_mode_command, các lệnh mode, 
# handle_callback_continue_learning, handle_callback_review_all, 
# handle_callback_show_due_sets, và register_handlers giữ nguyên như phiên bản trước.
# (Lưu ý: Đảm bảo các hàm này tương thích với các thay đổi về dữ liệu nếu có)

async def _display_card_backside(update_or_query, context, progress_id, user_info):
    # Giữ nguyên logic từ learning_session_update_v2 (đã có tích hợp note)
    telegram_id = user_info.get('telegram_id')
    actual_user_id = user_info.get('user_id')
    log_prefix = f"[DISPLAY_BACKSIDE|UserUID:{actual_user_id}, TG:{telegram_id}, ProgID:{progress_id}]"
    logger.info(f"{log_prefix}: Bắt đầu hiển thị mặt sau (tích hợp note, thứ tự mới).")

    chat_id = telegram_id
    if update_or_query:
        if hasattr(update_or_query, 'effective_chat') and update_or_query.effective_chat:
            chat_id = update_or_query.effective_chat.id
        elif hasattr(update_or_query, 'message') and update_or_query.message and hasattr(update_or_query.message, 'chat_id'):
            chat_id = update_or_query.message.chat_id
    logger.debug(f"{log_prefix}: Sử dụng chat_id: {chat_id}")

    await _delete_previous_messages(context, chat_id)

    flashcard = None
    note_data = None
    try:
        flashcard = get_progress_with_card_info(progress_id)
        if not flashcard: raise ProgressNotFoundError(progress_id=progress_id)
        flashcard_id = flashcard.get('flashcard_id')
        if not flashcard_id: raise DatabaseError(f"Progress ID {progress_id} không có flashcard_id.")
        note_data = get_note_by_card_and_user(flashcard_id, actual_user_id)
    except (ProgressNotFoundError, CardNotFoundError, DatabaseError) as e:
        logger.error(f"{log_prefix}: Lỗi DB/NotFound khi lấy thông tin: {e}")
        await context.bot.send_message(chat_id, "❌ Lỗi tải dữ liệu thẻ/note.")
        return
    except Exception as e_get_info:
        logger.error(f"{log_prefix}: Lỗi không mong muốn khi lấy thông tin: {e_get_info}", exc_info=True)
        await context.bot.send_message(chat_id, "❌ Có lỗi xảy ra khi chuẩn bị mặt sau thẻ.")
        return

    try:
        # Thứ tự hiển thị: Ảnh Note+Caption -> Ảnh Thẻ -> Audio Thẻ -> Text Thẻ+Keyboard.
        note_text_for_caption = None
        note_text_separate_after_card_back = None
        note_image_path_relative = note_data.get('image_path') if note_data else None
        note_content_text = note_data.get('note', '') if note_data else ''

        if note_image_path_relative:
            full_note_image_path = os.path.join(NOTE_IMAGES_DIR, note_image_path_relative)
            if os.path.exists(full_note_image_path):
                note_text_for_caption_raw = html.escape(note_content_text) if note_content_text else "Ảnh ghi chú"
                if len(note_text_for_caption_raw) > 1024:
                    note_text_for_caption = note_text_for_caption_raw[:1020] + "..."
                    note_text_separate_after_card_back = note_content_text
                else:
                    note_text_for_caption = note_text_for_caption_raw
                await asyncio.sleep(FLIP_DELAY_MEDIA / 3)
                try:
                    with open(full_note_image_path, 'rb') as photo_file:
                        sent_note_photo_msg = await context.bot.send_photo(
                            chat_id=chat_id, photo=photo_file, caption=note_text_for_caption,
                            parse_mode=ParseMode.HTML
                        )
                    context.user_data["last_note_photo_caption_id"] = sent_note_photo_msg.message_id
                    logger.info(f"{log_prefix}: Gửi ảnh note kèm caption OK ID: {sent_note_photo_msg.message_id}")
                except Exception as e_send_note_photo:
                    logger.error(f"{log_prefix}: Lỗi gửi ảnh note kèm caption: {e_send_note_photo}")
                    note_text_separate_after_card_back = note_content_text
            else:
                logger.warning(f"{log_prefix}: File ảnh note '{full_note_image_path}' không tồn tại.")
                note_text_separate_after_card_back = note_content_text
        elif note_content_text:
            note_text_separate_after_card_back = note_content_text

        play_back_image = user_info.get('back_image_enabled', 1) == 1
        if play_back_image:
            back_img_path_relative = flashcard.get("back_img")
            if back_img_path_relative:
                full_card_back_image_path = os.path.join(IMAGES_DIR, back_img_path_relative)
                if os.path.exists(full_card_back_image_path):
                    await asyncio.sleep(FLIP_DELAY_MEDIA / 3)
                    try:
                        with open(full_card_back_image_path, 'rb') as photo_file:
                            sent_card_back_img_msg = await context.bot.send_photo(chat_id=chat_id, photo=photo_file)
                        context.user_data["last_back_image_id"] = sent_card_back_img_msg.message_id
                        logger.info(f"{log_prefix}: Gửi ảnh mặt sau thẻ OK ID: {sent_card_back_img_msg.message_id}")
                    except Exception as e_send_card_img:
                        logger.error(f"{log_prefix}: Lỗi gửi ảnh mặt sau thẻ: {e_send_card_img}")

        play_back_audio = user_info.get('back_audio', 1) == 1
        if play_back_audio:
            back_audio_content = flashcard.get("back_audio_content")
            if back_audio_content:
                audio_path_back = await get_cached_or_generate_audio(back_audio_content, "mp3")
                if audio_path_back:
                    await asyncio.sleep(FLIP_DELAY_MEDIA / 3)
                    try:
                        with open(audio_path_back, "rb") as audio_file:
                            sent_back_audio_msg = await context.bot.send_audio(chat_id=chat_id, audio=audio_file)
                        context.user_data["last_back_audio_id"] = sent_back_audio_msg.message_id
                        logger.info(f"{log_prefix}: Gửi audio mặt sau thẻ OK ID: {sent_back_audio_msg.message_id}")
                    except Exception as e_send_card_audio:
                        logger.error(f"{log_prefix}: Lỗi gửi audio mặt sau thẻ: {e_send_card_audio}")

        final_text_parts = []
        card_back_text_raw = flashcard.get("back", "(Mặt sau trống)")
        final_text_parts.append(html.escape(card_back_text_raw))

        if note_text_separate_after_card_back:
            final_text_parts.append("\n\n📝 **Ghi chú của bạn:**")
            final_text_parts.append(html.escape(note_text_separate_after_card_back))

        final_display_text = "\n".join(final_text_parts).strip()
        if not final_display_text:
            final_display_text = "(Không có nội dung text để hiển thị)"

        keyboard_buttons = []
        note_id_for_button = note_data.get('note_id') if note_data else None
        current_flashcard_id = flashcard.get('flashcard_id')

        row1 = []
        if note_data and note_id_for_button:
            row1.append(InlineKeyboardButton("✏️ Sửa ghi chú", callback_data=f"update_note_by_id:{note_id_for_button}"))
        else:
            row1.append(InlineKeyboardButton("➕ Thêm ghi chú", callback_data=f"add_note_for_user:{current_flashcard_id}"))

        correct_streak_val = flashcard.get("correct_streak", 0)
        if correct_streak_val >= SKIP_STREAK_THRESHOLD:
            row1.append(InlineKeyboardButton("⏩ Bỏ qua thẻ", callback_data=f"skip:{progress_id}"))
        row1.append(InlineKeyboardButton("🚩 Báo lỗi", callback_data=f"report_card:{current_flashcard_id}"))
        keyboard_buttons.append(row1)

        is_new_card_display = flashcard.get("last_reviewed") is None
        if is_new_card_display:
            keyboard_buttons.append([InlineKeyboardButton("▶️ Tiếp tục", callback_data=f"rate:{progress_id}:2")])
        else:
            keyboard_buttons.append([
                InlineKeyboardButton("❌ Chưa nhớ", callback_data=f"rate:{progress_id}:-1"),
                InlineKeyboardButton("🤔 Mơ hồ", callback_data=f"rate:{progress_id}:0"),
                InlineKeyboardButton("✅ Nhớ", callback_data=f"rate:{progress_id}:1")
            ])
        final_reply_markup = InlineKeyboardMarkup(keyboard_buttons)

        await asyncio.sleep(FLIP_DELAY_TEXT)
        sent_final_message = await context.bot.send_message(
            chat_id=chat_id, text=final_display_text, reply_markup=final_reply_markup,
            parse_mode=ParseMode.HTML
        )
        if sent_final_message:
            context.user_data['last_card_id'] = sent_final_message.message_id
            logger.info(f"{log_prefix}: Gửi mặt sau thẻ (text+note+keyboard) OK ID: {sent_final_message.message_id}")

    except Exception as e_send_all_back:
        logger.exception(f"{log_prefix}: Lỗi khi gửi các thành phần mặt sau: {e_send_all_back}")
        await context.bot.send_message(chat_id, "❌ Lỗi hiển thị mặt sau thẻ.")


async def handle_callback_flip_card(update, context):
    # Giữ nguyên logic
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        logger.warning("handle_callback_flip_card: callback query/data/user lỗi.")
        return

    telegram_id = query.from_user.id
    log_prefix = f"[LEARN_FLIP|UserTG:{telegram_id}]"
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit_or_delete = query.message
    progress_id = -1
    user_info = None
    actual_user_id = None

    if chat_id != -1:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action:
            logger.warning(f"{log_prefix}: Lỗi gửi chat action: {e_action}")

    try:
        progress_id_str = query.data.split(":")[1]
        progress_id = int(progress_id_str)
        logger.info(f"{log_prefix}: Yêu cầu lật thẻ progress ID: {progress_id}")
        await query.answer()
    except (ValueError, IndexError):
        logger.error(f"{log_prefix}: Callback data flip lỗi: {query.data}")
        await context.bot.send_message(chat_id, "❌ Lỗi: Dữ liệu thẻ không hợp lệ.")
        return
    except Exception as e_ans:
        logger.warning(f"{log_prefix}: Lỗi answer callback: {e_ans}")

    if message_to_edit_or_delete:
        try:
            await context.bot.delete_message(chat_id=message_to_edit_or_delete.chat_id, message_id=message_to_edit_or_delete.message_id)
            logger.info(f"{log_prefix}: Đã xóa tin nhắn mặt trước ID: {message_to_edit_or_delete.message_id}")
        except Exception as e_del_front:
            logger.warning(f"{log_prefix}: Lỗi xóa tin nhắn mặt trước ID {message_to_edit_or_delete.message_id}: {e_del_front}")

    try:
        user_info_full = get_user_by_telegram_id(telegram_id)
        if not user_info_full:
            raise UserNotFoundError(identifier=telegram_id)
        user_info = user_info_full # Gán lại user_info để dùng trong _display_card_backside
        actual_user_id = user_info_full['user_id']

        if actual_user_id: # Cập nhật last_seen
            try:
                current_timestamp_flip = int(time.time())
                update_user_by_id(actual_user_id, last_seen=current_timestamp_flip)
                logger.debug(f"{log_prefix}: Đã cập nhật last_seen cho user_id {actual_user_id}")
            except Exception as e_update_seen_flip:
                logger.error(f"{log_prefix}: Lỗi khi cập nhật last_seen khi flip: {e_update_seen_flip}")
        await _display_card_backside(query, context, progress_id, user_info)
    except (UserNotFoundError, DatabaseError) as e:
        logger.error(f"{log_prefix}: Lỗi DB/UserNotFound khi chuẩn bị cho flip: {e}")
        await context.bot.send_message(chat_id, "❌ Lỗi tải dữ liệu người dùng.")
    except Exception as e_get_info:
        logger.error(f"{log_prefix}: Lỗi không mong muốn khi chuẩn bị cho flip: {e_get_info}", exc_info=True)
        await context.bot.send_message(chat_id, "❌ Có lỗi xảy ra.")

async def process_review_response_handler(update, context):
    # Giữ nguyên logic
    query = update.callback_query
    if not query or not query.data or not query.from_user: return

    telegram_id = query.from_user.id
    log_prefix = f"[LEARN_PROCESS_ANSWER|UserTG:{telegram_id}]"
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_delete_ref = query.message
    progress_id = -1
    response = -99

    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception: pass
    try:
        parts = query.data.split(":")
        if len(parts) < 3: raise ValueError("Callback data rate thiếu thông tin")
        progress_id = int(parts[1])
        response = int(parts[2])
        logger.info(f"{log_prefix}: Nhận đánh giá: progress_id={progress_id}, response={response}")
        await query.answer()
    except (ValueError, IndexError):
        logger.error(f"{log_prefix}: Callback rate lỗi: {query.data}")
        await context.bot.send_message(chat_id, "❌ Lỗi dữ liệu đánh giá.")
        return
    except Exception as e_ans: logger.warning(f"{log_prefix}: Lỗi answer callback: {e_ans}")

    if message_to_delete_ref:
        try:
            await context.bot.delete_message(chat_id=message_to_delete_ref.chat_id, message_id=message_to_delete_ref.message_id)
        except Exception as e_del_back_content:
            logger.warning(f"{log_prefix}: Lỗi xóa tin nhắn mặt sau (kèm note) ID {message_to_delete_ref.message_id}: {e_del_back_content}")
    await _delete_previous_messages(context, chat_id)

    user_info = None
    actual_user_id = None
    try:
        user_info_full = get_user_by_telegram_id(telegram_id)
        if not user_info_full: raise UserNotFoundError(identifier=telegram_id)
        user_info = user_info_full
        actual_user_id = user_info_full['user_id']

        if actual_user_id:
            try:
                current_timestamp_rate = int(time.time())
                update_user_by_id(actual_user_id, last_seen=current_timestamp_rate)
            except Exception as e_update_seen_rate: logger.error(f"{log_prefix}: Lỗi khi cập nhật last_seen khi rate: {e_update_seen_rate}")

        result_service = process_review_response(actual_user_id, progress_id, response)
        if not result_service or len(result_service) != 3:
            logger.error(f"{log_prefix}: Service process_review_response trả về kết quả không hợp lệ.")
            await context.bot.send_message(chat_id, "❌ Lỗi xử lý kết quả.")
            return
        flashcard_info_updated, _, _ = result_service
        if flashcard_info_updated is None:
            error_msg = result_service[1] if isinstance(result_service[1], str) else "Lỗi không xác định từ service."
            logger.error(f"{log_prefix}: Service process_review_response báo lỗi: {error_msg}")
            await context.bot.send_message(chat_id, f"❌ Không thể xử lý kết quả đánh giá: {error_msg}")
            return

        logger.info(f"{log_prefix}: Xử lý đánh giá xong. Hiển thị thẻ tiếp theo.")
        review_mode_next = user_info.get('current_mode', DEFAULT_LEARNING_MODE)
        await display_next_card(query, context, user_info, mode=review_mode_next)

    except (DatabaseError, UserNotFoundError, ProgressNotFoundError, ValidationError, DuplicateError) as e_proc:
        logger.exception(f"{log_prefix}: Lỗi DB/Logic khi xử lý đánh giá: {e_proc}")
        await context.bot.send_message(chat_id, "❌ Lỗi xử lý kết quả, vui lòng thử lại.")
    except Exception as e_proc_unk:
        logger.exception(f"{log_prefix}: Lỗi không mong muốn khi xử lý đánh giá: {e_proc_unk}")
        await context.bot.send_message(chat_id, "❌ Lỗi hệ thống khi xử lý kết quả.")

async def handle_callback_skip_card(update, context):
    # Giữ nguyên logic
    query = update.callback_query
    if not query or not query.data or not query.from_user: return

    telegram_id = query.from_user.id
    log_prefix = f"[LEARN_SKIP_CARD|UserTG:{telegram_id}]"
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_delete_skip = query.message
    progress_id = -1

    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception: pass
    try:
        progress_id = int(query.data.split(":")[1])
        logger.info(f"{log_prefix}: Yêu cầu bỏ qua thẻ progress ID: {progress_id}")
        await query.answer("Đang bỏ qua thẻ...")
    except (ValueError, IndexError):
        await send_or_edit_message(context, chat_id, "❌ Lỗi: Dữ liệu thẻ không hợp lệ.", message_to_edit=message_to_delete_skip)
        return
    except Exception as e_ans: logger.warning(f"{log_prefix}: Lỗi answer sau khi skip: {e_ans}")

    if message_to_delete_skip:
        try:
            await context.bot.delete_message(chat_id=message_to_delete_skip.chat_id, message_id=message_to_delete_skip.message_id)
        except Exception: pass
    await _delete_previous_messages(context, chat_id)

    user_info = None
    try:
        update_result = update_progress_record_by_id(progress_id, is_skipped=1)
        if update_result <= 0:
             logger.warning(f"{log_prefix}: Không tìm thấy progress ID {progress_id} để bỏ qua hoặc không đổi.")
        user_info_skip = get_user_by_telegram_id(telegram_id)
        if not user_info_skip: raise UserNotFoundError(identifier=telegram_id)
        user_info = user_info_skip
        review_mode = user_info.get('current_mode', DEFAULT_LEARNING_MODE)
        await display_next_card(query, context, user_info, mode=review_mode)
    except (DatabaseError, ValidationError, UserNotFoundError) as e_db:
        await send_or_edit_message(context, chat_id, "❌ Lỗi khi cập nhật hoặc tải thẻ mới.", message_to_edit=None)
    except Exception as e_skip:
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi bỏ qua thẻ.", message_to_edit=None)

async def handle_callback_review_set(update, context):
    # Giữ nguyên logic
    query = update.callback_query
    if not query or not query.data or not query.from_user: return

    telegram_id = query.from_user.id
    log_prefix = f"[HANDLER_START_REVIEW_SET|UserTG:{telegram_id}]"
    set_id = -1
    message_to_edit = query.message
    chat_id = query.message.chat_id if query.message else telegram_id

    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception: pass
    try:
        set_id = int(query.data.split(":")[1])
        logger.info(f"{log_prefix}: Bắt đầu ôn tập bộ ID: {set_id} từ callback 'review_set'.")
        await query.answer()
    except (ValueError, IndexError):
        await send_or_edit_message(context, chat_id, "❌ Lỗi: Dữ liệu bộ không hợp lệ.", message_to_edit=message_to_edit)
        return
    except Exception as e_ans: logger.warning(f"{log_prefix}: Lỗi answer callback: {e_ans}")

    user_info = None
    actual_user_id = None
    try:
        user_info_review_set = get_user_by_telegram_id(telegram_id)
        if not user_info_review_set: raise UserNotFoundError(identifier=telegram_id)
        user_info = user_info_review_set
        actual_user_id = user_info_review_set['user_id']

        review_mode_for_set = MODE_DUE_ONLY_RANDOM
        try:
            current_timestamp_review_set = int(time.time())
            update_user_by_id(actual_user_id, current_set_id=set_id, current_mode=review_mode_for_set, last_seen=current_timestamp_review_set)
        except Exception as e_update_db:
            await send_or_edit_message(context, chat_id, "❌ Lỗi khi lưu lựa chọn bộ/chế độ.", message_to_edit=message_to_edit)
            return

        user_info = get_user_by_telegram_id(telegram_id) # Lấy lại user_info sau khi cập nhật
        await display_next_card(query, context, user_info, mode=review_mode_for_set)
    except (UserNotFoundError, DatabaseError) as e_db_user:
        await send_or_edit_message(context, chat_id, "❌ Đã xảy ra lỗi khi tải thông tin người dùng.", message_to_edit=message_to_edit)
    except Exception as e:
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

async def _handle_mode_command(update, context, mode):
    # Giữ nguyên logic
    if not update or not update.effective_user: return

    telegram_id = update.effective_user.id
    log_prefix = f"[LEARN_MODE_CMD|UserTG:{telegram_id}|Mode:{mode}]"
    logger.info(f"{log_prefix}: Lệnh bắt đầu mode.")
    chat_id = -1
    if update.message: chat_id = update.message.chat_id
    elif update.callback_query:
        query_obj_mode = update.callback_query
        chat_id = query_obj_mode.message.chat_id if query_obj_mode.message else telegram_id
    else: chat_id = telegram_id

    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception: pass

    actual_user_id = None
    try:
        user_info_for_update = get_user_by_telegram_id(telegram_id)
        if not user_info_for_update: raise UserNotFoundError(identifier=telegram_id)
        actual_user_id = user_info_for_update.get('user_id')

        if actual_user_id:
            try:
                current_timestamp_mode = int(time.time())
                update_user_by_id(actual_user_id, current_mode=mode, last_seen=current_timestamp_mode)
            except Exception as e_update_db:
                await context.bot.send_message(chat_id, "⚠️ Lỗi khi lưu chế độ học, đang thử tiếp tục...")
        else:
            await context.bot.send_message(chat_id, "❌ Lỗi không tìm thấy thông tin người dùng.")
            return

        user_info_display = get_user_by_telegram_id(telegram_id) # Lấy lại thông tin user sau khi cập nhật mode
        if not user_info_display: raise UserNotFoundError(identifier=telegram_id)
        await display_next_card(update, context, user_info_display, mode=mode)
    except (UserNotFoundError, DatabaseError) as e:
        await context.bot.send_message(chat_id, "❌ Lỗi tải thông tin người dùng hoặc lưu chế độ.")
    except Exception as e:
        await context.bot.send_message(chat_id, "❌ Có lỗi xảy ra khi bắt đầu học.")

async def handle_command_learn_default(update, context): await _handle_mode_command(update, context, mode=MODE_SEQ_INTERSPERSED)
async def handle_command_learn_random_new(update, context): await _handle_mode_command(update, context, mode=MODE_SEQ_RANDOM_NEW)
async def handle_command_learn_only_new(update, context): await _handle_mode_command(update, context, mode=MODE_NEW_SEQUENTIAL)
async def handle_command_review_current(update, context): await _handle_mode_command(update, context, mode=MODE_DUE_ONLY_RANDOM)
async def handle_command_review_all(update, context): await _handle_mode_command(update, context, mode=MODE_REVIEW_ALL_DUE)
async def handle_command_learn_new_random(update, context): await _handle_mode_command(update, context, mode=MODE_NEW_RANDOM)
async def handle_command_review_hardest(update, context): await _handle_mode_command(update, context, mode=MODE_REVIEW_HARDEST)
async def handle_command_cram_set(update, context): await _handle_mode_command(update, context, mode=MODE_CRAM_SET)
async def handle_command_cram_all(update, context): await _handle_mode_command(update, context, mode=MODE_CRAM_ALL)

async def handle_callback_continue_learning(update, context):
    # Giữ nguyên logic
    query = update.callback_query
    if not query or not query.from_user: return

    telegram_id = query.from_user.id
    log_prefix = f"[LEARN_CONTINUE|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix}: Xử lý callback 'continue'.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_delete_cont = query.message

    try: await query.answer()
    except Exception: pass

    if message_to_delete_cont:
        try:
            await context.bot.delete_message(chat_id=message_to_delete_cont.chat_id, message_id=message_to_delete_cont.message_id)
        except Exception: pass
    await _delete_previous_messages(context, chat_id)

    try:
        user_info_cont = get_user_by_telegram_id(telegram_id)
        if not user_info_cont: raise UserNotFoundError(identifier=telegram_id)
        mode_to_use = user_info_cont.get('current_mode', DEFAULT_LEARNING_MODE)
        await display_next_card(query, context, user_info_cont, mode=mode_to_use)
    except (UserNotFoundError, DatabaseError) as e:
        await context.bot.send_message(chat_id, "❌ Lỗi tải thông tin người dùng.")
    except Exception as e:
        await context.bot.send_message(chat_id, "❌ Có lỗi xảy ra.")

async def handle_callback_review_all(update, context):
    # Giữ nguyên logic
    query = update.callback_query
    if not query or not query.from_user: return
    log_prefix = f"[LEARN_CB_REVIEW_ALL|UserTG:{query.from_user.id}]"
    logger.info(f"{log_prefix}: Xử lý callback 'review_all'.")
    try: await query.answer()
    except Exception: pass
    try:
        await _handle_mode_command(update, context, mode=MODE_REVIEW_ALL_DUE)
    except Exception as e:
        chat_id = query.message.chat_id if query.message else query.from_user.id
        await context.bot.send_message(chat_id, "❌ Có lỗi xảy ra khi bắt đầu ôn tập tổng hợp.")

async def handle_callback_show_due_sets(update, context):
    # Giữ nguyên logic
    query = update.callback_query
    if not query or not query.from_user: return

    telegram_id = query.from_user.id
    log_prefix = f"[LEARN_SHOW_DUE_SETS|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix}: Hiển thị danh sách bộ có thẻ đến hạn.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    actual_user_id = None
    conn = None
    due_card_in_set = defaultdict(int)
    set_id_to_title = {}
    due_flashcard_ids = []

    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception: pass
    try: await query.answer()
    except Exception: pass

    try:
        user_info_due_sets = get_user_by_telegram_id(telegram_id)
        if not user_info_due_sets: raise UserNotFoundError(identifier=telegram_id)
        actual_user_id = user_info_due_sets['user_id']

        if actual_user_id: # Cập nhật last_seen
            try:
                current_timestamp_show_due = int(time.time())
                update_user_by_id(actual_user_id, last_seen=current_timestamp_show_due)
            except Exception as e_update_seen_show_due:
                logger.error(f"{log_prefix}: Lỗi khi cập nhật last_seen: {e_update_seen_show_due}")
        try:
            conn = database_connect()
            if conn is None: raise DatabaseError("Lỗi kết nối DB")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            now_ts = int(time.time())
            # Lấy các flashcard_id đến hạn
            query_due_progress = 'SELECT ufp."flashcard_id" FROM "UserFlashcardProgress" ufp WHERE ufp."user_id" = ? AND ufp."due_time" IS NOT NULL AND ufp."due_time" <= ?'
            cursor.execute(query_due_progress, (actual_user_id, now_ts))
            due_flashcard_ids = [row['flashcard_id'] for row in cursor.fetchall()]

            if not due_flashcard_ids:
                kb_back = [[InlineKeyboardButton("🔙 Menu chính", callback_data="handle_callback_back_to_main")]]
                await send_or_edit_message(context, chat_id, "🎉 Hiện tại không có thẻ nào cần ôn tập!", reply_markup=InlineKeyboardMarkup(kb_back), message_to_edit=message_to_edit)
                return

            # Lấy thông tin set_id và title cho các thẻ đến hạn
            placeholders = ','.join('?' * len(due_flashcard_ids))
            query_set_info = f'SELECT f."set_id", vs."title" FROM "Flashcards" f JOIN "VocabularySets" vs ON f."set_id" = vs."set_id" WHERE f."flashcard_id" IN ({placeholders})'
            cursor.execute(query_set_info, due_flashcard_ids)
            fetched_set_info = cursor.fetchall()

            # Đếm số thẻ đến hạn cho mỗi bộ
            for row in fetched_set_info:
                set_id_db = row['set_id']
                if set_id_db is None: continue # Bỏ qua nếu set_id là None
                due_card_in_set[set_id_db] = due_card_in_set.get(set_id_db, 0) + 1
                if set_id_db not in set_id_to_title: # Chỉ lưu title lần đầu
                    set_id_to_title[set_id_db] = row['title']

            keyboard = []
            if due_card_in_set:
                # Sắp xếp các bộ theo tên
                sorted_sets = sorted(due_card_in_set.items(), key=lambda item: set_id_to_title.get(item[0], str(item[0])).lower())
                for set_id_due, due_count in sorted_sets:
                    set_title_display = set_id_to_title.get(set_id_due, f"Bộ ID {set_id_due}")
                    callback_data = f"review_set:{set_id_due}"
                    button_text = f"📚 {html.escape(set_title_display)} ({due_count} thẻ)"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            else: # Trường hợp này ít xảy ra nếu due_flashcard_ids không rỗng
                await send_or_edit_message(context, chat_id, "Không tìm thấy bộ nào có thẻ cần ôn luyện.", message_to_edit=message_to_edit)
                return

            keyboard.append([InlineKeyboardButton("🔙 Menu chính", callback_data="handle_callback_back_to_main")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_or_edit_message(context=context, chat_id=chat_id, text="Chọn bộ muốn ôn luyện:", reply_markup=reply_markup, message_to_edit=message_to_edit)
        finally:
            if conn: conn.close()
    except (UserNotFoundError, DatabaseError, sqlite3.Error) as e_db:
        await send_or_edit_message(context, chat_id, "❌ Lỗi tìm bộ cần ôn luyện.", message_to_edit=message_to_edit)
    except Exception as e:
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

def register_handlers(app: Application):
    # Giữ nguyên logic đăng ký
    app.add_handler(CommandHandler("flashcard_learn", handle_command_learn_default))
    app.add_handler(CommandHandler("flashcard_random", handle_command_learn_random_new))
    app.add_handler(CommandHandler("flashcard_only_new", handle_command_learn_only_new))
    app.add_handler(CommandHandler("flashcard_review_current", handle_command_review_current))
    app.add_handler(CommandHandler("flashcard_review_all", handle_command_review_all))
    app.add_handler(CommandHandler("flashcard_new_random", handle_command_learn_new_random))
    app.add_handler(CommandHandler("flashcard_hardest", handle_command_review_hardest))
    app.add_handler(CommandHandler("flashcard_cram_set", handle_command_cram_set))
    app.add_handler(CommandHandler("flashcard_cram_all", handle_command_cram_all))

    app.add_handler(CallbackQueryHandler(handle_callback_flip_card, pattern=r"^flip:"))
    app.add_handler(CallbackQueryHandler(process_review_response_handler, pattern=r"^rate:"))
    app.add_handler(CallbackQueryHandler(handle_callback_skip_card, pattern='^skip:'))
    app.add_handler(CallbackQueryHandler(handle_callback_review_set, pattern=r"^review_set:"))
    app.add_handler(CallbackQueryHandler(handle_callback_continue_learning, pattern=r"^continue$"))
    app.add_handler(CallbackQueryHandler(handle_callback_review_all, pattern=r"^review_all$"))
    app.add_handler(CallbackQueryHandler(handle_callback_show_due_sets, pattern=r"^show_due_sets_for_review$"))

    logger.info("Đã đăng ký các handler cho module Learning Session (cập nhật context message).")
