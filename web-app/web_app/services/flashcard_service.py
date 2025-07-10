# web_app/services/flashcard_service.py
import logging
from ..models import db, Flashcard, User, VocabularySet

logger = logging.getLogger(__name__)

class FlashcardService:
    """
    Mô tả: Lớp chứa các hàm xử lý logic nghiệp vụ liên quan đến từng flashcard.
    """
    def __init__(self):
        pass

    def get_card_by_id(self, flashcard_id):
        """
        Mô tả: Lấy một flashcard cụ thể bằng ID.
        Args:
            flashcard_id (int): ID của flashcard.
        Returns:
            Flashcard: Đối tượng flashcard nếu tìm thấy, ngược lại là None.
        """
        return Flashcard.query.get(flashcard_id)

    def update_card(self, flashcard_id, data, user_id):
        """
        Mô tả: Cập nhật thông tin của một flashcard.
        Args:
            flashcard_id (int): ID của flashcard cần cập nhật.
            data (dict): Dữ liệu mới cho flashcard.
            user_id (int): ID của người dùng thực hiện hành động để kiểm tra quyền.
        Returns:
            tuple: (Flashcard, "success") nếu thành công.
                   (None, "error_message") nếu thất bại.
        """
        log_prefix = f"[FLASHSVC|UpdateCard|Card:{flashcard_id}|User:{user_id}]"
        logger.info(f"{log_prefix} Đang cập nhật thẻ với dữ liệu: {data}")

        card = self.get_card_by_id(flashcard_id)
        if not card:
            return None, "card_not_found"

        user = User.query.get(user_id)
        if not user:
            return None, "user_not_found"

        # Kiểm tra quyền: Hoặc là admin, hoặc là người tạo bộ thẻ
        set_creator_id = card.vocabulary_set.creator_user_id
        if user.user_role != 'admin' and user.user_id != set_creator_id:
            logger.warning(f"{log_prefix} Người dùng không có quyền sửa thẻ này.")
            return None, "permission_denied"

        try:
            card.front = data.get('front', card.front)
            card.back = data.get('back', card.back)
            card.front_audio_content = data.get('front_audio_content', card.front_audio_content)
            card.back_audio_content = data.get('back_audio_content', card.back_audio_content)
            card.front_img = data.get('front_img', card.front_img)
            card.back_img = data.get('back_img', card.back_img)
            
            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật thẻ thành công.")
            return card, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật thẻ: {e}", exc_info=True)
            return None, str(e)

