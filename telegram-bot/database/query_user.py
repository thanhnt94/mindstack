# File: flashcard-telegram-bot/database/query_user.py
"""
Module chứa các hàm truy vấn và cập nhật dữ liệu liên quan đến bảng Users.
Các hàm cập nhật cốt lõi sử dụng user_id (khóa chính), một số hàm tiện ích
vẫn nhận telegram_id và gọi hàm cốt lõi.
Đã thêm hàm get_user_by_id.
Đã sửa lỗi import timezone.
Đã sửa lỗi định dạng code (bỏ hoàn toàn ; nối lệnh, thụt lề đúng).
(Sửa lần 1: Thêm các cột mới cho thông báo vào UPDATABLE_USER_COLUMNS)
"""
import sqlite3
import logging
from datetime import datetime, timezone 
import time

# Import từ các module khác
from database.connection import database_connect
from config import (
    DAILY_LIMIT_USER,
    DAILY_LIMIT_LITE,
    DAILY_LIMIT_VIP,
    ROLE_PERMISSIONS,
    DEFAULT_LEARNING_MODE,
    DEFAULT_TIMEZONE_OFFSET
)
from utils.exceptions import (
    UserNotFoundError,
    DatabaseError,
    ValidationError,
    DuplicateError
)

logger = logging.getLogger(__name__)

# Danh sách các cột được phép truy vấn/cập nhật
ALLOWED_USER_COLUMNS = [
    "user_id", "telegram_id", "current_set_id", "default_side",
    "daily_new_limit", "user_role", "timezone_offset", "username",
    "created_at", "last_seen", "score", "password",
    "front_audio", "back_audio",
    "front_image_enabled", "back_image_enabled",
    "is_notification_enabled", "notification_interval_minutes",
    "last_notification_sent_time", "show_review_summary",
    "current_mode", "default_mode",
    # Thêm các cột mới từ schema Sửa lần 2
    "notification_target_set_id", "enable_morning_brief", "last_morning_brief_sent_date"
]

# Sửa lần 1: Thêm các cột mới vào UPDATABLE_USER_COLUMNS
UPDATABLE_USER_COLUMNS = [
    "current_set_id", "default_side", "daily_new_limit", "user_role",
    "timezone_offset", "username", "last_seen", "score", "password",
    "front_audio", "back_audio", "front_image_enabled", "back_image_enabled",
    "is_notification_enabled", "notification_interval_minutes",
    "last_notification_sent_time", "show_review_summary",
    "current_mode", "default_mode",
    "notification_target_set_id", # Cột mới
    "enable_morning_brief",       # Cột mới
    "last_morning_brief_sent_date" # Cột mới
]


def get_user_by_telegram_id(telegram_id_param, conn=None):
    """
    Lấy thông tin chi tiết user dựa trên telegram_id. Tự động tạo nếu chưa có.
    (Sửa lần 1: Thêm các cột mới vào default_insert_values khi tạo user)
    """
    log_prefix = f"[GET_USER_BY_TGID|TG:{telegram_id_param}]"
    internal_conn = None
    should_close_conn = False
    user_data_dict = None
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
        select_columns_str = ", ".join(f'"{col}"' for col in ALLOWED_USER_COLUMNS)
        select_query = f"SELECT {select_columns_str} FROM Users WHERE telegram_id = ?"
        logger.debug(f"{log_prefix} Executing SELECT with TG ID {telegram_id_param}")
        cursor.execute(select_query, (telegram_id_param,))
        user_row = cursor.fetchone()

        if user_row is None:
            logger.info(f"{log_prefix} User không tồn tại. Tạo mới...")
            if not should_close_conn: # Chỉ tạo mới nếu kết nối được quản lý nội bộ
                logger.error(f"{log_prefix} Không thể tạo user mới với connection ngoài.")
                raise UserNotFoundError(identifier=telegram_id_param, message="Không tìm thấy người dùng và không thể tạo mới với connection ngoài.")

            try:
                insert_columns = [col for col in ALLOWED_USER_COLUMNS if col != 'user_id']
                current_dt_utc = datetime.now(timezone.utc) 
                current_ts = int(current_dt_utc.timestamp())
                created_at_str = current_dt_utc.strftime("%Y-%m-%d %H:%M:%S")

                # Sửa lần 1: Thêm các cột mới vào giá trị mặc định khi tạo user
                default_insert_values = {
                    "telegram_id": telegram_id_param, "current_set_id": None, "default_side": 0,
                    "daily_new_limit": DAILY_LIMIT_USER, "user_role": 'user', "timezone_offset": DEFAULT_TIMEZONE_OFFSET,
                    "username": None, "created_at": created_at_str, "last_seen": current_ts, "score": 0, "password": None,
                    "front_audio": 1, "back_audio": 1, "front_image_enabled": 1, "back_image_enabled": 1,
                    "is_notification_enabled": 0, "notification_interval_minutes": 60, "last_notification_sent_time": None,
                    "show_review_summary": 1, "current_mode": DEFAULT_LEARNING_MODE, "default_mode": DEFAULT_LEARNING_MODE,
                    "notification_target_set_id": None, # Giá trị mặc định cho cột mới
                    "enable_morning_brief": 1,         # Giá trị mặc định cho cột mới
                    "last_morning_brief_sent_date": None # Giá trị mặc định cho cột mới
                }
                insert_cols_str = ", ".join(f'"{col}"' for col in insert_columns)
                insert_placeholders = ", ".join("?" * len(insert_columns))
                insert_query = f"INSERT INTO Users ({insert_cols_str}) VALUES ({insert_placeholders})"
                values_to_insert = tuple(default_insert_values.get(col) for col in insert_columns)

                logger.debug(f"{log_prefix} Executing INSERT: {values_to_insert}")
                cursor.execute(insert_query, values_to_insert)
                conn.commit() 
                logger.info(f"{log_prefix} Tạo user mới thành công.")

                logger.debug(f"{log_prefix} Lấy lại info user mới...")
                cursor.execute(select_query, (telegram_id_param,))
                user_row = cursor.fetchone()
                if user_row:
                    logger.debug(f"{log_prefix} Lấy lại info OK.")
                    user_data_dict = dict(user_row)
                else:
                    logger.error(f"{log_prefix} LỖI NGHIÊM TRỌNG: Không lấy lại được user sau khi tạo!")
                    raise DatabaseError("Lỗi không xác định sau khi tạo người dùng.")

            except sqlite3.IntegrityError as insert_err:
                logger.exception(f"{log_prefix} Lỗi Integrity khi tạo user: {insert_err}")
                try: conn.rollback()
                except Exception: pass
                raise DuplicateError("Lỗi tạo user: telegram_id hoặc username có thể đã tồn tại.", original_exception=insert_err)
            except sqlite3.Error as insert_err:
                logger.exception(f"{log_prefix} Lỗi SQLite khác khi tạo user: {insert_err}")
                try: conn.rollback()
                except Exception: pass
                raise DatabaseError("Lỗi SQLite khi tạo người dùng.", original_exception=insert_err)
            except Exception as insert_gen_err:
                logger.exception(f"{log_prefix} Lỗi không mong muốn khi tạo user: {insert_gen_err}")
                try: conn.rollback()
                except Exception: pass
                raise DatabaseError("Lỗi không mong muốn khi tạo người dùng.", original_exception=insert_gen_err)
        else:
            logger.debug(f"{log_prefix} User đã tồn tại.")
            user_data_dict = dict(user_row)

        if original_factory is not None:
            try: 
                conn.execute("SELECT 1") 
                conn.row_factory = original_factory
            except Exception: pass 

        if user_data_dict:
            return user_data_dict
        else:
            raise DatabaseError("Không thể lấy hoặc tạo dữ liệu người dùng.")

    except sqlite3.Error as e:
        logger.exception(f"{log_prefix} Lỗi SQLite tổng thể: {e}")
        raise DatabaseError("Lỗi SQLite khi lấy thông tin người dùng.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm: {e}")
        if isinstance(e, (DatabaseError, UserNotFoundError, DuplicateError)):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi lấy thông tin người dùng.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
             try: 
                 conn.execute("SELECT 1")
                 conn.row_factory = original_factory
             except Exception: pass 
        if should_close_conn and internal_conn:
            try: 
                internal_conn.close()
                logger.debug(f"{log_prefix} Đã đóng kết nối nội bộ.")
            except Exception as e_close:
                 logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")

def update_user_by_id(user_id_param, conn=None, **kwargs):
    """
    Cập nhật thông tin người dùng trong bảng Users dựa trên user_id (PK).
    """
    key_column = "user_id"
    user_identifier = user_id_param
    log_prefix = f"[USER_UPDATE|{key_column}={user_identifier}]"
    logger.debug(f"{log_prefix} Hàm được gọi với user_id={user_id_param}, kwargs={kwargs}")
    internal_conn = None
    should_close_conn = False
    should_commit = False
    rows_affected = 0
    update_fields_clauses = []
    values = []

    for key, value in kwargs.items():
        if key in UPDATABLE_USER_COLUMNS: # Kiểm tra với danh sách đã cập nhật
            update_fields_clauses.append(f'"{key}" = ?')
            values.append(value)
            logger.debug(f"{log_prefix} Thêm trường cập nhật: {key}={value}")
        elif key in ["user_id", "telegram_id", "created_at"]:
             logger.warning(f"{log_prefix} Không cho phép cập nhật cột '{key}'. Bỏ qua.")
        else:
            logger.warning(f"{log_prefix} Cột '{key}' không hợp lệ để cập nhật hoặc không có trong UPDATABLE_USER_COLUMNS.")

    if not update_fields_clauses:
        logger.warning(f"{log_prefix} Không có cột hợp lệ để cập nhật.")
        raise ValidationError("Không có cột hợp lệ nào được cung cấp để cập nhật.")

    values.append(user_identifier) 
    set_clause = ", ".join(update_fields_clauses)
    query = f'UPDATE "Users" SET {set_clause} WHERE "{key_column}" = ?'
    logger.debug(f"{log_prefix} Chuẩn bị thực thi SQL: {query}")
    logger.debug(f"{log_prefix} Với giá trị: {values}")

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
        rows_affected = cursor.rowcount
        logger.debug(f"{log_prefix} Thực thi xong. Số hàng bị ảnh hưởng: {rows_affected}")

        if should_commit:
            conn.commit()
            logger.debug(f"{log_prefix} Đã commit.")

        if rows_affected > 0:
            logger.info(f"{log_prefix} Update thành công ({rows_affected} hàng).")
        else:
            logger.warning(f"{log_prefix} Không tìm thấy user hoặc dữ liệu không thay đổi.")

        return rows_affected

    except sqlite3.IntegrityError as e:
        logger.exception(f"{log_prefix} Lỗi Integrity: {e}")
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass 
        raise DuplicateError("Lỗi ràng buộc dữ liệu khi cập nhật user.", original_exception=e)
    except sqlite3.OperationalError as e:
        logger.exception(f"{log_prefix} Lỗi Operational: {e}")
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        raise DatabaseError("Lỗi Operational khi cập nhật user.", original_exception=e)
    except sqlite3.Error as e:
        logger.exception(f"{log_prefix} Lỗi SQLite khác: {e}")
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        raise DatabaseError("Lỗi SQLite khi cập nhật user.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm: {e}")
        if should_commit and conn:
            try: conn.rollback()
            except Exception: pass
        if isinstance(e, (DatabaseError, DuplicateError, ValidationError)):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi cập nhật user.", original_exception=e)
    finally:
        if should_close_conn and internal_conn:
            try: 
                internal_conn.close()
                logger.debug(f"{log_prefix} Đã đóng kết nối nội bộ.")
            except Exception as e_close:
                 logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")

def update_user_by_telegram_id(telegram_id_param, conn=None, **kwargs):
    """Cập nhật thông tin người dùng dựa trên telegram_id."""
    log_prefix = f"[USER_UPDATE_BY_TG|TG:{telegram_id_param}]"
    logger.debug(f"{log_prefix} Tìm user_id để cập nhật. Dữ liệu: {kwargs}")
    internal_conn = None
    should_close_temp_conn = False
    rows_affected = -1
    temp_conn_for_get = conn
    try:
        if temp_conn_for_get is None:
            temp_conn_for_get = database_connect()
            if temp_conn_for_get is None:
                 raise DatabaseError("Không thể kết nối DB để lấy user_id.")
            should_close_temp_conn = True

        user_info = get_user_by_telegram_id(telegram_id_param, conn=temp_conn_for_get)
        target_user_id = user_info['user_id']
        logger.debug(f"{log_prefix} Tìm thấy user_id: {target_user_id}")

        if should_close_temp_conn and temp_conn_for_get:
             temp_conn_for_get.close()
             logger.debug(f"{log_prefix} Đã đóng kết nối tạm sau khi lấy user_id.")
             temp_conn_for_get = None 

        rows_affected = update_user_by_id(target_user_id, conn=conn, **kwargs)
        return rows_affected

    except (UserNotFoundError, DatabaseError, DuplicateError, ValidationError) as e:
        logger.error(f"{log_prefix} Lỗi DB/User/Validation khi cập nhật bằng telegram_id: {e}")
        raise e
    except Exception as e: 
        logger.exception(f"{log_prefix} Lỗi không mong muốn khi cập nhật bằng telegram_id: {e}")
        raise DatabaseError("Lỗi không mong muốn khi cập nhật user bằng telegram_id.", original_exception=e)
    finally:
        if should_close_temp_conn and temp_conn_for_get:
             try: 
                 temp_conn_for_get.close()
                 logger.debug(f"{log_prefix} Đã đóng kết nối tạm trong finally.")
             except Exception as e_close_final:
                  logger.error(f"{log_prefix} Lỗi đóng kết nối tạm trong finally: {e_close_final}")

def get_all_users(pagination=None):
    """Lấy danh sách người dùng, hỗ trợ phân trang."""
    log_prefix = "[GET_ALL_USERS]"
    conn = None; users_data = []; limit = None; offset = None; original_factory = None
    if pagination is not None:
        if not isinstance(pagination, tuple) or len(pagination) != 2: raise ValidationError("pagination phải là tuple (page, limit).")
        page, limit_val = pagination
        if not isinstance(page, int) or not isinstance(limit_val, int) or page < 1 or limit_val < 1: raise ValidationError("page và limit phải là số nguyên >= 1.")
        limit = limit_val; offset = (page - 1) * limit; logger.debug(f"{log_prefix} Phân trang: page={page}, limit={limit}, offset={offset}")
    try:
        conn = database_connect();
        if conn is None: raise DatabaseError("Không thể tạo kết nối database.")
        original_factory = conn.row_factory; conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        select_all_columns_str = ", ".join(f'"{col}"' for col in ALLOWED_USER_COLUMNS)
        if pagination is None:
            query = f"SELECT {select_all_columns_str} FROM Users ORDER BY user_id"; logger.debug(f"{log_prefix} Lấy tất cả user."); cursor.execute(query)
        else:
            query = f"SELECT {select_all_columns_str} FROM Users ORDER BY user_id LIMIT ? OFFSET ?"; logger.debug(f"{log_prefix} Lấy user limit={limit}, offset={offset}"); cursor.execute(query, (limit, offset))
        users_rows = cursor.fetchall(); logger.info(f"{log_prefix} Lấy được {len(users_rows)} bản ghi.")
        users_data = [dict(user_row) for user_row in users_rows]
    except sqlite3.Error as e: logger.error(f"{log_prefix} Lỗi DB: {e}"); raise DatabaseError("Lỗi SQLite khi lấy danh sách user.", original_exception=e)
    except Exception as e: 
        logger.error(f"{log_prefix} Lỗi trong hàm: {e}", exc_info=True)
        if isinstance(e, (DatabaseError, ValidationError)): raise e
        raise DatabaseError("Lỗi không mong muốn khi lấy danh sách user.", original_exception=e)
    finally:
        if conn:
            if original_factory is not None:
                 try: conn.execute("SELECT 1"); conn.row_factory = original_factory
                 except Exception: pass
            conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối.")
    return users_data

def update_user_role(telegram_id_param, new_role):
    """Thiết lập vai trò mới cho người dùng dựa trên telegram_id."""
    log_prefix = f"[UPDATE_USER_ROLE|TG:{telegram_id_param}]"; logger.debug(f"Đang thiết lập role cho user TG:{telegram_id_param} thành '{new_role}'")
    if new_role not in ROLE_PERMISSIONS.keys(): logger.warning(f"{log_prefix} Vai trò '{new_role}' không hợp lệ."); raise ValidationError(f"Vai trò '{new_role}' không hợp lệ.")
    conn = None; rows_affected = -1
    try:
        conn = database_connect();
        if conn is None: raise DatabaseError("Không thể kết nối DB để cập nhật role.")
        logger.debug(f"{log_prefix} Lấy user_id..."); user_info = get_user_by_telegram_id(telegram_id_param, conn=conn); target_user_id = user_info['user_id']; logger.debug(f"{log_prefix} Tìm thấy user_id: {target_user_id}")
        logger.debug(f"{log_prefix} Gọi update_user_by_id...")
        rows_affected = update_user_by_id(target_user_id, conn=conn, user_role=new_role)
        if rows_affected > 0: logger.info(f"{log_prefix} Đã thiết lập role thành công."); return True
        else: logger.warning(f"{log_prefix} Không có hàng nào bị ảnh hưởng (role không đổi?)."); return False
    except (UserNotFoundError, DatabaseError, DuplicateError, ValidationError) as e: logger.error(f"{log_prefix} Lỗi DB/Validation/NotFound khi thiết lập role: {e}"); raise e
    except Exception as e: 
        logger.exception(f"{log_prefix} Lỗi không mong muốn khi thiết lập role: {e}"); raise DatabaseError("Lỗi không mong muốn khi thiết lập vai trò.", original_exception=e)
    finally:
        if conn: conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối.")

def update_user_daily_limit(telegram_id_param, new_limit):
    """Cập nhật giới hạn thẻ mới/ngày cho người dùng dựa trên telegram_id."""
    log_prefix = f"[UPDATE_DAILY_LIMIT|TG:{telegram_id_param}]"; logger.debug(f"Cập nhật daily_limit -> {new_limit}")
    if not isinstance(new_limit, int) or new_limit < 0: logger.error(f"{log_prefix} Giới hạn không hợp lệ: {new_limit}."); raise ValidationError("Giới hạn không hợp lệ. Phải là số nguyên >= 0.")
    conn = None; rows_affected = -1
    try:
        conn = database_connect();
        if conn is None: raise DatabaseError("Không thể kết nối DB để cập nhật limit.")
        logger.debug(f"{log_prefix} Lấy user_id..."); user_info = get_user_by_telegram_id(telegram_id_param, conn=conn); target_user_id = user_info['user_id']; logger.debug(f"{log_prefix} Tìm thấy user_id: {target_user_id}")
        logger.debug(f"{log_prefix} Gọi update_user_by_id...")
        rows_affected = update_user_by_id(target_user_id, conn=conn, daily_new_limit=new_limit)
        if rows_affected > 0: logger.info(f"{log_prefix} Cập nhật daily_limit thành công."); return True
        else: logger.warning(f"{log_prefix} Không có hàng nào bị ảnh hưởng (limit không đổi?)."); return False
    except (UserNotFoundError, DatabaseError, DuplicateError, ValidationError) as e: logger.error(f"{log_prefix} Lỗi DB/Validation/NotFound khi cập nhật limit: {e}"); raise e
    except Exception as e: 
        logger.exception(f"{log_prefix} Lỗi không mong muốn khi cập nhật giới hạn: {e}"); raise DatabaseError("Lỗi không mong muốn khi cập nhật giới hạn.", original_exception=e)
    finally:
        if conn: conn.close(); logger.debug(f"{log_prefix} Đã đóng kết nối.")

def get_user_by_id(user_id_db, conn=None):
    """
    Lấy thông tin chi tiết user dựa trên user_id (khóa chính của bảng Users).
    """
    log_prefix = f"[GET_USER_BY_DB_ID|UID:{user_id_db}]"
    internal_conn = None
    should_close_conn = False
    user_data_dict = None
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
        select_columns_str = ", ".join(f'"{col}"' for col in ALLOWED_USER_COLUMNS)
        query = f"SELECT {select_columns_str} FROM Users WHERE user_id = ?"
        logger.debug(f"{log_prefix} Executing SELECT User by DB ID: {user_id_db}")
        cursor.execute(query, (user_id_db,))
        user_row = cursor.fetchone()

        if user_row:
            user_data_dict = dict(user_row)
            logger.debug(f"{log_prefix} Tìm thấy user.")
        else:
            logger.warning(f"{log_prefix} Không tìm thấy user với ID: {user_id_db}")
            user_data_dict = None 

    except sqlite3.Error as e:
        logger.exception(f"{log_prefix} Lỗi SQLite: {e}")
        raise DatabaseError("Lỗi SQLite khi lấy thông tin người dùng bằng user_id.", original_exception=e)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm: {e}")
        if isinstance(e, DatabaseError):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi lấy thông tin người dùng bằng user_id.", original_exception=e)
    finally:
        if original_factory is not None and conn is not None and not should_close_conn:
             try: 
                 conn.execute("SELECT 1")
                 conn.row_factory = original_factory
             except Exception: pass 
        if should_close_conn and internal_conn:
            try: 
                internal_conn.close()
                logger.debug(f"{log_prefix} Đã đóng kết nối nội bộ.")
            except Exception as e_close:
                 logger.error(f"{log_prefix} Lỗi đóng kết nối nội bộ: {e_close}")

    return user_data_dict
