# web_app/services/user_service.py
import logging
from ..models import db, User

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self):
        pass

    def authenticate_user(self, username, password):
        """
        Mô tả: Xác thực người dùng bằng username và password.
        Args:
            username (str): Username của người dùng.
            password (str): Mật khẩu (chưa hash) của người dùng.
        Returns:
            tuple: (User, "success") nếu xác thực thành công.
                   (None, "user_not_found") nếu username không tồn tại.
                   (None, "incorrect_password") nếu mật khẩu không đúng.
        """
        log_prefix = f"[AUTH_SERVICE|User:{username}]"
        logger.info(f"{log_prefix} Đang cố gắng xác thực người dùng.")

        # Sử dụng raw SQL để kiểm tra TRIM() trực tiếp trong DB
        # Điều này giúp loại trừ các vấn đề về khoảng trắng hoặc ký tự ẩn
        # mà SQLAlchemy ORM có thể không xử lý như mong đợi.
        query = db.text("SELECT * FROM Users WHERE TRIM(username) = :username_param")
        result = db.session.execute(query, {"username_param": username}).fetchone()
        
        user = None
        if result:
            # Tải lại đối tượng User bằng ORM sau khi tìm thấy bằng raw SQL
            user = User.query.filter_by(user_id=result.user_id).first()
            if not user:
                logger.warning(f"{log_prefix} User_id {result.user_id} tìm thấy bằng raw SQL nhưng không tìm thấy bằng ORM.")
                return None, "user_not_found"
            
            logger.debug(f"{log_prefix} User found in DB. DB Username: '{user.username}', DB Password: '{user.password}'")

        if not user:
            logger.warning(f"{log_prefix} Username '{username}' không tồn tại.")
            return None, "user_not_found"

        # CẢNH BÁO: So sánh mật khẩu plaintext.
        # TRONG ỨNG DỤNG THỰC TẾ, HÃY SỬ DỤNG HASHED PASSWORDS!
        # Ví dụ: if bcrypt.check_password_hash(user.password_hash, password):
        # Sử dụng .strip() trên mật khẩu lấy từ DB để loại bỏ khoảng trắng thừa
        if user.password and user.password.strip() == password:
            logger.info(f"{log_prefix} Xác thực thành công cho user_id: {user.user_id}.")
            return user, "success"
        else:
            logger.warning(f"{log_prefix} Mật khẩu không đúng cho username '{username}'.")
            return None, "incorrect_password"

    def update_user_profile(self, user_id, data):
        """
        Mô tả: Cập nhật thông tin hồ sơ của người dùng.
        Args:
            user_id (int): ID của người dùng cần cập nhật.
            data (dict): Từ điển chứa các trường cần cập nhật và giá trị mới.
                         Các trường có thể bao gồm 'username', 'telegram_id',
                         'user_role', 'daily_new_limit', 'timezone_offset',
                         'password'.
        Returns:
            tuple: (User, "success") nếu cập nhật thành công.
                   (None, "user_not_found") nếu người dùng không tồn tại.
                   (None, "username_exists") nếu username mới đã tồn tại.
                   (None, "invalid_data") nếu dữ liệu không hợp lệ.
                   (None, "error") nếu có lỗi khác.
        """
        log_prefix = f"[USER_SERVICE|UpdateUser:{user_id}]"
        logger.info(f"{log_prefix} Đang cố gắng cập nhật thông tin người dùng.")

        user = User.query.get(user_id)
        if not user:
            logger.warning(f"{log_prefix} Người dùng với ID {user_id} không tìm thấy.")
            return None, "user_not_found"

        try:
            # Cập nhật username nếu có và kiểm tra trùng lặp
            if 'username' in data and data['username'] is not None:
                new_username = data['username'].strip()
                if new_username and new_username != user.username:
                    existing_user = User.query.filter(User.username == new_username, User.user_id != user_id).first()
                    if existing_user:
                        logger.warning(f"{log_prefix} Username '{new_username}' đã tồn tại cho người dùng khác.")
                        return None, "username_exists"
                    user.username = new_username
                elif not new_username: # Cho phép đặt username về NULL
                    user.username = None

            # Cập nhật telegram_id
            if 'telegram_id' in data and data['telegram_id'] is not None:
                user.telegram_id = int(data['telegram_id'])

            # Cập nhật user_role
            if 'user_role' in data and data['user_role'] is not None:
                user.user_role = data['user_role'].strip()

            # Cập nhật daily_new_limit
            if 'daily_new_limit' in data and data['daily_new_limit'] is not None:
                user.daily_new_limit = int(data['daily_new_limit'])

            # Cập nhật timezone_offset
            if 'timezone_offset' in data and data['timezone_offset'] is not None:
                user.timezone_offset = int(data['timezone_offset'])

            # Cập nhật password (chỉ khi được cung cấp và không rỗng)
            if 'password' in data and data['password']:
                # CẢNH BÁO: Trong ứng dụng thực tế, hãy hash mật khẩu trước khi lưu!
                user.password = data['password'].strip()
                logger.warning(f"{log_prefix} Mật khẩu người dùng {user_id} đã được cập nhật (chưa hash).")

            db.session.commit()
            logger.info(f"{log_prefix} Thông tin người dùng {user_id} đã được cập nhật thành công.")
            return user, "success"
        except ValueError as ve:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi chuyển đổi kiểu dữ liệu: {ve}", exc_info=True)
            return None, "invalid_data"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi không mong muốn khi cập nhật người dùng: {e}", exc_info=True)
            return None, "error"

    def delete_user(self, user_id):
        """
        Mô tả: Xóa một người dùng khỏi cơ sở dữ liệu.
        Args:
            user_id (int): ID của người dùng cần xóa.
        Returns:
            tuple: (True, "success") nếu xóa thành công.
                   (False, "user_not_found") nếu người dùng không tồn tại.
                   (False, "error") nếu có lỗi khác.
        """
        log_prefix = f"[USER_SERVICE|DeleteUser:{user_id}]"
        logger.info(f"{log_prefix} Đang cố gắng xóa người dùng.")

        user = User.query.get(user_id)
        if not user:
            logger.warning(f"{log_prefix} Người dùng với ID {user_id} không tìm thấy để xóa.")
            return False, "user_not_found"

        try:
            db.session.delete(user)
            db.session.commit()
            logger.info(f"{log_prefix} Người dùng ID: {user_id} đã được xóa thành công.")
            return True, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi không mong muốn khi xóa người dùng ID: {user_id}: {e}", exc_info=True)
            return False, "error"

    # BẮT ĐẦU THÊM: Hàm tạo người dùng mới
    def create_user(self, data):
        """
        Mô tả: Tạo một người dùng mới trong cơ sở dữ liệu.
        Args:
            data (dict): Từ điển chứa thông tin người dùng mới.
                         Bắt buộc phải có 'telegram_id' và 'password'.
                         Có thể có 'username', 'user_role', 'daily_new_limit', 'timezone_offset'.
        Returns:
            tuple: (User, "success") nếu tạo thành công.
                   (None, "username_exists") nếu username đã tồn tại.
                   (None, "telegram_id_exists") nếu telegram_id đã tồn tại.
                   (None, "missing_required_fields") nếu thiếu trường bắt buộc.
                   (None, "invalid_data") nếu dữ liệu không hợp lệ.
                   (None, "error") nếu có lỗi khác.
        """
        log_prefix = "[USER_SERVICE|CreateUser]"
        logger.info(f"{log_prefix} Đang cố gắng tạo người dùng mới.")

        # Kiểm tra các trường bắt buộc
        if 'telegram_id' not in data or 'password' not in data:
            logger.warning(f"{log_prefix} Thiếu trường bắt buộc (telegram_id hoặc password).")
            return None, "missing_required_fields"

        try:
            new_username = data.get('username', '').strip()
            new_telegram_id = int(data['telegram_id'])
            new_password = data['password'].strip()

            # Kiểm tra trùng lặp username (nếu có)
            if new_username:
                existing_user_by_username = User.query.filter_by(username=new_username).first()
                if existing_user_by_username:
                    logger.warning(f"{log_prefix} Username '{new_username}' đã tồn tại.")
                    return None, "username_exists"
            else:
                new_username = None # Đảm bảo là None nếu rỗng để lưu vào DB

            # Kiểm tra trùng lặp telegram_id
            existing_user_by_telegram_id = User.query.filter_by(telegram_id=new_telegram_id).first()
            if existing_user_by_telegram_id:
                logger.warning(f"{log_prefix} Telegram ID '{new_telegram_id}' đã tồn tại.")
                return None, "telegram_id_exists"

            new_user = User(
                username=new_username,
                telegram_id=new_telegram_id,
                password=new_password, # CẢNH BÁO: Trong ứng dụng thực tế, hãy hash mật khẩu!
                user_role=data.get('user_role', 'user').strip(),
                daily_new_limit=int(data.get('daily_new_limit', 10)),
                timezone_offset=int(data.get('timezone_offset', 7)),
                score=0, # Mặc định điểm ban đầu là 0
                front_audio=1, # Mặc định bật audio mặt trước
                back_audio=1,  # Mặc định bật audio mặt sau
                front_image_enabled=1, # Mặc định bật ảnh mặt trước
                back_image_enabled=1,  # Mặc định bật ảnh mặt sau
                is_notification_enabled=0, # Mặc định tắt thông báo
                notification_interval_minutes=60,
                current_mode='sequential_interspersed',
                default_mode='sequential_interspersed',
                show_review_summary=1,
                enable_morning_brief=1
            )

            db.session.add(new_user)
            db.session.commit()
            logger.info(f"{log_prefix} Người dùng mới '{new_user.username or new_user.telegram_id}' (ID: {new_user.user_id}) đã được tạo thành công.")
            return new_user, "success"
        except ValueError as ve:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi chuyển đổi kiểu dữ liệu: {ve}", exc_info=True)
            return None, "invalid_data"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi không mong muốn khi tạo người dùng mới: {e}", exc_info=True)
            return None, "error"
    # KẾT THÚC THÊM
