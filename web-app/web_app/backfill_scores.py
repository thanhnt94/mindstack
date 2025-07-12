# web_app/backfill_score_source.py
import os
import sys
import logging
import sqlite3

# Thiết lập để import từ thư mục gốc
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import cấu hình database sau khi đã thiết lập sys.path
from web_app.config import DATABASE_PATH

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='[DB_MIGRATION] %(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate_database():
    """
    Mô tả: Thêm cột 'source_type' vào bảng ScoreLogs và điền dữ liệu cũ.
    Hàm này được thiết kế để chạy an toàn nhiều lần, nó sẽ không làm gì nếu cột đã tồn tại.
    """
    if not os.path.exists(DATABASE_PATH):
        logger.error(f"File database không tìm thấy tại: {DATABASE_PATH}. Vui lòng chạy update_database.py trước.")
        return

    try:
        # Kết nối trực tiếp đến file database SQLite
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        logger.info("Đã kết nối tới database thành công.")

        # Bước 1: Thêm cột 'source_type' nếu nó chưa tồn tại.
        try:
            logger.info("Đang thử thêm cột 'source_type' vào bảng ScoreLogs...")
            # Thêm cột mới với giá trị mặc định là NULL
            cursor.execute("ALTER TABLE ScoreLogs ADD COLUMN source_type VARCHAR(50)")
            logger.info("Đã thêm cột 'source_type' thành công.")
        except sqlite3.OperationalError as e:
            # Bắt lỗi nếu cột đã tồn tại, đây là trường hợp bình thường nếu chạy script lần thứ 2
            if "duplicate column name" in str(e):
                logger.warning("Cột 'source_type' đã tồn tại. Bỏ qua bước thêm cột.")
            else:
                # Nếu là lỗi khác, thì báo lỗi
                raise e

        # Bước 2: Điền dữ liệu cho các bản ghi cũ.
        logger.info("Đang điền giá trị 'flashcard' cho các bản ghi điểm cũ...")
        # Chỉ cập nhật những dòng mà source_type đang là NULL để đảm bảo an toàn
        cursor.execute("UPDATE ScoreLogs SET source_type = 'flashcard' WHERE source_type IS NULL")
        conn.commit()
        # Ghi log số dòng đã được cập nhật
        logger.info(f"{cursor.rowcount} dòng đã được cập nhật với source_type = 'flashcard'.")

        logger.info("Nâng cấp database thành công!")

    except Exception as e:
        logger.error(f"Đã xảy ra lỗi trong quá trình nâng cấp database: {e}", exc_info=True)
    finally:
        # Đảm bảo kết nối luôn được đóng
        if 'conn' in locals() and conn:
            conn.close()
            logger.info("Đã đóng kết nối database.")

if __name__ == '__main__':
    # Chạy hàm nâng cấp khi thực thi file này
    migrate_database()
