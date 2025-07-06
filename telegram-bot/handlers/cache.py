"""
Module chứa các handlers cho chức năng quản lý cache audio trong phần admin.
Bao gồm hiển thị menu, dọn dẹp cache, bắt đầu/dừng job tạo cache nền.
"""
import logging
import asyncio
import functools 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackQueryHandler 
from config import CAN_MANAGE_CACHE 
from ui.admin_ui import build_admin_cache_menu 
from utils.helpers import send_or_edit_message, require_permission 
from services.audio_service import ( 
    cleanup_unused_audio_cache,
    run_background_audio_cache_job
)
logger = logging.getLogger(__name__)
async def _cache_job_done_callback_with_data(task: asyncio.Task, bot_data: dict, application: Application):
    """Hàm được gọi khi tác vụ cache nền hoàn thành, nhận bot_data và application."""
    log_prefix = "[CACHE_JOB_DONE_CB]"
    logger.info(f"{log_prefix} Tác vụ cache '{task.get_name()}' đã hoàn thành.")
    if not bot_data or not isinstance(bot_data, dict):
         logger.error(f"{log_prefix} Không nhận được bot_data hợp lệ.")
         return
    if not application or not isinstance(application, Application):
         logger.error(f"{log_prefix} Không nhận được application instance hợp lệ.")
         return
    bot = application.bot
    if not bot:
        logger.error(f"{log_prefix} Không lấy được bot instance từ application.")
        return
    status_msg = "kết thúc với lỗi không xác định"
    summary_dict = {'errors': 1} 
    try:
        result = task.result() 
        if isinstance(result, tuple) and len(result) == 2:
            status_msg_res = result[0]
            summary_dict_res = result[1]
            status_msg = status_msg_res 
            if isinstance(summary_dict_res, dict):
                 summary_dict = summary_dict_res
            else:
                 summary_dict = {'details': str(summary_dict_res)}
            logger.info(f"{log_prefix} Kết quả: status='{status_msg}', summary='{summary_dict}'")
        else:
            logger.error(f"{log_prefix} Kết quả trả về không hợp lệ: {result}")
            summary_dict = {'details': f"Kết quả không hợp lệ: {result}"}
            status_msg = "hoàn thành với kết quả lạ"
    except asyncio.CancelledError:
        status_msg = "bị hủy"
        summary_dict = {'details': "Tác vụ bị hủy bỏ."}
        logger.info(f"{log_prefix} Tác vụ bị hủy.")
    except Exception as e:
        status_msg = "kết thúc với lỗi"
        summary_dict = {'details': f"Lỗi không mong muốn khi lấy kết quả: {e}"}
        logger.exception(f"{log_prefix} Lỗi lấy kết quả task: {e}")
    bot_data['cache_job_running'] = False
    bot_data['cache_job_task'] = None
    starter_id = bot_data.pop("cache_job_starter_id", None) 
    logger.debug(f"{log_prefix} Đã cập nhật trạng thái job trong bot_data.")
    if starter_id and bot:
        summary_items = []
        for k, v in summary_dict.items():
            summary_items.append(f"{k}: {v}")
        summary_text = ", ".join(summary_items)
        final_message = f"Tác vụ tạo cache nền đã {status_msg}.\nKết quả: {summary_text}"
        try:
            asyncio.create_task(bot.send_message(chat_id=starter_id, text=final_message))
            logger.info(f"{log_prefix} Đã lên lịch gửi TB kết quả cho admin {starter_id}.")
        except Exception as send_err:
            logger.error(f"{log_prefix} Lỗi gửi TB kết quả cho admin {starter_id}: {send_err}")
    elif not starter_id:
        logger.warning(f"{log_prefix} Không tìm thấy starter_id để gửi thông báo kết quả.")
@require_permission(CAN_MANAGE_CACHE)
async def handle_callback_show_cache_menu(update, context):
    """Handler cho callback 'admin_cache:show_menu'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_show_cache_menu: Callback không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_show_cache_menu: User không hợp lệ."); return
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning(f"Lỗi answer callback cache menu: {e_ans}")
    admin_user_id = query.from_user.id
    log_prefix = f"[CACHE_MGMT_SHOW_MENU|Admin:{admin_user_id}]" 
    logger.info(f"{log_prefix} Yêu cầu menu quản lý cache.")
    chat_id = admin_user_id 
    message_to_edit = query.message
    try:
        reply_markup = build_admin_cache_menu()
        if reply_markup:
            sent_msg = await send_or_edit_message(
                context=context,
                chat_id=chat_id,
                text="🧹 Quản lý Cache Audio:",
                reply_markup=reply_markup,
                message_to_edit=message_to_edit
            )
            if not sent_msg:
                logger.error(f"{log_prefix} Lỗi gửi/sửa menu cache.")
        else:
            logger.error(f"{log_prefix} Lỗi tạo keyboard cache.")
            await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Lỗi hiển thị menu cache.", message_to_edit=message_to_edit)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi xảy ra.", message_to_edit=message_to_edit)
@require_permission(CAN_MANAGE_CACHE)
async def handle_callback_ask_clear_cache(update, context):
    """Handler cho callback 'admin_cache:ask_clear'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_ask_clear_cache: Callback không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_ask_clear_cache: User không hợp lệ."); return
    try:
        await query.answer()
    except Exception as e_ans:
         logger.warning(f"Lỗi answer callback ask clear: {e_ans}")
    admin_user_id = query.from_user.id
    chat_id = query.message.chat_id if query.message else admin_user_id
    log_prefix = f"[CACHE_MGMT_ASK_CLEAR|Admin:{admin_user_id}]" 
    logger.info(f"{log_prefix} Yêu cầu xác nhận xóa cache.")
    try:
        button_confirm = InlineKeyboardButton("🗑️ Có, xóa cache", callback_data="clear_cache:confirm")
        button_cancel = InlineKeyboardButton("🚫 Hủy", callback_data="clear_cache:cancel") 
        keyboard = [[button_confirm, button_cancel]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text="❓ Bạn chắc chắn muốn xóa cache audio không sử dụng?\n⚠️ Hành động này không thể hoàn tác.",
            reply_markup=reply_markup,
            message_to_edit=query.message
        )
        logger.debug(f"{log_prefix} Đã gửi yêu cầu xác nhận.")
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi gửi yêu cầu xác nhận: {e}", exc_info=True)
        await send_or_edit_message(context=context, chat_id=chat_id, text="❌ Có lỗi khi yêu cầu xác nhận.", message_to_edit=query.message)
@require_permission(CAN_MANAGE_CACHE)
async def handle_command_clear_cache(update, context):
    """Handler cho lệnh /flashcard_clear_cache."""
    if not update: return
    if not update.effective_user: return
    if not update.message: return
    admin_user_id = update.effective_user.id
    chat_id = update.message.chat_id
    log_prefix = f"[CACHE_MGMT_CLEAR_CMD|Admin:{admin_user_id}]" 
    logger.info(f"{log_prefix} Lệnh /flashcard_clear_cache.")
    button_confirm = InlineKeyboardButton("🗑️ Có, xóa cache", callback_data="clear_cache:confirm")
    button_cancel = InlineKeyboardButton("🚫 Hủy", callback_data="clear_cache:cancel")
    keyboard = [[button_confirm, button_cancel]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_or_edit_message(context=context, chat_id=chat_id, text="❓ Bạn chắc chắn muốn xóa cache audio không sử dụng?\n⚠️ Không thể hoàn tác.", reply_markup=reply_markup)
@require_permission(CAN_MANAGE_CACHE)
async def handle_callback_clear_cache_confirm(update, context):
    """Handler cho callback 'clear_cache:confirm' hoặc 'clear_cache:cancel'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_clear_cache_confirm: Callback không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_clear_cache_confirm: User không hợp lệ."); return
    if not query.data: logger.warning("handle_callback_clear_cache_confirm: Data không hợp lệ."); return
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning(f"Lỗi answer callback clear confirm: {e_ans}")
    admin_user_id = query.from_user.id
    chat_id = query.message.chat_id if query.message else admin_user_id
    log_prefix = f"[CACHE_MGMT_CLEAR_CB|Admin:{admin_user_id}]" 
    action = None
    result_message = "Lỗi không xác định."
    reply_markup_done = None 
    try:
        parts = query.data.split(":")
        if len(parts) < 2:
            raise IndexError("Callback data thiếu action")
        action = parts[1] 
        logger.info(f"{log_prefix} Action: {action}")
    except (IndexError, AttributeError):
        logger.error(f"{log_prefix} Callback data lỗi: {query.data}")
        await send_or_edit_message(context, chat_id, "Lỗi dữ liệu callback.", message_to_edit=query.message)
        return
    if action == "cancel":
        logger.info(f"{log_prefix} Hủy dọn cache.")
        kb_back_cache = [[InlineKeyboardButton("🔙 Quay lại Quản lý Cache", callback_data="admin_cache:show_menu")]]
        reply_markup = InlineKeyboardMarkup(kb_back_cache)
        await send_or_edit_message(context=context, chat_id=chat_id, text="Đã hủy xóa cache.", reply_markup=reply_markup, message_to_edit=query.message)
        return 
    elif action == "confirm":
        logger.info(f"{log_prefix} Xác nhận dọn cache.")
        status_message_obj = await send_or_edit_message(context=context, chat_id=chat_id, text="⏳ Đang kiểm tra và xóa cache audio không sử dụng...", reply_markup=None, message_to_edit=query.message)
        if not status_message_obj:
            logger.error(f"{log_prefix} Lỗi gửi status message.")
        loop = asyncio.get_running_loop()
        deleted_count = 0
        error_count = 0
        try:
            logger.info(f"{log_prefix} Chạy tác vụ dọn cache trong executor...")
            deleted_count, error_count = await loop.run_in_executor(None, cleanup_unused_audio_cache, "mp3")
            logger.info(f"{log_prefix} Dọn cache xong. Deleted: {deleted_count}, Errors: {error_count}")
            if deleted_count == 0 and error_count == 0:
                result_message = "✅ Không tìm thấy file cache audio nào không sử dụng."
            else:
                result_message = f"✅ Đã xóa thành công {deleted_count} file cache audio."
            if error_count > 0:
                result_message = result_message + f"\n⚠️ Có lỗi xảy ra khi xử lý {error_count} file/hash (kiểm tra log để biết chi tiết)."
        except Exception as e:
            logger.exception(f"{log_prefix} Lỗi chạy tác vụ dọn cache: {e}")
            result_message = f"❌ Lỗi nghiêm trọng khi xóa cache: {e}"
        kb_back_admin = [[InlineKeyboardButton("🔙 Quay lại Menu Admin", callback_data="flashcard_admin")]]
        reply_markup_done = InlineKeyboardMarkup(kb_back_admin)
        await send_or_edit_message(context=context, chat_id=chat_id, text=result_message, reply_markup=reply_markup_done, message_to_edit=status_message_obj)
    else:
        logger.warning(f"{log_prefix} Action không hợp lệ: {action}")
        await send_or_edit_message(context, chat_id, "Hành động không hợp lệ.", message_to_edit=query.message)
@require_permission(CAN_MANAGE_CACHE)
async def handle_callback_start_cache(update, context):
    """Handler cho callback 'admin_cache:start_job'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_start_cache: Callback không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_start_cache: User không hợp lệ."); return
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning(f"Lỗi answer callback start cache: {e_ans}")
    admin_user_id = query.from_user.id
    chat_id = query.message.chat_id if query.message else admin_user_id
    log_prefix = f"[CACHE_MGMT_START_CB|Admin:{admin_user_id}]" 
    logger.info(f"{log_prefix} Yêu cầu bắt đầu job cache qua callback.")
    bot_data = context.bot_data
    if bot_data.get('cache_job_running', False):
        logger.warning(f"{log_prefix} Job cache đã đang chạy.")
        await send_or_edit_message(context=context, chat_id=chat_id, text="⚠️ Tác vụ tạo cache hiện đang chạy.", message_to_edit=query.message)
        return
    logger.info(f"{log_prefix} Admin {admin_user_id} bắt đầu job cache.")
    kb_back_cache = [[InlineKeyboardButton("🔙 Quay lại Quản lý Cache", callback_data="admin_cache:show_menu")]]
    reply_markup_back = InlineKeyboardMarkup(kb_back_cache)
    status_msg = await send_or_edit_message(
        context=context,
        chat_id=chat_id,
        text="⏳ Bắt đầu tác vụ tạo cache audio nền...\nBạn sẽ nhận được thông báo khi hoàn thành.\nDùng nút 'Dừng Tạo Cache' để yêu cầu dừng.",
        message_to_edit=query.message,
        reply_markup=reply_markup_back 
    )
    bot_data['cache_job_running'] = True
    bot_data['cache_job_starter_id'] = admin_user_id
    bot_data['cache_job_task'] = None 
    try:
        application = context.application
        if not application:
             logger.error(f"{log_prefix} Không tìm thấy context.application.")
             raise RuntimeError("Thiếu Application instance trong context để chạy job")
        task = asyncio.create_task( run_background_audio_cache_job(), name=f"AudioCachePopulater_{admin_user_id}" )
        callback_with_data = functools.partial(_cache_job_done_callback_with_data, bot_data=context.bot_data, application=application)
        task.add_done_callback(callback_with_data)
        bot_data['cache_job_task'] = task
        logger.info(f"{log_prefix} Đã tạo task '{task.get_name()}' và thêm done callback.")
    except Exception as e_create_task:
        logger.error(f"{log_prefix} Lỗi khi tạo task cache: {e_create_task}", exc_info=True)
        bot_data['cache_job_running'] = False
        bot_data.pop("cache_job_starter_id", None)
        bot_data.pop('cache_job_task', None)
        await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text="❌ Lỗi: Không thể khởi tạo tác vụ tạo cache.",
            message_to_edit=status_msg 
        )
@require_permission(CAN_MANAGE_CACHE)
async def handle_callback_stop_cache(update, context):
    """Handler cho callback 'admin_cache:stop_job'."""
    query = update.callback_query
    if not query: logger.warning("handle_callback_stop_cache: Callback không hợp lệ."); return
    if not query.from_user: logger.warning("handle_callback_stop_cache: User không hợp lệ."); return
    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning(f"Lỗi answer callback stop cache: {e_ans}")
    admin_user_id = query.from_user.id
    chat_id = query.message.chat_id if query.message else admin_user_id
    log_prefix = f"[CACHE_MGMT_STOP_CB|Admin:{admin_user_id}]" 
    logger.info(f"{log_prefix} Yêu cầu dừng job cache qua callback.")
    bot_data = context.bot_data
    task = bot_data.get('cache_job_task') 
    is_running = bot_data.get('cache_job_running', False)
    kb_back_cache = [[InlineKeyboardButton("🔙 Quay lại Quản lý Cache", callback_data="admin_cache:show_menu")]]
    reply_markup_back = InlineKeyboardMarkup(kb_back_cache)
    if is_running and task and isinstance(task, asyncio.Task):
        if not task.done():
            logger.info(f"{log_prefix} Admin yêu cầu hủy task: {task.get_name()}")
            cancelled = task.cancel()
            if cancelled:
                logger.info(f"{log_prefix} Đã gửi yêu cầu hủy task thành công.")
                await send_or_edit_message(
                    context=context,
                    chat_id=chat_id,
                    text="✅ Đã gửi yêu cầu dừng tác vụ tạo cache.\nTác vụ sẽ dừng và bạn sẽ nhận được thông báo kết quả.",
                    message_to_edit=query.message,
                    reply_markup=reply_markup_back
                )
            else:
                logger.warning(f"{log_prefix} Không thể gửi yêu cầu hủy cho task.")
                await send_or_edit_message(
                    context=context,
                    chat_id=chat_id,
                    text="⚠️ Không thể gửi yêu cầu dừng cho tác vụ đang chạy.",
                    message_to_edit=query.message,
                    reply_markup=reply_markup_back
                )
        else:
            logger.warning(f"{log_prefix} Task đã kết thúc nhưng cờ 'running' vẫn True. Đang sửa lại trạng thái.")
            bot_data['cache_job_running'] = False
            bot_data['cache_job_task'] = None
            bot_data.pop("cache_job_starter_id", None) 
            await send_or_edit_message(
                context=context,
                chat_id=chat_id,
                text="⚠️ Tác vụ tạo cache đã kết thúc (trạng thái vừa được cập nhật).",
                message_to_edit=query.message,
                reply_markup=reply_markup_back
            )
    elif not is_running:
        logger.info(f"{log_prefix} Tác vụ không chạy (cờ running là False).")
        await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text="✅ Tác vụ tạo cache hiện không chạy.",
            message_to_edit=query.message,
            reply_markup=reply_markup_back
        )
        bot_data['cache_job_task'] = None
        bot_data.pop("cache_job_starter_id", None)
    else: 
        logger.warning(f"{log_prefix} Trạng thái lỗi: Job đang chạy nhưng không có task hợp lệ.")
        bot_data['cache_job_running'] = False
        bot_data.pop('cache_job_task', None)
        bot_data.pop("cache_job_starter_id", None)
        await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text="⚠️ Trạng thái tác vụ tạo cache bị lỗi, đã được đặt lại.",
            message_to_edit=query.message,
            reply_markup=reply_markup_back
        )
@require_permission(CAN_MANAGE_CACHE)
async def handle_command_start_cache_job(update, context):
    """Handler cho lệnh /flashcard_cache_start."""
    if not update: return
    if not update.effective_user: return
    if not update.message: return
    admin_user_id = update.effective_user.id
    chat_id = update.message.chat_id
    log_prefix = f"[CACHE_MGMT_START_CMD|Admin:{admin_user_id}]" 
    logger.info(f"{log_prefix} Lệnh /flashcard_cache_start.")
    bot_data = context.bot_data
    if bot_data.get('cache_job_running', False):
        await send_or_edit_message(context=context, chat_id=chat_id, text="⚠️ Tác vụ tạo cache hiện đang chạy.")
        return
    logger.info(f"{log_prefix} Admin {admin_user_id} bắt đầu job cache bằng lệnh.")
    status_msg = await send_or_edit_message(context=context, chat_id=chat_id, text="⏳ Bắt đầu tác vụ tạo cache audio nền...\nBạn sẽ nhận được thông báo khi hoàn thành.\nDùng /flashcard_cache_stop để yêu cầu dừng.")
    bot_data['cache_job_running'] = True
    bot_data['cache_job_starter_id'] = admin_user_id
    bot_data['cache_job_task'] = None
    try:
        application = context.application
        if not application: raise RuntimeError("Thiếu Application instance")
        task = asyncio.create_task( run_background_audio_cache_job(), name=f"AudioCachePopulater_{admin_user_id}" )
        callback_with_data = functools.partial(_cache_job_done_callback_with_data, bot_data=context.bot_data, application=application)
        task.add_done_callback(callback_with_data)
        bot_data['cache_job_task'] = task
        logger.info(f"{log_prefix} Đã tạo task '{task.get_name()}' và thêm done callback.")
    except Exception as e_create_task:
        logger.error(f"{log_prefix} Lỗi khi tạo task cache: {e_create_task}", exc_info=True)
        bot_data['cache_job_running'] = False
        bot_data.pop("cache_job_starter_id", None)
        bot_data.pop('cache_job_task', None)
        await send_or_edit_message(
            context=context,
            chat_id=chat_id,
            text="❌ Lỗi: Không thể khởi tạo tác vụ tạo cache.",
            message_to_edit=status_msg
        )
@require_permission(CAN_MANAGE_CACHE)
async def handle_command_stop_cache_job(update, context):
    """Handler cho lệnh /flashcard_cache_stop."""
    if not update: return
    if not update.effective_user: return
    if not update.message: return
    admin_user_id = update.effective_user.id
    chat_id = update.message.chat_id
    log_prefix = f"[CACHE_MGMT_STOP_CMD|Admin:{admin_user_id}]" 
    logger.info(f"{log_prefix} Lệnh /flashcard_cache_stop.")
    bot_data = context.bot_data
    task = bot_data.get('cache_job_task')
    is_running = bot_data.get('cache_job_running', False)
    if is_running and task and isinstance(task, asyncio.Task):
        if not task.done():
            logger.info(f"{log_prefix} Admin yêu cầu hủy task: {task.get_name()} bằng lệnh.")
            cancelled = task.cancel()
            if cancelled:
                logger.info(f"{log_prefix} Đã gửi yêu cầu hủy task thành công.")
                await send_or_edit_message(context=context, chat_id=chat_id, text="✅ Đã gửi yêu cầu dừng tác vụ tạo cache.")
            else:
                logger.warning(f"{log_prefix} Không thể gửi yêu cầu hủy cho task.")
                await send_or_edit_message(context=context, chat_id=chat_id, text="⚠️ Không thể gửi yêu cầu dừng cho tác vụ đang chạy.")
        else:
            logger.warning(f"{log_prefix} Task đã kết thúc nhưng cờ 'running' vẫn True (lệnh).")
            bot_data['cache_job_running'] = False; bot_data['cache_job_task'] = None; bot_data.pop("cache_job_starter_id", None)
            await send_or_edit_message( context=context, chat_id=chat_id, text="⚠️ Tác vụ tạo cache đã kết thúc (trạng thái được cập nhật)." )
    elif not is_running:
        logger.info(f"{log_prefix} Tác vụ không chạy (lệnh).")
        await send_or_edit_message( context=context, chat_id=chat_id, text="✅ Tác vụ tạo cache hiện không chạy." )
        bot_data['cache_job_task'] = None; bot_data.pop("cache_job_starter_id", None)
    else:
        logger.warning(f"{log_prefix} Trạng thái lỗi: Job đang chạy nhưng không có task (lệnh).")
        bot_data['cache_job_running'] = False; bot_data.pop('cache_job_task', None); bot_data.pop("cache_job_starter_id", None)
        await send_or_edit_message( context=context, chat_id=chat_id, text="⚠️ Trạng thái tác vụ tạo cache bị lỗi, đã được đặt lại." )
def register_handlers(app: Application):
    """Đăng ký các handler liên quan đến quản lý cache audio (admin)."""
    app.add_handler(CommandHandler("flashcard_clear_cache", handle_command_clear_cache))
    app.add_handler(CommandHandler("flashcard_cache_start", handle_command_start_cache_job))
    app.add_handler(CommandHandler("flashcard_cache_stop", handle_command_stop_cache_job))
    app.add_handler(CallbackQueryHandler(handle_callback_show_cache_menu, pattern=r"^admin_cache:show_menu$"))
    app.add_handler(CallbackQueryHandler(handle_callback_ask_clear_cache, pattern=r"^admin_cache:ask_clear$"))
    app.add_handler(CallbackQueryHandler(handle_callback_clear_cache_confirm, pattern=r"^clear_cache:")) 
    app.add_handler(CallbackQueryHandler(handle_callback_start_cache, pattern=r"^admin_cache:start_job$"))
    app.add_handler(CallbackQueryHandler(handle_callback_stop_cache, pattern=r"^admin_cache:stop_job$"))
    logger.info("Đã đăng ký các handler cho module Cache Management (Admin).")
