# web_app/routes/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, request
import logging
from ..services import user_service
from ..models import db, User
from .decorators import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
logger = logging.getLogger(__name__)

@admin_bp.route('/users')
@admin_required
def manage_users():
    """
    Mô tả: Hiển thị trang quản lý người dùng cho quản trị viên.
    """
    users = User.query.all()
    return render_template('admin/manage_users.html', users=users)

@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """
    Mô tả: Hiển thị form chỉnh sửa thông tin người dùng và xử lý việc cập nhật.
    """
    user_to_edit = User.query.get_or_404(user_id)
    if request.method == 'POST':
        data = request.form.to_dict()
        updated_user, status = user_service.update_user_profile(user_id, data)
        if status == "success":
            flash(f"Cập nhật thông tin người dùng '{updated_user.username or updated_user.telegram_id}' thành công.", "success")
            return redirect(url_for('admin.manage_users'))
        else:
            flash(f"Lỗi khi cập nhật: {status}", "error")
    
    return render_template('admin/edit_user.html', user=user_to_edit, roles=['user', 'admin'])

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    """
    Mô tả: Xử lý yêu cầu xóa người dùng.
    """
    if user_id == session.get('user_id'):
        flash("Bạn không thể tự xóa tài khoản của mình.", "error")
        return redirect(url_for('admin.manage_users'))

    success, status = user_service.delete_user(user_id)
    if success:
        flash(f"Người dùng ID: {user_id} đã được xóa thành công.", "success")
    else:
        flash(f"Lỗi khi xóa người dùng: {status}", "error")
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """
    Mô tả: Hiển thị form thêm người dùng mới và xử lý việc tạo người dùng.
    """
    if request.method == 'POST':
        data = request.form.to_dict()
        new_user, status = user_service.create_user(data)
        if status == "success":
            flash(f"Người dùng '{new_user.username or new_user.telegram_id}' đã được thêm thành công.", "success")
            return redirect(url_for('admin.manage_users'))
        else:
            flash(f"Lỗi khi thêm người dùng: {status}", "error")
            return render_template('admin/add_user.html', user_data=data, roles=['user', 'admin'])
    
    default_user_data = {
        'username': '', 'telegram_id': '', 'password': '', 'user_role': 'user',
        'daily_new_limit': 10, 'timezone_offset': 7
    }
    return render_template('admin/add_user.html', user_data=default_user_data, roles=['user', 'admin'])
