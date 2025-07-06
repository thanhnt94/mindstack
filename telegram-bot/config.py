# File: flashcard-telegram-bot/config.py
"""
File cấu hình trung tâm cho Flashcard Bot.
(Sửa lần 5: Thêm chú thích tiếng Việt cho các hằng số)
(Sửa lần 6: Thêm hằng số callback cho luồng xóa bộ từ)
"""

import os
import logging
import sys
from dotenv import load_dotenv

# --- Tải biến môi trường ---
load_dotenv()

# --- Định nghĩa Đường dẫn ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
FLASHCARD_DB_PATH = os.path.join(r"C:\Users\thanh\OneDrive\CodeHub\Flashcard-Proj\database\flashcard.db")
MEDIA_BASE_DIR = os.path.join(BASE_DIR, "..", "..","media", "flashcard")
AUDIO_CACHE_DIR = os.path.join(MEDIA_BASE_DIR, "audio")
IMAGES_DIR = os.path.join(MEDIA_BASE_DIR, "images") 
NOTE_IMAGES_DIR = os.path.join(IMAGES_DIR, "flashcard_note") 
TEMP_BASE_DIR = os.path.join(BASE_DIR, "..", "..", "temp") 
TEMP_UPLOAD_DIR = os.path.join(TEMP_BASE_DIR, "uploads")
TEMP_UPDATE_DIR = os.path.join(TEMP_BASE_DIR, "updates")
TEMP_EXPORT_DIR = os.path.join(TEMP_BASE_DIR, "exports")
TEMP_CHARTS_DIR = os.path.join(TEMP_BASE_DIR, "charts")
# -----------------------------------------------

# --- Cấu hình Bot ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.critical("LỖI NGHIÊM TRỌNG: BOT_TOKEN chưa được thiết lập.")
    sys.exit(1) 

# --- Hằng số Nghiệp vụ Chung ---
DEFAULT_TIMEZONE_OFFSET = 7
DEFAULT_ADMIN_TELEGRAM_ID = 936620007 
CACHE_GENERATION_DELAY = 1.5

# --- Hằng số Chế độ Học/Ôn tập ---
MODE_SEQ_INTERSPERSED = 'sequential_interspersed'
MODE_SEQ_RANDOM_NEW = 'sequential_random_new'    
MODE_NEW_SEQUENTIAL = 'new_sequential'           
MODE_DUE_ONLY_RANDOM = 'due_only_random'         
MODE_REVIEW_ALL_DUE = 'review_all_due'           
MODE_REVIEW_HARDEST = 'review_hardest'           
MODE_CRAM_SET = 'cram_set'                       
MODE_CRAM_ALL = 'cram_all'                       
MODE_NEW_RANDOM = 'new_random'                   
DEFAULT_LEARNING_MODE = MODE_SEQ_INTERSPERSED
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
SRS_INITIAL_INTERVAL_HOURS = 0.5
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

# === HỆ THỐNG PHÂN QUYỀN ===
CAN_LEARN = 'can_learn'                        
CAN_MANAGE_OWN_SETS = 'can_manage_own_sets'    
CAN_UPLOAD_SET = 'can_upload_set'              
CAN_EXPORT_SET = 'can_export_set'              
CAN_USE_TTS_AUDIO = 'can_use_tts_audio'        
CAN_EXPORT_AUDIO = 'can_export_audio'          
HAS_UNLIMITED_NEW_CARDS = 'has_unlimited_new_cards' 
NO_ADS = 'no_ads'                              
CAN_TOGGLE_SUMMARY = 'can_toggle_summary'      
CAN_ACCESS_ADMIN_MENU = 'can_access_admin_menu' 
CAN_MANAGE_USERS = 'can_manage_users'          
CAN_MANAGE_CACHE = 'can_manage_cache'          
CAN_SET_ROLES = 'can_set_roles'                
CAN_SET_LIMITS = 'can_set_limits'              
CAN_BROADCAST_MESSAGES = 'can_broadcast_messages' 
ALL_PERMISSIONS = {
    CAN_LEARN, CAN_MANAGE_OWN_SETS, CAN_UPLOAD_SET, CAN_EXPORT_SET,
    CAN_USE_TTS_AUDIO, CAN_EXPORT_AUDIO, HAS_UNLIMITED_NEW_CARDS, NO_ADS,
    CAN_TOGGLE_SUMMARY, CAN_ACCESS_ADMIN_MENU, CAN_MANAGE_USERS, CAN_MANAGE_CACHE,
    CAN_SET_ROLES, CAN_SET_LIMITS, CAN_BROADCAST_MESSAGES
}
ROLE_PERMISSIONS = {
    'user': {CAN_LEARN, CAN_MANAGE_OWN_SETS},
    'lite': {CAN_LEARN, CAN_MANAGE_OWN_SETS, CAN_USE_TTS_AUDIO, CAN_EXPORT_AUDIO, CAN_TOGGLE_SUMMARY, NO_ADS},
    'vip': {CAN_LEARN, CAN_MANAGE_OWN_SETS, CAN_UPLOAD_SET, CAN_EXPORT_SET, CAN_USE_TTS_AUDIO, CAN_EXPORT_AUDIO, HAS_UNLIMITED_NEW_CARDS, CAN_TOGGLE_SUMMARY, NO_ADS},
    'admin': ALL_PERMISSIONS,
    'banned': set() 
}
DAILY_LIMIT_USER = 10
DAILY_LIMIT_LITE = 50
DAILY_LIMIT_VIP = 99999 
AD_INTERVAL = 5
# === KẾT THÚC HỆ THỐNG PHÂN QUYỀN ===

# --- Hằng số Thông báo & Jobs ---
SLEEP_START_HOUR = 23 
SLEEP_END_HOUR = 7 
PERIODIC_REMINDER_INTERVAL_MIN = 5
BROADCAST_SEND_DELAY = 0.1 
INACTIVITY_REMINDER_DAYS = 3 
INACTIVITY_CHECK_INTERVAL_HOURS = 24
MORNING_BRIEF_JOB_HOUR_UTC = 1 
MORNING_BRIEF_LOCAL_START_HOUR = 6 
MORNING_BRIEF_LOCAL_END_HOUR = 9   
NOTIFICATION_SET_REMINDER_MEMORY = 5 
NOTIFICATION_MIN_INACTIVITY_MIN = 10

# --- Hằng số Audio ---
CONCAT_AUDIO_PAUSE_MS = 400
AUDIO_COMPILATION_PAUSE_MS = 2000
AUDIO_OUTPUT_FORMAT = "mp3"
AUDIO_N_OPTIONS = [5, 10, 15, 20, 30, 50]

# --- Hằng số Giao diện (UI) ---
LEADERBOARD_LIMIT = 10
DAILY_HISTORY_MAX_DAYS = 30
NOTIFICATION_INTERVAL_OPTIONS = [5, 10, 15, 30, 45, 60, 120, 180, 240]
SETS_PER_PAGE = 8 
REPORTS_PER_PAGE = 15
FLIP_DELAY_MEDIA = 0.5
FLIP_DELAY_TEXT = 0.2

# --- Hằng số Callback Query Prefixes & Patterns ---
NOTIFY_CALLBACK_PREFIX = "notify_settings" 
AUDIO_REVIEW_CALLBACK_PREFIX = "audioreview"
EXPORT_SET_CALLBACK_PREFIX = "export_set_select:"
UPDATE_SET_CALLBACK_PREFIX = "update_set_select:"
# Sửa lần 6: Thêm prefix cho quản lý bộ từ
SET_MGMT_CALLBACK_PREFIX = "set_management" 

NOTIFY_TOGGLE_PERIODIC = f"{NOTIFY_CALLBACK_PREFIX}:toggle_periodic" 
NOTIFY_INTERVAL_MENU = f"{NOTIFY_CALLBACK_PREFIX}:interval_menu"
NOTIFY_INTERVAL_SET = f"{NOTIFY_CALLBACK_PREFIX}:interval_set:" 
NOTIFY_BACK_TO_MAIN_SETTINGS = f"{NOTIFY_CALLBACK_PREFIX}:back_to_main_settings"
NOTIFY_CHOOSE_TARGET_SET_MENU = f"{NOTIFY_CALLBACK_PREFIX}:choose_target_set_menu"
NOTIFY_TARGET_SET_PAGE = f"{NOTIFY_CALLBACK_PREFIX}:target_set_page" 
NOTIFY_SELECT_TARGET_SET_ACTION = f"{NOTIFY_CALLBACK_PREFIX}:select_target_set_action:" 
NOTIFY_CLEAR_TARGET_SET_ACTION = f"{NOTIFY_CALLBACK_PREFIX}:clear_target_set_action"
NOTIFY_TOGGLE_MORNING_BRIEF_ACTION = f"{NOTIFY_CALLBACK_PREFIX}:toggle_morning_brief_action"

# Sửa lần 6: Callback cho luồng xóa bộ từ
SET_MGMT_DELETE_MENU_PFX = f"{SET_MGMT_CALLBACK_PREFIX}:delete_menu" # Hiển thị danh sách bộ để chọn xóa
SET_MGMT_ASK_CONFIRM_DELETE_PFX = f"{SET_MGMT_CALLBACK_PREFIX}:ask_delete_confirm:" # vd: ...:ask_delete_confirm:123
SET_MGMT_CONFIRM_DELETE_ACTION_PFX = f"{SET_MGMT_CALLBACK_PREFIX}:do_delete_action:" # vd: ...:do_delete_action:123
SET_MGMT_CANCEL_DELETE_PFX = f"{SET_MGMT_CALLBACK_PREFIX}:cancel_delete" # Hủy xóa, quay lại menu quản lý


# --- Hằng số Conversation Handler States ---
(
    SET_DAILY_LIMIT,              # 0
    WAITING_NEW_SET_UPLOAD,       # 1 
    WAITING_FOR_UPDATE_FILE,      # 2
    GETTING_BROADCAST_MESSAGE,    # 3
    CONFIRMING_BROADCAST,         # 4
    GETTING_REPORT_REASON,        # 5
    GET_NOTE_INPUT,               # 6
    SELECTING_NOTIFICATION_TARGET_SET # 7 
) = range(8) 

# === CẤU HÌNH HIỂN THỊ VAI TRÒ (ICON VÀ TÊN) ===
ROLE_DISPLAY_CONFIG = {
    'user':     ("👤", "Thường"), 'lite': ("⭐", "Lite"), 'vip': ("💎", "VIP"),
    'admin':    ("👑", "Admin"), 'banned': ("🚫", "Bị khóa")
}
# === KẾT THÚC CẤU HÌNH HIỂN THỊ VAI TRÒ ===

# --- Tạo các thư mục cần thiết ---
DIRECTORIES_TO_CREATE = [
    os.path.dirname(FLASHCARD_DB_PATH), MEDIA_BASE_DIR, AUDIO_CACHE_DIR,
    IMAGES_DIR, NOTE_IMAGES_DIR, TEMP_BASE_DIR, TEMP_UPLOAD_DIR,
    TEMP_UPDATE_DIR, TEMP_EXPORT_DIR, TEMP_CHARTS_DIR 
]
for dir_path in DIRECTORIES_TO_CREATE:
    if not dir_path: continue
    try:
        if not os.path.exists(dir_path): os.makedirs(dir_path); logging.info(f"Đã tạo thư mục: {dir_path}")
    except OSError as e: logging.error(f"Không thể tạo thư mục {dir_path}: {e}")
    except Exception as e_create: logging.error(f"Lỗi không mong muốn khi tạo thư mục {dir_path}: {e_create}")

# --- Cấu hình Logging ---
class HideHttpRequestFilter(logging.Filter):
    def filter(self, record): return "HTTP Request" not in record.getMessage()
logging.basicConfig(
    level=logging.DEBUG, 
    format='[%(levelname)s] %(asctime)s - %(name)s - %(module)s > %(funcName)s | (%(lineno)d) - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger_global = logging.getLogger(); filter_instance = HideHttpRequestFilter(); applied_filter = False
for handler_item in logger_global.handlers: handler_item.addFilter(filter_instance); applied_filter = True
if not applied_filter:
    console_handler = logging.StreamHandler(sys.stdout); console_handler.addFilter(filter_instance)
    formatter = logging.Formatter('[%(levelname)s] %(asctime)s - %(name)s - %(module)s > %(funcName)s | (%(lineno)d) - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console_handler.setFormatter(formatter); logger_global.addHandler(console_handler)
    logging.info("Đã thêm StreamHandler và áp dụng Filter.")
logging.info("Cấu hình logging hoàn tất.")

# --- In các đường dẫn và thông tin cấu hình quan trọng khi khởi động ---
# (Giữ nguyên phần logging thông tin cấu hình)
logging.info(f"BASE_DIR (config.py location): {BASE_DIR}")
# ... (các logging.info khác)
if BOT_TOKEN: logging.info(f"BOT_TOKEN đã được tải (...{BOT_TOKEN[-4:]})")

