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
from sqlalchemy import text 
from ..services import user_service, set_service, stats_service, quiz_service, audio_service
from ..models import db, User, UserFlashcardProgress
from .decorators import admin_required
from ..config import DATABASE_PATH, MAINTENANCE_CONFIG_PATH

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
logger = logging.getLogger(__name__)

audio_generation_task = {
    "status": "idle", "progress": 0, "total": 0, "message": "", "stop_requested": False
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
            status_dict['stop_requested'] = False
            processed, total = asyncio.run(audio_service.generate_cache_for_all_cards(status_dict))
            if status_dict.get('stop_requested'):
                status_dict['status'] = 'stopped'
                status_dict['message'] = f"Quá trình đã được dừng. Đã tạo {processed}/{total} file audio mới."
            else:
                status_dict['status'] = 'finished'
                status_dict['message'] = f"Hoàn tất! Đã tạo thành công {processed}/{total} file audio mới."
            logger.info(f"{log_prefix} Tác vụ chạy nền đã hoàn tất với trạng thái: {status_dict['status']}.")
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi trong thread tạo audio: {e}", exc_info=True)
            status_dict['status'] = 'error'
            status_dict['message'] = f"Đã xảy ra lỗi: {e}"
        finally:
            status_dict['stop_requested'] = False

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    admin_stats = stats_service.get_admin_dashboard_stats()
    if not admin_stats:
        flash("Không thể tải dữ liệu cho Admin Dashboard.", "error")
        admin_stats = {}
    return render_template('admin/dashboard.html', stats=admin_stats)

# --- Quản lý Người dùng ---
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

# --- Dọn dẹp các route quản lý bộ thẻ/câu hỏi ---

@admin_bp.route('/sets')
@admin_required
def manage_sets():
    """
    Mô tả: Chỉ hiển thị trang quản lý tất cả các bộ flashcard.
    Các hành động (thêm, sửa, xóa) giờ đây được xử lý bởi set_management blueprint.
    """
    sets = set_service.get_all_sets_with_details()
    return render_template('admin/manage_sets.html', sets=sets)

@admin_bp.route('/question-sets')
@admin_required
def manage_question_sets():
    """
    Mô tả: Chỉ hiển thị trang quản lý tất cả các bộ câu hỏi.
    Các hành động (thêm, sửa, xóa) giờ đây được xử lý bởi set_management blueprint.
    """
    question_sets = quiz_service.get_all_question_sets_with_details()
    return render_template('admin/manage_question_sets.html', question_sets=question_sets)

# Các route add_set, edit_set, delete_set, export_set, export_set_zip,
# add_question_set, edit_question_set, delete_question_set, export_question_set, export_question_set_zip
# đã được di chuyển và hợp nhất vào set_management.py

# --- Công cụ & Bảo trì (Không thay đổi) ---
@admin_bp.route('/tools')
@admin_required
def tools_page():
    if audio_generation_task['status'] in ['finished', 'error', 'stopped']:
        flash(audio_generation_task['message'], 'success' if audio_generation_task['status'] in ['finished', 'stopped'] else 'error')
        audio_generation_task['status'] = 'idle'
        audio_generation_task['progress'] = 0
        audio_generation_task['total'] = 0
        audio_generation_task['message'] = ''
    
    maintenance_config = {'is_active': False, 'duration_hours': 1, 'message': ''}
    if os.path.exists(MAINTENANCE_CONFIG_PATH):
        try:
            with open(MAINTENANCE_CONFIG_PATH, 'r') as f:
                maintenance_config = json.load(f)
        except (IOError, json.JSONDecodeError):
            pass
            
    return render_template('admin/tools.html', task_status=audio_generation_task, maintenance_config=maintenance_config)

@admin_bp.route('/backup-database')
@admin_required
def backup_database():
    log_prefix = "[ADMIN_TOOLS|BackupDB]"
    try:
        logger.info(f"{log_prefix} Yêu cầu sao lưu database từ admin ID: {session.get('user_id')}")
        
        logger.info(f"{log_prefix} Đang thực hiện checkpoint WAL để đảm bảo dữ liệu nhất quán...")
        db.session.execute(text('PRAGMA wal_checkpoint(TRUNCATE);'))
        db.session.commit()
        logger.info(f"{log_prefix} Checkpoint WAL thành công.")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"mindstack_backup_{timestamp}.db"
        
        return send_file(
            DATABASE_PATH,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    except Exception as e:
        db.session.rollback() 
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

@admin_bp.route('/update-maintenance', methods=['POST'])
@admin_required
def update_maintenance():
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
        with open(MAINTENANCE_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật chế độ bảo trì: {e}", exc_info=True)
        flash("Đã xảy ra lỗi khi cập nhật chế độ bảo trì.", "error")
    return redirect(url_for('admin.tools_page'))

@admin_bp.route('/stop-audio-cache', methods=['POST'])
@admin_required
def stop_audio_cache():
    global audio_generation_task
    if audio_generation_task['status'] == 'running':
        audio_generation_task['stop_requested'] = True
        flash("Đã gửi yêu cầu dừng. Quá trình sẽ kết thúc sau khi hoàn tất file hiện tại.", "info")
    else:
        flash("Không có tác vụ nào đang chạy để dừng.", "warning")
    return redirect(url_for('admin.tools_page'))

@admin_bp.route('/clean-audio-cache', methods=['POST'])
@admin_required
def clean_audio_cache():
    log_prefix = "[ADMIN_TOOLS|CleanAudioCache]"
    logger.info(f"{log_prefix} Yêu cầu dọn dẹp cache từ admin ID: {session.get('user_id')}")
    try:
        deleted_count = audio_service.clean_orphan_audio_cache()
        if deleted_count >= 0:
            flash(f"Đã dọn dẹp thành công và xóa {deleted_count} file audio không còn sử dụng.", "success")
        else:
            flash("Đã xảy ra lỗi trong quá trình dọn dẹp cache.", "error")
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi nghiêm trọng khi dọn dẹp cache: {e}", exc_info=True)
        flash("Đã xảy ra lỗi nghiêm trọng. Vui lòng kiểm tra log.", "error")
    return redirect(url_for('admin.tools_page'))