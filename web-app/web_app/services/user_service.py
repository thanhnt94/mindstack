# web_app/services/user_service.py
import logging
# --- BẮT ĐẦU SỬA LỖI: Xóa import không cần thiết ---
# from werkzeug.security import generate_password_hash, check_password_hash
# --- KẾT THÚC SỬA LỖI ---
from ..models import db, User

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self):
        pass

    def authenticate_user(self, username, password):
        """
        Mô tả: Xác thực thông tin đăng nhập của người dùng.
        Args:
            username (str): Tên đăng nhập.
            password (str): Mật khẩu.
        Returns:
            tuple: (User object, None) nếu thành công, (None, error_message) nếu thất bại.
        """
        log_prefix = f"[USER_SERVICE|Authenticate|User:{username}]"
        if not username or not password:
            return None, "Vui lòng nhập tên đăng nhập và mật khẩu."

        user = User.query.filter_by(username=username).first()
        # --- BẮT ĐẦU SỬA LỖI: So sánh mật khẩu trực tiếp ---
        if user and user.password == password:
        # --- KẾT THÚC SỬA LỖI ---
            logger.info(f"{log_prefix} Xác thực thành công.")
            return user, None
        
        logger.warning(f"{log_prefix} Sai tên đăng nhập hoặc mật khẩu.")
        return None, "Sai tên đăng nhập hoặc mật khẩu."

    def create_user(self, data):
        log_prefix = "[USER_SERVICE|CreateUser]"
        try:
            if 'username' in data and data['username']:
                if User.query.filter_by(username=data['username']).first():
                    return None, "Tên người dùng đã tồn tại."
            if 'telegram_id' in data and data['telegram_id']:
                if User.query.filter_by(telegram_id=data['telegram_id']).first():
                    return None, "Telegram ID đã tồn tại."
            
            # --- BẮT ĐẦU SỬA LỖI: Lưu mật khẩu trực tiếp, không hash ---
            new_user = User(
                username=data.get('username') or None,
                telegram_id=data.get('telegram_id') or None,
                password=data['password'], # Không hash
                user_role=data.get('user_role', 'user'),
                daily_new_limit=data.get('daily_new_limit', 10),
                timezone_offset=data.get('timezone_offset', 7)
            )
            # --- KẾT THÚC SỬA LỖI ---
            db.session.add(new_user)
            db.session.commit()
            logger.info(f"{log_prefix} Tạo người dùng mới thành công: {new_user.username or new_user.telegram_id}")
            return new_user, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi tạo người dùng: {e}", exc_info=True)
            return None, str(e)

    def update_user_profile(self, user_id, data):
        log_prefix = f"[USER_SERVICE|UpdateProfile|User:{user_id}]"
        user = User.query.get(user_id)
        if not user:
            return None, "user_not_found"
        try:
            if 'username' in data and data['username'] != user.username:
                if User.query.filter(User.user_id != user_id, User.username == data['username']).first():
                    return None, "Tên người dùng đã tồn tại."
                user.username = data['username'] or None
            
            if 'telegram_id' in data and data['telegram_id'] != user.telegram_id:
                if User.query.filter(User.user_id != user_id, User.telegram_id == data['telegram_id']).first():
                    return None, "Telegram ID đã tồn tại."
                user.telegram_id = data['telegram_id'] or None

            if 'user_role' in data: user.user_role = data['user_role']
            if 'daily_new_limit' in data: user.daily_new_limit = int(data['daily_new_limit'])
            if 'timezone_offset' in data: user.timezone_offset = int(data['timezone_offset'])
            
            # --- BẮT ĐẦU SỬA LỖI: Cập nhật mật khẩu trực tiếp ---
            if 'password' in data and data['password']:
                user.password = data['password'] # Không hash
            # --- KẾT THÚC SỬA LỖI ---

            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật hồ sơ thành công.")
            return user, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật hồ sơ: {e}", exc_info=True)
            return None, str(e)

    def delete_user(self, user_id):
        log_prefix = f"[USER_SERVICE|DeleteUser|User:{user_id}]"
        user = User.query.get(user_id)
        if not user:
            return False, "user_not_found"
        try:
            db.session.delete(user)
            db.session.commit()
            logger.info(f"{log_prefix} Xóa người dùng thành công.")
            return True, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi xóa người dùng: {e}", exc_info=True)
            return False, str(e)

    def change_user_password(self, user_id, data):
        log_prefix = f"[USER_SERVICE|ChangePassword|User:{user_id}]"
        user = User.query.get(user_id)
        if not user:
            return False, "Không tìm thấy người dùng."

        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')

        if not all([current_password, new_password, confirm_password]):
            return False, "Vui lòng điền đầy đủ tất cả các trường."
        
        # --- BẮT ĐẦU SỬA LỖI: So sánh mật khẩu trực tiếp ---
        if user.password != current_password:
        # --- KẾT THÚC SỬA LỖI ---
            return False, "Mật khẩu hiện tại không đúng."
        
        if new_password != confirm_password:
            return False, "Mật khẩu mới và xác nhận không khớp."
        
        if len(new_password) < 6:
            return False, "Mật khẩu mới phải có ít nhất 6 ký tự."

        try:
            # --- BẮT ĐẦU SỬA LỖI: Lưu mật khẩu mới trực tiếp ---
            user.password = new_password
            # --- KẾT THÚC SỬA LỖI ---
            db.session.commit()
            logger.info(f"{log_prefix} Đổi mật khẩu thành công.")
            return True, "Đổi mật khẩu thành công!"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi đổi mật khẩu: {e}", exc_info=True)
            return False, "Đã xảy ra lỗi server."

    def update_user_flashcard_options(self, user_id, data):
        log_prefix = f"[USER_SERVICE|UpdateFCOptions|User:{user_id}]"
        user = User.query.get(user_id)
        if not user:
            return None, "user_not_found"
        try:
            user.auto_play_audio_front = 'auto_play_audio_front' in data
            user.auto_play_audio_back = 'auto_play_audio_back' in data
            user.auto_show_image_front = 'auto_show_image_front' in data
            user.auto_show_image_back = 'auto_show_image_back' in data
            
            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật tùy chọn flashcard thành công.")
            return user, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật tùy chọn: {e}", exc_info=True)
            return None, str(e)
