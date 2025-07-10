# web_app/routes/api.py
from flask import Blueprint, send_file, session, jsonify, request
import logging
import os
import asyncio
from ..services import audio_service, note_service
from ..models import Flashcard
from ..config import IMAGES_DIR
from .decorators import login_required

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

@api_bp.route('/card_audio/<int:flashcard_id>/<string:side>')
@login_required
def get_card_audio(flashcard_id, side):
    """
    Mô tả: API endpoint để lấy và phục vụ file audio cho một mặt của thẻ.
    """
    if side not in ['front', 'back']:
        return {"error": "Invalid side specified"}, 400

    flashcard = Flashcard.query.get_or_404(flashcard_id)
    audio_content = flashcard.front_audio_content if side == 'front' else flashcard.back_audio_content

    if not audio_content:
        return {"error": "No audio content for this side"}, 404

    try:
        # Chạy hàm bất đồng bộ từ audio_service
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
    """
    Mô tả: Phục vụ các tệp hình ảnh từ thư mục IMAGES_DIR.
    """
    try:
        # Đường dẫn tuyệt đối đến file ảnh
        full_path = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(full_path):
            logger.warning(f"File ảnh không tìm thấy: {full_path}")
            return "Image not found", 404
        return send_file(full_path)
    except Exception as e:
        logger.error(f"Lỗi khi phục vụ ảnh '{filename}': {e}", exc_info=True)
        return "Internal server error", 500

# --- BẮT ĐẦU THÊM: API cho chức năng Ghi chú (Note) ---

@api_bp.route('/note/<int:flashcard_id>', methods=['GET'])
@login_required
def get_note(flashcard_id):
    """
    Mô tả: Lấy ghi chú của người dùng cho một flashcard cụ thể.
    """
    user_id = session.get('user_id')
    note = note_service.get_note_by_flashcard_id(user_id, flashcard_id)
    note_content = note.note if note else ""
    return jsonify({'note': note_content})

@api_bp.route('/note/<int:flashcard_id>', methods=['POST'])
@login_required
def save_note(flashcard_id):
    """
    Mô tả: Lưu (tạo mới hoặc cập nhật) ghi chú của người dùng cho một flashcard.
    """
    user_id = session.get('user_id')
    data = request.get_json()
    if not data or 'note' not in data:
        return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400

    note_content = data['note']
    
    note_obj, status, message = note_service.create_or_update_note(user_id, flashcard_id, note_content)

    if status == "error":
        return jsonify({'status': 'error', 'message': message}), 500
    
    return jsonify({'status': status, 'message': message, 'note': note_obj.note})

# --- KẾT THÚC THÊM ---
