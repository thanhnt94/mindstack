# web_app/services/flashcard_service.py
import logging
from datetime import datetime, timedelta, timezone
from ..models import db, Flashcard, User, UserFlashcardProgress, VocabularySet
from ..config import DEFAULT_TIMEZONE_OFFSET
from sqlalchemy import or_

logger = logging.getLogger(__name__)

def _get_current_unix_timestamp():
    """ Helper function to get current timestamp. """
    return int(datetime.now(timezone.utc).timestamp())

class FlashcardService:
    def __init__(self):
        pass

    def get_card_by_id(self, flashcard_id):
        return Flashcard.query.get(flashcard_id)

    def update_card(self, flashcard_id, data, user_id):
        """
        Mô tả: Cập nhật thông tin chi tiết cho một flashcard, có kiểm tra quyền.
        """
        log_prefix = f"[FLASHSVC|UpdateCard|Card:{flashcard_id}|User:{user_id}]"
        logger.info(f"{log_prefix} Đang cập nhật thẻ.")

        card = self.get_card_by_id(flashcard_id)
        if not card:
            return None, "card_not_found"

        user = User.query.get(user_id)
        if not user:
            return None, "user_not_found"

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
            card.ai_prompt = data.get('ai_prompt', card.ai_prompt)
            
            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật thẻ thành công.")
            return card, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật thẻ: {e}", exc_info=True)
            return None, str(e)

    def delete_card(self, flashcard_id, user_id):
        """
        Mô tả: Xóa một flashcard, có kiểm tra quyền.
        """
        log_prefix = f"[FLASHSVC|DeleteCard|Card:{flashcard_id}|User:{user_id}]"
        logger.info(f"{log_prefix} Đang xử lý yêu cầu xóa thẻ.")

        card = self.get_card_by_id(flashcard_id)
        if not card:
            return False, "card_not_found"

        user = User.query.get(user_id)
        if not user:
            return False, "user_not_found"

        set_creator_id = card.vocabulary_set.creator_user_id
        if user.user_role != 'admin' and user.user_id != set_creator_id:
            logger.warning(f"{log_prefix} Người dùng không có quyền xóa thẻ này.")
            return False, "permission_denied"

        try:
            db.session.delete(card)
            db.session.commit()
            logger.info(f"{log_prefix} Xóa thẻ thành công.")
            return True, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi xóa thẻ: {e}", exc_info=True)
            return False, str(e)

    def search_cards_in_set_paginated(self, set_id, search_term=None, search_field='all', page=1, per_page=10):
        """
        Mô tả: Tìm kiếm và phân trang danh sách các thẻ trong một bộ cụ thể.
        """
        log_prefix = f"[FLASHSVC|SearchCards|Set:{set_id}]"
        logger.info(f"{log_prefix} Tìm kiếm với term='{search_term}', field='{search_field}', page={page}.")
        
        query = Flashcard.query.filter_by(set_id=set_id)

        if search_term:
            term = f"%{search_term}%"
            if search_field == 'id':
                if search_term.isdigit():
                    query = query.filter(Flashcard.flashcard_id == int(search_term))
            elif search_field == 'front':
                query = query.filter(Flashcard.front.ilike(term))
            elif search_field == 'back':
                query = query.filter(Flashcard.back.ilike(term))
            else: # 'all'
                query = query.filter(or_(
                    Flashcard.front.ilike(term),
                    Flashcard.back.ilike(term)
                ))

        query = query.order_by(Flashcard.flashcard_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return pagination

    def get_cards_by_category(self, user_id, set_id, category, page, per_page=50):
        log_prefix = f"[FLASHSVC|GetCards|User:{user_id}|Set:{set_id}|Cat:{category}]"
        logger.info(f"{log_prefix} Đang lấy trang {page}...")
        
        query = None
        if category == 'unseen':
            subquery = db.session.query(UserFlashcardProgress.flashcard_id).filter_by(user_id=user_id)
            query = Flashcard.query.filter(
                Flashcard.set_id == set_id,
                ~Flashcard.flashcard_id.in_(subquery)
            )
        else:
            query = Flashcard.query.join(UserFlashcardProgress).filter(
                Flashcard.set_id == set_id,
                UserFlashcardProgress.user_id == user_id
            )
            current_ts = _get_current_unix_timestamp()
            ts_in_24_hours = current_ts + 86400
            if category == 'due':
                query = query.filter(UserFlashcardProgress.due_time <= current_ts)
            elif category == 'mastered':
                query = query.filter(UserFlashcardProgress.correct_streak > 5)
            elif category == 'lapsed':
                query = query.filter(UserFlashcardProgress.lapse_count > 0)
            elif category == 'due_soon':
                query = query.filter(UserFlashcardProgress.due_time > current_ts, UserFlashcardProgress.due_time <= ts_in_24_hours)
            elif category == 'learning':
                query = query.filter(UserFlashcardProgress.correct_streak <= 5)

        if query is None:
            raise ValueError(f"Danh mục không hợp lệ: {category}")

        query = query.order_by(Flashcard.front)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        logger.info(f"{log_prefix} Tìm thấy {pagination.total} thẻ. Trả về trang {page}.")
        return pagination

flashcard_service = FlashcardService()
