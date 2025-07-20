# web_app/services/quiz_service.py
import logging
import openpyxl
import io
import random
import time
import hashlib
import os
import zipfile
import requests # Thư viện để tải file từ URL, cần được cài đặt (pip install requests)
from sqlalchemy import func
from ..models import db, QuestionSet, User, QuizQuestion, UserQuizProgress, ScoreLog, QuizPassage
from ..config import (
    SCORE_QUIZ_CORRECT_FIRST_TIME, SCORE_QUIZ_CORRECT_REPEAT,
    QUIZ_MODE_NEW_SEQUENTIAL, QUIZ_MODE_NEW_RANDOM, QUIZ_MODE_REVIEW,
    QUIZ_IMAGES_DIR, QUIZ_AUDIO_CACHE_DIR # Thêm import thư mục media
)

logger = logging.getLogger(__name__)

# BẮT ĐẦU THÊM MỚI: Hàm sắp xếp tùy chỉnh cho các bộ (được sao chép từ flashcard.py)
def _sort_sets_by_progress(set_items, total_key, completed_key):
    """
    Mô tả: Sắp xếp danh sách các bộ (Flashcard Sets hoặc Question Sets) dựa trên tiến độ hoàn thành.
           Các bộ có phần trăm hoàn thành cao nhất sẽ được đưa lên đầu.
           Các bộ đã hoàn thành 100% sẽ được đưa xuống cuối danh sách.
           Nếu phần trăm hoàn thành bằng nhau, sẽ sắp xếp theo tiêu đề (alphabet).

    Args:
        set_items (list): Danh sách các đối tượng bộ.
        total_key (str): Tên thuộc tính chứa tổng số mục trong bộ.
        completed_key (str): Tên thuộc tính chứa số mục đã hoàn thành.

    Returns:
        list: Danh sách các bộ đã được sắp xếp.
    """
    def custom_sort_key(set_item):
        total = getattr(set_item, total_key, 0)
        completed = getattr(set_item, completed_key, 0)
        title = getattr(set_item, 'title', '')

        if total == 0:
            # Đặt các bộ không có mục nào xuống cuối cùng
            return (float('-inf'), title) 

        percentage = (completed * 100 / total)

        if percentage == 100:
            # Đặt các bộ đã hoàn thành 100% xuống cuối cùng
            return (0, title) 
        
        # Sắp xếp giảm dần theo phần trăm (sử dụng -percentage)
        # Nếu phần trăm bằng nhau, sắp xếp tăng dần theo title
        return (-percentage, title)

    return sorted(set_items, key=custom_sort_key)
# KẾT THÚC THÊM MỚI

class QuizService:
    """
    Mô tả: Lớp chứa các hàm xử lý logic nghiệp vụ liên quan đến bộ câu hỏi (QuestionSet)
    và các câu hỏi trắc nghiệm (QuizQuestion) theo logic "từng câu một".
    """
    def __init__(self):
        pass

    def get_categorized_question_sets_for_user(self, user_id):
        """
        Mô tả: Lấy và phân loại các bộ câu hỏi thành "đã bắt đầu" và "mới" cho một người dùng cụ thể.
        """
        log_prefix = f"[QUIZ_SERVICE|GetCategorized|User:{user_id}]"
        logger.info(f"{log_prefix} Bắt đầu lấy và phân loại bộ câu hỏi.")

        try:
            started_set_ids_query = db.session.query(QuizQuestion.set_id).join(
                UserQuizProgress, UserQuizProgress.question_id == QuizQuestion.question_id
            ).filter(UserQuizProgress.user_id == user_id).distinct()
            
            started_set_ids = {row[0] for row in started_set_ids_query.all()}
            
            started_sets_raw = []
            if started_set_ids:
                total_questions_map = dict(db.session.query(
                    QuizQuestion.set_id, func.count(QuizQuestion.question_id)
                ).filter(QuizQuestion.set_id.in_(started_set_ids)).group_by(QuizQuestion.set_id).all())
                
                answered_questions_map = dict(db.session.query(
                    QuizQuestion.set_id, func.count(UserQuizProgress.progress_id)
                ).join(QuizQuestion).filter(
                    UserQuizProgress.user_id == user_id,
                    QuizQuestion.set_id.in_(started_set_ids)
                ).group_by(QuizQuestion.set_id).all())

                set_objects = QuestionSet.query.filter(QuestionSet.set_id.in_(started_set_ids)).all()
                for s in set_objects:
                    s.total_questions = total_questions_map.get(s.set_id, 0)
                    s.answered_questions = answered_questions_map.get(s.set_id, 0)
                    s.creator_username = s.creator.username if s.creator else "N/A"
                    started_sets_raw.append(s)

            # BẮT ĐẦU THAY ĐỔI: Sắp xếp tùy chỉnh cho các bộ đã bắt đầu
            # Sử dụng hàm _sort_sets_by_progress đã định nghĩa ở trên
            started_sets = _sort_sets_by_progress(started_sets_raw, 
                                                total_key='total_questions', 
                                                completed_key='answered_questions')
            # KẾT THÚC THAY ĐỔI
            
            # BẮT ĐẦU THAY ĐỔI: Sắp xếp bộ mới theo alphabet
            new_sets_query = QuestionSet.query.filter(
                QuestionSet.is_public == True,
                ~QuestionSet.set_id.in_(started_set_ids)
            ).order_by(QuestionSet.title.asc()) # Sắp xếp theo alphabet
            new_sets = new_sets_query.all()
            for s in new_sets:
                 s.creator_username = s.creator.username if s.creator else "N/A"
            # KẾT THÚC THAY ĐỔI

            logger.info(f"{log_prefix} Tìm thấy {len(started_sets)} bộ đã bắt đầu và {len(new_sets)} bộ mới.")
            return started_sets, new_sets

        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi phân loại bộ câu hỏi: {e}", exc_info=True)
            return [], []

    # BẮT ĐẦU THAY ĐỔI: Hàm get_next_question_group_for_user để trả về nhóm câu hỏi
    def get_next_question_group_for_user(self, user_id, set_id, mode):
        """
        Mô tả: Lấy nhóm câu hỏi tiếp theo cho người dùng dựa trên chế độ đã chọn.
               Ưu tiên các câu hỏi trong cùng một nhóm đoạn văn nếu người dùng đang làm dở.
               Trả về một danh sách các câu hỏi (nếu thuộc cùng đoạn văn) hoặc một câu hỏi đơn lẻ.
        Args:
            user_id (int): ID của người dùng.
            set_id (int): ID của bộ câu hỏi.
            mode (str): Chế độ làm bài quiz.
        Returns:
            tuple: (list of QuizQuestion objects, QuizPassage object or None)
                   Trả về danh sách các câu hỏi cần hiển thị cùng lúc và đoạn văn liên quan.
                   Nếu không còn câu hỏi nào, trả về (None, None).
        """
        log_prefix = f"[QUIZ_SERVICE|GetNextQGroup|User:{user_id}|Set:{set_id}|Mode:{mode}]"
        logger.info(f"{log_prefix} Bắt đầu tìm nhóm câu hỏi tiếp theo.")

        # Lấy tất cả các ID câu hỏi trong bộ
        all_q_ids_in_set = {row[0] for row in QuizQuestion.query.with_entities(QuizQuestion.question_id).filter_by(set_id=set_id).all()}
        if not all_q_ids_in_set:
            logger.warning(f"{log_prefix} Bộ câu hỏi này không có câu hỏi nào.")
            return None, None

        # Lấy các ID câu hỏi mà người dùng đã trả lời trong bộ này
        answered_q_ids = {row[0] for row in UserQuizProgress.query.with_entities(UserQuizProgress.question_id).filter_by(user_id=user_id).join(QuizQuestion).filter(QuizQuestion.set_id == set_id).all()}

        # 1. Ưu tiên hoàn thành nhóm câu hỏi trong cùng đoạn văn đang làm dở
        user = User.query.get(user_id)
        if user and user.current_question_set_id == set_id:
            # Tìm câu hỏi cuối cùng mà người dùng đã trả lời trong bộ này
            last_answered_progress = UserQuizProgress.query.filter_by(user_id=user_id)\
                                     .join(QuizQuestion).filter(QuizQuestion.set_id == set_id)\
                                     .order_by(UserQuizProgress.last_answered.desc())\
                                     .first()
            
            if last_answered_progress and last_answered_progress.question.passage_id:
                current_passage_id = last_answered_progress.question.passage_id
                
                # Kiểm tra xem còn câu hỏi nào trong đoạn văn này chưa được trả lời không
                unanswered_in_passage_count = QuizQuestion.query.filter(
                    QuizQuestion.set_id == set_id,
                    QuizQuestion.passage_id == current_passage_id,
                    ~QuizQuestion.progresses.any(user_id=user_id) # Chưa được trả lời bởi người dùng này
                ).count()

                if unanswered_in_passage_count > 0:
                    # Nếu còn, trả về tất cả các câu hỏi trong đoạn văn này (để người dùng làm lại hoặc làm tiếp)
                    questions_in_passage = QuizQuestion.query.filter(
                        QuizQuestion.set_id == set_id,
                        QuizQuestion.passage_id == current_passage_id
                    ).order_by(QuizQuestion.passage_order.asc(), QuizQuestion.question_id.asc()).all()
                    
                    logger.info(f"{log_prefix} Tìm thấy {len(questions_in_passage)} câu hỏi trong nhóm đoạn văn đang làm dở (Passage ID: {current_passage_id}).")
                    return questions_in_passage, questions_in_passage[0].passage # Trả về list và passage object

                else:
                    logger.info(f"{log_prefix} Đã hoàn thành nhóm đoạn văn hiện tại. Chuyển sang tìm câu hỏi mới/ôn tập.")
        
        # 2. Nếu không có nhóm đoạn văn đang làm dở, tìm câu hỏi mới hoặc ôn tập
        next_question_id = None
        
        if mode == QUIZ_MODE_NEW_SEQUENTIAL:
            new_q_ids = all_q_ids_in_set - answered_q_ids
            if new_q_ids:
                # Tìm câu hỏi mới có ID nhỏ nhất (tuần tự)
                next_question_id = min(new_q_ids)
            else:
                logger.info(f"{log_prefix} Đã hoàn thành tất cả câu hỏi mới.")

        elif mode == QUIZ_MODE_NEW_RANDOM:
            new_q_ids = all_q_ids_in_set - answered_q_ids
            if new_q_ids:
                next_question_id = random.choice(list(new_q_ids))
            else:
                logger.info(f"{log_prefix} Đã hoàn thành tất cả câu hỏi mới.")
        
        elif mode == QUIZ_MODE_REVIEW:
            if answered_q_ids:
                # Lấy ngẫu nhiên một câu hỏi đã trả lời để ôn tập
                next_question_id = random.choice(list(answered_q_ids))
            else:
                logger.info(f"{log_prefix} Chưa có câu hỏi nào để ôn tập.")
        
        else:
            logger.error(f"{log_prefix} Chế độ không hợp lệ: {mode}")

        if next_question_id:
            next_question = self.get_question_by_id(next_question_id)
            if next_question.passage_id:
                # Nếu câu hỏi được tìm thấy thuộc về một đoạn văn, trả về tất cả câu hỏi trong đoạn văn đó
                questions_in_passage = QuizQuestion.query.filter(
                    QuizQuestion.set_id == set_id,
                    QuizQuestion.passage_id == next_question.passage_id
                ).order_by(QuizQuestion.passage_order.asc(), QuizQuestion.question_id.asc()).all()
                logger.info(f"{log_prefix} Tìm thấy nhóm câu hỏi mới từ đoạn văn (Passage ID: {next_question.passage_id}).")
                return questions_in_passage, next_question.passage
            else:
                # Nếu là câu hỏi độc lập, trả về một danh sách chứa một câu hỏi duy nhất
                logger.info(f"{log_prefix} Tìm thấy câu hỏi độc lập (ID: {next_question.question_id}).")
                return [next_question], None # Trả về list và None cho passage
        
        logger.info(f"{log_prefix} Không tìm thấy câu hỏi nào để hiển thị.")
        return None, None

    # KẾT THÚC THAY ĐỔI: Hàm get_next_question_group_for_user để trả về nhóm câu hỏi

    # BẮT ĐẦU THAY ĐỔI: Hàm process_user_answers để xử lý nhiều câu trả lời
    def process_user_answers(self, user_id, answers_data):
        """
        Mô tả: Xử lý nhiều câu trả lời của người dùng cho một nhóm câu hỏi, cập nhật tiến độ và điểm số cho từng câu.
        Args:
            user_id (int): ID của người dùng.
            answers_data (list): Danh sách các dictionary, mỗi dict chứa 'question_id' và 'selected_option'.
        Returns:
            list: Danh sách các dictionary kết quả, mỗi dict chứa 'question_id', 'is_correct', 'correct_answer', 'guidance'.
        """
        log_prefix = f"[QUIZ_SERVICE|ProcessAnswers|User:{user_id}]"
        logger.info(f"{log_prefix} Bắt đầu xử lý {len(answers_data)} câu trả lời.")

        results = []
        try:
            for answer in answers_data:
                question_id = answer.get('question_id')
                selected_option = answer.get('selected_option')

                question = self.get_question_by_id(question_id)
                if not question:
                    logger.error(f"{log_prefix} Không tìm thấy câu hỏi ID: {question_id}. Bỏ qua.")
                    results.append({
                        'question_id': question_id,
                        'is_correct': False,
                        'correct_answer': None,
                        'guidance': 'Không tìm thấy câu hỏi.',
                        'status': 'error'
                    })
                    continue

                is_correct = (selected_option == question.correct_answer)
                
                progress = UserQuizProgress.query.filter_by(user_id=user_id, question_id=question_id).first()
                if not progress:
                    progress = UserQuizProgress(user_id=user_id, question_id=question_id)
                    db.session.add(progress)
                
                # Khởi tạo giá trị nếu là None
                if progress.times_correct is None: progress.times_correct = 0
                if progress.times_incorrect is None: progress.times_incorrect = 0
                if progress.correct_streak is None: progress.correct_streak = 0

                progress.last_answered = int(time.time())
                score_change = 0
                
                is_first_correct = False
                if is_correct:
                    is_first_correct = (progress.times_correct == 0)
                    
                    if is_first_correct:
                        score_change = SCORE_QUIZ_CORRECT_FIRST_TIME
                        logger.info(f"{log_prefix} Câu hỏi {question_id}: ĐÚNG lần đầu. Điểm cộng: {score_change}")
                    else:
                        score_change = SCORE_QUIZ_CORRECT_REPEAT
                        logger.info(f"{log_prefix} Câu hỏi {question_id}: ĐÚNG (lặp lại). Điểm cộng: {score_change}")
                    
                    progress.times_correct += 1
                    progress.correct_streak += 1
                else:
                    progress.times_incorrect += 1
                    progress.correct_streak = 0
                    logger.info(f"{log_prefix} Câu hỏi {question_id}: SAI. Không cộng điểm.")
                
                # Cập nhật trạng thái mastered (ví dụ: 3 lần đúng liên tiếp)
                if progress.correct_streak >= 3: # Có thể điều chỉnh ngưỡng này trong config
                    progress.is_mastered = True
                else:
                    progress.is_mastered = False

                if score_change > 0:
                    user = User.query.get(user_id) # Lấy lại user để đảm bảo cập nhật điểm tổng
                    user.score = (user.score or 0) + score_change
                    db.session.add(user)
                    
                    reason = f"quiz_answer_{'first_correct' if is_first_correct else 'correct'}"
                    score_log = ScoreLog(
                        user_id=user_id,
                        score_change=score_change,
                        timestamp=int(time.time()),
                        reason=reason,
                        source_type='quiz'
                    )
                    db.session.add(score_log)
                    logger.info(f"{log_prefix} Câu hỏi {question_id}: Đã ghi ScoreLog cho Quiz: {score_change} điểm.")
                else:
                    logger.info(f"{log_prefix} Câu hỏi {question_id}: score_change là 0, không ghi ScoreLog.")
                
                db.session.add(progress) # Thêm progress vào session để commit
                
                results.append({
                    'question_id': question_id,
                    'is_correct': is_correct,
                    'correct_answer': question.correct_answer,
                    'guidance': question.guidance or '',
                    'status': 'success'
                })
            
            db.session.commit() # Commit tất cả các thay đổi sau khi xử lý tất cả câu hỏi
            logger.info(f"{log_prefix} Hoàn tất xử lý tất cả câu trả lời. Commit DB thành công.")
            return results
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi xử lý câu trả lời: {e}", exc_info=True)
            return [{'status': 'error', 'message': 'Lỗi server nội bộ khi xử lý câu trả lời.'}]
    # KẾT THÚC THAY ĐỔI: Hàm process_user_answers để xử lý nhiều câu trả lời

    def get_all_question_sets_with_details(self):
        """
        Mô tả: Lấy tất cả các bộ câu hỏi cùng với thông tin chi tiết.
        """
        log_prefix = "[QUIZ_SERVICE|GetAllSets]"
        try:
            sets = db.session.query(
                QuestionSet,
                User.username.label('creator_username'),
                db.func.count(QuizQuestion.question_id).label('question_count')
            ).outerjoin(User, QuestionSet.creator_user_id == User.user_id)\
             .outerjoin(QuizQuestion, QuestionSet.set_id == QuizQuestion.set_id)\
             .group_by(QuestionSet.set_id).order_by(QuestionSet.title).all()
            
            results = []
            for set_obj, creator_username, question_count in sets:
                set_obj.creator_username = creator_username or "N/A"
                set_obj.question_count = question_count
                results.append(set_obj)
            return results
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi truy vấn: {e}", exc_info=True)
            return []

    def get_question_set_by_id(self, set_id):
        """
        Mô tả: Lấy một bộ câu hỏi cụ thể bằng ID.
        Args:
            set_id (int): ID của bộ câu hỏi.
        Returns:
            QuestionSet: Đối tượng bộ câu hỏi nếu tìm thấy, ngược lại là None.
        """
        return QuestionSet.query.get(set_id)

    def get_question_by_id(self, question_id):
        """
        Mô tả: Lấy một câu hỏi trắc nghiệm cụ thể bằng ID.
        Args:
            question_id (int): ID của câu hỏi.
        Returns:
            QuizQuestion: Đối tượng câu hỏi nếu tìm thấy, ngược lại là None.
        """
        return QuizQuestion.query.get(question_id)

    def update_question(self, question_id, data, user_id):
        """
        Mô tả: Cập nhật nội dung của một câu hỏi.
        """
        log_prefix = f"[QUIZ_SERVICE|UpdateQ|Q:{question_id}|User:{user_id}]"
        logger.info(f"{log_prefix} Đang cập nhật câu hỏi.")

        question = self.get_question_by_id(question_id)
        if not question:
            return None, "question_not_found"

        user = User.query.get(user_id)
        if not user:
            return None, "user_not_found"

        set_creator_id = question.question_set.creator_user_id
        if user.user_role != 'admin' and user.user_id != set_creator_id:
            logger.warning(f"{log_prefix} Người dùng không có quyền sửa câu hỏi này.")
            return None, "permission_denied"

        try:
            # BẮT ĐẦU SỬA: Chuyển đổi chuỗi rỗng thành None cho các trường tùy chọn
            question.pre_question_text = data.get('pre_question_text') or None
            question.question = data.get('question') or None
            question.question_image_file = data.get('question_image_file') or None
            question.question_audio_file = data.get('question_audio_file') or None
            
            question.option_a = data.get('option_a')
            question.option_b = data.get('option_b')
            question.option_c = data.get('option_c') or None
            question.option_d = data.get('option_d') or None
            # KẾT THÚC SỬA
            question.correct_answer = data.get('correct_answer', question.correct_answer).upper()
            question.guidance = data.get('guidance') or None # SỬA: guidance cũng có thể là None
            
            # Cập nhật passage_order nếu có
            if 'passage_order' in data and data['passage_order'] is not None:
                try:
                    question.passage_order = int(data['passage_order'])
                except ValueError:
                    logger.warning(f"{log_prefix} passage_order không hợp lệ: {data['passage_order']}. Bỏ qua cập nhật.")
            else: # Nếu không có trong data hoặc là None, đặt về None
                question.passage_order = None
            
            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật câu hỏi thành công.")
            return question, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật câu hỏi: {e}", exc_info=True)
            return None, str(e)

    def _process_excel_file(self, question_set, file_stream, sync=False):
        """
        Mô tả: Xử lý file Excel được tải lên để thêm hoặc đồng bộ hóa câu hỏi.
               Hỗ trợ nhập liệu câu hỏi đơn lẻ và câu hỏi thuộc đoạn văn.
        Args:
            question_set (QuestionSet): Đối tượng bộ câu hỏi.
            file_stream (file-like object): Stream của file Excel.
            sync (bool): Nếu True, sẽ đồng bộ hóa (cập nhật/xóa) các câu hỏi hiện có.
                         Nếu False, chỉ thêm các câu hỏi mới.
        Raises:
            ValueError: Nếu file Excel thiếu các cột bắt buộc hoặc có lỗi dữ liệu.
        """
        log_prefix = f"[QUIZ_SERVICE|ProcessExcel|Set:{question_set.set_id}]"
        
        file_content = file_stream.read()
        in_memory_file = io.BytesIO(file_content)
        workbook = openpyxl.load_workbook(in_memory_file)

        sheet = workbook.active
        
        headers = [str(cell.value).strip().lower() if cell.value is not None else "" for cell in sheet[1]]
        # BẮT ĐẦU SỬA: Chỉ yêu cầu option_a và option_b là bắt buộc
        required_headers = ['question', 'option_a', 'option_b', 'correct_answer_text']
        # KẾT THÚC SỬA
        
        missing_headers = [h for h in required_headers if h not in headers]
        if missing_headers:
            error_message = (f"File Excel thiếu các cột bắt buộc: {', '.join(missing_headers)}. "
                             f"Các cột tìm thấy trong file của bạn là: {', '.join(h for h in headers if h)}.")
            raise ValueError(error_message)
        
        column_map = {header: idx for idx, header in enumerate(headers)}
        
        questions_from_excel = [] # Sẽ lưu các dict dữ liệu câu hỏi từ Excel
        passage_content_to_id_map = {} # Ánh xạ passage_hash -> passage_id

        # Lấy tất cả các đoạn văn hiện có để tránh tạo trùng lặp
        existing_passages = QuizPassage.query.all()
        for p in existing_passages:
            passage_content_to_id_map[p.passage_hash] = p.passage_id

        for row_index, row_cells in enumerate(sheet.iter_rows(min_row=2), start=2):
            row_values = [cell.value for cell in row_cells]
            
            # Lấy question_id từ Excel (nếu có)
            question_id_from_excel = None
            if 'question_id' in column_map and row_values[column_map['question_id']] is not None:
                try:
                    question_id_from_excel = int(row_values[column_map['question_id']])
                except ValueError:
                    logger.warning(f"{log_prefix} Hàng {row_index}: question_id không hợp lệ. Coi là câu hỏi mới.")

            # BẮT ĐẦU SỬA: Đọc giá trị và chuyển đổi rỗng thành None
            question_text = str(row_values[column_map.get('question')]).strip() if column_map.get('question') is not None and row_values[column_map.get('question')] is not None else ''
            question_image_file = str(row_values[column_map.get('question_image_file')]).strip() if column_map.get('question_image_file') is not None and row_values[column_map.get('question_image_file')] is not None else ''
            question_audio_file = str(row_values[column_map.get('question_audio_file')]).strip() if column_map.get('question_audio_file') is not None and row_values[column_map.get('question_audio_file')] is not None else ''

            # KẾT THÚC SỬA

            # BẮT ĐẦU SỬA: question_text không bắt buộc nếu có image hoặc audio
            if not question_text and not question_image_file and not question_audio_file:
                logger.warning(f"{log_prefix} Bỏ qua hàng {row_index} do thiếu nội dung câu hỏi và không có file media.")
                continue
            # KẾT THÚC SỬA

            option_a_text = str(row_values[column_map['option_a']]).strip()
            option_b_text = str(row_values[column_map['option_b']]).strip()
            # BẮT ĐẦU SỬA: option_c và option_d có thể rỗng
            option_c_text = str(row_values[column_map.get('option_c')]).strip() if column_map.get('option_c') is not None and row_values[column_map.get('option_c')] is not None else ''
            option_d_text = str(row_values[column_map.get('option_d')]).strip() if column_map.get('option_d') is not None and row_values[column_map.get('option_d')] is not None else ''
            # KẾT THÚC SỬA
            correct_answer_text = str(row_values[column_map['correct_answer_text']]).strip()

            determined_answer = None
            # BẮT ĐẦU SỬA: Kiểm tra đáp án đúng phải khớp với nội dung của option (nếu option đó không rỗng)
            if correct_answer_text and option_a_text and correct_answer_text == option_a_text:
                determined_answer = 'A'
            elif correct_answer_text and option_b_text and correct_answer_text == option_b_text:
                determined_answer = 'B'
            elif correct_answer_text and option_c_text and correct_answer_text == option_c_text:
                determined_answer = 'C'
            elif correct_answer_text and option_d_text and correct_answer_text == option_d_text:
                determined_answer = 'D'

            if not determined_answer:
                logger.warning(f"{log_prefix} Bỏ qua hàng {row_index} vì không tìm thấy đáp án đúng khớp với các lựa chọn hợp lệ.")
                continue
            # KẾT THÚC SỬA

            # Xử lý passage_text và passage_order
            passage_text_from_excel = str(row_values[column_map.get('passage_text')]).strip() \
                                      if column_map.get('passage_text') is not None and row_values[column_map.get('passage_text')] is not None else ''
            
            passage_order_from_excel = None
            if 'passage_order' in column_map and row_values[column_map['passage_order']] is not None:
                try:
                    passage_order_from_excel = int(row_values[column_map['passage_order']])
                except ValueError:
                    logger.warning(f"{log_prefix} Hàng {row_index}: passage_order không hợp lệ. Đặt là None.")

            passage_id_for_db = None
            if passage_text_from_excel:
                passage_hash = hashlib.sha256(passage_text_from_excel.encode('utf-8')).hexdigest()
                if passage_hash not in passage_content_to_id_map:
                    # Tạo đoạn văn mới nếu chưa tồn tại
                    new_passage = QuizPassage(passage_content=passage_text_from_excel, passage_hash=passage_hash)
                    db.session.add(new_passage)
                    db.session.flush() # Flush để lấy passage_id
                    passage_content_to_id_map[passage_hash] = new_passage.passage_id
                    logger.info(f"{log_prefix} Đã tạo đoạn văn mới (ID: {new_passage.passage_id}) từ hàng {row_index}.")
                passage_id_for_db = passage_content_to_id_map[passage_hash]
            
            question_data = {
                'question_id': question_id_from_excel, # Giữ lại ID để xử lý update/add
                'question': question_text or None, # Lưu rỗng thành None
                'option_a': option_a_text,
                'option_b': option_b_text,
                'option_c': option_c_text or None, # Lưu rỗng thành None
                'option_d': option_d_text or None, # Lưu rỗng thành None
                'correct_answer': determined_answer, 
                'pre_question_text': str(row_values[column_map.get('pre_question_text')]).strip() if column_map.get('pre_question_text') is not None and row_values[column_map.get('pre_question_text')] is not None else None,
                'guidance': str(row_values[column_map.get('guidance')]).strip() if column_map.get('guidance') is not None and row_values[column_map.get('guidance')] is not None else None,
                'question_image_file': question_image_file or None, # Lưu rỗng thành None
                'question_audio_file': question_audio_file or None, # Lưu rỗng thành None
                'passage_id': passage_id_for_db,
                'passage_order': passage_order_from_excel
            }
            questions_from_excel.append(question_data)

        if sync:
            # Lấy tất cả các câu hỏi hiện có trong bộ này
            existing_questions_map = {q.question_id: q for q in question_set.questions}
            excel_question_ids = {q_data['question_id'] for q_data in questions_from_excel if q_data['question_id'] is not None}

            for q_data in questions_from_excel:
                q_id = q_data.pop('question_id') # Lấy và xóa question_id khỏi dict để tránh lỗi khi dùng **q_data
                if q_id is not None and q_id in existing_questions_map:
                    # Cập nhật câu hỏi đã có
                    q_to_update = existing_questions_map[q_id]
                    for key, value in q_data.items():
                        setattr(q_to_update, key, value)
                    db.session.add(q_to_update)
                    logger.debug(f"{log_prefix} Cập nhật câu hỏi ID: {q_id}.")
                else:
                    # Thêm câu hỏi mới
                    new_question = QuizQuestion(set_id=question_set.set_id, **q_data)
                    db.session.add(new_question)
                    logger.debug(f"{log_prefix} Thêm câu hỏi mới từ Excel.")
            
            # Xóa các câu hỏi không còn trong file Excel
            questions_to_delete = [q for q_id, q in existing_questions_map.items() if q_id not in excel_question_ids]
            for q in questions_to_delete:
                db.session.delete(q)
                logger.debug(f"{log_prefix} Xóa câu hỏi ID: {q.question_id} không có trong Excel.")
            logger.info(f"{log_prefix} Đồng bộ hóa hoàn tất. Thêm/cập nhật {len(questions_from_excel)}, xóa {len(questions_to_delete)} câu hỏi.")
        else:
            # Chế độ thêm mới (không sync), chỉ thêm các câu hỏi mới từ Excel
            questions_to_add = []
            for q_data in questions_from_excel:
                q_data.pop('question_id') # Loại bỏ question_id vì đây là thêm mới
                new_question = QuizQuestion(set_id=question_set.set_id, **q_data)
                questions_to_add.append(new_question)
            
            if questions_to_add:
                db.session.bulk_save_objects(questions_to_add)
            logger.info(f"{log_prefix} Đã thêm {len(questions_to_add)} câu hỏi mới từ file.")

    def create_question_set(self, data, creator_id, file_stream=None):
        """
        Mô tả: Tạo một bộ câu hỏi mới, có thể kèm theo các câu hỏi từ file Excel.
        """
        log_prefix = f"[QUIZ_SERVICE|CreateSet|User:{creator_id}]"
        logger.info(f"{log_prefix} Đang tạo bộ câu hỏi mới.")
        
        try:
            new_set = QuestionSet(
                title=data.get('title'),
                description=data.get('description'),
                is_public=int(data.get('is_public', 1)),
                creator_user_id=creator_id
            )
            db.session.add(new_set)

            if file_stream:
                db.session.flush()
                logger.info(f"{log_prefix} Flushed session to get new set ID: {new_set.set_id}")
                self._process_excel_file(new_set, file_stream, sync=False) # sync=False để chỉ thêm mới

            db.session.commit()
            logger.info(f"{log_prefix} Tạo bộ câu hỏi '{new_set.title}' (ID: {new_set.set_id}) thành công.")
            return new_set, "success"
        except ValueError as ve:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi dữ liệu: {ve}", exc_info=True)
            return None, str(ve)
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi tạo bộ câu hỏi: {e}", exc_info=True)
            if "zip" in str(e).lower():
                 return None, "Lỗi đọc file Excel. Vui lòng đảm bảo file có định dạng .xlsx hợp lệ."
            return None, str(e)

    def update_question_set(self, set_id, data, file_stream=None):
        """
        Mô tả: Cập nhật thông tin và nội dung của một bộ câu hỏi.
        """
        log_prefix = f"[QUIZ_SERVICE|UpdateSet|Set:{set_id}]"
        logger.info(f"{log_prefix} Đang cập nhật bộ câu hỏi.")
        
        set_to_update = self.get_question_set_by_id(set_id)
        if not set_to_update:
            return None, "set_not_found"
            
        try:
            set_to_update.title = data.get('title', set_to_update.title)
            set_to_update.description = data.get('description', set_to_update.description)
            set_to_update.is_public = int(data.get('is_public', set_to_update.is_public))
            
            if file_stream:
                logger.info(f"{log_prefix} Phát hiện file Excel, bắt đầu đồng bộ hóa câu hỏi.")
                self._process_excel_file(set_to_update, file_stream, sync=True) # sync=True để đồng bộ hóa

            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật bộ câu hỏi '{set_to_update.title}' thành công.")
            return set_to_update, "success"
        except ValueError as ve:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi dữ liệu: {ve}", exc_info=True)
            return None, str(ve)
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật bộ câu hỏi: {e}", exc_info=True)
            return None, str(e)

    def delete_question_set(self, set_id):
        """
        Mô tả: Xóa một bộ câu hỏi và tất cả các câu hỏi bên trong nó.
        """
        log_prefix = f"[QUIZ_SERVICE|DeleteSet|Set:{set_id}]"
        logger.info(f"{log_prefix} Đang cố gắng xóa bộ câu hỏi.")
        
        set_to_delete = self.get_question_set_by_id(set_id)
        if not set_to_delete:
            logger.warning(f"{log_prefix} Không tìm thấy bộ câu hỏi để xóa.")
            return False, "set_not_found"
            
        try:
            db.session.delete(set_to_delete)
            db.session.commit()
            logger.info(f"{log_prefix} Xóa bộ câu hỏi '{set_to_delete.title}' thành công.")
            return True, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi xóa bộ câu hỏi: {e}", exc_info=True)
            return False, str(e)

    def export_set_to_excel(self, set_id):
        """
        Mô tả: Xuất tất cả các câu hỏi của một bộ ra file Excel trong bộ nhớ.
        """
        log_prefix = f"[QUIZ_SERVICE|ExportSet|Set:{set_id}]"
        logger.info(f"{log_prefix} Bắt đầu xuất bộ câu hỏi ra Excel.")
        
        set_to_export = self.get_question_set_by_id(set_id)
        if not set_to_export:
            logger.warning(f"{log_prefix} Không tìm thấy bộ câu hỏi để xuất.")
            return None

        try:
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            
            # --- BẮT ĐẦU SỬA LỖI: Làm sạch tên sheet ---
            invalid_chars = r'\/?*[]:'
            sanitized_title = "".join(c for c in set_to_export.title if c not in invalid_chars)
            sheet.title = sanitized_title[:30]
            # --- KẾT THÚC SỬA LỖI ---

            headers = ['question_id', 'pre_question_text', 'question', 'option_a', 'option_b', 'option_c', 'option_d', 
                       'correct_answer_text', 'guidance', 'question_image_file', 'question_audio_file',
                       'passage_text', 'passage_order']
            sheet.append(headers)

            sorted_questions = sorted(set_to_export.questions, 
                                      key=lambda q: (q.passage_id if q.passage_id is not None else float('inf'), 
                                                     q.passage_order if q.passage_order is not None else float('inf'), 
                                                     q.question_id))

            for q in sorted_questions:
                correct_answer_text = ""
                if q.correct_answer == 'A': correct_answer_text = q.option_a
                elif q.correct_answer == 'B': correct_answer_text = q.option_b
                elif q.correct_answer == 'C': correct_answer_text = q.option_c
                elif q.correct_answer == 'D': correct_answer_text = q.option_d

                passage_content_to_export = q.passage.passage_content if q.passage else None

                row_data = [
                    q.question_id, q.pre_question_text, q.question,
                    q.option_a, q.option_b, q.option_c, q.option_d,
                    correct_answer_text, q.guidance,
                    q.question_image_file, q.question_audio_file,
                    passage_content_to_export, q.passage_order
                ]
                sheet.append(row_data)
            
            excel_stream = io.BytesIO()
            workbook.save(excel_stream)
            excel_stream.seek(0)
            
            logger.info(f"{log_prefix} Xuất {len(set_to_export.questions)} câu hỏi ra Excel thành công.")
            return excel_stream
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi xuất bộ câu hỏi ra Excel: {e}", exc_info=True)
            return None

    def get_quiz_set_stats_for_user(self, user_id, set_id):
        """
        Mô tả: Lấy các số liệu thống kê chi tiết của một bộ câu hỏi quiz cụ thể cho người dùng.
        """
        log_prefix = f"[QUIZ_SERVICE|GetSetStats|User:{user_id}|Set:{set_id}]"
        logger.info(f"{log_prefix} Đang lấy thống kê bộ quiz.")

        stats = {
            'total_questions': 0, 'answered_questions': 0, 'correct_answers': 0,
            'incorrect_answers': 0, 'mastered_questions': 0, 'unanswered_questions': 0,
            'set_title': 'N/A',
            'set_id': set_id # BẮT ĐẦU THÊM MỚI: Thêm set_id vào dictionary trả về
        }

        question_set = QuestionSet.query.get(set_id)
        if not question_set:
            logger.warning(f"{log_prefix} Không tìm thấy bộ câu hỏi ID: {set_id}.")
            return stats

        stats['set_title'] = question_set.title
        stats['total_questions'] = QuizQuestion.query.filter_by(set_id=set_id).count()

        progress_in_quiz_set = UserQuizProgress.query.join(QuizQuestion)\
            .filter(QuizQuestion.set_id == set_id, UserQuizProgress.user_id == user_id)
        
        stats['answered_questions'] = progress_in_quiz_set.count()
        stats['correct_answers'] = progress_in_quiz_set.filter(UserQuizProgress.times_correct > 0).count()
        stats['incorrect_answers'] = progress_in_quiz_set.filter(UserQuizProgress.times_incorrect > 0).count()
        stats['mastered_questions'] = progress_in_quiz_set.filter(UserQuizProgress.is_mastered == True).count()
        stats['unanswered_questions'] = stats['total_questions'] - stats['answered_questions']

        logger.info(f"{log_prefix} Đã lấy thống kê bộ quiz thành công.")
        return stats

    def export_question_set_as_zip(self, set_id):
        """
        Mô tả: Xuất một bộ câu hỏi đầy đủ, bao gồm file Excel và các file media (ảnh, audio) vào một file ZIP.
        """
        log_prefix = f"[QUIZ_SERVICE|ExportZip|Set:{set_id}]"
        logger.info(f"{log_prefix} Bắt đầu xuất gói ZIP đầy đủ.")

        set_to_export = self.get_question_set_by_id(set_id)
        if not set_to_export:
            logger.warning(f"{log_prefix} Không tìm thấy bộ câu hỏi.")
            return None

        try:
            excel_stream = self.export_set_to_excel(set_id)
            if not excel_stream:
                logger.error(f"{log_prefix} Không thể tạo file Excel, hủy xuất ZIP.")
                return None

            zip_stream = io.BytesIO()
            with zipfile.ZipFile(zip_stream, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('data.xlsx', excel_stream.getvalue())
                logger.info(f"{log_prefix} Đã thêm data.xlsx vào file ZIP.")

                added_media_files = set()
                for question in set_to_export.questions:
                    # Xử lý hình ảnh
                    img_filename = question.question_image_file
                    if img_filename and img_filename not in added_media_files:
                        if img_filename.startswith('http://') or img_filename.startswith('https://'):
                            try:
                                response = requests.get(img_filename, stream=True, timeout=10)
                                if response.status_code == 200:
                                    safe_filename = hashlib.sha1(img_filename.encode()).hexdigest() + os.path.splitext(img_filename)[1]
                                    zf.writestr(os.path.join('images', safe_filename), response.content)
                                    added_media_files.add(img_filename)
                                    logger.debug(f"{log_prefix} Đã tải và thêm ảnh từ URL: images/{safe_filename}")
                                else:
                                    logger.warning(f"{log_prefix} Lỗi tải ảnh từ URL (status {response.status_code}): {img_filename}")
                            except requests.exceptions.RequestException as e:
                                logger.error(f"{log_prefix} Lỗi khi tải ảnh từ URL {img_filename}: {e}")
                        else:
                            img_path = os.path.join(QUIZ_IMAGES_DIR, img_filename)
                            if os.path.exists(img_path):
                                zf.write(img_path, os.path.join('images', img_filename))
                                added_media_files.add(img_filename)
                                logger.debug(f"{log_prefix} Đã thêm ảnh cục bộ: images/{img_filename}")
                            else:
                                logger.warning(f"{log_prefix} Không tìm thấy file ảnh cục bộ: {img_path}")

                    # Xử lý audio
                    audio_filename = question.question_audio_file
                    if audio_filename and audio_filename not in added_media_files:
                        if not (audio_filename.startswith('http://') or audio_filename.startswith('https://')):
                            audio_path = os.path.join(QUIZ_AUDIO_CACHE_DIR, audio_filename)
                            if os.path.exists(audio_path):
                                zf.write(audio_path, os.path.join('audio', audio_filename))
                                added_media_files.add(audio_filename)
                                logger.debug(f"{log_prefix} Đã thêm audio cục bộ: audio/{audio_filename}")
                            else:
                                logger.warning(f"{log_prefix} Không tìm thấy file audio cục bộ: {audio_path}")
            
            zip_stream.seek(0)
            logger.info(f"{log_prefix} Xuất gói ZIP thành công với {len(added_media_files)} file media.")
            return zip_stream

        except Exception as e:
            logger.error(f"{log_prefix} Lỗi nghiêm trọng khi tạo file ZIP: {e}", exc_info=True)
            return None
