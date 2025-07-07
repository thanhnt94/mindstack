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
from .config import LEARNING_MODE_DISPLAY_NAMES, IMAGES_DIR # ĐÃ THÊM IMAGES_DIR TỪ CONFIG

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
    
    # BẮT ĐẦU THAY ĐỔI: Xử lý đường dẫn hình ảnh
    front_img_url = None
    if flashcard_obj.front_img:
        # Tạo URL cho hình ảnh bằng route mới 'serve_image'
        # url_for sẽ tạo ra /images/<filename>
        front_img_url = url_for('main.serve_image', filename=flashcard_obj.front_img)

    back_img_url = None
    if flashcard_obj.back_img:
        # Tạo URL cho hình ảnh bằng route mới 'serve_image'
        back_img_url = url_for('main.serve_image', filename=flashcard_obj.back_img)
    # KẾT THÚC THAY ĐỔI

    return {
        'flashcard_id': flashcard_obj.flashcard_id,
        'front': flashcard_obj.front,
        'back': flashcard_obj.back,
        'front_audio_content': flashcard_obj.front_audio_content,
        'back_audio_content': flashcard_obj.back_audio_content,
        'front_img': front_img_url, # ĐÃ THAY ĐỔI: Sử dụng URL đã xử lý
        'back_img': back_img_url,   # ĐÃ THAY ĐỔI: Sử dụng URL đã xử lý
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

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Mô tả: Xử lý logic đăng nhập người dùng.
    """
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
    """
    Mô tả: Xử lý logic đăng xuất người dùng.
    """
    logger.info(f"Người dùng {session.get('username', 'N/A')} (ID: {session.get('user_id', 'N/A')}) đã đăng xuất.")
    session.pop('user_id', None)
    session.pop('username', None)
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for('main.login'))


@main_bp.route('/')
@login_required
def index():
    """
    Mô tả: Hiển thị trang chọn bộ thẻ cho người dùng.
    """
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

    # Use learning_logic_service for getting the next card
    flashcard_obj, progress_obj, wait_time_ts = learning_logic_service.get_next_card_for_review(
        user_id=user.user_id,
        set_id=set_id,
        mode=user.current_mode
    )

    # Use stats_service for getting context stats
    context_stats = stats_service.get_user_stats_for_context(user.user_id, set_id)

    # Lấy cài đặt audio của người dùng
    user_audio_settings = {
        'front_audio_enabled': user.front_audio == 1,
        'back_audio_enabled': user.back_audio == 1
    }

    # Nếu không có thẻ để học ngay lập tức, render template thông báo
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
        
        # Render template thông báo mới
        return render_template(
            'no_cards_message.html',
            wait_time_ts=wait_time_ts,
            wait_minutes=wait_minutes,
            is_midnight_tomorrow=is_midnight_tomorrow,
            set_id=set_id # Truyền set_id để nút "Tiếp tục (thử lại)" hoạt động
        )

    # Nếu có thẻ để học, tiếp tục render learn_card.html
    flashcard_json_string = json.dumps(_serialize_flashcard(flashcard_obj)) if flashcard_obj else "null"
    user_audio_settings_json_string = json.dumps(user_audio_settings)

    session['current_progress_id'] = progress_obj.progress_id
    session['current_flashcard_id'] = flashcard_obj.flashcard_id
    session['current_set_id'] = set_id
    session['learning_mode'] = user.current_mode

    return render_template(
        'learn_card.html',
        user=user,
        flashcard=flashcard_obj, # Vẫn truyền đối tượng Flashcard cho Jinja2 để hiển thị
        progress=progress_obj,
        context_stats=context_stats,
        is_front=True,
        wait_time_ts=None, # Không có wait_time_ts khi hiển thị thẻ
        user_audio_settings=user_audio_settings, # Vẫn truyền đối tượng dict cho Jinja2 để hiển thị
        # TRUYỀN CÁC CHUỖI JSON ĐÃ ĐƯỢC CHUYỂN ĐỔI CHO JAVASCRIPT
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
    # Use stats_service for getting context stats
    context_stats = stats_service.get_user_stats_for_context(user_id, progress.flashcard.set_id)

    # Lấy cài đặt audio của người dùng
    user_audio_settings = {
        'front_audio_enabled': user.front_audio == 1,
        'back_audio_enabled': user.back_audio == 1
    }

    # Chuyển đổi progress.flashcard và user_audio_settings thành JSON string TẠI ĐÂY
    flashcard_json_string = json.dumps(_serialize_flashcard(progress.flashcard))
    user_audio_settings_json_string = json.dumps(user_audio_settings)

    return render_template(
        'learn_card.html',
        user=user,
        flashcard=progress.flashcard, # Vẫn truyền đối tượng Flashcard cho Jinja2 để hiển thị
        progress=progress,
        context_stats=context_stats,
        is_front=False,
        user_audio_settings=user_audio_settings, # Vẫn truyền đối tượng dict cho Jinja2 để hiển thị
        # TRUYỀN CÁC CHUỖI JSON ĐÃ ĐƯỢC CHUYỂN ĐỔI CHO JAVASCRIPT
        flashcard_json_string=flashcard_json_string,
        user_audio_settings_json_string=user_audio_settings_json_string
    )

@main_bp.route('/rate/<int:progress_id>/<string:response_str>') # THAY ĐỔI TỪ <int:response> SANG <string:response_str>
@login_required
def rate_card(progress_id, response_str):
    """
    Mô tả: Xử lý đánh giá của người dùng cho một thẻ và chuyển sang thẻ tiếp theo.
    """
    user_id = session.get('user_id')
    if not user_id:
        flash("Vui lòng đăng nhập lại.", "error")
        return redirect(url_for('main.login'))

    # BẮT ĐẦU THÊM: Chuyển đổi response_str thành giá trị số nguyên
    response_mapping = {
        'forget': -1,
        'vague': 0,
        'remember': 1,
        'continue': 2 # Thêm trường hợp 'continue' cho thẻ mới
    }
    response = response_mapping.get(response_str)

    if response is None:
        flash("Phản hồi không hợp lệ.", "error")
        return redirect(url_for('main.index'))
    # KẾT THÚC THÊM

    # Use learning_logic_service for processing review response
    flashcard_info_updated, next_card_due_time_ts = learning_logic_service.process_review_response(
        user_id=user_id,
        progress_id=progress_id,
        response=response
    )

    if not flashcard_info_updated:
        flash("Lỗi khi xử lý đánh giá thẻ.", "error")
        return redirect(url_for('main.index'))
    
    # BẮT ĐẦU CHỈNH SỬA: XÓA DÒNG FLASH NÀY ĐỂ KHÔNG HIỂN THỊ THÔNG BÁO
    # response_display_text = ""
    # if response == -1:
    #     response_display_text = "Quên"
    # elif response == 0:
    #     response_display_text = "Mơ hồ"
    # elif response == 1:
    #     response_display_text = "Nhớ"
    # elif response == 2: # Trường hợp "Tiếp tục" cho thẻ mới
    #     response_display_text = "Tiếp tục"
    
    # if response_display_text:
    #     flash(f"Bạn đã đánh giá thẻ là '{response_display_text}'.", "success")
    # KẾT THÚC CHỈNH SỬA

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
        'select_mode.html',
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

    # Lấy thông tin thẻ từ database
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
        # Chạy hàm async bằng asyncio.run()
        # Lưu ý: asyncio.run() sẽ tạo một event loop mới và chạy coroutine.
        # Điều này có thể không tối ưu cho môi trường production với Flask WSGI,
        # nhưng là giải pháp đơn giản nhất cho môi trường phát triển.
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
        # Đảm bảo đường dẫn file là an toàn và nằm trong thư mục IMAGES_DIR
        # os.path.join sẽ nối IMAGES_DIR với filename
        # send_file sẽ kiểm tra tính an toàn của đường dẫn
        full_path = os.path.join(IMAGES_DIR, filename)
        
        # Kiểm tra xem file có tồn tại không
        if not os.path.exists(full_path):
            logger.warning(f"File ảnh không tìm thấy: {full_path}")
            # Có thể trả về một hình ảnh placeholder hoặc lỗi 404
            return "Image not found", 404
            
        logger.info(f"Đang phục vụ file ảnh: {full_path}")
        return send_file(full_path, mimetype='image/jpeg') # Có thể cần điều chỉnh mimetype tùy loại ảnh (png, jpg, webp...)
    except Exception as e:
        logger.error(f"Lỗi khi phục vụ ảnh '{filename}': {e}", exc_info=True)
        return "Internal server error", 500

