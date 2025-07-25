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
        Args:
            user_id (int): ID của người gửi feedback.
            content (str): Nội dung feedback.
            flashcard_id (int, optional): ID của flashcard được feedback.
            question_id (int, optional): ID của câu hỏi quiz được feedback.
        Returns:
            tuple: (Feedback object, "success" | "error", "message")
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

    # --- BẮT ĐẦU THAY ĐỔI: Tách thành 2 hàm riêng biệt ---
    def get_feedback_sent_by_user(self, user_id):
        """
        Mô tả: Lấy tất cả feedback đã được gửi bởi một người dùng cụ thể.
        Args:
            user_id (int): ID của người dùng đã gửi.
        Returns:
            list: Danh sách các đối tượng Feedback.
        """
        log_prefix = f"[FEEDBACK_SVC|GetSent|User:{user_id}]"
        try:
            logger.info(f"{log_prefix} Lấy danh sách feedback đã gửi.")
            feedbacks = Feedback.query.filter_by(user_id=user_id).options(
                joinedload(Feedback.flashcard).joinedload(Flashcard.vocabulary_set),
                joinedload(Feedback.quiz_question).joinedload(QuizQuestion.question_set)
            ).order_by(Feedback.timestamp.desc()).all()
            return feedbacks
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi lấy feedback đã gửi: {e}", exc_info=True)
            return []

    def get_feedback_received_by_user(self, user_id):
        """
        Mô tả: Lấy danh sách feedback mà người dùng (creator/admin) nhận được.
        Args:
            user_id (int): ID của người dùng hiện tại.
        Returns:
            list: Danh sách các đối tượng Feedback.
        """
        log_prefix = f"[FEEDBACK_SVC|GetReceived|User:{user_id}]"
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"{log_prefix} Không tìm thấy người dùng.")
            return []

        try:
            if user.user_role == 'admin':
                logger.info(f"{log_prefix} Lấy tất cả feedback cho admin.")
                feedbacks = Feedback.query.options(
                    joinedload(Feedback.user),
                    joinedload(Feedback.flashcard).joinedload(Flashcard.vocabulary_set),
                    joinedload(Feedback.quiz_question).joinedload(QuizQuestion.question_set)
                ).order_by(Feedback.timestamp.desc()).all()
                return feedbacks
            
            is_creator = bool(user.created_sets or user.created_question_sets)
            if is_creator:
                logger.info(f"{log_prefix} Lấy feedback cho creator.")
                created_flashcard_set_ids = [s.set_id for s in user.created_sets]
                created_quiz_set_ids = [qs.set_id for qs in user.created_question_sets]

                # Query rỗng ban đầu
                query = Feedback.query.filter(db.false()) 

                if created_flashcard_set_ids:
                    flashcard_feedbacks_query = Feedback.query.join(Flashcard).filter(
                        Flashcard.set_id.in_(created_flashcard_set_ids)
                    )
                    query = query.union(flashcard_feedbacks_query)

                if created_quiz_set_ids:
                    quiz_feedbacks_query = Feedback.query.join(QuizQuestion).filter(
                        QuizQuestion.set_id.in_(created_quiz_set_ids)
                    )
                    query = query.union(quiz_feedbacks_query)
                
                all_my_feedbacks = query.options(
                    joinedload(Feedback.user),
                    joinedload(Feedback.flashcard).joinedload(Flashcard.vocabulary_set),
                    joinedload(Feedback.quiz_question).joinedload(QuizQuestion.question_set)
                ).order_by(Feedback.timestamp.desc()).all()
                return all_my_feedbacks
            
            # Nếu không phải admin và không phải creator, không nhận được feedback nào
            return []

        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi lấy danh sách feedback nhận được: {e}", exc_info=True)
            return []
    # --- KẾT THÚC THAY ĐỔI ---
            
    def update_feedback_status(self, feedback_id, new_status, user_id):
        """
        Mô tả: Cập nhật trạng thái của một feedback.
        Args:
            feedback_id (int): ID của feedback cần cập nhật.
            new_status (str): Trạng thái mới ('seen', 'resolved', etc.).
            user_id (int): ID của người dùng thực hiện hành động.
        Returns:
            tuple: (Feedback object, bool, message)
        """
        log_prefix = f"[FEEDBACK_SVC|UpdateStatus|ID:{feedback_id}]"
        feedback = Feedback.query.get(feedback_id)
        if not feedback:
            logger.warning(f"{log_prefix} Không tìm thấy feedback.")
            return None, False, "Không tìm thấy feedback."
        
        user = User.query.get(user_id)
        if not user:
            return None, False, "Không tìm thấy người dùng."
            
        # Kiểm tra quyền
        is_creator = False
        if feedback.flashcard:
            if feedback.flashcard.vocabulary_set.creator_user_id == user_id:
                is_creator = True
        elif feedback.quiz_question:
            if feedback.quiz_question.question_set.creator_user_id == user_id:
                is_creator = True

        if user.user_role != 'admin' and not is_creator:
            return None, False, "Bạn không có quyền thực hiện hành động này."

        try:
            feedback.status = new_status
            db.session.commit()
            logger.info(f"{log_prefix} Đã cập nhật trạng thái thành '{new_status}'.")
            return feedback, True, "Cập nhật thành công."
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật trạng thái: {e}", exc_info=True)
            return None, False, "Lỗi server."
