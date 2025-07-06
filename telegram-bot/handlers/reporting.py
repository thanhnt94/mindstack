# Path: flashcard_v2/handlers/reporting.py
"""
Module chứa các handlers và conversation handler cho chức năng báo cáo lỗi thẻ.
Đã cập nhật luồng xem báo cáo theo thẻ với phân trang.
Sử dụng service/UI mới, gọi hàm async UI đúng cách.
Đã loại bỏ type hint và sửa lỗi cú pháp, escape MarkdownV2.
"""
import logging
import time
import html
import asyncio
import re

# Import từ thư viện telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# from telegram.ext import Application, ContextTypes, ConversationHandler # Bỏ import
from telegram.ext import (
    Application, ConversationHandler,
    MessageHandler, CommandHandler, CallbackQueryHandler, filters
)
from telegram.error import TelegramError, BadRequest, Forbidden, RetryAfter
from telegram.constants import ParseMode

# Import từ các module khác
from config import (
    DEFAULT_LEARNING_MODE, MODE_REVIEW_ALL_DUE, CAN_MANAGE_OWN_SETS
)
GETTING_REPORT_REASON = 6 # State conversation

# Import các hàm service, ui, query
from services.reporting_service import (
    submit_card_report,
    get_reportable_sets_summary,
    # resolve_card_report, # Có thể giữ lại nếu cần
    get_report_summary_by_card_in_set,
    get_pending_reports_for_card,
    resolve_all_reports_for_card
)
from ui.reporting_ui import (
    build_sets_with_reports_keyboard,
    build_reported_card_selection_keyboard,
    build_card_report_detail_display
)
from database.query_user import get_user_by_id, get_user_by_telegram_id
from database.query_card import get_card_by_id # <<< Import

# Import helpers và hàm escape
from utils.helpers import send_or_edit_message, require_permission, get_chat_display_name, escape_md_v2
from utils.exceptions import (
    DatabaseError, UserNotFoundError, PermissionsError, ValidationError,
    CardNotFoundError, SetNotFoundError, DuplicateError
)

logger = logging.getLogger(__name__)

# --- Conversation Handler cho việc gửi báo cáo ---
async def handle_callback_report_card(update, context):
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        logger.warning("handle_callback_report_card: Callback/data/user không hợp lệ.")
        return ConversationHandler.END
    reporter_telegram_id = query.from_user.id
    log_prefix = f"[REPORT_START|UserTG:{reporter_telegram_id}]"
    try:
        await query.answer("Vui lòng nhập lý do báo cáo...")
    except BadRequest as e:
        if "query is too old" not in str(e).lower():
             logger.warning(f"{log_prefix} Lỗi answer callback: {e}")
    except Exception as e_ans:
        logger.warning(f"{log_prefix} Lỗi answer callback khác: {e_ans}")
    try:
        parts = query.data.split(":")
        if len(parts) < 2: raise ValueError("Callback data thiếu flashcard_id")
        flashcard_id_to_report = int(parts[1])
        logger.info(f"{log_prefix} Bắt đầu báo cáo lỗi cho Card ID: {flashcard_id_to_report}")
        context.user_data['report_flashcard_id'] = flashcard_id_to_report
        cancel_button = InlineKeyboardButton("🚫 Hủy báo cáo", callback_data="report_cancel")
        cancel_keyboard = InlineKeyboardMarkup([[cancel_button]])
        # Escape các ký tự tĩnh cho MarkdownV2
        request_text = (
            f"📝 Vui lòng nhập lý do bạn báo cáo lỗi cho thẻ ID `{flashcard_id_to_report}` "
            f"\\(ví dụ: sai chính tả, sai nghĩa, ảnh/audio lỗi\\.\\.\\.\\)\\. \n\n" # Escape . ( )
            f"\\(Nhấn Hủy hoặc gõ /cancel để hủy\\)" # Escape ( )
        )
        await context.bot.send_message(
            chat_id=reporter_telegram_id,
            text=request_text,
            reply_markup=cancel_keyboard,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        if query.message:
            try:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
                logger.debug(f"{log_prefix} Đã xóa tin nhắn mặt sau thẻ.")
            except Exception as e_del:
                 logger.warning(f"{log_prefix} Lỗi xóa tin nhắn mặt sau thẻ: {e_del}")
        return GETTING_REPORT_REASON
    except (ValueError, IndexError):
        logger.error(f"{log_prefix} Callback data lỗi: {query.data}")
        await context.bot.send_message(reporter_telegram_id, "❌ Lỗi: Dữ liệu thẻ không hợp lệ để báo cáo.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi bắt đầu báo cáo: {e}", exc_info=True)
        await context.bot.send_message(reporter_telegram_id, "❌ Có lỗi xảy ra khi bắt đầu báo cáo.")
        return ConversationHandler.END

async def _handle_state_get_report_reason(update, context):
    if not update or not update.message or not update.effective_user or not update.message.text:
        logger.warning("_handle_state_get_report_reason: update/message/user/text không hợp lệ.")
        if update and update.message:
            await update.message.reply_text("Vui lòng nhập nội dung báo cáo bằng văn bản hoặc gõ /cancel.")
        return GETTING_REPORT_REASON
    reporter_telegram_id = update.effective_user.id
    report_text = update.message.text
    log_prefix = f"[REPORT_PROCESS|UserTG:{reporter_telegram_id}]"
    logger.info(f"{log_prefix} Nhận được nội dung báo cáo.")
    flashcard_id = context.user_data.get('report_flashcard_id')
    if not flashcard_id:
        logger.error(f"{log_prefix} Thiếu report_flashcard_id trong user_data.")
        await update.message.reply_text("❌ Lỗi: Không tìm thấy thông tin thẻ cần báo cáo. Vui lòng thử lại.")
        return ConversationHandler.END
    logger.debug(f"{log_prefix} Báo cáo cho Card ID: {flashcard_id}. Nội dung: '{report_text[:50]}...'")
    processing_msg = await update.message.reply_text("⏳ Đang gửi báo cáo của bạn...")
    submit_result = None
    reporter_user_id = None
    try:
        reporter_info = get_user_by_telegram_id(reporter_telegram_id)
        if not reporter_info or 'user_id' not in reporter_info:
            raise UserNotFoundError(identifier=reporter_telegram_id)
        reporter_user_id = reporter_info['user_id']
        submit_result = await submit_card_report(flashcard_id, reporter_user_id, report_text)
        if not submit_result or not isinstance(submit_result, dict):
             logger.error(f"{log_prefix} Service submit_card_report trả về kết quả không hợp lệ hoặc lỗi.")
             raise Exception("Lỗi xử lý báo cáo từ service.")
    except (CardNotFoundError, SetNotFoundError, ValidationError, DuplicateError, DatabaseError, UserNotFoundError) as e_submit:
        logger.error(f"{log_prefix} Lỗi đã biết khi submit report: {e_submit}")
        await send_or_edit_message(context, update.message.chat_id, f"❌ Lỗi khi xử lý báo cáo: {e_submit}", message_to_edit=processing_msg)
        context.user_data.pop('report_flashcard_id', None)
        return ConversationHandler.END
    except Exception as e_service:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi gọi service hoặc xử lý kết quả: {e_service}", exc_info=True)
        await send_or_edit_message(context, update.message.chat_id, "❌ Lỗi hệ thống khi gửi báo cáo.", message_to_edit=processing_msg)
        context.user_data.pop('report_flashcard_id', None)
        return ConversationHandler.END
    creator_user_id = submit_result.get('creator_user_id')
    card_info = submit_result.get('card_info', {})
    report_id = submit_result.get('report_id')
    if creator_user_id and creator_user_id != reporter_user_id:
        try:
            creator_info = get_user_by_id(creator_user_id)
            if creator_info and creator_info.get('telegram_id'):
                creator_telegram_id = creator_info.get('telegram_id')
                reporter_name = await get_chat_display_name(context.bot, reporter_telegram_id)
                # Sử dụng hàm escape_md_v2 đã import
                escaped_reporter = escape_md_v2(reporter_name)
                escaped_report_text = escape_md_v2(report_text)
                card_front_raw = card_info.get('front', 'N/A')
                card_back_raw = card_info.get('back', 'N/A')
                escaped_card_front = escape_md_v2(card_front_raw)
                escaped_card_back = escape_md_v2(card_back_raw)
                # Escape ký tự tĩnh
                notify_text = (
                    f"🔔 Có báo cáo lỗi mới cho thẻ ID `{flashcard_id}` trong bộ của bạn\\.\n\n"
                    f"📝 *Người báo cáo:* {escaped_reporter} \\(ID: `{reporter_telegram_id}`\\)\n"
                    f"🗒️ *Nội dung báo cáo:*\n{escaped_report_text}\n\n"
                    f"🔖 *Thông tin thẻ:*\n"
                    f"   \\- Mặt trước: {escaped_card_front}\n"
                    f"   \\- Mặt sau: {escaped_card_back}\n\n"
                    f"👉 Bạn có thể xem và xử lý báo cáo này trong menu 'Quản lý bộ thẻ' \\-\\> 'Xem Báo cáo Lỗi'\\." # Escape -> .
                )
                asyncio.create_task(
                    context.bot.send_message(
                        chat_id=creator_telegram_id,
                        text=notify_text,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                )
                logger.info(f"{log_prefix} Đã lên lịch gửi thông báo lỗi tới creator UID {creator_user_id} (TGID: {creator_telegram_id}).")
            else:
                logger.warning(f"{log_prefix} Không tìm thấy telegram_id cho creator UID {creator_user_id}. Không thể gửi thông báo.")
        except Exception as e_notify:
            logger.error(f"{log_prefix} Lỗi khi gửi thông báo cho creator: {e_notify}", exc_info=True)
    confirm_text = "✅ Đã gửi báo cáo lỗi của bạn thành công\\!" # Escape !
    review_mode = context.user_data.get('review_mode', DEFAULT_LEARNING_MODE)
    continue_callback = "review_all" if review_mode == MODE_REVIEW_ALL_DUE else "continue"
    continue_button = InlineKeyboardButton("▶️ Tiếp tục học", callback_data=continue_callback)
    confirm_keyboard = InlineKeyboardMarkup([[continue_button]])
    await send_or_edit_message(context, update.message.chat_id, confirm_text, reply_markup=confirm_keyboard, message_to_edit=processing_msg, parse_mode=ParseMode.MARKDOWN_V2)
    context.user_data.pop('report_flashcard_id', None)
    logger.debug(f"{log_prefix} Kết thúc conversation báo cáo.")
    return ConversationHandler.END

async def _handle_cancel_report(update, context):
    if not update: return ConversationHandler.END
    user_id_tg = -1; chat_id_cancel = -1; message_to_edit_cancel = None
    if update.callback_query and update.callback_query.from_user:
        query = update.callback_query; user_id_tg = query.from_user.id; chat_id_cancel = query.message.chat_id if query.message else user_id_tg; message_to_edit_cancel = query.message
        try: await query.answer()
        except Exception: pass
    elif update.message and update.effective_user: user_id_tg = update.effective_user.id; chat_id_cancel = update.message.chat_id
    else: logger.warning("_handle_cancel_report: update không hợp lệ hoặc thiếu user."); return ConversationHandler.END
    log_prefix = f"[REPORT_CANCEL|UserTG:{user_id_tg}]"; logger.info(f"{log_prefix} Hủy báo cáo lỗi.")
    context.user_data.pop("report_flashcard_id", None); logger.debug(f"{log_prefix} Đã xóa report_flashcard_id khỏi user_data.")
    review_mode = context.user_data.get('review_mode', DEFAULT_LEARNING_MODE)
    continue_callback = "review_all" if review_mode == MODE_REVIEW_ALL_DUE else "continue"
    continue_button = InlineKeyboardButton("▶️ Tiếp tục học", callback_data=continue_callback); continue_keyboard = InlineKeyboardMarkup([[continue_button]])
    cancel_message_text = "Đã hủy thao tác báo cáo lỗi."
    try:
        await send_or_edit_message(context=context, chat_id=chat_id_cancel, text=cancel_message_text, message_to_edit=message_to_edit_cancel, reply_markup=continue_keyboard)
        logger.debug(f"{log_prefix} Đã gửi/sửa xác nhận hủy.")
    except Exception as e_send_final: logger.error(f"{log_prefix} Lỗi gửi tin nhắn hủy cuối cùng: {e_send_final}")
    return ConversationHandler.END

report_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(handle_callback_report_card, pattern=r"^report_card:")
    ],
    states={
        GETTING_REPORT_REASON: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_state_get_report_reason)
        ],
    },
    fallbacks=[
        CommandHandler("cancel", _handle_cancel_report),
        CallbackQueryHandler(_handle_cancel_report, pattern='^report_cancel$')
    ],
    name="report_card_conversation",
    persistent=False,
    per_message=False
)
# --- Kết thúc Conversation Handler ---


# --- Handlers cho việc xem và xử lý báo cáo (cho Creator) ---

@require_permission(CAN_MANAGE_OWN_SETS)
async def handle_callback_view_reports_menu(update, context):
    """Handler cho callback 'view_reports_menu'."""
    query = update.callback_query
    if not query or not query.from_user: return
    creator_telegram_id = query.from_user.id
    log_prefix = f"[REPORT_VIEW_MENU|CreatorTG:{creator_telegram_id}]"
    logger.info(f"{log_prefix} Yêu cầu xem menu báo cáo lỗi.")
    chat_id = query.message.chat_id if query.message else creator_telegram_id
    message_to_edit = query.message
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    try:
        creator_info = get_user_by_telegram_id(creator_telegram_id)
        if not creator_info or 'user_id' not in creator_info:
            raise UserNotFoundError(identifier=creator_telegram_id)
        creator_user_id = creator_info['user_id']
        reportable_sets = await get_reportable_sets_summary(creator_user_id)
        text, reply_markup = build_sets_with_reports_keyboard(reportable_sets)
        parse_mode = ParseMode.MARKDOWN if reply_markup else None
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode=parse_mode)
    except (UserNotFoundError, DatabaseError) as e_db:
        logger.error(f"{log_prefix} Lỗi DB/User khi lấy báo cáo: {e_db}")
        await send_or_edit_message(context, chat_id, "❌ Lỗi tải danh sách báo cáo.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

# --- ĐÃ SỬA: Hiển thị danh sách ID thẻ có lỗi (phân trang) ---
@require_permission(CAN_MANAGE_OWN_SETS)
async def handle_callback_select_set_for_reports(update, context):
    """
    Handler cho callback 'view_set_reports:<set_id>'.
    Hiển thị danh sách (phân trang) các ID thẻ có lỗi trong bộ được chọn.
    """
    query = update.callback_query
    if not query or not query.data or not query.from_user: return
    creator_telegram_id = query.from_user.id
    log_prefix = f"[REPORT_SELECT_SET|CreatorTG:{creator_telegram_id}]"
    chat_id = query.message.chat_id if query.message else creator_telegram_id
    message_to_edit = query.message
    set_id = None
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    try:
        parts = query.data.split(":")
        if len(parts) < 2: raise ValueError("Callback data thiếu set_id")
        set_id = int(parts[1])
        logger.info(f"{log_prefix} Chọn xem báo cáo cho Set ID: {set_id}")
        creator_info = get_user_by_telegram_id(creator_telegram_id)
        if not creator_info or 'user_id' not in creator_info:
             raise UserNotFoundError(identifier=creator_telegram_id)
        creator_user_id = creator_info['user_id']
        card_summary = await get_report_summary_by_card_in_set(set_id, creator_user_id)
        # Hiển thị trang 1 đầu tiên
        text, reply_markup = build_reported_card_selection_keyboard(set_id, card_summary, current_page=1)
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode=ParseMode.MARKDOWN_V2)
    except (ValueError, IndexError): logger.error(f"{log_prefix} Callback data lỗi: {query.data}"); await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu callback.", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError) as e_db: logger.error(f"{log_prefix} Lỗi DB/User: {e_db}"); await send_or_edit_message(context, chat_id, "❌ Lỗi tải danh sách thẻ lỗi.", message_to_edit=message_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

# --- HANDLER MỚI: Xử lý phân trang danh sách ID thẻ lỗi ---
@require_permission(CAN_MANAGE_OWN_SETS)
async def handle_callback_report_card_page(update, context):
    """
    Handler cho callback 'report_card_page:<set_id>:<prev|next>:<current_page>'.
    Xử lý việc chuyển trang trong danh sách ID thẻ có lỗi.
    """
    query = update.callback_query
    if not query or not query.data or not query.from_user: return
    creator_telegram_id = query.from_user.id
    log_prefix = f"[REPORT_CARD_PAGE|CreatorTG:{creator_telegram_id}]"
    chat_id = query.message.chat_id if query.message else creator_telegram_id
    message_to_edit = query.message
    set_id = None
    action = None
    current_page = 1
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
    try:
        parts = query.data.split(":")
        if len(parts) != 4: raise ValueError("Callback data phân trang sai định dạng")
        set_id = int(parts[1])
        action = parts[2]
        current_page = int(parts[3])
        logger.info(f"{log_prefix} Phân trang cho Set ID: {set_id}, Action: {action}, Trang hiện tại: {current_page}")

        new_page = current_page
        if action == "next": new_page += 1
        elif action == "prev": new_page = max(1, current_page - 1)
        else: raise ValueError("Hành động phân trang không hợp lệ")

        creator_info = get_user_by_telegram_id(creator_telegram_id)
        if not creator_info or 'user_id' not in creator_info:
             raise UserNotFoundError(identifier=creator_telegram_id)
        creator_user_id = creator_info['user_id']

        card_summary = await get_report_summary_by_card_in_set(set_id, creator_user_id)
        text, reply_markup = build_reported_card_selection_keyboard(set_id, card_summary, current_page=new_page)
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode=ParseMode.MARKDOWN_V2)

    except (ValueError, IndexError, TypeError): logger.error(f"{log_prefix} Callback data lỗi: {query.data}"); await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu callback phân trang.", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError) as e_db: logger.error(f"{log_prefix} Lỗi DB/User: {e_db}"); await send_or_edit_message(context, chat_id, "❌ Lỗi tải danh sách thẻ lỗi.", message_to_edit=message_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra khi chuyển trang.", message_to_edit=message_to_edit)

# --- HANDLER MỚI: Xem chi tiết thẻ và báo cáo ---
@require_permission(CAN_MANAGE_OWN_SETS)
async def handle_callback_view_card_reports(update, context):
    """Handler cho callback 'view_card_reports:<flashcard_id>'."""
    query = update.callback_query
    if not query or not query.data or not query.from_user: return
    creator_telegram_id = query.from_user.id
    log_prefix = f"[REPORT_VIEW_CARD|CreatorTG:{creator_telegram_id}]"
    chat_id = query.message.chat_id if query.message else creator_telegram_id
    message_to_edit = query.message
    flashcard_id = None
    try: await query.answer()
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")

    try:
        parts = query.data.split(":")
        if len(parts) < 2: raise ValueError("Callback data thiếu flashcard_id")
        flashcard_id = int(parts[1])
        logger.info(f"{log_prefix} Chọn xem báo cáo cho Card ID: {flashcard_id}")

        creator_info = get_user_by_telegram_id(creator_telegram_id)
        if not creator_info or 'user_id' not in creator_info:
             raise UserNotFoundError(identifier=creator_telegram_id)
        creator_user_id = creator_info['user_id']

        # 1. Lấy thông tin thẻ
        card_info = get_card_by_id(flashcard_id)
        if not card_info: raise CardNotFoundError(card_id=flashcard_id)

        # 2. Lấy chi tiết các báo cáo
        pending_reports = await get_pending_reports_for_card(flashcard_id, creator_user_id)

        # 3. Gọi hàm UI async
        text, reply_markup = await build_card_report_detail_display(card_info, pending_reports, context)

        # 4. Gửi/sửa tin nhắn
        await send_or_edit_message(context, chat_id, text, reply_markup, message_to_edit=message_to_edit, parse_mode=ParseMode.MARKDOWN_V2)

    except (ValueError, IndexError): logger.error(f"{log_prefix} Callback data lỗi: {query.data}"); await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu callback.", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError, CardNotFoundError) as e_db: logger.error(f"{log_prefix} Lỗi DB/User/CardNotFound: {e_db}"); await send_or_edit_message(context, chat_id, "❌ Lỗi tải thông tin thẻ hoặc báo cáo.", message_to_edit=message_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)

# --- ĐÃ SỬA: Xử lý resolve cho cả thẻ ---
@require_permission(CAN_MANAGE_OWN_SETS)
async def handle_callback_resolve_report(update, context):
    """
    Handler cho callback 'resolve_card_reports:<flashcard_id>'.
    Đánh dấu tất cả báo cáo cho thẻ này là đã giải quyết.
    """
    query = update.callback_query
    if not query or not query.data or not query.from_user: return
    resolver_telegram_id = query.from_user.id
    log_prefix = f"[REPORT_RESOLVE_CARD|ResolverTG:{resolver_telegram_id}]"
    chat_id = query.message.chat_id if query.message else resolver_telegram_id
    message_to_edit = query.message
    flashcard_id = None
    set_id = None

    try: await query.answer("Đang đánh dấu đã xử lý...")
    except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")

    try:
        parts = query.data.split(":")
        if len(parts) != 2 or parts[0] != "resolve_card_reports": # Pattern mới
             raise ValueError("Callback data resolve_card_reports sai định dạng")
        flashcard_id = int(parts[1])
        logger.info(f"{log_prefix} Yêu cầu đánh dấu tất cả báo cáo cho card ID {flashcard_id} là đã giải quyết.")

        try:
            card_info_temp = get_card_by_id(flashcard_id)
            if card_info_temp: set_id = card_info_temp.get('set_id')
        except Exception as e_get_set: logger.warning(f"{log_prefix} Không lấy được set_id từ card_id {flashcard_id}: {e_get_set}")

        resolver_info = get_user_by_telegram_id(resolver_telegram_id)
        if not resolver_info or 'user_id' not in resolver_info:
            raise UserNotFoundError(identifier=resolver_telegram_id)
        resolver_user_id = resolver_info['user_id']

        # Gọi service mới
        resolve_result = await resolve_all_reports_for_card(flashcard_id, resolver_user_id)

        if resolve_result and isinstance(resolve_result, dict):
            updated_count = resolve_result.get('updated_count', 0)
            reporters_to_notify = resolve_result.get('reporters_to_notify', [])

            # Gửi tin nhắn mới xác nhận
            await context.bot.send_message(
                chat_id=chat_id,
                # Sửa escape sequence
                text=f"✅ Đã đánh dấu {updated_count} báo cáo cho thẻ ID `{flashcard_id}` là đã giải quyết\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )

            # Thông báo cho người báo cáo
            if reporters_to_notify:
                # Sửa escape sequence
                notify_text_base = f"🎉 Tin vui\\! Báo cáo lỗi của bạn cho thẻ ID `{flashcard_id}` đã được người tạo bộ thẻ xem xét và xử lý\\."
                send_tasks = []
                for reporter_tg_id in reporters_to_notify:
                    send_tasks.append(
                        context.bot.send_message(chat_id=reporter_tg_id, text=notify_text_base, parse_mode=ParseMode.MARKDOWN_V2)
                    )
                results = await asyncio.gather(*send_tasks, return_exceptions=True)
                success_notify = sum(1 for res in results if not isinstance(res, Exception))
                fail_notify = len(results) - success_notify
                logger.info(f"{log_prefix} Kết quả gửi thông báo giải quyết: {success_notify} thành công, {fail_notify} thất bại.")

            # Hiển thị nút quay lại danh sách thẻ lỗi của bộ
            kb_back = []
            if set_id:
                 # Quay lại trang 1 của danh sách thẻ lỗi
                 kb_back = [[InlineKeyboardButton("📊 Xem các thẻ lỗi khác", callback_data=f"view_set_reports:{set_id}")]]
            else:
                 kb_back = [[InlineKeyboardButton("📊 Xem các bộ có lỗi khác", callback_data="view_reports_menu")]]

            # Gửi thêm tin nhắn với nút quay lại (Sửa escape .)
            await context.bot.send_message(chat_id, "Hoàn thành xử lý\\.", reply_markup=InlineKeyboardMarkup(kb_back), parse_mode=ParseMode.MARKDOWN_V2)

            # Xóa tin nhắn chi tiết thẻ và lỗi cũ
            if message_to_edit:
                try: await context.bot.delete_message(chat_id=message_to_edit.chat_id, message_id=message_to_edit.message_id)
                except Exception: pass

        else:
            # Service trả về lỗi hoặc không thành công (Sửa escape ())
            await send_or_edit_message(context, chat_id, f"⚠️ Không thể cập nhật trạng thái cho các báo cáo của thẻ ID `{flashcard_id}` \\(có thể đã được xử lý hoặc không có báo cáo nào\\)\\.", message_to_edit=message_to_edit, parse_mode=ParseMode.MARKDOWN_V2)

    except (ValueError, IndexError): logger.error(f"{log_prefix} Callback data lỗi: {query.data}"); await send_or_edit_message(context, chat_id, "❌ Lỗi dữ liệu callback.", message_to_edit=message_to_edit)
    except (UserNotFoundError, DatabaseError, ValidationError) as e: logger.error(f"{log_prefix} Lỗi DB/User/Validation: {e}"); await send_or_edit_message(context, chat_id, f"❌ Lỗi khi xử lý báo cáo: {e}", message_to_edit=message_to_edit)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); await send_or_edit_message(context, chat_id, "❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)


# --- Cập nhật Đăng ký Handlers ---
def register_handlers(app):
    """Đăng ký các handler liên quan đến báo cáo lỗi thẻ."""
    logger.info("--- MODULE: Đăng ký handlers cho Reporting ---")
    app.add_handler(report_conv_handler)

    # 1. Xem danh sách các bộ có lỗi
    app.add_handler(CallbackQueryHandler(handle_callback_view_reports_menu, pattern=r"^view_reports_menu$"))
    # 2. Chọn bộ -> Hiển thị danh sách ID thẻ lỗi (trang 1)
    app.add_handler(CallbackQueryHandler(handle_callback_select_set_for_reports, pattern=r"^view_set_reports:"))
    # 2a. Xử lý phân trang cho danh sách ID thẻ lỗi
    app.add_handler(CallbackQueryHandler(handle_callback_report_card_page, pattern=r"^report_card_page:")) # Handler mới
    # 3. Chọn ID thẻ -> Hiển thị chi tiết thẻ và các báo cáo liên quan
    app.add_handler(CallbackQueryHandler(handle_callback_view_card_reports, pattern=r"^view_card_reports:")) # Handler mới
    # 4. Nhấn "Đã sửa xong" -> Xử lý tất cả báo cáo cho thẻ đó
    app.add_handler(CallbackQueryHandler(handle_callback_resolve_report, pattern=r"^resolve_card_reports:")) # Pattern mới

    logger.info("Đã đăng ký các handler cho module Reporting (đã cập nhật luồng xem theo thẻ + phân trang).")