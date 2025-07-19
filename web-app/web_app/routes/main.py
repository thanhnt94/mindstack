# web_app/routes/main.py
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
import logging
import json # Import json
from ..services import stats_service # Import stats_service
from ..models import User # Import User
from .decorators import login_required # Import login_required

# Tạo một Blueprint mới cho các route chính/chung
main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__) # Khởi tạo logger

@main_bp.route('/')
# BẮT ĐẦU THAY ĐỔI: Xóa decorator @login_required để route gốc có thể truy cập công khai
# @login_required
# KẾT THÚC THAY ĐỔI
def index():
    """
    Mô tả: Route gốc của ứng dụng. Chuyển hướng đến trang chủ giới thiệu (/home).
    """
    return redirect(url_for('main.home'))

@main_bp.route('/home')
def home():
    """
    Mô tả: Hiển thị trang chủ giới thiệu của ứng dụng (trang portfolio).
           Trang này có thể truy cập bởi cả người dùng đã đăng nhập và chưa đăng nhập.
    """
    return render_template('home.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Mô tả: Hiển thị trang thống kê (dashboard) cho người dùng.
    """
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    dashboard_data = stats_service.get_dashboard_stats(user_id)
    if not dashboard_data:
        flash("Không thể tải dữ liệu thống kê.", "error")
        # THAY ĐỔI: Chuyển hướng về trang chủ giới thiệu (/home)
        return redirect(url_for('main.home'))
    dashboard_data_json = json.dumps(dashboard_data)
    
    # Lấy current_question_set_id từ user
    current_question_set_id = user.current_question_set_id if user else None

    # Lấy dữ liệu bảng xếp hạng cho dashboard người dùng
    # Lấy tham số sort_by và timeframe từ request, mặc định là 'total_score' và 'all_time'
    sort_by = request.args.get('sort_by', 'total_score')
    timeframe = request.args.get('timeframe', 'all_time')
    
    leaderboard_data = stats_service.get_user_leaderboard_data(
        sort_by=sort_by,
        timeframe=timeframe,
        limit=10 # Giới hạn 10 người dùng hàng đầu cho bảng xếp hạng
    )

    return render_template(
        'dashboard.html', 
        dashboard_data=dashboard_data,
        dashboard_data_json=dashboard_data_json,
        current_set_id=user.current_set_id,
        current_question_set_id=current_question_set_id,
        leaderboard_data=leaderboard_data,
        current_sort_by=sort_by,
        current_timeframe=timeframe
    )
