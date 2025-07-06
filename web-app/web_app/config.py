# flashcard-web/web_app/config.py
import os

# KHÔNG DÙNG os.path.join HAY os.path.abspath NỮA.
# ĐƯỜNG DẪN DATABASE SẼ LÀ ĐƯỜNG DẪN TUYỆT ĐỐI BẠN ĐÃ XÁC NHẬN.
DATABASE_PATH = r"C:\Users\thanh\OneDrive\CodeHub\Flashcard-Proj\database\flashcard.db" # Đảm bảo đường dẫn này là chính xác trên máy bạn.

SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# DEFAULT_WEB_ADMIN_TELEGRAM_ID không còn cần thiết cho việc đăng nhập mặc định.
# DEFAULT_WEB_ADMIN_TELEGRAM_ID = 936620007

SECRET_KEY = os.getenv('SECRET_KEY', 'mot_chuoi_bi_mat_rat_dai_va_phuc_tap_cho_flask_moi')

# --- Hằng số Chế độ Học/Ôn tập ---
MODE_SEQ_INTERSPERSED = 'sequential_interspersed' # Chế độ học tuần tự (mặc định)
MODE_SEQ_RANDOM_NEW = 'sequential_random_new'    
MODE_NEW_SEQUENTIAL = 'new_sequential'           
MODE_DUE_ONLY_RANDOM = 'due_only_random'         
MODE_REVIEW_ALL_DUE = 'review_all_due'           
MODE_REVIEW_HARDEST = 'review_hardest'           
MODE_CRAM_SET = 'cram_set'                       
MODE_CRAM_ALL = 'cram_all'                       
MODE_NEW_RANDOM = 'new_random'                   
DEFAULT_LEARNING_MODE = MODE_SEQ_INTERSPERSED # Chế độ học mặc định cho web app

LEARNING_MODE_DISPLAY_NAMES = {
    MODE_SEQ_INTERSPERSED: "Ghi nhớ sâu tuần tự",
    MODE_SEQ_RANDOM_NEW: "Ghi nhớ sâu ngẫu nhiên",
    MODE_NEW_SEQUENTIAL: "Học mới tuần tự",
    MODE_NEW_RANDOM: "Học mới ngẫu nhiên",
    MODE_DUE_ONLY_RANDOM: "Ôn tập theo bộ",
    MODE_REVIEW_ALL_DUE: "Ôn tập tổng hợp",
    MODE_REVIEW_HARDEST: "Ôn tập nhanh từ khó",
    MODE_CRAM_SET: "Ôn tập nhanh theo bộ",
    MODE_CRAM_ALL: "Ôn tập nhanh tổng hợp",
}

# --- Hằng số Thuật toán SRS & Review Logic ---
SRS_INITIAL_INTERVAL_HOURS = 1.0 # Đã thay đổi từ 0.5 thành 1.0 để đồng bộ với Telegram bot
SRS_MAX_INTERVAL_DAYS = 30
RETRY_INTERVAL_WRONG_MIN = 30 # Thời gian chờ nếu trả lời sai (phút)
RETRY_INTERVAL_HARD_MIN = 60  # Thời gian chờ nếu trả lời mơ hồ (phút)
RETRY_INTERVAL_NEW_MIN = 10   # Thời gian chờ nếu là thẻ mới (phút)

# --- Điểm số ---
SCORE_INCREASE_CORRECT = 5
SCORE_INCREASE_HARD = 1
SCORE_INCREASE_NEW_CARD = 10
SCORE_INCREASE_QUICK_REVIEW_CORRECT = 1
SCORE_INCREASE_QUICK_REVIEW_HARD = 0
SKIP_STREAK_THRESHOLD = 10 # Số lần đúng liên tiếp để có thể bỏ qua thẻ

# --- Hằng số UI ---
DAILY_HISTORY_MAX_DAYS = 30 # Số ngày hiển thị trong lịch sử hoạt động
SETS_PER_PAGE = 8 # Số bộ thẻ hiển thị trên mỗi trang

# --- Hằng số Múi giờ ---
DEFAULT_TIMEZONE_OFFSET = 7 # Múi giờ mặc định (UTC+7)
