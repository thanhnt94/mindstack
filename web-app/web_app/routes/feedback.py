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
    Mô tả: Hiển thị trang danh sách feedback cho người dùng đã đăng nhập, có hỗ trợ lọc.
    """
    user_id = session['user_id']
    user = User.query.get(user_id)

    # BẮT ĐẦU THAY ĐỔI: Lấy tham số lọc từ URL
    filter_sent = request.args.get('filter_sent', 'all')
    filter_received = request.args.get('filter_received', 'all')
    # KẾT THÚC THAY ĐỔI

    # BẮT ĐẦU THAY ĐỔI: Truyền tham số lọc vào service
    feedbacks_sent = feedback_service.get_feedback_sent_by_user(user_id, filter_by=filter_sent)
    feedbacks_received = feedback_service.get_feedback_received_by_user(user_id, filter_by=filter_received)
    # KẾT THÚC THAY ĐỔI
    
    return render_template(
        'feedback/feedback_list.html', 
        feedbacks_sent=feedbacks_sent, 
        feedbacks_received=feedbacks_received,
        current_user=user,
        # BẮT ĐẦU THAY ĐỔI: Truyền lại giá trị filter để hiển thị trên form
        current_filter_sent=filter_sent,
        current_filter_received=filter_received
        # KẾT THÚC THAY ĐỔI
    )

@feedback_bp.route('/update_status/<int:feedback_id>', methods=['POST'])
@login_required
def update_status(feedback_id):
    """
    Mô tả: Cập nhật trạng thái và bình luận của một feedback.
    """
    user_id = session['user_id']
    new_status = request.form.get('status')
    resolver_comment = request.form.get('resolver_comment')
    
    feedback_obj, success, message = feedback_service.update_feedback_status(
        feedback_id, new_status, user_id, resolver_comment
    )

    if not success:
        flash(message, "error")
    else:
        flash(f"Đã cập nhật feedback #{feedback_id}.", "success")
        
    return redirect(url_for('feedback.list_feedback'))
