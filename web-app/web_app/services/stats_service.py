# web_app/services/stats_service.py
import logging
from datetime import datetime, timedelta, timezone

from ..models import db, User, VocabularySet, Flashcard, UserFlashcardProgress
from ..config import DEFAULT_TIMEZONE_OFFSET, LEARNING_MODE_DISPLAY_NAMES

logger = logging.getLogger(__name__)

class StatsService:
    def __init__(self):
        pass

    def _get_current_unix_timestamp(self, tz_offset_hours):
        """Lấy Unix timestamp hiện tại theo múi giờ cụ thể."""
        try:
            tz = timedelta(hours=tz_offset_hours)
            now = datetime.now(timezone.utc).astimezone(timezone(tz))
            return int(now.timestamp())
        except Exception as e:
            logger.error(f"Lỗi khi lấy current timestamp: {e}", exc_info=True)
            return int(datetime.now(timezone.utc).timestamp())

    def get_user_stats_for_context(self, user_id, set_id=None):
        """
        Lấy các thống kê nhỏ gọn để hiển thị bên cạnh thẻ (context panel).
        Args:
            user_id (int): ID của người dùng.
            set_id (int, optional): ID của bộ từ vựng hiện tại. Defaults to None.
        Returns:
            dict: Từ điển chứa các thống kê.
        """
        stats = {
            'total_score': 0,
            'learned_distinct_overall': 0,
            'due_overall': 0,
            'learned_sets_count': 0,
            'set_title': 'N/A',
            'set_total_cards': 0,
            'set_learned_cards': 0,
            'set_due_cards': 0,
            'current_mode_display': 'N/A'
        }

        user = User.query.get(user_id)
        if not user:
            logger.warning(f"[GET_CONTEXT_STATS] User {user_id} not found.")
            return stats
        
        stats['total_score'] = user.score
        stats['current_mode_display'] = LEARNING_MODE_DISPLAY_NAMES.get(user.current_mode, user.current_mode)

        current_ts = self._get_current_unix_timestamp(user.timezone_offset)

        # Thống kê tổng quan
        overall_progress = UserFlashcardProgress.query.filter_by(user_id=user_id)
        stats['learned_distinct_overall'] = overall_progress.filter(UserFlashcardProgress.learned_date.isnot(None)).distinct(UserFlashcardProgress.flashcard_id).count()
        stats['due_overall'] = overall_progress.filter(UserFlashcardProgress.due_time.isnot(None), UserFlashcardProgress.due_time <= current_ts).count()
        
        # Số bộ đã học
        stats['learned_sets_count'] = db.session.query(Flashcard.set_id).join(UserFlashcardProgress).filter(UserFlashcardProgress.user_id == user_id).distinct().count()

        # Thống kê theo bộ hiện tại
        if set_id:
            current_set = VocabularySet.query.get(set_id)
            if current_set:
                stats['set_title'] = current_set.title
                stats['set_total_cards'] = db.session.query(Flashcard).filter(Flashcard.set_id == set_id).count()
                
                # Số thẻ đã học trong bộ
                stats['set_learned_cards'] = UserFlashcardProgress.query.filter_by(user_id=user_id).\
                    join(Flashcard).filter(Flashcard.set_id == set_id, UserFlashcardProgress.learned_date.isnot(None)).count()
                
                # Số thẻ đến hạn trong bộ
                stats['set_due_cards'] = UserFlashcardProgress.query.filter_by(user_id=user_id).\
                    join(Flashcard).filter(Flashcard.set_id == set_id, UserFlashcardProgress.due_time.isnot(None), UserFlashcardProgress.due_time <= current_ts).count()
        
        return stats

