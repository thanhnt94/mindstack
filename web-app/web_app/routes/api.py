# web_app/routes/api.py
from flask import Blueprint, send_file, session, jsonify, request, redirect, Response # Bỏ make_response
import logging
import os
import asyncio
import hashlib
from ..services import audio_service, note_service, flashcard_service, quiz_service, quiz_note_service, feedback_service
from ..models import Flashcard, QuizQuestion, UserQuizProgress, QuizPassage, User 
from ..config import FLASHCARD_IMAGES_DIR, QUIZ_IMAGES_DIR, QUIZ_AUDIO_CACHE_DIR 
from .decorators import login_required
from ..db_instance import db 

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

def _check_edit_permission(user_id, flashcard_obj):
    """
    Mô tả: Helper function để kiểm tra quyền sửa thẻ.
    Args:
        user_id (int): ID của người dùng hiện tại.
        flashcard_obj (Flashcard): Đối tượng flashcard cần kiểm tra.
    Returns:
        bool: True nếu người dùng có quyền, False nếu không.
    """
    user = User.query.get(user_id)
    if not user or not flashcard_obj:
        return False
    set_creator_id = flashcard_obj.vocabulary_set.creator_user_id
    return user.user_role == 'admin' or user.user_id == set_creator_id

@api_bp.route('/card_audio/<int:flashcard_id>/<string:side>')
@login_required
def get_card_audio(flashcard_id, side):
    """
    Mô tả: Phục vụ file audio cho một mặt của flashcard.
    Args:
        flashcard_id (int): ID của flashcard.
        side (str): 'front' hoặc 'back' của flashcard.
    Returns:
        send_file: File audio nếu thành công.
        jsonify: Thông báo lỗi nếu có vấn đề.
    """
    if side not in ['front', 'back']:
        logger.warning(f"Yêu cầu audio flashcard {flashcard_id} với mặt không hợp lệ: {side}")
        return jsonify({"error": "Mặt thẻ không hợp lệ"}), 400

    flashcard = Flashcard.query.get_or_404(flashcard_id)
    audio_content = flashcard.front_audio_content if side == 'front' else flashcard.back_audio_content

    if not audio_content or not audio_content.strip():
        logger.info(f"Flashcard {flashcard_id} ({side}) không có nội dung audio.")
        return jsonify({"error": "Không có nội dung audio cho mặt này"}), 404

    try:
        # BẮT ĐẦU SỬA LỖI: Nhận kết quả trả về từ audio_service đúng cách
        audio_file_path, success, message = asyncio.run(audio_service.get_cached_or_generate_audio(audio_content))
        
        if success and audio_file_path and os.path.exists(audio_file_path):
            logger.info(f"Phục vụ audio thành công cho flashcard {flashcard_id} ({side}): {audio_file_path}")
            return send_file(audio_file_path, mimetype="audio/mpeg")
        else:
            # Ghi log lỗi chi tiết hơn từ service
            logger.error(f"Lỗi khi phục vụ audio flashcard {flashcard_id} ({side}): {message}")
            return jsonify({"error": f"Không thể tạo hoặc lấy file audio: {message}"}), 500
    except Exception as e:
        logger.error(f"Lỗi không mong muốn khi phục vụ audio flashcard {flashcard_id} ({side}): {e}", exc_info=True)
        return jsonify({"error": "Lỗi server nội bộ khi xử lý audio"}), 500

@api_bp.route('/flashcard_images/<path:filename>')
def serve_flashcard_image(filename):
    """
    Mô tả: Phục vụ hình ảnh cho flashcard từ thư mục cache.
    Args:
        filename (str): Tên file hình ảnh.
    Returns:
        send_file: File hình ảnh nếu tìm thấy.
        Response: 404 hoặc 500 nếu không tìm thấy hoặc lỗi.
    """
    try:
        full_path = os.path.join(FLASHCARD_IMAGES_DIR, filename)
        if not os.path.exists(full_path):
            logger.warning(f"Không tìm thấy hình ảnh Flashcard: {full_path}")
            return "Flashcard Image not found", 404
        return send_file(full_path)
    except Exception as e:
        logger.error(f"Lỗi khi phục vụ hình ảnh Flashcard {filename}: {e}", exc_info=True)
        return "Internal server error", 500

@api_bp.route('/quiz_images/<path:filename>')
def serve_quiz_image(filename):
    """
    Mô tả: Phục vụ hình ảnh cho quiz từ thư mục cache.
    Args:
        filename (str): Tên file hình ảnh.
    Returns:
        send_file: File hình ảnh nếu tìm thấy.
        Response: 404 hoặc 500 nếu không tìm thấy hoặc lỗi.
    """
    try:
        full_path = os.path.join(QUIZ_IMAGES_DIR, filename)
        if not os.path.exists(full_path):
            logger.warning(f"Không tìm thấy hình ảnh Quiz: {full_path}")
            return "Quiz Image not found", 404
        return send_file(full_path)
    except Exception as e:
        logger.error(f"Lỗi khi phục vụ hình ảnh Quiz {filename}: {e}", exc_info=True)
        return "Internal server error", 500

@api_bp.route('/note/<int:flashcard_id>', methods=['GET', 'POST'])
@login_required
def handle_note(flashcard_id):
    """
    Mô tả: Xử lý việc lấy và cập nhật ghi chú cho flashcard.
    Args:
        flashcard_id (int): ID của flashcard.
    Returns:
        jsonify: Dữ liệu ghi chú hoặc trạng thái cập nhật.
    """
    user_id = session.get('user_id')
    if request.method == 'GET':
        note = note_service.get_note_by_flashcard_id(user_id, flashcard_id)
        return jsonify({'note': note.note if note else ""})
    if request.method == 'POST':
        data = request.get_json()
        if not data or 'note' not in data:
            return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400
        note_obj, status, message = note_service.create_or_update_note(user_id, flashcard_id, data['note'])
        if status == "error":
            return jsonify({'status': 'error', 'message': message}), 500
        return jsonify({'status': status, 'message': message, 'note': note_obj.note})

@api_bp.route('/flashcard/details/<int:flashcard_id>', methods=['GET'])
@login_required
def get_flashcard_details(flashcard_id):
    """
    Mô tả: Lấy chi tiết của một flashcard.
    Args:
        flashcard_id (int): ID của flashcard.
    Returns:
        jsonify: Dữ liệu chi tiết flashcard hoặc thông báo lỗi.
    """
    card = flashcard_service.get_card_by_id(flashcard_id)
    if not card:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy thẻ.'}), 404
    card_data = {'front': card.front, 'back': card.back, 'front_audio_content': card.front_audio_content, 'back_audio_content': card.back_audio_content, 'front_img': card.front_img, 'back_img': card.back_img}
    return jsonify({'status': 'success', 'data': card_data})

@api_bp.route('/flashcard/edit/<int:flashcard_id>', methods=['POST'])
@login_required
def edit_flashcard(flashcard_id):
    """
    Mô tả: Chỉnh sửa nội dung của một flashcard.
    Args:
        flashcard_id (int): ID của flashcard cần chỉnh sửa.
    Returns:
        jsonify: Trạng thái cập nhật và thông báo.
    """
    user_id = session.get('user_id')
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400
    updated_card, status = flashcard_service.update_card(flashcard_id, data, user_id)
    if status != "success":
        message_map = {"permission_denied": "Bạn không có quyền sửa thẻ này.", "card_not_found": "Không tìm thấy thẻ."}
        return jsonify({'status': 'error', 'message': message_map.get(status, "Lỗi server.")}), 403 if status == "permission_denied" else 404 if status == "card_not_found" else 500
    card_data = {'front': updated_card.front, 'back': updated_card.back, 'front_img': updated_card.front_img, 'back_img': updated_card.back_img}
    return jsonify({'status': 'success', 'message': 'Cập nhật thành công!', 'data': card_data})

@api_bp.route('/flashcard/regenerate_audio/<int:flashcard_id>/<string:side>', methods=['POST'])
@login_required
def regenerate_audio(flashcard_id, side):
    """
    Mô tả: API để tái tạo audio cho một mặt của flashcard.
    Args:
        flashcard_id (int): ID của flashcard.
        side (str): 'front' hoặc 'back'.
    Returns:
        jsonify: Trạng thái và thông báo của quá trình tái tạo.
    """
    user_id = session.get('user_id')
    card = flashcard_service.get_card_by_id(flashcard_id)
    
    if not _check_edit_permission(user_id, card):
        return jsonify({'status': 'error', 'message': 'Bạn không có quyền thực hiện hành động này.'}), 403

    if side not in ['front', 'back']:
        return jsonify({'status': 'error', 'message': 'Mặt thẻ không hợp lệ.'}), 400

    # Chạy hàm async trong một event loop mới
    # BẮT ĐẦU SỬA LỖI: Nhận kết quả trả về từ audio_service đúng cách
    success, message = asyncio.run(audio_service.regenerate_audio_for_card(flashcard_id, side))
    
    if success:
        return jsonify({'status': 'success', 'message': f'Đã gửi yêu cầu tái tạo audio cho mặt {side}.'})
    else:
        # Trả về thông báo lỗi chi tiết từ service
        return jsonify({'status': 'error', 'message': f'Tái tạo audio thất bại: {message}. Vui lòng liên hệ quản trị viên.'}), 500

@api_bp.route('/cards_by_category/<int:set_id>/<string:category>')
@login_required
def get_cards_by_category(set_id, category):
    """
    Mô tả: Lấy danh sách các flashcard theo danh mục (ví dụ: due, mastered).
    Args:
        set_id (int): ID của bộ thẻ.
        category (str): Danh mục thẻ cần lấy.
    Returns:
        jsonify: Danh sách thẻ và thông tin phân trang.
    """
    user_id = session.get('user_id')
    page = request.args.get('page', 1, type=int)
    
    valid_categories = ['due', 'mastered', 'lapsed', 'due_soon', 'learning', 'unseen']
    if category not in valid_categories:
        return jsonify({'status': 'error', 'message': 'Danh mục không hợp lệ.'}), 400

    try:
        pagination = flashcard_service.get_cards_by_category(user_id, set_id, category, page)
        cards_data = [{'front': card.front, 'back': card.back} for card in pagination.items]
        pagination_data = {'page': pagination.page, 'pages': pagination.pages, 'has_prev': pagination.has_prev, 'has_next': pagination.has_next, 'total': pagination.total}
        
        return jsonify({'status': 'success', 'cards': cards_data, 'pagination': pagination_data})
    except Exception as e:
        logger.error(f"Lỗi khi lấy thẻ theo danh mục '{category}' cho bộ {set_id}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'Lỗi server nội bộ.'}), 500

@api_bp.route('/quiz_note/<int:question_id>', methods=['GET', 'POST'])
@login_required
def handle_quiz_note(question_id):
    """
    Mô tả: Xử lý việc lấy và cập nhật ghi chú cho câu hỏi quiz.
    Args:
        question_id (int): ID của câu hỏi quiz.
    Returns:
        jsonify: Dữ liệu ghi chú hoặc trạng thái cập nhật.
    """
    user_id = session.get('user_id')
    if request.method == 'GET':
        note = quiz_note_service.get_note_by_question_id(user_id, question_id)
        return jsonify({'note': note.note if note else ""})
    if request.method == 'POST':
        data = request.get_json()
        if not data or 'note' not in data:
            return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400
        note_obj, status, message = quiz_note_service.create_or_update_note(user_id, question_id, data['note'])
        if status == "error":
            return jsonify({'status': 'error', 'message': message}), 500
        return jsonify({'status': status, 'message': message, 'note': note_obj.note})

@api_bp.route('/quiz_passage/<int:passage_id>', methods=['GET'])
@login_required
def get_quiz_passage(passage_id):
    """
    Mô tả: Lấy nội dung của một đoạn văn quiz.
    Args:
        passage_id (int): ID của đoạn văn.
    Returns:
        jsonify: Nội dung đoạn văn hoặc thông báo lỗi.
    """
    passage = QuizPassage.query.get(passage_id)
    if not passage:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy đoạn văn.'}), 404
    return jsonify({'status': 'success', 'passage_content': passage.passage_content})

@api_bp.route('/quiz_question/details/<int:question_id>')
@login_required
def get_quiz_question_details(question_id):
    """
    Mô tả: Lấy chi tiết của một câu hỏi quiz.
    Args:
        question_id (int): ID của câu hỏi quiz.
    Returns:
        jsonify: Dữ liệu chi tiết câu hỏi hoặc thông báo lỗi.
    """
    question = quiz_service.get_question_by_id(question_id)
    if not question:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy câu hỏi.'}), 404
    
    question_data = {
        'pre_question_text': question.pre_question_text, 'question': question.question,
        'option_a': question.option_a, 'option_b': question.option_b,
        'option_c': question.option_c, 'option_d': question.option_d,
        'correct_answer': question.correct_answer, 'guidance': question.guidance,
        'question_image_file': question.question_image_file, 'question_audio_file': question.question_audio_file,
        'passage_id': question.passage_id, 'passage_order': question.passage_order
    }
    return jsonify({'status': 'success', 'data': question_data})

@api_bp.route('/quiz_question/edit/<int:question_id>', methods=['POST'])
@login_required
def edit_quiz_question(question_id):
    """
    Mô tả: Chỉnh sửa nội dung của một câu hỏi quiz.
    Args:
        question_id (int): ID của câu hỏi quiz.
    Returns:
        jsonify: Trạng thái cập nhật và thông báo.
    """
    user_id = session.get('user_id')
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400
    
    processed_data = {}
    for key, value in data.items():
        if isinstance(value, str) and value.strip() == '':
            processed_data[key] = None
        else:
            processed_data[key] = value

    passage_content_from_request = processed_data.pop('passage_content', None) 
    passage_order_from_request = processed_data.get('passage_order', None)

    question = quiz_service.get_question_by_id(question_id)
    if not question:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy câu hỏi.'}), 404

    if passage_content_from_request is not None:
        passage_content_from_request = passage_content_from_request.strip()
        if passage_content_from_request:
            passage_hash = hashlib.sha256(passage_content_from_request.encode('utf-8')).hexdigest()
            existing_passage = QuizPassage.query.filter_by(passage_hash=passage_hash).first()
            if existing_passage:
                question.passage_id = existing_passage.passage_id
            else:
                new_passage = QuizPassage(passage_content=passage_content_from_request, passage_hash=passage_hash)
                db.session.add(new_passage)
                db.session.flush()
                question.passage_id = new_passage.passage_id
            logger.info(f"Cập nhật/tạo đoạn văn cho câu hỏi {question_id}. Passage ID: {question.passage_id}")
        else:
            question.passage_id = None
            logger.info(f"Hủy liên kết đoạn văn cho câu hỏi {question_id}.")
    
    if passage_order_from_request is not None:
        try:
            question.passage_order = int(passage_order_from_request) if passage_order_from_request != '' else None
        except ValueError:
            question.passage_order = None
    else:
        question.passage_order = None

    updated_question, status = quiz_service.update_question(question_id, processed_data, user_id)
    
    if status != "success":
        message_map = {"permission_denied": "Bạn không có quyền sửa câu hỏi này.", "question_not_found": "Không tìm thấy câu hỏi."}
        return jsonify({'status': 'error', 'message': message_map.get(status, "Lỗi server.")}), 403 if status == "permission_denied" else 404 if status == "card_not_found" else 500
    
    return jsonify({'status': 'success', 'message': 'Cập nhật thành công!'})

@api_bp.route('/quiz_audio/<path:filepath>')
@login_required
def get_quiz_audio(filepath):
    """
    Mô tả: Phục vụ file audio cho quiz dựa trên đường dẫn tương đối của file (bao gồm thư mục con).
    Args:
        filepath (str): Đường dẫn tương đối của file audio từ thư mục QUIZ_AUDIO_CACHE_DIR
                        (ví dụ: "study4_toeic/hash.mp3").
    Returns:
        file: File audio nếu tìm thấy.
        Response: 404 hoặc 500 nếu không tìm thấy hoặc lỗi.
    """
    if not filepath or not filepath.strip():
        logger.warning(f"Yêu cầu audio quiz với đường dẫn rỗng.")
        return Response(status=404, mimetype='audio/mpeg')

    full_path = os.path.join(QUIZ_AUDIO_CACHE_DIR, filepath) 
    
    try:
        if not os.path.exists(full_path):
            logger.warning(f"Không tìm thấy file audio cục bộ: {full_path}")
            return Response(status=404, mimetype='audio/mpeg')
        logger.info(f"Phục vụ file audio cục bộ: {full_path}")
        
        return send_file(full_path, mimetype="audio/mpeg")
    except Exception as e:
        logger.error(f"Lỗi khi phục vụ file audio cục bộ {filepath}: {e}", exc_info=True)
        return Response(status=500, mimetype='audio/mpeg')

@api_bp.route('/quiz_questions_by_category/<int:set_id>/<string:category>')
@login_required
def get_quiz_questions_by_category(set_id, category):
    """
    Mô tả: Lấy danh sách các câu hỏi quiz theo danh mục.
    Args:
        set_id (int): ID của bộ câu hỏi.
        category (str): Danh mục câu hỏi cần lấy.
    Returns:
        jsonify: Danh sách câu hỏi và thông tin phân trang.
    """
    user_id = session.get('user_id')
    page = request.args.get('page', 1, type=int)
    valid_categories = ['correct', 'incorrect', 'unanswered', 'mastered']
    if category not in valid_categories:
        return jsonify({'status': 'error', 'message': 'Danh mục không hợp lệ.'}), 400
    try:
        all_questions_in_set = QuizQuestion.query.filter_by(set_id=set_id).order_by(QuizQuestion.question_id).all()
        user_progresses = {p.question_id: p for p in UserQuizProgress.query.filter_by(user_id=user_id).join(QuizQuestion).filter(QuizQuestion.set_id == set_id).all()}
        filtered_questions = []
        for question in all_questions_in_set:
            progress = user_progresses.get(question.question_id)
            if category == 'unanswered':
                if not progress:
                    filtered_questions.append(question)
            elif progress:
                if category == 'correct' and progress.times_correct > 0:
                    filtered_questions.append(question)
                elif category == 'incorrect' and progress.times_incorrect > 0:
                    filtered_questions.append(question)
                elif category == 'mastered' and progress.is_mastered:
                    filtered_questions.append(question)
        start_index = (page - 1) * 50
        end_index = start_index + 50
        paginated_items = filtered_questions[start_index:end_index]
        total_items = len(filtered_questions)
        total_pages = (total_items + 49) // 50
        questions_data = []
        for q in paginated_items:
            questions_data.append({
                'question_id': q.question_id, 'question': q.question,
                'option_a': q.option_a, 'option_b': q.option_b,
                'option_c': q.option_c, 'option_d': q.option_d,
                'correct_answer': q.correct_answer
            })
        pagination_data = {
            'page': page, 'pages': total_pages, 'has_prev': page > 1,
            'has_next': page < total_pages, 'total': total_items
        }
        return jsonify({'status': 'success', 'questions': questions_data, 'pagination': pagination_data})
    except Exception as e:
        logger.error(f"Lỗi khi lấy câu hỏi quiz theo danh mục '{category}' cho bộ {set_id}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'Lỗi server nội bộ.'}), 500

@api_bp.route('/quiz_set_stats/<int:set_id>', methods=['GET'])
@login_required
def get_quiz_set_stats(set_id):
    """
    Mô tả: Lấy thống kê của một bộ câu hỏi quiz cho người dùng.
    Args:
        set_id (int): ID của bộ câu hỏi.
    Returns:
        jsonify: Dữ liệu thống kê hoặc thông báo lỗi.
    """
    user_id = session.get('user_id')
    stats = quiz_service.get_quiz_set_stats_for_user(user_id, set_id)
    if not stats:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy thống kê bộ quiz.'}), 404
    return jsonify({'status': 'success', 'data': stats})

@api_bp.route('/quiz_question_progress/<int:question_id>', methods=['GET'])
@login_required
def get_quiz_question_progress(question_id):
    """
    Mô tả: Lấy tiến độ học tập của người dùng đối với một câu hỏi quiz cụ thể.
    Args:
        question_id (int): ID của câu hỏi quiz.
    Returns:
        jsonify: Dữ liệu tiến độ hoặc thông báo mặc định nếu không có tiến độ.
    """
    user_id = session.get('user_id')
    progress = UserQuizProgress.query.filter_by(
        user_id=user_id, question_id=question_id
    ).first()
    if not progress:
        return jsonify({
            'status': 'success',
            'data': {'times_correct': 0, 'times_incorrect': 0}
        })
    return jsonify({
        'status': 'success',
        'data': {
            'times_correct': progress.times_correct,
            'times_incorrect': progress.times_incorrect
        }
    })

# --- BẮT ĐẦU THÊM MỚI: Endpoint gửi feedback ---
@api_bp.route('/feedback/submit', methods=['POST'])
@login_required
def submit_feedback():
    """
    Mô tả: API endpoint để người dùng gửi feedback về một thẻ hoặc câu hỏi.
    """
    user_id = session.get('user_id')
    data = request.get_json()
    
    content = data.get('content')
    flashcard_id = data.get('flashcard_id')
    question_id = data.get('question_id')

    feedback_obj, status, message = feedback_service.create_feedback(
        user_id=user_id,
        content=content,
        flashcard_id=flashcard_id,
        question_id=question_id
    )

    if status == 'error':
        return jsonify({'status': 'error', 'message': message}), 400 if "Nội dung" in message else 500
    
    return jsonify({'status': 'success', 'message': message})
# --- KẾT THÚC THÊM MỚI ---
