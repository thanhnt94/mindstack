# web_app/services/quiz_note_service.py
import logging
from ..models import db, QuizQuestionNote

logger = logging.getLogger(__name__)

class QuizNoteService:
    """
    Mô tả: Lớp chứa các hàm xử lý logic nghiệp vụ liên quan đến ghi chú cho câu hỏi trắc nghiệm.
    """
    def __init__(self):
        pass

    def get_note_by_question_id(self, user_id, question_id):
        """
        Mô tả: Lấy ghi chú của một người dùng cho một câu hỏi cụ thể.
        """
        log_prefix = f"[QUIZ_NOTE_SVC|GetUserNote|User:{user_id}|Q:{question_id}]"
        try:
            note = QuizQuestionNote.query.filter_by(
                user_id=user_id,
                question_id=question_id
            ).first()
            if note:
                logger.info(f"{log_prefix} Đã tìm thấy ghi chú (ID: {note.note_id}).")
            else:
                logger.info(f"{log_prefix} Không tìm thấy ghi chú nào.")
            return note
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi truy vấn ghi chú: {e}", exc_info=True)
            return None

    def create_or_update_note(self, user_id, question_id, note_content):
        """
        Mô tả: Tạo mới hoặc cập nhật một ghi chú cho người dùng và câu hỏi.
        """
        log_prefix = f"[QUIZ_NOTE_SVC|UpdateUserNote|User:{user_id}|Q:{question_id}]"
        logger.info(f"{log_prefix} Đang tạo/cập nhật ghi chú.")

        existing_note = self.get_note_by_question_id(user_id, question_id)

        try:
            if existing_note:
                existing_note.note = note_content
                db.session.commit()
                logger.info(f"{log_prefix} Đã cập nhật ghi chú (ID: {existing_note.note_id}).")
                return existing_note, "updated", "Ghi chú đã được cập nhật thành công."
            else:
                new_note = QuizQuestionNote(
                    user_id=user_id,
                    question_id=question_id,
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
