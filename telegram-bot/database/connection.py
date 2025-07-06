"""
Module quản lý kết nối đến cơ sở dữ liệu SQLite.
(Đã thêm bật chế độ WAL để tăng hiệu năng đồng thời)
"""
import os
import sqlite3
import logging
from config import FLASHCARD_DB_PATH
from database.schema import database_initialize
def database_connect():
    """
    Thiết lập và trả về một kết nối đến cơ sở dữ liệu SQLite.
    Đã bật hỗ trợ foreign key và chế độ WAL (Write-Ahead Logging).
    Hàm này kiểm tra xem file database đã tồn tại chưa. Nếu chưa, nó sẽ tạo
    thư mục chứa database (nếu cần) và gọi hàm database_initialize để
    tạo các bảng và cấu trúc cần thiết.
    Returns:
        Đối tượng sqlite3.Connection nếu kết nối thành công, hoặc None nếu xảy ra lỗi.
    """
    db_path = FLASHCARD_DB_PATH
    logger = logging.getLogger(__name__) 
    should_initialize = not os.path.exists(db_path)
    if should_initialize:
        logger.info(f"File database không tìm thấy tại '{db_path}'. Sẽ tiến hành khởi tạo.")
        db_dir = os.path.dirname(db_path)
        if db_dir: 
            try:
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Đã tạo thư mục database: {db_dir}")
            except OSError as e:
                logger.error(f"Không thể tạo thư mục database '{db_dir}': {e}")
                return None 
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False) 
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        logger.debug(f"Đã bật foreign keys cho kết nối '{db_path}'.")
        try:
            cursor = conn.cursor() 
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA journal_mode;")
            current_journal_mode = cursor.fetchone()
            if current_journal_mode and current_journal_mode[0].lower() == 'wal':
                logger.info(f"Đã bật thành công chế độ WAL cho '{db_path}'.")
            else:
                 current_mode_str = current_journal_mode[0] if current_journal_mode else 'Không xác định'
                 logger.warning(f"Không thể bật chế độ WAL cho '{db_path}'. Chế độ hiện tại: {current_mode_str}.")
        except sqlite3.Error as e_wal:
             logger.error(f"Lỗi khi thực thi PRAGMA journal_mode=WAL: {e_wal}")
        logger.info(f"Kết nối database tại '{db_path}' thành công.")
    except sqlite3.Error as e:
        logger.error(f"Lỗi khi kết nối đến database tại '{db_path}': {e}")
        return None
    if should_initialize:
        try:
            logger.info(f"Bắt đầu khởi tạo schema cho database '{db_path}'...")
            database_initialize(conn) 
            logger.info(f"Database tại '{db_path}' đã được khởi tạo thành công.")
        except Exception as e_init:
            logger.error(f"Khởi tạo database thất bại: {e_init}", exc_info=True)
            conn.close()
            return None
    return conn