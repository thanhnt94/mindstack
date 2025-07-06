# File: flashcard-telegram-bot/handlers/notes.py
"""
Module chứa các handlers cho chức năng quản lý ghi chú (notes) của flashcard.
(Sửa lần 1: Thêm tính năng đính kèm 1 ảnh vào note).
(Sửa lần 2: Sửa lỗi TypeError khi gọi send_or_edit_message).
(Sửa lần 3: Sửa lỗi Pylance "is not defined" và register_handlers).
(Sửa lần 4: Thiết kế lại luồng ConversationHandler để cho phép gửi text hoặc ảnh+caption trực tiếp).
(Sửa lần 5: Cập nhật thông báo lưu note để hiển thị nội dung và thêm nút sửa).
(Sửa lần 6: Bỏ tin nhắn xác nhận riêng, gọi _display_card_backside để hiển thị note trên mặt sau thẻ).
"""

import logging
import html
import os
import uuid

from telegram import Update
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram.ext import Application
from telegram.ext import ConversationHandler
from telegram.ext import MessageHandler
from telegram.ext import CommandHandler
from telegram.ext import CallbackQueryHandler
from telegram.ext import filters
from telegram.error import TelegramError, BadRequest
from telegram.constants import ParseMode

from config import NOTE_IMAGES_DIR, DEFAULT_LEARNING_MODE, MODE_REVIEW_ALL_DUE
GET_NOTE_INPUT = 0

from database.query_note import get_note_by_card_and_user, add_note_for_user, update_note_by_id, get_flashcard_id_from_note, delete_note_image_path
from database.query_user import get_user_by_telegram_id
from database.query_progress import get_progress_id_by_card
from handlers import learning_session # Quan trọng: Đảm bảo learning_session được import

from utils.helpers import send_or_edit_message, escape_md_v2
from utils.exceptions import DatabaseError, UserNotFoundError, DuplicateError, ProgressNotFoundError

logger = logging.getLogger(__name__)

# --- Các hàm xử lý Note ---
# (handle_callback_show_note, start_add_note_for_user_conversation,
#  start_update_note_by_id_conversation, _handle_get_note_input
#  giữ nguyên như phiên bản notes_handler_update_v5)

async def handle_callback_show_note(update, context):
    # Giữ nguyên logic từ notes_handler_update_v5
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        logger.warning("handle_callback_show_note nhận callback query không hợp lệ.")
        return

    telegram_id = query.from_user.id
    log_prefix = "[NOTES_SHOW|UserTG:{}]".format(telegram_id)
    chat_id_to_use = telegram_id

    back_audio_id_to_delete = context.user_data.pop("last_back_audio_id", None)
    if back_audio_id_to_delete:
        logger.info("{}: Đang thử xóa last_back_audio_id: {}".format(log_prefix, back_audio_id_to_delete))
        try:
            chat_id_of_audio = query.message.chat_id if query.message else telegram_id
            await context.bot.delete_message(chat_id=chat_id_of_audio, message_id=back_audio_id_to_delete)
            logger.info("{}: Đã xóa audio mặt sau thành công.".format(log_prefix))
        except Exception as e_del_audio:
            logger.warning("{}: Lỗi khi xóa audio mặt sau {}: {}".format(log_prefix, back_audio_id_to_delete, e_del_audio))

    try:
        await query.answer()
    except Exception as e_ans:
        logger.warning("{}: Lỗi answer callback: {}".format(log_prefix, e_ans))

    flashcard_id = None
    actual_user_id = None
    try:
        flashcard_id_str = query.data.split(":")[1]
        flashcard_id = int(flashcard_id_str)
        logger.info("{}: Yêu cầu xem note cho Card ID: {}".format(log_prefix, flashcard_id))

        user_info = get_user_by_telegram_id(telegram_id)
        if not user_info or 'user_id' not in user_info:
            raise UserNotFoundError(identifier=telegram_id)
        actual_user_id = user_info['user_id']
        logger.debug("{}: Lấy được user_id: {}".format(log_prefix, actual_user_id))

        note_data = get_note_by_card_and_user(flashcard_id, actual_user_id)

        if note_data and isinstance(note_data, dict):
            note_content = note_data.get('note', '')
            image_path_relative = note_data.get('image_path')

            if not note_content and not image_path_relative:
                logger.debug("{}: Ghi chú rỗng (cả text và ảnh).".format(log_prefix))
                await context.bot.send_message(chat_id=chat_id_to_use, text="Bạn chưa có ghi chú (hoặc ghi chú trống) cho thẻ này.")
                return

            logger.debug("{}: Tìm thấy ghi chú. Text: '{}...', Image: '{}'. Đang gửi vào chat riêng...".format(
                log_prefix, note_content[:20] if note_content else "None", image_path_relative
            ))

            if image_path_relative:
                full_image_path = os.path.join(NOTE_IMAGES_DIR, image_path_relative)
                if os.path.exists(full_image_path):
                    try:
                        with open(full_image_path, 'rb') as photo_file:
                            await context.bot.send_photo(chat_id=chat_id_to_use, photo=photo_file)
                        logger.info("{}: Đã gửi ảnh của note vào chat riêng.".format(log_prefix))
                    except TelegramError as e_send_photo:
                        logger.error("{}: Lỗi Telegram khi gửi ảnh note: {}".format(log_prefix, e_send_photo))
                        await context.bot.send_message(chat_id=chat_id_to_use, text="Lỗi khi tải ảnh của ghi chú.")
                    except Exception as e_photo:
                        logger.error("{}: Lỗi khác khi gửi ảnh note: {}".format(log_prefix, e_photo))
                else:
                    logger.warning("{}: File ảnh '{}' không tồn tại.".format(log_prefix, full_image_path))

            if note_content:
                note_text_display = "📝 **Ghi chú của bạn cho thẻ [{}]**:\n\n{}".format(flashcard_id, html.escape(note_content))
                try:
                    await context.bot.send_message(
                        chat_id=chat_id_to_use,
                        text=note_text_display,
                        parse_mode='Markdown'
                    )
                    logger.info("{}: Đã gửi text của note vào chat riêng.".format(log_prefix))
                except TelegramError as e_send_text:
                    logger.error("{}: Lỗi Telegram khi gửi text note: {}".format(log_prefix, e_send_text))
                    if not image_path_relative:
                         await context.bot.send_message(chat_id=chat_id_to_use, text="Lỗi khi hiển thị nội dung ghi chú.")
            elif not image_path_relative:
                 pass
        else:
            logger.debug("{}: Không tìm thấy ghi chú nào.".format(log_prefix))
            await context.bot.send_message(chat_id=chat_id_to_use, text="Bạn chưa có ghi chú cho thẻ này.")

    except (ValueError, IndexError):
        logger.error("{}: Callback data không hợp lệ: {}".format(log_prefix, query.data))
        await context.bot.send_message(chat_id_to_use, text="❌ Lỗi: Dữ liệu thẻ không hợp lệ.")
    except UserNotFoundError:
        logger.error("{}: Không tìm thấy người dùng telegram_id {}".format(log_prefix, telegram_id))
        await context.bot.send_message(chat_id_to_use, text="❌ Lỗi: Không tìm thấy thông tin người dùng.")
    except DatabaseError as e_db:
        logger.error("{}: Lỗi DB khi xử lý show_note: {}".format(log_prefix, e_db))
        await context.bot.send_message(chat_id_to_use, text="❌ Lỗi tải dữ liệu ghi chú.")
    except Exception as e:
        logger.error("{}: Lỗi không mong muốn khi hiển thị note: {}".format(log_prefix, e), exc_info=True)
        await context.bot.send_message(chat_id_to_use, text="❌ Có lỗi xảy ra khi hiển thị ghi chú.")


async def start_add_note_for_user_conversation(update, context):
    query = update.callback_query
    await query.answer()
    telegram_id = query.from_user.id
    log_prefix = f"[NOTES_START_ADD|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Bắt đầu conversation thêm note, data: {query.data}")

    flashcard_id = int(query.data.split(":")[1])
    context.user_data["telegram_id"] = telegram_id
    context.user_data["note_action"] = "add"
    context.user_data["note_flashcard_id"] = flashcard_id
    context.user_data["original_card_back_message_id"] = query.message.message_id
    context.user_data["original_card_back_chat_id"] = query.message.chat_id

    prompt_text = "✏️ Vui lòng gửi nội dung ghi chú.\nBạn có thể gửi text thuần, hoặc gửi một ảnh kèm theo chú thích (caption sẽ là nội dung ghi chú)."
    sent_prompt_msg = await send_or_edit_message(
        context,
        query.message.chat_id,
        prompt_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚫 Hủy", callback_data="cancel_note_input")]]),
        message_to_edit=query.message
    )
    if sent_prompt_msg:
        context.user_data['note_prompt_message_id'] = sent_prompt_msg.message_id
        context.user_data['note_prompt_chat_id'] = sent_prompt_msg.chat_id
        return GET_NOTE_INPUT
    else:
        logger.error(f"{log_prefix} Lỗi gửi/sửa tin nhắn yêu cầu nhập note.")
        context.user_data.clear()
        return ConversationHandler.END

async def start_update_note_by_id_conversation(update, context):
    query = update.callback_query
    await query.answer()
    telegram_id = query.from_user.id
    log_prefix = f"[NOTES_START_EDIT|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Bắt đầu conversation sửa note, data: {query.data}")

    note_id_to_edit = int(query.data.split(":")[1])
    context.user_data["telegram_id"] = telegram_id
    context.user_data["note_action"] = "edit"
    context.user_data["note_id_to_edit"] = note_id_to_edit
    context.user_data["original_card_back_message_id"] = query.message.message_id
    context.user_data["original_card_back_chat_id"] = query.message.chat_id

    try:
        user_db_id = get_user_by_telegram_id(telegram_id)['user_id']
        flashcard_id_from_note = get_flashcard_id_from_note(note_id_to_edit)
        if not flashcard_id_from_note:
            await query.message.reply_text("Lỗi: Không tìm thấy thẻ liên quan.")
            context.user_data.clear()
            return ConversationHandler.END

        current_note_data = get_note_by_card_and_user(flashcard_id_from_note, user_db_id)
        if not current_note_data:
            await query.message.reply_text("Lỗi: Không tìm thấy ghi chú để sửa.")
            context.user_data.clear()
            return ConversationHandler.END

        context.user_data["note_flashcard_id"] = current_note_data.get("flashcard_id")
        context.user_data["current_note_text"] = current_note_data.get("note", "")
        context.user_data["current_note_image_path"] = current_note_data.get("image_path")

        current_text_display = html.escape(context.user_data["current_note_text"])
        prompt_lines = [f"✏️ Ghi chú hiện tại:"]
        if context.user_data["current_note_image_path"]:
            # Sửa lần 6: Thông báo sẽ hiển thị lại mặt sau thẻ, kèm ảnh nếu có
            prompt_lines.append(f"(Hiện tại có ảnh đính kèm. Gửi ảnh mới sẽ thay thế, gửi text không sẽ giữ lại ảnh nếu chỉ sửa text.)")
        prompt_lines.append(f"```\n{current_text_display}\n```")
        prompt_lines.append("Nhập nội dung mới (text hoặc ảnh kèm caption).")

        prompt_text = "\n".join(prompt_lines)
        sent_prompt_msg = await send_or_edit_message(
            context, query.message.chat_id, prompt_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚫 Hủy", callback_data="cancel_note_input")]]),
            parse_mode='Markdown', message_to_edit=query.message
        )
        if sent_prompt_msg:
            context.user_data['note_prompt_message_id'] = sent_prompt_msg.message_id
            context.user_data['note_prompt_chat_id'] = sent_prompt_msg.chat_id
            return GET_NOTE_INPUT
        else:
            context.user_data.clear()
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi khi chuẩn bị sửa note: {e}", exc_info=True)
        await query.message.reply_text("Lỗi khi tải thông tin ghi chú.")
        context.user_data.clear()
        return ConversationHandler.END

async def _handle_get_note_input(update, context):
    # Giữ nguyên logic từ notes_handler_update_v4
    telegram_id = update.effective_user.id
    log_prefix = f"[NOTES_GET_INPUT|UserTG:{telegram_id}]"
    note_text_to_save = None
    image_path_to_save = None
    delete_current_photo_if_editing = False

    prompt_message_id = context.user_data.get('note_prompt_message_id')
    prompt_chat_id = context.user_data.get('note_prompt_chat_id')

    if update.message.text:
        note_text_to_save = update.message.text
        logger.info(f"{log_prefix} Nhận được text: '{note_text_to_save[:30]}...'")
        if context.user_data.get("note_action") == "edit":
            # Nếu chỉ gửi text khi sửa, giữ lại ảnh cũ (nếu có)
            image_path_to_save = context.user_data.get("current_note_image_path")
    elif update.message.photo:
        logger.info(f"{log_prefix} Nhận được ảnh.")
        note_text_to_save = update.message.caption
        if note_text_to_save:
            logger.info(f"{log_prefix} Caption ảnh: '{note_text_to_save[:30]}...'")

        photo_file = await update.message.photo[-1].get_file()
        file_extension = os.path.splitext(photo_file.file_path)[1] if photo_file.file_path else '.jpg'
        unique_filename = f"{uuid.uuid4().hex}{file_extension}"
        save_path = os.path.join(NOTE_IMAGES_DIR, unique_filename)
        try:
            os.makedirs(NOTE_IMAGES_DIR, exist_ok=True)
            await photo_file.download_to_drive(save_path)
            logger.info(f"{log_prefix} Đã lưu ảnh vào: {save_path}")
            image_path_to_save = unique_filename
            if context.user_data.get("note_action") == "edit" and context.user_data.get("current_note_image_path"):
                if context.user_data.get("current_note_image_path") != image_path_to_save: # Chỉ xóa nếu ảnh mới khác ảnh cũ
                    delete_current_photo_if_editing = True
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi tải hoặc lưu ảnh: {e}", exc_info=True)
            await update.message.reply_text("Lỗi khi xử lý ảnh. Ghi chú sẽ được lưu không kèm ảnh (nếu có text).")
            if context.user_data.get("note_action") == "edit":
                image_path_to_save = context.user_data.get("current_note_image_path")
            else:
                image_path_to_save = None
    else:
        await update.message.reply_text("Vui lòng gửi text hoặc ảnh kèm caption. Hoặc /cancel để hủy.")
        return GET_NOTE_INPUT

    try:
        await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    context.user_data['note_text_to_save'] = note_text_to_save
    context.user_data['note_image_path_to_save'] = image_path_to_save
    if delete_current_photo_if_editing:
         context.user_data['delete_existing_image_file_on_save'] = context.user_data.get("current_note_image_path")

    return await _save_note_final(update, context, message_to_delete_id=prompt_message_id, chat_id_of_message_to_delete=prompt_chat_id)


async def _save_note_final(update, context, message_to_delete_id=None, chat_id_of_message_to_delete=None):
    """Sửa lần 6: Không gửi tin nhắn xác nhận riêng, gọi _display_card_backside."""
    telegram_id = context.user_data.get("telegram_id", update.effective_user.id)
    log_prefix = f"[NOTES_SAVE_FINAL|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Bắt đầu lưu ghi chú cuối cùng.")

    note_action = context.user_data.get("note_action")
    flashcard_id = context.user_data.get("note_flashcard_id")
    note_id_to_edit = context.user_data.get("note_id_to_edit")
    note_text_saved = context.user_data.get("note_text_to_save")
    image_path_saved = context.user_data.get("note_image_path_to_save")
    old_image_file_to_delete_on_server = context.user_data.get("delete_existing_image_file_on_save")

    actual_user_id = None
    note_save_success = False
    user_info = None

    try:
        user_info = get_user_by_telegram_id(telegram_id)
        if not user_info or 'user_id' not in user_info:
            raise UserNotFoundError(identifier=telegram_id)
        actual_user_id = user_info['user_id']

        final_note_text_to_db = note_text_saved if note_text_saved is not None else ""
        final_image_path_to_db = image_path_saved

        if note_action == "add":
            newly_added_note_id = add_note_for_user(flashcard_id, actual_user_id, final_note_text_to_db, final_image_path_to_db)
            if newly_added_note_id:
                note_save_success = True
                logger.info(f"{log_prefix} Thêm note ID {newly_added_note_id} cho card {flashcard_id} (Ảnh: {final_image_path_to_db})")
            else:
                note_save_success = False
                logger.error(f"{log_prefix} Hàm add_note_for_user không trả về ID hợp lệ.")

        elif note_action == "edit":
            if old_image_file_to_delete_on_server and old_image_file_to_delete_on_server != final_image_path_to_db:
                old_image_full_path = os.path.join(NOTE_IMAGES_DIR, old_image_file_to_delete_on_server)
                if os.path.exists(old_image_full_path):
                    try:
                        os.remove(old_image_full_path)
                        logger.info(f"{log_prefix} Đã xóa file ảnh cũ trên server: {old_image_full_path}")
                    except Exception as e_del_old_file:
                        logger.error(f"{log_prefix} Lỗi xóa file ảnh cũ {old_image_full_path}: {e_del_old_file}")

            rows_affected = update_note_by_id(note_id_to_edit, final_note_text_to_db, final_image_path_to_db)
            if rows_affected > 0:
                note_save_success = True
                logger.info(f"{log_prefix} Sửa note ID {note_id_to_edit} (Ảnh: {final_image_path_to_db})")
            else:
                note_save_success = True # Coi như thành công nếu không có gì thay đổi
                logger.warning(f"{log_prefix} Sửa note ID {note_id_to_edit} không ảnh hưởng dòng nào hoặc không có gì thay đổi.")
        else:
            raise ValueError(f"Hành động không xác định: {note_action}")

    except (UserNotFoundError, DatabaseError, DuplicateError, ValueError) as e_save:
        logger.error(f"{log_prefix} Lỗi khi lưu note: {e_save}", exc_info=True)
        original_chat_id_val = context.user_data.get("original_card_back_chat_id") # Đổi tên biến
        if original_chat_id_val:
            try:
                await context.bot.send_message(chat_id=original_chat_id_val, text=f"❌ Lỗi khi lưu ghi chú: {e_save}")
            except Exception as e_send_err:
                logger.error(f"{log_prefix} Lỗi gửi tin nhắn lỗi lưu note vào chat gốc: {e_send_err}")
        note_save_success = False
    except Exception as e_final:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi lưu note: {e_final}", exc_info=True)
        original_chat_id_val = context.user_data.get("original_card_back_chat_id") # Đổi tên biến
        if original_chat_id_val:
            try:
                await context.bot.send_message(chat_id=original_chat_id_val, text="❌ Lỗi hệ thống khi lưu ghi chú.")
            except Exception as e_send_err:
                logger.error(f"{log_prefix} Lỗi gửi tin nhắn lỗi hệ thống vào chat gốc: {e_send_err}")
        note_save_success = False

    if message_to_delete_id and chat_id_of_message_to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id_of_message_to_delete, message_id=message_to_delete_id)
            logger.debug(f"{log_prefix} Đã xóa tin nhắn prompt ID: {message_to_delete_id} trong chat {chat_id_of_message_to_delete}")
        except Exception as e_del_prompt_final:
            logger.warning(f"{log_prefix} Lỗi xóa tin nhắn prompt cuối cùng: {e_del_prompt_final}")

    if flashcard_id and actual_user_id and user_info:
        progress_id = None
        try:
            progress_id = get_progress_id_by_card(actual_user_id, flashcard_id)
        except Exception as e_get_prog:
            logger.error(f"{log_prefix} Lỗi khi lấy progress_id cho flashcard {flashcard_id}: {e_get_prog}")

        if progress_id:
            logger.info(f"{log_prefix} Lưu note xong (thành công: {note_save_success}). Gọi _display_card_backside cho progress_id {progress_id}.")
            update_for_display = update if isinstance(update, Update) else None
            if hasattr(update, 'callback_query') and update.callback_query:
                update_for_display = update.callback_query

            if hasattr(learning_session, '_display_card_backside'):
                 await learning_session._display_card_backside(update_for_display, context, progress_id, user_info)
            else:
                logger.error(f"{log_prefix} Không tìm thấy hàm learning_session._display_card_backside.")
                original_chat_id_val = context.user_data.get("original_card_back_chat_id") # Đổi tên biến
                if original_chat_id_val:
                    await context.bot.send_message(chat_id=original_chat_id_val, text="Đã xử lý ghi chú. Vui lòng lật lại thẻ hoặc tiếp tục.")
        elif note_save_success:
            logger.warning(f"{log_prefix} Lưu note thành công nhưng không có progress_id. Gửi thông báo đơn giản.")
            original_chat_id_val = context.user_data.get("original_card_back_chat_id") # Đổi tên biến
            if original_chat_id_val:
                 await context.bot.send_message(chat_id=original_chat_id_val, text="✅ Ghi chú đã được lưu.")
    else:
        logger.warning(f"{log_prefix} Thiếu flashcard_id, actual_user_id hoặc user_info. Không thể gọi _display_card_backside.")
        original_chat_id_val = context.user_data.get("original_card_back_chat_id") # Đổi tên biến
        if original_chat_id_val:
            final_reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Tiếp tục học", callback_data="continue")]])
            await context.bot.send_message(
                chat_id=original_chat_id_val,
                text="Đã xử lý ghi chú. Chọn hành động tiếp theo:",
                reply_markup=final_reply_markup
            )

    context.user_data.clear()
    logger.info(f"{log_prefix} Kết thúc conversation lưu note.")
    return ConversationHandler.END

async def _handle_cancel_note_input(update, context):
    # Giữ nguyên logic từ notes_handler_update_v6
    telegram_id = update.effective_user.id
    log_prefix = f"[NOTES_CANCEL|UserTG:{telegram_id}]"
    logger.info(f"{log_prefix} Người dùng hủy thao tác ghi chú.")

    prompt_message_id = context.user_data.get('note_prompt_message_id')
    prompt_chat_id = context.user_data.get('note_prompt_chat_id')
    original_card_back_chat_id = context.user_data.get("original_card_back_chat_id")
    flashcard_id_for_return = context.user_data.get("note_flashcard_id")

    if update.callback_query:
        query = update.callback_query
        try: await query.answer()
        except Exception: pass
        if query.message and prompt_message_id == query.message.message_id and prompt_chat_id == query.message.chat_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
            except Exception: pass
    elif update.message:
        try:
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        except Exception: pass
        if prompt_message_id and prompt_chat_id:
             try:
                await context.bot.delete_message(chat_id=prompt_chat_id, message_id=prompt_message_id)
             except Exception: pass

    user_info = None
    try: user_info = get_user_by_telegram_id(telegram_id)
    except Exception: logger.error(f"{log_prefix} Lỗi lấy user_info khi hủy.")

    if flashcard_id_for_return and user_info and user_info.get('user_id'):
        logger.info(f"{log_prefix} Hủy note. Hiển thị lại mặt sau thẻ {flashcard_id_for_return}.")
        actual_user_id = user_info.get('user_id')
        progress_id = get_progress_id_by_card(actual_user_id, flashcard_id_for_return)
        if progress_id:
            update_for_display = update if isinstance(update, Update) else (update.callback_query if hasattr(update, 'callback_query') else update.message)
            if hasattr(learning_session, '_display_card_backside'):
                await learning_session._display_card_backside(update_for_display, context, progress_id, user_info)
            else:
                logger.error(f"{log_prefix} learning_session._display_card_backside không tìm thấy.")
                if original_card_back_chat_id:
                     await context.bot.send_message(chat_id=original_card_back_chat_id, text="Đã hủy thao tác ghi chú. Vui lòng lật lại thẻ hoặc tiếp tục.")
        else:
            if original_card_back_chat_id:
                await context.bot.send_message(chat_id=original_card_back_chat_id, text="Đã hủy thao tác ghi chú. Không tìm thấy thẻ để hiển thị lại.")
    else:
        logger.warning(f"{log_prefix} Hủy note nhưng không đủ thông tin để hiển thị lại mặt sau.")
        target_chat_id_for_continue = original_card_back_chat_id or (update.effective_chat.id if update.effective_chat else telegram_id)
        if target_chat_id_for_continue:
            review_mode = context.user_data.get('review_mode', DEFAULT_LEARNING_MODE)
            continue_callback = "review_all" if review_mode == MODE_REVIEW_ALL_DUE else "continue"
            final_reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Tiếp tục học", callback_data=continue_callback)]])
            await context.bot.send_message(
                chat_id=target_chat_id_for_continue,
                text="Đã hủy ghi chú. Chọn hành động:",
                reply_markup=final_reply_markup
            )

    context.user_data.clear()
    logger.info(f"{log_prefix} Kết thúc conversation sau khi hủy.")
    return ConversationHandler.END

note_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_add_note_for_user_conversation, pattern=r"^add_note_for_user:"),
        CallbackQueryHandler(start_update_note_by_id_conversation, pattern=r"^update_note_by_id:")
    ],
    states={
        GET_NOTE_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_get_note_input),
            MessageHandler(filters.PHOTO, _handle_get_note_input),
            MessageHandler(filters.ALL & ~(filters.TEXT | filters.PHOTO | filters.COMMAND), _handle_get_note_input)
        ]
    },
    fallbacks=[
        CommandHandler("cancel", _handle_cancel_note_input),
        CallbackQueryHandler(_handle_cancel_note_input, pattern='^cancel_note_input$')
    ],
    name="note_conversation_v4", # Giữ tên v4 vì cấu trúc state vẫn vậy
    persistent=False,
    per_message=False
)

def register_handlers(app: Application):
    logger.info("--- MODULE: Đăng ký handlers cho Notes (Luồng ảnh+text, tích hợp hiển thị) ---")
    app.add_handler(note_conv_handler)
    app.add_handler(CallbackQueryHandler(handle_callback_show_note, pattern=r"^show_note:"))
    logger.info("Đã đăng ký handler cho Conversation (Note ảnh+text) và hiển thị Note.")

