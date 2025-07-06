"""
Module chứa business logic liên quan đến việc kiểm tra quyền hạn người dùng.
"""
import logging
from config import ROLE_PERMISSIONS
logger = logging.getLogger(__name__)
def check_permission(user_info, permission_name):
    """
    Kiểm tra quyền hạn của người dùng dựa trên thông tin user_info.
    Args:
        user_info (dict): Dictionary chứa thông tin người dùng,
                          phải có key 'user_role'.
        permission_name (str): Tên quyền hạn cần kiểm tra (vd: CAN_MANAGE_USERS).
    Returns:
        bool: True nếu người dùng có quyền, False nếu không.
    """
    log_prefix = "[AUTH_SERVICE_CHECK]"
    if not user_info or not isinstance(user_info, dict):
        logger.warning(f"{log_prefix} user_info không hợp lệ hoặc bị thiếu.")
        return False
    user_role = user_info.get('user_role', 'user') 
    allowed_permissions = ROLE_PERMISSIONS.get(user_role, set())
    user_id_log = user_info.get('user_id', 'UnknownID') 
    has_permission = permission_name in allowed_permissions
    logger.debug(f"{log_prefix} UserID:{user_id_log}, Role:'{user_role}', Required:'{permission_name}', HasPerm:{has_permission}")
    return has_permission