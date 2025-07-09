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
from .config import LEARNING_MODE_DISPLAY_NAMES, IMAGES_DIR

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

# --- Helper function to serialize Flashcard object to dictionary ---
def _serialize_flashcard(flashcard_obj):
    """
    Mô tả: Chuyển đổi một đối tượng Flashcard SQLAlchemy thành một dictionary
           có thể được JSON serialize.
           Đã cập nhật để tạo URL đầy đủ cho hình ảnh.
    Args:
        flashcard_obj (Flashcard): Đối tượng Flashcard cần chuyển đổi.
    Returns:
        dict: Dictionary chứa các thuộc tính cần thiết của Flashcard.
    """
    if not flashcard_obj:
        return {}
    
    front_img_url = None
    if flashcard_obj.front_img:
        front_img_url = url_for('main.serve_image', filename=flashcard_obj.front_img)

    back_img_url = None
    if flashcard_obj.back_img:
        back_img_url = url_for('main.serve_image', filename=flashcard_obj.back_img)

    return {
        'flashcard_id': flashcard_obj.flashcard_id,
        'front': flashcard_obj.front,
        'back': flashcard_obj.back,
        'front_audio_content': flashcard_obj.front_audio_content,
        'back_audio_content': flashcard_obj.back_audio_content,
        'front_img': front_img_url,
        'back_img': back_img_url,
        'notification_text': flashcard_obj.notification_text,
        'set_id': flashcard_obj.set_id
    }

# --- Decorator to check login ---
def login_required(f):
    """
    Mô tả: Decorator để kiểm tra xem người dùng đã đăng nhập hay chưa.
           Nếu chưa, chuyển hướng về trang đăng nhập.
    Args:
        f (function): Hàm route cần bảo vệ.
    Returns:
        function: Hàm đã được bọc với logic kiểm tra đăng nhập.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Vui lòng đăng nhập để truy cập trang này.", "info")
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator mới để kiểm tra quyền admin
def admin_required(f):
    """
    Mô tả: Decorator để kiểm tra xem người dùng có vai trò 'admin' hay không.
           Nếu không phải admin, chuyển hướng về trang chủ và hiển thị thông báo lỗi.
    Args:
        f (function): Hàm route cần bảo vệ.
    Returns:
        function: Hàm đã được bọc với logic kiểm tra quyền admin.
    """
    @wraps(f)
    @login_required # Đảm bảo người dùng đã đăng nhập trước khi kiểm tra quyền admin
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash("Bạn cần đăng nhập để truy cập trang này.", "info")
            return redirect(url_for('main.login'))

        user = User.query.get(user_id)
        if not user or user.user_role != 'admin':
            flash("Bạn không có quyền truy cập trang quản trị.", "error")
            logger.warning(f"Người dùng {user_id} (vai trò: {user.user_role if user else 'N/A'}) đã cố gắng truy cập trang admin.")
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Mô tả: Xử lý logic đăng nhập người dùng.
    """
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        logger.info(f"Đang cố gắng đăng nhập với username: {username}")

        user, status = user_service.authenticate_user(username, password)

        if status == "success":
            session['user_id'] = user.user_id
            session['username'] = user.username
            session['user_role'] = user.user_role
            flash(f"Chào mừng, {user.username or user.telegram_id}! Bạn đã đăng nhập thành công.", "success")
            logger.info(f"Người dùng {user.username or user.telegram_id} (ID: {user.user_id}) đã đăng nhập thành công.")
            return redirect(url_for('main.index'))
        elif status == "user_not_found":
            flash("Tên đăng nhập không tồn tại.", "error")
            logger.warning(f"Đăng nhập thất bại: Username '{username}' không tồn tại.")
            return render_template('auth/login.html')
        elif status == "incorrect_password":
            flash("Mật khẩu không đúng.", "error")
            logger.warning(f"Đăng nhập thất bại: Mật khẩu sai cho username '{username}'.")
            return render_template('auth/login.html')
        else:
            flash("Đã có lỗi xảy ra trong quá trình đăng nhập. Vui lòng thử lại.", "error")
            logger.error(f"Đăng nhập thất bại với trạng thái không xác định: {status} cho username '{username}'.")
            return render_template('auth/login.html')
    
    return render_template('auth/login.html')

@main_bp.route('/logout')
def logout():
    """
    Mô tả: Xử lý logic đăng xuất người dùng.
    """
    logger.info(f"Người dùng {session.get('username', 'N/A')} (ID: {session.get('user_id', 'N/A')}) đã đăng xuất.")
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('user_role', None)
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for('main.login'))


@main_bp.route('/')
@login_required
def index():
    """
    Mô tả: Hiển thị trang chọn bộ thẻ cho người dùng.
           Liệt kê tất cả các bộ thẻ, ưu tiên các bộ đang học, sau đó là các bộ đã có tiến trình (đang dở),
           cuối cùng là các bộ chưa học.
    """
    logger.info("Truy cập trang chủ (index route).")
    
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        flash("Người dùng không tồn tại. Vui lòng đăng nhập lại.", "error")
        session.pop('user_id', None)
        return redirect(url_for('main.login'))

    all_sets = VocabularySet.query.order_by(VocabularySet.title).all()
    
    # Lấy ID của các bộ thẻ mà người dùng đã có tiến trình (ít nhất 1 flashcard có progress)
    # Sử dụng subquery để tìm các set_id có flashcard_id trong UserFlashcardProgress của user
    progressed_set_ids = db.session.query(Flashcard.set_id).\
        join(UserFlashcardProgress).\
        filter(UserFlashcardProgress.user_id == user.user_id).\
        distinct().\
        all()
    progressed_set_ids = {s.set_id for s in progressed_set_ids}

    # Các danh sách để phân loại bộ thẻ
    current_learning_set = None
    in_progress_sets = []
    not_started_sets = []

    for s in all_sets:
        if user.current_set_id == s.set_id:
            current_learning_set = s
        elif s.set_id in progressed_set_ids:
            in_progress_sets.append(s)
        else:
            not_started_sets.append(s)
    
    # Sắp xếp các danh sách con theo tiêu đề
    in_progress_sets.sort(key=lambda s: s.title)
    not_started_sets.sort(key=lambda s: s.title)

    # Xây dựng danh sách cuối cùng để truyền vào template
    # Đảm bảo bộ đang học luôn đứng đầu
    final_sets_list = []
    if current_learning_set:
        final_sets_list.append({'set': current_learning_set, 'status': 'current'})
        # Loại bỏ bộ đang học khỏi danh sách in_progress_sets nếu nó cũng nằm trong đó
        in_progress_sets = [s for s in in_progress_sets if s.set_id != current_learning_set.set_id]
    
    # Thêm các bộ đang dở
    for s in in_progress_sets:
        final_sets_list.append({'set': s, 'status': 'in_progress'})
    
    # Thêm các bộ chưa học
    for s in not_started_sets:
        final_sets_list.append({'set': s, 'status': 'not_started'})

    # Truyền danh sách đã phân loại và trạng thái vào template
    return render_template('flashcard/select_set.html', user=user, sets_data=final_sets_list)

@main_bp.route('/learn/<int:set_id>')
@login_required
def learn_set(set_id):
    """
    Mô tả: Bắt đầu phiên học cho một bộ thẻ cụ thể, hiển thị mặt trước thẻ.
    """
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

    flashcard_obj, progress_obj, wait_time_ts = learning_logic_service.get_next_card_for_review(
        user_id=user.user_id,
        set_id=set_id,
        mode=user.current_mode
    )

    context_stats = stats_service.get_user_stats_for_context(user.user_id, set_id)

    user_audio_settings = {
        'front_audio_enabled': user.front_audio == 1,
        'back_audio_enabled': user.back_audio == 1
    }

    if flashcard_obj is None:
        session.pop('current_progress_id', None)
        session.pop('current_flashcard_id', None)
        session.pop('current_set_id', None)
        session.pop('learning_mode', None)

        wait_minutes = 0
        is_midnight_tomorrow = False

        if wait_time_ts:
            wait_dt = datetime.fromtimestamp(wait_time_ts)
            now_ts = int(time.time())
            wait_minutes = max(1, int((wait_time_ts - now_ts + 59) / 60)) if wait_time_ts > now_ts else 0

            user_tz_offset_hours = user.timezone_offset
            user_tz = timedelta(hours=user_tz_offset_hours)
            now_local = datetime.now(timezone.utc).astimezone(timezone(user_tz))
            midnight_next_day_dt = datetime.combine((now_local + timedelta(days=1)).date(), datetime.min.time(), tzinfo=now_local.tzinfo)
            
            if abs(wait_dt.replace(tzinfo=None) - midnight_next_day_dt.replace(tzinfo=None)) < timedelta(minutes=1):
                is_midnight_tomorrow = True
        
        return render_template(
            'flashcard/no_cards_message.html',
            wait_time_ts=wait_time_ts,
            wait_minutes=wait_minutes,
            is_midnight_tomorrow=is_midnight_tomorrow,
            set_id=set_id
        )

    flashcard_json_string = json.dumps(_serialize_flashcard(flashcard_obj)) if flashcard_obj else "null"
    user_audio_settings_json_string = json.dumps(user_audio_settings)

    session['current_progress_id'] = progress_obj.progress_id
    session['current_flashcard_id'] = flashcard_obj.flashcard_id
    session['current_set_id'] = set_id
    session['learning_mode'] = user.current_mode

    return render_template(
        'flashcard/learn_card.html',
        user=user,
        flashcard=flashcard_obj,
        progress=progress_obj,
        context_stats=context_stats,
        is_front=True,
        wait_time_ts=None,
        user_audio_settings=user_audio_settings,
        flashcard_json_string=flashcard_json_string,
        user_audio_settings_json_string=user_audio_settings_json_string
    )


@main_bp.route('/flip/<int:progress_id>')
@login_required
def flip_card(progress_id):
    """
    Mô tả: Lật thẻ để hiển thị mặt sau.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash("Vui lòng đăng nhập lại.", "error")
        return redirect(url_for('main.login'))

    progress = UserFlashcardProgress.query.get(progress_id)
    if not progress or progress.user_id != user_id:
        flash("Thẻ không hợp lệ hoặc không thuộc về bạn.", "error")
        return redirect(url_for('main.index'))
    
    user = User.query.get(user_id)
    context_stats = stats_service.get_user_stats_for_context(user_id, progress.flashcard.set_id)

    user_audio_settings = {
        'front_audio_enabled': user.front_audio == 1,
        'back_audio_enabled': user.back_audio == 1
    }

    flashcard_json_string = json.dumps(_serialize_flashcard(progress.flashcard))
    user_audio_settings_json_string = json.dumps(user_audio_settings)

    return render_template(
        'flashcard/learn_card.html',
        user=user,
        flashcard=progress.flashcard,
        progress=progress,
        context_stats=context_stats,
        is_front=False,
        user_audio_settings=user_audio_settings,
        flashcard_json_string=flashcard_json_string,
        user_audio_settings_json_string=user_audio_settings_json_string
    )

@main_bp.route('/rate/<int:progress_id>/<string:response_str>')
@login_required
def rate_card(progress_id, response_str):
    """
    Mô tả: Xử lý đánh giá của người dùng cho một thẻ và chuyển sang thẻ tiếp theo.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash("Vui lòng đăng nhập lại.", "error")
        return redirect(url_for('main.login'))

    response_mapping = {
        'forget': -1,
        'vague': 0,
        'remember': 1,
        'continue': 2
    }
    response = response_mapping.get(response_str)

    if response is None:
        flash("Phản hồi không hợp lệ.", "error")
        return redirect(url_for('main.index'))

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
    """
    Mô tả: Hiển thị trang chọn chế độ học tập.
    """
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        flash("Người dùng không tồn tại. Vui lòng đăng nhập lại.", "error")
        session.pop('user_id', None)
        return redirect(url_for('main.login'))
    
    return render_template(
        'flashcard/select_mode.html',
        modes=LEARNING_MODE_DISPLAY_NAMES,
        current_mode=user.current_mode
    )

@main_bp.route('/set_learning_mode/<string:mode_code>')
@login_required
def set_learning_mode(mode_code):
    """
    Mô tả: Đặt chế độ học tập mới cho người dùng.
    """
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
        flash("Phiên học đã kết thúc hoặc không xác định được bộ thẻ.", "info")
        return redirect(url_for('main.index'))


@main_bp.route('/select_set_page')
@login_required
def select_set_page():
    """
    Mô tả: Chuyển hướng về trang chọn bộ thẻ.
    """
    return redirect(url_for('main.index'))

@main_bp.route('/api/card_audio/<int:flashcard_id>/<string:side>')
@login_required
def get_card_audio(flashcard_id, side):
    """
    Mô tả: API endpoint để lấy và phục vụ file audio cho mặt trước hoặc mặt sau của thẻ.
    """
    user_id = session.get('user_id')
    if not user_id:
        return {"error": "Unauthorized"}, 401

    if side not in ['front', 'back']:
        return {"error": "Invalid side specified"}, 400

    flashcard = Flashcard.query.get(flashcard_id)
    if not flashcard:
        logger.warning(f"API Audio: Không tìm thấy Flashcard ID {flashcard_id}")
        return {"error": "Flashcard not found"}, 404

    audio_content = None
    if side == 'front':
        audio_content = flashcard.front_audio_content
    else: # side == 'back'
        audio_content = flashcard.back_audio_content

    if not audio_content:
        logger.info(f"API Audio: Flashcard ID {flashcard_id}, side '{side}' không có nội dung audio.")
        return {"error": "No audio content for this side"}, 404

    try:
        audio_file_path = asyncio.run(audio_service.get_cached_or_generate_audio(audio_content))

        if audio_file_path and os.path.exists(audio_file_path):
            logger.info(f"API Audio: Phục vụ file audio từ: {audio_file_path}")
            return send_file(audio_file_path, mimetype="audio/mpeg")
        else:
            logger.error(f"API Audio: Không thể tạo hoặc tìm thấy file audio cho Flashcard ID {flashcard_id}, side '{side}'.")
            return {"error": "Failed to generate or retrieve audio file"}, 500
    except Exception as e:
        logger.error(f"API Audio: Lỗi không mong muốn khi phục vụ audio cho Flashcard ID {flashcard_id}, side '{side}': {e}", exc_info=True)
        return {"error": "Internal server error"}, 500

@main_bp.route('/images/<path:filename>')
def serve_image(filename):
    """
    Mô tả: Phục vụ các tệp hình ảnh từ thư mục IMAGES_DIR.
           Route này cho phép trình duyệt truy cập các hình ảnh được lưu trữ
           ngoài thư mục 'static' mặc định của Flask.
    Args:
        filename (str): Tên tệp hình ảnh (bao gồm cả đường dẫn con nếu có).
    Returns:
        Response: Tệp hình ảnh được gửi về trình duyệt.
    """
    try:
        full_path = os.path.join(IMAGES_DIR, filename)
        
        if not os.path.exists(full_path):
            logger.warning(f"File ảnh không tìm thấy: {full_path}")
            return "Image not found", 404
            
        logger.info(f"Đang phục vụ file ảnh: {full_path}")
        return send_file(full_path, mimetype='image/jpeg')
    except Exception as e:
        logger.error(f"Lỗi khi phục vụ ảnh '{filename}': {e}", exc_info=True)
        return "Internal server error", 500

# Route quản lý người dùng cho Admin
@main_bp.route('/admin/users')
@admin_required
def manage_users():
    """
    Mô tả: Hiển thị trang quản lý người dùng cho quản trị viên.
           Liệt kê tất cả người dùng trong hệ thống.
    """
    logger.info("Admin truy cập trang quản lý người dùng.")
    users = User.query.all()
    
    return render_template('admin/manage_users.html', users=users)

# Route để chỉnh sửa thông tin người dùng
@main_bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """
    Mô tả: Hiển thị form chỉnh sửa thông tin người dùng và xử lý việc cập nhật.
    Args:
        user_id (int): ID của người dùng cần chỉnh sửa.
    """
    user_to_edit = User.query.get(user_id)
    if not user_to_edit:
        flash("Người dùng không tồn tại.", "error")
        return redirect(url_for('main.manage_users'))

    if request.method == 'POST':
        data = {
            'username': request.form.get('username'),
            'telegram_id': request.form.get('telegram_id', '').strip(), 
            'user_role': request.form.get('user_role'),
            'daily_new_limit': request.form.get('daily_new_limit'),
            'timezone_offset': request.form.get('timezone_offset'),
            'password': request.form.get('password')
        }

        updated_user, status = user_service.update_user_profile(user_id, data)

        if status == "success":
            flash(f"Cập nhật thông tin người dùng '{updated_user.username or updated_user.telegram_id}' thành công.", "success")
            logger.info(f"Admin đã cập nhật thành công thông tin người dùng ID: {user_id}.")
            return redirect(url_for('main.manage_users'))
        elif status == "user_not_found":
            flash("Người dùng không tồn tại.", "error")
            logger.warning(f"Admin cố gắng cập nhật người dùng ID: {user_id} nhưng không tìm thấy.")
        elif status == "username_exists":
            flash("Tên đăng nhập này đã tồn tại. Vui lòng chọn tên khác.", "error")
            logger.warning(f"Admin cố gắng cập nhật người dùng ID: {user_id} với username đã tồn tại.")
        elif status == "telegram_id_exists":
            flash("Telegram ID này đã tồn tại cho người dùng khác. Vui lòng nhập ID khác.", "error")
            logger.warning(f"Admin cố gắng cập nhật người dùng ID: {user_id} với Telegram ID đã tồn tại.")
        elif status == "invalid_data":
            flash("Dữ liệu nhập vào không hợp lệ. Vui lòng kiểm tra lại.", "error")
            logger.warning(f"Admin cố gắng cập nhật người dùng ID: {user_id} với dữ liệu không hợp lệ.")
        else:
            flash("Đã có lỗi xảy ra khi cập nhật thông tin người dùng. Vui lòng thử lại.", "error")
            logger.error(f"Lỗi không xác định khi cập nhật người dùng ID: {user_id}. Trạng thái: {status}")
        
        return render_template('admin/edit_user.html', user=user_to_edit, roles=['user', 'admin'])

    logger.info(f"Admin truy cập trang chỉnh sửa người dùng ID: {user_id}.")
    roles = ['user', 'admin'] 
    return render_template('admin/edit_user.html', user=user_to_edit, roles=roles)

# Route để xóa người dùng
@main_bp.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    """
    Mô tả: Xử lý yêu cầu xóa người dùng.
           Chỉ chấp nhận phương thức POST để tránh việc xóa nhầm qua GET request.
    Args:
        user_id (int): ID của người dùng cần xóa.
    """
    # Ngăn không cho admin tự xóa tài khoản của mình
    if user_id == session.get('user_id'):
        flash("Bạn không thể tự xóa tài khoản của mình.", "error")
        logger.warning(f"Admin ID: {session.get('user_id')} cố gắng tự xóa tài khoản.")
        return redirect(url_for('main.manage_users'))

    success, status = user_service.delete_user(user_id)

    if success:
        flash(f"Người dùng ID: {user_id} đã được xóa thành công.", "success")
        logger.info(f"Admin đã xóa thành công người dùng ID: {user_id}.")
    elif status == "user_not_found":
        flash("Người dùng không tồn tại.", "error")
        logger.warning(f"Admin cố gắng xóa người dùng ID: {user_id} nhưng không tìm thấy.")
    else:
        flash("Đã có lỗi xảy ra khi xóa người dùng. Vui lòng thử lại.", "error")
        logger.error(f"Lỗi không xác định khi xóa người dùng ID: {user_id}. Trạng thái: {status}")
    
    return redirect(url_for('main.manage_users'))

# Route để thêm người dùng mới
@main_bp.route('/admin/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """
    Mô tả: Hiển thị form thêm người dùng mới và xử lý việc tạo người dùng.
    """
    roles = ['user', 'admin'] # Các vai trò có thể chọn

    if request.method == 'POST':
        data = {
            'username': request.form.get('username'),
            'telegram_id': request.form.get('telegram_id', '').strip(),
            'password': request.form.get('password'),
            'user_role': request.form.get('user_role'),
            'daily_new_limit': request.form.get('daily_new_limit'),
            'timezone_offset': request.form.get('timezone_offset')
        }

        new_user, status = user_service.create_user(data)

        if status == "success":
            flash(f"Người dùng '{new_user.username or new_user.telegram_id}' đã được thêm thành công.", "success")
            logger.info(f"Admin đã thêm người dùng mới: {new_user.username or new_user.telegram_id} (ID: {new_user.user_id}).")
            return redirect(url_for('main.manage_users'))
        elif status == "username_exists":
            flash("Tên đăng nhập này đã tồn tại. Vui lòng chọn tên khác.", "error")
            logger.warning(f"Admin cố gắng thêm người dùng với username đã tồn tại: {data.get('username')}.")
        elif status == "telegram_id_exists":
            flash("Telegram ID này đã tồn tại. Vui lòng nhập ID khác.", "error")
            logger.warning(f"Admin cố gắng thêm người dùng với Telegram ID đã tồn tại: {data.get('telegram_id')}.")
        elif status == "missing_required_fields":
            flash("Vui lòng điền đầy đủ các trường bắt buộc (Mật khẩu).", "error")
            logger.warning(f"Admin cố gắng thêm người dùng nhưng thiếu trường bắt buộc.")
        elif status == "invalid_data":
            flash("Dữ liệu nhập vào không hợp lệ. Vui lòng kiểm tra lại.", "error")
            logger.warning(f"Admin cố gắng thêm người dùng với dữ liệu không hợp lệ.")
        else:
            flash("Đã có lỗi xảy ra khi thêm người dùng. Vui lòng thử lại.", "error")
            logger.error(f"Lỗi không xác định khi thêm người dùng. Trạng thái: {status}")
        
        return render_template('admin/add_user.html', user_data=data, roles=roles)

    logger.info("Admin truy cập trang thêm người dùng mới.")
    default_user_data = {
        'username': '',
        'telegram_id': '',
        'password': '',
        'user_role': 'user',
        'daily_new_limit': 10,
        'timezone_offset': 7
    }
    return render_template('admin/add_user.html', user_data=default_user_data, roles=roles)
