# web_app/routes/flashcard.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, request
import logging
import json
from ..services import learning_logic_service, stats_service, note_service
from ..models import db, User, VocabularySet, Flashcard, UserFlashcardProgress
from ..config import LEARNING_MODE_DISPLAY_NAMES, MODE_AUTOPLAY_REVIEW
from .decorators import login_required

flashcard_bp = Blueprint('flashcard', __name__)
logger = logging.getLogger(__name__)

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
    all_sets = VocabularySet.query.order_by(VocabularySet.title).all()
    
    progressed_set_ids = {p.flashcard.set_id for p in UserFlashcardProgress.query.filter_by(user_id=user_id).join(Flashcard).distinct(Flashcard.set_id)}

    sets_data, current_set_data, in_progress_data, not_started_data = [], None, [], []
    for s in all_sets:
        status = 'not_started'
        if s.set_id == user.current_set_id: status = 'current'
        elif s.set_id in progressed_set_ids: status = 'in_progress'
        set_info = {'set': s, 'status': status}
        if status == 'current': current_set_data = set_info
        elif status == 'in_progress': in_progress_data.append(set_info)
        else: not_started_data.append(set_info)

    if current_set_data: sets_data.append(current_set_data)
    sets_data.extend(sorted(in_progress_data, key=lambda x: x['set'].title))
    sets_data.extend(sorted(not_started_data, key=lambda x: x['set'].title))

    return render_template('flashcard/select_set.html', user=user, sets_data=sets_data)

# --- BẮT ĐẦU THÊM MỚI: Route điều hướng thông minh ---
@flashcard_bp.route('/go-to-learn')
@login_required
def go_to_learn_page():
    """
    Mô tả: Một route điều hướng thông minh.
    Chuyển người dùng đến trang học của bộ thẻ hiện tại nếu có,
    nếu không thì chuyển đến trang chọn bộ thẻ.
    """
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if user and user.current_set_id:
        # Nếu có bộ thẻ đang học, đi thẳng vào học
        logger.info(f"User {user_id} is going to current set {user.current_set_id}")
        return redirect(url_for('flashcard.learn_set', set_id=user.current_set_id))
    else:
        # Nếu không, về trang chọn bộ thẻ
        logger.info(f"User {user_id} has no current set, going to index.")
        return redirect(url_for('flashcard.index'))
# --- KẾT THÚC THÊM MỚI ---

@flashcard_bp.route('/dashboard')
@login_required
def dashboard():
    user_id = session.get('user_id')
    dashboard_data = stats_service.get_dashboard_stats(user_id)
    if not dashboard_data:
        flash("Không thể tải dữ liệu thống kê.", "error")
        return redirect(url_for('flashcard.index'))
    dashboard_data_json = json.dumps(dashboard_data)
    return render_template('dashboard.html', 
                           dashboard_data=dashboard_data,
                           dashboard_data_json=dashboard_data_json)

def _check_edit_permission(user, flashcard_obj):
    """Helper function to check if a user can edit a flashcard."""
    if not user or not flashcard_obj:
        return False
    set_creator_id = flashcard_obj.vocabulary_set.creator_user_id
    return user.user_role == 'admin' or user.user_id == set_creator_id

@flashcard_bp.route('/learn/<int:set_id>')
@login_required
def learn_set(set_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    selected_set = VocabularySet.query.get_or_404(set_id)
    
    user.current_set_id = set_id
    db.session.commit()

    flashcard_obj, progress_obj, wait_time_ts = learning_logic_service.get_next_card_for_review(user_id, set_id, user.current_mode)

    if not flashcard_obj:
        return render_template('flashcard/no_cards_message.html', set_id=set_id, wait_time_ts=wait_time_ts)

    session['current_progress_id'] = progress_obj.progress_id
    
    audio_url = url_for('api.get_card_audio', flashcard_id=flashcard_obj.flashcard_id, side='front') if flashcard_obj.front_audio_content else None
    context_stats = stats_service.get_user_stats_for_context(user_id, set_id)
    user_audio_settings = {'front_audio_enabled': user.front_audio == 1, 'back_audio_enabled': user.back_audio == 1}
    
    can_edit = _check_edit_permission(user, flashcard_obj)

    return render_template(
        'flashcard/learn_card.html', user=user, flashcard=flashcard_obj, progress=progress_obj,
        context_stats=context_stats, is_front=True,
        flashcard_json_string=json.dumps(_serialize_flashcard(flashcard_obj)),
        user_audio_settings_json_string=json.dumps(user_audio_settings),
        is_autoplay_mode=(user.current_mode == MODE_AUTOPLAY_REVIEW),
        audio_url=audio_url, has_back_audio_content=bool(flashcard_obj.back_audio_content),
        can_edit=can_edit
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

    can_edit = _check_edit_permission(user, flashcard_obj)

    return render_template(
        'flashcard/learn_card.html', user=user, flashcard=flashcard_obj, progress=progress,
        context_stats=context_stats, is_front=False,
        flashcard_json_string=json.dumps(_serialize_flashcard(flashcard_obj)),
        user_audio_settings_json_string=json.dumps(user_audio_settings),
        is_autoplay_mode=(user.current_mode == MODE_AUTOPLAY_REVIEW),
        audio_url=audio_url, has_back_audio_content=bool(flashcard_obj.back_audio_content),
        can_edit=can_edit
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
