# web_app/services/stats_service.py
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from ..models import db, User, VocabularySet, Flashcard, UserFlashcardProgress, ScoreLog, QuizQuestion, UserQuizProgress, QuestionSet
from ..config import DEFAULT_TIMEZONE_OFFSET, LEARNING_MODE_DISPLAY_NAMES, DAILY_HISTORY_MAX_DAYS
from sqlalchemy import func, case, and_ # Thêm import case và and_

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
            now = datetime.now(timezone.utc).astimezone(tz) # THAY ĐỔI: Chuyển đổi sang múi giờ cụ thể
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
            dt_now = datetime.fromtimestamp(current_timestamp, tz) # THAY ĐỔI: Sử dụng múi giờ cụ thể
            dt_midnight = datetime.combine(dt_now.date(), datetime.min.time(), tzinfo=tz)
            return int(dt_midnight.timestamp())
        except Exception as e:
            logger.error(f"Lỗi khi tính midnight timestamp: {e}", exc_info=True)
            # Fallback an toàn nếu có lỗi, nhưng cần kiểm tra kỹ múi giờ
            return int(current_timestamp - (current_timestamp % 86400))


    def get_admin_dashboard_stats(self):
        """
        Mô tả: Lấy các số liệu thống kê tổng quan cho trang quản trị viên.
        Returns:
            dict: Một dictionary chứa các số liệu thống kê như tổng số người dùng,
                  tổng số bộ thẻ, tổng số flashcard, tổng số lượt ôn tập,
                  và số người dùng hoạt động hôm nay.
        """
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
            # Logic này đếm tất cả các thẻ có learned_date trong 30 ngày qua.
            if new_card.learned_date: # Chỉ xử lý nếu learned_date không phải None
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
        ts_in_24_hours = current_ts + 86400 # 24 * 60 * 60

        for s in learned_sets:
            set_id = s.set_id
            total_cards = Flashcard.query.filter_by(set_id=set_id).count()
            
            progress_in_set = UserFlashcardProgress.query.join(Flashcard)\
                .filter(Flashcard.set_id == set_id, UserFlashcardProgress.user_id == user_id)
            
            # Tính toán các chỉ số cho lưới 6 ô
            learned_cards = progress_in_set.count()
            unseen_cards = total_cards - learned_cards
            mastered_cards = progress_in_set.filter(UserFlashcardProgress.correct_streak > 5).count()
            learning_cards = learned_cards - mastered_cards # Thẻ đang học là tổng thẻ đã có tiến trình trừ đi thẻ đã nhớ sâu
            due_cards = progress_in_set.filter(UserFlashcardProgress.due_time <= current_ts).count()
            lapsed_cards = progress_in_set.filter(UserFlashcardProgress.lapse_count > 0).count()
            due_soon_cards = progress_in_set.filter(UserFlashcardProgress.due_time > current_ts, UserFlashcardProgress.due_time <= ts_in_24_hours).count()

            stats['sets_stats'][set_id] = {
                'title': s.title,
                'total_cards': total_cards,
                'learned_cards': learned_cards,
                # Dữ liệu cho lưới 6 ô
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
        # Tổng điểm Quiz
        stats['quiz_score'] = db.session.query(db.func.sum(ScoreLog.score_change))\
            .filter(ScoreLog.user_id == user_id, ScoreLog.source_type == 'quiz').scalar() or 0
        
        # Tổng số câu hỏi đã trả lời
        stats['questions_answered_count'] = UserQuizProgress.query.filter_by(user_id=user_id).count()

        # Số lượng bộ Quiz đã bắt đầu
        stats['quiz_sets_started_count'] = db.session.query(QuizQuestion.set_id)\
            .join(UserQuizProgress)\
            .filter(UserQuizProgress.user_id == user_id)\
            .distinct()\
            .count()
        
        # Dữ liệu hoạt động Quiz 30 ngày qua
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
            'labels': chart_labels, # Sử dụng cùng nhãn ngày với flashcard
            'datasets': [
                {'label': 'Số lần trả lời (Quiz)', 'data': [quiz_questions_answered_by_day.get(label, 0) for label in chart_labels]},
                {'label': 'Số câu hỏi khác nhau (Quiz)', 'data': [len(quiz_distinct_questions_answered_by_day.get(label, set())) for label in chart_labels]},
                {'label': 'Điểm đạt được (Quiz)', 'data': [quiz_score_gained_by_day.get(label, 0) for label in chart_labels]}
            ]
        }

        # Thống kê chi tiết theo bộ Quiz
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
                    'unanswered': total_questions - answered_questions # Số câu chưa trả lời
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
            'set_mastered_cards': 0 # THÊM MỚI: Thêm trường mastered_cards
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
                
                # BẮT ĐẦU SỬA ĐỔI: Tính toán learned_cards và mastered_cards
                # Thay vì chỉ đếm thẻ có learned_date, đếm tất cả thẻ có progress (đã được giới thiệu)
                progress_in_set_query = UserFlashcardProgress.query.filter_by(user_id=user_id).join(Flashcard).filter(Flashcard.set_id == set_id)
                
                # SỬA LỖI: Đếm tất cả các thẻ mà người dùng đã có tiến trình (đã được giới thiệu)
                stats['set_learned_cards'] = progress_in_set_query.count() 
                stats['set_due_cards'] = progress_in_set_query.filter(UserFlashcardProgress.due_time.isnot(None), UserFlashcardProgress.due_time <= current_ts).count()
                stats['set_mastered_cards'] = progress_in_set_query.filter(UserFlashcardProgress.correct_streak > 5).count()
                # KẾT THÚC SỬA ĐỔI
        
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

        tz = timezone(timedelta(hours=DEFAULT_TIMEZONE_OFFSET)) # Lấy đối tượng timezone

        if timeframe == 'day':
            start_ts = self._get_midnight_timestamp(current_ts, DEFAULT_TIMEZONE_OFFSET)
            logger.debug(f"{log_prefix} Timeframe 'day', start_ts: {datetime.fromtimestamp(start_ts, tz)}")
        elif timeframe == 'week':
            # Lấy ngày đầu tuần (Thứ Hai)
            # datetime.weekday() trả về 0 cho Thứ Hai, 6 cho Chủ Nhật
            dt_now_in_tz = datetime.fromtimestamp(current_ts, tz)
            start_of_week = dt_now_in_tz.date() - timedelta(days=dt_now_in_tz.weekday())
            start_ts = int(datetime.combine(start_of_week, datetime.min.time(), tzinfo=tz).timestamp())
            logger.debug(f"{log_prefix} Timeframe 'week', start_ts: {datetime.fromtimestamp(start_ts, tz)}")
        elif timeframe == 'month':
            # Lấy ngày đầu tháng
            start_of_month = datetime.fromtimestamp(current_ts, tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_ts = int(start_of_month.timestamp())
            logger.debug(f"{log_prefix} Timeframe 'month', start_ts: {datetime.fromtimestamp(start_ts, tz)}")
        # 'all_time' means no start_ts filter

        # Bắt đầu truy vấn chính để lấy điểm số tổng hợp theo thời gian
        # và tổng điểm toàn thời gian
        # THAY ĐỔI: Đảm bảo ScoreLog.timestamp được lọc chính xác theo start_ts
        score_query = db.session.query(
            User.user_id,
            User.username,
            User.score.label('total_score_overall'), # Tổng điểm toàn thời gian
            func.sum(case((and_(ScoreLog.source_type == 'flashcard', ScoreLog.timestamp >= start_ts if start_ts else True), ScoreLog.score_change), else_=0)).label('flashcard_score_period'),
            func.sum(case((and_(ScoreLog.source_type == 'quiz', ScoreLog.timestamp >= start_ts if start_ts else True), ScoreLog.score_change), else_=0)).label('quiz_score_period')
        ).outerjoin(ScoreLog, and_(User.user_id == ScoreLog.user_id, ScoreLog.timestamp >= start_ts if start_ts else True)) # THAY ĐỔI: Thêm điều kiện lọc timestamp ngay trong join
        
        score_query = score_query.group_by(User.user_id, User.username, User.score)
        score_results = score_query.all()

        # THÊM LOG: In ra kết quả score_results thô
        logger.debug(f"{log_prefix} Raw Score Results: {score_results}")


        # Truy vấn riêng cho các chỉ số Flashcard (lượt ôn tập, thẻ đã học, thẻ mới)
        flashcard_stats_query = db.session.query(
            UserFlashcardProgress.user_id,
            func.count(UserFlashcardProgress.progress_id).label('total_reviews'),
            func.count(case((UserFlashcardProgress.learned_date.isnot(None), 1))).label('learned_cards'),
            # THAY ĐỔI: Sử dụng learned_date để đếm thẻ mới trong ngày
            func.count(case((UserFlashcardProgress.learned_date == self._get_midnight_timestamp(current_ts, DEFAULT_TIMEZONE_OFFSET), 1), else_=None)).label('new_cards_today')
        )
        if start_ts:
            # Lọc theo last_reviewed cho total_reviews và learned_cards trong khung thời gian
            flashcard_stats_query = flashcard_stats_query.filter(UserFlashcardProgress.last_reviewed >= start_ts)
        
        flashcard_stats_query = flashcard_stats_query.group_by(UserFlashcardProgress.user_id)
        flashcard_stats_map = {row.user_id: row for row in flashcard_stats_query.all()}

        # THÊM LOG: In ra kết quả flashcard_stats_map
        logger.debug(f"{log_prefix} Raw Flashcard Stats Map: {flashcard_stats_map}")


        # Truy vấn riêng cho các chỉ số Quiz (số câu trả lời)
        quiz_stats_query = db.session.query(
            UserQuizProgress.user_id,
            func.count(UserQuizProgress.progress_id).label('total_quiz_answers')
        )
        if start_ts:
            quiz_stats_query = quiz_stats_query.filter(UserQuizProgress.last_answered >= start_ts)
        
        quiz_stats_query = quiz_stats_query.group_by(UserQuizProgress.user_id)
        quiz_stats_map = {row.user_id: row for row in quiz_stats_query.all()}

        # THÊM LOG: In ra kết quả quiz_stats_map
        logger.debug(f"{log_prefix} Raw Quiz Stats Map: {quiz_stats_map}")


        leaderboard_data = []
        for user_id, username, total_score_overall, flashcard_score_period, quiz_score_period in score_results:
            flashcard_stats = flashcard_stats_map.get(user_id)
            quiz_stats = quiz_stats_map.get(user_id)

            total_reviews = flashcard_stats.total_reviews if flashcard_stats else 0
            learned_cards = flashcard_stats.learned_cards if flashcard_stats else 0
            new_cards_today = flashcard_stats.new_cards_today if flashcard_stats else 0
            total_quiz_answers = quiz_stats.total_quiz_answers if quiz_stats else 0

            # Tính toán tổng điểm cho khung thời gian hiện tại
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
        
        # Sắp xếp lại dữ liệu trong Python sau khi đã có tất cả các chỉ số
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
            leaderboard_data.sort(key=lambda x: x['current_period_score'], reverse=True) # Mặc định

        # Giới hạn số lượng kết quả
        leaderboard_data = leaderboard_data[:limit]
        
        logger.info(f"{log_prefix} Đã lấy thành công {len(leaderboard_data)} người dùng cho bảng xếp hạng.")
        return leaderboard_data


