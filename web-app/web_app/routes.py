# flashcard-web/web_app/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, request
import logging
import time # For timestamp
from datetime import datetime, timedelta, timezone # For consistent datetime handling
from functools import wraps # For decorator

# Import individual services from the new structure
from .services import learning_logic_service, user_service, stats_service
from .models import db, User, VocabularySet, Flashcard, UserFlashcardProgress # Still need models for queries
from .config import LEARNING_MODE_DISPLAY_NAMES # Still need config for display names

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

# --- Decorator to check login ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Vui lòng đăng nhập để truy cập trang này.", "info")
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        logger.info(f"Đang cố gắng đăng nhập với username: {username}")

        # Use user_service for authentication
        user, status = user_service.authenticate_user(username, password)

        if status == "success":
            session['user_id'] = user.user_id
            session['username'] = user.username # Save username to session for display
            flash(f"Chào mừng, {user.username or user.telegram_id}! Bạn đã đăng nhập thành công.", "success")
            logger.info(f"Người dùng {user.username or user.telegram_id} (ID: {user.user_id}) đã đăng nhập thành công.")
            return redirect(url_for('main.index'))
        elif status == "user_not_found":
            flash("Tên đăng nhập không tồn tại.", "error")
            logger.warning(f"Đăng nhập thất bại: Username '{username}' không tồn tại.")
            return render_template('login.html')
        elif status == "incorrect_password":
            flash("Mật khẩu không đúng.", "error")
            logger.warning(f"Đăng nhập thất bại: Mật khẩu sai cho username '{username}'.")
            return render_template('login.html')
        else:
            flash("Đã có lỗi xảy ra trong quá trình đăng nhập. Vui lòng thử lại.", "error")
            logger.error(f"Đăng nhập thất bại với trạng thái không xác định: {status} cho username '{username}'.")
            return render_template('login.html')
    
    return render_template('login.html')

@main_bp.route('/logout')
def logout():
    logger.info(f"Người dùng {session.get('username', 'N/A')} (ID: {session.get('user_id', 'N/A')}) đã đăng xuất.")
    session.pop('user_id', None)
    session.pop('username', None)
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for('main.login'))


@main_bp.route('/')
@login_required
def index():
    logger.info("Truy cập trang chủ (index route).")
    
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        flash("Người dùng không tồn tại. Vui lòng đăng nhập lại.", "error")
        session.pop('user_id', None)
        return redirect(url_for('main.login'))

    created_sets = VocabularySet.query.filter_by(creator_user_id=user.user_id).order_by(VocabularySet.title).all()

    progressed_set_ids = db.session.query(Flashcard.set_id).\
        join(UserFlashcardProgress).\
        filter(UserFlashcardProgress.user_id == user.user_id).\
        distinct().\
        all()
    progressed_set_ids = [s.set_id for s in progressed_set_ids]
    
    progressed_sets = VocabularySet.query.filter(VocabularySet.set_id.in_(progressed_set_ids)).order_by(VocabularySet.title).all()

    all_available_sets = {s.set_id: s for s in created_sets}
    for s in progressed_sets:
        all_available_sets[s.set_id] = s
    
    sorted_sets = sorted(all_available_sets.values(), key=lambda s: s.title)

    return render_template('select_set.html', user=user, sets=sorted_sets)

@main_bp.route('/learn/<int:set_id>')
@login_required
def learn_set(set_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        flash("Người dùng không tồn tại.", "error")
        return redirect(url_for('main.login'))

    selected_set = VocabularySet.query.get(set_id)
    if not selected_set:
        flash("Bộ thẻ không tồn tại.", "error")
        return redirect(url_for('main.index'))
    
    logger.info(f"User {user.username or user.telegram_id} (ID: {user.user_id}) bắt đầu học bộ {set_id} ({selected_set.title}).")

    user.current_set_id = set_id
    user.last_seen = int(time.time())
    db.session.commit()

    # Use learning_logic_service for getting the next card
    flashcard_obj, progress_obj, wait_time_ts = learning_logic_service.get_next_card_for_review(
        user_id=user.user_id,
        set_id=set_id,
        mode=user.current_mode
    )

    # Use stats_service for getting context stats
    context_stats = stats_service.get_user_stats_for_context(user.user_id, set_id)

    if flashcard_obj:
        session['current_progress_id'] = progress_obj.progress_id
        session['current_flashcard_id'] = flashcard_obj.flashcard_id
        session['current_set_id'] = set_id
        session['learning_mode'] = user.current_mode

        return render_template(
            'learn_card.html',
            user=user,
            flashcard=flashcard_obj,
            progress=progress_obj,
            context_stats=context_stats,
            is_front=True,
            wait_time_ts=None
        )
    elif wait_time_ts:
        session.pop('current_progress_id', None)
        session.pop('current_flashcard_id', None)
        session.pop('current_set_id', None)
        session.pop('learning_mode', None)

        wait_dt = datetime.fromtimestamp(wait_time_ts)
        now_ts = int(time.time())
        wait_minutes = max(1, int((wait_time_ts - now_ts + 59) / 60)) if wait_time_ts > now_ts else 0

        is_midnight_tomorrow = False
        user_tz_offset_hours = user.timezone_offset
        user_tz = timedelta(hours=user_tz_offset_hours)
        now_local = datetime.now(timezone.utc).astimezone(timezone(user_tz))
        midnight_next_day_dt = datetime.combine((now_local + timedelta(days=1)).date(), datetime.min.time(), tzinfo=now_local.tzinfo)
        
        if abs(wait_dt.replace(tzinfo=None) - midnight_next_day_dt.replace(tzinfo=None)) < timedelta(minutes=1):
            is_midnight_tomorrow = True

        return render_template(
            'learn_card.html',
            user=user,
            flashcard=None,
            progress=None,
            context_stats=context_stats,
            is_front=True,
            wait_time_ts=wait_time_ts,
            wait_minutes=wait_minutes,
            is_midnight_tomorrow=is_midnight_tomorrow
        )
    else:
        flash("Không tìm thấy thẻ nào để học trong bộ này.", "info")
        return redirect(url_for('main.index'))


@main_bp.route('/flip/<int:progress_id>')
@login_required
def flip_card(progress_id):
    user_id = session.get('user_id')
    if not user_id:
        flash("Vui lòng đăng nhập lại.", "error")
        return redirect(url_for('main.login'))

    progress = UserFlashcardProgress.query.get(progress_id)
    if not progress or progress.user_id != user_id:
        flash("Thẻ không hợp lệ hoặc không thuộc về bạn.", "error")
        return redirect(url_for('main.index'))
    
    user = User.query.get(user_id)
    # Use stats_service for getting context stats
    context_stats = stats_service.get_user_stats_for_context(user_id, progress.flashcard.set_id)

    return render_template(
        'learn_card.html',
        user=user,
        flashcard=progress.flashcard,
        progress=progress,
        context_stats=context_stats,
        is_front=False
    )

@main_bp.route('/rate/<int:progress_id>/<int:response>')
@login_required
def rate_card(progress_id, response):
    user_id = session.get('user_id')
    if not user_id:
        flash("Vui lòng đăng nhập lại.", "error")
        return redirect(url_for('main.login'))

    # Use learning_logic_service for processing review response
    flashcard_info_updated, next_card_due_time_ts = learning_logic_service.process_review_response(
        user_id=user_id,
        progress_id=progress_id,
        response=response
    )

    if not flashcard_info_updated:
        flash("Lỗi khi xử lý đánh giá thẻ.", "error")
        return redirect(url_for('main.index'))
    
    current_set_id = session.get('current_set_id')
    if current_set_id:
        return redirect(url_for('main.learn_set', set_id=current_set_id))
    else:
        flash("Phiên học đã kết thúc hoặc không xác định được bộ thẻ.", "info")
        return redirect(url_for('main.index'))

@main_bp.route('/select_mode')
@login_required
def select_mode():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        flash("Người dùng không tồn tại. Vui lòng đăng nhập lại.", "error")
        session.pop('user_id', None)
        return redirect(url_for('main.login'))
    
    return render_template(
        'select_mode.html',
        modes=LEARNING_MODE_DISPLAY_NAMES,
        current_mode=user.current_mode
    )

@main_bp.route('/set_learning_mode/<string:mode_code>')
@login_required
def set_learning_mode(mode_code):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        flash("Người dùng không tồn tại. Vui lòng đăng nhập lại.", "error")
        session.pop('user_id', None)
        return redirect(url_for('main.login'))
    
    if mode_code not in LEARNING_MODE_DISPLAY_NAMES:
        flash("Chế độ học không hợp lệ.", "error")
        return redirect(url_for('main.select_mode'))
    
    try:
        user.current_mode = mode_code
        db.session.commit()
        session['learning_mode'] = mode_code
        flash(f"Chế độ học đã được thay đổi thành '{LEARNING_MODE_DISPLAY_NAMES[mode_code]}'.", "success")
        logger.info(f"User {user.username} (ID: {user.user_id}) đã thay đổi chế độ học thành: {mode_code}")
    except Exception as e:
        db.session.rollback()
        flash("Lỗi khi cập nhật chế độ học. Vui lòng thử lại.", "error")
        logger.error(f"Lỗi khi cập nhật chế độ học cho user {user.user_id}: {e}", exc_info=True)
    
    current_set_id = session.get('current_set_id')
    if current_set_id:
        return redirect(url_for('main.learn_set', set_id=current_set_id))
    else:
        return redirect(url_for('main.index'))


@main_bp.route('/select_set_page')
@login_required
def select_set_page():
    return redirect(url_for('main.index'))

