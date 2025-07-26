# web-app/database_install.py
import os
import sys
import logging
# BẮT ĐẦU THAY ĐỔI: Thêm thư viện mã hóa
from werkzeug.security import generate_password_hash
# KẾT THÚC THAY ĐỔI

# --- Thiết lập môi trường ---
logging.basicConfig(
    level=logging.INFO,
    format='[DB_INSTALLER] %(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("Đang khởi động kịch bản cài đặt cơ sở dữ liệu...")

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
    3. Tạo một tài khoản quản trị viên (admin) mặc định với mật khẩu đã được mã hóa.
    """
    try:
        from web_app import create_app, db
        from web_app.models import User
        from web_app.config import DATABASE_PATH

        if os.path.exists(DATABASE_PATH):
            logger.warning(f"Phát hiện file database cũ tại: {DATABASE_PATH}. File này sẽ bị xóa.")
            try:
                os.remove(DATABASE_PATH)
                logger.info("Đã xóa file database cũ thành công.")
            except OSError as e:
                logger.critical(f"LỖI: Không thể xóa file database cũ. Lỗi: {e}", exc_info=True)
                return

        app = create_app()
        with app.app_context():
            logger.info(f"Đang kết nối tới database tại: {app.config['SQLALCHEMY_DATABASE_URI']}")

            db_dir = os.path.dirname(DATABASE_PATH)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
                logger.info(f"Đã tạo thư mục database: {db_dir}")

            logger.info("Đang tạo tất cả các bảng trong database...")
            db.create_all()
            logger.info("Tạo bảng thành công.")

            if User.query.filter_by(username='admin').first():
                logger.warning("Tài khoản 'admin' đã tồn tại. Bỏ qua bước tạo tài khoản mặc định.")
            else:
                logger.info("Đang tạo tài khoản quản trị viên mặc định...")
                # BẮT ĐẦU THAY ĐỔI: Mã hóa mật khẩu mặc định
                hashed_password = generate_password_hash('admin')
                admin_user = User(
                    username='admin',
                    password=hashed_password,  # Lưu mật khẩu đã được mã hóa
                    user_role='admin',
                    daily_new_limit=999,
                    timezone_offset=7
                )
                # KẾT THÚC THAY ĐỔI
                db.session.add(admin_user)
                db.session.commit()
                logger.info("Tạo tài khoản admin mặc định thành công!")
                logger.info("-> Tên đăng nhập: admin")
                logger.info("-> Mật khẩu: admin")
                logger.info("Vui lòng đổi mật khẩu sau khi đăng nhập lần đầu tiên.")

            logger.info("Quá trình cài đặt cơ sở dữ liệu đã hoàn tất!")

    except ImportError as e:
        logger.critical(f"LỖI IMPORT: Không thể import các thành phần từ 'web_app'. Lỗi: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"Đã xảy ra lỗi không mong muốn trong quá trình cài đặt: {e}", exc_info=True)

if __name__ == '__main__':
    confirm = input("BẠN CÓ CHẮC CHẮN MUỐN CÀI ĐẶT LẠI DATABASE KHÔNG? TOÀN BỘ DỮ LIỆU HIỆN TẠI SẼ BỊ XÓA. (yes/no): ")
    if confirm.lower() == 'yes':
        install_database()
    else:
        logger.info("Hủy bỏ thao tác cài đặt.")
