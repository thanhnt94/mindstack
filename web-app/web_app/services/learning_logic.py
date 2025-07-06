# web_app/services/learning_logic.py
import logging
import time
import math
import random
from datetime import datetime, timedelta, time as dt_time, timezone

from ..models import db, User, VocabularySet, Flashcard, UserFlashcardProgress
from ..config import (
    DEFAULT_TIMEZONE_OFFSET,
    SRS_INITIAL_INTERVAL_HOURS, SRS_MAX_INTERVAL_DAYS,
    RETRY_INTERVAL_WRONG_MIN, RETRY_INTERVAL_HARD_MIN, RETRY_INTERVAL_NEW_MIN,
    SCORE_INCREASE_CORRECT, SCORE_INCREASE_HARD,
    SCORE_INCREASE_QUICK_REVIEW_CORRECT, SCORE_INCREASE_QUICK_REVIEW_HARD,
    SCORE_INCREASE_NEW_CARD,
    MODE_SEQ_INTERSPERSED, MODE_SEQ_RANDOM_NEW, MODE_NEW_SEQUENTIAL,
    MODE_DUE_ONLY_RANDOM, MODE_REVIEW_ALL_DUE, MODE_NEW_RANDOM,
    MODE_REVIEW_HARDEST, MODE_CRAM_SET, MODE_CRAM_ALL
)

# Import các hàm chiến lược từ mode_strategies.py
from .mode_strategies import (
    _get_current_unix_timestamp, # Vẫn cần các helper này ở đây để các hàm khác trong class dùng
    _get_midnight_timestamp,
    _get_wait_time_for_set,
    get_card_for_new_sequential_or_random,
    get_card_for_due_only,
    get_card_for_interspersed,
    get_card_for_cram_set,
    get_card_for_cram_all
)


logger = logging.getLogger(__name__)

class LearningLogicService:
    def __init__(self):
        # Ánh xạ các chế độ học với hàm chiến lược tương ứng
        self.mode_strategies = {
            MODE_NEW_SEQUENTIAL: get_card_for_new_sequential_or_random,
            MODE_NEW_RANDOM: get_card_for_new_sequential_or_random,
            MODE_DUE_ONLY_RANDOM: get_card_for_due_only,
            MODE_REVIEW_ALL_DUE: get_card_for_due_only,
            MODE_REVIEW_HARDEST: get_card_for_due_only,
            MODE_SEQ_INTERSPERSED: get_card_for_interspersed,
            MODE_SEQ_RANDOM_NEW: get_card_for_interspersed,
            MODE_CRAM_SET: get_card_for_cram_set,
            MODE_CRAM_ALL: get_card_for_cram_all
        }

    # Các hàm helper vẫn giữ trong class này nếu chúng được dùng bởi các phương thức khác trong class
    # và không chỉ riêng get_next_card_for_review
    def _get_current_unix_timestamp(self, tz_offset_hours):
        return _get_current_unix_timestamp(tz_offset_hours)

    def _get_midnight_timestamp(self, current_timestamp, tz_offset_hours):
        return _get_midnight_timestamp(current_timestamp, tz_offset_hours)

    def _calculate_next_review_time(self, streak_correct=0, total_correct=0, current_timestamp=None, tz_offset_hours=DEFAULT_TIMEZONE_OFFSET):
        """
        Tính toán Unix timestamp cho lần ôn tập tiếp theo dựa trên thuật toán SRS đơn giản.
        """
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
        """
        Xử lý kết quả đánh giá flashcard của người dùng (logic nghiệp vụ).
        Cập nhật tiến trình học, điểm số.
        Args:
            user_id (int): ID của người dùng.
            progress_id (int): ID bản ghi tiến trình (UserFlashcardProgress PK).
            response (int): Kết quả đánh giá (-1: Sai, 0: Mơ hồ, 1: Đúng, 2: Thẻ mới - Tiếp tục).
        Returns:
            tuple: (flashcard_info_updated_dict, next_card_due_time_ts) nếu thành công.
                   (None, None) nếu lỗi.
        """
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

        current_streak_correct = progress.correct_streak
        current_total_correct = progress.correct_count
        current_incorrect_count = progress.incorrect_count
        current_lapse_count = progress.lapse_count
        current_review_count = progress.review_count

        tz_offset_hours = user.timezone_offset
        current_mode = user.current_mode
        current_ts = self._get_current_unix_timestamp(tz_offset_hours)

        quick_review_modes = {MODE_REVIEW_HARDEST, MODE_CRAM_SET, MODE_CRAM_ALL}
        is_quick_review = (current_mode in quick_review_modes)

        new_streak_correct = current_streak_correct
        new_total_correct = current_total_correct
        new_incorrect_count = current_incorrect_count
        new_lapse_count = current_lapse_count
        
        # Sửa lỗi: review_count phải tăng lên cho tất cả các phản hồi
        new_review_count = current_review_count + 1 
        
        score_to_add = 0
        next_review_time = progress.due_time or current_ts + 60 # Fallback

        if is_quick_review:
            if response == 1: score_to_add = SCORE_INCREASE_QUICK_REVIEW_CORRECT
            elif response == 0: score_to_add = SCORE_INCREASE_QUICK_REVIEW_HARD
        else: # Chế độ học SRS thông thường
            if response == 1: # Đúng
                score_to_add = SCORE_INCREASE_CORRECT
                new_streak_correct += 1
                new_total_correct += 1
                next_review_time = self._calculate_next_review_time(new_streak_correct, new_total_correct, current_ts, tz_offset_hours)
            elif response == -1: # Sai
                if current_streak_correct > 0: new_lapse_count += 1 # Chỉ tăng lapse nếu trước đó có streak
                new_streak_correct = 0
                new_incorrect_count += 1
                next_review_time = current_ts + RETRY_INTERVAL_WRONG_MIN * 60
            elif response == 0: # Mơ hồ
                new_streak_correct = 0 # Reset streak
                next_review_time = current_ts + RETRY_INTERVAL_HARD_MIN * 60
            elif response == 2: # Thẻ mới (chỉ tiếp tục)
                # Dành cho thẻ mới học lần đầu, không thay đổi streak/correct_count
                next_review_time = current_ts + RETRY_INTERVAL_NEW_MIN * 60
                # Nếu đây là lần đầu tiên thẻ được học (learned_date is None), đặt learned_date
                if progress.learned_date is None:
                    progress.learned_date = self._get_midnight_timestamp(current_ts, tz_offset_hours)
                score_to_add = SCORE_INCREASE_NEW_CARD # Cộng điểm cho thẻ mới học

            else:
                logger.error(f"{log_prefix} Response không hợp lệ: {response}")
                return None, None

        # Cập nhật đối tượng progress
        progress.last_reviewed = current_ts
        progress.review_count = new_review_count
        progress.due_time = next_review_time
        progress.correct_streak = new_streak_correct
        progress.correct_count = new_total_correct
        progress.incorrect_count = new_incorrect_count
        progress.lapse_count = new_lapse_count

        try:
            db.session.add(progress)
            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật progress thành công.")
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi commit progress: {e}", exc_info=True)
            return None, None

        # Cập nhật điểm người dùng
        if score_to_add != 0:
            user.score = (user.score or 0) + score_to_add
            try:
                db.session.add(user)
                db.session.commit()
                logger.info(f"{log_prefix} Cập nhật điểm người dùng thành công. New score: {user.score}")
            except Exception as e:
                db.session.rollback()
                logger.error(f"{log_prefix} Lỗi khi commit điểm người dùng: {e}", exc_info=True)
                # Không return None, vẫn tiếp tục vì progress đã được lưu

        # Trả về thông tin thẻ đã cập nhật và thời gian đến hạn tiếp theo
        # Kết hợp thông tin từ progress và flashcard để trả về đầy đủ
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
        """
        Xác định flashcard_id tiếp theo để ôn tập hoặc học mới dựa trên user_id, set_id và mode.
        Args:
            user_id (int): ID của người dùng.
            set_id (int): ID của bộ từ cụ thể.
            mode (str): Chế độ học/ôn tập.
        Returns:
            tuple: (flashcard_obj, progress_obj) nếu tìm thấy thẻ.
                   (None, None) nếu không tìm thấy thẻ ngay lập tức.
                   (None, UnixTimestamp) nếu không có thẻ nào và cần chờ đến timestamp đó.
        """
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

        # Lấy hàm chiến lược tương ứng với chế độ
        strategy_func = self.mode_strategies.get(mode)

        if strategy_func:
            # Gọi hàm chiến lược với tất cả các tham số cần thiết
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

