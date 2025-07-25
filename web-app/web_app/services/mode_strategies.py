# web_app/services/mode_strategies.py
import logging
import random
from datetime import datetime, timedelta, timezone

from ..models import db, Flashcard, UserFlashcardProgress, VocabularySet, User
from ..config import (
    DEFAULT_TIMEZONE_OFFSET,
    RETRY_INTERVAL_HARD_MIN,
    RETRY_INTERVAL_NEW_MIN,
    # BẮT ĐẦU THAY ĐỔI: Import các hằng số chế độ mới
    MODE_SEQUENTIAL_LEARNING,
    MODE_NEW_CARDS_ONLY,
    MODE_REVIEW_ALL_DUE,
    MODE_REVIEW_HARDEST,
    MODE_AUTOPLAY_REVIEW,
    RETRY_INTERVAL_WRONG_MIN,
    SCORE_INCREASE_CORRECT,
    SCORE_INCREASE_NEW_CARD,
    SCORE_INCREASE_QUICK_REVIEW_CORRECT,
    SCORE_INCREASE_QUICK_REVIEW_HARD,
    SRS_INITIAL_INTERVAL_HOURS,
    SRS_MAX_INTERVAL_DAYS
    # KẾT THÚC THAY ĐỔI
)

logger = logging.getLogger(__name__)

# Helper functions (copied from learning_logic.py to be self-contained for strategies)
def _get_current_unix_timestamp(tz_offset_hours):
    """
    Mô tả: Lấy Unix timestamp hiện tại theo múi giờ cụ thể.
    Args:
        tz_offset_hours (int): Độ lệch múi giờ tính bằng giờ (ví dụ: 7 cho UTC+7).
    Returns:
        int: Unix timestamp hiện tại.
    """
    try:
        tz = timedelta(hours=tz_offset_hours)
        now = datetime.now(timezone.utc).astimezone(timezone(tz))
        return int(now.timestamp())
    except Exception as e:
        logger.error(f"Lỗi khi lấy current timestamp: {e}", exc_info=True)
        return int(datetime.now(timezone.utc).timestamp())

def _get_midnight_timestamp(current_timestamp, tz_offset_hours):
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
        tz = timedelta(hours=tz_offset_hours)
        dt_now = datetime.fromtimestamp(current_timestamp, timezone.utc).astimezone(timezone(tz))
        dt_midnight = datetime.combine(dt_now.date(), datetime.min.time(), tzinfo=timezone(tz))
        return int(dt_midnight.timestamp())
    except Exception as e:
        logger.error(f"Lỗi khi tính midnight timestamp: {e}", exc_info=True)
        return int(current_timestamp - (current_timestamp % 86400))

def _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix):
    """
    Mô tả: Xác định thời gian chờ đến khi có thẻ tiếp theo để ôn tập trong một bộ cụ thể.
           Nếu không có thẻ nào đến hạn trong bộ, sẽ chờ đến nửa đêm ngày hôm sau.
    Args:
        user_id (int): ID của người dùng.
        set_id (int): ID của bộ thẻ.
        current_ts (int): Unix timestamp hiện tại.
        tz_offset_hours (int): Độ lệch múi giờ của người dùng.
        log_prefix (str): Tiền tố cho log để dễ theo dõi.
    Returns:
        tuple: (None, None, UnixTimestamp) nếu không có thẻ nào và cần chờ.
    """
    next_due_time_overall = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.is_skipped == 0,
        UserFlashcardProgress.due_time > current_ts
    ).join(Flashcard).filter(Flashcard.set_id == set_id).with_entities(db.func.min(UserFlashcardProgress.due_time)).scalar()

    if next_due_time_overall:
        logger.info(f"{log_prefix} Không có thẻ ngay lập tức. Thẻ tiếp theo đến hạn lúc: {next_due_time_overall}")
        return None, None, next_due_time_overall
    else:
        midnight_next_day_ts = _get_midnight_timestamp(current_ts, tz_offset_hours) + 86400
        logger.info(f"{log_prefix} Không còn thẻ nào để học/ôn trong bộ này. Chờ đến nửa đêm ngày mai: {midnight_next_day_ts}")
        return None, None, midnight_next_day_ts


# --- Strategy Functions for each Learning Mode ---

def get_card_for_new_cards_only(user_id, set_id, mode, user, current_ts, today_midnight_ts, daily_new_limit, tz_offset_hours, log_prefix):
    """
    Mô tả: Chiến lược cho chế độ 'Chỉ học mới' (MODE_NEW_CARDS_ONLY).
           Chỉ tìm thẻ chưa có tiến trình và học theo thứ tự tuần tự.
    Args:
        user_id (int): ID của người dùng.
        set_id (int): ID của bộ từ cụ thể.
        mode (str): Chế độ học/ôn tập.
        user (User): Đối tượng người dùng.
        current_ts (int): Unix timestamp hiện tại.
        today_midnight_ts (int): Unix timestamp của nửa đêm hôm nay.
        daily_new_limit (int): Giới hạn thẻ mới hàng ngày của người dùng.
        tz_offset_hours (int): Độ lệch múi giờ của người dùng.
        log_prefix (str): Tiền tố cho log.
    Returns:
        tuple: (flashcard_obj, progress_obj, wait_time_ts)
    """
    logger.debug(f"{log_prefix} Chế độ: Chỉ học mới (MODE_NEW_CARDS_ONLY).")
    
    learned_today_count = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.learned_date == today_midnight_ts
    ).count()

    if learned_today_count >= daily_new_limit:
        logger.info(f"{log_prefix} Đã đạt giới hạn thẻ MỚI hàng ngày ({learned_today_count}/{daily_new_limit}).")
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)
    
    # Tìm thẻ mới theo thứ tự tuần tự
    new_card = Flashcard.query.filter(
        Flashcard.set_id == set_id,
        ~Flashcard.progresses.any(user_id=user_id)
    ).order_by(Flashcard.flashcard_id.asc()).first()

    if new_card:
        new_progress = UserFlashcardProgress(
            user_id=user_id,
            flashcard_id=new_card.flashcard_id,
            last_reviewed=None,
            due_time=current_ts + RETRY_INTERVAL_NEW_MIN * 60,
            review_count=0,
            learned_date=today_midnight_ts,
            correct_streak=0,
            correct_count=0,
            incorrect_count=0,
            lapse_count=0,
            is_skipped=0
        )
        db.session.add(new_progress)
        db.session.commit()
        logger.info(f"{log_prefix} Tìm thấy và tạo progress cho thẻ MỚI (ID: {new_card.flashcard_id}).")
        return new_card, new_progress, None
    else:
        logger.info(f"{log_prefix} Không còn thẻ MỚI nào trong bộ {set_id} để học.")
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)


def get_card_for_review_modes(user_id, set_id, mode, user, current_ts, today_midnight_ts, daily_new_limit, tz_offset_hours, log_prefix):
    """
    Mô tả: Chiến lược cho các chế độ ôn tập: 'Ôn tập tổng hợp' (MODE_REVIEW_ALL_DUE)
           và 'Chỉ từ khó' (MODE_REVIEW_HARDEST).
           Chỉ tìm các thẻ đã đến hạn hoặc các thẻ khó nhất.
    Args:
        user_id (int): ID của người dùng.
        set_id (int): ID của bộ từ cụ thể (có thể là None cho 'review_all_due').
        mode (str): Chế độ học/ôn tập.
        user (User): Đối tượng người dùng.
        current_ts (int): Unix timestamp hiện tại.
        today_midnight_ts (int): Unix timestamp của nửa đêm hôm nay.
        daily_new_limit (int): Giới hạn thẻ mới hàng ngày của người dùng.
        tz_offset_hours (int): Độ lệch múi giờ của người dùng.
        log_prefix (str): Tiền tố cho log.
    Returns:
        tuple: (flashcard_obj, progress_obj, wait_time_ts)
    """
    logger.debug(f"{log_prefix} Chế độ: Ôn tập (MODE_REVIEW_ALL_DUE hoặc MODE_REVIEW_HARDEST).")
    
    due_cards_query = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.is_skipped == 0,
        UserFlashcardProgress.due_time <= current_ts
    )
    
    # Lọc theo set_id nếu không phải chế độ ôn tập tổng hợp (nếu set_id được cung cấp)
    if set_id:
        due_cards_query = due_cards_query.join(Flashcard).filter(Flashcard.set_id == set_id)
    else:
        # Nếu set_id là None (ví dụ: cho ôn tập tổng hợp toàn bộ),
        # cần đảm bảo chỉ lấy thẻ thuộc các bộ mà người dùng có quyền truy cập
        # (ví dụ: bộ của người dùng tạo hoặc bộ công khai).
        # Hiện tại, chúng ta sẽ cho phép ôn tập tất cả thẻ đến hạn của người dùng.
        pass

    if mode == MODE_REVIEW_HARDEST:
        # Sắp xếp theo số lần sai và số lần lỡ (lapse) giảm dần
        due_cards_query = due_cards_query.order_by(
            UserFlashcardProgress.incorrect_count.desc(),
            UserFlashcardProgress.lapse_count.desc(),
            db.func.random() # Thêm random để có sự đa dạng nếu các chỉ số bằng nhau
        )
    elif mode == MODE_REVIEW_ALL_DUE:
        # Sắp xếp ngẫu nhiên cho ôn tập tổng hợp
        due_cards_query = due_cards_query.order_by(db.func.random())

    due_card_progress = due_cards_query.first() # Lấy một thẻ duy nhất

    if due_card_progress:
        flashcard_to_return = due_card_progress.flashcard
        progress_to_return = due_card_progress
        logger.info(f"{log_prefix} Tìm thấy thẻ ĐẾN HẠN: {flashcard_to_return.flashcard_id} (Mode: {mode}). Review Count: {progress_to_return.review_count}")
        return flashcard_to_return, progress_to_return, None
    else:
        logger.info(f"{log_prefix} Không có thẻ ĐẾN HẠN nào để ôn tập (Mode: {mode}).")
        # Nếu không có thẻ đến hạn, chờ đến nửa đêm ngày mai
        midnight_next_day_ts = _get_midnight_timestamp(current_ts, tz_offset_hours) + 86400
        return None, None, midnight_next_day_ts


def get_card_for_sequential_learning(user_id, set_id, mode, user, current_ts, today_midnight_ts, daily_new_limit, tz_offset_hours, log_prefix):
    """
    Mô tả: Chiến lược cho chế độ 'Học tuần tự' (MODE_SEQUENTIAL_LEARNING).
           Ưu tiên các thẻ đến hạn, sau đó học các thẻ mới theo thứ tự tuần tự.
    Args:
        user_id (int): ID của người dùng.
        set_id (int): ID của bộ từ cụ thể.
        mode (str): Chế độ học/ôn tập.
        user (User): Đối tượng người dùng.
        current_ts (int): Unix timestamp hiện tại.
        today_midnight_ts (int): Unix timestamp của nửa đêm hôm nay.
        daily_new_limit (int): Giới hạn thẻ mới hàng ngày của người dùng.
        tz_offset_hours (int): Độ lệch múi giờ của người dùng.
        log_prefix (str): Tiền tố cho log.
    Returns:
        tuple: (flashcard_obj, progress_obj, wait_time_ts)
    """
    logger.debug(f"{log_prefix} Chế độ: Học tuần tự (MODE_SEQUENTIAL_LEARNING).")
    
    # 1. Tìm thẻ đến hạn trước (ngẫu nhiên trong các thẻ đến hạn của bộ hiện tại)
    due_cards_query = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.is_skipped == 0,
        UserFlashcardProgress.due_time <= current_ts
    ).join(Flashcard).filter(Flashcard.set_id == set_id).order_by(db.func.random())

    due_card_progress = due_cards_query.first()
    
    if due_card_progress:
        flashcard_to_return = due_card_progress.flashcard
        progress_to_return = due_card_progress
        logger.info(f"{log_prefix} Tìm thấy thẻ ĐẾN HẠN: {flashcard_to_return.flashcard_id}.")
        return flashcard_to_return, progress_to_return, None
    
    logger.debug(f"{log_prefix} Không tìm thấy thẻ đến hạn. Đang tìm thẻ mới.")
    
    # 2. Nếu không có thẻ đến hạn, tìm thẻ mới (nếu chưa đạt giới hạn)
    learned_today_count = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.learned_date == today_midnight_ts
    ).count()

    if learned_today_count >= daily_new_limit:
        logger.info(f"{log_prefix} Đã đạt giới hạn thẻ MỚI hàng ngày ({learned_today_count}/{daily_new_limit}).")
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)

    # Tìm thẻ mới theo thứ tự tuần tự
    new_card = Flashcard.query.filter(
        Flashcard.set_id == set_id,
        ~Flashcard.progresses.any(user_id=user_id)
    ).order_by(Flashcard.flashcard_id.asc()).first()

    if new_card:
        new_progress = UserFlashcardProgress(
            user_id=user_id,
            flashcard_id=new_card.flashcard_id,
            last_reviewed=None,
            due_time=current_ts + RETRY_INTERVAL_NEW_MIN * 60,
            review_count=0,
            learned_date=today_midnight_ts,
            correct_streak=0,
            correct_count=0,
            incorrect_count=0,
            lapse_count=0,
            is_skipped=0
        )
        db.session.add(new_progress)
        db.session.commit()
        logger.info(f"{log_prefix} Tìm thấy và tạo progress cho thẻ MỚI: {new_card.flashcard_id}.")
        return new_card, new_progress, None
    else:
        logger.info(f"{log_prefix} Không còn thẻ MỚI nào trong bộ {set_id} để học.")
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)

def get_card_for_autoplay_review(user_id, set_id, mode, user, current_ts, today_midnight_ts, daily_new_limit, tz_offset_hours, log_prefix):
    """
    Mô tả: Chiến lược cho chế độ 'Autoplay' (MODE_AUTOPLAY_REVIEW).
           Tìm một thẻ đã học bất kỳ (có progress) trong bộ hiện tại (hoặc tất cả các bộ nếu set_id là None).
           Thẻ được chọn ngẫu nhiên. Chế độ này không ảnh hưởng đến tiến trình SRS.
    Args:
        user_id (int): ID của người dùng.
        set_id (int): ID của bộ từ cụ thể (hoặc None để chọn từ tất cả các bộ).
        mode (str): Chế độ học/ôn tập.
        user (User): Đối tượng người dùng.
        current_ts (int): Unix timestamp hiện tại.
        today_midnight_ts (int): Unix timestamp của nửa đêm hôm nay.
        daily_new_limit (int): Giới hạn thẻ mới hàng ngày của người dùng.
        tz_offset_hours (int): Độ lệch múi giờ của người dùng.
        log_prefix (str): Tiền tố cho log.
    Returns:
        tuple: (flashcard_obj, progress_obj, wait_time_ts)
    """
    logger.debug(f"{log_prefix} Chế độ: Autoplay (MODE_AUTOPLAY_REVIEW).")

    # Tìm tất cả các thẻ mà người dùng đã có tiến trình (đã học ít nhất 1 lần)
    # trong bộ hiện tại hoặc tất cả các bộ nếu set_id là None.
    learned_cards_query = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.learned_date.isnot(None) # Đảm bảo thẻ đã được học ít nhất 1 lần
    )

    if set_id:
        learned_cards_query = learned_cards_query.join(Flashcard).filter(Flashcard.set_id == set_id)
    else:
        # Nếu không có set_id, lấy tất cả các thẻ đã học của người dùng
        pass
    
    # Lấy tất cả các progress object của các thẻ đã học
    all_learned_progresses = learned_cards_query.all()

    if all_learned_progresses:
        # Chọn ngẫu nhiên một progress object từ danh sách các thẻ đã học
        selected_progress = random.choice(all_learned_progresses)
        flashcard_to_return = selected_progress.flashcard
        progress_to_return = selected_progress # Trả về progress hiện có

        logger.info(f"{log_prefix} Tìm thấy thẻ đã học cho Autoplay: {flashcard_to_return.flashcard_id}.")
        return flashcard_to_return, progress_to_return, None
    else:
        logger.info(f"{log_prefix} Không có thẻ nào đã học để chạy Autoplay.")
        # Nếu không có thẻ nào đã học, không có thẻ để autoplay
        return None, None, None


class LearningLogicService:
    def __init__(self):
        # Ánh xạ các chế độ học với hàm chiến lược tương ứng
        self.mode_strategies = {
            # BẮT ĐẦU THAY ĐỔI: Cập nhật ánh xạ chiến lược cho các chế độ mới
            MODE_SEQUENTIAL_LEARNING: get_card_for_sequential_learning,
            MODE_NEW_CARDS_ONLY: get_card_for_new_cards_only,
            MODE_REVIEW_ALL_DUE: get_card_for_review_modes,
            MODE_REVIEW_HARDEST: get_card_for_review_modes,
            MODE_AUTOPLAY_REVIEW: get_card_for_autoplay_review
            # KẾT THÚC THAY ĐỔI
        }

    # Các hàm helper vẫn giữ trong class này nếu chúng được dùng bởi các phương thức khác trong class
    # và không chỉ riêng get_next_card_for_review
    def _get_current_unix_timestamp(self, tz_offset_hours):
        return _get_current_unix_timestamp(tz_offset_hours)

    def _get_midnight_timestamp(self, current_timestamp, tz_offset_hours):
        return _get_midnight_timestamp(current_timestamp, tz_offset_hours)

    def _calculate_next_review_time(self, streak_correct=0, total_correct=0, current_timestamp=None, tz_offset_hours=DEFAULT_TIMEZONE_OFFSET):
        """
        Mô tả: Tính toán Unix timestamp cho lần ôn tập tiếp theo dựa trên thuật toán SRS đơn giản.
        Args:
            streak_correct (int): Số lần đúng liên tiếp.
            total_correct (int): Tổng số lần đúng.
            current_timestamp (int, optional): Unix timestamp hiện tại. Mặc định là None (sẽ lấy thời gian hiện tại).
            tz_offset_hours (int): Độ lệch múi giờ tính bằng giờ.
        Returns:
            int: Unix timestamp cho lần ôn tập tiếp theo.
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
        Mô tả: Xử lý kết quả đánh giá flashcard của người dùng (logic nghiệp vụ).
               Cập nhật tiến trình học, điểm số.
               Đối với chế độ Autoplay, không cập nhật tiến độ.
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

        # BẮT ĐẦU THAY ĐỔI: Logic đặc biệt cho chế độ Autoplay
        if user.current_mode == MODE_AUTOPLAY_REVIEW:
            logger.info(f"{log_prefix} Chế độ Autoplay, không cập nhật tiến trình và điểm số.")
            # Trong chế độ Autoplay, chúng ta không thay đổi progress hay score
            # Chỉ cần trả về thông tin thẻ hiện tại để chuyển sang thẻ tiếp theo
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
            # next_card_due_time_ts không có ý nghĩa trong autoplay, có thể trả về current_ts
            return flashcard_info_updated, self._get_current_unix_timestamp(user.timezone_offset)
        # KẾT THÚC THAY ĐỔI

        current_streak_correct = progress.correct_streak
        current_total_correct = progress.correct_count
        current_incorrect_count = progress.incorrect_count
        current_lapse_count = progress.lapse_count
        current_review_count = progress.review_count

        tz_offset_hours = user.timezone_offset
        current_mode = user.current_mode
        current_ts = self._get_current_unix_timestamp(tz_offset_hours)

        # BẮT ĐẦU THAY ĐỔI: Loại bỏ các chế độ quick_review_modes cũ, chỉ còn các chế độ SRS
        # Chế độ ôn tập nhanh không thay đổi SRS, chỉ cần tăng điểm
        is_quick_review_score_only_mode = (current_mode == MODE_REVIEW_HARDEST) 
        # KẾT THÚC THAY ĐỔI

        new_streak_correct = current_streak_correct
        new_total_correct = current_total_correct
        new_incorrect_count = current_incorrect_count
        new_lapse_count = current_lapse_count
        
        new_review_count = current_review_count + 1 
        
        score_to_add = 0
        next_review_time = progress.due_time or current_ts + 60 # Fallback

        if is_quick_review_score_only_mode: # Chế độ chỉ tăng điểm, không thay đổi SRS
            if response == 1: score_to_add = SCORE_INCREASE_QUICK_REVIEW_CORRECT
            elif response == 0: score_to_add = SCORE_INCREASE_QUICK_REVIEW_HARD
            # Nếu sai (-1) trong chế độ này, không làm gì với điểm (hoặc có thể trừ điểm nếu muốn)
            # Không thay đổi next_review_time, streak, correct_count, v.v.
        else: # Chế độ học SRS thông thường (bao gồm MODE_SEQUENTIAL_LEARNING, MODE_NEW_CARDS_ONLY, MODE_REVIEW_ALL_DUE)
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
        Mô tả: Xác định flashcard_id tiếp theo để ôn tập hoặc học mới dựa trên user_id, set_id và mode.
               Đây là hàm chính điều phối các chiến lược học tập.
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
            # Fallback về logic chờ chung nếu chế độ không hợp lệ
            return self._get_wait_time_for_set(user_id, set_id, current_ts, user.timezone_offset, log_prefix)
