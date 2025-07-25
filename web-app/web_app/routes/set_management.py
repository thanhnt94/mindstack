# web_app/routes/set_management.py (File mới)
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, send_file
from ..services import set_service, quiz_service
from ..models import User
from .decorators import login_required

set_management_bp = Blueprint('set_management', __name__, url_prefix='/sets')

@set_management_bp.route('/manage')
@login_required
def manage():
    """
    Mô tả: Hiển thị trang quản lý các bộ thẻ và bộ câu hỏi do người dùng tạo.
    """
    user_id = session['user_id']
    
    user_flashcard_sets = set_service.get_sets_by_creator_id(user_id)
    user_quiz_sets = quiz_service.get_question_sets_by_creator_id(user_id)

    return render_template(
        'set_management/manage_sets.html',
        flashcard_sets=user_flashcard_sets,
        quiz_sets=user_quiz_sets
    )

# --- Routes cho Flashcard Sets ---

@set_management_bp.route('/flashcard/add', methods=['GET', 'POST'])
@login_required
def add_flashcard_set():
    """
    Mô tả: Hiển thị form và xử lý việc thêm mới một bộ flashcard.
    """
    if request.method == 'POST':
        data = request.form.to_dict()
        creator_id = session['user_id']
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                if not file.filename.endswith('.xlsx'):
                    flash("File không hợp lệ. Vui lòng chỉ tải lên file .xlsx", "error")
                    return render_template('set_management/add_flashcard_set.html', set_data=data)
                file_stream = file.stream
        
        new_set, status = set_service.create_set(data, creator_id, file_stream)
        
        if status == "success":
            flash(f"Bộ thẻ '{new_set.title}' đã được thêm thành công.", "success")
            return redirect(url_for('set_management.manage'))
        else:
            flash(f"Lỗi khi thêm bộ thẻ: {status}", "error")
            return render_template('set_management/add_flashcard_set.html', set_data=data)
            
    return render_template('set_management/add_flashcard_set.html', set_data={})

@set_management_bp.route('/flashcard/edit/<int:set_id>', methods=['GET', 'POST'])
@login_required
def edit_flashcard_set(set_id):
    """
    Mô tả: Hiển thị form và xử lý việc chỉnh sửa một bộ flashcard.
    """
    set_to_edit = set_service.get_set_by_id(set_id)
    if not set_to_edit or set_to_edit.creator_user_id != session['user_id']:
        flash("Bạn không có quyền sửa bộ thẻ này.", "error")
        return redirect(url_for('set_management.manage'))

    if request.method == 'POST':
        data = request.form.to_dict()
        user_id = session['user_id']
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                file_stream = file.stream
        
        updated_set, status = set_service.update_set(set_id, data, user_id, file_stream)
        
        if status == "success":
            flash(f"Cập nhật bộ thẻ '{updated_set.title}' thành công.", "success")
            return redirect(url_for('set_management.manage'))
        else:
            flash(f"Lỗi khi cập nhật bộ thẻ: {status}", "error")
    
    return render_template('set_management/edit_flashcard_set.html', set_data=set_to_edit)

@set_management_bp.route('/flashcard/delete/<int:set_id>', methods=['POST'])
@login_required
def delete_flashcard_set(set_id):
    """
    Mô tả: Xử lý việc xóa một bộ flashcard.
    """
    user_id = session['user_id']
    success, status = set_service.delete_set(set_id, user_id)
    if success:
        flash("Bộ thẻ đã được xóa thành công.", "success")
    else:
        flash(f"Lỗi khi xóa bộ thẻ: {status}", "error")
    return redirect(url_for('set_management.manage'))

# --- Routes cho Quiz Sets ---

@set_management_bp.route('/quiz/add', methods=['GET', 'POST'])
@login_required
def add_quiz_set():
    """
    Mô tả: Hiển thị form và xử lý việc thêm mới một bộ câu hỏi quiz.
    """
    if request.method == 'POST':
        data = request.form.to_dict()
        creator_id = session['user_id']
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                file_stream = file.stream
        
        new_set, status = quiz_service.create_question_set(data, creator_id, file_stream)
        
        if status == "success":
            flash(f"Bộ câu hỏi '{new_set.title}' đã được thêm thành công.", "success")
            return redirect(url_for('set_management.manage'))
        else:
            flash(f"Lỗi khi thêm bộ câu hỏi: {status}", "error")
            return render_template('set_management/add_quiz_set.html', set_data=data)
            
    return render_template('set_management/add_quiz_set.html', set_data={})

@set_management_bp.route('/quiz/edit/<int:set_id>', methods=['GET', 'POST'])
@login_required
def edit_quiz_set(set_id):
    """
    Mô tả: Hiển thị form và xử lý việc chỉnh sửa một bộ câu hỏi quiz.
    """
    set_to_edit = quiz_service.get_question_set_by_id(set_id)
    if not set_to_edit or set_to_edit.creator_user_id != session['user_id']:
        flash("Bạn không có quyền sửa bộ câu hỏi này.", "error")
        return redirect(url_for('set_management.manage'))

    if request.method == 'POST':
        data = request.form.to_dict()
        user_id = session['user_id']
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                file_stream = file.stream
        
        updated_set, status = quiz_service.update_question_set(set_id, data, user_id, file_stream)
        
        if status == "success":
            flash(f"Cập nhật bộ câu hỏi '{updated_set.title}' thành công.", "success")
            return redirect(url_for('set_management.manage'))
        else:
            flash(f"Lỗi khi cập nhật bộ câu hỏi: {status}", "error")
    
    return render_template('set_management/edit_quiz_set.html', set_data=set_to_edit)

@set_management_bp.route('/quiz/delete/<int:set_id>', methods=['POST'])
@login_required
def delete_quiz_set(set_id):
    """
    Mô tả: Xử lý việc xóa một bộ câu hỏi quiz.
    """
    user_id = session['user_id']
    success, status = quiz_service.delete_question_set(set_id, user_id)
    if success:
        flash("Bộ câu hỏi đã được xóa thành công.", "success")
    else:
        flash(f"Lỗi khi xóa bộ câu hỏi: {status}", "error")
    return redirect(url_for('set_management.manage'))
