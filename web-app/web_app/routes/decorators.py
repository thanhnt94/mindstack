# web_app/routes/decorators.py
from functools import wraps
from flask import session, flash, redirect, url_for
from ..models import User

def login_required(f):
    """
    Mô tả: Decorator để kiểm tra xem người dùng đã đăng nhập hay chưa.
    Nếu chưa, chuyển hướng về trang đăng nhập.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Vui lòng đăng nhập để truy cập trang này.", "info")
            return redirect(url_for('auth.login')) # Đã cập nhật url_for
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """
    Mô tả: Decorator để kiểm tra xem người dùng có vai trò 'admin' hay không.
    """
    @wraps(f)
    @login_required # Tự động kiểm tra đăng nhập trước
    def decorated_function(*args, **kwargs):
        user = User.query.get(session.get('user_id'))
        if not user or user.user_role != 'admin':
            flash("Bạn không có quyền truy cập trang quản trị.", "error")
            return redirect(url_for('flashcard.index')) # Đã cập nhật url_for
        return f(*args, **kwargs)
    return decorated_function
