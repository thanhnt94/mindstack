# web_app/services/learning_logic.py
import logging
import time
import math
import random
from datetime import datetime, timedelta, time as dt_time, timezone

# --- BẮT ĐẦU SỬA: Thêm ScoreLog ---
from ..models import db, User, VocabularySet, Flashcard, UserFlashcardProgress, ScoreLog
# --- KẾT THÚC SỬA ---
from ..config import (
    DEFAULT_TIMEZONE_OFFSET,
    SRS_INITIAL_INTERVAL_HOURS, SRS_MAX_INTERVAL_DAYS,
    RETRY_INTERVAL_WRONG_MIN, RETRY_INTERVAL_HARD_MIN, RETRY_INTERVAL_NEW_MIN,
    SCORE_INCREASE_CORRECT, SCORE_INCREASE_HARD,
    SCORE_INCREASE_QUICK_REVIEW_CORRECT, SCORE_INCREASE_QUICK_REVIEW_HARD,
    SCORE_INCREASE_NEW_CARD,
    MODE_SEQUENTIAL_LEARNING,
    MODE_NEW_CARDS_ONLY,
    MODE_REVIEW_ALL_DUE,
    MODE_REVIEW_HARDEST,
    MODE_AUTOPLAY_REVIEW
)

from .mode_strategies import (
    _get_current_unix_timestamp,
    _get_midnight_timestamp,
    _get_wait_time_for_set,
    get_card_for_new_cards_only,
    get_card_for_review_modes,
    get_card_for_sequential_learning,
    get_card_for_autoplay_review
)


logger = logging.getLogger(__name__)

class LearningLogicService:
    def __init__(self):
        self.mode_strategies = {
            MODE_SEQUENTIAL_LEARNING: get_card_for_sequential_learning,
            MODE_NEW_CARDS_ONLY: get_card_for_new_cards_only,
            MODE_REVIEW_ALL_DUE: get_card_for_review_modes,
            MODE_REVIEW_HARDEST: get_card_for_review_modes,
            MODE_AUTOPLAY_REVIEW: get_card_for_autoplay_review
        }

    def _get_current_unix_timestamp(self, tz_offset_hours):
        return _get_current_unix_timestamp(tz_offset_hours)

    def _get_midnight_timestamp(self, current_timestamp, tz_offset_hours):
        return _get_midnight_timestamp(current_timestamp, tz_offset_hours)

    def _calculate_next_review_time(self, streak_correct=0, total_correct=0, current_timestamp=None, tz_offset_hours=DEFAULT_TIMEZONE_OFFSET):
        log_prefix = "[CALC_SRS_TIME]"
        if current_timestamp is None:
            current_timestamp = self._get_current_unix_timestamp(tz_offset_hours)
        
        streak_correct = max(0, int(streak_correct or 0))
        total_correct = max(0, int(total_correct or 0))

        base_interval_hours = SRS_INITIAL_INTERVAL_HOURS
        if streak_correct > 0:
            base_interval_hours = (2 ** (streak_correct - 1)) * 2 
        
        max_interval_hours = SRS_MAX_INTERVAL_DAYS * 24
        final_interval_hours = min(base_interval_hours, max_interval_hours)
        delay_minutes = final_interval_hours * 60

        delay_seconds = int(round(delay_minutes * 60))
        next_review_timestamp = current_timestamp + delay_seconds
        
        min_next_ts = current_timestamp + 60
        next_review_timestamp = max(next_review_timestamp, min_next_ts)

        logger.debug(f"{log_prefix} Input: streak={streak_correct}, total={total_correct} -> delay={delay_minutes:.2f}m, next_ts={next_review_timestamp}")
        return next_review_timestamp

    def _get_wait_time_for_set(self, user_id, set_id, current_ts, tz_offset_hours, log_prefix):
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)


    def process_review_response(self, user_id, progress_id, response):
        log_prefix = f"[PROCESS_ANSWER|UserUID:{user_id}|ProgID:{progress_id}|Resp:{response}]" 
        logger.info(f"{log_prefix} Bắt đầu xử lý đánh giá.")

        progress = UserFlashcardProgress.query.get(progress_id)
        if not progress:
            logger.error(f"{log_prefix} Không tìm thấy tiến trình với ID: {progress_id}")
            return None, None

        user = User.query.get(user_id)
        if not user:
            logger.error(f"{log_prefix} Không tìm thấy người dùng với ID: {user_id}")
            return None, None

        if user.current_mode == MODE_AUTOPLAY_REVIEW:
            logger.info(f"{log_prefix} Chế độ Autoplay, không cập nhật tiến trình và điểm số.")
            flashcard_info_updated = {
                'progress_id': progress.progress_id,
                'flashcard_id': progress.flashcard.flashcard_id,
                'user_id': progress.user_id,
                'front': progress.flashcard.front,
                'back': progress.flashcard.back,
                'front_audio_content': progress.flashcard.front_audio_content,
                'back_audio_content': progress.flashcard.back_audio_content,
                'front_img': progress.flashcard.front_img,
                'back_img': progress.flashcard.back_img,
                'notification_text': progress.flashcard.notification_text,
                'set_id': progress.flashcard.set_id,
                'title': progress.flashcard.vocabulary_set.title if progress.flashcard.vocabulary_set else None
            }
            return flashcard_info_updated, self._get_current_unix_timestamp(user.timezone_offset)

        current_streak_correct = progress.correct_streak
        current_total_correct = progress.correct_count
        current_incorrect_count = progress.incorrect_count
        current_lapse_count = progress.lapse_count
        current_review_count = progress.review_count

        tz_offset_hours = user.timezone_offset
        current_mode = user.current_mode
        current_ts = self._get_current_unix_timestamp(tz_offset_hours)

        is_quick_review_score_only_mode = (current_mode == MODE_REVIEW_HARDEST) 

        new_streak_correct = current_streak_correct
        new_total_correct = current_total_correct
        new_incorrect_count = current_incorrect_count
        new_lapse_count = current_lapse_count
        new_review_count = current_review_count + 1 
        
        score_to_add = 0
        score_reason = ''
        next_review_time = progress.due_time or current_ts + 60

        if is_quick_review_score_only_mode:
            if response == 1: 
                score_to_add = SCORE_INCREASE_QUICK_REVIEW_CORRECT
                score_reason = 'quick_review_correct'
            elif response == 0: 
                score_to_add = SCORE_INCREASE_QUICK_REVIEW_HARD
                score_reason = 'quick_review_hard'
        else:
            if response == 1:
                score_to_add = SCORE_INCREASE_CORRECT
                score_reason = 'srs_correct'
                new_streak_correct += 1
                new_total_correct += 1
                next_review_time = self._calculate_next_review_time(new_streak_correct, new_total_correct, current_ts, tz_offset_hours)
            elif response == -1:
                if current_streak_correct > 0: new_lapse_count += 1
                new_streak_correct = 0
                new_incorrect_count += 1
                next_review_time = current_ts + RETRY_INTERVAL_WRONG_MIN * 60
            elif response == 0:
                new_streak_correct = 0
                next_review_time = current_ts + RETRY_INTERVAL_HARD_MIN * 60
            elif response == 2:
                next_review_time = current_ts + RETRY_INTERVAL_NEW_MIN * 60
                if progress.learned_date is None:
                    progress.learned_date = self._get_midnight_timestamp(current_ts, tz_offset_hours)
                score_to_add = SCORE_INCREASE_NEW_CARD
                score_reason = 'new_card'
            else:
                logger.error(f"{log_prefix} Response không hợp lệ: {response}")
                return None, None

        progress.last_reviewed = current_ts
        progress.review_count = new_review_count
        progress.due_time = next_review_time
        progress.correct_streak = new_streak_correct
        progress.correct_count = new_total_correct
        progress.incorrect_count = new_incorrect_count
        progress.lapse_count = new_lapse_count

        try:
            db.session.add(progress)
            
            # --- BẮT ĐẦU SỬA: Ghi lại log điểm ---
            if score_to_add != 0:
                user.score = (user.score or 0) + score_to_add
                db.session.add(user) # Thêm user vào session để cập nhật
                
                score_log_entry = ScoreLog(
                    user_id=user_id,
                    score_change=score_to_add,
                    timestamp=current_ts,
                    reason=score_reason
                )
                db.session.add(score_log_entry)
                logger.info(f"{log_prefix} Đã ghi log thay đổi điểm: {score_to_add}. Lý do: {score_reason}")
            # --- KẾT THÚC SỬA ---

            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật progress và score thành công.")
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi commit progress/score: {e}", exc_info=True)
            return None, None

        flashcard_info_updated = {
            'progress_id': progress.progress_id,
            'flashcard_id': progress.flashcard.flashcard_id,
            'user_id': progress.user_id,
            'last_reviewed': progress.last_reviewed,
            'due_time': progress.due_time,
            'review_count': progress.review_count,
            'learned_date': progress.learned_date,
            'correct_streak': progress.correct_streak,
            'correct_count': progress.correct_count,
            'incorrect_count': progress.incorrect_count,
            'lapse_count': progress.lapse_count,
            'is_skipped': progress.is_skipped,
            'front': progress.flashcard.front,
            'back': progress.flashcard.back,
            'front_audio_content': progress.flashcard.front_audio_content,
            'back_audio_content': progress.flashcard.back_audio_content,
            'front_img': progress.flashcard.front_img,
            'back_img': progress.flashcard.back_img,
            'notification_text': progress.flashcard.notification_text,
            'set_id': progress.flashcard.set_id,
            'title': progress.flashcard.vocabulary_set.title if progress.flashcard.vocabulary_set else None
        }
        return flashcard_info_updated, next_review_time

    def get_next_card_for_review(self, user_id, set_id, mode):
        log_prefix = f"[GET_NEXT_CARD|UserUID:{user_id}|Set:{set_id}|Mode:{mode}]"
        logger.info(f"{log_prefix} Bắt đầu tìm thẻ tiếp theo.")

        user = User.query.get(user_id)
        if not user:
            logger.error(f"{log_prefix} Người dùng không tồn tại: {user_id}")
            return None, None, None

        current_ts = self._get_current_unix_timestamp(user.timezone_offset)
        today_midnight_ts = self._get_midnight_timestamp(current_ts, user.timezone_offset)
        daily_new_limit = user.daily_new_limit
        tz_offset_hours = user.timezone_offset

        strategy_func = self.mode_strategies.get(mode)

        if strategy_func:
            return strategy_func(
                user_id=user_id,
                set_id=set_id,
                mode=mode,
                user=user,
                current_ts=current_ts,
                today_midnight_ts=today_midnight_ts,
                daily_new_limit=daily_new_limit,
                tz_offset_hours=tz_offset_hours,
                log_prefix=log_prefix
            )
        else:
            logger.warning(f"{log_prefix} Không tìm thấy chiến lược cho chế độ '{mode}'. Chuyển sang logic chờ chung.")
            return self._get_wait_time_for_set(user_id, set_id, current_ts, user.timezone_offset, log_prefix)
