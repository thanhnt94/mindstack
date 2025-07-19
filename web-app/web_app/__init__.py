# flashcard-web/web_app/__init__.py
from flask import Flask, request, session, redirect, url_for, render_template
from .db_instance import db
import logging
import json
import os
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    app.config.from_object('web_app.config')

    db.init_app(app)

    app.jinja_env.add_extension('jinja2.ext.do')

    @app.template_filter('format_unix_timestamp')
    def format_unix_timestamp_filter(timestamp):
        if timestamp is None:
            return "N/A"
        try:
            from .config import DEFAULT_TIMEZONE_OFFSET
            tz = timezone(timedelta(hours=DEFAULT_TIMEZONE_OFFSET))
            dt_object = datetime.fromtimestamp(timestamp, tz)
            return dt_object.strftime("%H:%M %d/%m/%Y")
        except (TypeError, ValueError, OSError) as e:
            logger.error(f"Lỗi khi định dạng timestamp {timestamp}: {e}", exc_info=True)
            return "Invalid Date"

    @app.before_request
    def check_maintenance_mode():
        # --- BẮT ĐẦU SỬA LỖI: Thêm 'auth.login' vào danh sách ngoại lệ ---
        if request.endpoint and (
            request.endpoint.startswith('static') or
            request.endpoint.startswith('admin.') or
            request.endpoint == 'main.maintenance_page' or
            request.endpoint == 'auth.login'  # Cho phép truy cập trang login
        ):
            return
        # --- KẾT THÚC SỬA LỖI ---

        if session.get('user_role') == 'admin':
            return
            
        from .config import MAINTENANCE_CONFIG_PATH
        maintenance_config = {}
        if os.path.exists(MAINTENANCE_CONFIG_PATH):
            try:
                with open(MAINTENANCE_CONFIG_PATH, 'r') as f:
                    maintenance_config = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                logger.error(f"Lỗi khi đọc file cấu hình bảo trì: {e}")
        
        is_active = maintenance_config.get('is_active', False)
        end_timestamp = maintenance_config.get('end_timestamp', 0)

        if is_active and time.time() < end_timestamp:
            return redirect(url_for('main.maintenance_page'))

    @app.before_request
    def log_request_info():
        logger.debug(f"REQUEST_DEBUG: Path: {request.path}, Endpoint: {request.endpoint}")

    from .routes.auth import auth_bp
    from .routes.flashcard import flashcard_bp
    from .routes.admin import admin_bp
    from .routes.api import api_bp
    from .routes.quiz import quiz_bp
    from .routes.main import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(flashcard_bp, url_prefix='/flashcard')
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(main_bp)

    logger.info("Ứng dụng Flask đã được khởi tạo và cấu hình với các route đã tách.")
    return app
