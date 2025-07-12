# web_app/routes/main.py
from flask import Blueprint, render_template
from .decorators import login_required

# Tạo một Blueprint mới cho các route chính/chung
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def index():
    """
    Mô tả: Hiển thị trang chủ của ứng dụng, nơi người dùng có thể chọn
    giữa việc học Flashcard hoặc làm Trắc nghiệm.
    """
    return render_template('home.html')
