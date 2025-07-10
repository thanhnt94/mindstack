# web_app/routes/api.py
from flask import Blueprint, send_file, session
import logging
import os
import asyncio
from ..services import audio_service
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
