# export_schema.py (Phiên bản đã sửa lỗi đường dẫn)

import os
import sqlite3
import sys

print("--- Thông tin Debug Mới ---")
# Lấy thư mục chứa script hiện tại (export_schema.py)
current_script_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Thư mục script hiện tại: {current_script_dir}")

# Xây dựng đường dẫn tuyệt đối đến thư mục 'web-app' (chứa gói Python 'web_app')
# Đây là thư mục mà chúng ta cần thêm vào sys.path để import 'web_app.config'
web_app_container_dir = os.path.join(current_script_dir, 'web-app')
print(f"Thư mục chứa gói 'web_app' cần thêm vào sys.path: {web_app_container_dir}")

# Thêm thư mục chứa gói 'web_app' vào sys.path
if web_app_container_dir not in sys.path:
    sys.path.insert(0, web_app_container_dir)
print(f"sys.path sau khi thêm thư mục web-app-container: {sys.path}")

# Đường dẫn dự kiến đến file config.py (chỉ để kiểm tra tồn tại)
expected_config_path_for_check = os.path.join(web_app_container_dir, 'web_app', 'config.py')
print(f"Đường dẫn dự kiến đến config.py để kiểm tra: {expected_config_path_for_check}")
print(f"File config.py tồn tại tại đường dẫn này: {os.path.exists(expected_config_path_for_check)}")
print("--------------------------")


# Import cấu hình từ web_app.config
try:
    # Với web_app_container_dir đã được thêm vào sys.path, Python có thể tìm thấy web_app
    from web_app.config import DATABASE_PATH
    print("Đã import DATABASE_PATH thành công từ web_app.config.")
except ImportError as e:
    print(f"Lỗi: Không tìm thấy module 'web_app' hoặc không thể import DATABASE_PATH. Chi tiết lỗi: {e}")
    sys.exit(1)
except AttributeError as e:
    print(f"Lỗi: Không tìm thấy DATABASE_PATH trong config.py. Chi tiết lỗi: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Đã xảy ra lỗi không mong muốn khi import config: {e}")
    sys.exit(1)

OUTPUT_SCHEMA_FILE = "flashcard_schema.sql"

def export_database_schema():
    """
    Mô tả: Kết nối đến cơ sở dữ liệu SQLite và xuất định nghĩa schema của tất cả các bảng
           ra một file SQL.
    """
    if not os.path.exists(DATABASE_PATH):
        print(f"Lỗi: File database không tìm thấy tại: {DATABASE_PATH}")
        # In ra đường dẫn DATABASE_PATH đang được sử dụng để debug thêm nếu cần
        print(f"DATABASE_PATH được cấu hình: {DATABASE_PATH}")
        return

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        print(f"Đã kết nối thành công tới database: {DATABASE_PATH}")

        # Lấy tất cả các định nghĩa bảng
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
        schemas = cursor.fetchall()

        if not schemas:
            print("Không tìm thấy bất kỳ bảng nào trong database.")
            return

        with open(OUTPUT_SCHEMA_FILE, 'w', encoding='utf-8') as f:
            for schema in schemas:
                f.write(schema[0])
                f.write(";\n\n") # Thêm dấu chấm phẩy và dòng trống để dễ đọc

        print(f"Đã xuất schema thành công ra file: {OUTPUT_SCHEMA_FILE}")

    except sqlite3.Error as e:
        print(f"Lỗi SQLite trong quá trình xuất schema: {e}")
    except Exception as e:
        print(f"Đã xảy ra lỗi không mong muốn: {e}")
    finally:
        if conn:
            conn.close()
            print("Đã đóng kết nối database.")

if __name__ == '__main__':
    export_database_schema()