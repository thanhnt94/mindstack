# web_app/routes/quiz.py
from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
import logging
from ..services import quiz_service, quiz_note_service
from ..models import db, User, QuizQuestion, UserQuizProgress, QuizPassage 
from ..config import QUIZ_MODE_DISPLAY_NAMES
from .decorators import login_required
from markupsafe import Markup, escape
import json
import os

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

# BẮT ĐẦU THÊM MỚI: Hàm kiểm tra quyền gửi feedback
def _check_quiz_feedback_permission(user, question_obj):
    """
    Mô tả: Kiểm tra xem người dùng có quyền gửi feedback cho câu hỏi hay không.
           Người dùng có thể gửi feedback nếu họ KHÔNG phải là người tạo hoặc admin.
    """
    if not user or not question_obj:
        return False
    # Nếu người dùng có quyền sửa, họ không cần gửi feedback
    return not _check_quiz_edit_permission(user, question_obj)
# KẾT THÚC THÊM MỚI

def _serialize_quiz_question(q_data_dict):
    """
    Mô tả: Chuyển đổi đối tượng QuizQuestion và các dữ liệu liên quan thành một dictionary
           có thể JSON serializable.
    """
    question_obj = q_data_dict['obj']
    question_progress_obj = q_data_dict['progress']

    question_audio_filepath = question_obj.question_audio_file
    question_image_filepath = question_obj.question_image_file

    serialized_question = {
        'question_id': question_obj.question_id,
        'set_id': question_obj.set_id,
        'pre_question_text': question_obj.pre_question_text,
        'question': question_obj.question,
        'option_a': question_obj.option_a,
        'option_b': question_obj.option_b,
        'option_c': question_obj.option_c,
        'option_d': question_obj.option_d,
        'correct_answer': question_obj.correct_answer,
        'guidance': question_obj.guidance,
        'question_image_file': question_image_filepath,
        'question_audio_file': question_audio_filepath,
        'passage_id': question_obj.passage_id,
        'passage_order': question_obj.passage_order,
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
        'can_feedback': q_data_dict['can_feedback'], # THÊM MỚI
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
    Mô tả: Bắt đầu làm bài hoặc lấy nhóm câu hỏi tiếp theo trong một bộ đề.
    """
    user_id = session.get('user_id')
    log_prefix = f"[QUIZ_ROUTE|TakeSet|User:{user_id}|Set:{set_id}]"
    
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
        UserQuizProgress.user_id == user_id,
        QuizQuestion.set_id == set_id
    ).count()

    progress_data = {
        'current': answered_count_in_set,
        'total': total_questions_in_set
    }
    
    quiz_set_stats = quiz_service.get_quiz_set_stats_for_user(user_id, set_id)
    
    questions_data_for_template = []
    
    previous_pre_question_text = None
    previous_audio_file = None
    previous_image_file = None
    previous_passage_id = None

    common_audio_file_for_group = None
    common_image_file_for_group = None
    
    if passage:
        first_q_audio_in_group = questions[0].question_audio_file if questions else None
        if first_q_audio_in_group and first_q_audio_in_group.strip():
            all_share_same_audio = all((q.question_audio_file or '') == first_q_audio_in_group for q in questions)
            if all_share_same_audio:
                common_audio_file_for_group = first_q_audio_in_group

        first_q_image_in_group = questions[0].question_image_file if questions else None
        if first_q_image_in_group and first_q_image_in_group.strip():
            all_share_same_image = all((q.question_image_file or '') == first_q_image_in_group for q in questions)
            if all_share_same_image:
                common_image_file_for_group = first_q_image_in_group

    for i, q in enumerate(questions):
        can_edit_q = _check_quiz_edit_permission(user, q)
        can_feedback_q = _check_quiz_feedback_permission(user, q) # THÊM MỚI
        note = quiz_note_service.get_note_by_question_id(user_id, q.question_id)
        has_note_q = note is not None
        
        question_progress = UserQuizProgress.query.filter_by(
            user_id=user_id,
            question_id=q.question_id
        ).first()

        display_pre_question_text_flag = True
        display_audio_controls_flag = True
        display_image_controls_flag = True

        if i > 0 and q.passage_id is not None and q.passage_id == questions[i-1].passage_id:
            if q.pre_question_text == previous_pre_question_text:
                display_pre_question_text_flag = False
        
        if common_audio_file_for_group:
            display_audio_controls_flag = False
        elif not q.question_audio_file or not q.question_audio_file.strip():
            display_audio_controls_flag = False

        if common_image_file_for_group:
            display_image_controls_flag = False
        elif not q.question_image_file or not q.question_image_file.strip():
            display_image_controls_flag = False

        questions_data_for_template.append({
            'obj': q,
            'can_edit': can_edit_q,
            'can_feedback': can_feedback_q, # THÊM MỚI
            'has_note': has_note_q,
            'progress': question_progress,
            'display_pre_question_text': display_pre_question_text_flag,
            'display_audio_controls': display_audio_controls_flag,
            'display_image_controls': display_image_controls_flag,
            'is_first_in_group': (i == 0)
        })
        
        previous_pre_question_text = q.pre_question_text
        previous_audio_file = q.question_audio_file
        previous_image_file = q.question_image_file
        previous_passage_id = q.passage_id
    
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
                           common_image_file_for_group=common_image_file_for_group
                           )

@quiz_bp.route('/submit_answers', methods=['POST'])
@login_required
def submit_answers():
    """
    Mô tả: API endpoint để kiểm tra nhiều câu trả lời của người dùng cùng lúc.
    """
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
