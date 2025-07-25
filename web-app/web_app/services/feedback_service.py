# web_app/services/feedback_service.py
import logging
import time
from ..models import db, Feedback, User, Flashcard, QuizQuestion
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)

class FeedbackService:
    """
    Mô tả: Lớp chứa các hàm xử lý logic nghiệp vụ liên quan đến feedback của người dùng.
    """
    def __init__(self):
        pass

    def create_feedback(self, user_id, content, flashcard_id=None, question_id=None):
        """
        Mô tả: Tạo một feedback mới từ người dùng.
        """
        log_prefix = f"[FEEDBACK_SVC|Create|User:{user_id}]"
        
        if not content or not content.strip():
            return None, "error", "Nội dung feedback không được để trống."
        
        if not flashcard_id and not question_id:
            return None, "error", "Feedback phải liên quan đến một Flashcard hoặc một Câu hỏi Quiz."

        try:
            new_feedback = Feedback(
                user_id=user_id,
                content=content,
                flashcard_id=flashcard_id,
                question_id=question_id,
                status='new',
                timestamp=int(time.time())
            )
            db.session.add(new_feedback)
            db.session.commit()
            logger.info(f"{log_prefix} Đã tạo feedback mới (ID: {new_feedback.feedback_id}) thành công.")
            return new_feedback, "success", "Gửi feedback thành công!"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi lưu feedback: {e}", exc_info=True)
            return None, "error", "Đã xảy ra lỗi server khi gửi feedback."

    def get_feedback_sent_by_user(self, user_id, filter_by='all'):
        """
        Mô tả: Lấy tất cả feedback đã được gửi bởi một người dùng, có hỗ trợ lọc.
        """
        log_prefix = f"[FEEDBACK_SVC|GetSent|User:{user_id}]"
        try:
            query = Feedback.query.filter_by(user_id=user_id).options(
                joinedload(Feedback.flashcard).joinedload(Flashcard.vocabulary_set),
                joinedload(Feedback.quiz_question).joinedload(QuizQuestion.question_set),
                joinedload(Feedback.resolver)
            )
            if filter_by and filter_by != 'all':
                query = query.filter(Feedback.status == filter_by)
            
            return query.order_by(Feedback.timestamp.desc()).all()
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi lấy feedback đã gửi: {e}", exc_info=True)
            return []

    def get_feedback_received_by_user(self, user_id, filter_by='all'):
        """
        Mô tả: Lấy danh sách feedback mà người dùng (creator/admin) nhận được, có hỗ trợ lọc.
        """
        log_prefix = f"[FEEDBACK_SVC|GetReceived|User:{user_id}]"
        user = User.query.get(user_id)
        if not user:
            return []

        try:
            base_query = Feedback.query.options(
                joinedload(Feedback.user),
                joinedload(Feedback.flashcard).joinedload(Flashcard.vocabulary_set),
                joinedload(Feedback.quiz_question).joinedload(QuizQuestion.question_set),
                joinedload(Feedback.resolver)
            )

            if filter_by and filter_by != 'all':
                base_query = base_query.filter(Feedback.status == filter_by)

            if user.user_role == 'admin':
                return base_query.order_by(Feedback.timestamp.desc()).all()
            
            is_creator = bool(user.created_sets or user.created_question_sets)
            if is_creator:
                created_flashcard_set_ids = [s.set_id for s in user.created_sets]
                created_quiz_set_ids = [qs.set_id for qs in user.created_question_sets]
                
                query = base_query.join(Flashcard, Flashcard.flashcard_id == Feedback.flashcard_id, isouter=True)\
                                  .join(QuizQuestion, QuizQuestion.question_id == Feedback.question_id, isouter=True)\
                                  .filter(
                                      db.or_(
                                          Flashcard.set_id.in_(created_flashcard_set_ids),
                                          QuizQuestion.set_id.in_(created_quiz_set_ids)
                                      )
                                  ).order_by(Feedback.timestamp.desc())
                return query.all()
            
            return []

        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi lấy danh sách feedback nhận được: {e}", exc_info=True)
            return []
            
    def update_feedback_status(self, feedback_id, new_status, user_id, resolver_comment=None):
        """
        Mô tả: Cập nhật trạng thái và bình luận của một feedback, tuân thủ logic trạng thái.
        """
        log_prefix = f"[FEEDBACK_SVC|UpdateStatus|ID:{feedback_id}]"
        feedback = Feedback.query.get(feedback_id)
        if not feedback:
            return None, False, "Không tìm thấy feedback."
        
        user = User.query.get(user_id)
        if not user:
            return None, False, "Không tìm thấy người dùng."
            
        is_creator = False
        if feedback.flashcard:
            if feedback.flashcard.vocabulary_set.creator_user_id == user_id:
                is_creator = True
        elif feedback.quiz_question:
            if feedback.quiz_question.question_set.creator_user_id == user_id:
                is_creator = True

        if user.user_role != 'admin' and not is_creator:
            return None, False, "Bạn không có quyền thực hiện hành động này."

        # BẮT ĐẦU THAY ĐỔI: Áp dụng logic trạng thái
        if feedback.status == 'resolved':
            return None, False, "Feedback đã được giải quyết và không thể thay đổi."
        
        if feedback.status == 'new' and resolver_comment and resolver_comment.strip():
            return None, False, "Không thể thêm phản hồi khi feedback ở trạng thái 'Chưa giải quyết'. Vui lòng chuyển sang 'Đã tiếp nhận' trước."
        # KẾT THÚC THAY ĐỔI

        try:
            feedback.status = new_status
            
            if resolver_comment is not None:
                feedback.resolver_comment = resolver_comment.strip() if resolver_comment else None
                feedback.resolved_by_user_id = user_id
                feedback.resolved_timestamp = int(time.time())

            db.session.commit()
            logger.info(f"{log_prefix} Đã cập nhật trạng thái thành '{new_status}'.")
            return feedback, True, "Cập nhật thành công."
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật trạng thái: {e}", exc_info=True)
            return None, False, "Lỗi server."
