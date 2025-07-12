# web_app/services/stats_service.py
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from ..models import db, User, VocabularySet, Flashcard, UserFlashcardProgress, ScoreLog
from ..config import DEFAULT_TIMEZONE_OFFSET, LEARNING_MODE_DISPLAY_NAMES

logger = logging.getLogger(__name__)

class StatsService:
    def __init__(self):
        pass

    def _get_current_unix_timestamp(self, tz_offset_hours):
        try:
            tz = timedelta(hours=tz_offset_hours)
            now = datetime.now(timezone.utc).astimezone(timezone(tz))
            return int(now.timestamp())
        except Exception as e:
            logger.error(f"Lỗi khi lấy current timestamp: {e}", exc_info=True)
            return int(datetime.now(timezone.utc).timestamp())

    def _get_midnight_timestamp(self, current_timestamp, tz_offset_hours):
        try:
            tz = timedelta(hours=tz_offset_hours)
            dt_now = datetime.fromtimestamp(current_timestamp, timezone.utc).astimezone(timezone(tz))
            dt_midnight = datetime.combine(dt_now.date(), datetime.min.time(), tzinfo=timezone(tz))
            return int(dt_midnight.timestamp())
        except Exception as e:
            logger.error(f"Lỗi khi tính midnight timestamp: {e}", exc_info=True)
            return int(current_timestamp - (current_timestamp % 86400))


    def get_admin_dashboard_stats(self):
        log_prefix = "[ADMIN_DASHBOARD_STATS]"
        logger.info(f"{log_prefix} Bắt đầu tổng hợp dữ liệu thống kê cho admin.")
        
        try:
            tz_offset = DEFAULT_TIMEZONE_OFFSET
            current_ts = self._get_current_unix_timestamp(tz_offset)
            today_midnight_ts = self._get_midnight_timestamp(current_ts, tz_offset)

            active_users_today = db.session.query(UserFlashcardProgress.user_id)\
                .filter(UserFlashcardProgress.last_reviewed >= today_midnight_ts)\
                .distinct()\
                .count()

            stats = {
                'total_users': User.query.count(),
                'total_sets': VocabularySet.query.count(),
                'total_flashcards': Flashcard.query.count(),
                'total_reviews': UserFlashcardProgress.query.count(),
                'active_users_today': active_users_today
            }
            logger.info(f"{log_prefix} Tổng hợp dữ liệu admin thành công.")
            return stats
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi lấy dữ liệu admin: {e}", exc_info=True)
            return None

    def get_dashboard_stats(self, user_id):
        log_prefix = f"[DASHBOARD_STATS|User:{user_id}]"
        logger.info(f"{log_prefix} Bắt đầu tổng hợp dữ liệu thống kê.")
        
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"{log_prefix} Không tìm thấy người dùng.")
            return None

        stats = {
            'total_score': user.score or 0,
            'current_mode_display': LEARNING_MODE_DISPLAY_NAMES.get(user.current_mode, user.current_mode),
            'learned_distinct_overall': 0,
            'learned_sets_count': 0,
            'activity_chart_data': {},
            'sets_stats': {},
            'heatmap_data': {}
        }

        all_user_progress = UserFlashcardProgress.query.filter_by(user_id=user_id)
        stats['learned_distinct_overall'] = all_user_progress.filter(UserFlashcardProgress.learned_date.isnot(None)).count()
        
        tz_offset = user.timezone_offset or DEFAULT_TIMEZONE_OFFSET
        tz = timezone(timedelta(hours=tz_offset))
        today = datetime.now(tz).date()
        
        one_year_ago_date = today - timedelta(days=365)
        one_year_ago_ts = int(datetime.combine(one_year_ago_date, datetime.min.time(), tzinfo=tz).timestamp())
        
        reviews_last_year = db.session.query(UserFlashcardProgress.last_reviewed, UserFlashcardProgress.flashcard_id)\
            .filter(UserFlashcardProgress.user_id == user_id, UserFlashcardProgress.last_reviewed >= one_year_ago_ts)\
            .all()
        
        heatmap_activity = defaultdict(int)
        for review_ts, _ in reviews_last_year:
            review_date_str = datetime.fromtimestamp(review_ts, tz).strftime('%Y-%m-%d')
            heatmap_activity[review_date_str] += 1
        stats['heatmap_data'] = dict(heatmap_activity)

        thirty_days_ago_ts = int((datetime.now(tz) - timedelta(days=30)).timestamp())
        
        review_actions_by_day = defaultdict(int)
        reviewed_cards_by_day = defaultdict(set)
        for review_ts, card_id in reviews_last_year:
            if review_ts >= thirty_days_ago_ts:
                review_date_str = datetime.fromtimestamp(review_ts, tz).strftime('%d/%m')
                review_actions_by_day[review_date_str] += 1
                reviewed_cards_by_day[review_date_str].add(card_id)

        new_cards_last_30_days = db.session.query(UserFlashcardProgress.learned_date)\
            .filter(UserFlashcardProgress.user_id == user_id, UserFlashcardProgress.learned_date >= thirty_days_ago_ts)\
            .all()
        new_card_activity_by_day = defaultdict(int)
        for new_card in new_cards_last_30_days:
            learned_date = datetime.fromtimestamp(new_card.learned_date, tz).strftime('%d/%m')
            new_card_activity_by_day[learned_date] += 1
        
        score_logs_last_30_days = db.session.query(ScoreLog.timestamp, ScoreLog.score_change)\
            .filter(ScoreLog.user_id == user_id, ScoreLog.timestamp >= thirty_days_ago_ts)\
            .all()
        score_gained_by_day = defaultdict(int)
        for log in score_logs_last_30_days:
            log_date = datetime.fromtimestamp(log.timestamp, tz).strftime('%d/%m')
            score_gained_by_day[log_date] += log.score_change

        chart_labels = [(today - timedelta(days=i)).strftime('%d/%m') for i in range(29, -1, -1)]
        review_actions_data = [review_actions_by_day.get(label, 0) for label in chart_labels]
        distinct_cards_data = [len(reviewed_cards_by_day.get(label, set())) for label in chart_labels]
        new_cards_chart_data = [new_card_activity_by_day.get(label, 0) for label in chart_labels]
        score_chart_data = [score_gained_by_day.get(label, 0) for label in chart_labels]

        stats['activity_chart_data'] = {
            'labels': chart_labels,
            'datasets': [
                {'label': 'Số lần ôn tập', 'data': review_actions_data},
                {'label': 'Số thẻ ôn tập', 'data': distinct_cards_data},
                {'label': 'Số thẻ học mới', 'data': new_cards_chart_data},
                {'label': 'Điểm đạt được', 'data': score_chart_data}
            ]
        }

        learned_sets = VocabularySet.query.join(Flashcard).join(UserFlashcardProgress)\
            .filter(UserFlashcardProgress.user_id == user_id).distinct().all()
        
        stats['learned_sets_count'] = len(learned_sets)

        # --- BẮT ĐẦU SỬA: Thêm logic lấy chi tiết cho từng bộ ---
        current_ts = self._get_current_unix_timestamp(tz_offset)
        for s in learned_sets:
            set_id = s.set_id
            total_cards = Flashcard.query.filter_by(set_id=set_id).count()
            
            progress_in_set = UserFlashcardProgress.query.join(Flashcard)\
                .filter(Flashcard.set_id == set_id, UserFlashcardProgress.user_id == user_id)
            
            learned_cards = progress_in_set.count()
            mastered_cards = progress_in_set.filter(UserFlashcardProgress.correct_streak > 5).count()
            due_cards = progress_in_set.filter(UserFlashcardProgress.due_time <= current_ts).count()
            lapsed_cards = progress_in_set.filter(UserFlashcardProgress.lapse_count > 0).count()
            learning_cards = learned_cards - mastered_cards

            stats['sets_stats'][set_id] = {
                'title': s.title,
                'total_cards': total_cards,
                'learned_cards': learned_cards,
                'due_cards': due_cards,
                'mastered_cards': mastered_cards,
                'lapsed_cards': lapsed_cards,
                'pie_chart_data': {
                    'labels': ['Nhớ sâu', 'Đang học', 'Chưa học'],
                    'data': [mastered_cards, learning_cards, total_cards - learned_cards]
                }
            }
        # --- KẾT THÚC SỬA ---
        
        logger.info(f"{log_prefix} Tổng hợp dữ liệu thành công.")
        return stats

    def get_user_stats_for_context(self, user_id, set_id=None):
        stats = {
            'total_score': 0, 'learned_distinct_overall': 0, 'due_overall': 0,
            'learned_sets_count': 0, 'set_title': 'N/A', 'set_total_cards': 0,
            'set_learned_cards': 0, 'set_due_cards': 0, 'current_mode_display': 'N/A'
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
                stats['set_learned_cards'] = UserFlashcardProgress.query.filter_by(user_id=user_id).join(Flashcard).filter(Flashcard.set_id == set_id, UserFlashcardProgress.learned_date.isnot(None)).count()
                stats['set_due_cards'] = UserFlashcardProgress.query.filter_by(user_id=user_id).join(Flashcard).filter(Flashcard.set_id == set_id, UserFlashcardProgress.due_time.isnot(None), UserFlashcardProgress.due_time <= current_ts).count()
        
        return stats
