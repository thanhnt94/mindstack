# flashcard/web-app/update_database.py
import os
import sys
import logging
import sqlite3

# --- Thiết lập môi trường ---
logging.basicConfig(
    level=logging.INFO,
    format='[DB_UPDATER] %(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("Đang khởi động script cập nhật cơ sở dữ liệu...")

# Thêm thư mục gốc của dự án vào sys.path để có thể import web_app
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    logger.info(f"Đã thêm thư mục gốc dự án vào sys.path: {project_root}")

# --- Hàm nâng cấp các bảng cũ ---
def migrate_existing_tables():
    """
    Mô tả: Sử dụng kết nối SQLite trực tiếp để thêm các cột mới vào các bảng đã tồn tại
    và dọn dẹp các bảng cũ không còn sử dụng. Chạy an toàn nhiều lần.
    """
    try:
        from web_app.config import DATABASE_PATH, DEFAULT_QUIZ_MODE
        if not os.path.exists(DATABASE_PATH):
            logger.warning(f"File database không tìm thấy tại: {DATABASE_PATH}. Bỏ qua bước nâng cấp.")
            return

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        logger.info("Đã kết nối tới database để thực hiện nâng cấp.")

        # Xóa các bảng quiz cũ nếu tồn tại
        logger.info("Đang kiểm tra và xóa các bảng quiz cũ không còn sử dụng (QuizAttempts, UserQuizAnswers)...")
        cursor.execute("DROP TABLE IF EXISTS UserQuizAnswers")
        cursor.execute("DROP TABLE IF EXISTS QuizAttempts")
        logger.info("Đã xóa các bảng quiz cũ thành công (nếu có).")

        # Lấy danh sách các cột của bảng Users
        cursor.execute("PRAGMA table_info(Users)")
        users_columns = [row[1] for row in cursor.fetchall()]
        
        # Lấy danh sách các cột của bảng ScoreLogs
        cursor.execute("PRAGMA table_info(ScoreLogs)")
        scorelogs_columns = [row[1] for row in cursor.fetchall()]

        # Nâng cấp bảng Users
        if 'current_question_set_id' not in users_columns:
            logger.info("Đang thêm cột 'current_question_set_id' vào bảng Users...")
            cursor.execute("ALTER TABLE Users ADD COLUMN current_question_set_id INTEGER")
            logger.info("Đã thêm cột 'current_question_set_id'.")
        else:
            logger.warning("Cột 'current_question_set_id' đã tồn tại trong bảng Users.")

        if 'current_quiz_mode' not in users_columns:
            logger.info("Đang thêm cột 'current_quiz_mode' vào bảng Users...")
            cursor.execute(f"ALTER TABLE Users ADD COLUMN current_quiz_mode VARCHAR(50) DEFAULT '{DEFAULT_QUIZ_MODE}'")
            logger.info(f"Đã thêm cột 'current_quiz_mode' với giá trị mặc định là '{DEFAULT_QUIZ_MODE}'.")
        else:
            logger.warning("Cột 'current_quiz_mode' đã tồn tại trong bảng Users.")

        # Nâng cấp bảng ScoreLogs
        if 'source_type' not in scorelogs_columns:
            logger.info("Đang thêm cột 'source_type' vào bảng ScoreLogs...")
            cursor.execute("ALTER TABLE ScoreLogs ADD COLUMN source_type VARCHAR(50)")
            logger.info("Đã thêm cột 'source_type'.")
            
            logger.info("Đang điền giá trị 'flashcard' cho các bản ghi điểm cũ...")
            cursor.execute("UPDATE ScoreLogs SET source_type = 'flashcard' WHERE source_type IS NULL")
            logger.info(f"{cursor.rowcount} dòng đã được cập nhật với source_type = 'flashcard'.")
        else:
            logger.warning("Cột 'source_type' đã tồn tại trong bảng ScoreLogs.")

        conn.commit()
    except Exception as e:
        logger.error(f"Lỗi khi nâng cấp các bảng cũ: {e}", exc_info=True)
        if 'conn' in locals() and conn:
            conn.rollback()
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            logger.info("Đã đóng kết nối nâng cấp database.")

# --- Hàm tạo các bảng mới ---
def create_new_tables():
    """
    Mô tả: Sử dụng Flask-SQLAlchemy để tạo tất cả các bảng được định nghĩa trong models.py.
    Hàm này sẽ không sửa đổi các bảng đã tồn tại.
    """
    try:
        from web_app import create_app, db
        app = create_app()
        with app.app_context():
            logger.info(f"Đang kết nối tới database qua SQLAlchemy: {app.config['SQLALCHEMY_DATABASE_URI']}")
            logger.info("Đang chạy db.create_all() để tạo các bảng mới (nếu có)...")
            db.create_all()
            logger.info("db.create_all() đã hoàn tất.")
    except Exception as e:
        logger.error(f"Lỗi khi tạo bảng mới qua SQLAlchemy: {e}", exc_info=True)

# --- Chạy script ---
if __name__ == '__main__':
    # Bước 1: Nâng cấp và dọn dẹp các bảng đã có bằng kết nối trực tiếp
    migrate_existing_tables()
    
    # Bước 2: Tạo các bảng mới bằng SQLAlchemy
    create_new_tables()
    
    logger.info("Script cập nhật cơ sở dữ liệu đã hoàn tất.")
