# web_app/services/user_service.py
import logging
from ..models import db, User

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self):
        pass

    def authenticate_user(self, username, password):
        """
        Xác thực người dùng bằng username và password.
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

