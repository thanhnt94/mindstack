# flashcard-web/web_app/__init__.py
from flask import Flask
from .db_instance import db
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Tải cấu hình từ file config.py
    app.config.from_pyfile('config.py')

    # Khởi tạo DB
    db.init_app(app)

    app.jinja_env.add_extension('jinja2.ext.do')

    # Đăng ký Jinja2 filter
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

    # Đăng ký các Blueprint
    from .routes.auth import auth_bp
    from .routes.flashcard import flashcard_bp
    from .routes.admin import admin_bp
    from .routes.api import api_bp
    from .routes.quiz import quiz_bp
    # --- BẮT ĐẦU THÊM MỚI ---
    from .routes.main import main_bp
    # --- KẾT THÚC THÊM MỚI ---

    app.register_blueprint(auth_bp)
    app.register_blueprint(flashcard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(quiz_bp) # url_prefix đã được định nghĩa trong file quiz.py
    # --- BẮT ĐẦU THÊM MỚI ---
    app.register_blueprint(main_bp)
    # --- KẾT THÚC THÊM MỚI ---

    logger.info("Ứng dụng Flask đã được khởi tạo và cấu hình với các route đã tách.")
    return app
