"""
Module chứa các hàm CRUD (Create, Read, Update, Delete) chung
và các hàm thao tác cơ sở dữ liệu cơ bản khác.
(Đã cập nhật để sử dụng Exception thay vì trả về mã lỗi/None)
"""
import sqlite3
import logging
from database.connection import database_connect
from utils.exceptions import (
    DatabaseError,
    ValidationError,
    DuplicateError
)
logger = logging.getLogger(__name__)
def fetch_records(table_name, return_type='dict', conn=None, **kwargs):
    """
    Lấy (các) bản ghi từ một bảng dựa trên các điều kiện lọc.
    Args:
        table_name (str): Tên của bảng cần truy vấn.
        return_type (str, optional): Kiểu dữ liệu trả về ('dict' hoặc 'tuple'). Mặc định là 'dict'.
        conn (sqlite3.Connection, optional): Đối tượng kết nối DB có sẵn.
        **kwargs: Các cặp key-value tương ứng với tên cột và giá trị cần lọc.
                  Nếu giá trị bắt đầu bằng '*', sẽ sử dụng LIKE thay vì =.
    Returns:
        list: Danh sách các bản ghi tìm thấy (dạng dict hoặc tuple),
              hoặc danh sách rỗng nếu không tìm thấy.
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
    """
    log_prefix = f"[DB_FETCH|{table_name}]"
    internal_conn = None
    should_close_conn = False
    rows_data = []
    original_factory = None 
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            if return_type == 'dict':
                conn.row_factory = sqlite3.Row
            else:
                conn.row_factory = None 
        else:
             original_factory = conn.row_factory
             if return_type == 'dict':
                 conn.row_factory = sqlite3.Row
             else:
                 conn.row_factory = None 
        cursor = conn.cursor()
        query = f'SELECT * FROM "{table_name}" WHERE 1=1' 
        parameters = []
        for key, value in kwargs.items():
            if isinstance(value, str) and value.startswith('*'):
                query += f' AND "{key}" LIKE ?'
                parameters.append(f"%{value[1:]}%")
            else:
                query += f' AND "{key}" = ?'
                parameters.append(value)
        logger.debug(f"{log_prefix} Executing query: {query} with params: {parameters}")
        cursor.execute(query, parameters)
        rows = cursor.fetchall()
        logger.debug(f"{log_prefix} Fetched {len(rows)} rows.")
        if return_type == 'dict':
            if rows and isinstance(rows[0], sqlite3.Row):
                 rows_data = [dict(row) for row in rows]
            elif rows: 
                 column_names = [description[0] for description in cursor.description]
                 rows_data = [dict(zip(column_names, row)) for row in rows]
            else: 
                 rows_data = []
        else:
            rows_data = rows 
        if original_factory is not None:
            conn.row_factory = original_factory
        return rows_data 
    except sqlite3.Error as e:
        logger.error(f"{log_prefix} Lỗi database: {e}")
        raise DatabaseError(f"Lỗi SQLite khi fetch từ bảng '{table_name}'.", original_exception=e)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi trong hàm: {e}", exc_info=True)
        if isinstance(e, DatabaseError):
            raise e
        raise DatabaseError(f"Lỗi không mong muốn khi fetch từ bảng '{table_name}'.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None:
             try:
                 conn.execute("SELECT 1")
                 conn.row_factory = original_factory
             except:
                 pass
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")
def update_record_by_id(table_name, record_id, key_column="id", conn=None, **kwargs):
    """
    Cập nhật một bản ghi trong bảng dựa trên ID (hoặc cột khóa chính được chỉ định).
    Args:
        table_name (str): Tên bảng cần cập nhật.
        record_id: Giá trị của khóa chính của bản ghi cần cập nhật.
        key_column (str, optional): Tên cột khóa chính. Mặc định là "id".
        conn (sqlite3.Connection, optional): Đối tượng kết nối DB có sẵn.
        **kwargs: Các cặp key-value chứa tên cột và giá trị mới cần cập nhật.
    Returns:
        int: Số lượng hàng bị ảnh hưởng (thường là 1 nếu thành công, 0 nếu không tìm thấy).
    Raises:
        ValidationError: Nếu không có trường hợp lệ nào để cập nhật.
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite khác xảy ra.
        DuplicateError: Nếu có lỗi ràng buộc dữ liệu (ví dụ: UNIQUE constraint).
    """
    log_prefix = f"[DB_UPDATE|{table_name}|{key_column}={record_id}]"
    internal_conn = None
    should_close_conn = False
    should_commit = False
    rows_affected = 0 
    if not kwargs:
        logger.warning(f"{log_prefix} Không có trường nào được cung cấp để cập nhật.")
        raise ValidationError("Không có trường nào được cung cấp để cập nhật.")
    update_clauses = []
    parameters = []
    for key, value in kwargs.items():
        update_clauses.append(f'"{key}" = ?')
        parameters.append(value)
    parameters.append(record_id)
    set_clause = ", ".join(update_clauses)
    query = f'UPDATE "{table_name}" SET {set_clause} WHERE "{key_column}" = ?'
    logger.debug(f"{log_prefix} Executing query: {query} with params: {parameters}")
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True
        cursor = conn.cursor()
        cursor.execute(query, parameters)
        rows_affected = cursor.rowcount
        if should_commit:
            conn.commit()
            logger.debug(f"{log_prefix} Thay đổi đã được commit (kết nối nội bộ).")
        if rows_affected > 0:
            logger.info(f"{log_prefix} Cập nhật hoàn tất. Số hàng bị ảnh hưởng: {rows_affected}.")
        else:
            logger.warning(f"{log_prefix} Không tìm thấy bản ghi hoặc dữ liệu không thay đổi (0 hàng bị ảnh hưởng).")
        return rows_affected 
    except sqlite3.IntegrityError as e:
        logger.error(f"{log_prefix} Lỗi database Integrity: {e}")
        if should_commit and conn:
            try: conn.rollback(); logger.warning(f"{log_prefix} Đã rollback thay đổi do lỗi.")
            except Exception: pass
        raise DuplicateError(f"Lỗi ràng buộc dữ liệu khi cập nhật bảng '{table_name}'.", original_exception=e)
    except sqlite3.Error as e:
        logger.error(f"{log_prefix} Lỗi database khác: {e}")
        if should_commit and conn:
            try: conn.rollback(); logger.warning(f"{log_prefix} Đã rollback thay đổi do lỗi.")
            except Exception: pass
        raise DatabaseError(f"Lỗi SQLite khi cập nhật bảng '{table_name}'.", original_exception=e)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi trong hàm: {e}", exc_info=True)
        if should_commit and conn:
            try: conn.rollback(); logger.warning(f"{log_prefix} Đã rollback thay đổi do lỗi không mong muốn.")
            except Exception: pass
        if isinstance(e, (DatabaseError, ValidationError, DuplicateError)):
            raise e
        raise DatabaseError(f"Lỗi không mong muốn khi cập nhật bảng '{table_name}'.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")
def insert_record(table_name, conn=None, **kwargs):
    """
    Chèn một bản ghi mới vào bảng được chỉ định.
    Args:
        table_name (str): Tên bảng cần chèn dữ liệu.
        conn (sqlite3.Connection, optional): Đối tượng kết nối DB có sẵn.
        **kwargs: Các cặp key-value chứa tên cột và giá trị cần chèn.
    Returns:
        int: ID của bản ghi vừa được chèn (nếu thành công và bảng có rowid).
    Raises:
        ValidationError: Nếu không có dữ liệu để chèn.
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite khác xảy ra.
        DuplicateError: Nếu có lỗi ràng buộc dữ liệu (ví dụ: UNIQUE constraint).
    """
    log_prefix = f"[DB_INSERT|{table_name}]"
    internal_conn = None
    should_close_conn = False
    should_commit = False
    last_row_id = None 
    if not kwargs:
        logger.warning(f"{log_prefix} Không có dữ liệu để chèn.")
        raise ValidationError("Không có dữ liệu được cung cấp để chèn.")
    columns = ', '.join(f'"{k}"' for k in kwargs.keys())
    placeholders = ', '.join(['?'] * len(kwargs))
    values = tuple(kwargs.values())
    query = f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})'
    logger.debug(f"{log_prefix} Executing query: {query} with values: {values}")
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True
        cursor = conn.cursor()
        cursor.execute(query, values)
        last_row_id = cursor.lastrowid
        if last_row_id is None or last_row_id <= 0:
            logger.warning(f"{log_prefix} Không nhận được lastrowid hợp lệ sau khi INSERT.")
            raise DatabaseError(f"Không nhận được lastrowid hợp lệ sau khi chèn vào bảng '{table_name}'.")
        if should_commit:
            conn.commit()
            logger.debug(f"{log_prefix} Thay đổi đã được commit (kết nối nội bộ).")
        logger.info(f"{log_prefix} Đã chèn bản ghi mới thành công. Last row ID: {last_row_id}.")
        return int(last_row_id) 
    except sqlite3.IntegrityError as e:
         logger.error(f"{log_prefix} Lỗi ràng buộc dữ liệu (IntegrityError): {e}")
         if should_commit and conn:
             try: conn.rollback()
             except Exception: pass
         raise DuplicateError(f"Lỗi ràng buộc dữ liệu khi chèn vào bảng '{table_name}'.", original_exception=e)
    except sqlite3.Error as e:
        logger.error(f"{log_prefix} Lỗi database khác: {e}")
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        raise DatabaseError(f"Lỗi SQLite khi chèn vào bảng '{table_name}'.", original_exception=e)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi trong hàm: {e}", exc_info=True)
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        if isinstance(e, (DatabaseError, ValidationError, DuplicateError)):
            raise e
        raise DatabaseError(f"Lỗi không mong muốn khi chèn vào bảng '{table_name}'.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")
def delete_records_by_id(table_name, record_ids, key_column="id", conn=None):
    """
    Xóa (các) bản ghi khỏi bảng dựa trên danh sách ID (hoặc cột khóa được chỉ định).
    Args:
        table_name (str): Tên bảng cần xóa bản ghi.
        record_ids (list | int): Danh sách các giá trị khóa chính cần xóa, hoặc một giá trị đơn lẻ.
        key_column (str, optional): Tên cột khóa chính. Mặc định là "id".
        conn (sqlite3.Connection, optional): Đối tượng kết nối DB có sẵn.
    Returns:
        int: Số lượng hàng bị ảnh hưởng.
    Raises:
        ValidationError: Nếu danh sách ID rỗng.
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
    """
    log_prefix = f"[DB_DELETE|{table_name}|{key_column}]"
    internal_conn = None
    should_close_conn = False
    should_commit = False
    rows_affected = 0 
    if not isinstance(record_ids, list):
        record_ids_list = [record_ids]
    else:
        record_ids_list = record_ids
    if not record_ids_list:
        logger.warning(f"{log_prefix} Danh sách ID cần xóa rỗng.")
        raise ValidationError("Danh sách ID cần xóa không được rỗng.")
    placeholders = ', '.join('?' * len(record_ids_list))
    query = f'DELETE FROM "{table_name}" WHERE "{key_column}" IN ({placeholders})'
    logger.debug(f"{log_prefix} Executing query: {query} with IDs: {record_ids_list}")
    try:
        if conn is None:
            internal_conn = database_connect()
            if internal_conn is None:
                raise DatabaseError("Không thể tạo kết nối database nội bộ.")
            conn = internal_conn
            should_close_conn = True
            should_commit = True
        cursor = conn.cursor()
        cursor.execute(query, record_ids_list)
        rows_affected = cursor.rowcount
        if should_commit:
            conn.commit()
            logger.debug(f"{log_prefix} Thay đổi đã được commit (kết nối nội bộ).")
        logger.info(f"{log_prefix} Đã xóa {rows_affected} bản ghi.")
        return rows_affected 
    except sqlite3.Error as e:
        logger.error(f"{log_prefix} Lỗi database: {e}")
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        raise DatabaseError(f"Lỗi SQLite khi xóa từ bảng '{table_name}'.", original_exception=e)
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi trong hàm: {e}", exc_info=True)
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        if isinstance(e, (DatabaseError, ValidationError)):
            raise e
        raise DatabaseError(f"Lỗi không mong muốn khi xóa từ bảng '{table_name}'.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            internal_conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB nội bộ.")
def create_table(table_name, columns):
    """Tạo một bảng mới nếu nó chưa tồn tại."""
    conn = None
    try:
        conn = database_connect()
        if conn is None:
            raise DatabaseError(f"Không thể kết nối DB để tạo bảng '{table_name}'.")
        c = conn.cursor()
        columns_definition = ', '.join(columns)
        query = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns_definition})'
        c.execute(query)
        conn.commit()
        logger.info(f"Bảng {table_name} đã được tạo (hoặc đã tồn tại).")
    except sqlite3.Error as e:
        logger.error(f"Lỗi database khi tạo bảng {table_name}: {e}")
        if conn: conn.rollback()
        raise DatabaseError(f"Lỗi SQLite khi tạo bảng '{table_name}'.", original_exception=e)
    except Exception as e:
        logger.error(f"Lỗi không mong muốn khi tạo bảng {table_name}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise DatabaseError(f"Lỗi không mong muốn khi tạo bảng '{table_name}'.", original_exception=e)
    finally:
        if conn: conn.close()
def drop_table(table_name):
    """Xóa một bảng nếu nó tồn tại. Cẩn thận khi sử dụng!"""
    conn = None
    try:
        conn = database_connect()
        if conn is None:
            raise DatabaseError(f"Không thể kết nối DB để xóa bảng '{table_name}'.")
        c = conn.cursor()
        query = f'DROP TABLE IF EXISTS "{table_name}"'
        c.execute(query)
        conn.commit()
        logger.info(f"Bảng {table_name} đã được xóa (nếu tồn tại).")
    except sqlite3.Error as e:
        logger.error(f"Lỗi database khi xóa bảng {table_name}: {e}")
        if conn: conn.rollback()
        raise DatabaseError(f"Lỗi SQLite khi xóa bảng '{table_name}'.", original_exception=e)
    except Exception as e:
        logger.error(f"Lỗi không mong muốn khi xóa bảng {table_name}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise DatabaseError(f"Lỗi không mong muốn khi xóa bảng '{table_name}'.", original_exception=e)
    finally:
        if conn: conn.close()
def add_table_column(table_name, column_definition):
    """Thêm một cột mới vào bảng đã tồn tại."""
    conn = None
    try:
        conn = database_connect()
        if conn is None:
             raise DatabaseError(f"Không thể kết nối DB để thêm cột vào bảng '{table_name}'.")
        c = conn.cursor()
        query = f'ALTER TABLE "{table_name}" ADD COLUMN {column_definition}' 
        c.execute(query)
        conn.commit()
        logger.info(f"Đã thêm cột '{column_definition}' vào bảng {table_name}.")
    except sqlite3.Error as e:
        logger.error(f"Lỗi database khi thêm cột vào bảng {table_name}: {e}")
        if conn: conn.rollback()
        raise DatabaseError(f"Lỗi SQLite khi thêm cột vào bảng '{table_name}'.", original_exception=e)
    except Exception as e:
        logger.error(f"Lỗi không mong muốn khi thêm cột vào bảng {table_name}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise DatabaseError(f"Lỗi không mong muốn khi thêm cột vào bảng '{table_name}'.", original_exception=e)
    finally:
        if conn: conn.close()
def rename_table_column(table_name, old_column_name, new_column_definition):
    """Đổi tên (và có thể cả định nghĩa) một cột trong bảng."""
    logger.warning(f"Hàm rename_table_column sử dụng phương pháp tạo lại bảng, có thể không an toàn hoặc thiếu sót. Cần kiểm tra kỹ lưỡng.")
    conn = None
    try:
        conn = database_connect()
        if conn is None:
            raise DatabaseError(f"Không thể kết nối DB để đổi tên cột bảng '{table_name}'.")
        c = conn.cursor()
        new_table_name = f"{table_name}_new"
        c.execute(f'PRAGMA table_info("{table_name}")')
        columns = c.fetchall()
        new_columns_defs = []
        old_columns_names_list = []
        new_columns_names_list = []
        found_old = False
        for column in columns:
            current_name = column[1]
            old_columns_names_list.append(f'"{current_name}"')
            if current_name == old_column_name:
                new_columns_defs.append(new_column_definition)
                new_name = new_column_definition.split()[0]
                new_columns_names_list.append(f'"{new_name}"')
                found_old = True
            else:
                col_def = f'"{column[1]}" {column[2]}'
                if column[3]: col_def += " NOT NULL"
                if column[4] is not None: col_def += f" DEFAULT {column[4]}" 
                if column[5]: col_def += " PRIMARY KEY"
                new_columns_defs.append(col_def)
                new_columns_names_list.append(f'"{current_name}"')
        if not found_old:
             logger.error(f"Không tìm thấy cột cũ '{old_column_name}' trong bảng {table_name}.")
             raise ValueError(f"Không tìm thấy cột '{old_column_name}' trong bảng '{table_name}'.")
        new_columns_definition_str = ', '.join(new_columns_defs)
        old_columns_names_str = ', '.join(old_columns_names_list)
        new_columns_names_str = ', '.join(new_columns_names_list) 
        conn.execute("BEGIN TRANSACTION;")
        logger.debug(f"Creating new table {new_table_name} with columns: {new_columns_definition_str}")
        c.execute(f'CREATE TABLE "{new_table_name}" ({new_columns_definition_str})')
        logger.debug(f"Copying data from {table_name} to {new_table_name}...")
        c.execute(f'INSERT INTO "{new_table_name}" ({new_columns_names_str}) SELECT {old_columns_names_str} FROM "{table_name}"')
        logger.debug(f"Dropping old table {table_name}...")
        c.execute(f'DROP TABLE "{table_name}"')
        logger.debug(f"Renaming {new_table_name} to {table_name}...")
        c.execute(f'ALTER TABLE "{new_table_name}" RENAME TO "{table_name}"')
        conn.commit()
        logger.info(f"Đã đổi tên cột {old_column_name} thành '{new_column_definition}' trong bảng {table_name} (thông qua tạo lại bảng).")
    except sqlite3.Error as e:
        logger.error(f"Lỗi database khi đổi tên cột trong bảng {table_name}: {e}")
        if conn: conn.rollback()
        raise DatabaseError(f"Lỗi SQLite khi đổi tên cột bảng '{table_name}'.", original_exception=e)
    except Exception as e:
        logger.error(f"Lỗi không mong muốn khi đổi tên cột trong bảng {table_name}: {e}", exc_info=True)
        if conn: conn.rollback()
        if isinstance(e, (DatabaseError, ValueError)):
            raise e
        raise DatabaseError(f"Lỗi không mong muốn khi đổi tên cột bảng '{table_name}'.", original_exception=e)
    finally:
        if conn: conn.close()
def get_table_info(table_name):
    """Lấy và in ra thông tin cấu trúc của một bảng."""
    conn = None
    columns = None
    try:
        conn = database_connect()
        if conn is None:
            raise DatabaseError(f"Không thể kết nối DB để lấy thông tin bảng '{table_name}'.")
        c = conn.cursor()
        c.execute(f'PRAGMA table_info("{table_name}")')
        columns = c.fetchall()
        logger.info(f"Cấu trúc bảng {table_name}: {columns}")
        return columns 
    except sqlite3.Error as e:
        logger.error(f"Lỗi database khi lấy thông tin bảng {table_name}: {e}")
        raise DatabaseError(f"Lỗi SQLite khi lấy thông tin bảng '{table_name}'.", original_exception=e)
    except Exception as e:
        logger.error(f"Lỗi không mong muốn khi lấy thông tin bảng {table_name}: {e}", exc_info=True)
        raise DatabaseError(f"Lỗi không mong muốn khi lấy thông tin bảng '{table_name}'.", original_exception=e)
    finally:
        if conn: conn.close()