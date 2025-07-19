# web_app/routes/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, send_file, current_app
import logging
import io
import asyncio
import threading
import json
import os
import time
from datetime import datetime
from ..services import user_service, set_service, stats_service, quiz_service, audio_service
from ..models import db, User, UserFlashcardProgress
from .decorators import admin_required
from ..config import DATABASE_PATH, MAINTENANCE_CONFIG_PATH

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
logger = logging.getLogger(__name__)

# --- Biến toàn cục để theo dõi tác vụ chạy nền ---
audio_generation_task = {
    "status": "idle", "progress": 0, "total": 0, "message": ""
}

def audio_generation_worker(app, status_dict):
    with app.app_context():
        log_prefix = "[AUDIO_WORKER]"
        try:
            logger.info(f"{log_prefix} Bắt đầu tác vụ chạy nền.")
            status_dict['status'] = 'running'
            status_dict['progress'] = 0
            status_dict['total'] = 0
            status_dict['message'] = 'Đang khởi động...'
            processed, total = asyncio.run(audio_service.generate_cache_for_all_cards(status_dict))
            status_dict['status'] = 'finished'
            status_dict['message'] = f"Hoàn tất! Đã tạo thành công {processed}/{total} file audio mới."
            logger.info(f"{log_prefix} Tác vụ chạy nền đã hoàn tất.")
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi trong thread tạo audio: {e}", exc_info=True)
            status_dict['status'] = 'error'
            status_dict['message'] = f"Đã xảy ra lỗi: {e}"

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    admin_stats = stats_service.get_admin_dashboard_stats()
    if not admin_stats:
        flash("Không thể tải dữ liệu cho Admin Dashboard.", "error")
        admin_stats = {}
    return render_template('admin/dashboard.html', stats=admin_stats)

# ... (Các route user, set, question set không thay đổi) ...
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
                    return render_template('admin/edit_set.html', set_data=data)
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
        excel_stream, as_attachment=True, download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
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
        excel_stream, as_attachment=True, download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
@admin_bp.route('/tools')
@admin_required
def tools_page():
    if audio_generation_task['status'] in ['finished', 'error']:
        flash(audio_generation_task['message'], 'success' if audio_generation_task['status'] == 'finished' else 'error')
        audio_generation_task['status'] = 'idle'
        audio_generation_task['progress'] = 0
        audio_generation_task['total'] = 0
        audio_generation_task['message'] = ''
    
    # --- BẮT ĐẦU THÊM MỚI: Đọc trạng thái bảo trì hiện tại ---
    maintenance_config = {'is_active': False, 'duration_hours': 1, 'message': ''}
    if os.path.exists(MAINTENANCE_CONFIG_PATH):
        try:
            with open(MAINTENANCE_CONFIG_PATH, 'r') as f:
                maintenance_config = json.load(f)
        except (IOError, json.JSONDecodeError):
            pass # Sử dụng giá trị mặc định nếu có lỗi
    # --- KẾT THÚC THÊM MỚI ---
            
    return render_template('admin/tools.html', task_status=audio_generation_task, maintenance_config=maintenance_config)

@admin_bp.route('/backup-database')
@admin_required
def backup_database():
    log_prefix = "[ADMIN_TOOLS|BackupDB]"
    try:
        logger.info(f"{log_prefix} Yêu cầu sao lưu database từ admin ID: {session.get('user_id')}")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"mindstack_backup_{timestamp}.db"
        return send_file(
            DATABASE_PATH,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi khi tạo file sao lưu database: {e}", exc_info=True)
        flash("Đã xảy ra lỗi khi sao lưu database.", "error")
        return redirect(url_for('admin.tools_page'))

@admin_bp.route('/generate-audio-cache', methods=['POST'])
@admin_required
def generate_audio_cache():
    global audio_generation_task
    log_prefix = "[ADMIN_TOOLS|GenerateAudioCache]"
    if audio_generation_task['status'] == 'running':
        flash("Quá trình tạo audio cache đã đang chạy.", "warning")
        return redirect(url_for('admin.tools_page'))
    logger.info(f"{log_prefix} Yêu cầu tạo audio cache từ admin ID: {session.get('user_id')}")
    app = current_app._get_current_object()
    thread = threading.Thread(target=audio_generation_worker, args=(app, audio_generation_task))
    thread.start()
    flash("Đã bắt đầu quá trình tạo audio cache trong nền. Bạn có thể tải lại trang này để xem tiến trình.", "info")
    return redirect(url_for('admin.tools_page'))

@admin_bp.route('/sets/export-zip/<int:set_id>')
@admin_required
def export_set_zip(set_id):
    set_to_export = set_service.get_set_by_id(set_id)
    if not set_to_export:
        flash("Không tìm thấy bộ thẻ để xuất.", "error")
        return redirect(url_for('admin.manage_sets'))
    zip_stream = set_service.export_set_as_zip(set_id)
    if not zip_stream:
        flash("Lỗi khi tạo file ZIP.", "error")
        return redirect(url_for('admin.edit_set', set_id=set_id))
    safe_title = "".join(c for c in set_to_export.title if c.isalnum() or c in (' ', '_')).rstrip()
    filename = f"BoThe_{safe_title}_Full.zip"
    return send_file(
        zip_stream, as_attachment=True, download_name=filename, mimetype='application/zip'
    )

@admin_bp.route('/question-sets/export-zip/<int:set_id>')
@admin_required
def export_question_set_zip(set_id):
    set_to_export = quiz_service.get_question_set_by_id(set_id)
    if not set_to_export:
        flash("Không tìm thấy bộ câu hỏi để xuất.", "error")
        return redirect(url_for('admin.manage_question_sets'))
    zip_stream = quiz_service.export_question_set_as_zip(set_id)
    if not zip_stream:
        flash("Lỗi khi tạo file ZIP.", "error")
        return redirect(url_for('admin.edit_question_set', set_id=set_id))
    safe_title = "".join(c for c in set_to_export.title if c.isalnum() or c in (' ', '_')).rstrip()
    filename = f"BoCauHoi_{safe_title}_Full.zip"
    return send_file(
        zip_stream, as_attachment=True, download_name=filename, mimetype='application/zip'
    )

# --- BẮT ĐẦU THÊM MỚI: Route xử lý chế độ bảo trì ---
@admin_bp.route('/update-maintenance', methods=['POST'])
@admin_required
def update_maintenance():
    """
    Mô tả: Cập nhật trạng thái bảo trì của trang web.
    """
    try:
        status = request.form.get('maintenance_status')
        duration_hours = request.form.get('duration_hours', 0, type=float)
        message = request.form.get('message', 'Hệ thống đang được bảo trì. Vui lòng quay lại sau.')

        config = {
            'is_active': status == 'on',
            'duration_hours': duration_hours,
            'message': message,
            'end_timestamp': 0
        }

        if config['is_active']:
            duration_seconds = duration_hours * 3600
            config['end_timestamp'] = time.time() + duration_seconds
            flash(f"Đã bật chế độ bảo trì trong {duration_hours} giờ.", "success")
        else:
            flash("Đã tắt chế độ bảo trì.", "info")

        # Ghi vào file JSON
        with open(MAINTENANCE_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=4)

    except Exception as e:
        logger.error(f"Lỗi khi cập nhật chế độ bảo trì: {e}", exc_info=True)
        flash("Đã xảy ra lỗi khi cập nhật chế độ bảo trì.", "error")

    return redirect(url_for('admin.tools_page'))
# --- KẾT THÚC THÊM MỚI ---
