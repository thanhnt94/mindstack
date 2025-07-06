# flashcard-web/web_app/__init__.py
from flask import Flask
from .db_instance import db  # Import đối tượng db từ file db_instance.py
import logging
from datetime import datetime, timedelta, timezone # Import các module cần thiết cho filter

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Tải cấu hình từ file config.py trong cùng thư mục
    app.config.from_pyfile('config.py')

    # Gắn Flask app với đối tượng db (đã được tạo global)
    db.init_app(app)

    # Thêm log để hiển thị đường dẫn cơ sở dữ liệu đang kết nối
    logger.info(f"Database connected at: {app.config['SQLALCHEMY_DATABASE_URI']}")

    # Đăng ký Jinja2 filter để định dạng Unix timestamp
    @app.template_filter('format_unix_timestamp')
    def format_unix_timestamp_filter(timestamp):
        if timestamp is None:
            return "N/A"
        try:
            # Lấy múi giờ mặc định từ config
            # Để đảm bảo tính độc lập, chúng ta sẽ import config ở đây
            # hoặc giả định một offset mặc định nếu config không thể truy cập
            from .config import DEFAULT_TIMEZONE_OFFSET
            tz = timezone(timedelta(hours=DEFAULT_TIMEZONE_OFFSET))
            dt_object = datetime.fromtimestamp(timestamp, tz)
            return dt_object.strftime("%H:%M %d/%m/%Y")
        except (TypeError, ValueError, OSError) as e:
            logger.error(f"Lỗi khi định dạng timestamp {timestamp}: {e}", exc_info=True)
            return "Invalid Date"

    # Đăng ký Blueprint route (nên làm sau khi init_app để tránh lỗi)
    from . import routes
    app.register_blueprint(routes.main_bp)

    logger.info("Ứng dụng Flask đã được khởi tạo và cấu hình.")
    return app

