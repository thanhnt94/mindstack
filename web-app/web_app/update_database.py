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

        # Lấy danh sách tất cả các bảng trong DB
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        # Xóa các bảng quiz cũ nếu tồn tại
        if 'UserQuizAnswers' in tables:
            cursor.execute("DROP TABLE UserQuizAnswers")
            logger.info("Đã xóa bảng cũ: UserQuizAnswers.")
        if 'QuizAttempts' in tables:
            cursor.execute("DROP TABLE QuizAttempts")
            logger.info("Đã xóa bảng cũ: QuizAttempts.")

        # Lấy danh sách các cột của bảng Users
        cursor.execute("PRAGMA table_info(Users)")
        users_columns = [row[1] for row in cursor.fetchall()]
        
        # Lấy danh sách các cột của bảng ScoreLogs
        cursor.execute("PRAGMA table_info(ScoreLogs)")
        scorelogs_columns = [row[1] for row in cursor.fetchall()]

        # Nâng cấp bảng Users
        if 'current_question_set_id' not in users_columns:
            cursor.execute("ALTER TABLE Users ADD COLUMN current_question_set_id INTEGER")
            logger.info("Đã thêm cột 'current_question_set_id' vào bảng Users.")
        if 'current_quiz_mode' not in users_columns:
            cursor.execute(f"ALTER TABLE Users ADD COLUMN current_quiz_mode VARCHAR(50) DEFAULT '{DEFAULT_QUIZ_MODE}'")
            logger.info(f"Đã thêm cột 'current_quiz_mode' vào bảng Users với giá trị mặc định.")

        # Nâng cấp bảng ScoreLogs
        if 'source_type' not in scorelogs_columns:
            cursor.execute("ALTER TABLE ScoreLogs ADD COLUMN source_type VARCHAR(50)")
            cursor.execute("UPDATE ScoreLogs SET source_type = 'flashcard' WHERE source_type IS NULL")
            logger.info("Đã thêm và điền dữ liệu cho cột 'source_type' trong ScoreLogs.")

        # Nâng cấp bảng UserQuizProgress
        if 'UserQuizProgress' in tables:
            cursor.execute("PRAGMA table_info(UserQuizProgress)")
            progress_columns = [row[1] for row in cursor.fetchall()]
            if 'correct_streak' not in progress_columns:
                logger.info("Đang thêm cột 'correct_streak' vào bảng UserQuizProgress...")
                cursor.execute("ALTER TABLE UserQuizProgress ADD COLUMN correct_streak INTEGER DEFAULT 0 NOT NULL")
                logger.info("Đã thêm cột 'correct_streak'.")
            else:
                logger.warning("Cột 'correct_streak' đã tồn tại trong bảng UserQuizProgress.")
        
        # BẮT ĐẦU THÊM MỚI: Nâng cấp bảng QuizQuestions
        if 'QuizQuestions' in tables:
            cursor.execute("PRAGMA table_info(QuizQuestions)")
            quiz_question_columns = [row[1] for row in cursor.fetchall()]

            if 'passage_content' not in quiz_question_columns:
                logger.info("Đang thêm cột 'passage_content' vào bảng QuizQuestions...")
                cursor.execute("ALTER TABLE QuizQuestions ADD COLUMN passage_content TEXT")
                logger.info("Đã thêm cột 'passage_content'.")
            else:
                logger.warning("Cột 'passage_content' đã tồn tại trong bảng QuizQuestions.")

            if 'passage_group_id' not in quiz_question_columns:
                logger.info("Đang thêm cột 'passage_group_id' vào bảng QuizQuestions...")
                cursor.execute("ALTER TABLE QuizQuestions ADD COLUMN passage_group_id INTEGER")
                logger.info("Đã thêm cột 'passage_group_id'.")
            else:
                logger.warning("Cột 'passage_group_id' đã tồn tại trong bảng QuizQuestions.")

            if 'is_passage_main_question' not in quiz_question_columns:
                logger.info("Đang thêm cột 'is_passage_main_question' vào bảng QuizQuestions...")
                cursor.execute("ALTER TABLE QuizQuestions ADD COLUMN is_passage_main_question BOOLEAN DEFAULT 0 NOT NULL")
                logger.info("Đã thêm cột 'is_passage_main_question'.")
            else:
                logger.warning("Cột 'is_passage_main_question' đã tồn tại trong bảng QuizQuestions.")
        # KẾT THÚC THÊM MỚI

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
    migrate_existing_tables()
    create_new_tables()
    logger.info("Script cập nhật cơ sở dữ liệu đã hoàn tất.")
