# web_app/routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from ..services import user_service
import logging
# BẮT ĐẦU THAY ĐỔI: Import time và db
import time
from ..models import db
# KẾT THÚC THAY ĐỔI

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
        
        user, error = user_service.authenticate_user(username, password)

        if user:
            session['user_id'] = user.user_id
            session['username'] = user.username
            session['user_role'] = user.user_role
            logger.info(f"Người dùng '{username}' (ID: {user.user_id}) đã đăng nhập thành công.")
            
            # BẮT ĐẦU THAY ĐỔI: Cập nhật last_seen khi đăng nhập
            try:
                user.last_seen = int(time.time())
                db.session.commit()
                logger.info(f"Đã cập nhật last_seen cho người dùng ID: {user.user_id}")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Lỗi khi cập nhật last_seen cho người dùng ID {user.user_id}: {e}", exc_info=True)
            # KẾT THÚC THAY ĐỔI
            
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
