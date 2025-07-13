# flashcard-web/web_app/config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_PATH = os.path.join(BASE_DIR, "..", "..", "database", "flashcard.db")

# BẮT ĐẦU THAY ĐỔI: Định nghĩa các thư mục media riêng biệt
APP_MEDIA_BASE_DIR = os.path.join(BASE_DIR, "..", "..", "media")

# Thư mục media cho Flashcard
FLASHCARD_MEDIA_DIR = os.path.join(APP_MEDIA_BASE_DIR, "flashcard")
FLASHCARD_AUDIO_CACHE_DIR = os.path.join(FLASHCARD_MEDIA_DIR, "audio")
FLASHCARD_IMAGES_DIR = os.path.join(FLASHCARD_MEDIA_DIR, "images")

# Thư mục media cho Quiz
QUIZ_MEDIA_DIR = os.path.join(APP_MEDIA_BASE_DIR, "quiz")
QUIZ_AUDIO_CACHE_DIR = os.path.join(QUIZ_MEDIA_DIR, "audio")
QUIZ_IMAGES_DIR = os.path.join(QUIZ_MEDIA_DIR, "images")

# Cập nhật các biến toàn cục mà các service/module khác đang sử dụng
AUDIO_CACHE_DIR = FLASHCARD_AUDIO_CACHE_DIR # Được sử dụng bởi audio_service
IMAGES_DIR = FLASHCARD_IMAGES_DIR # Được sử dụng bởi serve_flashcard_image (trước đây là serve_image)
# KẾT THÚC THAY ĐỔI

CACHE_GENERATION_DELAY = 1.5 # Độ trễ giữa các lần gọi TTS (giây)
TEMP_CHARTS_DIR = os.path.join(BASE_DIR, 'temp_charts')

SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
SQLALCHEMY_TRACK_MODIFICATIONS = False

SECRET_KEY = os.getenv('SECRET_KEY', 'mot_chuoi_bi_mat_rat_dai_va_phuc_tap_cho_flask_moi')

# --- Hằng số Chế độ Học/Ôn tập (Flashcard) ---
MODE_SEQUENTIAL_LEARNING = 'sequential_learning' 
MODE_NEW_CARDS_ONLY = 'new_cards_only'         
MODE_REVIEW_ALL_DUE = 'review_all_due'          
MODE_REVIEW_HARDEST = 'review_hardest'          
MODE_AUTOPLAY_REVIEW = 'autoplay_review'        

DEFAULT_LEARNING_MODE = MODE_SEQUENTIAL_LEARNING

LEARNING_MODE_DISPLAY_NAMES = {
    MODE_SEQUENTIAL_LEARNING: "Học tuần tự",
    MODE_NEW_CARDS_ONLY: "Chỉ học mới",
    MODE_REVIEW_ALL_DUE: "Ôn tập tổng hợp",
    MODE_REVIEW_HARDEST: "Chỉ từ khó",
    MODE_AUTOPLAY_REVIEW: "Autoplay",
}

# --- Hằng số Chế độ Quiz ---
QUIZ_MODE_NEW_SEQUENTIAL = 'quiz_new_sequential' # Làm mới tuần tự
QUIZ_MODE_NEW_RANDOM = 'quiz_new_random'         # Làm mới ngẫu nhiên
QUIZ_MODE_REVIEW = 'quiz_review'                 # Ôn tập ngẫu nhiên

DEFAULT_QUIZ_MODE = QUIZ_MODE_NEW_SEQUENTIAL

QUIZ_MODE_DISPLAY_NAMES = {
    QUIZ_MODE_NEW_SEQUENTIAL: "Làm mới tuần tự",
    QUIZ_MODE_NEW_RANDOM: "Làm mới ngẫu nhiên",
    QUIZ_MODE_REVIEW: "Ôn tập",
}

# --- Hằng số Thuật toán SRS & Review Logic ---
SRS_INITIAL_INTERVAL_HOURS = 1.0
SRS_MAX_INTERVAL_DAYS = 30
RETRY_INTERVAL_WRONG_MIN = 30
RETRY_INTERVAL_HARD_MIN = 60
RETRY_INTERVAL_NEW_MIN = 10

# --- Điểm số ---
SCORE_INCREASE_CORRECT = 5
SCORE_INCREASE_HARD = 1
SCORE_INCREASE_NEW_CARD = 10
SCORE_INCREASE_QUICK_REVIEW_CORRECT = 1
SCORE_INCREASE_QUICK_REVIEW_HARD = 0
SKIP_STREAK_THRESHOLD = 10
SCORE_QUIZ_CORRECT_FIRST_TIME = 10
SCORE_QUIZ_CORRECT_REPEAT = 3

# --- Hằng số UI ---
DAILY_HISTORY_MAX_DAYS = 30
SETS_PER_PAGE = 8
LEADERBOARD_LIMIT = 50

# --- Hằng số Múi giờ ---
DEFAULT_TIMEZONE_OFFSET = 7

# --- Tạo các thư mục cần thiết ---
DIRECTORIES_TO_CREATE = [
    FLASHCARD_AUDIO_CACHE_DIR,
    FLASHCARD_IMAGES_DIR,
    QUIZ_AUDIO_CACHE_DIR, # THÊM MỚI
    QUIZ_IMAGES_DIR # THÊM MỚI
]

for dir_path in DIRECTORIES_TO_CREATE:
    if not dir_path:
        continue
    try:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"Đã tạo thư mục: {dir_path}")
    except OSError as e:
        print(f"Lỗi: Không thể tạo thư mục {dir_path}: {e}")
    except Exception as e_create:
        print(f"Lỗi không mong muốn khi tạo thư mục {dir_path}: {e_create}")

