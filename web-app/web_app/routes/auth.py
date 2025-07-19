# web_app/routes/auth.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, request
import logging
from ..services import user_service
from ..models import User

# Tạo một Blueprint mới cho các route xác thực
auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
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
            
            # BẮT ĐẦU THAY ĐỔI: Chuyển hướng về URL gốc nếu có tham số 'next'
            # Nếu người dùng cố gắng truy cập một trang được bảo vệ, Flask sẽ lưu URL đó vào 'next'
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            else:
                # Nếu không có 'next' (ví dụ: đăng nhập trực tiếp từ trang /login),
                # chuyển hướng về trang chủ giới thiệu (/home)
                return redirect(url_for('main.home'))
            # KẾT THÚC THAY ĐỔI
        else:
            flash("Tên đăng nhập hoặc mật khẩu không đúng.", "error")
            logger.warning(f"Đăng nhập thất bại cho username '{username}'.")
            return render_template('auth/login.html')
    
    # Nếu là GET request hoặc đăng nhập thất bại, hiển thị lại trang login
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    """
    Mô tả: Xử lý logic đăng xuất người dùng.
    """
    logger.info(f"Người dùng {session.get('username', 'N/A')} (ID: {session.get('user_id', 'N/A')}) đã đăng xuất.")
    session.clear() # Xóa tất cả dữ liệu trong session
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for('auth.login'))
