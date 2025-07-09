# flashcard-web/web_app/config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "..", "..", "database", "flashcard.db")

SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
SQLALCHEMY_TRACK_MODIFICATIONS = False

SECRET_KEY = os.getenv('SECRET_KEY', 'mot_chuoi_bi_mat_rat_dai_va_phuc_tap_cho_flask_moi')

# --- Hằng số Chế độ Học/Ôn tập (ĐÃ ĐƠN GIẢN HÓA) ---
MODE_SEQUENTIAL_LEARNING = 'sequential_learning' # Chế độ học tuần tự (mặc định mới): Học mới tuần tự + ôn tập đến hạn
MODE_NEW_CARDS_ONLY = 'new_cards_only'         # Chỉ học thẻ mới (tuần tự)
MODE_REVIEW_ALL_DUE = 'review_all_due'          # Ôn tập tổng hợp tất cả thẻ đến hạn (ngẫu nhiên)
MODE_REVIEW_HARDEST = 'review_hardest'          # Ôn tập các từ khó nhất (đến hạn)
MODE_AUTOPLAY_REVIEW = 'autoplay_review'        # Chế độ Autoplay: Tự động lật thẻ đã học

DEFAULT_LEARNING_MODE = MODE_SEQUENTIAL_LEARNING # Chế độ học mặc định mới

LEARNING_MODE_DISPLAY_NAMES = {
    MODE_SEQUENTIAL_LEARNING: "Học tuần tự",
    MODE_NEW_CARDS_ONLY: "Chỉ học mới",
    MODE_REVIEW_ALL_DUE: "Ôn tập tổng hợp",
    MODE_REVIEW_HARDEST: "Chỉ từ khó",
    MODE_AUTOPLAY_REVIEW: "Autoplay",
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

# --- Hằng số UI ---
DAILY_HISTORY_MAX_DAYS = 30
SETS_PER_PAGE = 8
LEADERBOARD_LIMIT = 50

# --- Hằng số Múi giờ ---
DEFAULT_TIMEZONE_OFFSET = 7

# --- Hằng số Audio (MỚI THÊM CHO WEB APP) ---
MEDIA_BASE_DIR = os.path.join(BASE_DIR, "..", "..", "..", "media", "flashcard")
AUDIO_CACHE_DIR = os.path.join(MEDIA_BASE_DIR, "audio")
CACHE_GENERATION_DELAY = 1.5 # Độ trễ giữa các lần gọi TTS (giây)
IMAGES_DIR = os.path.join(MEDIA_BASE_DIR, "images")
TEMP_CHARTS_DIR = os.path.join(BASE_DIR, 'temp_charts')

# BẮT ĐẦU THAY ĐỔI: Hằng số cho Autoplay
AUTOPLAY_CARD_DELAY_MS = 2000 # Khoảng thời gian chờ sau khi audio mặt sau kết thúc (miligiây)
# KẾT THÚC THAY ĐỔI

# --- Tạo các thư mục cần thiết (MỚI THÊM CHO WEB APP) ---
DIRECTORIES_TO_CREATE = [
    AUDIO_CACHE_DIR,
    IMAGES_DIR
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
