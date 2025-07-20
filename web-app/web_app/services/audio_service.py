# Path: flashcard-web/web_app/services/audio_service.py
import os
import logging
import tempfile
import hashlib
import shutil
import asyncio
import random

from gtts import gTTS
from pydub import AudioSegment

from .. import db
from ..models import Flashcard, User
from ..config import FLASHCARD_AUDIO_CACHE_DIR

logger = logging.getLogger(__name__)

class AudioService:
    def __init__(self):
        """
        Mô tả: Khởi tạo dịch vụ AudioService, đảm bảo thư mục cache audio tồn tại.
        """
        try:
            os.makedirs(FLASHCARD_AUDIO_CACHE_DIR, exist_ok=True)
            logger.info(f"AudioService khởi tạo thành công. Thư mục cache: {FLASHCARD_AUDIO_CACHE_DIR}")
        except OSError as e:
            logger.critical(f"Lỗi: Không thể tạo thư mục cache audio tại {FLASHCARD_AUDIO_CACHE_DIR}: {e}", exc_info=True)
        except Exception as e:
            logger.critical(f"Lỗi không mong muốn khi khởi tạo AudioService: {e}", exc_info=True)

    def _generate_tts_sync(self, text, lang='en'):
        """
        Mô tả: Tạo file audio Text-to-Speech (TTS) từ một đoạn văn bản bằng gTTS.
               Đây là hàm đồng bộ, sẽ được gọi trong executor.
        Args:
            text (str): Đoạn văn bản cần chuyển đổi thành audio.
            lang (str): Ngôn ngữ của văn bản (mặc định là 'en').
        Returns:
            tuple: (đường dẫn file tạm thời, thành công (bool), thông báo lỗi/thành công).
                   Trả về (None, False, message) nếu có lỗi.
        """
        temp_path = None
        log_prefix = "[GENERATE_TTS_SYNC]"
        try:
            if not text or not text.strip():
                logger.warning(f"{log_prefix} Nhận được text rỗng hoặc chỉ chứa khoảng trắng. Không tạo TTS.")
                return None, False, "Nội dung văn bản rỗng."

            logger.debug(f"{log_prefix} Đang tạo TTS cho lang '{lang}', text '{text[:50]}...'")
            tts = gTTS(text=text, lang=lang, slow=False)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmpfile:
                temp_path = tmpfile.name
            tts.save(temp_path)
            logger.info(f"{log_prefix} Đã tạo file TTS tạm thời thành công: {temp_path}")
            return temp_path, True, "Tạo TTS thành công."
        except Exception as e:
            error_message = f"Lỗi khi tạo TTS cho lang '{lang}' và text '{text[:50]}...': {e}"
            logger.error(f"{log_prefix} {error_message}", exc_info=True)
            # Cố gắng xóa file tạm nếu nó được tạo ra nhưng bị lỗi
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    logger.debug(f"{log_prefix} Đã xóa file TTS tạm lỗi: {temp_path}")
                except OSError as e_remove:
                    logger.error(f"{log_prefix} Lỗi xóa file TTS tạm lỗi {temp_path}: {e_remove}")
            return None, False, f"Lỗi tạo audio từ Google Text-to-Speech. Có thể do giới hạn API hoặc lỗi kết nối: {e}"

    async def _generate_concatenated_audio(self, audio_content_string, output_format="mp3", pause_ms=400):
        """
        Mô tả: Ghép nhiều đoạn audio TTS thành một file duy nhất.
               Hỗ trợ định dạng 'lang: text' cho từng dòng.
        Args:
            audio_content_string (str): Chuỗi chứa nội dung audio, mỗi dòng có thể có định dạng 'lang: text'.
            output_format (str): Định dạng đầu ra của file audio (mặc định là 'mp3').
            pause_ms (int): Thời gian tạm dừng giữa các đoạn audio khi ghép (miligiây).
        Returns:
            tuple: (đường dẫn file tạm thời cuối cùng, thành công (bool), thông báo lỗi/thành công).
                   Trả về (None, False, message) nếu có lỗi.
        """
        log_prefix = "[GEN_CONCAT_AUDIO]"
        if not audio_content_string or not audio_content_string.strip():
            logger.warning(f"{log_prefix} Chuỗi nội dung audio rỗng. Không cần ghép.")
            return None, True, "Nội dung audio rỗng, không cần ghép."

        lines = [line.strip() for line in audio_content_string.strip().splitlines() if line.strip()]
        if not lines:
            logger.warning(f"{log_prefix} Không có dòng hợp lệ nào để tạo TTS.")
            return None, True, "Không có dòng hợp lệ để tạo TTS."

        temp_files = []
        final_temp_path = None
        loop = asyncio.get_running_loop()
        overall_success = True
        overall_message = "Ghép audio thành công."

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

                    # Thêm độ trễ ngẫu nhiên để tránh bị rate limit
                    delay = random.uniform(0.5, 2.0)
                    await asyncio.sleep(delay)
                    logger.debug(f"{log_prefix} Chờ {delay:.2f} giây trước khi gọi TTS.")
                    
                    tasks.append(loop.run_in_executor(None, self._generate_tts_sync, text_to_read, lang_code))
                except Exception as e_prep:
                    logger.error(f"{log_prefix} Lỗi chuẩn bị TTS cho dòng '{line}': {e_prep}", exc_info=True)
                    overall_success = False
                    overall_message = f"Lỗi chuẩn bị audio cho một phần: {e_prep}"
                    # Không return ngay, để các task khác có thể hoàn thành hoặc thất bại
                    # và dọn dẹp các file tạm đã tạo.

            if not tasks:
                logger.warning(f"{log_prefix} Không có tác vụ TTS nào được tạo.")
                return None, False, "Không có tác vụ TTS nào được tạo."

            logger.info(f"{log_prefix} Đang đợi {len(tasks)} tác vụ TTS.")
            generated_files_results = await asyncio.gather(*tasks)
            
            # Kiểm tra kết quả từ các tác vụ TTS riêng lẻ
            for path, success, msg in generated_files_results:
                if not success:
                    overall_success = False
                    overall_message = msg # Lấy thông báo lỗi từ TTS thất bại đầu tiên
                    logger.error(f"{log_prefix} Một tác vụ TTS đã thất bại: {msg}")
                if path:
                    temp_files.append(path) # Thêm vào danh sách để dọn dẹp sau

            if not overall_success:
                logger.error(f"{log_prefix} Một hoặc nhiều tác vụ TTS đã thất bại. Hủy bỏ việc ghép audio.")
                return None, False, overall_message
            
            logger.info(f"{log_prefix} Tạo thành công {len(temp_files)} file audio riêng lẻ.")

            if len(temp_files) == 0:
                logger.warning(f"{log_prefix} Không có file audio nào được tạo để ghép.")
                return None, False, "Không có file audio nào được tạo để ghép."
            elif len(temp_files) == 1:
                final_temp_path = temp_files[0]
                logger.info(f"{log_prefix} Chỉ có 1 file, không cần ghép. Trả về: {final_temp_path}")
                return final_temp_path, True, "Tạo audio thành công (chỉ 1 file)."
            
            def concatenate_sync_internal():
                """
                Mô tả: Hàm đồng bộ để ghép các file audio.
                """
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
                    return exported_path, True, "Ghép audio thành công."
                except Exception as e_concat:
                    logger.error(f"{log_prefix} Lỗi khi ghép đồng bộ: {e_concat}", exc_info=True)
                    return None, False, f"Lỗi khi ghép các đoạn audio: {e_concat}"

            final_temp_path, success, msg = await loop.run_in_executor(None, concatenate_sync_internal)
            return final_temp_path, success, msg

        except Exception as e:
            logger.critical(f"{log_prefix} Lỗi nghiêm trọng trong quá trình ghép audio: {e}", exc_info=True)
            return None, False, f"Lỗi nghiêm trọng trong quá trình tạo/ghép audio: {e}"
        finally:
            # Dọn dẹp các file tạm thời đã tạo, trừ file cuối cùng nếu nó thành công
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
        Mô tả: Lấy đường dẫn đến file audio đã cache hoặc tạo mới nếu chưa có.
        Args:
            audio_content_string (str): Chuỗi nội dung dùng để tạo audio và làm khóa cache.
            output_format (str): Định dạng file audio (mặc định là 'mp3').
        Returns:
            tuple: (đường dẫn file audio, thành công (bool), thông báo lỗi/thành công).
                   Trả về (None, False, message) nếu có lỗi.
        """
        log_prefix = "[GET_OR_GEN_AUDIO]"
        if not audio_content_string or not audio_content_string.strip():
            logger.debug(f"{log_prefix} Nội dung audio rỗng hoặc chỉ chứa khoảng trắng. Trả về None.")
            return None, True, "Nội dung audio rỗng."
        
        try:
            content_hash = hashlib.sha1(audio_content_string.encode('utf-8')).hexdigest()
            cache_filename = f"{content_hash}.{output_format}"
            cached_file_path = os.path.join(FLASHCARD_AUDIO_CACHE_DIR, cache_filename)
            
            if os.path.exists(cached_file_path):
                logger.info(f"{log_prefix} Cache HIT: {cached_file_path}")
                return cached_file_path, True, "Đã tìm thấy trong cache."
            
            logger.info(f"{log_prefix} Cache MISS cho hash {content_hash}. Đang tạo audio...")
            # Gọi hàm tạo audio và nhận lại trạng thái và thông báo
            temp_generated_path, success, message = await self._generate_concatenated_audio(audio_content_string, output_format)
            
            if success and temp_generated_path and os.path.exists(temp_generated_path):
                logger.info(f"{log_prefix} Tạo thành công file tạm: {temp_generated_path}. Chuẩn bị cache...")
                try:
                    shutil.move(temp_generated_path, cached_file_path)
                    logger.info(f"[SYNC_CACHE] Cache thành công: {cached_file_path}")
                    return cached_file_path, True, "Tạo và cache audio thành công."
                except Exception as e_sync:
                    error_message = f"Lỗi copy/move vào cache từ {temp_generated_path} đến {cached_file_path}: {e_sync}"
                    logger.error(f"[SYNC_CACHE] {error_message}", exc_info=True)
                    # Nếu lỗi khi di chuyển, xóa file tạm để tránh rác
                    if os.path.exists(temp_generated_path):
                        try:
                            os.remove(temp_generated_path)
                        except OSError as e_remove:
                            logger.error(f"[SYNC_CACHE] Lỗi xóa file tạm {temp_generated_path} sau khi copy lỗi: {e_remove}")
                    return None, False, f"Lỗi khi lưu file audio vào cache: {e_sync}"
            else:
                logger.error(f"{log_prefix} Tạo audio cho hash {content_hash} thất bại hoặc file tạm không tồn tại. Thông báo: {message}")
                return None, False, message # Trả về thông báo lỗi từ hàm con
        except Exception as e:
            error_message = f"Lỗi nghiêm trọng trong quá trình lấy/tạo/cache audio: {e}"
            logger.critical(f"{log_prefix} {error_message}", exc_info=True)
            return None, False, error_message

    async def generate_cache_for_all_cards(self, status_dict):
        """
        Mô tả: Quét toàn bộ database, xác định các file audio còn thiếu và tạo chúng.
               Có thể dừng giữa chừng.
        Args:
            status_dict (dict): Từ điển để cập nhật trạng thái tiến độ (total, progress, stop_requested).
        Returns:
            tuple: (created_count, total_to_process) - Số lượng file đã tạo và tổng số file cần xử lý.
        """
        log_prefix = "[AUDIO_SERVICE|GenerateAllCache]"
        logger.info(f"{log_prefix} Bắt đầu quá trình tạo cache cho toàn bộ audio.")
        
        # 1. Lấy tất cả nội dung audio duy nhất từ DB
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
        
        # 2. Lọc ra những nội dung chưa có file trong cache
        contents_to_generate = []
        for content in all_audio_contents:
            content_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()
            cached_file_path = os.path.join(FLASHCARD_AUDIO_CACHE_DIR, f"{content_hash}.mp3")
            if not os.path.exists(cached_file_path):
                contents_to_generate.append(content)

        # 3. Cập nhật tổng số file cần tạo
        total_to_process = len(contents_to_generate)
        status_dict['total'] = total_to_process
        status_dict['progress'] = 0
        status_dict['errors'] = [] # Thêm danh sách lỗi để báo cáo

        logger.info(f"{log_prefix} Tìm thấy {total_to_process} nội dung audio mới cần tạo cache.")

        if total_to_process == 0:
            return 0, 0

        created_count = 0
        # 4. Chỉ lặp qua danh sách các file cần tạo
        for content in contents_to_generate:
            if status_dict.get('stop_requested'):
                logger.info(f"{log_prefix} Nhận được yêu cầu dừng. Kết thúc sớm.")
                break
            try:
                # Gọi hàm get_cached_or_generate_audio và nhận kết quả chi tiết
                result_path, success, message = await self.get_cached_or_generate_audio(content)
                if success:
                    created_count += 1
                else:
                    # Ghi nhận lỗi để báo cáo lại cho người dùng
                    status_dict['errors'].append(f"Lỗi tạo audio cho '{content[:50]}...': {message}")
                    logger.error(f"{log_prefix} Lỗi khi xử lý nội dung: '{content[:50]}...': {message}")
            except Exception as e:
                # Lỗi không mong muốn trong vòng lặp
                error_message = f"Lỗi không mong muốn khi xử lý nội dung: '{content[:50]}...': {e}"
                status_dict['errors'].append(error_message)
                logger.error(f"{log_prefix} {error_message}", exc_info=True)
            finally:
                status_dict['progress'] += 1

        logger.info(f"{log_prefix} Hoàn tất. Đã tạo thành công {created_count}/{total_to_process} file audio mới.")
        return created_count, total_to_process

    def clean_orphan_audio_cache(self):
        """
        Mô tả: Dọn dẹp các file audio trong cache không còn được liên kết với bất kỳ flashcard nào.
        Returns:
            int: Số lượng file đã bị xóa.
        """
        log_prefix = "[AUDIO_SERVICE|CleanCache]"
        logger.info(f"{log_prefix} Bắt đầu quá trình dọn dẹp cache audio.")
        
        try:
            active_audio_contents = set()
            cards_with_audio = Flashcard.query.filter(
                (Flashcard.front_audio_content != None) & (Flashcard.front_audio_content != '') |
                (Flashcard.back_audio_content != None) & (Flashcard.back_audio_content != '')
            ).all()

            for card in cards_with_audio:
                if card.front_audio_content:
                    active_audio_contents.add(card.front_audio_content.strip())
                if card.back_audio_content:
                    active_audio_contents.add(card.back_audio_content.strip())

            valid_cache_files = set()
            for content in active_audio_contents:
                content_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()
                valid_cache_files.add(f"{content_hash}.mp3")
            
            logger.info(f"{log_prefix} Tìm thấy {len(valid_cache_files)} file cache hợp lệ trong database.")

            deleted_count = 0
            if not os.path.exists(FLASHCARD_AUDIO_CACHE_DIR):
                logger.warning(f"{log_prefix} Thư mục cache không tồn tại: {FLASHCARD_AUDIO_CACHE_DIR}")
                return 0

            for filename in os.listdir(FLASHCARD_AUDIO_CACHE_DIR):
                if filename.endswith('.mp3') and filename not in valid_cache_files:
                    try:
                        file_path = os.path.join(FLASHCARD_AUDIO_CACHE_DIR, filename)
                        os.remove(file_path)
                        deleted_count += 1
                        logger.info(f"{log_prefix} Đã xóa file cache mồ côi: {filename}")
                    except OSError as e:
                        logger.error(f"{log_prefix} Lỗi khi xóa file {filename}: {e}")
            
            logger.info(f"{log_prefix} Hoàn tất. Đã xóa {deleted_count} file cache không hợp lệ.")
            return deleted_count
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi nghiêm trọng trong quá trình dọn dẹp cache: {e}", exc_info=True)
            return -1

    async def regenerate_audio_for_card(self, flashcard_id, side):
        """
        Mô tả: Tái tạo file audio cho một mặt cụ thể của một flashcard.
        Args:
            flashcard_id (int): ID của flashcard.
            side (str): 'front' hoặc 'back'.
        Returns:
            tuple: (thành công (bool), thông báo lỗi/thành công).
                   Trả về (False, message) nếu có lỗi.
        """
        log_prefix = f"[AUDIO_SERVICE|Regenerate|Card:{flashcard_id}|Side:{side}]"
        logger.info(f"{log_prefix} Bắt đầu tái tạo audio.")

        card = Flashcard.query.get(flashcard_id)
        if not card:
            logger.error(f"{log_prefix} Không tìm thấy flashcard.")
            return False, "Không tìm thấy flashcard."

        audio_content = None
        if side == 'front':
            audio_content = card.front_audio_content
        elif side == 'back':
            audio_content = card.back_audio_content
        
        if not audio_content or not audio_content.strip():
            logger.warning(f"{log_prefix} Không có nội dung audio để tái tạo.")
            return False, "Không có nội dung audio để tái tạo."

        try:
            content_hash = hashlib.sha1(audio_content.encode('utf-8')).hexdigest()
            cache_filename = f"{content_hash}.mp3"
            cached_file_path = os.path.join(FLASHCARD_AUDIO_CACHE_DIR, cache_filename)
            if os.path.exists(cached_file_path):
                os.remove(cached_file_path)
                logger.info(f"{log_prefix} Đã xóa file cache cũ: {cache_filename}")

            # Gọi hàm get_cached_or_generate_audio và nhận kết quả chi tiết
            new_path, success, message = await self.get_cached_or_generate_audio(audio_content)
            if success:
                logger.info(f"{log_prefix} Tái tạo audio thành công.")
                return True, "Tái tạo audio thành công."
            else:
                logger.error(f"{log_prefix} Tái tạo audio thất bại. Thông báo: {message}")
                return False, message # Trả về thông báo lỗi chi tiết từ hàm con
        except Exception as e:
            error_message = f"Lỗi nghiêm trọng khi tái tạo audio: {e}"
            logger.error(f"{log_prefix} {error_message}", exc_info=True)
            return False, error_message
