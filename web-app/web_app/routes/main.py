# web_app/routes/main.py
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
import logging
import json
import os
import time
from ..services import stats_service
from ..models import User
from .decorators import login_required
from ..config import MAINTENANCE_CONFIG_PATH # Thêm import

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

@main_bp.route('/')
def index():
    """
    Mô tả: Route gốc của ứng dụng. Chuyển hướng đến trang chủ giới thiệu (/home).
    """
    return redirect(url_for('main.home'))

@main_bp.route('/home')
def home():
    """
    Mô tả: Hiển thị trang chủ giới thiệu của ứng dụng (trang portfolio).
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
        return redirect(url_for('main.home'))
    dashboard_data_json = json.dumps(dashboard_data)
    
    current_question_set_id = user.current_question_set_id if user else None
    sort_by = request.args.get('sort_by', 'total_score')
    timeframe = request.args.get('timeframe', 'all_time')
    
    leaderboard_data = stats_service.get_user_leaderboard_data(
        sort_by=sort_by, timeframe=timeframe, limit=10
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

# --- BẮT ĐẦU THÊM MỚI: Route cho trang bảo trì ---
@main_bp.route('/maintenance')
def maintenance_page():
    """
    Mô tả: Hiển thị trang thông báo bảo trì cho người dùng.
    """
    config = {'end_timestamp': time.time() + 3600, 'message': 'Hệ thống sẽ sớm quay trở lại.'} # Mặc định
    if os.path.exists(MAINTENANCE_CONFIG_PATH):
        try:
            with open(MAINTENANCE_CONFIG_PATH, 'r') as f:
                config = json.load(f)
        except (IOError, json.JSONDecodeError):
            pass # Sử dụng giá trị mặc định nếu có lỗi
    
    return render_template('maintenance.html', config=config)
# --- KẾT THÚC THÊM MỚI ---
