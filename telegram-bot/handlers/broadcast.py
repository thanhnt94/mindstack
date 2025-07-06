"""
Module chứa các handlers và conversation handler cho chức năng
gửi thông báo hàng loạt (broadcast) của admin.
"""
import logging
import asyncio
import time 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters 
)
from telegram.error import BadRequest, TelegramError, Forbidden 
from config import ( 
    CAN_BROADCAST_MESSAGES,
    GETTING_BROADCAST_MESSAGE,
    CONFIRMING_BROADCAST,
    BROADCAST_SEND_DELAY 
)
from database.query_user import get_all_users 
from ui.core_ui import build_main_menu 
from utils.helpers import send_or_edit_message, require_permission 
from utils.exceptions import DatabaseError 
logger = logging.getLogger(__name__)
@require_permission(CAN_BROADCAST_MESSAGES)
async def start_broadcast_conversation(update, context):
    """Entry Point: Bắt đầu conversation để admin gửi thông báo hàng loạt."""
    if not update: return ConversationHandler.END
    if not update.effective_user: return ConversationHandler.END
    user_id = update.effective_user.id
    log_prefix = f"[BROADCAST_START|Admin:{user_id}]"
    logger.info(f"{log_prefix} Bắt đầu conversation gửi thông báo.")
    chat_id_to_reply = -1
    message_to_edit = None
    source = "Unknown"
    if update.callback_query:
        source = "Callback(start_broadcast)"
        query = update.callback_query
        try: await query.answer()
        except Exception as e_ans: logger.warning(f"{log_prefix} Lỗi answer callback: {e_ans}")
        if query.message:
            chat_id_to_reply = query.message.chat_id
            message_to_edit = query.message
        else:
            chat_id_to_reply = user_id
            logger.warning(f"{log_prefix} Callback query không có message gốc.")
    elif update.message: 
        source = "Command(/broadcast)"
        chat_id_to_reply = update.message.chat_id
        message_to_edit = None
    else:
        logger.error(f"{log_prefix} Không xác định được nguồn update.")
        return ConversationHandler.END
    cancel_button = InlineKeyboardButton("🚫 Hủy", callback_data="broadcast_cancel")
    cancel_keyboard = InlineKeyboardMarkup([[cancel_button]])
    await send_or_edit_message(
        context=context,
        chat_id=chat_id_to_reply,
        text="📝 Vui lòng gửi nội dung tin nhắn bạn muốn broadcast.\nBạn có thể dùng định dạng Markdown/HTML, gửi ảnh kèm caption, hoặc chỉ text thường.\n\n(Nhấn Hủy hoặc gõ /cancel để hủy)",
        message_to_edit=message_to_edit,
        reply_markup=cancel_keyboard
    )
    return GETTING_BROADCAST_MESSAGE
async def get_broadcast_message(update, context):
    """Handler cho state GETTING_BROADCAST_MESSAGE, xử lý tin nhắn từ admin."""
    if not update: logger.warning("get_broadcast_message: update không hợp lệ."); return GETTING_BROADCAST_MESSAGE
    if not update.effective_user: logger.warning("get_broadcast_message: user không hợp lệ."); return GETTING_BROADCAST_MESSAGE
    if not update.message: logger.warning("get_broadcast_message: message không hợp lệ."); return GETTING_BROADCAST_MESSAGE
    admin_id = update.effective_user.id
    log_prefix = f"[BROADCAST_GET_MSG|Admin:{admin_id}]"
    message = update.message 
    logger.info(f"{log_prefix} Đã nhận tin nhắn broadcast (message_id: {message.message_id}).")
    context.user_data['broadcast_message_chat_id'] = message.chat_id
    context.user_data['broadcast_message_id'] = message.message_id
    logger.info(f"{log_prefix} Đã lưu message ID: {message.message_id} từ chat ID: {message.chat_id}.")
    users_to_send_ids = []
    try:
        all_users_info = get_all_users() 
        users_to_send_ids = []
        for user in all_users_info:
            telegram_id = user.get('telegram_id')
            if telegram_id:
                users_to_send_ids.append(telegram_id)
        if not users_to_send_ids:
            await context.bot.send_message(admin_id, "⚠️ Không tìm thấy thành viên nào để gửi thông báo.")
            context.user_data.pop('broadcast_message_chat_id', None)
            context.user_data.pop('broadcast_message_id', None)
            return ConversationHandler.END
    except DatabaseError as e:
        logger.error(f"{log_prefix} Lỗi DB khi lấy danh sách user: {e}")
        await context.bot.send_message(admin_id, "❌ Lỗi lấy danh sách thành viên từ cơ sở dữ liệu.")
        return ConversationHandler.END 
    except Exception as e: 
        logger.error(f"{log_prefix} Lỗi không mong muốn khi lấy user: {e}", exc_info=True)
        await context.bot.send_message(admin_id, "❌ Có lỗi không mong muốn xảy ra khi lấy danh sách người nhận.")
        return ConversationHandler.END
    context.user_data['broadcast_user_list'] = users_to_send_ids
    num_users = len(users_to_send_ids)
    logger.info(f"{log_prefix} Sẽ gửi tới {num_users} thành viên.")
    confirm_text = f"Tin nhắn của bạn sẽ được gửi tới **{num_users}** thành viên. Nội dung như sau (preview):"
    await context.bot.send_message(admin_id, confirm_text, parse_mode='Markdown')
    try:
        await context.bot.copy_message(
            chat_id=admin_id,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
    except Exception as e_copy:
        logger.error(f"{log_prefix} Lỗi copy preview message: {e_copy}")
        await context.bot.send_message(admin_id, "(Lỗi hiển thị nội dung xem trước)")
    button_yes = InlineKeyboardButton("✅ Gửi ngay", callback_data="broadcast_confirm:yes")
    button_no = InlineKeyboardButton("🚫 Hủy bỏ", callback_data="broadcast_confirm:no")
    keyboard = [[button_yes], [button_no]] 
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(admin_id, "❓ Bạn có chắc chắn muốn gửi thông báo này không?", reply_markup=reply_markup)
    return CONFIRMING_BROADCAST
async def confirm_broadcast(update, context):
    """Handler cho state CONFIRMING_BROADCAST, xử lý nút bấm Yes/No."""
    query = update.callback_query
    if not query: logger.warning("confirm_broadcast: Callback không hợp lệ."); return ConversationHandler.END
    if not query.from_user: logger.warning("confirm_broadcast: User không hợp lệ."); return ConversationHandler.END
    if not query.data: logger.warning("confirm_broadcast: Data không hợp lệ."); return ConversationHandler.END
    admin_id = query.from_user.id
    log_prefix = f"[BROADCAST_CONFIRM|Admin:{admin_id}]"
    decision = None
    message_to_edit = query.message 
    try:
        await query.answer() 
        parts = query.data.split(":")
        if len(parts) < 2:
             raise IndexError("Callback data thiếu decision")
        decision = parts[1] 
    except (IndexError, AttributeError, BadRequest) as e:
        logger.error(f"{log_prefix} Lỗi xử lý callback xác nhận: {e}")
        await send_or_edit_message(context=context, chat_id=admin_id, text="Lỗi xử lý lựa chọn.", message_to_edit=message_to_edit)
        context.user_data.pop('broadcast_message_chat_id', None)
        context.user_data.pop('broadcast_message_id', None)
        context.user_data.pop('broadcast_user_list', None)
        return ConversationHandler.END
    if decision == "no":
        logger.info(f"{log_prefix} Admin đã hủy gửi broadcast.")
        await send_or_edit_message(context=context, chat_id=admin_id, text="Đã hủy gửi thông báo.", message_to_edit=message_to_edit, reply_markup=None)
    elif decision == "yes":
        logger.info(f"{log_prefix} Admin xác nhận gửi broadcast.")
        broadcast_chat_id = context.user_data.get('broadcast_message_chat_id')
        broadcast_msg_id = context.user_data.get('broadcast_message_id')
        user_list = context.user_data.get('broadcast_user_list')
        if not broadcast_chat_id or not broadcast_msg_id or not user_list:
            logger.error(f"{log_prefix} Thiếu dữ liệu trong user_data để gửi broadcast.")
            await send_or_edit_message(context=context, chat_id=admin_id, text="❌ Lỗi: Thiếu thông tin để gửi. Vui lòng thử lại.", message_to_edit=message_to_edit, reply_markup=None)
        else:
            num_users_bc = len(user_list)
            await send_or_edit_message(
                context=context,
                chat_id=admin_id,
                text=f"⏳ Bắt đầu gửi thông báo tới {num_users_bc} thành viên...\nBạn sẽ nhận được báo cáo khi hoàn tất.",
                message_to_edit=message_to_edit,
                reply_markup=None 
            )
            task_data = {
                'admin_id': admin_id,
                'from_chat_id': broadcast_chat_id,
                'message_id': broadcast_msg_id,
                'user_list': user_list
            }
            if context.job_queue:
                job_name = f"broadcast_{admin_id}_{int(time.time())}"
                context.job_queue.run_once( _send_broadcast_task, when=0, data=task_data, name=job_name )
                logger.info(f"{log_prefix} Đã lên lịch job gửi broadcast: {job_name}")
            else:
                logger.error(f"{log_prefix} Không tìm thấy JobQueue!")
                await context.bot.send_message(admin_id, "❌ Lỗi hệ thống: Không thể lên lịch gửi.")
    else:
        logger.warning(f"{log_prefix} Callback data không hợp lệ: {query.data}")
        await context.bot.send_message(admin_id, "Lựa chọn không hợp lệ.")
        return CONFIRMING_BROADCAST 
    context.user_data.pop('broadcast_message_chat_id', None)
    context.user_data.pop('broadcast_message_id', None)
    context.user_data.pop('broadcast_user_list', None)
    logger.debug(f"{log_prefix} Đã xóa broadcast keys.")
    return ConversationHandler.END
async def _send_broadcast_task(context: ContextTypes.DEFAULT_TYPE):
    """Hàm được gọi bởi JobQueue để thực hiện gửi broadcast."""
    if not context or not context.job or not context.job.data:
        logger.error("[BROADCAST_TASK] Thiếu context hoặc job data.")
        return
    job_data = context.job.data
    admin_id = job_data.get('admin_id')
    from_chat_id = job_data.get('from_chat_id')
    message_id = job_data.get('message_id')
    user_list = job_data.get('user_list', [])
    bot = context.bot 
    if not bot:
        logger.error("[BROADCAST_TASK] Thiếu bot instance trong context.")
        return 
    if not admin_id or not from_chat_id or not message_id or not user_list:
        logger.error(f"[BROADCAST_TASK] Thiếu dữ liệu: admin={admin_id}, from_chat={from_chat_id}, msg_id={message_id}, users={len(user_list)}")
        if admin_id:
             try:
                 await bot.send_message(admin_id, "❌ Lỗi nghiêm trọng: Thiếu dữ liệu để gửi broadcast.")
             except Exception as e_send_err:
                 logger.error(f"Lỗi gửi thông báo thiếu dữ liệu cho admin {admin_id}: {e_send_err}")
        return 
    log_prefix = f"[BROADCAST_TASK|Admin:{admin_id}]"
    logger.info(f"{log_prefix} Bắt đầu gửi tới {len(user_list)} users.")
    success_count = 0
    fail_count = 0
    for target_user_id in user_list:
        user_task_log = f"{log_prefix}[Target:{target_user_id}]"
        try:
            await bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            success_count = success_count + 1
            logger.debug(f"{user_task_log} Gửi thành công.")
        except Forbidden:
            fail_count = fail_count + 1
            logger.warning(f"{user_task_log} Gửi thất bại: Bot bị chặn.")
        except (BadRequest, TelegramError) as e_tg:
            fail_count = fail_count + 1
            logger.error(f"{user_task_log} Gửi thất bại: Lỗi Telegram - {e_tg}")
        except Exception as e_unk:
            fail_count = fail_count + 1
            logger.error(f"{user_task_log} Gửi thất bại: Lỗi không mong muốn - {e_unk}", exc_info=True)
        await asyncio.sleep(BROADCAST_SEND_DELAY)
    final_report = f"📢 Hoàn tất gửi thông báo hàng loạt:\n- Thành công: {success_count}\n- Thất bại: {fail_count}"
    logger.info(f"{log_prefix} Gửi báo cáo: {final_report}")
    try:
        await bot.send_message(admin_id, final_report)
    except Exception as e_report:
        logger.error(f"{log_prefix} Lỗi gửi báo cáo cuối cùng cho admin: {e_report}")
async def cancel_broadcast(update, context):
    """Fallback handler để hủy conversation gửi broadcast."""
    if not update: return ConversationHandler.END
    if not update.effective_user: return ConversationHandler.END
    user_id = update.effective_user.id
    log_prefix = f"[BROADCAST_CANCEL|Admin:{user_id}]"
    logger.info(f"{log_prefix} Hủy gửi thông báo.")
    context.user_data.pop('broadcast_message_chat_id', None)
    context.user_data.pop('broadcast_message_id', None)
    context.user_data.pop('broadcast_user_list', None)
    logger.debug(f"{log_prefix} Đã xóa broadcast keys khỏi user_data.")
    chat_id_cancel = user_id 
    message_to_edit_cancel = None
    parse_mode_cancel = None 
    if update.callback_query:
        query = update.callback_query
        try: await query.answer()
        except Exception: pass
        if query.message:
            message_to_edit_cancel = query.message
            chat_id_cancel = query.message.chat_id 
    elif update.message: 
        chat_id_cancel = update.message.chat_id
    reply_markup_final = None
    cancel_message_text_final = "Đã hủy gửi thông báo."
    try:
        bot_instance_cancel = context.bot if hasattr(context, 'bot') else (context.application.bot if context.application and hasattr(context.application, 'bot') else None)
        if bot_instance_cancel:
            text_menu, reply_markup_menu = await build_main_menu(user_id, bot_instance_cancel)
            if text_menu and reply_markup_menu:
                 reply_markup_final = reply_markup_menu
                 cancel_message_text_final = text_menu 
                 parse_mode_cancel = 'Markdown' 
            else:
                 logger.warning(f"{log_prefix} Lỗi build menu chính khi hủy.")
                 cancel_message_text_final = "Đã hủy. Có lỗi khi tải menu chính."
        else:
            logger.error(f"{log_prefix} Không có bot instance để build menu chính.")
            cancel_message_text_final = "Đã hủy. Lỗi hệ thống."
    except Exception as e_menu:
        logger.error(f"{log_prefix} Lỗi khi hiển thị menu chính sau khi hủy: {e_menu}", exc_info=True)
        cancel_message_text_final = "Đã hủy. Lỗi hiển thị menu."
    try:
        await send_or_edit_message(
            context=context,
            chat_id=chat_id_cancel,
            text=cancel_message_text_final,
            reply_markup=reply_markup_final,
            parse_mode=parse_mode_cancel,
            message_to_edit=message_to_edit_cancel
        )
        logger.debug(f"{log_prefix} Đã gửi/sửa tin nhắn hủy.")
    except Exception as e_send_final:
         logger.error(f"{log_prefix} Lỗi gửi tin nhắn hủy cuối cùng: {e_send_final}")
    return ConversationHandler.END
broadcast_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_broadcast_conversation, pattern='^start_broadcast$'),
        CommandHandler("broadcast", start_broadcast_conversation) 
    ],
    states={
        GETTING_BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, get_broadcast_message)], 
        CONFIRMING_BROADCAST: [CallbackQueryHandler(confirm_broadcast, pattern='^broadcast_confirm:(yes|no)$')], 
    },
    fallbacks=[
        CommandHandler('cancel', cancel_broadcast), 
        CallbackQueryHandler(cancel_broadcast, pattern='^broadcast_cancel$') 
    ],
    name="admin_broadcast_conversation", 
    persistent=False, 
    per_message=True 
)
def register_handlers(app: Application):
    """Đăng ký Conversation Handler cho chức năng broadcast."""
    app.add_handler(broadcast_conv_handler)
    logger.info("Đã đăng ký các handler cho module Broadcast (Admin).")
