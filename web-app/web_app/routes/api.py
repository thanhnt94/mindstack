# web_app/routes/api.py
from flask import Blueprint, send_file, session, jsonify, request
import logging
import os
import asyncio
from ..services import audio_service, note_service, flashcard_service # THÊM flashcard_service
from ..models import Flashcard
from ..config import IMAGES_DIR
from .decorators import login_required

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

# --- Các API cũ (Audio, Image, Note) không thay đổi ---
@api_bp.route('/card_audio/<int:flashcard_id>/<string:side>')
@login_required
def get_card_audio(flashcard_id, side):
    if side not in ['front', 'back']:
        return {"error": "Invalid side specified"}, 400
    flashcard = Flashcard.query.get_or_404(flashcard_id)
    audio_content = flashcard.front_audio_content if side == 'front' else flashcard.back_audio_content
    if not audio_content:
        return {"error": "No audio content for this side"}, 404
    try:
        audio_file_path = asyncio.run(audio_service.get_cached_or_generate_audio(audio_content))
        if audio_file_path and os.path.exists(audio_file_path):
            return send_file(audio_file_path, mimetype="audio/mpeg")
        else:
            logger.error(f"API Audio: Không thể tạo hoặc tìm thấy file audio cho Flashcard ID {flashcard_id}, side '{side}'.")
            return {"error": "Failed to generate or retrieve audio file"}, 500
    except Exception as e:
        logger.error(f"API Audio: Lỗi không mong muốn khi phục vụ audio cho Flashcard ID {flashcard_id}, side '{side}': {e}", exc_info=True)
        return {"error": "Internal server error"}, 500

@api_bp.route('/images/<path:filename>')
def serve_image(filename):
    try:
        full_path = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(full_path):
            logger.warning(f"File ảnh không tìm thấy: {full_path}")
            return "Image not found", 404
        return send_file(full_path)
    except Exception as e:
        logger.error(f"Lỗi khi phục vụ ảnh '{filename}': {e}", exc_info=True)
        return "Internal server error", 500

@api_bp.route('/note/<int:flashcard_id>', methods=['GET'])
@login_required
def get_note(flashcard_id):
    user_id = session.get('user_id')
    note = note_service.get_note_by_flashcard_id(user_id, flashcard_id)
    note_content = note.note if note else ""
    return jsonify({'note': note_content})

@api_bp.route('/note/<int:flashcard_id>', methods=['POST'])
@login_required
def save_note(flashcard_id):
    user_id = session.get('user_id')
    data = request.get_json()
    if not data or 'note' not in data:
        return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400
    note_content = data['note']
    note_obj, status, message = note_service.create_or_update_note(user_id, flashcard_id, note_content)
    if status == "error":
        return jsonify({'status': 'error', 'message': message}), 500
    return jsonify({'status': status, 'message': message, 'note': note_obj.note})

# --- BẮT ĐẦU THÊM MỚI: API cho chức năng Sửa thẻ (Edit) ---

@api_bp.route('/flashcard/details/<int:flashcard_id>', methods=['GET'])
@login_required
def get_flashcard_details(flashcard_id):
    """
    Mô tả: Lấy toàn bộ thông tin chi tiết của một flashcard để điền vào form sửa.
    """
    card = flashcard_service.get_card_by_id(flashcard_id)
    if not card:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy thẻ.'}), 404
    
    card_data = {
        'front': card.front,
        'back': card.back,
        'front_audio_content': card.front_audio_content,
        'back_audio_content': card.back_audio_content,
        'front_img': card.front_img,
        'back_img': card.back_img
    }
    return jsonify({'status': 'success', 'data': card_data})

@api_bp.route('/flashcard/edit/<int:flashcard_id>', methods=['POST'])
@login_required
def edit_flashcard(flashcard_id):
    """
    Mô tả: Lưu các thay đổi của flashcard sau khi người dùng sửa.
    """
    user_id = session.get('user_id')
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400

    updated_card, status = flashcard_service.update_card(flashcard_id, data, user_id)

    if status != "success":
        # Chuyển đổi các mã lỗi thành thông báo thân thiện hơn
        if status == "permission_denied":
            message = "Bạn không có quyền sửa thẻ này."
            return jsonify({'status': 'error', 'message': message}), 403 # Forbidden
        elif status == "card_not_found":
            message = "Không tìm thấy thẻ để cập nhật."
            return jsonify({'status': 'error', 'message': message}), 404 # Not Found
        else:
            message = "Đã xảy ra lỗi không mong muốn."
            return jsonify({'status': 'error', 'message': message}), 500 # Internal Server Error

    # Trả về dữ liệu thẻ đã cập nhật để frontend có thể làm mới giao diện
    card_data = {
        'front': updated_card.front,
        'back': updated_card.back,
        'front_img': updated_card.front_img,
        'back_img': updated_card.back_img
    }
    return jsonify({'status': 'success', 'message': 'Cập nhật thẻ thành công!', 'data': card_data})

# --- KẾT THÚC THÊM MỚI ---
