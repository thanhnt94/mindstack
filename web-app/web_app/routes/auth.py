# web_app/routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from ..services import user_service
import logging

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Mô tả: Xử lý logic đăng nhập cho người dùng.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # --- BẮT ĐẦU SỬA LỖI: Gọi đúng hàm xác thực ---
        user, error = user_service.authenticate_user(username, password)
        # --- KẾT THÚC SỬA LỖI ---

        if user:
            session['user_id'] = user.user_id
            session['username'] = user.username
            session['user_role'] = user.user_role
            logger.info(f"Người dùng '{username}' (ID: {user.user_id}) đã đăng nhập thành công.")
            
            # Chuyển hướng dựa trên vai trò
            if user.user_role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('flashcard.index'))
        else:
            flash(error, 'error')
            logger.warning(f"Đăng nhập thất bại cho người dùng '{username}': {error}")

    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    """
    Mô tả: Xử lý logic đăng xuất, xóa thông tin phiên làm việc.
    """
    user_id = session.get('user_id')
    if user_id:
        logger.info(f"Người dùng ID: {user_id} đang đăng xuất.")
        session.clear()
        flash('Bạn đã đăng xuất thành công.', 'success')
    return redirect(url_for('auth.login'))
