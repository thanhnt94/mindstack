# Path: flashcard_v2/database/query_report.py
"""
Module chứa các hàm truy vấn và cập nhật dữ liệu liên quan đến
bảng CardReports (báo cáo lỗi thẻ).
Đã thêm hàm lấy tóm tắt report theo card_id và hàm cập nhật status cho card.
"""
import sqlite3
import logging
import time

# Import từ các module khác (tuyệt đối)
from database.connection import database_connect
from utils.exceptions import DatabaseError, DuplicateError, ValidationError

logger = logging.getLogger(__name__)

def add_card_report(flashcard_id, reporter_user_id, creator_user_id, set_id, report_text, conn=None):
    """
    Thêm một báo cáo lỗi thẻ mới vào database.

    Args:
        flashcard_id (int): ID của thẻ bị báo lỗi.
        reporter_user_id (int): User ID của người báo cáo.
        creator_user_id (int): User ID của người tạo bộ thẻ.
        set_id (int): ID của bộ thẻ chứa thẻ lỗi.
        report_text (str): Nội dung báo cáo lỗi.
        conn (sqlite3.Connection, optional): Kết nối DB có sẵn.

    Returns:
        int: ID của báo cáo vừa được tạo (report_id).

    Raises:
        DatabaseError: Nếu có lỗi DB.
        DuplicateError: Nếu lỗi ràng buộc (ít xảy ra với bảng này).
        ValidationError: Nếu dữ liệu đầu vào không hợp lệ.
    """
    log_prefix = f"[REPORT_ADD|Card:{flashcard_id}|Reporter:{reporter_user_id}]"
    logger.info(f"{log_prefix} Thêm báo cáo lỗi mới.")

    if not all([isinstance(flashcard_id, int), isinstance(reporter_user_id, int)]):
        raise ValidationError("flashcard_id và reporter_user_id phải là số nguyên.")
    report_text_to_save = str(report_text).strip() if report_text is not None else ""

    internal_conn = None
    should_close_conn = False
    should_commit = False
    new_report_id = None

    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True

        cursor = conn.cursor()
        query = """
            INSERT INTO CardReports
            (flashcard_id, reporter_user_id, creator_user_id, set_id, report_text, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (flashcard_id, reporter_user_id, creator_user_id, set_id, report_text_to_save, 'pending')

        logger.debug(f"{log_prefix} Executing INSERT Report: {params}")
        cursor.execute(query, params)
        new_report_id = cursor.lastrowid

        if new_report_id is None or new_report_id <= 0:
            if should_commit and conn:
                conn.rollback()
            raise DatabaseError("Lỗi không xác định: Không nhận được lastrowid hợp lệ sau khi INSERT report.")

        if should_commit:
            conn.commit()
            logger.info(f"{log_prefix} Đã thêm và commit report ID: {new_report_id}.")
        else:
            logger.info(f"{log_prefix} Đã thêm report ID: {new_report_id} (kết nối ngoài quản lý commit).")

        # Đảm bảo trả về int
        return int(new_report_id) if new_report_id is not None else 0


    except sqlite3.IntegrityError as e:
        logger.error(f"{log_prefix} Lỗi ràng buộc dữ liệu (IntegrityError): {e}.")
        if should_commit and conn:
            conn.rollback()
        raise DuplicateError("Lỗi ràng buộc dữ liệu khi thêm báo cáo.", original_exception=e)
    except sqlite3.Error as e:
        logger.exception(f"{log_prefix} Lỗi SQLite khác khi thêm báo cáo: {e}")
        if should_commit and conn:
            conn.rollback()
        raise DatabaseError("Lỗi SQLite khi thêm báo cáo.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm thêm báo cáo: {e}")
        if should_commit and conn:
            conn.rollback()
        if isinstance(e, (DatabaseError, DuplicateError, ValidationError)):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi thêm báo cáo.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")

def get_sets_with_pending_reports(creator_user_id, conn=None):
    """
    Lấy danh sách các bộ từ của một người tạo đang có báo cáo lỗi ở trạng thái 'pending'.
    Trả về thông tin set và số lượng báo cáo pending cho mỗi set.

    Args:
        creator_user_id (int): User ID của người tạo bộ thẻ.
        conn (sqlite3.Connection, optional): Kết nối DB có sẵn.

    Returns:
        list: Danh sách các dict {'set_id': ..., 'title': ..., 'pending_count': ...}.
              Trả về list rỗng nếu không có hoặc lỗi.
    """
    log_prefix = f"[REPORT_GET_SETS_PENDING|Creator:{creator_user_id}]"
    logger.debug(f"{log_prefix} Lấy danh sách bộ có report pending.")
    results = []
    internal_conn = None
    should_close_conn = False
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
        query = """
            SELECT
                cr.set_id,
                vs.title,
                COUNT(cr.report_id) as pending_count
            FROM CardReports cr
            JOIN VocabularySets vs ON cr.set_id = vs.set_id
            WHERE cr.creator_user_id = ? AND cr.status = 'pending'
            GROUP BY cr.set_id, vs.title
            ORDER BY vs.title COLLATE NOCASE
        """
        logger.debug(f"{log_prefix} Executing query: {query.strip()} with params: ({creator_user_id},)")
        cursor.execute(query, (creator_user_id,))
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        logger.info(f"{log_prefix} Tìm thấy {len(results)} bộ có report pending.")

        if original_factory is not None:
            conn.row_factory = original_factory

        return results

    except sqlite3.Error as e_db:
        logger.error(f"{log_prefix} Lỗi SQLite: {e_db}", exc_info=True)
        # Không raise lỗi ở đây, trả về list rỗng để handler xử lý
        return []
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        return []
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
            try:
                conn.execute("SELECT 1")
                conn.row_factory = original_factory
            except Exception:
                pass
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")

def get_pending_reports_for_set(set_id, creator_user_id, conn=None):
    """
    Lấy danh sách chi tiết các báo cáo lỗi đang chờ xử lý cho một bộ từ cụ thể
    của một người tạo.

    Args:
        set_id (int): ID của bộ từ.
        creator_user_id (int): User ID của người tạo (để kiểm tra quyền).
        conn (sqlite3.Connection, optional): Kết nối DB có sẵn.

    Returns:
        list: Danh sách các dict chứa thông tin báo cáo chi tiết.
              Trả về list rỗng nếu không có hoặc lỗi.
    """
    log_prefix = f"[REPORT_GET_PENDING_FOR_SET|Set:{set_id}|Creator:{creator_user_id}]"
    logger.debug(f"{log_prefix} Lấy chi tiết report pending cho bộ.")
    results = []
    internal_conn = None
    should_close_conn = False
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
        # Thêm join với Flashcards để lấy front (nếu cần hiển thị ở đây)
        # Bổ sung thông tin front để UI dễ hiển thị hơn
        query = """
            SELECT
                cr.report_id, cr.flashcard_id, cr.reporter_user_id,
                cr.report_text, cr.reported_at,
                f.front
            FROM CardReports cr
            LEFT JOIN Flashcards f ON cr.flashcard_id = f.flashcard_id
            WHERE cr.set_id = ? AND cr.creator_user_id = ? AND cr.status = 'pending'
            ORDER BY cr.flashcard_id ASC, cr.reported_at ASC
        """
        params = (set_id, creator_user_id)
        logger.debug(f"{log_prefix} Executing query: {query.strip()} with params: {params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        logger.info(f"{log_prefix} Tìm thấy {len(results)} report pending chi tiết.")

        if original_factory is not None:
            conn.row_factory = original_factory

        return results

    except sqlite3.Error as e_db:
        logger.error(f"{log_prefix} Lỗi SQLite: {e_db}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        return []
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
            try:
                conn.execute("SELECT 1")
                conn.row_factory = original_factory
            except Exception:
                pass
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")

def update_report_status(report_id, new_status, resolver_user_id, conn=None):
    """
    Cập nhật trạng thái của một báo cáo lỗi cụ thể.

    Args:
        report_id (int): ID của báo cáo cần cập nhật.
        new_status (str): Trạng thái mới ('resolved', 'rejected', ...).
        resolver_user_id (int): User ID của người thực hiện cập nhật.
        conn (sqlite3.Connection, optional): Kết nối DB có sẵn.

    Returns:
        bool: True nếu cập nhật thành công (ít nhất 1 hàng bị ảnh hưởng), False nếu không.

    Raises:
        DatabaseError: Nếu có lỗi DB.
        ValidationError: Nếu trạng thái mới không hợp lệ.
    """
    log_prefix = f"[REPORT_UPDATE_STATUS|ReportID:{report_id}|NewStatus:{new_status}]"
    logger.info(f"{log_prefix} Cập nhật trạng thái báo cáo.")

    valid_statuses = ['pending', 'resolved', 'rejected', 'acknowledged']
    if new_status not in valid_statuses:
        raise ValidationError(f"Trạng thái '{new_status}' không hợp lệ.")

    internal_conn = None
    should_close_conn = False
    should_commit = False
    rows_affected = 0

    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True

        cursor = conn.cursor()
        resolved_at_ts = int(time.time()) if new_status != 'pending' else None
        query = """
            UPDATE CardReports
            SET status = ?, resolved_at = ?, resolver_user_id = ?
            WHERE report_id = ? AND status = 'pending'
        """
        params = (new_status, resolved_at_ts, resolver_user_id, report_id)

        logger.debug(f"{log_prefix} Executing query: {query.strip()} with params: {params}")
        cursor.execute(query, params)
        rows_affected = cursor.rowcount

        if should_commit:
            conn.commit()
            logger.debug(f"{log_prefix} Commit cập nhật trạng thái.")

        if rows_affected > 0:
            logger.info(f"{log_prefix} Cập nhật trạng thái thành công ({rows_affected} hàng).")
            return True
        else:
            logger.warning(f"{log_prefix} Không tìm thấy báo cáo ID {report_id} ở trạng thái 'pending' để cập nhật.")
            return False

    except sqlite3.Error as e_db:
        logger.error(f"{log_prefix} Lỗi SQLite: {e_db}", exc_info=True)
        if should_commit and conn:
            conn.rollback()
        raise DatabaseError("Lỗi SQLite khi cập nhật trạng thái báo cáo.", original_exception=e_db)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        if should_commit and conn:
            conn.rollback()
        if isinstance(e, (DatabaseError, ValidationError)):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi cập nhật trạng thái báo cáo.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")

def get_report_details_by_id(report_id, conn=None):
    """
    Lấy thông tin chi tiết của một báo cáo lỗi dựa trên report_id.

    Args:
        report_id (int): ID của báo cáo.
        conn (sqlite3.Connection, optional): Kết nối DB có sẵn.

    Returns:
        dict: Dictionary chứa thông tin báo cáo, hoặc None nếu không tìm thấy.
    Raises:
        DatabaseError: Nếu có lỗi DB.
    """
    log_prefix = f"[REPORT_GET_DETAILS|ReportID:{report_id}]"
    logger.debug(f"{log_prefix} Lấy chi tiết báo cáo.")
    internal_conn = None
    should_close_conn = False
    original_factory = None
    report_data = None

    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối DB.")
            conn = internal_conn
            should_close_conn = True
            conn.row_factory = sqlite3.Row
        else:
            original_factory = conn.row_factory
            conn.row_factory = sqlite3.Row

        cursor = conn.cursor()
        query = "SELECT * FROM CardReports WHERE report_id = ?"
        cursor.execute(query, (report_id,))
        row = cursor.fetchone()

        if row:
            report_data = dict(row)
            logger.info(f"{log_prefix} Tìm thấy báo cáo.")
        else:
            logger.warning(f"{log_prefix} Không tìm thấy báo cáo với ID {report_id}.")

        if original_factory is not None:
            conn.row_factory = original_factory

        return report_data

    except sqlite3.Error as e_db:
        logger.error(f"{log_prefix} Lỗi SQLite: {e_db}", exc_info=True)
        raise DatabaseError("Lỗi SQLite khi lấy chi tiết báo cáo.", original_exception=e_db)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        raise DatabaseError("Lỗi không mong muốn khi lấy chi tiết báo cáo.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
             try:
                 conn.execute("SELECT 1")
                 conn.row_factory = original_factory
             except Exception: pass
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB.")

# --- HÀM MỚI ---
def get_pending_reports_summary_by_card(set_id, creator_user_id, conn=None):
    """
    Lấy danh sách tóm tắt các thẻ có báo cáo lỗi đang chờ xử lý cho một bộ từ cụ thể.

    Args:
        set_id (int): ID của bộ từ.
        creator_user_id (int): User ID của người tạo (để kiểm tra quyền).
        conn (sqlite3.Connection, optional): Kết nối DB có sẵn.

    Returns:
        list: Danh sách các dict {'flashcard_id': ..., 'report_count': ...}.
              Trả về list rỗng nếu không có hoặc lỗi.
    """
    log_prefix = f"[REPORT_GET_SUMMARY_BY_CARD|Set:{set_id}|Creator:{creator_user_id}]"
    logger.debug(f"{log_prefix} Lấy tóm tắt báo cáo theo flashcard_id.")
    results = []
    internal_conn = None
    should_close_conn = False
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
        # Truy vấn nhóm theo flashcard_id
        query = """
            SELECT
                flashcard_id,
                COUNT(report_id) as report_count
            FROM CardReports
            WHERE set_id = ? AND creator_user_id = ? AND status = 'pending'
            GROUP BY flashcard_id
            ORDER BY flashcard_id ASC
        """
        params = (set_id, creator_user_id)
        logger.debug(f"{log_prefix} Executing query: {query.strip()} with params: {params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        logger.info(f"{log_prefix} Tìm thấy {len(results)} thẻ có report pending.")

        if original_factory is not None:
            conn.row_factory = original_factory

        return results

    except sqlite3.Error as e_db:
        logger.error(f"{log_prefix} Lỗi SQLite: {e_db}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        return []
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
            try:
                conn.execute("SELECT 1")
                conn.row_factory = original_factory
            except Exception:
                pass
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")

# --- HÀM MỚI ---
def update_status_for_card_reports(flashcard_id, new_status, resolver_user_id, conn=None):
    """
    Cập nhật trạng thái cho tất cả các báo cáo đang chờ xử lý của một flashcard cụ thể.

    Args:
        flashcard_id (int): ID của thẻ flashcard.
        new_status (str): Trạng thái mới ('resolved', 'rejected', etc.).
        resolver_user_id (int): User ID của người thực hiện cập nhật.
        conn (sqlite3.Connection, optional): Kết nối DB có sẵn.

    Returns:
        int: Số lượng báo cáo đã được cập nhật.

    Raises:
        DatabaseError: Nếu có lỗi DB.
        ValidationError: Nếu trạng thái mới không hợp lệ.
    """
    log_prefix = f"[REPORT_UPDATE_FOR_CARD|CardID:{flashcard_id}|NewStatus:{new_status}]"
    logger.info(f"{log_prefix} Cập nhật trạng thái cho các báo cáo của thẻ.")

    valid_statuses = ['pending', 'resolved', 'rejected', 'acknowledged']
    if new_status not in valid_statuses:
        raise ValidationError(f"Trạng thái '{new_status}' không hợp lệ.")

    internal_conn = None
    should_close_conn = False
    should_commit = False
    rows_affected = 0

    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True

        cursor = conn.cursor()
        resolved_at_ts = int(time.time()) if new_status != 'pending' else None

        # Câu lệnh UPDATE nhắm vào các report của flashcard_id và có status là 'pending'
        query = """
            UPDATE CardReports
            SET status = ?, resolved_at = ?, resolver_user_id = ?
            WHERE flashcard_id = ? AND status = 'pending'
        """
        params = (new_status, resolved_at_ts, resolver_user_id, flashcard_id)

        logger.debug(f"{log_prefix} Executing query: {query.strip()} with params: {params}")
        cursor.execute(query, params)
        rows_affected = cursor.rowcount

        if should_commit:
            conn.commit()
            logger.debug(f"{log_prefix} Commit cập nhật trạng thái cho thẻ.")

        if rows_affected > 0:
            logger.info(f"{log_prefix} Cập nhật thành công {rows_affected} báo cáo cho thẻ {flashcard_id}.")
        else:
            logger.info(f"{log_prefix} Không tìm thấy báo cáo nào ở trạng thái 'pending' cho thẻ {flashcard_id} để cập nhật.")

        return rows_affected

    except sqlite3.Error as e_db:
        logger.error(f"{log_prefix} Lỗi SQLite: {e_db}", exc_info=True)
        if should_commit and conn:
            conn.rollback()
        raise DatabaseError("Lỗi SQLite khi cập nhật trạng thái báo cáo cho thẻ.", original_exception=e_db)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        if should_commit and conn:
            conn.rollback()
        if isinstance(e, (DatabaseError, ValidationError)):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi cập nhật trạng thái báo cáo cho thẻ.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")