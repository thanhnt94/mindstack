# web_app/routes/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, send_file
import logging
import io
from ..services import user_service, set_service, stats_service, quiz_service
from ..models import db, User
from .decorators import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
logger = logging.getLogger(__name__)

# ... (các route quản lý user và flashcard set không đổi) ...
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    admin_stats = stats_service.get_admin_dashboard_stats()
    if not admin_stats:
        flash("Không thể tải dữ liệu cho Admin Dashboard.", "error")
        admin_stats = {}
    return render_template('admin/dashboard.html', stats=admin_stats)

@admin_bp.route('/users')
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin/manage_users.html', users=users)

@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
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
    if request.method == 'POST':
        data = request.form.to_dict()
        new_user, status = user_service.create_user(data)
        if status == "success":
            flash(f"Người dùng '{new_user.username or new_user.telegram_id}' đã được thêm thành công.", "success")
            return redirect(url_for('admin.manage_users'))
        else:
            flash(f"Lỗi khi thêm người dùng: {status}", "error")
            return render_template('admin/add_user.html', user_data=data, roles=['user', 'admin'])
    default_user_data = {'username': '', 'telegram_id': '', 'password': '', 'user_role': 'user', 'daily_new_limit': 10, 'timezone_offset': 7}
    return render_template('admin/add_user.html', user_data=default_user_data, roles=['user', 'admin'])

@admin_bp.route('/sets')
@admin_required
def manage_sets():
    sets = set_service.get_all_sets_with_details()
    return render_template('admin/manage_sets.html', sets=sets)

@admin_bp.route('/sets/add', methods=['GET', 'POST'])
@admin_required
def add_set():
    if request.method == 'POST':
        data = request.form.to_dict()
        creator_id = session.get('user_id')
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                if not file.filename.endswith('.xlsx'):
                    flash("File không hợp lệ. Vui lòng chỉ tải lên file .xlsx", "error")
                    return render_template('admin/add_set.html', set_data=data)
                file_stream = file.stream
        new_set, status = set_service.create_set(data, creator_id, file_stream)
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
    set_to_edit = set_service.get_set_by_id(set_id)
    if not set_to_edit:
        flash("Không tìm thấy bộ thẻ.", "error")
        return redirect(url_for('admin.manage_sets'))

    if request.method == 'POST':
        data = request.form.to_dict()
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                if not file.filename.endswith('.xlsx'):
                    flash("File không hợp lệ. Vui lòng chỉ tải lên file .xlsx", "error")
                    return render_template('admin/edit_set.html', set_data=set_to_edit)
                file_stream = file.stream
        updated_set, status = set_service.update_set(set_id, data, file_stream)
        if status == "success":
            flash(f"Cập nhật bộ thẻ '{updated_set.title}' thành công.", "success")
            return redirect(url_for('admin.manage_sets'))
        else:
            flash(f"Lỗi khi cập nhật bộ thẻ: {status}", "error")
    return render_template('admin/edit_set.html', set_data=set_to_edit)

@admin_bp.route('/sets/delete/<int:set_id>', methods=['POST'])
@admin_required
def delete_set(set_id):
    success, status = set_service.delete_set(set_id)
    if success:
        flash("Bộ thẻ đã được xóa thành công.", "success")
    else:
        flash(f"Lỗi khi xóa bộ thẻ: {status}", "error")
    return redirect(url_for('admin.manage_sets'))

@admin_bp.route('/sets/export/<int:set_id>')
@admin_required
def export_set(set_id):
    set_to_export = set_service.get_set_by_id(set_id)
    if not set_to_export:
        flash("Không tìm thấy bộ thẻ để xuất.", "error")
        return redirect(url_for('admin.manage_sets'))
        
    excel_stream = set_service.export_set_to_excel(set_id)
    if not excel_stream:
        flash("Lỗi khi tạo file Excel.", "error")
        return redirect(url_for('admin.edit_set', set_id=set_id))

    safe_title = "".join(c for c in set_to_export.title if c.isalnum() or c in (' ', '_')).rstrip()
    filename = f"BoThe_{safe_title}.xlsx"

    return send_file(
        excel_stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# --- BẮT ĐẦU SỬA ĐỔI: Quản lý Bộ Câu hỏi (Question Set) ---

@admin_bp.route('/question-sets')
@admin_required
def manage_question_sets():
    question_sets = quiz_service.get_all_question_sets_with_details()
    return render_template('admin/manage_question_sets.html', question_sets=question_sets)

@admin_bp.route('/question-sets/add', methods=['GET', 'POST'])
@admin_required
def add_question_set():
    if request.method == 'POST':
        data = request.form.to_dict()
        creator_id = session.get('user_id')
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                if not file.filename.endswith('.xlsx'):
                    flash("File không hợp lệ. Vui lòng chỉ tải lên file .xlsx", "error")
                    return render_template('admin/add_question_set.html', set_data=data)
                file_stream = file.stream
        new_set, status = quiz_service.create_question_set(data, creator_id, file_stream)
        if status == "success":
            flash(f"Bộ câu hỏi '{new_set.title}' đã được thêm thành công.", "success")
            return redirect(url_for('admin.manage_question_sets'))
        else:
            flash(f"Lỗi khi thêm bộ câu hỏi: {status}", "error")
            return render_template('admin/add_question_set.html', set_data=data)
    return render_template('admin/add_question_set.html', set_data={})

@admin_bp.route('/question-sets/edit/<int:set_id>', methods=['GET', 'POST'])
@admin_required
def edit_question_set(set_id):
    set_to_edit = quiz_service.get_question_set_by_id(set_id)
    if not set_to_edit:
        flash("Không tìm thấy bộ câu hỏi.", "error")
        return redirect(url_for('admin.manage_question_sets'))

    if request.method == 'POST':
        data = request.form.to_dict()
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                if not file.filename.endswith('.xlsx'):
                    flash("File không hợp lệ. Vui lòng chỉ tải lên file .xlsx", "error")
                    return render_template('admin/edit_question_set.html', set_data=set_to_edit)
                file_stream = file.stream
        updated_set, status = quiz_service.update_question_set(set_id, data, file_stream)
        if status == "success":
            flash(f"Cập nhật bộ câu hỏi '{updated_set.title}' thành công.", "success")
            return redirect(url_for('admin.manage_question_sets'))
        else:
            flash(f"Lỗi khi cập nhật bộ câu hỏi: {status}", "error")
    
    return render_template('admin/edit_question_set.html', set_data=set_to_edit)

@admin_bp.route('/question-sets/delete/<int:set_id>', methods=['POST'])
@admin_required
def delete_question_set(set_id):
    success, status = quiz_service.delete_question_set(set_id)
    if success:
        flash("Bộ câu hỏi đã được xóa thành công.", "success")
    else:
        flash(f"Lỗi khi xóa bộ câu hỏi: {status}", "error")
    return redirect(url_for('admin.manage_question_sets'))

@admin_bp.route('/question-sets/export/<int:set_id>')
@admin_required
def export_question_set(set_id):
    """
    Mô tả: Xử lý yêu cầu xuất một bộ câu hỏi ra file Excel.
    """
    set_to_export = quiz_service.get_question_set_by_id(set_id)
    if not set_to_export:
        flash("Không tìm thấy bộ câu hỏi để xuất.", "error")
        return redirect(url_for('admin.manage_question_sets'))
        
    excel_stream = quiz_service.export_set_to_excel(set_id)
    if not excel_stream:
        flash("Lỗi khi tạo file Excel.", "error")
        return redirect(url_for('admin.edit_question_set', set_id=set_id))

    safe_title = "".join(c for c in set_to_export.title if c.isalnum() or c in (' ', '_')).rstrip()
    filename = f"BoCauHoi_{safe_title}.xlsx"

    return send_file(
        excel_stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
# --- KẾT THÚC SỬA ĐỔI ---
