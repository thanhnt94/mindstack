# web_app/routes/set_management.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, send_file
# --- BẮT ĐẦU THAY ĐỔI: Import thêm flashcard_service ---
from ..services import set_service, quiz_service, flashcard_service
# --- KẾT THÚC THAY ĐỔI ---
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
            if session.get('user_role') == 'admin':
                return redirect(url_for('admin.manage_sets'))
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
    Đã được nâng cấp để hỗ trợ tìm kiếm và phân trang danh sách thẻ.
    """
    user_id = session['user_id']
    user_role = session.get('user_role')
    set_to_edit = set_service.get_set_by_id(set_id)

    # Kiểm tra quyền truy cập
    if not set_to_edit or (set_to_edit.creator_user_id != user_id and user_role != 'admin'):
        flash("Bạn không có quyền sửa bộ thẻ này.", "error")
        return redirect(url_for('admin.manage_sets') if user_role == 'admin' else url_for('set_management.manage'))

    # Xử lý khi người dùng LƯU THÔNG TIN BỘ THẺ (POST request)
    if request.method == 'POST':
        data = request.form.to_dict()
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                file_stream = file.stream
        
        updated_set, status = set_service.update_set(set_id, data, user_id, file_stream)
        
        if status == "success":
            flash(f"Cập nhật bộ thẻ '{updated_set.title}' thành công.", "success")
            # Chuyển hướng về chính trang edit để xem thay đổi
            return redirect(url_for('set_management.edit_flashcard_set', set_id=set_id))
        else:
            flash(f"Lỗi khi cập nhật bộ thẻ: {status}", "error")

    # Xử lý khi người dùng XEM TRANG hoặc TÌM KIẾM/PHÂN TRANG (GET request)
    search_term = request.args.get('q', '')
    search_field = request.args.get('field', 'all')
    page = request.args.get('page', 1, type=int)

    # Lấy danh sách thẻ đã được tìm kiếm và phân trang
    cards_pagination = flashcard_service.search_cards_in_set_paginated(
        set_id=set_id,
        search_term=search_term,
        search_field=search_field,
        page=page,
        per_page=10 # Hiển thị 10 thẻ mỗi trang
    )
    
    return render_template(
        'set_management/edit_flashcard_set.html', 
        set_data=set_to_edit,
        cards_pagination=cards_pagination,
        search_term=search_term,
        search_field=search_field
    )

@set_management_bp.route('/flashcard/delete/<int:set_id>', methods=['POST'])
@login_required
def delete_flashcard_set(set_id):
    """
    Mô tả: Xử lý việc xóa một bộ flashcard.
    Admin có thể xóa mọi bộ, người dùng chỉ có thể xóa bộ của mình.
    """
    user_id = session['user_id']
    user_role = session.get('user_role')
    
    success, status = set_service.delete_set(set_id, user_id)
    if success:
        flash("Bộ thẻ đã được xóa thành công.", "success")
    else:
        flash(f"Lỗi khi xóa bộ thẻ: {status}", "error")
    
    if user_role == 'admin':
        return redirect(url_for('admin.manage_sets'))
    return redirect(url_for('set_management.manage'))

@set_management_bp.route('/flashcard/export-excel/<int:set_id>')
@login_required
def export_flashcard_set_excel(set_id):
    """
    Mô tả: Xuất bộ thẻ flashcard ra file Excel.
    """
    set_to_export = set_service.get_set_by_id(set_id)
    if not set_to_export or (set_to_export.creator_user_id != session['user_id'] and session.get('user_role') != 'admin'):
        flash("Bạn không có quyền xuất bộ thẻ này.", "error")
        return redirect(request.referrer or url_for('set_management.manage'))

    excel_stream = set_service.export_set_to_excel(set_id)
    if not excel_stream:
        flash("Lỗi khi tạo file Excel.", "error")
        return redirect(url_for('set_management.edit_flashcard_set', set_id=set_id))
    
    safe_title = "".join(c for c in set_to_export.title if c.isalnum() or c in (' ', '_')).rstrip()
    filename = f"BoThe_{safe_title}.xlsx"
    return send_file(
        excel_stream, as_attachment=True, download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@set_management_bp.route('/flashcard/export-zip/<int:set_id>')
@login_required
def export_flashcard_set_zip(set_id):
    """
    Mô tả: Xuất bộ thẻ flashcard ra file ZIP (bao gồm cả media).
    """
    set_to_export = set_service.get_set_by_id(set_id)
    if not set_to_export or (set_to_export.creator_user_id != session['user_id'] and session.get('user_role') != 'admin'):
        flash("Bạn không có quyền xuất bộ thẻ này.", "error")
        return redirect(request.referrer or url_for('set_management.manage'))

    zip_stream = set_service.export_set_as_zip(set_id)
    if not zip_stream:
        flash("Lỗi khi tạo file ZIP.", "error")
        return redirect(url_for('set_management.edit_flashcard_set', set_id=set_id))
    
    safe_title = "".join(c for c in set_to_export.title if c.isalnum() or c in (' ', '_')).rstrip()
    filename = f"BoThe_{safe_title}_Full.zip"
    return send_file(
        zip_stream, as_attachment=True, download_name=filename, mimetype='application/zip'
    )

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
            if session.get('user_role') == 'admin':
                return redirect(url_for('admin.manage_question_sets'))
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
    Admin có thể sửa mọi bộ, người dùng chỉ có thể sửa bộ của mình.
    """
    set_to_edit = quiz_service.get_question_set_by_id(set_id)
    user_id = session['user_id']
    user_role = session.get('user_role')

    if not set_to_edit or (set_to_edit.creator_user_id != user_id and user_role != 'admin'):
        flash("Bạn không có quyền sửa bộ câu hỏi này.", "error")
        if user_role == 'admin':
            return redirect(url_for('admin.manage_question_sets'))
        return redirect(url_for('set_management.manage'))

    if request.method == 'POST':
        data = request.form.to_dict()
        file_stream = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename != '':
                file_stream = file.stream
        
        updated_set, status = quiz_service.update_question_set(set_id, data, user_id, file_stream)
        
        if status == "success":
            flash(f"Cập nhật bộ câu hỏi '{updated_set.title}' thành công.", "success")
            if user_role == 'admin':
                return redirect(url_for('admin.manage_question_sets'))
            return redirect(url_for('set_management.manage'))
        else:
            flash(f"Lỗi khi cập nhật bộ câu hỏi: {status}", "error")
    
    return render_template('set_management/edit_quiz_set.html', set_data=set_to_edit)

@set_management_bp.route('/quiz/delete/<int:set_id>', methods=['POST'])
@login_required
def delete_quiz_set(set_id):
    """
    Mô tả: Xử lý việc xóa một bộ câu hỏi quiz.
    Admin có thể xóa mọi bộ, người dùng chỉ có thể xóa bộ của mình.
    """
    user_id = session['user_id']
    user_role = session.get('user_role')

    success, status = quiz_service.delete_question_set(set_id, user_id)
    if success:
        flash("Bộ câu hỏi đã được xóa thành công.", "success")
    else:
        flash(f"Lỗi khi xóa bộ câu hỏi: {status}", "error")
    
    if user_role == 'admin':
        return redirect(url_for('admin.manage_question_sets'))
    return redirect(url_for('set_management.manage'))

@set_management_bp.route('/quiz/export-excel/<int:set_id>')
@login_required
def export_quiz_set_excel(set_id):
    """
    Mô tả: Xuất bộ câu hỏi quiz ra file Excel.
    """
    set_to_export = quiz_service.get_question_set_by_id(set_id)
    if not set_to_export or (set_to_export.creator_user_id != session['user_id'] and session.get('user_role') != 'admin'):
        flash("Bạn không có quyền xuất bộ câu hỏi này.", "error")
        return redirect(request.referrer or url_for('set_management.manage'))

    excel_stream = quiz_service.export_set_to_excel(set_id)
    if not excel_stream:
        flash("Lỗi khi tạo file Excel.", "error")
        return redirect(url_for('set_management.edit_quiz_set', set_id=set_id))
    
    safe_title = "".join(c for c in set_to_export.title if c.isalnum() or c in (' ', '_')).rstrip()
    filename = f"BoCauHoi_{safe_title}.xlsx"
    return send_file(
        excel_stream, as_attachment=True, download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@set_management_bp.route('/quiz/export-zip/<int:set_id>')
@login_required
def export_quiz_set_zip(set_id):
    """
    Mô tả: Xuất bộ câu hỏi quiz ra file ZIP (bao gồm cả media).
    """
    set_to_export = quiz_service.get_question_set_by_id(set_id)
    if not set_to_export or (set_to_export.creator_user_id != session['user_id'] and session.get('user_role') != 'admin'):
        flash("Bạn không có quyền xuất bộ câu hỏi này.", "error")
        return redirect(request.referrer or url_for('set_management.manage'))

    zip_stream = quiz_service.export_question_set_as_zip(set_id)
    if not zip_stream:
        flash("Lỗi khi tạo file ZIP.", "error")
        return redirect(url_for('set_management.edit_quiz_set', set_id=set_id))
    
    safe_title = "".join(c for c in set_to_export.title if c.isalnum() or c in (' ', '_')).rstrip()
    filename = f"BoCauHoi_{safe_title}_Full.zip"
    return send_file(
        zip_stream, as_attachment=True, download_name=filename, mimetype='application/zip'
    )
