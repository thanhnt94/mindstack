# web_app/services/stats_service.py
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

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

    def get_dashboard_stats(self, user_id):
        """
        Mô tả: Lấy tất cả dữ liệu thống kê cần thiết cho trang dashboard của người dùng.
        Args:
            user_id (int): ID của người dùng.
        Returns:
            dict: Một từ điển lớn chứa tất cả các thống kê cho dashboard.
        """
        log_prefix = f"[DASHBOARD_STATS|User:{user_id}]"
        logger.info(f"{log_prefix} Bắt đầu tổng hợp dữ liệu thống kê.")
        
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"{log_prefix} Không tìm thấy người dùng.")
            return None

        # 1. Thống kê tổng quan
        stats = {
            'total_score': user.score or 0,
            'current_mode_display': LEARNING_MODE_DISPLAY_NAMES.get(user.current_mode, user.current_mode),
            'learned_distinct_overall': 0,
            'learned_sets_count': 0,
            'activity_chart_data': {},
            'sets_stats': {}
        }

        all_user_progress = UserFlashcardProgress.query.filter_by(user_id=user_id)
        stats['learned_distinct_overall'] = all_user_progress.filter(UserFlashcardProgress.learned_date.isnot(None)).count()
        
        # --- BẮT ĐẦU SỬA: Thêm dữ liệu học mới vào biểu đồ ---
        # 2. Dữ liệu cho biểu đồ hoạt động 30 ngày
        tz_offset = user.timezone_offset or DEFAULT_TIMEZONE_OFFSET
        tz = timezone(timedelta(hours=tz_offset))
        today = datetime.now(tz).date()
        thirty_days_ago_ts = int((datetime.now(tz) - timedelta(days=30)).timestamp())

        # Lấy dữ liệu ôn tập
        reviews_last_30_days = db.session.query(UserFlashcardProgress.last_reviewed)\
            .filter(UserFlashcardProgress.user_id == user_id, UserFlashcardProgress.last_reviewed >= thirty_days_ago_ts)\
            .all()
        
        review_activity_by_day = defaultdict(int)
        for review in reviews_last_30_days:
            review_date = datetime.fromtimestamp(review.last_reviewed, tz).strftime('%d/%m')
            review_activity_by_day[review_date] += 1

        # Lấy dữ liệu học mới
        new_cards_last_30_days = db.session.query(UserFlashcardProgress.learned_date)\
            .filter(UserFlashcardProgress.user_id == user_id, UserFlashcardProgress.learned_date >= thirty_days_ago_ts)\
            .all()

        new_card_activity_by_day = defaultdict(int)
        for new_card in new_cards_last_30_days:
            learned_date = datetime.fromtimestamp(new_card.learned_date, tz).strftime('%d/%m')
            new_card_activity_by_day[learned_date] += 1
        
        # Tạo nhãn và dữ liệu cho cả hai
        chart_labels = [(today - timedelta(days=i)).strftime('%d/%m') for i in range(29, -1, -1)]
        reviews_chart_data = [review_activity_by_day.get(label, 0) for label in chart_labels]
        new_cards_chart_data = [new_card_activity_by_day.get(label, 0) for label in chart_labels]

        stats['activity_chart_data'] = {
            'labels': chart_labels,
            'datasets': [
                {
                    'label': 'Số thẻ đã ôn tập',
                    'data': reviews_chart_data
                },
                {
                    'label': 'Số thẻ học mới',
                    'data': new_cards_chart_data
                }
            ]
        }
        # --- KẾT THÚC SỬA ---

        # 3. Thống kê chi tiết cho từng bộ đã học
        learned_sets = VocabularySet.query.join(Flashcard).join(UserFlashcardProgress)\
            .filter(UserFlashcardProgress.user_id == user_id).distinct().all()
        
        stats['learned_sets_count'] = len(learned_sets)

        for s in learned_sets:
            set_id = s.set_id
            total_cards = Flashcard.query.filter_by(set_id=set_id).count()
            
            progress_in_set = UserFlashcardProgress.query.join(Flashcard)\
                .filter(Flashcard.set_id == set_id, UserFlashcardProgress.user_id == user_id)
            
            learned_cards = progress_in_set.count()
            mastered_cards = progress_in_set.filter(UserFlashcardProgress.correct_streak > 5).count()
            learning_cards = learned_cards - mastered_cards
            not_started_cards = total_cards - learned_cards

            stats['sets_stats'][set_id] = {
                'title': s.title,
                'total_cards': total_cards,
                'learned_cards': learned_cards,
                'pie_chart_data': {
                    'labels': ['Đã thuộc', 'Đang học', 'Chưa học'],
                    'data': [mastered_cards, learning_cards, not_started_cards]
                }
            }
        
        logger.info(f"{log_prefix} Tổng hợp dữ liệu thành công.")
        return stats

    def get_user_stats_for_context(self, user_id, set_id=None):
        """
        Lấy các thống kê nhỏ gọn để hiển thị bên cạnh thẻ (context panel).
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

        overall_progress = UserFlashcardProgress.query.filter_by(user_id=user_id)
        stats['learned_distinct_overall'] = overall_progress.filter(UserFlashcardProgress.learned_date.isnot(None)).distinct(UserFlashcardProgress.flashcard_id).count()
        stats['due_overall'] = overall_progress.filter(UserFlashcardProgress.due_time.isnot(None), UserFlashcardProgress.due_time <= current_ts).count()
        
        stats['learned_sets_count'] = db.session.query(Flashcard.set_id).join(UserFlashcardProgress).filter(UserFlashcardProgress.user_id == user_id).distinct().count()

        if set_id:
            current_set = VocabularySet.query.get(set_id)
            if current_set:
                stats['set_title'] = current_set.title
                stats['set_total_cards'] = db.session.query(Flashcard).filter(Flashcard.set_id == set_id).count()
                
                stats['set_learned_cards'] = UserFlashcardProgress.query.filter_by(user_id=user_id).\
                    join(Flashcard).filter(Flashcard.set_id == set_id, UserFlashcardProgress.learned_date.isnot(None)).count()
                
                stats['set_due_cards'] = UserFlashcardProgress.query.filter_by(user_id=user_id).\
                    join(Flashcard).filter(Flashcard.set_id == set_id, UserFlashcardProgress.due_time.isnot(None), UserFlashcardProgress.due_time <= current_ts).count()
        
        return stats
