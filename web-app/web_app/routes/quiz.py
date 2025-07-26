# web_app/routes/quiz.py
from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
import logging
from ..services import quiz_service, quiz_note_service
from ..models import db, User, QuizQuestion, UserQuizProgress, QuizPassage, QuestionSet
# BẮT ĐẦU SỬA: Import thêm config và func
from ..config import QUIZ_MODE_DISPLAY_NAMES, SETS_PER_PAGE
from sqlalchemy import func
# KẾT THÚC SỬA
from .decorators import login_required
from markupsafe import Markup, escape
import json
import os

quiz_bp = Blueprint('quiz', __name__, url_prefix='/quiz')
logger = logging.getLogger(__name__)

# BẮT ĐẦU THÊM MỚI: Sao chép lớp CustomPagination và hàm sắp xếp từ flashcard.py
class CustomPagination:
    def __init__(self, page, per_page, total, items):
        self.page = page
        self.per_page = per_page
        self.total = total
        self.items = items
        self.pages = (total + per_page - 1) // per_page if total > 0 else 0
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1
        self.next_num = page + 1
    
    def iter_pages(self, left_edge=1, right_edge=1, left_current=1, right_current=2):
        last_page = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last_page + 1 != num:
                    yield None
                yield num
                last_page = num

def _sort_sets_by_progress(set_items, total_key, completed_key):
    def custom_sort_key(set_item):
        total = getattr(set_item, total_key, 0)
        completed = getattr(set_item, completed_key, 0)
        title = getattr(set_item, 'title', '')
        if total == 0: return (float('-inf'), title) 
        percentage = (completed * 100 / total)
        if percentage == 100: return (0, title) 
        return (-percentage, title)
    return sorted(set_items, key=custom_sort_key)
# KẾT THÚC THÊM MỚI

def _serialize_quiz_question(q_data_dict):
    """
    Mô tả: Chuyển đổi đối tượng QuizQuestion và các dữ liệu liên quan thành dictionary.
    """
    question_obj = q_data_dict['obj']
    question_progress_obj = q_data_dict['progress']

    serialized_question = {
        'question_id': question_obj.question_id, 'set_id': question_obj.set_id,
        'pre_question_text': question_obj.pre_question_text, 'question': question_obj.question,
        'option_a': question_obj.option_a, 'option_b': question_obj.option_b,
        'option_c': question_obj.option_c, 'option_d': question_obj.option_d,
        'correct_answer': question_obj.correct_answer, 'guidance': question_obj.guidance,
        'question_image_file': question_obj.question_image_file,
        'question_audio_file': question_obj.question_audio_file,
        'passage_id': question_obj.passage_id, 'passage_order': question_obj.passage_order,
    }

    serialized_progress = None
    if question_progress_obj:
        serialized_progress = {
            'times_correct': question_progress_obj.times_correct,
            'times_incorrect': question_progress_obj.times_incorrect,
            'correct_streak': question_progress_obj.correct_streak,
            'is_mastered': question_progress_obj.is_mastered,
            'last_answered': question_progress_obj.last_answered
        }

    return {
        'obj': serialized_question,
        'can_edit': q_data_dict['can_edit'],
        'can_feedback': q_data_dict['can_feedback'],
        'has_note': q_data_dict['has_note'],
        'progress': serialized_progress,
        'display_pre_question_text': q_data_dict.get('display_pre_question_text', True),
        'display_audio_controls': q_data_dict.get('display_audio_controls', True),
        'display_image_controls': q_data_dict.get('display_image_controls', True),
        'is_first_in_group': q_data_dict.get('is_first_in_group', False)
    }

@quiz_bp.route('/')
@login_required
def index():
    # BẮT ĐẦU SỬA: Thêm logic phân trang
    user_id = session.get('user_id')
    page_started = request.args.get('page_started', 1, type=int)
    page_new = request.args.get('page_new', 1, type=int)

    # Lấy ID của các bộ đã bắt đầu
    started_set_ids_query = db.session.query(QuizQuestion.set_id).join(
        UserQuizProgress, UserQuizProgress.question_id == QuizQuestion.question_id
    ).filter(UserQuizProgress.user_id == user_id).distinct()
    started_set_ids = {row[0] for row in started_set_ids_query.all()}

    # Xử lý danh sách các bộ đã bắt đầu (sắp xếp và phân trang thủ công)
    started_sets_with_progress = []
    if started_set_ids:
        started_sets_raw = QuestionSet.query.filter(QuestionSet.set_id.in_(started_set_ids)).all()
        total_questions_map = dict(db.session.query(
            QuizQuestion.set_id, func.count(QuizQuestion.question_id)
        ).filter(QuizQuestion.set_id.in_(started_set_ids)).group_by(QuizQuestion.set_id).all())
        
        answered_questions_map = dict(db.session.query(
            QuizQuestion.set_id, func.count(UserQuizProgress.progress_id)
        ).join(QuizQuestion).filter(
            UserQuizProgress.user_id == user_id,
            QuizQuestion.set_id.in_(started_set_ids)
        ).group_by(QuizQuestion.set_id).all())

        for set_item in started_sets_raw:
            set_item.total_questions = total_questions_map.get(set_item.set_id, 0)
            set_item.answered_questions = answered_questions_map.get(set_item.set_id, 0)
            set_item.creator_username = set_item.creator.username if set_item.creator else "N/A"
            started_sets_with_progress.append(set_item)

    sorted_started_sets = _sort_sets_by_progress(started_sets_with_progress, 
                                                 total_key='total_questions', 
                                                 completed_key='answered_questions')
    
    total_items_started = len(sorted_started_sets)
    start_index_started = (page_started - 1) * SETS_PER_PAGE
    end_index_started = start_index_started + SETS_PER_PAGE
    paginated_started_sets_items = sorted_started_sets[start_index_started:end_index_started]
    started_sets_pagination = CustomPagination(page_started, SETS_PER_PAGE, total_items_started, paginated_started_sets_items)

    # Xử lý danh sách các bộ mới (dùng .paginate() của SQLAlchemy)
    new_sets_query = QuestionSet.query.filter(
        QuestionSet.is_public == True,
        ~QuestionSet.set_id.in_(started_set_ids)
    ).order_by(QuestionSet.title.asc())
    new_sets_pagination = new_sets_query.paginate(page=page_new, per_page=SETS_PER_PAGE, error_out=False)

    # Gán creator_username cho các mục trong trang hiện tại của new_sets
    for set_item in new_sets_pagination.items:
        set_item.creator_username = set_item.creator.username if set_item.creator else "N/A"

    return render_template('quiz/select_question_set.html', 
                           started_sets_pagination=started_sets_pagination, 
                           new_sets_pagination=new_sets_pagination)
    # KẾT THÚC SỬA

@quiz_bp.route('/take/<int:set_id>')
@login_required
def take_set(set_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    user.current_question_set_id = set_id
    db.session.commit()
    
    current_mode = user.current_quiz_mode
    questions, passage = quiz_service.get_next_question_group_for_user(user_id, set_id, current_mode)
    
    if not questions:
        flash("Chúc mừng! Bạn đã hoàn thành tất cả câu hỏi trong chế độ này.", "success")
        return redirect(url_for('quiz.index'))

    total_questions_in_set = QuizQuestion.query.filter_by(set_id=set_id).count()
    answered_count_in_set = UserQuizProgress.query.join(QuizQuestion).filter(
        UserQuizProgress.user_id == user_id, QuizQuestion.set_id == set_id
    ).count()

    progress_data = {'current': answered_count_in_set, 'total': total_questions_in_set}
    quiz_set_stats = quiz_service.get_quiz_set_stats_for_user(user_id, set_id)
    
    questions_data_for_template = []
    common_audio_file_for_group = None
    common_image_file_for_group = None
    
    if passage:
        first_q_audio = questions[0].question_audio_file if questions and questions[0].question_audio_file else None
        if first_q_audio and all((q.question_audio_file or '') == first_q_audio for q in questions):
            common_audio_file_for_group = first_q_audio

        first_q_image = questions[0].question_image_file if questions and questions[0].question_image_file else None
        if first_q_image and all((q.question_image_file or '') == first_q_image for q in questions):
            common_image_file_for_group = first_q_image

    for i, q in enumerate(questions):
        can_edit_q = (user.user_id == q.question_set.creator_user_id)
        can_feedback_q = not can_edit_q
        
        note = quiz_note_service.get_note_by_question_id(user_id, q.question_id)
        question_progress = UserQuizProgress.query.filter_by(user_id=user_id, question_id=q.question_id).first()

        display_pre_text = i == 0 or (q.passage_id is None or q.pre_question_text != questions[i-1].pre_question_text)
        
        questions_data_for_template.append({
            'obj': q,
            'can_edit': can_edit_q,
            'can_feedback': can_feedback_q,
            'has_note': note is not None,
            'progress': question_progress,
            'display_pre_question_text': display_pre_text,
            'display_audio_controls': not common_audio_file_for_group and q.question_audio_file,
            'display_image_controls': not common_image_file_for_group and q.question_image_file,
            'is_first_in_group': (i == 0)
        })
    
    serialized_questions_data = [_serialize_quiz_question(q_data) for q_data in questions_data_for_template]
    serialized_questions_data_json_safe = escape(json.dumps(serialized_questions_data))

    return render_template('quiz/take_quiz.html', 
                           questions=questions_data_for_template,
                           current_passage=passage,
                           progress=progress_data,
                           current_mode_display=QUIZ_MODE_DISPLAY_NAMES.get(current_mode, "Không rõ"),
                           quiz_set_stats=quiz_set_stats,
                           body_class='body-quiz-page',
                           serialized_questions_data_json=serialized_questions_data_json_safe,
                           common_audio_file_for_group=common_audio_file_for_group,
                           common_image_file_for_group=common_image_file_for_group)

@quiz_bp.route('/submit_answers', methods=['POST'])
@login_required
def submit_answers():
    user_id = session.get('user_id')
    data = request.get_json()
    if not data or not isinstance(data, list):
        return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400
    results = quiz_service.process_user_answers(user_id, data)
    if not results or any(r.get('status') == 'error' for r in results):
        return jsonify({'status': 'error', 'message': 'Lỗi khi xử lý câu trả lời.', 'results': results}), 500
    return jsonify({'status': 'success', 'message': 'Đã nộp câu trả lời thành công!', 'results': results})

@quiz_bp.route('/select-mode')
@login_required
def select_mode():
    user = User.query.get(session.get('user_id'))
    return render_template('quiz/select_quiz_mode.html', 
                           modes=QUIZ_MODE_DISPLAY_NAMES, 
                           current_mode=user.current_quiz_mode)

@quiz_bp.route('/set-mode/<string:mode_code>')
@login_required
def set_quiz_mode(mode_code):
    if mode_code not in QUIZ_MODE_DISPLAY_NAMES:
        flash("Chế độ làm bài không hợp lệ.", "error")
        return redirect(url_for('quiz.select_mode'))
    
    user = User.query.get(session.get('user_id'))
    user.current_quiz_mode = mode_code
    db.session.commit()
    flash(f"Chế độ làm bài đã được thay đổi thành '{QUIZ_MODE_DISPLAY_NAMES[mode_code]}'.", "success")
    
    current_set_id = user.current_question_set_id
    if current_set_id:
        return redirect(url_for('quiz.take_set', set_id=current_set_id))
    return redirect(url_for('quiz.index'))
