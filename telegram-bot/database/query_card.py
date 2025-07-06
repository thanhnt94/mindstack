"""
Module chứa các hàm truy vấn dữ liệu liên quan trực tiếp đến bảng Flashcards.
"""
import sqlite3
import logging
import html 
from database.connection import database_connect
from utils.exceptions import DatabaseError, CardNotFoundError
logger = logging.getLogger(__name__)
def get_card_by_id(flashcard_id, conn=None):
    """
    Lấy thông tin chi tiết của một flashcard dựa vào flashcard_id.
    Bao gồm cả cột ảnh và cột notification_text.
    Args:
        flashcard_id (int): ID của flashcard cần lấy thông tin.
        conn (sqlite3.Connection): Đối tượng kết nối DB có sẵn (tùy chọn).
    Returns:
        dict: Một dictionary chứa thông tin của flashcard.
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite khác xảy ra.
        CardNotFoundError: Nếu không tìm thấy flashcard với ID cung cấp.
    """
    log_prefix = f"[GET_CARD_INFO|Card:{flashcard_id}]"
    internal_conn = None
    should_close_conn = False
    card_data = None
    original_factory = None
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            conn.row_factory = sqlite3.Row 
        else:
             original_factory = conn.row_factory
             conn.row_factory = sqlite3.Row 
        query = """
            SELECT
                flashcard_id, set_id, front, back,
                front_audio_content, back_audio_content,
                front_img, back_img,
                notification_text
            FROM Flashcards
            WHERE flashcard_id = ?
            """
        logger.debug(f"{log_prefix} Executing query: {query.strip()} with ID: {flashcard_id}")
        cursor = conn.cursor()
        cursor.execute(query, (flashcard_id,))
        row = cursor.fetchone()
        if row:
            logger.debug(f"{log_prefix} Tìm thấy flashcard. Chuyển đổi sang dict.")
            card_data = dict(row) 
            if card_data.get("front"):
                card_data["front"] = html.unescape(card_data["front"])
            if card_data.get("back"):
                card_data["back"] = html.unescape(card_data["back"])
            if card_data.get("notification_text"):
                pass 
            log_extra = []
            if card_data.get("front_img"): log_extra.append("có front_img")
            if card_data.get("back_img"): log_extra.append("có back_img")
            if card_data.get("notification_text"): log_extra.append("có notification_text")
            if log_extra: logger.debug(f"{log_prefix} Thẻ này {', '.join(log_extra)}.")
            if original_factory is not None:
                conn.row_factory = original_factory
            return card_data 
        else:
            logger.warning(f"{log_prefix} Không tìm thấy flashcard với ID: {flashcard_id}")
            raise CardNotFoundError(card_id=flashcard_id) 
    except sqlite3.Error as e:
        logger.exception(f"{log_prefix} Lỗi SQLite: {e}")
        raise DatabaseError("Lỗi SQLite khi lấy thông tin thẻ.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm: {e}")
        if isinstance(e, (DatabaseError, CardNotFoundError)): 
            raise e
        raise DatabaseError("Lỗi không mong muốn khi lấy thông tin thẻ.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
             try:
                 conn.execute("SELECT 1") 
                 conn.row_factory = original_factory
             except Exception: pass
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")