# web_app/services/mode_strategies.py
import logging
import random
from datetime import datetime, timedelta, timezone

from ..models import db, Flashcard, UserFlashcardProgress, VocabularySet, User
from ..config import (
    RETRY_INTERVAL_NEW_MIN,
    MODE_NEW_SEQUENTIAL, MODE_NEW_RANDOM,
    MODE_DUE_ONLY_RANDOM, MODE_REVIEW_ALL_DUE, MODE_REVIEW_HARDEST,
    MODE_SEQ_INTERSPERSED, MODE_SEQ_RANDOM_NEW,
    MODE_CRAM_SET, MODE_CRAM_ALL
)

logger = logging.getLogger(__name__)

# Helper functions (copied from learning_logic.py to be self-contained for strategies)
def _get_current_unix_timestamp(tz_offset_hours):
    try:
        tz = timedelta(hours=tz_offset_hours)
        now = datetime.now(timezone.utc).astimezone(timezone(tz))
        return int(now.timestamp())
    except Exception as e:
        logger.error(f"Lỗi khi lấy current timestamp: {e}", exc_info=True)
        return int(datetime.now(timezone.utc).timestamp())

def _get_midnight_timestamp(current_timestamp, tz_offset_hours):
    try:
        tz = timedelta(hours=tz_offset_hours)
        dt_now = datetime.fromtimestamp(current_timestamp, timezone.utc).astimezone(timezone(tz))
        dt_midnight = datetime.combine(dt_now.date(), datetime.min.time(), tzinfo=timezone(tz))
        return int(dt_midnight.timestamp())
    except Exception as e:
        logger.error(f"Lỗi khi tính midnight timestamp: {e}", exc_info=True)
        return int(current_timestamp - (current_timestamp % 86400))

def _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix):
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

def get_card_for_new_sequential_or_random(user_id, set_id, mode, user, current_ts, today_midnight_ts, daily_new_limit, tz_offset_hours, log_prefix):
    """Logic for MODE_NEW_SEQUENTIAL and MODE_NEW_RANDOM."""
    logger.debug(f"{log_prefix} Chế độ: Học mới (chỉ tìm thẻ chưa có progress).")
    
    learned_today_count = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.learned_date == today_midnight_ts
    ).count()

    if learned_today_count >= daily_new_limit:
        logger.info(f"{log_prefix} Đã đạt giới hạn thẻ MỚI hàng ngày ({learned_today_count}/{daily_new_limit}) (Mode: {mode}).")
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)
    
    new_card_query = Flashcard.query.filter(
        Flashcard.set_id == set_id,
        ~Flashcard.progresses.any(user_id=user_id)
    )
    
    if mode == MODE_NEW_SEQUENTIAL:
        new_card_query = new_card_query.order_by(Flashcard.flashcard_id.asc())
    elif mode == MODE_NEW_RANDOM:
        new_card_query = new_card_query.order_by(db.func.random())

    new_card = new_card_query.first()

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
        logger.info(f"{log_prefix} Tìm thấy và tạo progress cho thẻ MỚI (ID: {new_card.flashcard_id}) (Mode: {mode}).")
        return new_card, new_progress, None
    else:
        logger.info(f"{log_prefix} Không còn thẻ MỚI nào trong bộ {set_id} để học (Mode: {mode}).")
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)


def get_card_for_due_only(user_id, set_id, mode, user, current_ts, today_midnight_ts, daily_new_limit, tz_offset_hours, log_prefix):
    """Logic for MODE_DUE_ONLY_RANDOM, MODE_REVIEW_ALL_DUE, MODE_REVIEW_HARDEST."""
    logger.debug(f"{log_prefix} Chế độ: Ôn tập (chỉ tìm thẻ đến hạn).")
    due_cards_query = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.is_skipped == 0,
        UserFlashcardProgress.due_time <= current_ts
    ).join(Flashcard).filter(Flashcard.set_id == set_id)

    if mode == MODE_REVIEW_HARDEST:
        due_cards_query = due_cards_query.order_by(
            UserFlashcardProgress.incorrect_count.desc(),
            UserFlashcardProgress.lapse_count.desc()
        )
    elif mode == MODE_DUE_ONLY_RANDOM or mode == MODE_REVIEW_ALL_DUE:
        due_cards_query = due_cards_query.order_by(db.func.random())

    due_cards = due_cards_query.all()
    
    if due_cards:
        selected_progress = due_cards[0]
        flashcard_to_return = selected_progress.flashcard
        progress_to_return = selected_progress
        logger.info(f"{log_prefix} Tìm thấy thẻ ĐẾN HẠN: {flashcard_to_return.flashcard_id} (Mode: {mode}). Review Count: {progress_to_return.review_count}")
        return flashcard_to_return, progress_to_return, None
    else:
        logger.info(f"{log_prefix} Không có thẻ ĐẾN HẠN nào trong bộ {set_id} (Mode: {mode}).")
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)


def get_card_for_interspersed(user_id, set_id, mode, user, current_ts, today_midnight_ts, daily_new_limit, tz_offset_hours, log_prefix):
    """Logic for MODE_SEQ_INTERSPERSED and MODE_SEQ_RANDOM_NEW (mixed modes)."""
    logger.debug(f"{log_prefix} Chế độ: Hỗn hợp (ưu tiên đến hạn, sau đó thẻ mới).")
    # 1. Tìm thẻ đến hạn trước
    due_cards_query = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.is_skipped == 0,
        UserFlashcardProgress.due_time <= current_ts
    ).join(Flashcard).filter(Flashcard.set_id == set_id)

    if mode == MODE_SEQ_INTERSPERSED:
        # Sửa lỗi: Sắp xếp ngẫu nhiên cho thẻ đến hạn trong chế độ "Ghi nhớ sâu tuần tự"
        due_cards_query = due_cards_query.order_by(db.func.random())
    elif mode == MODE_SEQ_RANDOM_NEW:
        due_cards_query = due_cards_query.order_by(db.func.random())

    due_cards = due_cards_query.all()
    
    if due_cards:
        selected_progress = due_cards[0]
        flashcard_to_return = selected_progress.flashcard
        progress_to_return = selected_progress
        logger.info(f"{log_prefix} Tìm thấy thẻ ĐẾN HẠN: {flashcard_to_return.flashcard_id} (Mode: {mode}). Review Count: {progress_to_return.review_count}")
        return flashcard_to_return, progress_to_return, None
    
    logger.debug(f"{log_prefix} Không tìm thấy thẻ đến hạn. Đang tìm thẻ mới.")
    # 2. Nếu không có thẻ đến hạn, tìm thẻ mới (nếu chưa đạt giới hạn)
    learned_today_count = UserFlashcardProgress.query.filter(
        UserFlashcardProgress.user_id == user_id,
        UserFlashcardProgress.learned_date == today_midnight_ts
    ).count()

    if learned_today_count >= daily_new_limit:
        logger.info(f"{log_prefix} Đã đạt giới hạn thẻ MỚI hàng ngày ({learned_today_count}/{daily_new_limit}) (Mode: {mode}).")
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)

    new_card_query = Flashcard.query.filter(
        Flashcard.set_id == set_id,
        ~Flashcard.progresses.any(user_id=user_id)
    )
    
    if mode == MODE_SEQ_INTERSPERSED:
        # Thẻ mới vẫn sắp xếp tuần tự cho chế độ "Ghi nhớ sâu tuần tự"
        new_card_query = new_card_query.order_by(Flashcard.flashcard_id.asc())
    elif mode == MODE_SEQ_RANDOM_NEW:
        new_card_query = new_card_query.order_by(db.func.random())

    new_card = new_card_query.first()

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
        logger.info(f"{log_prefix} Tìm thấy và tạo progress cho thẻ MỚI: {new_card.flashcard_id} (Mode: {mode}).")
        return new_card, new_progress, None
    else:
        logger.info(f"{log_prefix} Không còn thẻ MỚI nào trong bộ {set_id} (Mode: {mode}).")
        return _get_wait_time_for_set(user_id, set_id, current_ts, tz_offset_hours, log_prefix)


def get_card_for_cram_set(user_id, set_id, mode, user, current_ts, today_midnight_ts, daily_new_limit, tz_offset_hours, log_prefix):
    """Logic for MODE_CRAM_SET."""
    logger.debug(f"{log_prefix} Chế độ: Cram theo bộ '{mode}'.")
    all_cards_in_set = Flashcard.query.filter(Flashcard.set_id == set_id).all()
    
    if not all_cards_in_set:
        logger.info(f"{log_prefix} Không có thẻ nào trong bộ {set_id} để ôn tập (Mode: {mode}).")
        return None, None, None

    user_progresses = {p.flashcard_id: p for p in UserFlashcardProgress.query.filter_by(user_id=user_id).join(Flashcard).filter(Flashcard.set_id == set_id).all()}
    
    candidate_cards = []
    for card in all_cards_in_set:
        progress = user_progresses.get(card.flashcard_id)
        if progress and progress.last_reviewed and (current_ts - progress.last_reviewed < 300): # 300s = 5 phút
            continue
        candidate_cards.append((card, progress))
    
    if not candidate_cards:
        logger.info(f"{log_prefix} Tất cả thẻ trong bộ đã được cram gần đây. Chọn ngẫu nhiên một thẻ bất kỳ để cram lại.")
        selected_card_tuple = random.choice([(c, user_progresses.get(c.flashcard_id)) for c in all_cards_in_set])
        selected_card = selected_card_tuple[0]
        selected_progress = selected_card_tuple[1]
    else:
        selected_card, selected_progress = random.choice(candidate_cards)

    if not selected_progress:
        selected_progress = UserFlashcardProgress(
            user_id=user_id,
            flashcard_id=selected_card.flashcard_id,
            last_reviewed=None,
            due_time=current_ts + RETRY_INTERVAL_NEW_MIN * 60,
            review_count=0,
            learned_date=None,
            correct_streak=0,
            correct_count=0,
            incorrect_count=0,
            lapse_count=0,
            is_skipped=0
        )
        db.session.add(selected_progress)
        db.session.commit()
        logger.info(f"{log_prefix} Đã tạo progress mới cho thẻ {selected_card.flashcard_id} trong chế độ Cram.")
    
    logger.info(f"{log_prefix} Tìm thấy thẻ CRAM: {selected_card.flashcard_id} (Mode: {mode}). Review Count: {selected_progress.review_count}")
    return selected_card, selected_progress, None


def get_card_for_cram_all(user_id, set_id, mode, user, current_ts, today_midnight_ts, daily_new_limit, tz_offset_hours, log_prefix):
    """Logic for MODE_CRAM_ALL."""
    logger.debug(f"{log_prefix} Chế độ: Cram All '{mode}'.")
    
    all_user_cards_query = Flashcard.query.join(VocabularySet).filter(
        VocabularySet.creator_user_id == user_id
    )
    
    all_user_cards = all_user_cards_query.all()

    if not all_user_cards:
        logger.info(f"{log_prefix} Không có thẻ nào để ôn tập (Mode: {mode}).")
        return None, None, None

    user_progresses = {p.flashcard_id: p for p in UserFlashcardProgress.query.filter_by(user_id=user_id).all()}
    
    candidate_cards = []
    for card in all_user_cards:
        progress = user_progresses.get(card.flashcard_id)
        if progress and progress.last_reviewed and (current_ts - progress.last_reviewed < 300):
            continue
        candidate_cards.append((card, progress))
    
    if not candidate_cards:
        logger.info(f"{log_prefix} Tất cả thẻ đã được cram gần đây. Chọn ngẫu nhiên một thẻ bất kỳ để cram lại.")
        selected_card_tuple = random.choice([(c, user_progresses.get(c.flashcard_id)) for c in all_user_cards])
        selected_card = selected_card_tuple[0]
        selected_progress = selected_card_tuple[1]
    else:
        selected_card, selected_progress = random.choice(candidate_cards)

    if not selected_progress:
        selected_progress = UserFlashcardProgress(
            user_id=user_id,
            flashcard_id=selected_card.flashcard_id,
            last_reviewed=None,
            due_time=current_ts + RETRY_INTERVAL_NEW_MIN * 60,
            review_count=0,
            learned_date=None,
            correct_streak=0,
            correct_count=0,
            incorrect_count=0,
            lapse_count=0,
            is_skipped=0
        )
        db.session.add(selected_progress)
        db.session.commit()
        logger.info(f"{log_prefix} Đã tạo progress mới cho thẻ {selected_card.flashcard_id} trong chế độ Cram All.")
    
    logger.info(f"{log_prefix} Tìm thấy thẻ CRAM: {selected_card.flashcard_id} (Mode: {mode}). Review Count: {selected_progress.review_count}")
    return selected_card, selected_progress, None

