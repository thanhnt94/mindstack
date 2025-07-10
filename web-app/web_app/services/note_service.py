# web_app/services/note_service.py
import logging
from ..models import db, FlashcardNote

logger = logging.getLogger(__name__)

class NoteService:
    """
    Mô tả: Lớp chứa các hàm xử lý logic nghiệp vụ liên quan đến ghi chú (notes).
    """
    def __init__(self):
        pass

    def get_note_by_flashcard_id(self, user_id, flashcard_id):
        """
        Mô tả: Lấy ghi chú của một người dùng cho một flashcard cụ thể.
        Args:
            user_id (int): ID của người dùng.
            flashcard_id (int): ID của flashcard.
        Returns:
            FlashcardNote: Đối tượng ghi chú nếu tìm thấy, ngược lại là None.
        """
        log_prefix = f"[NOTE_SERVICE|GetUserNote|User:{user_id}|Card:{flashcard_id}]"
        try:
            note = FlashcardNote.query.filter_by(
                user_id=user_id,
                flashcard_id=flashcard_id
            ).first()
            if note:
                logger.info(f"{log_prefix} Đã tìm thấy ghi chú (ID: {note.note_id}).")
            else:
                logger.info(f"{log_prefix} Không tìm thấy ghi chú nào.")
            return note
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi truy vấn ghi chú: {e}", exc_info=True)
            return None

    def create_or_update_note(self, user_id, flashcard_id, note_content):
        """
        Mô tả: Tạo mới hoặc cập nhật một ghi chú cho người dùng và flashcard.
        Args:
            user_id (int): ID của người dùng.
            flashcard_id (int): ID của flashcard.
            note_content (str): Nội dung của ghi chú.
        Returns:
            tuple: (FlashcardNote, "created" | "updated" | "error", "message")
                   Trả về đối tượng ghi chú, trạng thái (tạo mới, cập nhật, hoặc lỗi), và một thông báo.
        """
        log_prefix = f"[NOTE_SERVICE|UpdateUserNote|User:{user_id}|Card:{flashcard_id}]"
        logger.info(f"{log_prefix} Đang tạo/cập nhật ghi chú.")

        # Tìm ghi chú hiện có
        existing_note = self.get_note_by_flashcard_id(user_id, flashcard_id)

        try:
            if existing_note:
                # Cập nhật ghi chú đã có
                existing_note.note = note_content
                db.session.commit()
                logger.info(f"{log_prefix} Đã cập nhật ghi chú (ID: {existing_note.note_id}).")
                return existing_note, "updated", "Ghi chú đã được cập nhật thành công."
            else:
                # Tạo ghi chú mới
                new_note = FlashcardNote(
                    user_id=user_id,
                    flashcard_id=flashcard_id,
                    note=note_content
                )
                db.session.add(new_note)
                db.session.commit()
                logger.info(f"{log_prefix} Đã tạo ghi chú mới (ID: {new_note.note_id}).")
                return new_note, "created", "Ghi chú đã được tạo thành công."
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi lưu ghi chú vào DB: {e}", exc_info=True)
            return None, "error", "Đã xảy ra lỗi khi lưu ghi chú."
