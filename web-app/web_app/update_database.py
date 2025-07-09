# flashcard/web-app/update_database.py
import os
import sys
import logging

# Thiết lập logging cơ bản cho script này
logging.basicConfig(
    level=logging.INFO,
    format='[DB_UPDATER] %(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("Đang khởi động script cập nhật cơ sở dữ liệu...")

# Lấy đường dẫn thư mục gốc của dự án (nơi file start_web_app.py và web_app nằm)
# Giả sử script này nằm trong thư mục web-app
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Thêm thư mục gốc của dự án vào sys.path để có thể import web_app
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    logger.info(f"Đã thêm thư mục gốc dự án vào sys.path: {project_root}")

try:
    # Import create_app và db từ package web_app
    from web_app import create_app, db
    logger.info("Đã import create_app và db thành công.")

    # Tạo ứng dụng Flask
    app = create_app()
    logger.info("Ứng dụng Flask đã được khởi tạo.")

    # Đẩy ngữ cảnh ứng dụng để có thể tương tác với database
    with app.app_context():
        logger.info(f"Đang kết nối tới database: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        # Kiểm tra xem database file có tồn tại không
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        if os.path.exists(db_path):
            logger.warning(f"File database '{db_path}' đã tồn tại. db.create_all() sẽ không sửa đổi các bảng hiện có, chỉ tạo bảng mới nếu thiếu.")
            logger.warning("Nếu bạn muốn áp dụng các thay đổi cấu trúc cho các bảng hiện có (ví dụ: thay đổi NOT NULL), bạn cần XÓA file database này thủ công TRƯỚC KHI chạy script.")
        else:
            logger.info(f"File database '{db_path}' chưa tồn tại. Sẽ được tạo mới.")

        # Tạo tất cả các bảng được định nghĩa trong models.py
        # Nếu bảng đã tồn tại, nó sẽ không làm gì cả.
        # Nếu bảng chưa tồn tại, nó sẽ tạo bảng mới.
        db.create_all()
        logger.info("Đã chạy db.create_all() thành công.")
        logger.info("Cấu trúc database đã được cập nhật (hoặc tạo mới).")

except ImportError as e:
    logger.error(f"Lỗi Import: Không thể tìm thấy module. Vui lòng kiểm tra cấu trúc thư mục của bạn. Lỗi: {e}", exc_info=True)
    logger.error(f"Đảm bảo thư mục 'web_app' nằm trong '{project_root}' và có __init__.py.")
except Exception as e:
    logger.critical(f"Lỗi nghiêm trọng khi chạy script cập nhật database: {e}", exc_info=True)

logger.info("Script cập nhật cơ sở dữ liệu đã hoàn tất.")
