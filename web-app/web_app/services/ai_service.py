# flashcard-web/web_app/services/ai_service.py
import logging
from web_app.config import GEMINI_API_KEY

# Thử import thư viện của Google, nếu không có thì sẽ không dùng được service này
try:
    import google.generativeai as genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)

# --- Cấu hình API ---
# Cấu hình API key cho Google Gemini.
# Nếu không có API key hoặc thư viện, service sẽ không hoạt động.
if genai:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Không thể cấu hình Google Gemini API: {e}")
        genai = None # Vô hiệu hóa nếu cấu hình thất bại
else:
    logger.warning("Thư viện 'google-generativeai' chưa được cài đặt. AI service sẽ bị vô hiệu hóa.")

# --- BẮT ĐẦU THAY ĐỔI: Định nghĩa các prompt mặc định ---
DEFAULT_FLASHCARD_PROMPT = (
    "Với vai trò là một trợ lý học tập, hãy giải thích ngắn gọn, rõ ràng và dễ hiểu về thuật ngữ sau. "
    "Tập trung vào ý nghĩa cốt lõi, cung cấp ví dụ thực tế về cách dùng.\n\n"
    "**Thuật ngữ:** '{front}'\n"
    "**Định nghĩa:** '{back}'\n\n"
    "Hãy trình bày câu trả lời theo định dạng Markdown."
)

DEFAULT_QUIZ_PROMPT = (
    "Với vai trò là một trợ lý học tập, hãy giải thích cặn kẽ câu hỏi trắc nghiệm sau.\n\n"
    "**Câu hỏi:** {question_text}\n"
    "**Các lựa chọn:**\n{options}\n"
    "**Đáp án đúng:** {correct_answer}\n\n"
    "**Yêu cầu:**\n"
    "1. Giải thích chi tiết tại sao đáp án '{correct_answer}' là phương án chính xác.\n"
    "2. Phân tích và giải thích tại sao các phương án còn lại không đúng.\n"
    "Hãy trình bày câu trả lời một cách logic, rõ ràng và sử dụng định dạng Markdown."
)
# --- KẾT THÚC THAY ĐỔI ---

def _get_active_prompt(item, item_type):
    """
    Xác định prompt sẽ được sử dụng dựa trên hệ thống cấp bậc: Item > Set > Default.
    Mục đích: Lấy ra prompt phù hợp nhất để sử dụng cho việc tạo giải thích AI.
    1. Ưu tiên prompt được định nghĩa riêng cho từng thẻ (item).
    2. Nếu không có, tìm đến prompt của bộ chứa nó (set).
    3. Nếu vẫn không có, sử dụng prompt mặc định của hệ thống.
    """
    # Ưu tiên 1: Prompt của riêng item (thẻ hoặc câu hỏi)
    if item.ai_prompt:
        logger.debug(f"Sử dụng prompt tùy chỉnh của item ID {getattr(item, f'{item_type}_id', 'N/A')}.")
        return item.ai_prompt

    # Ưu tiên 2: Prompt của bộ chứa item
    parent_set = getattr(item, 'vocabulary_set' if item_type == 'flashcard' else 'question_set', None)
    if parent_set and parent_set.ai_prompt:
        logger.debug(f"Sử dụng prompt tùy chỉnh của Set ID {parent_set.set_id}.")
        return parent_set.ai_prompt

    # Ưu tiên 3: Prompt mặc định
    logger.debug("Sử dụng prompt mặc định của hệ thống.")
    if item_type == 'flashcard':
        return DEFAULT_FLASHCARD_PROMPT
    elif item_type == 'quiz':
        return DEFAULT_QUIZ_PROMPT
    return None

def _format_prompt(raw_prompt, item, item_type):
    """
    Điền các thông tin cụ thể của item vào trong chuỗi prompt thô.
    Mục đích: Tạo ra nội dung prompt cuối cùng để gửi đến AI.
    Hàm này thay thế các placeholder như {front}, {back}, {question_text} bằng dữ liệu thật.
    """
    if item_type == 'flashcard':
        return raw_prompt.format(front=item.front, back=item.back)
    
    elif item_type == 'quiz':
        options_list = [f"A. {item.option_a}", f"B. {item.option_b}"]
        if item.option_c:
            options_list.append(f"C. {item.option_c}")
        if item.option_d:
            options_list.append(f"D. {item.option_d}")
        
        return raw_prompt.format(
            question_text=(item.question or item.pre_question_text),
            options="\n".join(options_list),
            correct_answer=item.correct_answer
        )
    return raw_prompt


def generate_ai_explanation(item, item_type='flashcard'):
    """
    Tạo và trả về nội dung giải thích từ AI cho một đối tượng (flashcard hoặc quiz).

    Hàm này là giao diện chính để tương tác với Gemini API. Nó kiểm tra các điều kiện cần thiết,
    chọn prompt phù hợp theo hệ thống cấp bậc, định dạng prompt, gọi API và xử lý kết quả trả về.

    Args:
        item: Đối tượng `Flashcard` hoặc `QuizQuestion`.
        item_type (str): Loại đối tượng, có thể là 'flashcard' hoặc 'quiz'.

    Returns:
        str: Nội dung giải thích do AI tạo ra, hoặc None nếu có lỗi hoặc API không khả dụng.
    """
    # Kiểm tra xem Gemini API có sẵn sàng để sử dụng không
    if not genai or GEMINI_API_KEY == 'YOUR_GEMINI_API_KEY_HERE':
        logger.warning("Gemini API chưa được cấu hình hoặc chưa cài đặt, bỏ qua việc tạo giải thích.")
        return None

    try:
        # Khởi tạo mô hình AI
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        # --- BẮT ĐẦU THAY ĐỔI: Logic chọn và định dạng prompt ---
        # 1. Lấy prompt thô dựa trên hệ thống cấp bậc
        raw_prompt = _get_active_prompt(item, item_type)
        if not raw_prompt:
            logger.error(f"Không thể xác định prompt cho item_type: {item_type}")
            return None

        # 2. Định dạng prompt với dữ liệu của item
        final_prompt = _format_prompt(raw_prompt, item, item_type)
        # --- KẾT THÚC THAY ĐỔI ---

        # Gửi yêu cầu đến API
        response = model.generate_content(final_prompt)
        
        # Xử lý và trả về kết quả
        if response and hasattr(response, 'text'):
            explanation = response.text
            item_id = item.flashcard_id if item_type == 'flashcard' else item.question_id
            logger.info(f"Đã tạo giải thích AI thành công cho {item_type} ID {item_id}")
            return explanation
        else:
            item_id = item.flashcard_id if item_type == 'flashcard' else item.question_id
            logger.warning(f"Không nhận được nội dung hợp lệ từ Gemini API cho {item_type} ID {item_id}. Response: {getattr(response, 'prompt_feedback', 'N/A')}")
            return None

    except Exception as e:
        item_id = item.flashcard_id if item_type == 'flashcard' else item.question_id
        logger.error(f"Lỗi xảy ra trong quá trình gọi Gemini API cho {item_type} ID {item_id}: {e}", exc_info=True)
        return None
