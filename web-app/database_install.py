# web-app/database_install.py
import os
import sys
import logging

# --- Thiết lập môi trường ---
# Cấu hình logging để theo dõi quá trình cài đặt
logging.basicConfig(
    level=logging.INFO,
    format='[DB_INSTALLER] %(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("Đang khởi động kịch bản cài đặt cơ sở dữ liệu...")

# Thêm thư mục gốc của dự án vào sys.path để có thể import từ package 'web_app'
# Kịch bản này nằm trong thư mục 'web-app', cùng cấp với 'start_web_app.py'
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    logger.info(f"Đã thêm thư mục gốc dự án vào sys.path: {project_root}")

def install_database():
    """
    Mô tả:
    Thực hiện quá trình cài đặt lại cơ sở dữ liệu từ đầu.
    1. Xóa file database cũ (nếu có).
    2. Tạo lại toàn bộ cấu trúc bảng từ các model.
    3. Tạo một tài khoản quản trị viên (admin) mặc định.
    """
    try:
        # Import các thành phần cần thiết từ package web_app
        from web_app import create_app, db
        from web_app.models import User
        from web_app.config import DATABASE_PATH

        # --- Bước 1: Xóa file database cũ ---
        if os.path.exists(DATABASE_PATH):
            logger.warning(f"Phát hiện file database cũ tại: {DATABASE_PATH}. File này sẽ bị xóa.")
            try:
                os.remove(DATABASE_PATH)
                logger.info("Đã xóa file database cũ thành công.")
            except OSError as e:
                logger.critical(f"LỖI: Không thể xóa file database cũ. Vui lòng kiểm tra quyền truy cập. Lỗi: {e}", exc_info=True)
                return # Dừng kịch bản nếu không thể xóa file

        # --- Bước 2: Tạo lại cấu trúc và tài khoản admin ---
        # Tạo một ứng dụng Flask để có ngữ cảnh ứng dụng (application context)
        app = create_app()
        with app.app_context():
            logger.info(f"Đang kết nối tới database tại: {app.config['SQLALCHEMY_DATABASE_URI']}")

            # Đảm bảo thư mục chứa database tồn tại
            db_dir = os.path.dirname(DATABASE_PATH)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
                logger.info(f"Đã tạo thư mục database: {db_dir}")

            # Tạo tất cả các bảng dựa trên định nghĩa trong models.py
            logger.info("Đang tạo tất cả các bảng trong database...")
            db.create_all()
            logger.info("Tạo bảng thành công.")

            # Kiểm tra xem tài khoản admin đã tồn tại chưa (đề phòng)
            if User.query.filter_by(username='admin').first():
                logger.warning("Tài khoản 'admin' đã tồn tại. Bỏ qua bước tạo tài khoản mặc định.")
            else:
                # Tạo tài khoản admin mặc định
                logger.info("Đang tạo tài khoản quản trị viên mặc định...")
                admin_user = User(
                    username='admin',
                    password='admin',  # Mật khẩu được lưu trực tiếp
                    user_role='admin',
                    daily_new_limit=999, # Giới hạn cao cho admin
                    timezone_offset=7    # Múi giờ mặc định (Việt Nam)
                )
                db.session.add(admin_user)
                db.session.commit()
                logger.info("Tạo tài khoản admin mặc định thành công!")
                logger.info("-> Tên đăng nhập: admin")
                logger.info("-> Mật khẩu: admin")
                logger.info("Vui lòng đổi mật khẩu sau khi đăng nhập lần đầu tiên.")

            logger.info("Quá trình cài đặt cơ sở dữ liệu đã hoàn tất!")

    except ImportError as e:
        logger.critical(f"LỖI IMPORT: Không thể import các thành phần từ 'web_app'. Đảm bảo bạn chạy kịch bản này từ thư mục 'web-app'. Lỗi: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"Đã xảy ra lỗi không mong muốn trong quá trình cài đặt: {e}", exc_info=True)

# --- Chạy kịch bản ---
if __name__ == '__main__':
    # Hỏi người dùng xác nhận trước khi thực hiện
    confirm = input("BẠN CÓ CHẮC CHẮN MUỐN CÀI ĐẶT LẠI DATABASE KHÔNG? TOÀN BỘ DỮ LIỆU HIỆN TẠI SẼ BỊ XÓA. (yes/no): ")
    if confirm.lower() == 'yes':
        install_database()
    else:
        logger.info("Hủy bỏ thao tác cài đặt.")
