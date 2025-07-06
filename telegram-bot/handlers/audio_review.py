"""
Module chứa các handlers cho chức năng ôn tập bằng audio.
Các hàm đã được cập nhật để lấy user_id từ telegram_id và sử dụng user_id
khi gọi các hàm service/database. Đã thêm send_chat_action.
"""
import logging
import asyncio
import sqlite3
import os
import time
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackQueryHandler 
from telegram.error import BadRequest, TelegramError, Forbidden
from telegram.constants import ChatAction
from config import ( 
    AUDIO_REVIEW_CALLBACK_PREFIX,
    CAN_EXPORT_AUDIO, 
    AUDIO_N_OPTIONS, 
    BASE_DIR 
)
from database.connection import database_connect 
from database.query_set import get_sets 
from database.query_user import get_user_by_telegram_id 
from services.audio_service import generate_review_audio_compilation, get_card_ids_for_audio 
from utils.helpers import send_or_edit_message, require_permission 
from utils.exceptions import DatabaseError, SetNotFoundError, UserNotFoundError 
from ui.core_ui import build_audio_n_selection_keyboard 
logger = logging.getLogger(__name__)
@require_permission(CAN_EXPORT_AUDIO)
async def handle_command_audio_review(update, context):
    """Handler cho lệnh /flashcard_audioreview."""
    if not update: logger.warning("handle_command_audio_review: update không hợp lệ."); return
    if not update.effective_user: logger.warning("handle_command_audio_review: user không hợp lệ."); return
    if not update.message: logger.warning("handle_command_audio_review: message không hợp lệ."); return
    user_id_tg = update.effective_user.id
    chat_id = update.message.chat_id
    log_prefix = f"[AUDIOREVIEW_CMD|UserTG:{user_id_tg}]" 
    logger.info(f"{log_prefix} Lệnh /flashcard_audioreview.")
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception as e_action:
        logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")
    keyboard = [
        [InlineKeyboardButton("🎧 Chọn Bộ để Tạo Audio", callback_data=f"{AUDIO_REVIEW_CALLBACK_PREFIX}:choose_set")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent_msg = await send_or_edit_message(
        context=context,
        chat_id=chat_id,
        text="Chọn bộ từ bạn muốn tạo audio ôn tập:",
        reply_markup=reply_markup
    )
    if not sent_msg:
        logger.error(f"{log_prefix} Lỗi gửi nút chọn bộ.")
async def handle_callback_audio_choose_set(update, context):
    """Hiển thị danh sách các bộ từ user đã học để chọn tạo audio."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_audio_choose_set: callback query không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_audio_choose_set: user không hợp lệ."); return
    telegram_id = query.from_user.id
    log_prefix = f"[AUDIOREVIEW_CHOOSE_SET|UserTG:{telegram_id}]" 
    logger.info(f"{log_prefix} Đang chọn bộ để tạo audio.")
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    if chat_id != -1:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action:
            logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    conn = None
    sets_with_progress = []
    actual_user_id = None
    try:
        logger.debug(f"{log_prefix} Lấy user_id...")
        user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']
        logger.debug(f"{log_prefix} Lấy được user_id: {actual_user_id}")
        try:
            conn = database_connect()
            if conn is None: raise DatabaseError("Không thể kết nối DB.")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query_learned_sets = """
                SELECT DISTINCT vs.set_id, vs.title
                FROM UserFlashcardProgress ufp
                JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id
                JOIN VocabularySets vs ON f.set_id = vs.set_id
                WHERE ufp.user_id = ? ORDER BY vs.title COLLATE NOCASE
            """
            cursor.execute(query_learned_sets, (actual_user_id,))
            sets_with_progress = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"{log_prefix} Tìm thấy {len(sets_with_progress)} bộ user đã học.")
        finally:
            if conn: conn.close()
        if not sets_with_progress:
            logger.warning(f"{log_prefix} User {actual_user_id} chưa học bộ nào.")
            kb_back = [[InlineKeyboardButton("🔙 Menu chính", callback_data="handle_callback_back_to_main")]]
            await send_or_edit_message(context, chat_id, "Bạn chưa học bộ từ nào để tạo audio.", reply_markup=InlineKeyboardMarkup(kb_back), message_to_edit=message_to_edit)
            return
        keyboard = []
        for set_data in sets_with_progress:
            set_id = set_data.get('set_id'); set_title = set_data.get('title')
            if set_id is None or set_title is None: continue
            callback_data = f"{AUDIO_REVIEW_CALLBACK_PREFIX}:show_options:{set_id}"
            keyboard.append([InlineKeyboardButton(f"📚 {html.escape(set_title)}", callback_data=callback_data)])
        keyboard.append([InlineKeyboardButton("🔙 Menu chính", callback_data="handle_callback_back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_msg = await send_or_edit_message(context=context, chat_id=chat_id, text="Chọn bộ bạn muốn tạo audio:", reply_markup=reply_markup, message_to_edit=message_to_edit)
        if not sent_msg: logger.error(f"{log_prefix} Lỗi hiển thị danh sách bộ.")
    except (UserNotFoundError, DatabaseError, sqlite3.Error) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User khi lấy list bộ từ: {e_db}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Lỗi tải danh sách bộ từ.", message_to_edit=message_to_edit)
    except Exception as e:
         logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
         await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)
async def handle_callback_audio_show_options(update, context):
    """Handler cho callback 'audioreview:show_options:<set_id>'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_audio_show_options: Callback không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_audio_show_options: User không hợp lệ."); return
    if not query.data: logger.warning("handle_callback_audio_show_options: Data không hợp lệ."); return
    telegram_id = query.from_user.id
    log_prefix = f"[AUDIOREVIEW_SHOW_OPTIONS|UserTG:{telegram_id}]" 
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    set_id = None
    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action: logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    try:
        parts = query.data.split(":")
        if len(parts) < 3: raise ValueError("Callback data thiếu set_id")
        set_id = int(parts[2])
        logger.info(f"{log_prefix} Hiển thị tùy chọn audio cho Set ID: {set_id}")
        set_info_tuple = get_sets(columns=["title"], set_id=set_id) 
        set_info = set_info_tuple[0][0] if set_info_tuple and set_info_tuple[0] else None
        if not set_info: raise SetNotFoundError(set_id=set_id)
        set_title = set_info.get('title', f"Bộ {set_id}")
        keyboard = [
            [InlineKeyboardButton("✅ Tất cả từ đã học", callback_data=f"{AUDIO_REVIEW_CALLBACK_PREFIX}:trigger:set_all:{set_id}")],
            [InlineKeyboardButton("🕒 Các từ mới học gần nhất", callback_data=f"{AUDIO_REVIEW_CALLBACK_PREFIX}:show_n_options:set_recent:{set_id}")],
            [InlineKeyboardButton("⏳ Các từ học lâu nhất", callback_data=f"{AUDIO_REVIEW_CALLBACK_PREFIX}:show_n_options:set_oldest:{set_id}")],
            [InlineKeyboardButton("🔙 Quay lại Chọn bộ", callback_data=f"{AUDIO_REVIEW_CALLBACK_PREFIX}:choose_set")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        escaped_set_title = html.escape(set_title)
        sent_msg = await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text=f"Chọn loại thẻ muốn tạo audio cho bộ '**{escaped_set_title}**':",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            message_to_edit=message_to_edit
        )
        if not sent_msg: logger.error(f"{log_prefix} Lỗi hiển thị tùy chọn audio.")
    except (ValueError, IndexError):
        logger.error(f"{log_prefix} Callback data lỗi: {query.data}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi: Dữ liệu callback không hợp lệ.", message_to_edit=message_to_edit)
    except SetNotFoundError:
        logger.warning(f"{log_prefix} Không tìm thấy Set ID {set_id}.")
        await send_or_edit_message(context, chat_id, "❌ Không tìm thấy bộ từ này.", message_to_edit=message_to_edit)
    except DatabaseError as e:
        logger.error(f"{log_prefix} Lỗi DB khi lấy thông tin set {set_id}: {e}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi tải thông tin bộ từ.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)
async def handle_callback_audio_show_n_options(update, context):
    """Handler cho callback 'audioreview:show_n_options:<mode>:<set_id>'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_audio_show_n_options: Callback không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_audio_show_n_options: User không hợp lệ."); return
    if not query.data: logger.warning("handle_callback_audio_show_n_options: Data không hợp lệ."); return
    telegram_id = query.from_user.id
    log_prefix = f"[AUDIOREVIEW_SHOW_N|UserTG:{telegram_id}]" 
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e_action: logger.warning(f"{log_prefix} Lỗi gửi chat action: {e_action}")
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    try:
        parts = query.data.split(":")
        if len(parts) != 4 or parts[1] != "show_n_options":
            raise ValueError("Format callback show_n_options không đúng")
        mode = parts[2] 
        set_id = int(parts[3])
        logger.info(f"{log_prefix} Yêu cầu chọn N cho mode={mode}, set_id={set_id}")
        reply_markup = build_audio_n_selection_keyboard(mode, set_id)
        if reply_markup:
            sent_msg = await send_or_edit_message(
                context=context,
                chat_id=chat_id,
                text="Chọn số lượng thẻ (N) bạn muốn đưa vào file audio:",
                reply_markup=reply_markup,
                message_to_edit=message_to_edit
            )
            if not sent_msg: logger.error(f"{log_prefix} Lỗi hiển thị keyboard chọn N.")
        else:
            logger.error(f"{log_prefix} Lỗi tạo keyboard chọn N (có thể do config AUDIO_N_OPTIONS lỗi).")
            await send_or_edit_message(context, chat_id, "Lỗi tạo danh sách lựa chọn số lượng.", message_to_edit=message_to_edit)
    except (ValueError, IndexError, TypeError) as e_parse:
        logger.error(f"{log_prefix} Lỗi parse callback data '{query.data}': {e_parse}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu callback.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)
async def handle_callback_audio_select_n(update, context):
    """Handler cho callback 'audioreview:trigger:<mode>:<set_id>:<n>'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_audio_select_n: Callback không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_audio_select_n: User không hợp lệ."); return
    if not query.data: logger.warning("handle_callback_audio_select_n: Data không hợp lệ."); return
    telegram_id = query.from_user.id
    log_prefix = f"[AUDIOREVIEW_SELECT_N|UserTG:{telegram_id}]" 
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message 
    actual_user_id = None
    set_id = None
    mode = None
    n_cards = None
    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        except Exception as e_action: logger.warning(f"{log_prefix} Lỗi gửi chat action upload: {e_action}")
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    try:
        parts = query.data.split(":")
        if len(parts) != 5 or parts[1] != "trigger":
            raise ValueError("Format callback trigger audio N không đúng")
        mode = parts[2] 
        set_id = int(parts[3])
        n_cards = int(parts[4])
        logger.info(f"{log_prefix} User chọn N={n_cards}, mode={mode}, set_id={set_id}")
        logger.debug(f"{log_prefix} Lấy user_id...")
        user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']
        logger.debug(f"{log_prefix} Lấy được user_id: {actual_user_id}")
        card_ids = None
        loop = asyncio.get_running_loop()
        logger.debug(f"{log_prefix} Gọi service get_card_ids_for_audio...")
        card_ids = await loop.run_in_executor(None, get_card_ids_for_audio, actual_user_id, set_id, mode, n_cards)
        if card_ids is None: 
             await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi: Dữ liệu yêu cầu không hợp lệ hoặc lỗi truy vấn.", message_to_edit=message_to_edit)
             return
        elif not card_ids: 
            await send_or_edit_message(context=context, chat_id=chat_id, text=f"Không tìm thấy thẻ nào khớp yêu cầu (N={n_cards}) trong bộ này.", message_to_edit=message_to_edit)
            return
        await _initiate_audio_compilation_task(update, context, card_ids, set_id)
    except (ValueError, IndexError, TypeError) as e_parse:
        logger.error(f"{log_prefix} Lỗi parse callback data '{query.data}': {e_parse}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu callback lựa chọn N.", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User khi xử lý: {e_db}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Lỗi tải dữ liệu thẻ từ database.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi xử lý lựa chọn N.", message_to_edit=message_to_edit)
async def handle_callback_audio_trigger_set_all(update, context):
    """Handler cho callback 'audioreview:trigger:set_all:<set_id>'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_audio_trigger_set_all: Callback không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_audio_trigger_set_all: User không hợp lệ."); return
    if not query.data: logger.warning("handle_callback_audio_trigger_set_all: Data không hợp lệ."); return
    telegram_id = query.from_user.id
    log_prefix = f"[AUDIOREVIEW_SET_ALL|UserTG:{telegram_id}]" 
    chat_id = query.message.chat_id if query.message else telegram_id
    message_to_edit = query.message
    set_id = None
    actual_user_id = None
    if chat_id != -1:
        try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        except Exception as e_action: logger.warning(f"{log_prefix} Lỗi gửi chat action upload: {e_action}")
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    try:
        parts = query.data.split(":")
        if len(parts) < 4: raise ValueError("Callback data thiếu set_id")
        set_id = int(parts[3])
        logger.info(f"{log_prefix} Yêu cầu audio 'set_all' cho Set ID: {set_id}")
        logger.debug(f"{log_prefix} Lấy user_id...")
        user_info = get_user_by_telegram_id(telegram_id)
        actual_user_id = user_info['user_id']
        logger.debug(f"{log_prefix} Lấy được user_id: {actual_user_id}")
        card_ids = None
        loop = asyncio.get_running_loop()
        logger.debug(f"{log_prefix} Gọi service get_card_ids_for_audio...")
        card_ids = await loop.run_in_executor(None, get_card_ids_for_audio, actual_user_id, set_id, 'set_all', None)
        if card_ids is None: 
             await send_or_edit_message(context, chat_id, "❌ Lỗi: Dữ liệu yêu cầu không hợp lệ hoặc lỗi truy vấn.", message_to_edit=message_to_edit)
             return
        elif not card_ids: 
            logger.warning(f"{log_prefix} Không có thẻ đã học trong bộ {set_id}.")
            kb_back = [[InlineKeyboardButton("🔙 Quay lại", callback_data=f"{AUDIO_REVIEW_CALLBACK_PREFIX}:show_options:{set_id}")]]
            await send_or_edit_message(context, chat_id, "Bạn chưa học từ nào trong bộ này để tạo audio.", reply_markup=InlineKeyboardMarkup(kb_back), message_to_edit=message_to_edit)
            return
        await _initiate_audio_compilation_task(update, context, card_ids, set_id)
    except (ValueError, IndexError):
        logger.error(f"{log_prefix} Callback data lỗi: {query.data}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi: Dữ liệu callback không hợp lệ.", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User khi xử lý: {e_db}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Lỗi tải danh sách thẻ từ database.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)
async def _initiate_audio_compilation_task(update, context, card_ids, set_id):
    """
    Hàm nội bộ để bắt đầu quá trình tạo file audio tổng hợp và gửi cho người dùng.
    """
    user_id_tg = None
    if update.callback_query and update.callback_query.from_user: user_id_tg = update.callback_query.from_user.id
    elif update.effective_user: user_id_tg = update.effective_user.id
    if not user_id_tg: logger.error("[_initiate_audio_compilation_task] Không thể xác định telegram_id."); return
    chat_id_for_status = update.callback_query.message.chat_id if update.callback_query and update.callback_query.message else user_id_tg
    message_to_edit_status = update.callback_query.message if update.callback_query else None
    log_prefix = f"[_INITIATE_AUDIO_COMP|UserTG:{user_id_tg}|Set:{set_id}]"; logger.info(f"{log_prefix} Bắt đầu tạo audio cho {len(card_ids)} thẻ.")
    status_message = None; set_title = f"Bộ {set_id}"; output_filepath = None; loop = asyncio.get_running_loop()
    try: await context.bot.send_chat_action(chat_id=chat_id_for_status, action=ChatAction.UPLOAD_DOCUMENT)
    except Exception as e_action: logger.warning(f"{log_prefix} Lỗi gửi chat action upload: {e_action}")
    try:
        try:
            set_info_tuple = get_sets(set_id=set_id); set_info = set_info_tuple[0][0] if set_info_tuple and set_info_tuple[0] else None
            if set_info: set_title = set_info.get('title', set_title)
        except (SetNotFoundError, DatabaseError) as e_title: logger.warning(f"{log_prefix} Lỗi lấy tên bộ: {e_title}. Dùng tên mặc định.")
        escaped_title_status = html.escape(set_title); status_message_text = f"⏳ Đang tạo audio cho {len(card_ids)} thẻ từ '**{escaped_title_status}**'... Xin chờ một lát nhé!"
        status_message = await send_or_edit_message(context=context, chat_id=chat_id_for_status, text=status_message_text, parse_mode='Markdown', reply_markup=None, message_to_edit=message_to_edit_status)
        if not status_message: logger.error(f"{log_prefix} Lỗi gửi/sửa status.")
        conn = None; audio_contents = []
        try:
            conn = database_connect();
            if conn is None: raise DatabaseError("Lỗi kết nối DB.")
            cursor = conn.cursor(); placeholders = ','.join('?' * len(card_ids))
            sql_get_audio = f"SELECT back_audio_content FROM Flashcards WHERE flashcard_id IN ({placeholders})"
            cursor.execute(sql_get_audio, card_ids)
            audio_contents = [row[0] for row in cursor.fetchall() if row and row[0] and row[0].strip()]
            logger.info(f"{log_prefix} Tìm thấy {len(audio_contents)} nội dung audio cần ghép.")
        except (sqlite3.Error, DatabaseError) as e_db_content:
            logger.error(f"{log_prefix} Lỗi DB lấy audio content: {e_db_content}", exc_info=True); await send_or_edit_message(context=context, chat_id=chat_id_for_status, text="❌ Lỗi lấy dữ liệu audio từ database.", message_to_edit=status_message); return
        finally:
            if conn: conn.close()
        if not audio_contents:
            logger.warning(f"{log_prefix} Không có audio content để tạo file."); await send_or_edit_message(context=context, chat_id=chat_id_for_status, text="ℹ️ Không có nội dung audio nào trong các thẻ được chọn.", message_to_edit=status_message); return
        logger.info(f"{log_prefix} Gọi generate_review_audio_compilation...")
        output_filepath = await generate_review_audio_compilation(audio_contents, pause_ms=2000)
        final_status_text = "❌ Lỗi tạo audio."; file_sent_successfully = False
        if output_filepath:
            file_exists = await loop.run_in_executor(None, os.path.exists, output_filepath)
            if file_exists:
                logger.info(f"{log_prefix} Tạo audio OK: {output_filepath}. Gửi file...")
                try:
                    safe_title_file = "".join(c for c in set_title if c.isalnum() or c in ('_', '-')).strip() or f"set_{set_id}"
                    with open(output_filepath, 'rb') as audio_file_obj:
                        await context.bot.send_audio(chat_id=user_id_tg, audio=audio_file_obj, title=f"Audio_{safe_title_file}.mp3", caption=f"Audio ôn tập {len(audio_contents)} thẻ từ bộ '{html.escape(set_title)}'.")
                    logger.info(f"{log_prefix} Gửi file OK."); final_status_text = ""; file_sent_successfully = True
                except (Forbidden, BadRequest, TelegramError) as send_err_tg:
                    logger.error(f"{log_prefix} Lỗi Telegram gửi file audio: {send_err_tg}"); final_status_text = f"❌ Tạo OK nhưng lỗi gửi file: {send_err_tg}"
                except Exception as send_err:
                    logger.error(f"{log_prefix} Lỗi khác gửi file audio: {send_err}", exc_info=True); final_status_text = f"❌ Tạo OK nhưng lỗi gửi file: {send_err}"
            else: logger.error(f"{log_prefix} Lỗi lạ: Service báo OK nhưng file không tồn tại."); final_status_text = "❌ Lỗi: File audio kết quả không được tạo ra."
        else: logger.error(f"{log_prefix} Tạo audio thất bại (service trả về None)."); final_status_text = "❌ Lỗi khi tạo file audio tổng hợp."
        if final_status_text and status_message: await send_or_edit_message(context=context, chat_id=chat_id_for_status, text=final_status_text, message_to_edit=status_message)
        elif final_status_text: await send_or_edit_message(context=context, chat_id=chat_id_for_status, text=final_status_text)
        elif status_message and file_sent_successfully:
             try: await context.bot.delete_message(chat_id=status_message.chat_id, message_id=status_message.message_id); logger.info(f"{log_prefix} Đã xóa tin nhắn trạng thái.")
             except Exception as e_del: logger.warning(f"{log_prefix} Lỗi xóa tin nhắn trạng thái: {e_del}")
    except Exception as e_compile:
        logger.exception(f"{log_prefix} Lỗi trong quá trình tạo/gửi audio: {e_compile}"); await send_or_edit_message(context=context, chat_id=chat_id_for_status, text="❌ Lỗi hệ thống khi tạo audio.", message_to_edit=status_message)
    finally:
        if output_filepath:
            def remove_if_exists_sync_final(path):
                if os.path.exists(path):
                    try: os.remove(path); return True
                    except Exception as inner_remove_err: logger.error(f"[SYNC_REMOVE_FINAL_AUDIO] Lỗi xóa file {path}: {inner_remove_err}"); return False
                return False
            try:
                removed = await loop.run_in_executor(None, remove_if_exists_sync_final, output_filepath)
                if removed: logger.info(f"{log_prefix} Đã xóa file tạm audio tổng hợp: {output_filepath}")
            except Exception as e_remove: logger.error(f"{log_prefix} Lỗi xóa file tạm audio tổng hợp {output_filepath}: {e_remove}")
def register_handlers(app: Application):
    """Đăng ký các handler cho chức năng tạo audio ôn tập."""
    app.add_handler(CommandHandler("flashcard_audioreview", handle_command_audio_review))
    prefix = AUDIO_REVIEW_CALLBACK_PREFIX
    app.add_handler(CallbackQueryHandler(handle_callback_audio_choose_set, pattern=f"^{prefix}:choose_set$"))
    app.add_handler(CallbackQueryHandler(handle_callback_audio_show_options, pattern=f"^{prefix}:show_options:"))
    app.add_handler(CallbackQueryHandler(handle_callback_audio_trigger_set_all, pattern=f"^{prefix}:trigger:set_all:"))
    app.add_handler(CallbackQueryHandler(handle_callback_audio_show_n_options, pattern=f"^{prefix}:show_n_options:"))
    app.add_handler(CallbackQueryHandler(handle_callback_audio_select_n, pattern=f"^{prefix}:trigger:(set_recent|set_oldest):"))
    logger.info("Đã đăng ký các handler cho module Audio Review.")
