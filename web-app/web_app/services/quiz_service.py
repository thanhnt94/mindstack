# web_app/services/quiz_service.py
import logging
import openpyxl
import io
import random
import time
import hashlib # Import hashlib để tạo hash cho đoạn văn
from sqlalchemy import func
from ..models import db, QuestionSet, User, QuizQuestion, UserQuizProgress, ScoreLog, QuizPassage # Thêm QuizPassage

# BẮT ĐẦU SỬA LỖI: Đảm bảo tất cả các hằng số cần thiết được import từ config.py
from ..config import (
    SCORE_QUIZ_CORRECT_FIRST_TIME, SCORE_QUIZ_CORRECT_REPEAT,
    QUIZ_MODE_NEW_SEQUENTIAL, QUIZ_MODE_NEW_RANDOM, QUIZ_MODE_REVIEW
)
# Vui lòng đảm bảo các hằng số trên đã được định nghĩa trong web_app/config.py của bạn.
# KẾT THÚC SỬA LỖI

logger = logging.getLogger(__name__)

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
            
            started_sets = []
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
                    started_sets.append(s)

            new_sets_query = QuestionSet.query.filter(
                QuestionSet.is_public == True,
                ~QuestionSet.set_id.in_(started_set_ids)
            ).order_by(QuestionSet.title)
            new_sets = new_sets_query.all()
            for s in new_sets:
                 s.creator_username = s.creator.username if s.creator else "N/A"

            logger.info(f"{log_prefix} Tìm thấy {len(started_sets)} bộ đã bắt đầu và {len(new_sets)} bộ mới.")
            return started_sets, new_sets

        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi phân loại bộ câu hỏi: {e}", exc_info=True)
            return [], []

    def get_next_question_for_user(self, user_id, set_id, mode):
        """
        Mô tả: Lấy câu hỏi tiếp theo cho người dùng dựa trên chế độ đã chọn.
               Ưu tiên các câu hỏi trong cùng một nhóm đoạn văn nếu người dùng đang làm dở.
        """
        log_prefix = f"[QUIZ_SERVICE|GetNextQ|User:{user_id}|Set:{set_id}|Mode:{mode}]"
        
        # Lấy tất cả các ID câu hỏi trong bộ
        all_q_ids_in_set = {row[0] for row in QuizQuestion.query.with_entities(QuizQuestion.question_id).filter_by(set_id=set_id).all()}
        if not all_q_ids_in_set:
            logger.warning(f"{log_prefix} Bộ câu hỏi này không có câu hỏi nào.")
            return None

        # Lấy các ID câu hỏi mà người dùng đã trả lời trong bộ này
        answered_q_ids = {row[0] for row in UserQuizProgress.query.with_entities(UserQuizProgress.question_id).filter_by(user_id=user_id).join(QuizQuestion).filter(QuizQuestion.set_id == set_id).all()}
        
        next_question_id = None
        
        # Logic ưu tiên câu hỏi trong cùng nhóm đoạn văn (dựa trên passage_id và passage_order)
        user = User.query.get(user_id)
        if user and user.current_question_set_id == set_id: # Đảm bảo người dùng đang ở đúng bộ quiz
            # Tìm câu hỏi cuối cùng mà người dùng đã trả lời trong bộ này
            last_answered_progress = UserQuizProgress.query.filter_by(user_id=user_id)\
                                     .join(QuizQuestion).filter(QuizQuestion.set_id == set_id)\
                                     .order_by(UserQuizProgress.last_answered.desc())\
                                     .first()
            
            if last_answered_progress and last_answered_progress.question.passage_id:
                current_passage_id = last_answered_progress.question.passage_id
                
                # Tìm câu hỏi tiếp theo trong cùng nhóm đoạn văn chưa được trả lời, sắp xếp theo passage_order
                next_question_in_passage = QuizQuestion.query.filter(
                    QuizQuestion.set_id == set_id,
                    QuizQuestion.passage_id == current_passage_id,
                    ~QuizQuestion.progresses.any(user_id=user_id) # Chưa được trả lời bởi người dùng này
                ).order_by(QuizQuestion.passage_order.asc(), QuizQuestion.question_id.asc()).first() # Sắp xếp theo order, sau đó ID
                
                if next_question_in_passage:
                    logger.info(f"{log_prefix} Tìm thấy câu hỏi tiếp theo trong cùng nhóm đoạn văn (ID: {next_question_in_passage.question_id}).")
                    return next_question_in_passage
                else:
                    logger.info(f"{log_prefix} Đã hoàn thành nhóm đoạn văn hiện tại. Chuyển sang tìm câu hỏi mới/ôn tập.")
        
        # Logic cũ để tìm câu hỏi mới/ôn tập
        if mode == QUIZ_MODE_NEW_SEQUENTIAL:
            new_q_ids = all_q_ids_in_set - answered_q_ids
            if new_q_ids:
                # Sắp xếp theo question_id để đảm bảo tuần tự
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
            return self.get_question_by_id(next_question_id)
        
        return None

    def process_user_answer(self, user_id, question_id, selected_option):
        """
        Mô tả: Xử lý câu trả lời của người dùng, cập nhật tiến độ và điểm số.
        """
        log_prefix = f"[QUIZ_SERVICE|ProcessAnswer|User:{user_id}|Q:{question_id}]"
        
        question = self.get_question_by_id(question_id)
        if not question:
            return None, None

        is_correct = (selected_option == question.correct_answer)
        
        try:
            progress = UserQuizProgress.query.filter_by(user_id=user_id, question_id=question_id).first()
            if not progress:
                progress = UserQuizProgress(user_id=user_id, question_id=question_id)
                db.session.add(progress)
            
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
                else:
                    score_change = SCORE_QUIZ_CORRECT_REPEAT
                
                progress.times_correct += 1
                progress.correct_streak += 1
            else:
                progress.times_incorrect += 1
                progress.correct_streak = 0
            
            if score_change > 0:
                user = User.query.get(user_id)
                user.score = (user.score or 0) + score_change
                
                reason = f"quiz_answer_{'first_correct' if is_first_correct else 'correct'}"
                score_log = ScoreLog(
                    user_id=user_id,
                    score_change=score_change,
                    timestamp=int(time.time()),
                    reason=reason,
                    source_type='quiz'
                )
                db.session.add(score_log)

            db.session.commit()
            return is_correct, question.correct_answer
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi xử lý câu trả lời: {e}", exc_info=True)
            return None, None

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
            sheet.title = set_to_export.title[:30]

            # Thêm các cột mới cho export (question_id, passage_text, passage_order)
            # BẮT ĐẦU SỬA: option_c và option_d là tùy chọn trong Excel
            headers = ['question_id', 'pre_question_text', 'question', 'option_a', 'option_b', 'option_c', 'option_d', 
                       'correct_answer_text', 'guidance', 'question_image_file', 'question_audio_file',
                       'passage_text', 'passage_order']
            # KẾT THÚC SỬA
            sheet.append(headers)

            # Sắp xếp câu hỏi để các câu trong cùng đoạn văn xuất hiện liền kề và theo thứ tự
            # Ưu tiên sắp xếp theo passage_id, sau đó là passage_order, cuối cùng là question_id
            sorted_questions = sorted(set_to_export.questions, 
                                      key=lambda q: (q.passage_id if q.passage_id is not None else float('inf'), 
                                                     q.passage_order if q.passage_order is not None else float('inf'), 
                                                     q.question_id))

            for q in sorted_questions: # Sử dụng danh sách đã sắp xếp
                correct_answer_text = ""
                if q.correct_answer == 'A':
                    correct_answer_text = q.option_a
                elif q.correct_answer == 'B':
                    correct_answer_text = q.option_b
                elif q.correct_answer == 'C':
                    correct_answer_text = q.option_c
                elif q.correct_answer == 'D':
                    correct_answer_text = q.option_d

                # Lấy passage_content từ QuizPassage
                passage_content_to_export = q.passage.passage_content if q.passage else None

                row_data = [
                    q.question_id, # Thêm question_id vào hàng xuất
                    q.pre_question_text, q.question,
                    q.option_a, q.option_b, q.option_c, q.option_d, # THÊM: option_c, option_d
                    correct_answer_text,
                    q.guidance,
                    q.question_image_file, q.question_audio_file,
                    passage_content_to_export, # Sử dụng passage_content từ QuizPassage
                    q.passage_order # Thêm passage_order vào hàng xuất
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

