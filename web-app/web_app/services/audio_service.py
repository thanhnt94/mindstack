# Path: flashcard-web/web_app/services/audio_service.py
"""
Module chứa business logic liên quan đến xử lý audio (TTS, Cache).
Đã được đóng gói hoàn toàn cho Web App, sử dụng Flask-SQLAlchemy.
Chỉ giữ lại chức năng tạo và lấy audio cho từng thẻ riêng lẻ từ cache.
"""

import os
import logging
import tempfile
import hashlib
import shutil
import asyncio
import random # Thêm import random

from gtts import gTTS
from pydub import AudioSegment

# Import các thành phần của Flask-SQLAlchemy và models
from .. import db # Import db instance
from ..models import Flashcard, User # Import models nếu cần truy vấn trực tiếp

# BẮT ĐẦU THAY ĐỔI: Cập nhật import để sử dụng FLASHCARD_AUDIO_CACHE_DIR
from ..config import FLASHCARD_AUDIO_CACHE_DIR, CACHE_GENERATION_DELAY
# KẾT THÚC THAY ĐỔI

logger = logging.getLogger(__name__)

class AudioService:
    """
    Lớp chứa các hàm xử lý audio cho ứng dụng web.
    Bao gồm tạo TTS, quản lý cache, và lấy file audio.
    """
    def __init__(self):
        # Đảm bảo thư mục cache tồn tại khi khởi tạo service
        try:
            # BẮT ĐẦU THAY ĐỔI: Sử dụng FLASHCARD_AUDIO_CACHE_DIR
            os.makedirs(FLASHCARD_AUDIO_CACHE_DIR, exist_ok=True)
            logger.info(f"AudioService khởi tạo thành công. Thư mục cache: {FLASHCARD_AUDIO_CACHE_DIR}")
            # KẾT THÚC THAY ĐỔI
        except OSError as e:
            logger.critical(f"Lỗi: Không thể tạo thư mục cache audio tại {FLASHCARD_AUDIO_CACHE_DIR}: {e}", exc_info=True)
            # Có thể thêm logic để dừng ứng dụng hoặc cảnh báo nghiêm trọng tại đây
        except Exception as e:
            logger.critical(f"Lỗi không mong muốn khi khởi tạo AudioService: {e}", exc_info=True)


    def _generate_tts_sync(self, text, lang='en'):
        """
        Tạo file audio từ text bằng Google Text-to-Speech (hàm đồng bộ).
        Được gọi từ asyncio.run_in_executor.
        """
        temp_path = None
        log_prefix = "[GENERATE_TTS_SYNC]"
        try:
            if not text or not text.strip():
                logger.warning(f"{log_prefix} Nhận được text rỗng hoặc chỉ chứa khoảng trắng. Không tạo TTS.")
                return None
            logger.debug(f"{log_prefix} Đang tạo TTS cho lang '{lang}', text '{text[:50]}...'")
            tts = gTTS(text=text, lang=lang, slow=False)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmpfile:
                temp_path = tmpfile.name
            tts.save(temp_path)
            logger.info(f"{log_prefix} Đã tạo file TTS tạm thời thành công: {temp_path}")
            return temp_path
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi tạo TTS cho lang '{lang}' và text '{text[:50]}...': {e}", exc_info=True)
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    logger.debug(f"{log_prefix} Đã xóa file TTS tạm lỗi: {temp_path}")
                except OSError as e_remove:
                    logger.error(f"{log_prefix} Lỗi xóa file TTS tạm lỗi {temp_path}: {e_remove}")
            return None

    async def _generate_concatenated_audio(self, audio_content_string, output_format="mp3", pause_ms=400):
        """
        Ghép nhiều file audio nhỏ thành một file duy nhất.
        Thất bại ngay nếu bất kỳ file con nào không tạo được.
        """
        log_prefix = "[GEN_CONCAT_AUDIO]"
        if not audio_content_string or not audio_content_string.strip():
            logger.warning(f"{log_prefix} Chuỗi nội dung audio rỗng. Không cần ghép.")
            return None

        lines = [line.strip() for line in audio_content_string.strip().splitlines() if line.strip()]
        if not lines:
            logger.warning(f"{log_prefix} Không có dòng hợp lệ nào để tạo TTS.")
            return None

        temp_files = []
        final_temp_path = None
        loop = asyncio.get_running_loop()

        try:
            tasks = []
            for line in lines:
                try:
                    lang_code, text_to_read = 'en', line
                    if ":" in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2 and parts[0].strip():
                            lang_code, text_to_read = parts[0].strip().lower(), parts[1].strip()

                    if not text_to_read:
                        logger.warning(f"{log_prefix} Bỏ qua dòng không có nội dung text: '{line}'")
                        continue

                    # --- BẮT ĐẦU THAY ĐỔI: Thêm độ trễ ngẫu nhiên ---
                    # Thay vì dùng hằng số CACHE_GENERATION_DELAY
                    delay = random.uniform(0.5, 2.0)
                    await asyncio.sleep(delay)
                    logger.debug(f"{log_prefix} Chờ {delay:.2f} giây trước khi gọi TTS.")
                    # --- KẾT THÚC THAY ĐỔI ---
                    
                    tasks.append(loop.run_in_executor(None, self._generate_tts_sync, text_to_read, lang_code))
                except Exception as e_prep:
                    logger.error(f"{log_prefix} Lỗi chuẩn bị TTS cho dòng '{line}': {e_prep}", exc_info=True)
                    # Nếu có lỗi ngay từ khâu chuẩn bị, hủy toàn bộ
                    return None

            if not tasks:
                logger.warning(f"{log_prefix} Không có tác vụ TTS nào được tạo.")
                return None

            logger.info(f"{log_prefix} Đang đợi {len(tasks)} tác vụ TTS.")
            generated_files_results = await asyncio.gather(*tasks)
            
            # SỬA LỖI: Kiểm tra nghiêm ngặt. Nếu bất kỳ file nào là None (lỗi), hủy bỏ.
            if any(result is None for result in generated_files_results):
                logger.error(f"{log_prefix} Một hoặc nhiều tác vụ TTS đã thất bại. Hủy bỏ việc ghép audio.")
                temp_files = [f for f in generated_files_results if f is not None] # Chỉ lấy các file đã tạo thành công để dọn dẹp
                return None # Trả về None để báo hiệu lỗi
            
            temp_files = list(generated_files_results)
            logger.info(f"{log_prefix} Tạo thành công {len(temp_files)} file audio riêng lẻ.")

            if len(temp_files) == 1:
                final_temp_path = temp_files[0]
                logger.info(f"{log_prefix} Chỉ có 1 file, không cần ghép. Trả về: {final_temp_path}")
                return final_temp_path
            
            # Logic ghép file (chỉ chạy khi tất cả file con đều thành công)
            def concatenate_sync_internal():
                try:
                    combined = AudioSegment.from_file(temp_files[0])
                    silence = AudioSegment.silent(duration=pause_ms) if pause_ms > 0 else None
                    for i in range(1, len(temp_files)):
                        if silence: combined += silence
                        combined += AudioSegment.from_file(temp_files[i])
                    
                    with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as tmp:
                        exported_path = tmp.name
                    combined.export(exported_path, format=output_format)
                    logger.info(f"{log_prefix} Ghép thành công -> {exported_path}")
                    return exported_path
                except Exception as e_concat:
                    logger.error(f"{log_prefix} Lỗi khi ghép đồng bộ: {e_concat}", exc_info=True)
                    return None

            final_temp_path = await loop.run_in_executor(None, concatenate_sync_internal)
            return final_temp_path

        except Exception as e:
            logger.critical(f"{log_prefix} Lỗi nghiêm trọng trong quá trình ghép audio: {e}", exc_info=True)
            return None
        finally:
            # Dọn dẹp tất cả các file tạm đã được tạo, bất kể thành công hay thất bại
            if temp_files:
                logger.debug(f"{log_prefix} Dọn dẹp {len(temp_files)} file TTS tạm...")
                for f in temp_files:
                    if f and os.path.exists(f) and f != final_temp_path:
                        try:
                            os.remove(f)
                        except Exception as e_remove:
                             logger.error(f"{log_prefix} Lỗi xóa file tạm {f}: {e_remove}")


    async def get_cached_or_generate_audio(self, audio_content_string, output_format="mp3"):
        """
        Lấy đường dẫn file audio từ cache hoặc tạo mới nếu chưa có.
        Sử dụng SHA1 hash của nội dung làm tên file cache.
        """
        log_prefix = "[GET_OR_GEN_AUDIO]"
        if not audio_content_string or not audio_content_string.strip():
            logger.debug(f"{log_prefix} Nội dung audio rỗng hoặc chỉ chứa khoảng trắng. Trả về None.")
            return None
        
        try:
            content_hash = hashlib.sha1(audio_content_string.encode('utf-8')).hexdigest()
            cache_filename = f"{content_hash}.{output_format}"
            # BẮT ĐẦU THAY ĐỔI: Sử dụng FLASHCARD_AUDIO_CACHE_DIR
            cached_file_path = os.path.join(FLASHCARD_AUDIO_CACHE_DIR, cache_filename)
            # KẾT THÚC THAY ĐỔI
            
            if os.path.exists(cached_file_path):
                logger.info(f"{log_prefix} Cache HIT: {cached_file_path}")
                return cached_file_path
            
            logger.info(f"{log_prefix} Cache MISS cho hash {content_hash}. Đang tạo audio...")
            temp_generated_path = await self._generate_concatenated_audio(audio_content_string, output_format)
            
            if temp_generated_path and os.path.exists(temp_generated_path):
                logger.info(f"{log_prefix} Tạo thành công file tạm: {temp_generated_path}. Chuẩn bị cache...")
                try:
                    shutil.move(temp_generated_path, cached_file_path)
                    logger.info(f"[SYNC_CACHE] Cache thành công: {cached_file_path}")
                    return cached_file_path
                except Exception as e_sync:
                    logger.error(f"[SYNC_CACHE] Lỗi copy/move vào cache từ {temp_generated_path} đến {cached_file_path}: {e_sync}", exc_info=True)
                    # Dọn dẹp file tạm nếu cache lỗi
                    if os.path.exists(temp_generated_path): os.remove(temp_generated_path)
                    return None
            else:
                logger.error(f"{log_prefix} Tạo audio cho hash {content_hash} thất bại hoặc file tạm không tồn tại.")
                return None
        except Exception as e:
            logger.critical(f"{log_prefix} Lỗi nghiêm trọng trong quá trình lấy/tạo/cache audio: {e}", exc_info=True)
            return None

    # --- BẮT ĐẦU THAY ĐỔI: Cập nhật hàm để nhận và cập nhật status_dict ---
    async def generate_cache_for_all_cards(self, status_dict):
        """
        Mô tả: Quét toàn bộ database và tạo file audio cache cho tất cả các thẻ
               có nội dung audio. Cập nhật tiến trình vào status_dict.
        Args:
            status_dict (dict): Dictionary để chia sẻ trạng thái tiến trình.
        Returns:
            tuple: (số file đã tạo thành công, tổng số file cần tạo)
        """
        log_prefix = "[AUDIO_SERVICE|GenerateAllCache]"
        logger.info(f"{log_prefix} Bắt đầu quá trình tạo cache cho toàn bộ audio.")
        
        all_audio_contents = set()
        cards_with_audio = Flashcard.query.filter(
            (Flashcard.front_audio_content != None) & (Flashcard.front_audio_content != '') |
            (Flashcard.back_audio_content != None) & (Flashcard.back_audio_content != '')
        ).all()

        for card in cards_with_audio:
            if card.front_audio_content:
                all_audio_contents.add(card.front_audio_content.strip())
            if card.back_audio_content:
                all_audio_contents.add(card.back_audio_content.strip())
        
        # Lọc ra những nội dung chưa có trong cache
        contents_to_generate = []
        for content in all_audio_contents:
            content_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()
            cached_file_path = os.path.join(FLASHCARD_AUDIO_CACHE_DIR, f"{content_hash}.mp3")
            if not os.path.exists(cached_file_path):
                contents_to_generate.append(content)

        # Cập nhật tổng số file cần tạo
        total_to_process = len(contents_to_generate)
        status_dict['total'] = total_to_process
        status_dict['progress'] = 0
        
        logger.info(f"{log_prefix} Tìm thấy {total_to_process} nội dung audio mới cần tạo cache.")

        if total_to_process == 0:
            return 0, 0

        created_count = 0
        for content in contents_to_generate:
            try:
                # Hàm này sẽ tạo file vì chúng ta đã lọc những file tồn tại
                result_path = await self.get_cached_or_generate_audio(content)
                if result_path:
                    created_count += 1
            except Exception as e:
                logger.error(f"{log_prefix} Lỗi khi xử lý nội dung: '{content[:50]}...': {e}", exc_info=True)
            finally:
                # Cập nhật tiến trình sau mỗi lần thử, dù thành công hay thất bại
                status_dict['progress'] += 1

        logger.info(f"{log_prefix} Hoàn tất. Đã tạo thành công {created_count}/{total_to_process} file audio mới.")
        return created_count, total_to_process
    # --- KẾT THÚC THAY ĐỔI ---
