# web_app/services/__init__.py
from .learning_logic import LearningLogicService
from .user_service import UserService
from .stats_service import StatsService
from .audio_service import AudioService
from .note_service import NoteService
from .set_service import SetService
from .flashcard_service import FlashcardService
from .quiz_service import QuizService
from .quiz_note_service import QuizNoteService
# --- BẮT ĐẦU THÊM MỚI ---
from .feedback_service import FeedbackService
# --- KẾT THÚC THÊM MỚI ---

# Khởi tạo các service để có thể import và sử dụng trực tiếp
learning_logic_service = LearningLogicService()
user_service = UserService()
stats_service = StatsService()
audio_service = AudioService()
note_service = NoteService()
set_service = SetService()
flashcard_service = FlashcardService()
quiz_service = QuizService()
quiz_note_service = QuizNoteService()
# --- BẮT ĐẦU THÊM MỚI ---
feedback_service = FeedbackService()
# --- KẾT THÚC THÊM MỚI ---
