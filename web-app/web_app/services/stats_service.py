# web_app/services/stats_service.py
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from ..models import db, User, VocabularySet, Flashcard, UserFlashcardProgress, ScoreLog, QuizQuestion, UserQuizProgress, QuestionSet
from ..config import DEFAULT_TIMEZONE_OFFSET, LEARNING_MODE_DISPLAY_NAMES, DAILY_HISTORY_MAX_DAYS
from sqlalchemy import func, case, and_, or_

logger = logging.getLogger(__name__)

class StatsService:
    def __init__(self):
        pass

    def _get_current_unix_timestamp(self, tz_offset_hours):
        """
        Mô tả: Lấy Unix timestamp hiện tại theo múi giờ cụ thể.
        Args:
            tz_offset_hours (int): Độ lệch múi giờ tính bằng giờ (ví dụ: 7 cho UTC+7).
        Returns:
            int: Unix timestamp hiện tại.
        """
        try:
            tz = timezone(timedelta(hours=tz_offset_hours))
            now = datetime.now(timezone.utc).astimezone(tz)
            return int(now.timestamp())
        except Exception as e:
            logger.error(f"Lỗi khi lấy current timestamp: {e}", exc_info=True)
            return int(datetime.now(timezone.utc).timestamp())

    def _get_midnight_timestamp(self, current_timestamp, tz_offset_hours):
        """
        Mô tả: Tính toán Unix timestamp của nửa đêm (00:00:00) của ngày hiện tại
               dựa trên một timestamp cho trước và độ lệch múi giờ.
        Args:
            current_timestamp (int): Unix timestamp hiện tại.
            tz_offset_hours (int): Độ lệch múi giờ tính bằng giờ.
        Returns:
            int: Unix timestamp của nửa đêm của ngày hiện tại.
        """
        try:
            tz = timezone(timedelta(hours=tz_offset_hours))
            dt_now = datetime.fromtimestamp(current_timestamp, tz)
            dt_midnight = datetime.combine(dt_now.date(), datetime.min.time(), tzinfo=tz)
            return int(dt_midnight.timestamp())
        except Exception as e:
            logger.error(f"Lỗi khi tính midnight timestamp: {e}", exc_info=True)
            return int(current_timestamp - (current_timestamp % 86400))


    def get_admin_dashboard_stats(self):
        """
        Mô tả: Lấy các số liệu thống kê tổng quan và hoạt động gần đây cho trang quản trị viên.
        Returns:
            dict: Một dictionary chứa các số liệu thống kê.
        """
        log_prefix = "[ADMIN_DASHBOARD_STATS]"
        logger.info(f"{log_prefix} Bắt đầu tổng hợp dữ liệu thống kê cho admin.")
        
        try:
            tz_offset = DEFAULT_TIMEZONE_OFFSET
            current_ts = self._get_current_unix_timestamp(tz_offset)
            today_midnight_ts = self._get_midnight_timestamp(current_ts, tz_offset)

            # --- Thống kê tổng quan ---
            total_users = User.query.count()
            total_sets = VocabularySet.query.count()
            total_flashcards = Flashcard.query.count()
            total_reviews = UserFlashcardProgress.query.count()

            # --- BẮT ĐẦU THAY ĐỔI: Tính toán hoạt động trong ngày dựa trên last_seen ---
            active_users_today_query = User.query.filter(User.last_seen >= today_midnight_ts)
            active_users_today_count = active_users_today_query.count()
            active_users_today_list = active_users_today_query.all()
            # --- KẾT THÚC THAY ĐỔI ---

            # --- Hoạt động gần đây ---
            recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
            recent_sets = VocabularySet.query.order_by(VocabularySet.creation_date.desc()).limit(5).all()
            recent_question_sets = QuestionSet.query.order_by(QuestionSet.creation_date.desc()).limit(5).all()

            stats = {
                'total_users': total_users,
                'total_sets': total_sets,
                'total_flashcards': total_flashcards,
                'total_reviews': total_reviews,
                'active_users_today': active_users_today_count,
                'recent_activities': {
                    'users': recent_users,
                    'sets': recent_sets,
                    'question_sets': recent_question_sets,
                    'active_users': active_users_today_list
                }
            }
            logger.info(f"{log_prefix} Tổng hợp dữ liệu admin thành công.")
            return stats
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi lấy dữ liệu admin: {e}", exc_info=True)
            return None

    def get_dashboard_stats(self, user_id):
        """
        Mô tả: Lấy các số liệu thống kê chi tiết cho bảng điều khiển của người dùng.
               Bao gồm thống kê flashcard, thống kê quiz, lịch sử hoạt động,
               và chi tiết theo bộ thẻ.
        Args:
            user_id (int): ID của người dùng.
        Returns:
            dict: Một dictionary chứa tất cả các số liệu thống kê cần thiết cho dashboard.
        """
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
            'heatmap_data': {},
            'quiz_score': 0,
            'questions_answered_count': 0,
            'quiz_sets_started_count': 0,
            'quiz_activity_chart_data': {},
            'quiz_sets_stats': {}
        }

        # --- Thống kê Flashcard ---
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
            if new_card.learned_date:
                learned_date = datetime.fromtimestamp(new_card.learned_date, tz).strftime('%d/%m')
                new_card_activity_by_day[learned_date] += 1
        
        score_logs_last_30_days = db.session.query(ScoreLog.timestamp, ScoreLog.score_change, ScoreLog.source_type)\
            .filter(ScoreLog.user_id == user_id, ScoreLog.timestamp >= thirty_days_ago_ts)\
            .all()
        
        flashcard_score_gained_by_day = defaultdict(int)
        quiz_score_gained_by_day = defaultdict(int)
        for log in score_logs_last_30_days:
            log_date = datetime.fromtimestamp(log.timestamp, tz).strftime('%d/%m')
            if log.source_type == 'flashcard':
                flashcard_score_gained_by_day[log_date] += log.score_change
            elif log.source_type == 'quiz':
                quiz_score_gained_by_day[log_date] += log.score_change

        chart_labels = [(today - timedelta(days=i)).strftime('%d/%m') for i in range(29, -1, -1)]
        review_actions_data = [review_actions_by_day.get(label, 0) for label in chart_labels]
        distinct_cards_data = [len(reviewed_cards_by_day.get(label, set())) for label in chart_labels]
        new_cards_chart_data = [new_card_activity_by_day.get(label, 0) for label in chart_labels]
        flashcard_score_chart_data = [flashcard_score_gained_by_day.get(label, 0) for label in chart_labels]

        stats['activity_chart_data'] = {
            'labels': chart_labels,
            'datasets': [
                {'label': 'Số lần ôn tập', 'data': review_actions_data},
                {'label': 'Số thẻ ôn tập', 'data': distinct_cards_data},
                {'label': 'Số thẻ học mới', 'data': new_cards_chart_data},
                {'label': 'Điểm đạt được (Flashcard)', 'data': flashcard_score_chart_data}
            ]
        }

        learned_sets = VocabularySet.query.join(Flashcard).join(UserFlashcardProgress)\
            .filter(UserFlashcardProgress.user_id == user_id).distinct().all()
        
        stats['learned_sets_count'] = len(learned_sets)

        current_ts = self._get_current_unix_timestamp(tz_offset)
        ts_in_24_hours = current_ts + 86400

        for s in learned_sets:
            set_id = s.set_id
            total_cards = Flashcard.query.filter_by(set_id=set_id).count()
            
            progress_in_set = UserFlashcardProgress.query.join(Flashcard)\
                .filter(Flashcard.set_id == set_id, UserFlashcardProgress.user_id == user_id)
            
            learned_cards = progress_in_set.count()
            unseen_cards = total_cards - learned_cards
            mastered_cards = progress_in_set.filter(UserFlashcardProgress.correct_streak > 5).count()
            learning_cards = learned_cards - mastered_cards
            due_cards = progress_in_set.filter(UserFlashcardProgress.due_time <= current_ts).count()
            lapsed_cards = progress_in_set.filter(UserFlashcardProgress.lapse_count > 0).count()
            due_soon_cards = progress_in_set.filter(UserFlashcardProgress.due_time > current_ts, UserFlashcardProgress.due_time <= ts_in_24_hours).count()

            stats['sets_stats'][set_id] = {
                'title': s.title,
                'total_cards': total_cards,
                'learned_cards': learned_cards,
                'stat_values': {
                    'learning': learning_cards,
                    'mastered': mastered_cards,
                    'unseen': unseen_cards,
                    'due': due_cards,
                    'due_soon': due_soon_cards,
                    'lapsed': lapsed_cards
                }
            }

        # --- Thống kê Quiz ---
        stats['quiz_score'] = db.session.query(db.func.sum(ScoreLog.score_change))\
            .filter(ScoreLog.user_id == user_id, ScoreLog.source_type == 'quiz').scalar() or 0
        
        stats['questions_answered_count'] = UserQuizProgress.query.filter_by(user_id=user_id).count()

        stats['quiz_sets_started_count'] = db.session.query(QuizQuestion.set_id)\
            .join(UserQuizProgress)\
            .filter(UserQuizProgress.user_id == user_id)\
            .distinct()\
            .count()
        
        quiz_questions_answered_by_day = defaultdict(int)
        quiz_distinct_questions_answered_by_day = defaultdict(set)
        
        quiz_progresses_last_30_days = db.session.query(UserQuizProgress.last_answered, UserQuizProgress.question_id)\
            .filter(UserQuizProgress.user_id == user_id, UserQuizProgress.last_answered >= thirty_days_ago_ts)\
            .all()

        for answered_ts, question_id in quiz_progresses_last_30_days:
            answered_date_str = datetime.fromtimestamp(answered_ts, tz).strftime('%d/%m')
            quiz_questions_answered_by_day[answered_date_str] += 1
            quiz_distinct_questions_answered_by_day[answered_date_str].add(question_id)

        stats['quiz_activity_chart_data'] = {
            'labels': chart_labels,
            'datasets': [
                {'label': 'Số lần trả lời (Quiz)', 'data': [quiz_questions_answered_by_day.get(label, 0) for label in chart_labels]},
                {'label': 'Số câu hỏi khác nhau (Quiz)', 'data': [len(quiz_distinct_questions_answered_by_day.get(label, set())) for label in chart_labels]},
                {'label': 'Điểm đạt được (Quiz)', 'data': [quiz_score_gained_by_day.get(label, 0) for label in chart_labels]}
            ]
        }

        started_quiz_sets = QuestionSet.query.join(QuizQuestion).join(UserQuizProgress)\
            .filter(UserQuizProgress.user_id == user_id).distinct().all()

        for q_set in started_quiz_sets:
            set_id = q_set.set_id
            total_questions = QuizQuestion.query.filter_by(set_id=set_id).count()
            
            progress_in_quiz_set = UserQuizProgress.query.join(QuizQuestion)\
                .filter(QuizQuestion.set_id == set_id, UserQuizProgress.user_id == user_id)
            
            answered_questions = progress_in_quiz_set.count()
            correct_answers = progress_in_quiz_set.filter(UserQuizProgress.times_correct > 0).count()
            incorrect_answers = progress_in_quiz_set.filter(UserQuizProgress.times_incorrect > 0).count()
            mastered_questions = progress_in_quiz_set.filter(UserQuizProgress.is_mastered == True).count()
            
            stats['quiz_sets_stats'][set_id] = {
                'title': q_set.title,
                'total_questions': total_questions,
                'answered_questions': answered_questions,
                'stat_values': {
                    'correct': correct_answers,
                    'incorrect': incorrect_answers,
                    'mastered': mastered_questions,
                    'unanswered': total_questions - answered_questions
                }
            }
        
        logger.info(f"{log_prefix} Tổng hợp dữ liệu thành công.")
        return stats

    def get_user_stats_for_context(self, user_id, set_id=None):
        """
        Mô tả: Lấy các số liệu thống kê cơ bản của người dùng để hiển thị trong panel ngữ cảnh
               trên trang học thẻ.
        Args:
            user_id (int): ID của người dùng.
            set_id (int, optional): ID của bộ thẻ hiện tại. Mặc định là None.
        Returns:
            dict: Một dictionary chứa các số liệu thống kê tóm tắt.
        """
        stats = {
            'total_score': 0, 'learned_distinct_overall': 0, 'due_overall': 0,
            'learned_sets_count': 0, 'set_title': 'N/A', 'set_total_cards': 0,
            'set_learned_cards': 0, 'set_due_cards': 0, 'current_mode_display': 'N/A',
            'set_mastered_cards': 0
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
                
                progress_in_set_query = UserFlashcardProgress.query.filter_by(user_id=user_id).join(Flashcard).filter(Flashcard.set_id == set_id)
                
                stats['set_learned_cards'] = progress_in_set_query.count() 
                stats['set_due_cards'] = progress_in_set_query.filter(UserFlashcardProgress.due_time.isnot(None), UserFlashcardProgress.due_time <= current_ts).count()
                stats['set_mastered_cards'] = progress_in_set_query.filter(UserFlashcardProgress.correct_streak > 5).count()
        
        return stats

    def get_user_leaderboard_data(self, sort_by='total_score', timeframe='all_time', limit=10):
        """
        Mô tả: Lấy dữ liệu bảng xếp hạng người dùng dựa trên tiêu chí sắp xếp và khung thời gian.
        Args:
            sort_by (str): Tiêu chí sắp xếp ('total_score', 'total_reviews', 'learned_cards', 'new_cards', 'total_quiz_answers').
            timeframe (str): Khung thời gian ('day', 'week', 'month', 'all_time').
            limit (int): Số lượng người dùng hàng đầu muốn lấy.
        Returns:
            list: Danh sách các dictionary chứa thông tin người dùng và các chỉ số xếp hạng.
        """
        log_prefix = f"[LEADERBOARD_STATS|Sort:{sort_by}|Time:{timeframe}]"
        logger.info(f"{log_prefix} Bắt đầu lấy dữ liệu bảng xếp hạng.")

        current_ts = self._get_current_unix_timestamp(DEFAULT_TIMEZONE_OFFSET)
        start_ts = None

        tz = timezone(timedelta(hours=DEFAULT_TIMEZONE_OFFSET))

        if timeframe == 'day':
            start_ts = self._get_midnight_timestamp(current_ts, DEFAULT_TIMEZONE_OFFSET)
            logger.debug(f"{log_prefix} Timeframe 'day', start_ts: {datetime.fromtimestamp(start_ts, tz)}")
        elif timeframe == 'week':
            dt_now_in_tz = datetime.fromtimestamp(current_ts, tz)
            start_of_week = dt_now_in_tz.date() - timedelta(days=dt_now_in_tz.weekday())
            start_ts = int(datetime.combine(start_of_week, datetime.min.time(), tzinfo=tz).timestamp())
            logger.debug(f"{log_prefix} Timeframe 'week', start_ts: {datetime.fromtimestamp(start_ts, tz)}")
        elif timeframe == 'month':
            start_of_month = datetime.fromtimestamp(current_ts, tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_ts = int(start_of_month.timestamp())
            logger.debug(f"{log_prefix} Timeframe 'month', start_ts: {datetime.fromtimestamp(start_ts, tz)}")

        score_query = db.session.query(
            User.user_id,
            User.username,
            User.score.label('total_score_overall'),
            func.sum(case((and_(ScoreLog.source_type == 'flashcard', ScoreLog.timestamp >= start_ts if start_ts else True), ScoreLog.score_change), else_=0)).label('flashcard_score_period'),
            func.sum(case((and_(ScoreLog.source_type == 'quiz', ScoreLog.timestamp >= start_ts if start_ts else True), ScoreLog.score_change), else_=0)).label('quiz_score_period')
        ).outerjoin(ScoreLog, and_(User.user_id == ScoreLog.user_id, ScoreLog.timestamp >= start_ts if start_ts else True))
        
        score_query = score_query.group_by(User.user_id, User.username, User.score)
        score_results = score_query.all()

        logger.debug(f"{log_prefix} Raw Score Results: {score_results}")

        flashcard_stats_query = db.session.query(
            UserFlashcardProgress.user_id,
            func.count(UserFlashcardProgress.progress_id).label('total_reviews'),
            func.count(case((UserFlashcardProgress.learned_date.isnot(None), 1))).label('learned_cards'),
            func.count(case((UserFlashcardProgress.learned_date == self._get_midnight_timestamp(current_ts, DEFAULT_TIMEZONE_OFFSET), 1), else_=None)).label('new_cards_today')
        )
        if start_ts:
            flashcard_stats_query = flashcard_stats_query.filter(UserFlashcardProgress.last_reviewed >= start_ts)
        
        flashcard_stats_query = flashcard_stats_query.group_by(UserFlashcardProgress.user_id)
        flashcard_stats_map = {row.user_id: row for row in flashcard_stats_query.all()}

        logger.debug(f"{log_prefix} Raw Flashcard Stats Map: {flashcard_stats_map}")

        quiz_stats_query = db.session.query(
            UserQuizProgress.user_id,
            func.count(UserQuizProgress.progress_id).label('total_quiz_answers')
        )
        if start_ts:
            quiz_stats_query = quiz_stats_query.filter(UserQuizProgress.last_answered >= start_ts)
        
        quiz_stats_query = quiz_stats_query.group_by(UserQuizProgress.user_id)
        quiz_stats_map = {row.user_id: row for row in quiz_stats_query.all()}

        logger.debug(f"{log_prefix} Raw Quiz Stats Map: {quiz_stats_map}")

        leaderboard_data = []
        for user_id, username, total_score_overall, flashcard_score_period, quiz_score_period in score_results:
            flashcard_stats = flashcard_stats_map.get(user_id)
            quiz_stats = quiz_stats_map.get(user_id)

            total_reviews = flashcard_stats.total_reviews if flashcard_stats else 0
            learned_cards = flashcard_stats.learned_cards if flashcard_stats else 0
            new_cards_today = flashcard_stats.new_cards_today if flashcard_stats else 0
            total_quiz_answers = quiz_stats.total_quiz_answers if quiz_stats else 0

            current_period_score = (flashcard_score_period if flashcard_score_period else 0) + (quiz_score_period if quiz_score_period else 0)

            leaderboard_data.append({
                'user_id': user_id,
                'username': username,
                'total_score_overall': total_score_overall,
                'current_period_score': current_period_score,
                'total_reviews': total_reviews,
                'learned_cards': learned_cards,
                'new_cards_today': new_cards_today,
                'total_quiz_answers': total_quiz_answers
            })
        
        if sort_by == 'total_score':
            leaderboard_data.sort(key=lambda x: x['current_period_score'], reverse=True)
        elif sort_by == 'total_reviews':
            leaderboard_data.sort(key=lambda x: x['total_reviews'], reverse=True)
        elif sort_by == 'learned_cards':
            leaderboard_data.sort(key=lambda x: x['learned_cards'], reverse=True)
        elif sort_by == 'new_cards':
            leaderboard_data.sort(key=lambda x: x['new_cards_today'], reverse=True)
        elif sort_by == 'total_quiz_answers':
            leaderboard_data.sort(key=lambda x: x['total_quiz_answers'], reverse=True)
        else:
            leaderboard_data.sort(key=lambda x: x['current_period_score'], reverse=True)

        leaderboard_data = leaderboard_data[:limit]
        
        logger.info(f"{log_prefix} Đã lấy thành công {len(leaderboard_data)} người dùng cho bảng xếp hạng.")
        return leaderboard_data
