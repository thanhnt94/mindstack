# web_app/routes/quiz.py
from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
import logging
from ..services import quiz_service, quiz_note_service
from ..models import db, User, QuizQuestion, UserQuizProgress # Thêm QuizQuestion để truy cập passage
from ..config import QUIZ_MODE_DISPLAY_NAMES
from .decorators import login_required

quiz_bp = Blueprint('quiz', __name__, url_prefix='/quiz')
logger = logging.getLogger(__name__)

def _check_quiz_edit_permission(user, question_obj):
    """
    Mô tả: Kiểm tra xem người dùng có quyền sửa một câu hỏi trắc nghiệm hay không.
    """
    if not user or not question_obj:
        return False
    set_creator_id = question_obj.question_set.creator_user_id
    return user.user_role == 'admin' or user.user_id == set_creator_id

@quiz_bp.route('/')
@login_required
def index():
    """
    Mô tả: Hiển thị trang cho người dùng chọn một bộ câu hỏi để làm bài.
    """
    user_id = session.get('user_id')
    started_sets, new_sets = quiz_service.get_categorized_question_sets_for_user(user_id)
    return render_template('quiz/select_question_set.html', 
                           started_sets=started_sets, 
                           new_sets=new_sets)

@quiz_bp.route('/take/<int:set_id>')
@login_required
def take_set(set_id):
    """
    Mô tả: Bắt đầu làm bài hoặc lấy câu hỏi tiếp theo trong một bộ đề.
    """
    user_id = session.get('user_id')
    log_prefix = f"[QUIZ_ROUTE|TakeSet|User:{user_id}|Set:{set_id}]"
    
    user = User.query.get(user_id)
    user.current_question_set_id = set_id
    db.session.commit()
    
    current_mode = user.current_quiz_mode
    question = quiz_service.get_next_question_for_user(user_id, set_id, current_mode)
    
    if not question:
        flash("Chúc mừng! Bạn đã hoàn thành tất cả câu hỏi trong chế độ này.", "success")
        return redirect(url_for('quiz.index'))

    can_edit = _check_quiz_edit_permission(user, question)
    note = quiz_note_service.get_note_by_question_id(user_id, question.question_id)
    has_note = note is not None

    total_questions = len(question.question_set.questions)
    answered_count = UserQuizProgress.query.join(QuizQuestion).filter(
        UserQuizProgress.user_id == user_id,
        QuizQuestion.set_id == set_id
    ).count()

    progress = {
        'current': answered_count + 1,
        'total': total_questions
    }
    
    # BẮT ĐẦU THAY ĐỔI: Lấy nội dung đoạn văn từ quan hệ 'passage'
    passage_content_to_display = question.passage.passage_content if question.passage else None
    # KẾT THÚC THAY ĐỔI

    logger.info(f"{log_prefix} Hiển thị câu hỏi ID: {question.question_id} ở chế độ '{current_mode}'")
    return render_template('quiz/take_quiz.html', 
                           question=question, 
                           progress=progress, 
                           current_mode_display=QUIZ_MODE_DISPLAY_NAMES.get(current_mode, "Không rõ"),
                           can_edit=can_edit,
                           has_note=has_note,
                           # BẮT ĐẦU THAY ĐỔI: Truyền dữ liệu đoạn văn đến template
                           passage_content=passage_content_to_display
                           # KẾT THÚC THAY ĐỔI
                           )

@quiz_bp.route('/check_answer/<int:question_id>', methods=['POST'])
@login_required
def check_answer(question_id):
    """
    Mô tả: API endpoint để kiểm tra câu trả lời của người dùng.
    """
    user_id = session.get('user_id')
    data = request.get_json()
    selected_option = data.get('option')

    if not selected_option:
        return jsonify({'status': 'error', 'message': 'Vui lòng chọn một đáp án.'}), 400

    is_correct, correct_answer = quiz_service.process_user_answer(user_id, question_id, selected_option)
    
    if is_correct is None:
        return jsonify({'status': 'error', 'message': 'Lỗi khi xử lý câu trả lời.'}), 500

    question = quiz_service.get_question_by_id(question_id)
    
    return jsonify({
        'status': 'success',
        'is_correct': is_correct,
        'correct_answer': correct_answer,
        'guidance': question.guidance or ''
    })

@quiz_bp.route('/select-mode')
@login_required
def select_mode():
    """
    Mô tả: Hiển thị trang cho phép người dùng chọn chế độ làm quiz.
    """
    user = User.query.get(session.get('user_id'))
    return render_template('quiz/select_quiz_mode.html', 
                           modes=QUIZ_MODE_DISPLAY_NAMES, 
                           current_mode=user.current_quiz_mode)

@quiz_bp.route('/set-mode/<string:mode_code>')
@login_required
def set_quiz_mode(mode_code):
    """
    Mô tả: Cập nhật chế độ làm quiz của người dùng và chuyển hướng họ.
    """
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

