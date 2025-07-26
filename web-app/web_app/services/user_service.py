# web_app/services/user_service.py
import logging
# BẮT ĐẦU THAY ĐỔI: Thêm thư viện mã hóa mật khẩu
from werkzeug.security import generate_password_hash, check_password_hash
# KẾT THÚC THAY ĐỔI
from ..models import db, User

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self):
        pass

    def authenticate_user(self, username, password):
        """
        Mô tả: Xác thực thông tin đăng nhập của người dùng bằng mật khẩu đã mã hóa.
        """
        log_prefix = f"[USER_SERVICE|Authenticate|User:{username}]"
        if not username or not password:
            return None, "Vui lòng nhập tên đăng nhập và mật khẩu."

        user = User.query.filter_by(username=username).first()
        
        # BẮT ĐẦU THAY ĐỔI: So sánh mật khẩu đã được băm (hash)
        # Kiểm tra xem người dùng có tồn tại không và mật khẩu có khớp với hash trong DB không
        if user and user.password and check_password_hash(user.password, password):
        # KẾT THÚC THAY ĐỔI
            logger.info(f"{log_prefix} Xác thực thành công.")
            return user, None
        
        logger.warning(f"{log_prefix} Sai tên đăng nhập hoặc mật khẩu.")
        return None, "Sai tên đăng nhập hoặc mật khẩu."

    def create_user(self, data):
        """
        Mô tả: Tạo người dùng mới với mật khẩu được mã hóa.
        """
        log_prefix = "[USER_SERVICE|CreateUser]"
        try:
            if 'username' in data and data['username']:
                if User.query.filter_by(username=data['username']).first():
                    return None, "Tên người dùng đã tồn tại."
            if 'telegram_id' in data and data['telegram_id']:
                if User.query.filter_by(telegram_id=data['telegram_id']).first():
                    return None, "Telegram ID đã tồn tại."
            
            # BẮT ĐẦU THAY ĐỔI: Mã hóa mật khẩu trước khi lưu
            hashed_password = generate_password_hash(data['password'])
            new_user = User(
                username=data.get('username') or None,
                telegram_id=data.get('telegram_id') or None,
                password=hashed_password, # Lưu mật khẩu đã mã hóa
                user_role=data.get('user_role', 'user'),
                daily_new_limit=data.get('daily_new_limit', 10),
                timezone_offset=data.get('timezone_offset', 7)
            )
            # KẾT THÚC THAY ĐỔI
            db.session.add(new_user)
            db.session.commit()
            logger.info(f"{log_prefix} Tạo người dùng mới thành công: {new_user.username or new_user.telegram_id}")
            return new_user, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi tạo người dùng: {e}", exc_info=True)
            return None, str(e)

    def update_user_profile(self, user_id, data):
        """
        Mô tả: Cập nhật thông tin người dùng, bao gồm cả việc mã hóa mật khẩu mới nếu có.
        """
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
            
            # BẮT ĐẦU THAY ĐỔI: Mã hóa mật khẩu mới nếu được cung cấp
            if 'password' in data and data['password']:
                user.password = generate_password_hash(data['password'])
            # KẾT THÚC THAY ĐỔI

            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật hồ sơ thành công.")
            return user, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật hồ sơ: {e}", exc_info=True)
            return None, str(e)

    def delete_user(self, user_id):
        """
        Mô tả: Xóa một người dùng khỏi cơ sở dữ liệu.
        """
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
        """
        Mô tả: Thay đổi mật khẩu cho người dùng, có xác thực mật khẩu cũ và mã hóa mật khẩu mới.
        """
        log_prefix = f"[USER_SERVICE|ChangePassword|User:{user_id}]"
        user = User.query.get(user_id)
        if not user:
            return False, "Không tìm thấy người dùng."

        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')

        if not all([current_password, new_password, confirm_password]):
            return False, "Vui lòng điền đầy đủ tất cả các trường."
        
        # BẮT ĐẦU THAY ĐỔI: So sánh mật khẩu hiện tại với hash
        if not user.password or not check_password_hash(user.password, current_password):
        # KẾT THÚC THAY ĐỔI
            return False, "Mật khẩu hiện tại không đúng."
        
        if new_password != confirm_password:
            return False, "Mật khẩu mới và xác nhận không khớp."
        
        if len(new_password) < 6:
            return False, "Mật khẩu mới phải có ít nhất 6 ký tự."

        try:
            # BẮT ĐẦU THAY ĐỔI: Mã hóa và lưu mật khẩu mới
            user.password = generate_password_hash(new_password)
            # KẾT THÚC THAY ĐỔI
            db.session.commit()
            logger.info(f"{log_prefix} Đổi mật khẩu thành công.")
            return True, "Đổi mật khẩu thành công!"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi đổi mật khẩu: {e}", exc_info=True)
            return False, "Đã xảy ra lỗi server."

    def update_user_flashcard_options(self, user_id, data):
        """
        Mô tả: Cập nhật các tùy chọn học flashcard của người dùng.
        """
        log_prefix = f"[USER_SERVICE|UpdateFCOptions|User:{user_id}]"
        user = User.query.get(user_id)
        if not user:
            return None, "user_not_found"
        try:
            # Sửa lỗi: Chuyển đổi giá trị checkbox sang boolean đúng cách
            user.front_audio = 1 if 'auto_play_audio_front' in data else 0
            user.back_audio = 1 if 'auto_play_audio_back' in data else 0
            user.front_image_enabled = 1 if 'auto_show_image_front' in data else 0
            user.back_image_enabled = 1 if 'auto_show_image_back' in data else 0
            
            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật tùy chọn flashcard thành công.")
            return user, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật tùy chọn: {e}", exc_info=True)
            return None, str(e)
