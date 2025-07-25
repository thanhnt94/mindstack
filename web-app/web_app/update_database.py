# flashcard/web-app/update_database.py
import os
import sys
import logging
import sqlite3 # Vẫn giữ để có thể kiểm tra file database và thực hiện DROP TABLE

# --- Thiết lập môi trường ---
logging.basicConfig(
    level=logging.INFO,
    format='[DB_UPDATER] %(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("Đang khởi động script cập nhật cơ sở dữ liệu...")

# BẮT ĐẦU SỬA LỖI: Cập nhật cách xác định web_app_container_dir
# project_root là thư mục gốc của toàn bộ dự án (ví dụ: flashcard/)
# Script update_database.py của bạn nằm trong web-app/web_app/,
# nên để tìm project_root, chúng ta cần lùi 2 cấp thư mục.
current_script_path = os.path.abspath(__file__)
# Lùi 2 cấp thư mục từ vị trí của update_database.py để đến thư mục gốc của project
# C:\Users\thanh\OneDrive\CodeHub\Flashcard\flashcard\web-app\web_app\update_database.py
# -> C:\Users\thanh\OneDrive\CodeHub\Flashcard\flashcard\web-app\web_app (dirname)
# -> C:\Users\thanh\OneDrive\CodeHub\Flashcard\flashcard\web-app (dirname) <- Đây là web_app_container_dir
# -> C:\Users\thanh\OneDrive\CodeHub\Flashcard\flashcard (dirname) <- Đây là project_root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_script_path)))

# web_app_container_dir là thư mục chứa gói 'web_app' (tức là thư mục 'web-app' ngang hàng với 'migrations')
# Dựa trên cấu trúc bạn cung cấp: C:\Users\thanh\OneDrive\CodeHub\Flashcard\flashcard\web-app
web_app_container_dir = os.path.join(project_root, 'web-app')


if web_app_container_dir not in sys.path:
    sys.path.insert(0, web_app_container_dir)
    logger.info(f"Đã thêm thư mục chứa gói 'web_app' vào sys.path: {web_app_container_dir}")
# KẾT THÚC SỬA LỖI

# --- Hàm tạo/cập nhật các bảng ---
def create_or_update_tables_with_sqlite_direct_drops():
    """
    Mô tả: Sử dụng Flask-SQLAlchemy để tạo hoặc cập nhật tất cả các bảng.
           Đồng thời, thực hiện xóa các bảng Quiz cũ trực tiếp bằng SQLite
           để đảm bảo schema mới được áp dụng chính xác cho các bảng này
           mà không cần migration phức tạp, chấp nhận mất dữ liệu Quiz.
           Các bảng Flashcard sẽ được bảo toàn dữ liệu.
    """
    try:
        from web_app import create_app, db
        from web_app.config import DATABASE_PATH, DEFAULT_QUIZ_MODE # Import DEFAULT_QUIZ_MODE

        app = create_app()
        with app.app_context():
            logger.info(f"Đang kết nối tới database qua SQLAlchemy: {app.config['SQLALCHEMY_DATABASE_URI']}")
            
            # Đảm bảo thư mục database tồn tại
            if not os.path.exists(os.path.dirname(DATABASE_PATH)):
                os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
                logger.info(f"Đã tạo thư mục database: {os.path.dirname(DATABASE_PATH)}")

            conn = None
            try:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                
                # Xóa các bảng Quiz cũ để đảm bảo schema mới
                logger.info("Đang xóa các bảng cũ (nếu tồn tại) để cập nhật schema mới...")
                
                # Thứ tự xóa quan trọng do khóa ngoại
                tables_to_drop = [
                    'Feedbacks', # THÊM MỚI: Xóa bảng feedback cũ nếu có để tạo lại
                    'QuizQuestionNotes',
                    'UserQuizProgress',
                    'QuizQuestions',
                    'QuizPassages', # Bảng mới, xóa nếu có từ lần chạy thử nghiệm trước
                    'QuestionSets'
                ]
                
                for table_name in tables_to_drop:
                    try:
                        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                        logger.info(f"Đã xóa bảng: {table_name}")
                    except sqlite3.OperationalError as e:
                        logger.warning(f"Không thể xóa bảng {table_name}: {e}. Có thể do khóa ngoại chưa được giải quyết hoặc bảng không tồn tại.")
                
                conn.commit()
                logger.info("Hoàn tất việc xóa các bảng cũ.")

                logger.info("Đang chạy db.create_all() để tạo tất cả các bảng mới (bao gồm cả các bảng đã xóa)...")
                db.create_all() # Tạo lại tất cả các bảng theo models.py
                logger.info("db.create_all() đã hoàn tất.")

                # Nâng cấp các cột cũ trong các bảng Flashcard/User
                logger.info("Đang kiểm tra và nâng cấp các cột cũ trong bảng Users và ScoreLogs (nếu cần)...")

                # Nâng cấp bảng Users
                cursor.execute("PRAGMA table_info(Users)")
                users_columns = [row[1] for row in cursor.fetchall()]
                if 'current_question_set_id' not in users_columns:
                    cursor.execute("ALTER TABLE Users ADD COLUMN current_question_set_id INTEGER")
                    logger.info("Đã thêm cột 'current_question_set_id' vào bảng Users.")
                if 'current_quiz_mode' not in users_columns:
                    cursor.execute(f"ALTER TABLE Users ADD COLUMN current_quiz_mode VARCHAR(50) DEFAULT '{DEFAULT_QUIZ_MODE}'")
                    logger.info(f"Đã thêm cột 'current_quiz_mode' vào bảng Users với giá trị mặc định.")
                
                # Nâng cấp bảng ScoreLogs
                cursor.execute("PRAGMA table_info(ScoreLogs)")
                scorelogs_columns = [row[1] for row in cursor.fetchall()]
                if 'source_type' not in scorelogs_columns:
                    cursor.execute("ALTER TABLE ScoreLogs ADD COLUMN source_type VARCHAR(50)")
                    cursor.execute("UPDATE ScoreLogs SET source_type = 'flashcard' WHERE source_type IS NULL")
                    logger.info("Đã thêm và điền dữ liệu cho cột 'source_type' trong ScoreLogs.")

                # Nâng cấp bảng UserFlashcardProgress (nếu cần cột correct_streak)
                cursor.execute("PRAGMA table_info(UserFlashcardProgress)")
                progress_columns = [row[1] for row in cursor.fetchall()]
                if 'correct_streak' not in progress_columns:
                    logger.info("Đang thêm cột 'correct_streak' vào bảng UserFlashcardProgress...")
                    cursor.execute("ALTER TABLE UserFlashcardProgress ADD COLUMN correct_streak INTEGER DEFAULT 0 NOT NULL")
                    logger.info("Đã thêm cột 'correct_streak'.")

                conn.commit()
                logger.info("Nâng cấp các cột cũ đã hoàn tất.")

            except sqlite3.Error as e:
                logger.error(f"Lỗi SQLite trong quá trình cập nhật database: {e}", exc_info=True)
                if conn:
                    conn.rollback() # Rollback nếu có lỗi trong giao dịch SQLite
            except Exception as e:
                logger.error(f"Đã xảy ra lỗi không mong muốn khi cập nhật database: {e}", exc_info=True)
            finally:
                if conn:
                    conn.close()
                    logger.info("Đã đóng kết nối database.")

    except Exception as e:
        logger.error(f"Lỗi khi khởi tạo ứng dụng hoặc truy cập DB: {e}", exc_info=True)

# --- Chạy script ---
if __name__ == '__main__':
    create_or_update_tables_with_sqlite_direct_drops()
    logger.info("Script cập nhật cơ sở dữ liệu đã hoàn tất.")
