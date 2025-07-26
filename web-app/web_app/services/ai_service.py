# flashcard-web/web_app/services/ai_service.py
import logging
import os
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

def _create_flashcard_prompt(flashcard):
    """
    Tạo prompt để yêu cầu AI giải thích cho một flashcard.
    Hàm này tạo ra một câu lệnh rõ ràng để AI hiểu và trả về kết quả mong muốn.
    """
    return (f"Với vai trò là một trợ lý học tập, hãy giải thích ngắn gọn, rõ ràng và dễ hiểu về thuật ngữ sau. "
            f"Tập trung vào ý nghĩa cốt lõi, cung cấp ví dụ thực tế về cách dùng.\n\n"
            f"**Thuật ngữ:** '{flashcard.front}'\n"
            f"**Định nghĩa:** '{flashcard.back}'\n\n"
            f"Hãy trình bày câu trả lời theo định dạng Markdown.")

def _create_quiz_question_prompt(question):
    """
    Tạo prompt để yêu cầu AI giải thích cho một câu hỏi trắc nghiệm.
    Hàm này yêu cầu AI không chỉ giải thích đáp án đúng mà còn phân tích các đáp án sai.
    """
    options = f"A. {question.option_a}\nB. {question.option_b}"
    if question.option_c:
        options += f"\nC. {question.option_c}"
    if question.option_d:
        options += f"\nD. {question.option_d}"
    
    return (f"Với vai trò là một trợ lý học tập, hãy giải thích cặn kẽ câu hỏi trắc nghiệm sau.\n\n"
            f"**Câu hỏi:** {question.question or question.pre_question_text}\n"
            f"**Các lựa chọn:**\n{options}\n"
            f"**Đáp án đúng:** {question.correct_answer}\n\n"
            f"**Yêu cầu:**\n"
            f"1. Giải thích chi tiết tại sao đáp án '{question.correct_answer}' là phương án chính xác.\n"
            f"2. Phân tích và giải thích tại sao các phương án còn lại không đúng.\n"
            f"Hãy trình bày câu trả lời một cách logic, rõ ràng và sử dụng định dạng Markdown.")

def generate_ai_explanation(item, item_type='flashcard'):
    """
    Tạo và trả về nội dung giải thích từ AI cho một đối tượng (flashcard hoặc quiz).

    Hàm này là giao diện chính để tương tác với Gemini API. Nó kiểm tra các điều kiện cần thiết,
    chọn prompt phù hợp, gọi API và xử lý kết quả trả về.

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
        # Khởi tạo mô hình AI - ĐÃ THAY ĐỔI
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        # Chọn prompt phù hợp dựa trên loại item
        if item_type == 'flashcard':
            prompt = _create_flashcard_prompt(item)
        elif item_type == 'quiz':
            prompt = _create_quiz_question_prompt(item)
        else:
            logger.error(f"Loại item không hợp lệ được cung cấp cho AI service: {item_type}")
            return None

        # Gửi yêu cầu đến API
        response = model.generate_content(prompt)
        
        # Xử lý và trả về kết quả
        if response and hasattr(response, 'text'):
            explanation = response.text
            item_id = item.flashcard_id if item_type == 'flashcard' else item.question_id
            logger.info(f"Đã tạo giải thích AI thành công cho {item_type} ID {item_id}")
            return explanation
        else:
            item_id = item.flashcard_id if item_type == 'flashcard' else item.question_id
            logger.warning(f"Không nhận được nội dung hợp lệ từ Gemini API cho {item_type} ID {item_id}. Response: {response.prompt_feedback}")
            return None

    except Exception as e:
        logger.error(f"Lỗi xảy ra trong quá trình gọi Gemini API: {e}")
        return None
