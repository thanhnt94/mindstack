# web_app/services/set_service.py
import logging
from ..models import db, VocabularySet, User, Flashcard

logger = logging.getLogger(__name__)

class SetService:
    """
    Mô tả: Lớp chứa các hàm xử lý logic nghiệp vụ liên quan đến bộ thẻ (VocabularySet).
    """
    def __init__(self):
        pass

    def get_all_sets_with_details(self):
        """
        Mô tả: Lấy tất cả các bộ thẻ cùng với thông tin chi tiết như người tạo và số lượng thẻ.
        Returns:
            list: Danh sách các đối tượng VocabularySet, mỗi đối tượng đã được bổ sung thông tin.
        """
        log_prefix = "[SET_SERVICE|GetAllSets]"
        logger.info(f"{log_prefix} Bắt đầu lấy danh sách tất cả bộ thẻ.")
        try:
            # Sử dụng join để lấy thông tin người tạo và subquery để đếm số thẻ
            sets = db.session.query(
                VocabularySet,
                User.username.label('creator_username'),
                db.func.count(Flashcard.flashcard_id).label('flashcard_count')
            ).outerjoin(User, VocabularySet.creator_user_id == User.user_id)\
             .outerjoin(Flashcard, VocabularySet.set_id == Flashcard.set_id)\
             .group_by(VocabularySet.set_id)\
             .order_by(VocabularySet.title)\
             .all()
            
            logger.info(f"{log_prefix} Lấy thành công {len(sets)} bộ thẻ.")
            
            # Kết quả trả về là một list các tuple (VocabularySet, creator_username, flashcard_count)
            # Ta cần chuyển đổi nó thành một cấu trúc dễ sử dụng hơn
            results = []
            for set_obj, creator_username, flashcard_count in sets:
                set_obj.creator_username = creator_username or "N/A"
                set_obj.flashcard_count = flashcard_count
                results.append(set_obj)
                
            return results
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi truy vấn danh sách bộ thẻ: {e}", exc_info=True)
            return []

    def get_set_by_id(self, set_id):
        """
        Mô tả: Lấy một bộ thẻ cụ thể bằng ID.
        Args:
            set_id (int): ID của bộ thẻ.
        Returns:
            VocabularySet: Đối tượng bộ thẻ nếu tìm thấy, ngược lại là None.
        """
        return VocabularySet.query.get(set_id)

    def create_set(self, data, creator_id):
        """
        Mô tả: Tạo một bộ thẻ mới.
        Args:
            data (dict): Dữ liệu của bộ thẻ mới (title, description, tags, is_public).
            creator_id (int): ID của người dùng tạo bộ thẻ.
        Returns:
            tuple: (VocabularySet, "success") nếu thành công.
                   (None, "error_message") nếu thất bại.
        """
        log_prefix = f"[SET_SERVICE|CreateSet|User:{creator_id}]"
        logger.info(f"{log_prefix} Đang tạo bộ thẻ mới với dữ liệu: {data}")
        try:
            new_set = VocabularySet(
                title=data.get('title'),
                description=data.get('description'),
                tags=data.get('tags'),
                is_public=int(data.get('is_public', 1)),
                creator_user_id=creator_id
            )
            db.session.add(new_set)
            db.session.commit()
            logger.info(f"{log_prefix} Tạo bộ thẻ '{new_set.title}' (ID: {new_set.set_id}) thành công.")
            return new_set, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi tạo bộ thẻ: {e}", exc_info=True)
            return None, str(e)

    def update_set(self, set_id, data):
        """
        Mô tả: Cập nhật thông tin của một bộ thẻ đã có.
        Args:
            set_id (int): ID của bộ thẻ cần cập nhật.
            data (dict): Dữ liệu mới cho bộ thẻ.
        Returns:
            tuple: (VocabularySet, "success") nếu thành công.
                   (None, "error_message") nếu thất bại.
        """
        log_prefix = f"[SET_SERVICE|UpdateSet|Set:{set_id}]"
        logger.info(f"{log_prefix} Đang cập nhật bộ thẻ với dữ liệu: {data}")
        
        set_to_update = self.get_set_by_id(set_id)
        if not set_to_update:
            return None, "set_not_found"
            
        try:
            set_to_update.title = data.get('title', set_to_update.title)
            set_to_update.description = data.get('description', set_to_update.description)
            set_to_update.tags = data.get('tags', set_to_update.tags)
            set_to_update.is_public = int(data.get('is_public', set_to_update.is_public))
            
            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật bộ thẻ '{set_to_update.title}' thành công.")
            return set_to_update, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật bộ thẻ: {e}", exc_info=True)
            return None, str(e)

    def delete_set(self, set_id):
        """
        Mô tả: Xóa một bộ thẻ khỏi cơ sở dữ liệu.
        Args:
            set_id (int): ID của bộ thẻ cần xóa.
        Returns:
            tuple: (True, "success") nếu xóa thành công.
                   (False, "error_message") nếu thất bại.
        """
        log_prefix = f"[SET_SERVICE|DeleteSet|Set:{set_id}]"
        logger.info(f"{log_prefix} Đang cố gắng xóa bộ thẻ.")
        
        set_to_delete = self.get_set_by_id(set_id)
        if not set_to_delete:
            logger.warning(f"{log_prefix} Không tìm thấy bộ thẻ để xóa.")
            return False, "set_not_found"
            
        try:
            # Logic xóa ở đây. Lưu ý rằng các flashcard liên quan cũng sẽ bị xóa
            # do 'ondelete=CASCADE' trong model Flashcard.
            db.session.delete(set_to_delete)
            db.session.commit()
            logger.info(f"{log_prefix} Xóa bộ thẻ '{set_to_delete.title}' thành công.")
            return True, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi xóa bộ thẻ: {e}", exc_info=True)
            return False, str(e)
