import os
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, send_file
import logging
import time # For timestamp
from datetime import datetime, timedelta, timezone # For consistent datetime handling
from functools import wraps # For decorator
import asyncio # Để chạy các hàm async từ audio_service
import json # Để chuyển đổi đối tượng Python thành JSON string

# Import individual services from the new structure
from .services import learning_logic_service, user_service, stats_service, audio_service
from .models import db, User, VocabularySet, Flashcard, UserFlashcardProgress # Still need models for queries
from .config import (
    LEARNING_MODE_DISPLAY_NAMES, IMAGES_DIR,
    DEFAULT_LEARNING_MODE,
    MODE_AUTOPLAY_REVIEW
)

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

# --- Helper function to serialize Flashcard object to dictionary ---
def _serialize_flashcard(flashcard_obj):
    """
    Mô tả: Chuyển đổi một đối tượng Flashcard SQLAlchemy thành một dictionary
           có thể được JSON serialize.
    Args:
        flashcard_obj (Flashcard): Đối tượng Flashcard cần chuyển đổi.
    Returns:
        dict: Dictionary chứa các thuộc tính cần thiết của Flashcard.
    """
    if not flashcard_obj:
        return {}
    
    return {
        'flashcard_id': flashcard_obj.flashcard_id,
        'front': flashcard_obj.front,
        'back': flashcard_obj.back,
        'front_audio_content': flashcard_obj.front_audio_content,
        'back_audio_content': flashcard_obj.back_audio_content,
        'front_img': flashcard_obj.front_img,
        'back_img': flashcard_obj.back_img,
        'notification_text': flashcard_obj.notification_text,
        'set_id': flashcard_obj.set_id
    }

# --- Decorator to check login ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Vui lòng đăng nhập để truy cập trang này.", "info")
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator mới để kiểm tra quyền admin
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        if not user or user.user_role != 'admin':
            flash("Bạn không có quyền truy cập trang quản trị.", "error")
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        user, status = user_service.authenticate_user(username, password)
        if status == "success":
            session['user_id'] = user.user_id
            session['username'] = user.username
            session['user_role'] = user.user_role
            flash(f"Chào mừng, {user.username or user.telegram_id}! Bạn đã đăng nhập thành công.", "success")
            return redirect(url_for('main.index'))
        else:
            flash("Tên đăng nhập hoặc mật khẩu không đúng.", "error")
            return render_template('auth/login.html')
    return render_template('auth/login.html')

@main_bp.route('/logout')
def logout():
    session.clear()
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for('main.login'))

@main_bp.route('/')
@login_required
def index():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    all_sets = VocabularySet.query.order_by(VocabularySet.title).all()
    
    progressed_set_ids = {p.flashcard.set_id for p in UserFlashcardProgress.query.filter_by(user_id=user_id).join(Flashcard).distinct(Flashcard.set_id)}

    sets_data = []
    current_set_data = None
    in_progress_data = []
    not_started_data = []

    for s in all_sets:
        status = 'not_started'
        if s.set_id == user.current_set_id:
            status = 'current'
        elif s.set_id in progressed_set_ids:
            status = 'in_progress'
        
        set_info = {'set': s, 'status': status}
        if status == 'current':
            current_set_data = set_info
        elif status == 'in_progress':
            in_progress_data.append(set_info)
        else:
            not_started_data.append(set_info)

    if current_set_data:
        sets_data.append(current_set_data)
    sets_data.extend(sorted(in_progress_data, key=lambda x: x['set'].title))
    sets_data.extend(sorted(not_started_data, key=lambda x: x['set'].title))

    return render_template('flashcard/select_set.html', user=user, sets_data=sets_data)

@main_bp.route('/learn/<int:set_id>')
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
    
    # SỬA LỖI AUDIO: Chuẩn bị sẵn URL audio cho mặt trước
    audio_url = None
    if flashcard_obj.front_audio_content:
        audio_url = url_for('main.get_card_audio', flashcard_id=flashcard_obj.flashcard_id, side='front')

    context_stats = stats_service.get_user_stats_for_context(user_id, set_id)
    user_audio_settings = {'front_audio_enabled': user.front_audio == 1, 'back_audio_enabled': user.back_audio == 1}

    return render_template(
        'flashcard/learn_card.html',
        user=user,
        flashcard=flashcard_obj,
        progress=progress_obj,
        context_stats=context_stats,
        is_front=True,
        flashcard_json_string=json.dumps(_serialize_flashcard(flashcard_obj)),
        user_audio_settings_json_string=json.dumps(user_audio_settings),
        is_autoplay_mode=(user.current_mode == MODE_AUTOPLAY_REVIEW),
        audio_url=audio_url,  # Truyền URL đã chuẩn bị sẵn
        has_back_audio_content=bool(flashcard_obj.back_audio_content)
    )

@main_bp.route('/flip/<int:progress_id>')
@login_required
def flip_card(progress_id):
    progress = UserFlashcardProgress.query.get_or_404(progress_id)
    if progress.user_id != session.get('user_id'):
        flash("Thẻ không hợp lệ.", "error")
        return redirect(url_for('main.index'))

    user = User.query.get(session.get('user_id'))
    flashcard_obj = progress.flashcard
    
    # SỬA LỖI AUDIO: Chuẩn bị sẵn URL audio cho mặt sau
    audio_url = None
    if flashcard_obj.back_audio_content:
        audio_url = url_for('main.get_card_audio', flashcard_id=flashcard_obj.flashcard_id, side='back')

    context_stats = stats_service.get_user_stats_for_context(user.user_id, flashcard_obj.set_id)
    user_audio_settings = {'front_audio_enabled': user.front_audio == 1, 'back_audio_enabled': user.back_audio == 1}

    return render_template(
        'flashcard/learn_card.html',
        user=user,
        flashcard=flashcard_obj,
        progress=progress,
        context_stats=context_stats,
        is_front=False,
        flashcard_json_string=json.dumps(_serialize_flashcard(flashcard_obj)),
        user_audio_settings_json_string=json.dumps(user_audio_settings),
        is_autoplay_mode=(user.current_mode == MODE_AUTOPLAY_REVIEW),
        audio_url=audio_url, # Truyền URL đã chuẩn bị sẵn
        has_back_audio_content=bool(flashcard_obj.back_audio_content) # Thêm biến này để JS biết có cache hay không
    )

@main_bp.route('/rate/<int:progress_id>/<string:response_str>')
@login_required
def rate_card(progress_id, response_str):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    progress = UserFlashcardProgress.query.get(progress_id)
    
    if not progress or progress.user_id != user_id:
        flash("Thẻ không hợp lệ.", "error")
        return redirect(url_for('main.index'))

    current_set_id = progress.flashcard.set_id

    if user.current_mode == MODE_AUTOPLAY_REVIEW and response_str == 'next':
        return redirect(url_for('main.learn_set', set_id=current_set_id))

    response_mapping = {'forget': -1, 'vague': 0, 'remember': 1, 'continue': 2}
    response = response_mapping.get(response_str)

    if response is not None:
        learning_logic_service.process_review_response(user_id, progress_id, response)
    else:
        flash("Phản hồi không hợp lệ.", "error")

    return redirect(url_for('main.learn_set', set_id=current_set_id))

@main_bp.route('/select_mode')
@login_required
def select_mode():
    user = User.query.get(session.get('user_id'))
    return render_template('flashcard/select_mode.html', modes=LEARNING_MODE_DISPLAY_NAMES, current_mode=user.current_mode)

@main_bp.route('/set_learning_mode/<string:mode_code>')
@login_required
def set_learning_mode(mode_code):
    if mode_code not in LEARNING_MODE_DISPLAY_NAMES:
        flash("Chế độ học không hợp lệ.", "error")
        return redirect(url_for('main.select_mode'))
    
    user = User.query.get(session.get('user_id'))
    user.current_mode = mode_code
    db.session.commit()
    flash(f"Chế độ học đã được thay đổi thành '{LEARNING_MODE_DISPLAY_NAMES[mode_code]}'.", "success")
    
    current_set_id = session.get('current_set_id')
    if current_set_id:
        return redirect(url_for('main.learn_set', set_id=current_set_id))
    return redirect(url_for('main.index'))

@main_bp.route('/select_set_page')
@login_required
def select_set_page():
    return redirect(url_for('main.index'))

@main_bp.route('/api/card_audio/<int:flashcard_id>/<string:side>')
@login_required
def get_card_audio(flashcard_id, side):
    if side not in ['front', 'back']:
        return {"error": "Invalid side specified"}, 400

    flashcard = Flashcard.query.get_or_404(flashcard_id)
    audio_content = flashcard.front_audio_content if side == 'front' else flashcard.back_audio_content

    if not audio_content:
        return {"error": "No audio content for this side"}, 404

    try:
        audio_file_path = asyncio.run(audio_service.get_cached_or_generate_audio(audio_content))
        if audio_file_path and os.path.exists(audio_file_path):
            return send_file(audio_file_path, mimetype="audio/mpeg")
        else:
            logger.error(f"API Audio: Không thể tạo hoặc tìm thấy file audio cho Flashcard ID {flashcard_id}, side '{side}'.")
            return {"error": "Failed to generate or retrieve audio file"}, 500
    except Exception as e:
        logger.error(f"API Audio: Lỗi không mong muốn khi phục vụ audio cho Flashcard ID {flashcard_id}, side '{side}': {e}", exc_info=True)
        return {"error": "Internal server error"}, 500

@main_bp.route('/images/<path:filename>')
def serve_image(filename):
    return send_file(os.path.join(IMAGES_DIR, filename))

# Các route admin không thay đổi
@main_bp.route('/admin/users')
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin/manage_users.html', users=users)

@main_bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    if request.method == 'POST':
        data = request.form.to_dict()
        updated_user, status = user_service.update_user_profile(user_id, data)
        if status == "success":
            flash(f"Cập nhật thông tin người dùng '{updated_user.username or updated_user.telegram_id}' thành công.", "success")
            return redirect(url_for('main.manage_users'))
        else:
            flash(f"Lỗi khi cập nhật: {status}", "error")
            return render_template('admin/edit_user.html', user=user_to_edit, roles=['user', 'admin'])
    return render_template('admin/edit_user.html', user=user_to_edit, roles=['user', 'admin'])

@main_bp.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash("Bạn không thể tự xóa tài khoản của mình.", "error")
        return redirect(url_for('main.manage_users'))
    success, status = user_service.delete_user(user_id)
    if success:
        flash(f"Người dùng ID: {user_id} đã được xóa thành công.", "success")
    else:
        flash(f"Lỗi khi xóa người dùng: {status}", "error")
    return redirect(url_for('main.manage_users'))

@main_bp.route('/admin/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        data = request.form.to_dict()
        new_user, status = user_service.create_user(data)
        if status == "success":
            flash(f"Người dùng '{new_user.username or new_user.telegram_id}' đã được thêm thành công.", "success")
            return redirect(url_for('main.manage_users'))
        else:
            flash(f"Lỗi khi thêm người dùng: {status}", "error")
            return render_template('admin/add_user.html', user_data=data, roles=['user', 'admin'])
    
    default_user_data = {
        'username': '', 'telegram_id': '', 'password': '', 'user_role': 'user',
        'daily_new_limit': 10, 'timezone_offset': 7
    }
    return render_template('admin/add_user.html', user_data=default_user_data, roles=['user', 'admin'])
