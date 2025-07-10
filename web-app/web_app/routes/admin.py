# web_app/routes/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, request
import logging
from ..services import user_service, set_service # THÊM: Import set_service
from ..models import db, User
from .decorators import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
logger = logging.getLogger(__name__)

# ========================== User Management ==========================
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

# ========================== Set Management (BẮT ĐẦU THÊM MỚI) ==========================
@admin_bp.route('/sets')
@admin_required
def manage_sets():
    """
    Mô tả: Hiển thị trang quản lý tất cả các bộ thẻ cho quản trị viên.
    """
    sets = set_service.get_all_sets_with_details()
    return render_template('admin/manage_sets.html', sets=sets)

@admin_bp.route('/sets/add', methods=['GET', 'POST'])
@admin_required
def add_set():
    """
    Mô tả: Hiển thị form thêm bộ thẻ mới và xử lý việc tạo.
    """
    if request.method == 'POST':
        data = request.form.to_dict()
        creator_id = session.get('user_id')
        new_set, status = set_service.create_set(data, creator_id)
        if status == "success":
            flash(f"Bộ thẻ '{new_set.title}' đã được thêm thành công.", "success")
            return redirect(url_for('admin.manage_sets'))
        else:
            flash(f"Lỗi khi thêm bộ thẻ: {status}", "error")
            return render_template('admin/add_set.html', set_data=data)
    
    return render_template('admin/add_set.html', set_data={})

@admin_bp.route('/sets/edit/<int:set_id>', methods=['GET', 'POST'])
@admin_required
def edit_set(set_id):
    """
    Mô tả: Hiển thị form chỉnh sửa bộ thẻ và xử lý việc cập nhật.
    """
    set_to_edit = set_service.get_set_by_id(set_id)
    if not set_to_edit:
        flash("Không tìm thấy bộ thẻ.", "error")
        return redirect(url_for('admin.manage_sets'))

    if request.method == 'POST':
        data = request.form.to_dict()
        updated_set, status = set_service.update_set(set_id, data)
        if status == "success":
            flash(f"Cập nhật bộ thẻ '{updated_set.title}' thành công.", "success")
            return redirect(url_for('admin.manage_sets'))
        else:
            flash(f"Lỗi khi cập nhật bộ thẻ: {status}", "error")
    
    return render_template('admin/edit_set.html', set_data=set_to_edit)

@admin_bp.route('/sets/delete/<int:set_id>', methods=['POST'])
@admin_required
def delete_set(set_id):
    """
    Mô tả: Xử lý yêu cầu xóa bộ thẻ.
    """
    success, status = set_service.delete_set(set_id)
    if success:
        flash("Bộ thẻ đã được xóa thành công.", "success")
    else:
        flash(f"Lỗi khi xóa bộ thẻ: {status}", "error")
    
    return redirect(url_for('admin.manage_sets'))

# ========================== (KẾT THÚC THÊM MỚI) ==========================
