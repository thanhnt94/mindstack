# File: flashcard-telegram-bot/database/query_note.py
"""
Module chứa các hàm truy vấn và cập nhật dữ liệu liên quan đến bảng FlashcardNotes.
Các hàm này đã sử dụng user_id (khóa chính) để tham chiếu người dùng.
(Thêm hàm get_flashcard_id_from_note).
(Sửa lần 1: Cập nhật các hàm để hỗ trợ cột image_path, thêm hàm delete_note_image_path).
"""
import sqlite3
import logging

# Sử dụng import tuyệt đối
from database.connection import database_connect
from utils.exceptions import (
    DatabaseError,
    DuplicateError
)

logger = logging.getLogger(__name__)

def get_note_by_card_and_user(flashcard_id, user_id, conn=None):
    """
    Lấy nội dung ghi chú và đường dẫn ảnh của người dùng cho một flashcard cụ thể.
    Sửa lần 1: Thêm image_path vào SELECT.
    Args:
        flashcard_id (int): ID của flashcard.
        user_id (int): ID (khóa chính) của người dùng.
        conn (sqlite3.Connection): Đối tượng kết nối DB có sẵn (tùy chọn).
    Returns:
        dict: Dictionary thông tin ghi chú (bao gồm image_path) nếu tìm thấy.
        None: Nếu không tìm thấy ghi chú.
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
    """
    log_prefix = "[get_note_by_card_and_user|UserUID:{}, Card:{}]".format(user_id, flashcard_id)
    internal_conn = None
    should_close_conn = False
    note_data = None
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

        cursor = conn.cursor()
        # Sửa lần 1: Thêm cột image_path vào câu truy vấn
        query = """
            SELECT note_id, flashcard_id, user_id, note, created_at, image_path
            FROM FlashcardNotes
            WHERE flashcard_id = ? AND user_id = ?
        """
        logger.debug("{}: Executing query: {} with params: ({}, {})".format(log_prefix, query.strip(), flashcard_id, user_id))
        cursor.execute(query, (flashcard_id, user_id))
        note_row = cursor.fetchone()

        if note_row:
            note_data = dict(note_row)
            logger.debug("{}: Tìm thấy ghi chú: {}".format(log_prefix, note_data))
        else:
            logger.debug("{}: Không tìm thấy ghi chú nào.".format(log_prefix))
            note_data = None

        if original_factory is not None and conn is not None and not should_close_conn:
            try:
                conn.execute("SELECT 1")
                conn.row_factory = original_factory
            except Exception:
                pass
        return note_data

    except sqlite3.Error as e:
        logger.exception("{}: Lỗi SQLite: {}".format(log_prefix, e))
        raise DatabaseError("Lỗi SQLite khi lấy ghi chú.", original_exception=e)
    except Exception as e:
        logger.exception("{}: Lỗi trong hàm: {}".format(log_prefix, e))
        if isinstance(e, DatabaseError):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi lấy ghi chú.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
            try:
                conn.execute("SELECT 1")
                conn.row_factory = original_factory
            except Exception:
                logger.warning("{}: Không thể khôi phục row_factory gốc cho connection bên ngoài.".format(log_prefix))
                pass
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug("{}: Đã đóng kết nối DB nội bộ.".format(log_prefix))

def add_note_for_user(flashcard_id, user_id, note_text, image_path_param=None, conn=None):
    """
    Thêm một ghi chú mới (bao gồm cả đường dẫn ảnh nếu có) cho flashcard của người dùng.
    Sửa lần 1: Thêm tham số image_path_param và xử lý việc chèn nó.
    Args:
        flashcard_id (int): ID của flashcard.
        user_id (int): ID (khóa chính) của người dùng.
        note_text (str): Nội dung ghi chú cần thêm.
        image_path_param (str, optional): Đường dẫn tương đối của file ảnh. Mặc định là None.
        conn (sqlite3.Connection): Đối tượng kết nối DB có sẵn (tùy chọn).
    Returns:
        int: note_id mới được tạo.
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
        DuplicateError: Nếu có lỗi ràng buộc dữ liệu khi chèn.
    """
    log_prefix = "[add_note_for_user|UserUID:{}, Card:{}]".format(user_id, flashcard_id)
    logger.debug("{}: Đang thêm ghi chú (image_path: {}).".format(log_prefix, image_path_param))
    internal_conn = None
    should_close_conn = False
    should_commit = False
    new_note_id = None

    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True

        cursor = conn.cursor()
        # Sửa lần 1: Thêm cột image_path và giá trị tương ứng vào câu INSERT
        query = "INSERT INTO FlashcardNotes (flashcard_id, user_id, note, image_path) VALUES (?, ?, ?, ?)"
        params = (flashcard_id, user_id, note_text, image_path_param)
        logger.debug("{}: Executing query: {} with params: ({}, {}, '{}...', '{}')".format(
            log_prefix, query, flashcard_id, user_id, note_text[:50] if note_text else "", image_path_param
        ))
        cursor.execute(query, params)
        new_note_id = cursor.lastrowid

        if new_note_id is None or new_note_id <= 0:
            if should_commit and conn:
                conn.rollback()
            raise DatabaseError("Lỗi không xác định: Không nhận được lastrowid hợp lệ sau khi INSERT note.")

        if should_commit:
            conn.commit()
            logger.debug("{}: Ghi chú đã được thêm với ID {} và commit.".format(log_prefix, new_note_id))
        else:
            logger.debug("{}: Ghi chú đã được thêm với ID {} (kết nối ngoài quản lý commit).".format(log_prefix, new_note_id))

        return int(new_note_id)

    except sqlite3.IntegrityError as e:
        logger.error("{}: Lỗi ràng buộc dữ liệu (IntegrityError): {}.".format(log_prefix, e))
        if should_commit and conn:
            conn.rollback()
        raise DuplicateError("Lỗi ràng buộc dữ liệu khi thêm ghi chú.", original_exception=e)
    except sqlite3.Error as e:
        logger.exception("{}: Lỗi SQLite khác khi thêm ghi chú: {}".format(log_prefix, e))
        if should_commit and conn:
            conn.rollback()
        raise DatabaseError("Lỗi SQLite khi thêm ghi chú.", original_exception=e)
    except Exception as e:
        logger.exception("{}: Lỗi trong hàm thêm ghi chú: {}".format(log_prefix, e))
        if should_commit and conn:
            conn.rollback()
        if isinstance(e, (DatabaseError, DuplicateError)):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi thêm ghi chú.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug("{}: Đã đóng kết nối DB nội bộ.".format(log_prefix))

def update_note_by_id(note_id, note_text=None, image_path_param=None, delete_image=False, conn=None):
    """
    Chỉnh sửa nội dung và/hoặc đường dẫn ảnh của một ghi chú đã tồn tại dựa trên note_id.
    Sửa lần 1: Thêm image_path_param và delete_image để quản lý ảnh.
    Args:
        note_id (int): ID của ghi chú cần chỉnh sửa.
        note_text (str, optional): Nội dung ghi chú mới. Nếu None, không cập nhật text.
        image_path_param (str, optional): Đường dẫn ảnh mới. Nếu None, không cập nhật ảnh.
                                         Nếu được cung cấp, sẽ ghi đè đường dẫn ảnh cũ.
        delete_image (bool): Nếu True, sẽ xóa (đặt thành NULL) đường dẫn ảnh hiện tại.
                             Tham số này sẽ được ưu tiên hơn image_path_param nếu cả hai cùng được đặt.
        conn (sqlite3.Connection): Đối tượng kết nối DB có sẵn (tùy chọn).
    Returns:
        int: Số hàng bị ảnh hưởng (thường là 1 nếu thành công, 0 nếu không tìm thấy).
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
    """
    log_prefix = "[update_note_by_id|NoteID:{}]".format(note_id)
    logger.debug("{}: Đang chỉnh sửa ghi chú (note_text is None: {}, image_path: {}, delete_image: {}).".format(
        log_prefix, note_text is None, image_path_param, delete_image
    ))
    internal_conn = None
    should_close_conn = False
    should_commit = False
    rows_affected = 0

    update_fields = []
    params = []

    if note_text is not None:
        update_fields.append("note = ?")
        params.append(note_text)

    if delete_image: # Ưu tiên xóa ảnh
        update_fields.append("image_path = ?")
        params.append(None) # Đặt thành NULL để xóa
        logger.debug(f"{log_prefix}: Sẽ xóa image_path.")
    elif image_path_param is not None: # Nếu không xóa và có đường dẫn mới
        update_fields.append("image_path = ?")
        params.append(image_path_param)
        logger.debug(f"{log_prefix}: Sẽ cập nhật image_path thành '{image_path_param}'.")
    # Nếu cả delete_image=False và image_path_param=None, thì không làm gì với image_path

    if not update_fields:
        logger.warning("{}: Không có trường nào để cập nhật.".format(log_prefix))
        return 0 # Không có gì để làm

    params.append(note_id) # Thêm note_id vào cuối cho điều kiện WHERE

    set_clause = ", ".join(update_fields)
    query = "UPDATE FlashcardNotes SET {} WHERE note_id = ?".format(set_clause)

    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True

        cursor = conn.cursor()
        logger.debug("{}: Executing query: {} with params: {}".format(log_prefix, query, params))
        cursor.execute(query, params)
        rows_affected = cursor.rowcount

        if should_commit:
            conn.commit()
            logger.debug("{}: Cập nhật ghi chú đã được commit. Rows affected: {}".format(log_prefix, rows_affected))
        else:
            logger.debug("{}: Cập nhật ghi chú hoàn tất (kết nối ngoài quản lý commit). Rows affected: {}".format(log_prefix, rows_affected))

        if rows_affected == 0:
            logger.warning("{}: Không tìm thấy ghi chú ID {} để cập nhật.".format(log_prefix, note_id))
        return rows_affected

    except sqlite3.Error as e:
        logger.exception("{}: Lỗi SQLite: {}".format(log_prefix, e))
        if should_commit and conn:
            conn.rollback()
        raise DatabaseError("Lỗi SQLite khi cập nhật ghi chú.", original_exception=e)
    except Exception as e:
        logger.exception("{}: Lỗi trong hàm cập nhật ghi chú: {}".format(log_prefix, e))
        if should_commit and conn:
            conn.rollback()
        if isinstance(e, DatabaseError):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi cập nhật ghi chú.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug("{}: Đã đóng kết nối DB nội bộ.".format(log_prefix))

def get_flashcard_id_from_note(note_id, conn=None):
    """
    Lấy flashcard_id từ một note_id cho trước.
    Args:
        note_id (int): ID của ghi chú.
        conn (sqlite3.Connection, optional): Đối tượng kết nối DB có sẵn.
    Returns:
        int: flashcard_id nếu tìm thấy.
        None: Nếu không tìm thấy ghi chú hoặc có lỗi.
    Raises:
        DatabaseError: Nếu có lỗi SQLite xảy ra trong quá trình truy vấn.
    """
    log_prefix = "[get_flashcard_id_from_note|NoteID:{}]".format(note_id)
    logger.debug("{}: Đang lấy flashcard_id từ note_id.".format(log_prefix))
    internal_conn = None
    should_close_conn = False
    flashcard_id_result = None

    if not isinstance(note_id, int) or note_id <= 0:
        logger.warning("{}: note_id không hợp lệ: {}".format(log_prefix, note_id))
        return None

    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
        else:
            pass # Không thay đổi row_factory nếu conn được truyền vào

        cursor = conn.cursor()
        query = "SELECT flashcard_id FROM FlashcardNotes WHERE note_id = ?"
        logger.debug("{}: Executing query: {} with params: ({})".format(log_prefix, query, note_id))
        cursor.execute(query, (note_id,))
        row = cursor.fetchone()

        if row:
            flashcard_id_result = row[0] # Truy cập bằng index
            if flashcard_id_result is not None:
                logger.debug("{}: Tìm thấy flashcard_id: {}".format(log_prefix, flashcard_id_result))
            else:
                logger.warning("{}: Tìm thấy note_id {} nhưng flashcard_id là NULL.".format(log_prefix, note_id))
                flashcard_id_result = None
        else:
            logger.warning("{}: Không tìm thấy ghi chú với ID: {}".format(log_prefix, note_id))
            flashcard_id_result = None

        return flashcard_id_result

    except sqlite3.Error as e:
        logger.exception("{}: Lỗi SQLite khi lấy flashcard_id từ note: {}".format(log_prefix, e))
        raise DatabaseError("Lỗi SQLite khi lấy flashcard_id từ note.", original_exception=e)
    except Exception as e:
        logger.exception("{}: Lỗi không mong muốn: {}".format(log_prefix, e))
        return None
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug("{}: Đã đóng kết nối DB nội bộ.".format(log_prefix))

# Sửa lần 1: Thêm hàm delete_note_image_path
def delete_note_image_path(note_id, conn=None):
    """
    Xóa (đặt thành NULL) đường dẫn ảnh của một ghi chú dựa trên note_id.
    Hàm này không xóa nội dung text của ghi chú.

    Args:
        note_id (int): ID của ghi chú cần xóa ảnh.
        conn (sqlite3.Connection, optional): Đối tượng kết nối DB có sẵn.

    Returns:
        int: Số hàng bị ảnh hưởng (thường là 1 nếu thành công, 0 nếu không tìm thấy note_id).

    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
    """
    log_prefix = "[delete_note_image|NoteID:{}]".format(note_id)
    logger.info("{}: Yêu cầu xóa image_path.".format(log_prefix))
    internal_conn = None
    should_close_conn = False
    should_commit = False
    rows_affected = 0

    if not isinstance(note_id, int) or note_id <= 0:
        logger.warning("{}: note_id không hợp lệ: {}".format(log_prefix, note_id))
        return 0

    query = "UPDATE FlashcardNotes SET image_path = NULL WHERE note_id = ?"
    params = (note_id,)

    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True

        cursor = conn.cursor()
        logger.debug("{}: Executing query: {} with params: {}".format(log_prefix, query, params))
        cursor.execute(query, params)
        rows_affected = cursor.rowcount

        if should_commit:
            conn.commit()
            logger.debug("{}: Xóa image_path đã được commit. Rows affected: {}".format(log_prefix, rows_affected))
        else:
            logger.debug("{}: Xóa image_path hoàn tất (kết nối ngoài quản lý commit). Rows affected: {}".format(log_prefix, rows_affected))

        if rows_affected == 0:
            logger.warning("{}: Không tìm thấy ghi chú ID {} để xóa image_path.".format(log_prefix, note_id))
        else:
            logger.info("{}: Đã xóa thành công image_path cho note ID {}.".format(log_prefix, note_id))
        return rows_affected

    except sqlite3.Error as e:
        logger.exception("{}: Lỗi SQLite khi xóa image_path: {}".format(log_prefix, e))
        if should_commit and conn:
            conn.rollback()
        raise DatabaseError("Lỗi SQLite khi xóa đường dẫn ảnh của ghi chú.", original_exception=e)
    except Exception as e:
        logger.exception("{}: Lỗi không mong muốn khi xóa image_path: {}".format(log_prefix, e))
        if should_commit and conn:
            conn.rollback()
        if isinstance(e, DatabaseError):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi xóa đường dẫn ảnh của ghi chú.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug("{}: Đã đóng kết nối DB nội bộ.".format(log_prefix))
