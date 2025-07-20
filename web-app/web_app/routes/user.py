# web_app/routes/user.py (File mới)
from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from ..services import user_service
from ..models import User
from .decorators import login_required

user_bp = Blueprint('user', __name__, url_prefix='/user')

@user_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """
    Mô tả: Hiển thị và xử lý trang cài đặt tài khoản cho người dùng.
    """
    user_id = session['user_id']
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            data = request.form.to_dict()
            _, status = user_service.update_user_profile(user_id, data)
            if status == "success":
                flash("Cập nhật hồ sơ thành công!", "success")
            else:
                flash(f"Lỗi khi cập nhật hồ sơ: {status}", "error")

        elif action == 'change_password':
            data = request.form.to_dict()
            success, message = user_service.change_user_password(user_id, data)
            if success:
                flash(message, "success")
            else:
                flash(message, "error")
        
        elif action == 'update_flashcard_options':
            data = request.form.to_dict()
            _, status = user_service.update_user_flashcard_options(user_id, data)
            if status == "success":
                flash("Cập nhật tùy chọn Flashcard thành công!", "success")
            else:
                flash(f"Lỗi khi cập nhật tùy chọn: {status}", "error")
        
        return redirect(url_for('user.settings'))

    user = User.query.get_or_404(user_id)
    return render_template('user/settings.html', user=user)
