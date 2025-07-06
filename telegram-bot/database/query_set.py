# File: flashcard-telegram-bot/database/query_set.py
"""
Module chứa các hàm truy vấn và thao tác dữ liệu liên quan đến
bảng VocabularySets, sử dụng user_id làm khóa ngoại chính cho người tạo.
(Sửa lần 1: Đổi tên _display_set_deletion_menu_by_id_and_owner thành delete_set_by_id_and_owner)
"""
import sqlite3
import logging
from database.connection import database_connect
from utils.exceptions import (
    DatabaseError,
    SetNotFoundError,
    UserNotFoundError, 
    PermissionsError
)
logger = logging.getLogger(__name__)

def get_sets(columns=None, creator_user_id=None, set_id=None, conn=None, limit=None, offset=None):
    """
    Lấy thông tin của một hoặc nhiều bộ từ vựng (VocabularySets), hỗ trợ phân trang.
    """
    log_prefix = f"[get_sets|Set:{set_id}|CreatorUID:{creator_user_id}|Limit:{limit}|Offset:{offset}]"
    internal_conn = None; should_close_conn = False; result_data = []; total_count = 0; original_factory = None
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None: raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn; should_close_conn = True; conn.row_factory = sqlite3.Row
        else:
             original_factory = conn.row_factory; conn.row_factory = sqlite3.Row 
        cursor = conn.cursor(); where_clauses = []; params = []
        if set_id is not None: where_clauses.append('"set_id" = ?'); params.append(set_id)
        if creator_user_id is not None: where_clauses.append('"creator_user_id" = ?'); params.append(creator_user_id) 
        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        count_query = f'SELECT COUNT(*) as count FROM "VocabularySets"{where_sql}'
        logger.debug(f"{log_prefix} Executing COUNT query: {count_query} with params: {params}")
        cursor.execute(count_query, params); count_row = cursor.fetchone()
        total_count = count_row['count'] if count_row else 0
        logger.debug(f"{log_prefix} Total matching sets: {total_count}")
        if total_count > 0 or set_id is not None: 
            cols_str = ", ".join(f'"{c}"' for c in columns) if columns else "*"
            query = f'SELECT {cols_str} FROM "VocabularySets"{where_sql} ORDER BY "title" COLLATE NOCASE'
            limit_params = []
            if limit is not None and isinstance(limit, int) and limit > 0:
                query += " LIMIT ?"; limit_params.append(limit)
                if offset is not None and isinstance(offset, int) and offset >= 0: query += " OFFSET ?"; limit_params.append(offset)
                else: query += " OFFSET ?"; limit_params.append(0) 
            final_params = params + limit_params
            logger.debug(f"{log_prefix} Executing SELECT query: {query} with params: {final_params}")
            cursor.execute(query, final_params); rows = cursor.fetchall()
            logger.debug(f"{log_prefix} Fetched {len(rows)} rows for this page.")
            if set_id is not None:
                if rows: result_data = [dict(rows[0])]
                else: raise SetNotFoundError(set_id=set_id)
            else: result_data = [dict(row) for row in rows]
        else: result_data = []
        if original_factory is not None: conn.row_factory = original_factory
        return result_data, total_count
    except sqlite3.Error as e: logger.error(f"{log_prefix} Lỗi database: {e}", exc_info=True); raise DatabaseError("Lỗi SQLite khi truy vấn bộ từ.", original_exception=e)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi trong hàm: {e}", exc_info=True)
        if isinstance(e, (DatabaseError, SetNotFoundError)): raise e
        raise DatabaseError("Lỗi không mong muốn khi truy vấn bộ từ.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
             try: conn.execute("SELECT 1"); conn.row_factory = original_factory
             except Exception: pass
        if should_close_conn and internal_conn: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")

def get_user_learned_set_ids(user_id, conn=None):
    """
    Lấy một tập hợp (set) chứa ID của các bộ từ mà người dùng đã học.
    """
    log_prefix = f"[GET_LEARNED_SETS|UserUID:{user_id}]" 
    logger.debug(f"{log_prefix} Bắt đầu lấy danh sách set ID đã học.")
    internal_conn = None; should_close_conn = False; learned_set_ids = set()
    try:
        if conn is None:
            internal_conn = database_connect();
            if internal_conn is None: raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn; should_close_conn = True
        cursor = conn.cursor()
        query_learned = "SELECT DISTINCT f.set_id FROM UserFlashcardProgress ufp JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id WHERE ufp.user_id = ?"
        logger.debug(f"{log_prefix} Executing query: {query_learned.strip()}")
        cursor.execute(query_learned, (user_id,))
        for row in cursor.fetchall():
            if row and row[0] is not None: learned_set_ids.add(int(row[0]))
        logger.info(f"{log_prefix} Tìm thấy {len(learned_set_ids)} set ID đã học.")
        return learned_set_ids
    except sqlite3.Error as e: logger.error(f"{log_prefix} Lỗi SQLite: {e}", exc_info=True); raise DatabaseError("Lỗi SQLite khi lấy danh sách bộ đã học.", original_exception=e)
    except Exception as e: logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True); raise DatabaseError("Lỗi không mong muốn khi lấy danh sách bộ đã học.", original_exception=e)
    finally:
        if should_close_conn and internal_conn: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")

# Sửa lần 1: Đổi tên hàm từ _display_set_deletion_menu_by_id_and_owner thành delete_set_by_id_and_owner
def delete_set_by_id_and_owner(set_id, deleter_user_id, conn=None):
    """
    Xóa một bộ từ vựng và tất cả dữ liệu liên quan (progress, notes, logs).
    Chỉ người tạo ra bộ từ (so sánh bằng user_id) mới có quyền xóa.
    Args:
        set_id (int): ID của bộ từ cần xóa.
        deleter_user_id (int): ID (khóa chính) của người yêu cầu xóa.
        conn (sqlite3.Connection, optional): Kết nối DB có sẵn (tùy chọn).
    Returns:
        list: Danh sách telegram_id của những người dùng đang học bộ này (để thông báo).
    Raises:
        DatabaseError, SetNotFoundError, PermissionsError, UserNotFoundError.
    """
    log_prefix = f"[DELETE_SET|Set:{set_id}|DeleterUID:{deleter_user_id}]"
    logger.info(f"{log_prefix} Bắt đầu xóa bộ từ {set_id} bởi người dùng UID:{deleter_user_id}")
    internal_conn = None; should_close_conn = False; should_commit = False
    affected_telegram_ids = []
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None: raise DatabaseError(f"Không thể kết nối database để xóa bộ từ.")
            conn = internal_conn; should_close_conn = True; should_commit = True
        
        # Sử dụng with conn để quản lý transaction nếu should_commit là True
        # Tuy nhiên, để logic commit rõ ràng hơn, sẽ commit thủ công nếu should_commit
        
        conn.execute("BEGIN TRANSACTION;") # Bắt đầu transaction thủ công
        logger.debug(f"{log_prefix} Bắt đầu TRANSACTION xóa.")
        cursor = conn.cursor()
        
        cursor.execute('SELECT creator_user_id FROM "VocabularySets" WHERE set_id = ?', (set_id,))
        record = cursor.fetchone() 
        if record is None: conn.rollback(); raise SetNotFoundError(set_id=set_id) 
        creator_id = record[0] # Truy cập bằng index vì không đặt row_factory cho cursor này
        if creator_id != deleter_user_id: conn.rollback(); raise PermissionsError(message=f"Người dùng UID:{deleter_user_id} không có quyền xóa bộ {set_id} (Owner UID:{creator_id}).")
        
        logger.debug(f"{log_prefix} Xác nhận quyền xóa. Bắt đầu xóa dữ liệu liên quan...")
        cursor.execute('SELECT telegram_id FROM "Users" WHERE current_set_id = ?', (set_id,))
        affected_telegram_ids = [row[0] for row in cursor.fetchall() if row and row[0] is not None] # Lấy telegram_id
        logger.debug(f"{log_prefix} User TG bị ảnh hưởng (current_set_id): {affected_telegram_ids}")
        
        if affected_telegram_ids: # Cập nhật current_set_id của họ thành NULL
             cursor.execute('UPDATE "Users" SET current_set_id = NULL WHERE current_set_id = ?', (set_id,))
             logger.debug(f"{log_prefix} Đặt NULL current_set_id cho {cursor.rowcount} user.")

        # Xóa dữ liệu liên quan theo đúng thứ tự (từ bảng con trước)
        cursor.execute('SELECT flashcard_id FROM "Flashcards" WHERE set_id = ?', (set_id,))
        flashcard_ids_tuples = cursor.fetchall()
        if flashcard_ids_tuples:
            flashcard_ids = [item[0] for item in flashcard_ids_tuples]
            placeholders = ','.join('?' * len(flashcard_ids))
            cursor.execute(f'DELETE FROM "UserFlashcardProgress" WHERE flashcard_id IN ({placeholders})', flashcard_ids)
            logger.debug(f"{log_prefix} Đã xóa {cursor.rowcount} bản ghi UserFlashcardProgress.")
            cursor.execute(f'DELETE FROM "FlashcardNotes" WHERE flashcard_id IN ({placeholders})', flashcard_ids)
            logger.debug(f"{log_prefix} Đã xóa {cursor.rowcount} bản ghi FlashcardNotes.")
        
        cursor.execute('DELETE FROM "DailyReviewLog" WHERE set_id = ?', (set_id,))
        logger.debug(f"{log_prefix} Đã xóa {cursor.rowcount} bản ghi DailyReviewLog.")
        cursor.execute('DELETE FROM "Flashcards" WHERE set_id = ?', (set_id,))
        deleted_flashcards_count = cursor.rowcount
        logger.debug(f"{log_prefix} Đã xóa {deleted_flashcards_count} bản ghi Flashcards.")
        
        # Cuối cùng xóa bộ từ
        cursor.execute('DELETE FROM "VocabularySets" WHERE set_id = ?', (set_id,))
        logger.info(f"{log_prefix} Đã xóa bộ {set_id} khỏi VocabularySets ({cursor.rowcount} hàng).")
        
        if should_commit:
            conn.commit()
            logger.info(f"{log_prefix} Đã COMMIT transaction xóa.")
        else: # Nếu là connection ngoài, không commit ở đây
            logger.info(f"{log_prefix} Hoàn thành các thao tác xóa trên connection ngoài (chưa commit).")
            
        return affected_telegram_ids
    except sqlite3.Error as e_delete: 
        logger.exception(f"{log_prefix} Lỗi SQLite khi xóa dữ liệu: {e_delete}")
        if conn and should_commit : conn.rollback(); logger.info(f"{log_prefix} Đã ROLLBACK do lỗi SQLite.")
        raise DatabaseError("Lỗi SQLite khi xóa dữ liệu bộ từ.", original_exception=e_delete)
    except Exception as e: 
        logger.exception(f"{log_prefix} Lỗi trong hàm xóa bộ từ {set_id}: {e}")
        if conn and should_commit: conn.rollback(); logger.info(f"{log_prefix} Đã ROLLBACK do lỗi không mong muốn.")
        if isinstance(e, (DatabaseError, SetNotFoundError, UserNotFoundError, PermissionsError)): raise e 
        raise DatabaseError("Lỗi không mong muốn khi xóa bộ từ.", original_exception=e)
    finally:
        if should_close_conn and internal_conn: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")

def get_users_by_current_set(set_id, conn=None):
    # Giữ nguyên logic
    log_prefix = f"[GET_USERS_USING|Set:{set_id}]"
    conn = None; affected_telegram_ids = []
    internal_conn = None; should_close_conn = False
    try:
        if conn is None:
            internal_conn = database_connect();
            if internal_conn is None: raise DatabaseError("Không thể kết nối database.")
            conn = internal_conn; should_close_conn = True
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id FROM "Users" WHERE current_set_id = ?', (set_id,))
        affected_telegram_ids = [row[0] for row in cursor.fetchall() if row and row[0] is not None] 
        logger.debug(f"{log_prefix} Tìm thấy {len(affected_telegram_ids)} người dùng: {affected_telegram_ids}")
        return affected_telegram_ids
    except sqlite3.Error as e: logger.exception(f"{log_prefix} Lỗi SQLite: {e}"); raise DatabaseError("Lỗi SQLite khi lấy người dùng theo bộ.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm: {e}")
        if isinstance(e, DatabaseError): raise e
        raise DatabaseError("Lỗi không mong muốn khi lấy người dùng theo bộ.", original_exception=e)
    finally:
        if should_close_conn and internal_conn: internal_conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối database.")
