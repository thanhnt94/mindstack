# web_app/routes/api.py
from flask import Blueprint, send_file, session, jsonify, request, redirect
import logging
import os
import asyncio
import hashlib # Import hashlib để tạo hash cho đoạn văn
from ..services import audio_service, note_service, flashcard_service, quiz_service, quiz_note_service
from ..models import Flashcard, QuizQuestion, UserQuizProgress, QuizPassage 
from ..config import FLASHCARD_IMAGES_DIR, QUIZ_IMAGES_DIR, QUIZ_AUDIO_CACHE_DIR # Cập nhật import
from .decorators import login_required
from ..db_instance import db 

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

# API cho Flashcard audio
@api_bp.route('/card_audio/<int:flashcard_id>/<string:side>')
@login_required
def get_card_audio(flashcard_id, side):
    """
    Mô tả: Phục vụ file audio cho flashcard dựa trên ID và mặt (front/back).
    Args:
        flashcard_id (int): ID của flashcard.
        side (str): 'front' hoặc 'back' để chỉ định mặt của thẻ.
    Returns:
        Response: File audio hoặc JSON báo lỗi.
    """
    if side not in ['front', 'back']:
        return {"error": "Invalid side specified"}, 400
    flashcard = Flashcard.query.get_or_404(flashcard_id)
    audio_content = flashcard.front_audio_content if side == 'front' else flashcard.back_audio_content
    if not audio_content:
        return {"error": "No audio content for this side"}, 404
    try:
        # Vẫn sử dụng audio_service cho flashcard (TTS)
        # audio_service sẽ sử dụng AUDIO_CACHE_DIR (đã được đổi tên thành FLASHCARD_AUDIO_CACHE_DIR trong config)
        audio_file_path = asyncio.run(audio_service.get_cached_or_generate_audio(audio_content))
        if audio_file_path and os.path.exists(audio_file_path):
            return send_file(audio_file_path, mimetype="audio/mpeg")
        else:
            return {"error": "Failed to generate or retrieve audio file"}, 500
    except Exception as e:
        logger.error(f"Lỗi khi phục vụ audio flashcard {flashcard_id} ({side}): {e}", exc_info=True)
        return {"error": "Internal server error"}, 500

# BẮT ĐẦU THAY ĐỔI: Tách API phục vụ hình ảnh cho Flashcard và Quiz

@api_bp.route('/flashcard_images/<path:filename>')
def serve_flashcard_image(filename):
    """
    Mô tả: Phục vụ file hình ảnh cho Flashcard từ thư mục FLASHCARD_IMAGES_DIR.
    Args:
        filename (str): Tên file hình ảnh bao gồm cả đường dẫn tương đối.
    Returns:
        Response: File hình ảnh hoặc chuỗi báo lỗi.
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
    Mô tả: Phục vụ file hình ảnh cho Quiz từ thư mục QUIZ_IMAGES_DIR.
    Args:
        filename (str): Tên file hình ảnh bao gồm cả đường dẫn tương đối.
    Returns:
        Response: File hình ảnh hoặc chuỗi báo lỗi.
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

# KẾT THÚC THAY ĐỔI

# API cho Flashcard ghi chú
@api_bp.route('/note/<int:flashcard_id>', methods=['GET', 'POST'])
@login_required
def handle_note(flashcard_id):
    """
    Mô tả: Xử lý các yêu cầu GET/POST cho ghi chú flashcard.
    Args:
        flashcard_id (int): ID của flashcard.
    Returns:
        JSON: Nội dung ghi chú hoặc trạng thái/thông báo lỗi.
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

# API lấy chi tiết Flashcard
@api_bp.route('/flashcard/details/<int:flashcard_id>', methods=['GET'])
@login_required
def get_flashcard_details(flashcard_id):
    """
    Mô tả: Lấy chi tiết của một flashcard cụ thể.
    Args:
        flashcard_id (int): ID của flashcard.
    Returns:
        JSON: Chi tiết flashcard hoặc JSON báo lỗi.
    """
    card = flashcard_service.get_card_by_id(flashcard_id)
    if not card:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy thẻ.'}), 404
    card_data = {'front': card.front, 'back': card.back, 'front_audio_content': card.front_audio_content, 'back_audio_content': card.back_audio_content, 'front_img': card.front_img, 'back_img': card.back_img}
    return jsonify({'status': 'success', 'data': card_data})

# API chỉnh sửa Flashcard
@api_bp.route('/flashcard/edit/<int:flashcard_id>', methods=['POST'])
@login_required
def edit_flashcard(flashcard_id):
    """
    Mô tả: Cập nhật thông tin của một flashcard.
    Args:
        flashcard_id (int): ID của flashcard.
    Returns:
        JSON: Trạng thái cập nhật và thông báo.
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

# API lấy thẻ theo danh mục (Flashcard)
@api_bp.route('/cards_by_category/<int:set_id>/<string:category>')
@login_required
def get_cards_by_category(set_id, category):
    """
    Mô tả: Lấy danh sách flashcard theo bộ và danh mục (due, mastered, v.v.).
    Args:
        set_id (int): ID của bộ thẻ.
        category (str): Danh mục thẻ.
    Returns:
        JSON: Danh sách thẻ và thông tin phân trang.
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

# API cho Quiz ghi chú
@api_bp.route('/quiz_note/<int:question_id>', methods=['GET', 'POST'])
@login_required
def handle_quiz_note(question_id):
    """
    Mô tả: Xử lý các yêu cầu GET/POST cho ghi chú câu hỏi trắc nghiệm.
    Args:
        question_id (int): ID của câu hỏi trắc nghiệm.
    Returns:
        JSON: Nội dung ghi chú hoặc trạng thái/thông báo lỗi.
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

# API lấy nội dung đoạn văn Quiz
@api_bp.route('/quiz_passage/<int:passage_id>', methods=['GET'])
@login_required
def get_quiz_passage(passage_id):
    """
    Mô tả: Lấy nội dung của một đoạn văn Quiz dựa trên passage_id.
    Args:
        passage_id (int): ID của đoạn văn.
    Returns:
        JSON: Nội dung đoạn văn hoặc JSON báo lỗi.
    """
    passage = QuizPassage.query.get(passage_id)
    if not passage:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy đoạn văn.'}), 404
    return jsonify({'status': 'success', 'passage_content': passage.passage_content})


# API lấy chi tiết câu hỏi Quiz
@api_bp.route('/quiz_question/details/<int:question_id>')
@login_required
def get_quiz_question_details(question_id):
    """
    Mô tả: Lấy chi tiết của một câu hỏi trắc nghiệm cụ thể.
    Args:
        question_id (int): ID của câu hỏi.
    Returns:
        JSON: Chi tiết câu hỏi hoặc JSON báo lỗi.
    """
    question = quiz_service.get_question_by_id(question_id)
    if not question:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy câu hỏi.'}), 404
    
    question_data = {
        'pre_question_text': question.pre_question_text,
        'question': question.question,
        'option_a': question.option_a,
        'option_b': question.option_b,
        'option_c': question.option_c,
        'option_d': question.option_d,
        'correct_answer': question.correct_answer,
        'guidance': question.guidance,
        'question_image_file': question.question_image_file,
        'question_audio_file': question.question_audio_file,
        # Thêm passage_id và passage_order
        'passage_id': question.passage_id,
        'passage_order': question.passage_order
    }
    return jsonify({'status': 'success', 'data': question_data})

# API chỉnh sửa câu hỏi Quiz
@api_bp.route('/quiz_question/edit/<int:question_id>', methods=['POST'])
@login_required
def edit_quiz_question(question_id):
    """
    Mô tả: Cập nhật thông tin của một câu hỏi trắc nghiệm.
    Args:
        question_id (int): ID của câu hỏi.
    Returns:
        JSON: Trạng thái cập nhật và thông báo.
    """
    user_id = session.get('user_id')
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400
    
    # BẮT ĐẦU SỬA: Tiền xử lý dữ liệu để chuyển chuỗi rỗng thành None
    processed_data = {}
    for key, value in data.items():
        # Chuyển đổi chuỗi rỗng thành None cho các trường có thể nullable
        if isinstance(value, str) and value.strip() == '':
            processed_data[key] = None
        else:
            processed_data[key] = value
    # KẾT THÚC SỬA

    # Xử lý cập nhật passage_content và passage_order
    # Lấy passage_content ra khỏi processed_data
    passage_content_from_request = processed_data.pop('passage_content', None) 
    passage_order_from_request = processed_data.get('passage_order', None)

    question = quiz_service.get_question_by_id(question_id)
    if not question:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy câu hỏi.'}), 404

    # Cập nhật hoặc tạo QuizPassage nếu passage_content được cung cấp
    if passage_content_from_request is not None:
        passage_content_from_request = passage_content_from_request.strip()
        if passage_content_from_request:
            passage_hash = hashlib.sha256(passage_content_from_request.encode('utf-8')).hexdigest()
            existing_passage = QuizPassage.query.filter_by(passage_hash=passage_hash).first()

            if existing_passage:
                # Nếu đoạn văn đã tồn tại, chỉ cần liên kết câu hỏi với nó
                question.passage_id = existing_passage.passage_id
            else:
                # Nếu đoạn văn chưa tồn tại, tạo mới
                new_passage = QuizPassage(passage_content=passage_content_from_request, passage_hash=passage_hash)
                db.session.add(new_passage)
                db.session.flush() # Flush để lấy passage_id mới
                question.passage_id = new_passage.passage_id
            logger.info(f"Cập nhật/tạo đoạn văn cho câu hỏi {question_id}. Passage ID: {question.passage_id}")
        else:
            # Nếu passage_content rỗng, hủy liên kết với đoạn văn
            question.passage_id = None
            logger.info(f"Hủy liên kết đoạn văn cho câu hỏi {question_id}.")
    
    # Cập nhật passage_order
    if passage_order_from_request is not None:
        try:
            question.passage_order = int(passage_order_from_request) if passage_order_from_request != '' else None
        except ValueError:
            question.passage_order = None # Đặt là None nếu không hợp lệ
    else:
        question.passage_order = None # Đặt là None nếu không được gửi

    # Cập nhật các trường còn lại của câu hỏi
    updated_question, status = quiz_service.update_question(question_id, processed_data, user_id) # SỬA: Dùng processed_data
    
    if status != "success":
        message_map = {"permission_denied": "Bạn không có quyền sửa câu hỏi này.", "question_not_found": "Không tìm thấy câu hỏi."}
        return jsonify({'status': 'error', 'message': message_map.get(status, "Lỗi server.")}), 403 if status == "permission_denied" else 404 if status == "question_not_found" else 500
    
    return jsonify({'status': 'success', 'message': 'Cập nhật thành công!'})

# API phục vụ audio cho câu hỏi Quiz
@api_bp.route('/quiz_audio/<int:question_id>')
@login_required
def get_quiz_audio(question_id):
    """
    Mô tả: Phục vụ file audio cho câu hỏi trắc nghiệm dựa trên ID.
           File audio có thể là một URL bên ngoài hoặc một file cục bộ.
    Args:
        question_id (int): ID của câu hỏi trắc nghiệm.
    Returns:
        Response: File audio hoặc chuyển hướng đến URL, hoặc JSON báo lỗi.
    """
    question = QuizQuestion.query.get_or_404(question_id)
    audio_file_ref = question.question_audio_file

    if not audio_file_ref:
        logger.warning(f"Không có tham chiếu audio cho câu hỏi quiz ID: {question_id}")
        return {"error": "No audio content for this question"}, 404

    # Kiểm tra nếu là URL đầy đủ (http/https)
    if audio_file_ref.startswith('http://') or audio_file_ref.startswith('https://'):
        logger.info(f"Chuyển hướng đến URL audio bên ngoài: {audio_file_ref}")
        return redirect(audio_file_ref)
    else:
        # Giả định đây là một đường dẫn file cục bộ tương đối trong QUIZ_AUDIO_CACHE_DIR
        try:
            full_path = os.path.join(QUIZ_AUDIO_CACHE_DIR, audio_file_ref) # SỬA: Sử dụng QUIZ_AUDIO_CACHE_DIR
            if not os.path.exists(full_path):
                logger.warning(f"Không tìm thấy file audio cục bộ: {full_path}")
                return "Audio file not found", 404
            logger.info(f"Phục vụ file audio cục bộ: {full_path}")
            return send_file(full_path, mimetype="audio/mpeg")
        except Exception as e:
            logger.error(f"Lỗi khi phục vụ file audio cục bộ {audio_file_ref} cho câu hỏi {question_id}: {e}", exc_info=True)
            return "Internal server error", 500

# API lấy câu hỏi Quiz theo danh mục (để dùng trong Dashboard)
@api_bp.route('/quiz_questions_by_category/<int:set_id>/<string:category>')
@login_required
def get_quiz_questions_by_category(set_id, category):
    """
    Mô tả: Lấy danh sách câu hỏi trắc nghiệm theo bộ và danh mục (correct, incorrect, v.v.).
           Đây là endpoint cần thiết cho chức năng chi tiết bộ Quiz trên Dashboard.
    Args:
        set_id (int): ID của bộ câu hỏi.
        category (str): Danh mục câu hỏi (ví dụ: 'correct', 'incorrect', 'unanswered', 'mastered').
    Returns:
        JSON: Danh sách câu hỏi và thông tin phân trang.
    """
    user_id = session.get('user_id')
    page = request.args.get('page', 1, type=int)
    
    # Định nghĩa các danh mục hợp lệ cho Quiz
    valid_categories = ['correct', 'incorrect', 'unanswered', 'mastered']
    if category not in valid_categories:
        return jsonify({'status': 'error', 'message': 'Danh mục không hợp lệ.'}), 400

    try:
        # Lấy tất cả câu hỏi trong bộ
        all_questions_in_set = QuizQuestion.query.filter_by(set_id=set_id).order_by(QuizQuestion.question_id).all()
        all_question_ids = {q.question_id for q in all_questions_in_set}

        # Lấy tiến trình của người dùng cho bộ này
        user_progresses = {p.question_id: p for p in UserQuizProgress.query.filter_by(user_id=user_id).join(QuizQuestion).filter(QuizQuestion.set_id == set_id).all()}

        filtered_questions = []

        for question in all_questions_in_set:
            progress = user_progresses.get(question.question_id)
            
            if category == 'unanswered':
                if not progress: # Câu hỏi chưa có tiến trình là chưa trả lời
                    filtered_questions.append(question)
            elif progress: # Chỉ xem xét các câu hỏi đã có tiến trình cho các danh mục còn lại
                if category == 'correct' and progress.times_correct > 0:
                    filtered_questions.append(question)
                elif category == 'incorrect' and progress.times_incorrect > 0:
                    filtered_questions.append(question)
                elif category == 'mastered' and progress.is_mastered:
                    filtered_questions.append(question)
        
        # Áp dụng phân trang thủ công trên danh sách đã lọc
        start_index = (page - 1) * 50 # Giả sử 50 mục mỗi trang
        end_index = start_index + 50
        paginated_items = filtered_questions[start_index:end_index]
        
        total_items = len(filtered_questions)
        total_pages = (total_items + 49) // 50 # Làm tròn lên

        questions_data = []
        for q in paginated_items:
            questions_data.append({
                'question_id': q.question_id,
                'question': q.question,
                'option_a': q.option_a,
                'option_b': q.option_b,
                'option_c': q.option_c,
                'option_d': q.option_d,
                'correct_answer': q.correct_answer
            })
        
        pagination_data = {
            'page': page,
            'pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'total': total_items
        }
        
        return jsonify({'status': 'success', 'questions': questions_data, 'pagination': pagination_data})
    except Exception as e:
        logger.error(f"Lỗi khi lấy câu hỏi quiz theo danh mục '{category}' cho bộ {set_id}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'Lỗi server nội bộ.'}), 500

