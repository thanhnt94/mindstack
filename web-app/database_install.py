# web-app/database_install.py
import os
import sys
import logging
from werkzeug.security import generate_password_hash

# --- Thiết lập môi trường ---
# Cấu hình logging để cung cấp thông tin chi tiết trong quá trình thực thi
logging.basicConfig(
    level=logging.INFO,
    format='[DB_INSTALLER] %(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("Đang khởi động kịch bản cài đặt cơ sở dữ liệu...")

# Thêm thư mục gốc của dự án vào sys.path để đảm bảo import hoạt động chính xác
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    logger.info(f"Đã thêm thư mục gốc dự án vào sys.path: {project_root}")

def install_database():
    """
    Thực hiện quá trình cài đặt lại cơ sở dữ liệu từ đầu.
    1. Xóa file database cũ (nếu có) để đảm bảo môi trường sạch.
    2. Gọi `db.create_all()` để tạo lại toàn bộ cấu trúc bảng từ các model trong `web_app/models.py`.
       - QUAN TRỌNG: Quá trình này sẽ tự động thêm các cột mới (ví dụ: `ai_prompt`)
         vào các bảng tương ứng vì chúng đã được định nghĩa trong model.
    3. Tạo một tài khoản quản trị viên (admin) mặc định nếu chưa tồn tại.
    """
    try:
        # Import các thành phần cần thiết từ ứng dụng
        from web_app import create_app, db
        # --- BẮT ĐẦU SỬA LỖI: Sử dụng tên Model chính xác ---
        from web_app.models import User, VocabularySet, Flashcard, QuestionSet, QuizQuestion
        # --- KẾT THÚC SỬA LỖI ---
        from web_app.config import DATABASE_PATH

        # Kiểm tra và xóa file database cũ
        if os.path.exists(DATABASE_PATH):
            logger.warning(f"Phát hiện file database cũ tại: {DATABASE_PATH}. File này sẽ bị xóa.")
            try:
                os.remove(DATABASE_PATH)
                logger.info("Đã xóa file database cũ thành công.")
            except OSError as e:
                logger.critical(f"LỖI: Không thể xóa file database cũ. Lỗi: {e}", exc_info=True)
                return

        # Tạo một instance của ứng dụng Flask để có app_context
        app = create_app()
        with app.app_context():
            logger.info(f"Đang kết nối tới database tại: {app.config['SQLALCHEMY_DATABASE_URI']}")

            # Đảm bảo thư mục chứa database tồn tại
            db_dir = os.path.dirname(DATABASE_PATH)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
                logger.info(f"Đã tạo thư mục database: {db_dir}")

            logger.info("Đang tạo tất cả các bảng trong database dựa trên 'models.py'...")
            # Lệnh này sẽ đọc tất cả các class Model và tạo bảng tương ứng,
            # bao gồm cả các cột mới sẽ được thêm vào.
            db.create_all()
            logger.info("Tạo bảng thành công. Các cột mới (nếu có) sẽ được thêm vào.")

            # Kiểm tra và tạo tài khoản admin mặc định
            if User.query.filter_by(username='admin').first():
                logger.warning("Tài khoản 'admin' đã tồn tại. Bỏ qua bước tạo tài khoản mặc định.")
            else:
                logger.info("Đang tạo tài khoản quản trị viên mặc định...")
                hashed_password = generate_password_hash('admin')
                admin_user = User(
                    username='admin',
                    password=hashed_password,
                    user_role='admin',
                    daily_new_limit=999,
                    timezone_offset=7
                )
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
    # Yêu cầu xác nhận từ người dùng trước khi thực hiện hành động nguy hiểm
    confirm = input("BẠN CÓ CHẮC CHẮN MUỐN CÀI ĐẶT LẠI DATABASE KHÔNG? TOÀN BỘ DỮ LIỆU HIỆN TẠI SẼ BỊ XÓA. (yes/no): ")
    if confirm.lower() == 'yes':
        install_database()
    else:
        logger.info("Hủy bỏ thao tác cài đặt.")
