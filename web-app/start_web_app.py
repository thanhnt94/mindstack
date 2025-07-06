# flashcard-web/start_web_app.py
import sys
import os
import logging
from flask import session # Import session để sử dụng SECRET_KEY

# CHỈNH SỬA: Thay đổi cấp độ logging từ INFO thành DEBUG để xem các log chi tiết hơn
logging.basicConfig(
    level=logging.DEBUG, # Đã thay đổi từ logging.INFO thành logging.DEBUG
    format='[LAUNCHER_LOG] %(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("Đang khởi tạo Web Application Launcher...")

# Lấy đường dẫn thư mục gốc của dự án (nơi file start_web_app.py này đang nằm)
project_root = os.path.abspath(os.path.dirname(__file__))

# Thêm thư mục gốc vào sys.path.
# Điều này giúp Python tìm thấy 'web_app' như một package cấp cao nhất
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    logger.info(f"Đã thêm thư mục gốc dự án vào sys.path: {project_root}")

try:
    # 1. Import create_app và db từ package 'web_app'.
    from web_app import create_app, db
    logger.info("Đã import create_app và db (đối tượng db global từ web_app.__init__).")

    # 2. Tạo ứng dụng Flask bằng factory 'create_app()'.
    app = create_app()
    logger.info("Ứng dụng Flask đã được khởi tạo và cấu hình (db đã được liên kết thông qua create_app).")

    # 3. ĐẨY NGỮ CẢNH ỨNG DỤNG (Application Context) một cách TƯỜNG MINH.
    app_ctx = app.app_context()
    app_ctx.push()
    logger.info("Ngữ cảnh ứng dụng Flask đã được đẩy thủ công.")

    try:
        # 4. Import Models *SAU KHI* ngữ cảnh ứng dụng đã được đẩy.
        from web_app.models import User, VocabularySet, Flashcard, UserFlashcardProgress, FlashcardNote
        logger.info("Đã import thành công các Model (sau khi ngữ cảnh được đẩy).")

        # Các kiểm tra database ban đầu
        logger.info("Đang thực hiện kiểm tra database ban đầu.")
        try:
            inspector = db.inspect(db.engine)
            if not inspector.has_table("Users"):
                logger.critical("Bảng 'Users' KHÔNG TỒN TẠI trong database. Vui lòng đảm bảo database đã được khởi tạo.")
                sys.exit(1)
            logger.info("Kết nối database thành công và bảng 'Users' tồn tại.")

            # Flask cần SECRET_KEY để mã hóa session
            app.secret_key = app.config.get('SECRET_KEY', 'default_fallback_secret_key_if_not_set')
            logger.info("Đã thiết lập SECRET_KEY cho ứng dụng Flask.")

            # LOẠI BỎ LOGIC TÌM KIẾM VÀ THIẾT LẬP SESSION CHO ADMIN MẶC ĐỊNH
            # Người dùng sẽ cần đăng nhập thủ công qua trang /login
            logger.info("Logic đăng nhập admin mặc định đã được loại bỏ. Người dùng sẽ được chuyển hướng đến trang đăng nhập.")

        except Exception as e:
            logger.critical(f"LỖI NGHIÊM TRỌNG KHI KIỂM TRA DATABASE LÚC KHỞI ĐỘNG: {e}", exc_info=True)
            logger.critical("Đảm bảo đường dẫn DATABASE_PATH là chính xác và file database tồn tại và không bị khóa.")
            sys.exit(1)
        
        logger.info("Các kiểm tra ban đầu đã hoàn tất. Chuẩn bị chạy máy chủ Flask.")

    finally:
        # Đảm bảo ngữ cảnh ứng dụng được gỡ bỏ ngay cả khi có lỗi xảy ra
        app_ctx.pop()
        logger.info("Ngữ cảnh ứng dụng Flask đã được gỡ bỏ thủ công.")

    # 5. Khởi chạy ứng dụng Flask
    if __name__ == '__main__':
        app.run(host='0.0.0.0', port=5000, debug=True)

except ImportError as e:
    logger.critical(f"Lỗi Import: Không thể tìm thấy module. Vui lòng kiểm tra cấu trúc thư mục của bạn. Lỗi: {e}")
    logger.critical(f"Đảm bảo 'web_app' là một thư mục con của '{project_root}' và có __init__.py.")
    sys.exit(1)
except Exception as e:
    logger.critical(f"Lỗi không mong muốn khi khởi động ứng dụng: {e}", exc_info=True)
    sys.exit(1)
