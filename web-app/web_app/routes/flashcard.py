# web_app/routes/flashcard.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, request
import logging
import json
# BẮT ĐẦU SỬA: Import thêm `or_` từ sqlalchemy
from sqlalchemy import func, or_
# KẾT THÚC SỬA
from ..services import learning_logic_service, stats_service, note_service
from ..models import db, User, VocabularySet, Flashcard, UserFlashcardProgress
from ..config import LEARNING_MODE_DISPLAY_NAMES, MODE_AUTOPLAY_REVIEW, SETS_PER_PAGE, MODE_NEW_CARDS_ONLY, MODE_SEQUENTIAL_LEARNING, MODE_REVIEW_ALL_DUE, MODE_REVIEW_HARDEST
from .decorators import login_required

flashcard_bp = Blueprint('flashcard', __name__)
logger = logging.getLogger(__name__)

class CustomPagination:
    def __init__(self, page, per_page, total, items):
        self.page = page
        self.per_page = per_page
        self.total = total
        self.items = items
        self.pages = (total + per_page - 1) // per_page if total > 0 else 0
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1
        self.next_num = page + 1
    
    def iter_pages(self, left_edge=1, right_edge=1, left_current=1, right_current=2):
        last_page = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last_page + 1 != num:
                    yield None
                yield num
                last_page = num

def _sort_sets_by_progress(set_items, total_key, completed_key):
    def custom_sort_key(set_item):
        total = getattr(set_item, total_key, 0)
        completed = getattr(set_item, completed_key, 0)
        title = getattr(set_item, 'title', '')
        if total == 0: return (float('-inf'), title) 
        percentage = (completed * 100 / total)
        if percentage == 100: return (0, title) 
        return (-percentage, title)
    return sorted(set_items, key=custom_sort_key)

def _serialize_flashcard(flashcard_obj):
    if not flashcard_obj: return {}
    return {
        'flashcard_id': flashcard_obj.flashcard_id, 'front': flashcard_obj.front,
        'back': flashcard_obj.back, 'front_audio_content': flashcard_obj.front_audio_content,
        'back_audio_content': flashcard_obj.back_audio_content, 'front_img': flashcard_obj.front_img,
        'back_img': flashcard_obj.back_img, 'notification_text': flashcard_obj.notification_text,
        'set_id': flashcard_obj.set_id
    }

@flashcard_bp.route('/')
@login_required
def index():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    page_started = request.args.get('page_started', 1, type=int)
    page_new = request.args.get('page_new', 1, type=int)
    # BẮT ĐẦU THÊM MỚI: Lấy tham số tìm kiếm
    search_query = request.args.get('q', None)
    # KẾT THÚC THÊM MỚI

    progressed_set_ids = {row[0] for row in db.session.query(Flashcard.set_id).join(UserFlashcardProgress).filter(UserFlashcardProgress.user_id == user_id).distinct().all()}

    started_sets_with_progress = []
    if progressed_set_ids:
        # BẮT ĐẦU SỬA: Thêm logic lọc tìm kiếm cho các bộ đã bắt đầu
        started_sets_query = VocabularySet.query.filter(VocabularySet.set_id.in_(progressed_set_ids))
        if search_query:
            search_term = f"%{search_query}%"
            started_sets_query = started_sets_query.filter(
                or_(
                    VocabularySet.title.ilike(search_term),
                    VocabularySet.description.ilike(search_term)
                )
            )
        started_sets_raw = started_sets_query.all()
        # KẾT THÚC SỬA

        total_cards_map = dict(db.session.query(Flashcard.set_id, func.count(Flashcard.flashcard_id)).filter(Flashcard.set_id.in_(progressed_set_ids)).group_by(Flashcard.set_id).all())
        learned_cards_map = dict(db.session.query(Flashcard.set_id, func.count(db.distinct(UserFlashcardProgress.flashcard_id))).join(Flashcard).filter(UserFlashcardProgress.user_id == user_id, Flashcard.set_id.in_(progressed_set_ids), UserFlashcardProgress.learned_date.isnot(None)).group_by(Flashcard.set_id).all())
        for set_item in started_sets_raw:
            set_item.total_cards = total_cards_map.get(set_item.set_id, 0)
            set_item.learned_cards = learned_cards_map.get(set_item.set_id, 0)
            started_sets_with_progress.append(set_item)

    sorted_started_sets = _sort_sets_by_progress(started_sets_with_progress, total_key='total_cards', completed_key='learned_cards')
    total_items_started = len(sorted_started_sets)
    start_index_started = (page_started - 1) * SETS_PER_PAGE
    end_index_started = start_index_started + SETS_PER_PAGE
    paginated_started_sets_items = sorted_started_sets[start_index_started:end_index_started]
    started_sets_pagination = CustomPagination(page_started, SETS_PER_PAGE, total_items_started, paginated_started_sets_items)

    # BẮT ĐẦU SỬA: Thêm logic lọc tìm kiếm cho các bộ mới
    new_sets_query = VocabularySet.query.filter(VocabularySet.is_public == 1, VocabularySet.set_id.notin_(progressed_set_ids))
    if search_query:
        search_term = f"%{search_query}%"
        new_sets_query = new_sets_query.filter(
            or_(
                VocabularySet.title.ilike(search_term),
                VocabularySet.description.ilike(search_term)
            )
        )
    new_sets_query = new_sets_query.order_by(VocabularySet.title.asc())
    # KẾT THÚC SỬA
    new_sets_pagination = new_sets_query.paginate(page=page_new, per_page=SETS_PER_PAGE, error_out=False)
    
    return render_template('flashcard/select_set.html', 
                           user=user, 
                           started_sets_pagination=started_sets_pagination,
                           new_sets_pagination=new_sets_pagination,
                           search_query=search_query) # Thêm search_query vào context

@flashcard_bp.route('/go-to-learn')
@login_required
def go_to_learn_page():
    user = User.query.get(session.get('user_id'))
    if user and user.current_set_id:
        return redirect(url_for('flashcard.learn_set', set_id=user.current_set_id))
    else:
        return redirect(url_for('flashcard.index'))

@flashcard_bp.route('/learn/<int:set_id>')
@login_required
def learn_set(set_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    user.current_set_id = set_id
    db.session.commit()

    flashcard_obj, progress_obj, wait_time_ts = learning_logic_service.get_next_card_for_review(user_id, set_id, user.current_mode)

    if not flashcard_obj:
        return render_template('flashcard/no_cards_message.html', set_id=set_id, wait_time_ts=wait_time_ts)

    session['current_progress_id'] = progress_obj.progress_id
    
    audio_url = url_for('api.get_card_audio', flashcard_id=flashcard_obj.flashcard_id, side='front') if flashcard_obj.front_audio_content else None
    context_stats = stats_service.get_user_stats_for_context(user_id, set_id)
    user_audio_settings = {'front_audio_enabled': user.front_audio == 1, 'back_audio_enabled': user.back_audio == 1}
    
    can_edit = (user.user_id == flashcard_obj.vocabulary_set.creator_user_id)
    can_feedback = not can_edit
    
    note = note_service.get_note_by_flashcard_id(user_id, flashcard_obj.flashcard_id)
    has_note = note is not None

    return render_template(
        'flashcard/learn_card.html', user=user, flashcard=flashcard_obj, progress=progress_obj,
        context_stats=context_stats, is_front=True,
        user_audio_settings_json_string=json.dumps(user_audio_settings),
        is_autoplay_mode=(user.current_mode == MODE_AUTOPLAY_REVIEW),
        audio_url=audio_url, has_back_audio_content=bool(flashcard_obj.back_audio_content),
        can_edit=can_edit,
        can_feedback=can_feedback,
        has_note=has_note,
        current_mode=user.current_mode,
        set_total_cards=context_stats['set_total_cards'],
        set_learned_cards=context_stats['set_learned_cards'],
        set_mastered_cards=context_stats['set_mastered_cards'],
        set_due_cards=context_stats['set_due_cards']
    )

@flashcard_bp.route('/flip/<int:progress_id>')
@login_required
def flip_card(progress_id):
    progress = UserFlashcardProgress.query.get_or_404(progress_id)
    if progress.user_id != session.get('user_id'):
        flash("Thẻ không hợp lệ.", "error")
        return redirect(url_for('flashcard.index'))

    user = User.query.get(session.get('user_id'))
    flashcard_obj = progress.flashcard
    
    audio_url = url_for('api.get_card_audio', flashcard_id=flashcard_obj.flashcard_id, side='back') if flashcard_obj.back_audio_content else None
    context_stats = stats_service.get_user_stats_for_context(user.user_id, flashcard_obj.set_id)
    user_audio_settings = {'front_audio_enabled': user.front_audio == 1, 'back_audio_enabled': user.back_audio == 1}

    can_edit = (user.user_id == flashcard_obj.vocabulary_set.creator_user_id)
    can_feedback = not can_edit

    note = note_service.get_note_by_flashcard_id(user.user_id, flashcard_obj.flashcard_id)
    has_note = note is not None

    return render_template(
        'flashcard/learn_card.html', user=user, flashcard=flashcard_obj, progress=progress,
        context_stats=context_stats, is_front=False,
        user_audio_settings_json_string=json.dumps(user_audio_settings),
        is_autoplay_mode=(user.current_mode == MODE_AUTOPLAY_REVIEW),
        audio_url=audio_url, has_back_audio_content=bool(flashcard_obj.back_audio_content),
        can_edit=can_edit,
        can_feedback=can_feedback,
        has_note=has_note,
        current_mode=user.current_mode,
        set_total_cards=context_stats['set_total_cards'],
        set_learned_cards=context_stats['set_learned_cards'],
        set_mastered_cards=context_stats['set_mastered_cards'],
        set_due_cards=context_stats['set_due_cards']
    )

@flashcard_bp.route('/rate/<int:progress_id>/<string:response_str>')
@login_required
def rate_card(progress_id, response_str):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    progress = UserFlashcardProgress.query.get(progress_id)
    
    if not progress or progress.user_id != user_id:
        flash("Thẻ không hợp lệ.", "error")
        return redirect(url_for('flashcard.index'))

    current_set_id = progress.flashcard.set_id

    if user.current_mode == MODE_AUTOPLAY_REVIEW and response_str == 'next':
        return redirect(url_for('flashcard.learn_set', set_id=current_set_id))

    response_mapping = {'forget': -1, 'vague': 0, 'remember': 1, 'continue': 2}
    response = response_mapping.get(response_str)

    if response is not None:
        learning_logic_service.process_review_response(user_id, progress_id, response)
    else:
        flash("Phản hồi không hợp lệ.", "error")

    return redirect(url_for('flashcard.learn_set', set_id=current_set_id))

@flashcard_bp.route('/select_mode')
@login_required
def select_mode():
    user = User.query.get(session.get('user_id'))
    return render_template('flashcard/select_mode.html', modes=LEARNING_MODE_DISPLAY_NAMES, current_mode=user.current_mode)

@flashcard_bp.route('/set_learning_mode/<string:mode_code>')
@login_required
def set_learning_mode(mode_code):
    if mode_code not in LEARNING_MODE_DISPLAY_NAMES:
        flash("Chế độ học không hợp lệ.", "error")
        return redirect(url_for('flashcard.select_mode'))
    
    user = User.query.get(session.get('user_id'))
    user.current_mode = mode_code
    db.session.commit()
    flash(f"Chế độ học đã được thay đổi thành '{LEARNING_MODE_DISPLAY_NAMES[mode_code]}'.", "success")
    
    current_set_id = user.current_set_id 
    
    if current_set_id:
        return redirect(url_for('flashcard.learn_set', set_id=current_set_id))
    return redirect(url_for('flashcard.index'))

@flashcard_bp.route('/select_set_page')
@login_required
def select_set_page():
    return redirect(url_for('flashcard.index'))
