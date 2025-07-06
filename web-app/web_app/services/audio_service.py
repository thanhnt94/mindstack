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

from gtts import gTTS
from pydub import AudioSegment

# Import các thành phần của Flask-SQLAlchemy và models
from .. import db # Import db instance
from ..models import Flashcard, User # Import models nếu cần truy vấn trực tiếp

# Import cấu hình từ web_app.config
from ..config import AUDIO_CACHE_DIR, CACHE_GENERATION_DELAY

logger = logging.getLogger(__name__)

class AudioService:
    """
    Lớp chứa các hàm xử lý audio cho ứng dụng web.
    Bao gồm tạo TTS, quản lý cache, và lấy file audio.
    """
    def __init__(self):
        # Đảm bảo thư mục cache tồn tại khi khởi tạo service
        try:
            os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
            logger.info(f"AudioService khởi tạo thành công. Thư mục cache: {AUDIO_CACHE_DIR}")
        except OSError as e:
            logger.critical(f"Lỗi: Không thể tạo thư mục cache audio tại {AUDIO_CACHE_DIR}: {e}", exc_info=True)
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
        Mỗi dòng trong audio_content_string có dạng "lang:text".
        Thêm delay trước mỗi lần gọi TTS.
        """
        log_prefix = "[GEN_CONCAT_AUDIO]"
        if not audio_content_string or not audio_content_string.strip():
            logger.warning(f"{log_prefix} Chuỗi nội dung audio rỗng. Không cần ghép.")
            return None
        lines = audio_content_string.strip().splitlines()
        temp_files = []
        final_temp_path = None
        loop = asyncio.get_running_loop()
        tts_call_count = 0 
        try:
            tasks = []
            valid_line_data = []
            for line in lines:
                line = line.strip()
                if not line:
                    logger.debug(f"{log_prefix} Bỏ qua dòng rỗng.")
                    continue
                try:
                    lang_code = None
                    text_to_read = None
                    split_parts = line.split(":", 1)
                    if len(split_parts) == 2:
                        lang_code = split_parts[0].strip().lower()
                        text_to_read = split_parts[1].strip()
                    else:
                        # Nếu không có lang code, mặc định là tiếng Anh
                        lang_code = 'en' 
                        text_to_read = line
                    
                    if not text_to_read:
                        logger.warning(f"{log_prefix} Dòng '{line}' không có nội dung text để đọc. Bỏ qua.")
                        continue
                    if not lang_code:
                        logger.warning(f"{log_prefix} Dòng '{line}' không có mã ngôn ngữ hợp lệ. Bỏ qua.")
                        continue

                    if CACHE_GENERATION_DELAY > 0:
                        logger.debug(f"{log_prefix} Delaying {CACHE_GENERATION_DELAY}s trước khi gọi TTS cho: '{text_to_read[:30]}...'")
                        await asyncio.sleep(CACHE_GENERATION_DELAY)
                        tts_call_count += 1
                    # Gọi hàm đồng bộ _generate_tts_sync trong executor
                    tasks.append(loop.run_in_executor(None, self._generate_tts_sync, text_to_read, lang_code))
                    valid_line_data.append(line)
                except Exception as e:
                    logger.error(f"{log_prefix} Lỗi phân tích hoặc chuẩn bị TTS cho dòng '{line}': {e}", exc_info=True)
            
            if not tasks:
                logger.warning(f"{log_prefix} Không có dòng hợp lệ nào để tạo TTS. Trả về None.")
                return None
            
            logger.info(f"{log_prefix} Đang đợi {len(tasks)} tác vụ TTS (đã gọi API {tts_call_count} lần).")
            generated_files_results = await asyncio.gather(*tasks, return_exceptions=True)
            logger.debug(f"{log_prefix} Các tác vụ TTS hoàn thành.")
            
            temp_files = [] 
            for i, result in enumerate(generated_files_results):
                if isinstance(result, str) and os.path.exists(result):
                    temp_files.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"{log_prefix} Lỗi tác vụ TTS {i} (nội dung gốc: '{valid_line_data[i]}'): {result}")
                else:
                    logger.warning(f"{log_prefix} Tác vụ TTS {i} (nội dung gốc: '{valid_line_data[i]}') không trả về file hợp lệ.")
            
            logger.info(f"{log_prefix} Tạo thành công {len(temp_files)}/{len(valid_line_data)} file audio riêng lẻ.")
            
            if not temp_files:
                logger.warning(f"{log_prefix} Không tạo được file audio riêng lẻ nào để ghép. Trả về None.")
                return None
            elif len(temp_files) == 1:
                logger.info(f"{log_prefix} Chỉ có 1 file ({temp_files[0]}), không cần ghép. Trả về file đó.")
                final_temp_path = temp_files[0]
                return final_temp_path
            else:
                logger.info(f"{log_prefix} Ghép {len(temp_files)} file với khoảng lặng {pause_ms}ms...")
                def concatenate_sync_internal():
                    combined = None
                    exported_path = None
                    try:
                        combined = AudioSegment.from_file(temp_files[0])
                        silence = None
                        if pause_ms > 0:
                            silence = AudioSegment.silent(duration=pause_ms)
                        for i in range(1, len(temp_files)):
                            if silence:
                                combined += silence
                            next_segment = AudioSegment.from_file(temp_files[i])
                            combined += next_segment
                        with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as tmp:
                            exported_path = tmp.name
                        combined.export(exported_path, format=output_format)
                        logger.info(f"{log_prefix} Ghép thành công -> {exported_path}")
                        return exported_path
                    except Exception as e_concat:
                         logger.error(f"{log_prefix} Lỗi khi ghép đồng bộ: {e_concat}", exc_info=True)
                         if exported_path and os.path.exists(exported_path):
                             try:
                                 os.remove(exported_path)
                             except OSError:
                                 pass
                         return None
                
                final_temp_path = await loop.run_in_executor(None, concatenate_sync_internal)
                if not final_temp_path:
                    logger.error(f"{log_prefix} Ghép audio thất bại, final_temp_path là None.")
                return final_temp_path
        except Exception as e:
            logger.critical(f"{log_prefix} Lỗi nghiêm trọng trong quá trình ghép audio: {e}", exc_info=True)
            return None
        finally:
            if temp_files:
                logger.debug(f"{log_prefix} Dọn dẹp {len(temp_files)} file TTS tạm...")
                for f in temp_files:
                    if f and os.path.exists(f) and f != final_temp_path:
                        try:
                            await loop.run_in_executor(None, os.remove, f)
                            logger.debug(f"{log_prefix} Đã xóa file tạm: {f}")
                        except Exception as e_remove:
                             logger.error(f"{log_prefix} Lỗi xóa file tạm {f}: {e_remove}")

    async def get_cached_or_generate_audio(self, audio_content_string, output_format="mp3"):
        """
        Lấy đường dẫn file audio từ cache hoặc tạo mới nếu chưa có.
        Sử dụng SHA1 hash của nội dung làm tên file cache.
        Args:
            audio_content_string (str): Chuỗi nội dung audio (có thể nhiều dòng).
            output_format (str): Định dạng file audio (mặc định 'mp3').
        Returns:
            str: Đường dẫn đến file audio trong cache.
            None: Nếu có lỗi.
        """
        log_prefix = "[GET_OR_GEN_AUDIO]"
        if not audio_content_string or not audio_content_string.strip():
            logger.debug(f"{log_prefix} Nội dung audio rỗng hoặc chỉ chứa khoảng trắng. Trả về None.")
            return None
        
        cached_file_path = None
        temp_generated_path = None
        final_cache_path = None
        loop = asyncio.get_running_loop()
        
        try:
            content_hash = hashlib.sha1(audio_content_string.encode('utf-8')).hexdigest()
            cache_filename = f"{content_hash}.{output_format}"
            cached_file_path = os.path.join(AUDIO_CACHE_DIR, cache_filename)
            
            # Đảm bảo thư mục cache tồn tại (đã được gọi trong __init__ nhưng gọi lại để an toàn)
            os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

            cache_exists = await loop.run_in_executor(None, os.path.exists, cached_file_path)
            if cache_exists:
                logger.info(f"{log_prefix} Cache HIT: {cached_file_path}")
                return cached_file_path
            else:
                logger.info(f"{log_prefix} Cache MISS cho hash {content_hash}. Đang tạo audio...")
                temp_generated_path = await self._generate_concatenated_audio(audio_content_string, output_format)
                
                if temp_generated_path and os.path.exists(temp_generated_path):
                    logger.info(f"{log_prefix} Tạo thành công file tạm: {temp_generated_path}. Chuẩn bị cache...")
                    def cache_file_sync_internal():
                        try:
                            # Sử dụng shutil.move để di chuyển và ghi đè nếu cần, hiệu quả hơn copy rồi xóa
                            shutil.move(temp_generated_path, cached_file_path)
                            logger.info(f"[SYNC_CACHE] Cache thành công: {cached_file_path}")
                            return cached_file_path
                        except Exception as e_sync:
                            logger.error(f"[SYNC_CACHE] Lỗi copy/move vào cache từ {temp_generated_path} đến {cached_file_path}: {e_sync}", exc_info=True)
                            return None
                    
                    final_cache_path = await loop.run_in_executor(None, cache_file_sync_internal)
                    if not final_cache_path:
                        logger.error(f"{log_prefix} Cache file thất bại cho hash {content_hash}.")
                    return final_cache_path
                else:
                    logger.error(f"{log_prefix} Tạo audio cho hash {content_hash} thất bại hoặc file tạm không tồn tại.")
                    return None
        except Exception as e:
            logger.critical(f"{log_prefix} Lỗi nghiêm trọng trong quá trình lấy/tạo/cache audio: {e}", exc_info=True)
            return None
        finally:
            # Dọn dẹp file tạm nếu nó vẫn còn và không phải là file đã được cache cuối cùng
            if temp_generated_path and os.path.exists(temp_generated_path) and temp_generated_path != final_cache_path:
                logger.debug(f"{log_prefix} Dọn dẹp file tạm {temp_generated_path} (vì đã cache hoặc lỗi cache).")
                try:
                    await loop.run_in_executor(None, os.remove, temp_generated_path)
                    logger.debug(f"{log_prefix} Đã xóa file tạm: {temp_generated_path}")
                except Exception as e_remove:
                     logger.error(f"{log_prefix} Lỗi xóa file tạm {temp_generated_path}: {e_remove}")

