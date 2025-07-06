# File: flashcard-telegram-bot/database/database_update.py
"""
Script cập nhật schema cơ sở dữ liệu.
Chức năng chính: 
- Thêm cột 'image_path' vào bảng 'FlashcardNotes' nếu chưa tồn tại.
- Thêm các cột 'notification_target_set_id', 'enable_morning_brief', 
  'last_morning_brief_sent_date' vào bảng 'Users' nếu chưa tồn tại.
(Sửa lần 1: Thêm nhiều log chi tiết để debug)
(Sửa lần 2: Đổi tên hàm, thêm logic cập nhật bảng Users với các cột mới cho thông báo)
"""
import sqlite3
import logging
import os
import sys

# --- Thiết lập đường dẫn để import config.py ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_BOT = os.path.dirname(CURRENT_DIR) # Giả định config.py nằm ở thư mục gốc của bot
sys.path.insert(0, PROJECT_ROOT_BOT)

FLASHCARD_DB_PATH_FROM_CONFIG = None
try:
    from config import FLASHCARD_DB_PATH
    FLASHCARD_DB_PATH_FROM_CONFIG = FLASHCARD_DB_PATH
except ImportError:
    logging.error(
        "Lỗi nghiêm trọng: Không thể import FLASHCARD_DB_PATH từ config.py."
    )
    # Fallback path, giả định database nằm cùng cấp với thư mục chứa script này nếu config lỗi
    FALLBACK_DB_DIR = os.path.join(PROJECT_ROOT_BOT, "database") # Thư mục database
    os.makedirs(FALLBACK_DB_DIR, exist_ok=True) # Đảm bảo thư mục database tồn tại
    FLASHCARD_DB_PATH_FROM_CONFIG = os.path.join(FALLBACK_DB_DIR, 'flashcard.db') 
    logging.warning(
        f"Sử dụng đường dẫn DB fallback: '{FLASHCARD_DB_PATH_FROM_CONFIG}'. "
        "VUI LÒNG KIỂM TRA LẠI CẤU TRÚC DỰ ÁN VÀ IMPORT."
    )
# --- Kết thúc thiết lập đường dẫn ---

logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def check_column_exists(cursor, table_name, column_name):
    logger.debug(f"Kiểm tra sự tồn tại của cột '{column_name}' trong bảng '{table_name}'...")
    query_table_info = f"PRAGMA table_info('{table_name}')"
    logger.debug(f"Executing: {query_table_info}")
    cursor.execute(query_table_info)
    columns_info = cursor.fetchall()
    logger.debug(f"Thông tin các cột của bảng '{table_name}': {columns_info}")
    columns = [info[1] for info in columns_info] # info[1] là tên cột
    exists = column_name in columns
    if exists:
        logger.debug(f"Cột '{column_name}' ĐÃ tồn tại trong bảng '{table_name}'.")
    else:
        logger.debug(f"Cột '{column_name}' CHƯA tồn tại trong bảng '{table_name}'.")
    return exists

def add_column_if_not_exists(cursor, table_name, column_name, column_definition):
    """Thêm một cột vào bảng nếu nó chưa tồn tại."""
    if not check_column_exists(cursor, table_name, column_name):
        logger.info(f"Cột '{column_name}' chưa tồn tại trong bảng '{table_name}'. Đang tiến hành thêm...")
        alter_query = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        logger.debug(f"Thực thi câu lệnh ALTER TABLE: {alter_query}")
        try:
            cursor.execute(alter_query)
            logger.info(f"Đã thêm thành công cột '{column_name}' ({column_definition}) vào bảng '{table_name}'.")
            # Kiểm tra lại sau khi thêm
            if check_column_exists(cursor, table_name, column_name):
                 logger.info(f"Xác nhận: Cột '{column_name}' đã tồn tại sau khi thêm.")
            else:
                 logger.error(f"LỖI NGHIÊM TRỌNG: Cột '{column_name}' vẫn không tồn tại sau khi cố gắng thêm!")
        except sqlite3.Error as e_alter:
            logger.error(f"Lỗi SQLite khi thêm cột '{column_name}' vào bảng '{table_name}': {e_alter}", exc_info=True)
            raise # Ném lại lỗi để rollback nếu cần
    else:
        logger.info(f"Cột '{column_name}' đã tồn tại trong bảng '{table_name}'. Không cần thực hiện thêm.")


def update_database_schema_if_needed():
    """
    Kiểm tra và cập nhật schema của các bảng nếu cần.
    Sửa lần 2: Đổi tên hàm và thêm logic cập nhật bảng Users.
    """
    conn = None
    db_path_to_connect = FLASHCARD_DB_PATH_FROM_CONFIG

    if not os.path.isabs(db_path_to_connect):
        # Nếu đường dẫn không tuyệt đối và không chứa thư mục, giả định nó nằm trong thư mục gốc của bot
        if not os.path.dirname(db_path_to_connect): # Ví dụ: "flashcard.db"
            db_path_to_connect = os.path.join(PROJECT_ROOT_BOT, db_path_to_connect)
        # Nếu là đường dẫn tương đối có thư mục, ví dụ "database/flashcard.db"
        # thì os.path.abspath sẽ xử lý đúng dựa trên thư mục làm việc hiện tại.
        # Tuy nhiên, để chắc chắn, chúng ta có thể join với PROJECT_ROOT_BOT nếu cần.
        # Hiện tại, để đơn giản, giả định os.path.abspath hoạt động đúng.

    abs_db_path = os.path.abspath(db_path_to_connect)
    logger.info(f"Bắt đầu quá trình cập nhật cơ sở dữ liệu.")
    logger.info(f"Đường dẫn DB được cấu hình (từ config hoặc fallback): '{FLASHCARD_DB_PATH_FROM_CONFIG}'")
    logger.info(f"Đường dẫn tuyệt đối sẽ kết nối đến: '{abs_db_path}'")
    logger.info(f"Script đang chạy từ: '{CURRENT_DIR}'")
    logger.info(f"Thư mục gốc của bot được xác định là: '{PROJECT_ROOT_BOT}'")

    if not os.path.exists(abs_db_path):
        logger.error(f"LỖI: File cơ sở dữ liệu KHÔNG TỒN TẠI tại đường dẫn: '{abs_db_path}'. Script không thể tiếp tục.")
        logger.info("Vui lòng chạy bot lần đầu để khởi tạo database, hoặc kiểm tra lại đường dẫn FLASHCARD_DB_PATH trong config.py.")
        return
    else:
        logger.info(f"XÁC NHẬN: File cơ sở dữ liệu tồn tại tại: '{abs_db_path}'.")

    try:
        logger.debug(f"Đang thử kết nối tới DB: '{abs_db_path}'...")
        conn = sqlite3.connect(abs_db_path)
        cursor = conn.cursor()
        logger.info(f"Kết nối tới DB '{abs_db_path}' thành công.")

        # Bắt đầu transaction
        conn.execute("BEGIN TRANSACTION;")
        logger.debug("Bắt đầu TRANSACTION.")

        # 1. Cập nhật bảng FlashcardNotes
        logger.info("--- Cập nhật bảng FlashcardNotes ---")
        table_flashcard_notes = "FlashcardNotes"
        column_image_path = "image_path"
        definition_image_path = "TEXT" # Không có DEFAULT
        add_column_if_not_exists(cursor, table_flashcard_notes, column_image_path, definition_image_path)

        # 2. Cập nhật bảng Users
        logger.info("--- Cập nhật bảng Users ---")
        table_users = "Users"
        
        # Cột notification_target_set_id
        column_notify_set_id = "notification_target_set_id"
        definition_notify_set_id = "INTEGER DEFAULT NULL REFERENCES VocabularySets(set_id) ON DELETE SET NULL"
        add_column_if_not_exists(cursor, table_users, column_notify_set_id, definition_notify_set_id)

        # Cột enable_morning_brief
        column_enable_brief = "enable_morning_brief"
        definition_enable_brief = "INTEGER DEFAULT 1" # Mặc định là bật
        add_column_if_not_exists(cursor, table_users, column_enable_brief, definition_enable_brief)

        # Cột last_morning_brief_sent_date
        column_last_brief_date = "last_morning_brief_sent_date"
        definition_last_brief_date = "TEXT DEFAULT NULL"
        add_column_if_not_exists(cursor, table_users, column_last_brief_date, definition_last_brief_date)

        # Commit transaction nếu tất cả thành công
        conn.commit()
        logger.info("TRANSACTION đã được COMMIT thành công.")

    except sqlite3.Error as e:
        logger.error(f"Lỗi SQLite khi cập nhật schema tại '{abs_db_path}': {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
                logger.info("Đã ROLLBACK thay đổi do lỗi SQLite.")
            except Exception as rb_err:
                logger.error(f"Lỗi khi rollback: {rb_err}")
    except Exception as e:
        logger.error(f"Đã xảy ra lỗi không mong muốn: {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
                logger.info("Đã ROLLBACK thay đổi do lỗi không mong muốn.")
            except Exception as rb_err:
                logger.error(f"Lỗi khi rollback: {rb_err}")
    finally:
        if conn:
            conn.close()
            logger.info("Đã đóng kết nối cơ sở dữ liệu.")

if __name__ == '__main__':
    logger.info("Bắt đầu chạy script cập nhật cơ sở dữ liệu thủ công...")
    update_database_schema_if_needed()
    logger.info("Hoàn tất script cập nhật cơ sở dữ liệu thủ công.")
