"""
Module chứa business logic liên quan đến xử lý audio (TTS, Cache, Compilation).
Hàm chạy nền tạo cache đã được tách logic lấy dữ liệu DB ra hàm riêng.
Việc kiểm soát dừng job cache được chuyển ra ngoài (tầng gọi job).
Các hàm đã được cập nhật để sử dụng user_id (khóa chính) khi cần thiết.
Các câu lệnh đã được tách dòng để đảm bảo tường minh.
"""
import os
import logging
import tempfile
import hashlib
import shutil
import asyncio
import sqlite3
from gtts import gTTS
from pydub import AudioSegment
from config import (
    AUDIO_CACHE_DIR,
    CACHE_GENERATION_DELAY,
)
from database.connection import database_connect
from utils.exceptions import DatabaseError
logger = logging.getLogger(__name__)
def generate_tts(text, lang='en'):
    """
    Tạo file audio từ text bằng Google Text-to-Speech.
    Args:
        text (str): Nội dung cần chuyển thành giọng nói.
        lang (str): Mã ngôn ngữ (ví dụ: 'en', 'vi').
    Returns:
        str: Đường dẫn đến file audio tạm thời nếu thành công.
        None: Nếu có lỗi xảy ra.
    """
    temp_path = None
    log_prefix = "[GENERATE_TTS]"
    try:
        if not text or not text.strip():
             logger.warning(f"{log_prefix} Nhận được text rỗng.")
             return None
        logger.debug(f"{log_prefix} Đang tạo TTS cho lang '{lang}', text '{text[:50]}...'")
        tts = gTTS(text=text, lang=lang, slow=False)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmpfile:
             temp_path = tmpfile.name
        tts.save(temp_path)
        logger.info(f"{log_prefix} Đã tạo file TTS tạm thời: {temp_path}")
        return temp_path
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi khi tạo TTS cho lang '{lang}': {e}", exc_info=True)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.debug(f"{log_prefix} Đã xóa file TTS tạm lỗi: {temp_path}")
            except OSError as e_remove:
                logger.error(f"{log_prefix} Lỗi xóa file TTS tạm lỗi {temp_path}: {e_remove}")
        return None
async def generate_concatenated_audio(audio_content_string, output_format="mp3", pause_ms=400):
    """
    Ghép nhiều file audio nhỏ thành một file duy nhất.
    Mỗi dòng trong audio_content_string có dạng "lang:text".
    Thêm delay trước mỗi lần gọi TTS.
    Args:
        audio_content_string (str): Chuỗi chứa nội dung các audio, mỗi dòng một audio.
        output_format (str): Định dạng file đầu ra (mặc định 'mp3').
        pause_ms (int): Khoảng lặng (ms) giữa các đoạn audio.
    Returns:
        str: Đường dẫn đến file audio đã ghép tạm thời nếu thành công.
        None: Nếu có lỗi.
    """
    log_prefix = "[GEN_CONCAT_AUDIO]"
    if not audio_content_string or not audio_content_string.strip():
        logger.warning(f"{log_prefix} Chuỗi nội dung audio rỗng.")
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
                continue
            try:
                lang_code = None
                text_to_read = None
                split_parts = line.split(":", 1)
                if len(split_parts) == 2:
                    lang_code = split_parts[0].strip().lower()
                    text_to_read = split_parts[1].strip()
                else:
                    lang_code = 'en' 
                    text_to_read = line
                if not text_to_read or not lang_code:
                    continue
                if CACHE_GENERATION_DELAY > 0:
                    logger.debug(f"{log_prefix} Delaying {CACHE_GENERATION_DELAY}s trước khi gọi TTS cho: '{text_to_read[:30]}...'")
                    await asyncio.sleep(CACHE_GENERATION_DELAY)
                    tts_call_count += 1
                tasks.append(loop.run_in_executor(None, generate_tts, text_to_read, lang_code))
                valid_line_data.append(line)
            except ValueError:
                logger.warning(f"{log_prefix} Bỏ qua dòng sai định dạng: {line}")
            except Exception as e:
                logger.error(f"{log_prefix} Lỗi phân tích dòng '{line}': {e}")
        if not tasks:
            logger.warning(f"{log_prefix} Không có dòng hợp lệ để tạo TTS.")
            return None
        logger.info(f"{log_prefix} Đang đợi {len(tasks)} tác vụ TTS (đã gọi API {tts_call_count} lần).")
        generated_files_results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"{log_prefix} Các tác vụ TTS hoàn thành.")
        temp_files = [] 
        for i, result in enumerate(generated_files_results):
            if isinstance(result, str) and os.path.exists(result):
                temp_files.append(result)
            elif isinstance(result, Exception):
                logger.error(f"{log_prefix} Lỗi tác vụ TTS {i} ({valid_line_data[i]}): {result}")
        logger.info(f"{log_prefix} Tạo thành công {len(temp_files)}/{len(valid_line_data)} file audio riêng lẻ.")
        if not temp_files:
            logger.warning(f"{log_prefix} Không tạo được file audio riêng lẻ nào.")
            return None
        elif len(temp_files) == 1:
            logger.info(f"{log_prefix} Chỉ có 1 file, không cần ghép.")
            final_temp_path = temp_files[0]
            return final_temp_path
        else:
            logger.info(f"{log_prefix} Ghép {len(temp_files)} file với pause {pause_ms}ms...")
            def concatenate_sync():
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
            final_temp_path = await loop.run_in_executor(None, concatenate_sync)
            return final_temp_path
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi nghiêm trọng trong quá trình ghép audio: {e}", exc_info=True)
        return None
    finally:
        if temp_files:
            logger.debug(f"{log_prefix} Dọn dẹp {len(temp_files)} file TTS tạm...")
            for f in temp_files:
                if f and os.path.exists(f) and f != final_temp_path:
                    try:
                        await loop.run_in_executor(None, os.remove, f)
                    except OSError as e_remove:
                        logger.error(f"{log_prefix} Lỗi xóa file TTS tạm {f}: {e_remove}")
async def get_cached_or_generate_audio(audio_content_string, output_format="mp3"):
    """
    Lấy đường dẫn file audio từ cache hoặc tạo mới nếu chưa có.
    Sử dụng SHA1 hash của nội dung làm tên file cache.
    Hàm này giờ sẽ gọi generate_concatenated_audio nếu cache miss.
    Args:
        audio_content_string (str): Chuỗi nội dung audio (có thể nhiều dòng).
        output_format (str): Định dạng file audio (mặc định 'mp3').
    Returns:
        str: Đường dẫn đến file audio trong cache.
        None: Nếu có lỗi.
    """
    log_prefix = "[GET_OR_GEN_AUDIO]"
    if not audio_content_string or not audio_content_string.strip():
        logger.debug(f"{log_prefix} Nội dung audio rỗng.")
        return None
    cached_file_path = None
    temp_generated_path = None
    final_cache_path = None
    loop = asyncio.get_running_loop()
    try:
        content_hash = hashlib.sha1(audio_content_string.encode('utf-8')).hexdigest()
        cache_filename = f"{content_hash}.{output_format}"
        cached_file_path = os.path.join(AUDIO_CACHE_DIR, cache_filename)
        cache_exists = await loop.run_in_executor(None, os.path.exists, cached_file_path)
        if cache_exists:
            logger.info(f"{log_prefix} Cache HIT: {cached_file_path}")
            return cached_file_path
        else:
            logger.info(f"{log_prefix} Cache MISS: {content_hash}. Đang tạo...")
            temp_generated_path = await generate_concatenated_audio(audio_content_string, output_format)
            if temp_generated_path and os.path.exists(temp_generated_path):
                logger.info(f"{log_prefix} Tạo thành công file tạm: {temp_generated_path}. Chuẩn bị cache...")
                def cache_file_sync():
                    try:
                        os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
                        shutil.copy2(temp_generated_path, cached_file_path)
                        logger.info(f"[SYNC_CACHE] Cache thành công: {cached_file_path}")
                        return cached_file_path
                    except Exception as e_sync:
                        logger.error(f"[SYNC_CACHE] Lỗi copy vào cache từ {temp_generated_path}: {e_sync}", exc_info=True)
                        return None
                final_cache_path = await loop.run_in_executor(None, cache_file_sync)
                return final_cache_path
            else:
                logger.error(f"{log_prefix} Tạo audio cho hash {content_hash} thất bại.")
                return None
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi trong quá trình lấy/tạo/cache audio: {e}", exc_info=True)
        return None
    finally:
        if temp_generated_path and os.path.exists(temp_generated_path) and temp_generated_path != final_cache_path:
            logger.debug(f"{log_prefix} Dọn dẹp file tạm {temp_generated_path} (vì đã cache hoặc lỗi cache).")
            try:
                await loop.run_in_executor(None, os.remove, temp_generated_path)
            except Exception as e_remove:
                 logger.error(f"{log_prefix} Lỗi xóa file tạm {temp_generated_path}: {e_remove}")
def _get_all_unique_audio_contents():
    """
    Hàm helper đồng bộ để truy vấn và trả về một tập hợp (set)
    chứa tất cả các chuỗi audio content duy nhất, không rỗng
    từ bảng Flashcards trong cơ sở dữ liệu.
    Returns:
        set: Set chứa các chuỗi audio content.
        None: Nếu có lỗi xảy ra khi truy vấn DB.
    """
    log_prefix = "[_GET_UNIQUE_AUDIO_CONTENTS]"
    logger.debug(f"{log_prefix} Bắt đầu lấy unique audio contents từ DB.")
    conn = None
    unique_contents = set()
    try:
        conn = database_connect()
        if conn is None:
            logger.error(f"{log_prefix} Không thể kết nối database.")
            return None
        cursor = conn.cursor()
        logger.debug(f"{log_prefix} Lấy front_audio_content...")
        cursor.execute("SELECT DISTINCT front_audio_content FROM Flashcards WHERE front_audio_content IS NOT NULL AND front_audio_content != ''")
        for row in cursor.fetchall():
            if row and row[0]:
                unique_contents.add(row[0])
        logger.debug(f"{log_prefix} Lấy back_audio_content...")
        cursor.execute("SELECT DISTINCT back_audio_content FROM Flashcards WHERE back_audio_content IS NOT NULL AND back_audio_content != ''")
        for row in cursor.fetchall():
            if row and row[0]:
                unique_contents.add(row[0])
        logger.info(f"{log_prefix} Tìm thấy {len(unique_contents)} unique audio contents.")
        return unique_contents
    except sqlite3.Error as e_db:
        logger.error(f"{log_prefix} Lỗi SQLite khi lấy audio contents: {e_db}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn: {e}", exc_info=True)
        return None
    finally:
        if conn:
            try:
                conn.close()
                logger.debug(f"{log_prefix} Đã đóng kết nối DB.")
            except Exception as e_close:
                logger.error(f"{log_prefix} Lỗi khi đóng kết nối DB: {e_close}")
async def run_background_audio_cache_job():
    """
    Chạy tác vụ nền để quét các nội dung audio duy nhất từ DB
    và tạo cache cho những nội dung chưa có.
    Hàm này không còn quản lý trạng thái chạy/dừng nữa.
    Returns:
        tuple: (status_msg, summary_dict)
               status_msg (str): Trạng thái kết thúc ('hoàn thành', 'hoàn thành với lỗi', 'lỗi DB', 'lỗi không xác định').
               summary_dict (dict): Thông tin tóm tắt {'total_unique':.., 'processed':.., 'cached_ok':.., 'errors':..}.
    """
    log_prefix = "[POPULATE_CACHE_JOB]"
    logger.info(f"{log_prefix} Bắt đầu tác vụ tạo cache nền.")
    total_contents_processed = 0
    cached_ok_count = 0
    error_count = 0
    processed_hashes = set()
    status_msg = "hoàn thành"
    loop = asyncio.get_running_loop()
    total_unique_contents = 0 
    try:
        logger.info(f"{log_prefix} Lấy danh sách unique audio contents...")
        unique_audio_contents = await loop.run_in_executor(None, _get_all_unique_audio_contents)
        if unique_audio_contents is None:
            status_msg = "lỗi DB"
            logger.error(f"{log_prefix} Không thể lấy danh sách audio content.")
            summary = {'total_unique': 0, 'processed': 0, 'cached_ok': 0, 'errors': 1}
            return status_msg, summary
        elif not unique_audio_contents:
            status_msg = "hoàn thành (không có nội dung)"
            logger.info(f"{log_prefix} Không có nội dung audio nào để cache.")
            summary = {'total_unique': 0, 'processed': 0, 'cached_ok': 0, 'errors': 0}
            return status_msg, summary
        total_unique_contents = len(unique_audio_contents)
        logger.info(f"{log_prefix} Tìm thấy {total_unique_contents} unique audio contents cần kiểm tra/tạo cache.")
        for content in unique_audio_contents:
            total_contents_processed += 1
            content_log_prefix = f"{log_prefix} Content {total_contents_processed}/{total_unique_contents}:"
            if not content or not content.strip():
                logger.debug(f"{content_log_prefix} Bỏ qua nội dung rỗng.")
                continue
            try:
                content_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()
                if content_hash not in processed_hashes:
                    logger.debug(f"{content_log_prefix} Processing hash: {content_hash[:7]}...")
                    generated_path = await get_cached_or_generate_audio(content, "mp3")
                    if generated_path:
                        logger.info(f"{content_log_prefix} Cache/Tạo OK cho hash {content_hash[:7]}.")
                        cached_ok_count += 1
                    else:
                        error_count += 1
                        logger.warning(f"{content_log_prefix} Lỗi generate/cache cho hash {content_hash[:7]}.")
                    processed_hashes.add(content_hash) 
                else:
                     logger.debug(f"{content_log_prefix} Hash {content_hash[:7]} đã xử lý.")
            except Exception as e_cont:
                error_count += 1
                logger.error(f"{content_log_prefix} Lỗi xử lý content '{content[:30]}...': {e_cont}")
            await asyncio.sleep(0.02)
        if status_msg == "hoàn thành" and error_count > 0:
            status_msg = "hoàn thành với lỗi"
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi nghiêm trọng trong job: {e}", exc_info=True)
        error_count += 1
        status_msg = "lỗi không xác định"
    finally:
        summary_dict = {
            'total_unique': total_unique_contents,
            'processed': total_contents_processed,
            'cached_ok': cached_ok_count,
            'errors': error_count
        }
        logger.info(f"{log_prefix} Job {status_msg}. Summary: {summary_dict}")
        return status_msg, summary_dict
def cleanup_unused_audio_cache(audio_format="mp3"):
    """
    Dọn dẹp các file audio trong cache không còn được tham chiếu trong database.
    Args:
        audio_format (str): Định dạng file cần dọn (mặc định 'mp3').
    Returns:
        tuple: (deleted_count, error_count)
    """
    log_prefix = "[CACHE_CLEANUP_WORKER]"
    logger.info(f"{log_prefix} Bắt đầu dọn dẹp cache audio định dạng .{audio_format}...")
    required_files = set()
    deleted_count = 0
    error_count = 0
    cache_dir = AUDIO_CACHE_DIR
    try:
        unique_contents = _get_all_unique_audio_contents() 
        if unique_contents is None:
            logger.error(f"{log_prefix} Không thể lấy danh sách nội dung audio từ DB.")
            return (0, 1)
        elif not unique_contents:
             logger.info(f"{log_prefix} Không có nội dung audio nào trong DB, không cần giữ file nào.")
        else:
            logger.info(f"{log_prefix} Tìm thấy {len(unique_contents)} unique audio content trong DB.")
            for content in unique_contents:
                try:
                    content_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()
                    required_files.add(f"{content_hash}.{audio_format}")
                except Exception as e_hash:
                    error_count += 1
                    logger.error(f"{log_prefix} Lỗi hash content '{content[:50]}...': {e_hash}")
            logger.info(f"{log_prefix} Tạo được {len(required_files)} tên file cache cần giữ.")
    except Exception as e_get_contents:
        logger.error(f"{log_prefix} Lỗi nghiêm trọng khi lấy audio contents: {e_get_contents}", exc_info=True)
        return (0, 1)
    try:
        if not os.path.isdir(cache_dir):
            logger.warning(f"{log_prefix} Thư mục cache '{cache_dir}' không tồn tại hoặc không phải thư mục.")
            return (0, error_count)
        logger.debug(f"{log_prefix} Quét thư mục cache: {cache_dir}")
        files_to_delete = []
        for filename in os.listdir(cache_dir):
            file_path = os.path.join(cache_dir, filename)
            if filename.endswith(f".{audio_format}") and os.path.isfile(file_path):
                if filename not in required_files:
                    files_to_delete.append(filename)
        logger.info(f"{log_prefix} Tìm thấy {len(files_to_delete)} file cache không cần thiết (không có trong DB).")
        if files_to_delete:
            logger.info(f"{log_prefix} Bắt đầu xóa...")
            for filename in files_to_delete:
                file_path = os.path.join(cache_dir, filename)
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.debug(f"{log_prefix} Đã xóa: {filename}")
                except Exception as e_remove:
                    error_count += 1
                    logger.error(f"{log_prefix} Lỗi xóa file {filename}: {e_remove}")
            logger.info(f"{log_prefix} Xóa xong. Đã xóa: {deleted_count}, Lỗi xóa: {error_count}")
        else:
            logger.info(f"{log_prefix} Không có file nào cần xóa.")
    except Exception as e_scan:
        logger.error(f"{log_prefix} Lỗi khi quét/xóa cache: {e_scan}", exc_info=True)
        error_count += 1
    return (deleted_count, error_count)
async def generate_review_audio_compilation(audio_contents, output_format="mp3", pause_ms=2000):
    """
    Ghép nhiều nội dung audio (dạng string) thành một file duy nhất cho ôn tập.
    Args:
        audio_contents (list): Danh sách các chuỗi nội dung audio.
        output_format (str): Định dạng file đầu ra.
        pause_ms (int): Khoảng lặng giữa các đoạn.
    Returns:
        str: Đường dẫn file tạm nếu thành công.
        None: Nếu lỗi.
    """
    log_prefix = "[COMPILE_AUDIO]"
    logger.info(f"{log_prefix} Bắt đầu ghép {len(audio_contents)} nội dung audio.")
    if not audio_contents:
        logger.warning(f"{log_prefix} Danh sách nội dung audio rỗng.")
        return None
    final_temp_path = None
    temp_segment_files = []
    loop = asyncio.get_running_loop()
    try:
        tasks = [get_cached_or_generate_audio(content, output_format) for content in audio_contents]
        logger.debug(f"{log_prefix} Chờ tạo/lấy {len(tasks)} segments...")
        segment_paths_results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"{log_prefix} Hoàn thành tạo/lấy segments.")
        temp_segment_files = [path for path in segment_paths_results if isinstance(path, str) and os.path.exists(path)]
        error_segments = [res for res in segment_paths_results if isinstance(res, Exception)]
        if error_segments:
            logger.warning(f"{log_prefix} Có lỗi khi tạo {len(error_segments)} segment(s).")
        if not temp_segment_files:
            logger.error(f"{log_prefix} Không tạo/lấy được segment nào hợp lệ.")
            return None
        logger.info(f"{log_prefix} Có {len(temp_segment_files)} segment hợp lệ để ghép.")
        if len(temp_segment_files) == 1:
             logger.info(f"{log_prefix} Chỉ có 1 segment, không cần ghép. Trả về đường dẫn segment.")
             final_temp_path = temp_segment_files[0]
             return final_temp_path
        else:
            logger.info(f"{log_prefix} Bắt đầu ghép {len(temp_segment_files)} segment...")
            def concatenate_segments_sync():
                combined = None
                exported_path = None
                count = 0
                try:
                    combined = AudioSegment.from_file(temp_segment_files[0])
                    count = 1
                    silence = None
                    if pause_ms > 0:
                        silence = AudioSegment.silent(duration=pause_ms)
                    for i in range(1, len(temp_segment_files)):
                        if silence:
                            combined += silence
                        next_segment = AudioSegment.from_file(temp_segment_files[i])
                        combined += next_segment
                        count += 1
                    with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as tmp:
                        exported_path = tmp.name
                    combined.export(exported_path, format=output_format)
                    logger.info(f"{log_prefix} Ghép thành công ({count} segments) -> {exported_path}")
                    return exported_path
                except Exception as e_concat_sync:
                     logger.error(f"{log_prefix} Lỗi ghép đồng bộ: {e_concat_sync}", exc_info=True)
                     if exported_path and os.path.exists(exported_path):
                         try:
                             os.remove(exported_path)
                         except OSError:
                             pass
                     return None
            final_temp_path = await loop.run_in_executor(None, concatenate_segments_sync)
            return final_temp_path
    except Exception as e_compile:
        logger.error(f"{log_prefix} Lỗi khi tạo compilation: {e_compile}", exc_info=True)
        if final_temp_path and os.path.exists(final_temp_path):
            try:
                await loop.run_in_executor(None, os.remove, final_temp_path)
            except OSError:
                 pass
        return None
def get_card_ids_for_audio(user_id, set_id, mode, limit=None):
    """
    Lấy danh sách flashcard_id phù hợp để tạo audio ôn tập.
    Args:
        user_id (int): ID (khóa chính) của người dùng.
        set_id (int): ID của bộ từ cụ thể.
        mode (str): Chế độ chọn thẻ ('set_all', 'set_recent', 'set_oldest').
        limit (int): Giới hạn số lượng thẻ trả về (tùy chọn).
    Returns:
        list: Danh sách flashcard_id (có thể rỗng).
        None: Nếu lỗi đầu vào.
    Raises:
        DatabaseError: Nếu có lỗi kết nối hoặc lỗi SQLite xảy ra.
    """
    log_prefix = f"[SERVICE_GET_AUDIO_IDS|UserUID:{user_id}|Set:{set_id}|Mode:{mode}|Limit:{limit}]"
    logger.info(f"{log_prefix} Bắt đầu lấy danh sách card IDs.")
    card_ids = []
    conn = None
    valid_modes = ['set_all', 'set_recent', 'set_oldest']
    if mode not in valid_modes:
        logger.error(f"{log_prefix} Chế độ '{mode}' không hợp lệ.")
        return None
    if mode in ['set_recent', 'set_oldest'] and (limit is None or not isinstance(limit, int) or limit <= 0):
        logger.error(f"{log_prefix} Giới hạn (limit={limit}) không hợp lệ cho '{mode}'.")
        return None
    try:
        conn = database_connect()
        if conn is None:
            raise DatabaseError("Không thể kết nối database.")
        cursor = conn.cursor() 
        query_base = """
            SELECT ufp.flashcard_id
            FROM UserFlashcardProgress ufp
            JOIN Flashcards f ON ufp.flashcard_id = f.flashcard_id
            WHERE ufp.user_id = ? AND f.set_id = ?
        """
        params = [user_id, set_id] 
        order_clause = ""
        limit_clause = ""
        if mode == 'set_recent':
            order_clause = "ORDER BY ufp.learned_date DESC, ufp.progress_id DESC"
            limit_clause = "LIMIT ?"
            params.append(limit)
        elif mode == 'set_oldest':
            order_clause = "ORDER BY ufp.learned_date ASC, ufp.progress_id ASC"
            limit_clause = "LIMIT ?"
            params.append(limit)
        final_query = f"{query_base} {order_clause} {limit_clause}"
        logger.debug(f"{log_prefix} Executing query: {final_query.strip()} with params: {params}")
        cursor.execute(final_query, params)
        card_ids = [row[0] for row in cursor.fetchall() if row and row[0] is not None]
        logger.info(f"{log_prefix} Tìm thấy {len(card_ids)} card IDs.")
        return card_ids
    except sqlite3.Error as db_err:
        logger.exception(f"{log_prefix} Lỗi SQLite: {db_err}")
        raise DatabaseError("Lỗi SQLite khi lấy card IDs audio.", original_exception=db_err)
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi trong hàm: {e}")
        if isinstance(e, DatabaseError):
            raise e 
        raise DatabaseError("Lỗi không mong muốn khi lấy card IDs audio.", original_exception=e)
    finally:
        if conn:
            try:
                conn.close()
                logger.debug(f"{log_prefix} Đã đóng kết nối DB.")
            except Exception as e_close_conn:
                logger.error(f"{log_prefix} Lỗi khi đóng kết nối DB: {e_close_conn}")