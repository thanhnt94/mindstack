# web_app/routes/feedback.py
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from ..services import feedback_service
from ..models import User
from .decorators import login_required

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')

@feedback_bp.route('/list')
@login_required
def list_feedback():
    """
    Mô tả: Hiển thị trang danh sách feedback cho người dùng đã đăng nhập.
    - Hiển thị feedback đã gửi cho tất cả người dùng.
    - Hiển thị feedback nhận được cho admin và người tạo bộ thẻ.
    """
    user_id = session['user_id']
    user = User.query.get(user_id)

    # --- BẮT ĐẦU THAY ĐỔI: Bỏ kiểm tra quyền truy cập nghiêm ngặt ---
    # Lấy cả hai danh sách feedback
    feedbacks_sent = feedback_service.get_feedback_sent_by_user(user_id)
    feedbacks_received = feedback_service.get_feedback_received_by_user(user_id)
    # --- KẾT THÚC THAY ĐỔI ---
    
    return render_template(
        'feedback/feedback_list.html', 
        feedbacks_sent=feedbacks_sent, 
        feedbacks_received=feedbacks_received,
        current_user=user
    )

@feedback_bp.route('/update_status/<int:feedback_id>', methods=['POST'])
@login_required
def update_status(feedback_id):
    """
    Mô tả: Cập nhật trạng thái của một feedback (ví dụ: từ 'new' sang 'seen').
    """
    user_id = session['user_id']
    new_status = request.form.get('status')
    
    feedback_obj, success, message = feedback_service.update_feedback_status(feedback_id, new_status, user_id)

    if not success:
        flash(message, "error")
    else:
        flash(f"Đã cập nhật trạng thái feedback #{feedback_id} thành '{new_status}'.", "success")
        
    return redirect(url_for('feedback.list_feedback'))
