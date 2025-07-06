# File: flashcard-telegram-bot/database/schema.py
"""
Module định nghĩa schema ban đầu cho database.
(Đã thêm cột notification_text vào bảng Flashcards,
 sử dụng hằng số từ config, thêm cột show_review_summary vào bảng Users,
 và thêm bảng CardReports).
(Sửa lần 1: Thêm cột image_path vào bảng FlashcardNotes).
(Sửa lần 2: Thêm các cột notification_target_set_id, enable_morning_brief, 
             last_morning_brief_sent_date vào bảng Users để hỗ trợ
             tính năng thông báo ôn tập theo bộ và lời chào buổi sáng).
"""
import logging
import sqlite3
from config import (
    DEFAULT_ADMIN_TELEGRAM_ID,
    DEFAULT_LEARNING_MODE,
    DEFAULT_TIMEZONE_OFFSET,
    DAILY_LIMIT_VIP,
    DAILY_LIMIT_USER
)

# Lấy logger theo tên module thay vì logger gốc
logger = logging.getLogger(__name__)

def database_initialize(conn):
    """
    Khởi tạo cấu trúc (schema) và dữ liệu ban đầu cho cơ sở dữ liệu.
    Đã thêm bảng CardReports.
    Sửa lần 1: Thêm cột image_path TEXT vào bảng FlashcardNotes.
    Sửa lần 2: Thêm các cột mới vào bảng Users cho cài đặt thông báo.

    Args:
        conn: Đối tượng kết nối sqlite3.Connection.
    """
    logger.info("Đang khởi tạo các bảng, index và dữ liệu mẫu cho database (sử dụng hằng số config)...")
    try:
        with conn:
            cursor = conn.cursor()
            logger.debug("Đang tạo các bảng...")

            # Bảng Users
            # Sửa lần 2: Thêm cột notification_target_set_id, enable_morning_brief, last_morning_brief_sent_date
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS Users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    current_set_id INTEGER,
                    default_side INTEGER DEFAULT 0,
                    daily_new_limit INTEGER DEFAULT {DAILY_LIMIT_USER},
                    user_role TEXT DEFAULT 'user',
                    timezone_offset INTEGER DEFAULT {DEFAULT_TIMEZONE_OFFSET},
                    username TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP,
                    score INTEGER DEFAULT 0,
                    password TEXT,
                    front_audio INTEGER DEFAULT 1,
                    back_audio INTEGER DEFAULT 1,
                    front_image_enabled INTEGER DEFAULT 1,
                    back_image_enabled INTEGER DEFAULT 1,
                    is_notification_enabled INTEGER DEFAULT 0,
                    notification_interval_minutes INTEGER DEFAULT 60,
                    last_notification_sent_time TIMESTAMP,
                    show_review_summary INTEGER DEFAULT 1,
                    current_mode TEXT DEFAULT '{DEFAULT_LEARNING_MODE}',
                    default_mode TEXT DEFAULT '{DEFAULT_LEARNING_MODE}',
                    notification_target_set_id INTEGER DEFAULT NULL,
                    enable_morning_brief INTEGER DEFAULT 1,
                    last_morning_brief_sent_date TEXT DEFAULT NULL,
                    FOREIGN KEY (notification_target_set_id) REFERENCES VocabularySets(set_id) ON DELETE SET NULL
                );
            ''')
            logger.debug("Đã tạo/kiểm tra bảng Users (có cột mới cho thông báo).")

            # Bảng VocabularySets
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS VocabularySets (
                    set_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    tags TEXT,
                    creator_user_id INTEGER,
                    creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_public INTEGER DEFAULT 1,
                    FOREIGN KEY (creator_user_id) REFERENCES Users(user_id) ON DELETE SET NULL
                );
            ''')
            logger.debug("Đã tạo/kiểm tra bảng VocabularySets.")

            # Bảng Flashcards
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Flashcards (
                    flashcard_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    set_id INTEGER NOT NULL,
                    front TEXT NOT NULL,
                    back TEXT NOT NULL,
                    front_audio_content TEXT,
                    back_audio_content TEXT,
                    front_img TEXT,
                    back_img TEXT,
                    notification_text TEXT,
                    FOREIGN KEY (set_id) REFERENCES VocabularySets(set_id) ON DELETE CASCADE
                );
            ''')
            logger.debug("Đã tạo/kiểm tra bảng Flashcards.")

            # Bảng UserFlashcardProgress
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS UserFlashcardProgress (
                    progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    flashcard_id INTEGER NOT NULL,
                    last_reviewed TIMESTAMP,
                    due_time TIMESTAMP,
                    review_count INTEGER DEFAULT 0,
                    learned_date DATE,
                    correct_streak INTEGER DEFAULT 0,
                    correct_count INTEGER DEFAULT 0,
                    incorrect_count INTEGER DEFAULT 0,
                    lapse_count INTEGER DEFAULT 0,
                    is_skipped INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (flashcard_id) REFERENCES Flashcards(flashcard_id) ON DELETE CASCADE
                );
            ''')
            logger.debug("Đã tạo/kiểm tra bảng UserFlashcardProgress.")

            # Bảng FlashcardNotes
            # Sửa lần 1: Thêm cột image_path TEXT
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS FlashcardNotes (
                    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    flashcard_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    image_path TEXT,
                    FOREIGN KEY (flashcard_id) REFERENCES Flashcards(flashcard_id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
                );
            ''')
            logger.debug("Đã tạo/kiểm tra bảng FlashcardNotes (có cột image_path).")

            # Bảng DailyReviewLog
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS DailyReviewLog (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    flashcard_id INTEGER NOT NULL,
                    set_id INTEGER,
                    review_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    response INTEGER NOT NULL,
                    score_change INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (flashcard_id) REFERENCES Flashcards(flashcard_id) ON DELETE CASCADE,
                    FOREIGN KEY (set_id) REFERENCES VocabularySets(set_id) ON DELETE SET NULL
                );
            ''')
            logger.debug("Đã tạo/kiểm tra bảng DailyReviewLog.")

            # Bảng CardReports
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS CardReports (
                    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    flashcard_id INTEGER NOT NULL,
                    reporter_user_id INTEGER NOT NULL,
                    creator_user_id INTEGER,
                    set_id INTEGER,
                    report_text TEXT,
                    reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    resolved_at TIMESTAMP,
                    resolver_user_id INTEGER,
                    FOREIGN KEY (flashcard_id) REFERENCES Flashcards(flashcard_id) ON DELETE CASCADE,
                    FOREIGN KEY (reporter_user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (creator_user_id) REFERENCES Users(user_id) ON DELETE SET NULL,
                    FOREIGN KEY (set_id) REFERENCES VocabularySets(set_id) ON DELETE SET NULL,
                    FOREIGN KEY (resolver_user_id) REFERENCES Users(user_id) ON DELETE SET NULL
                );
            ''')
            logger.debug("Đã tạo/kiểm tra bảng CardReports.")

            # Tạo Indexes
            logger.debug("Đang tạo các index...")
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON Users (telegram_id);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_users_username ON Users (username);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_users_score ON Users (score DESC);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_flashcards_set_id ON Flashcards (set_id);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_reviewlog_user_time ON DailyReviewLog (user_id, review_timestamp);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_reviewlog_set_user_time ON DailyReviewLog (set_id, user_id, review_timestamp);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_progress_user_card ON UserFlashcardProgress (user_id, flashcard_id);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_progress_user_due ON UserFlashcardProgress (user_id, due_time);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_progress_user_learned ON UserFlashcardProgress (user_id, learned_date);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_progress_user_incorrect ON UserFlashcardProgress (user_id, incorrect_count DESC);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_notes_card_user ON FlashcardNotes (flashcard_id, user_id);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_reports_card_status ON CardReports (flashcard_id, status);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_reports_creator_status ON CardReports (creator_user_id, status);''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_reports_set_status ON CardReports (set_id, status);''')
            logger.debug("Đã tạo/kiểm tra các index.")

            # Thêm admin và bộ từ mẫu
            default_user_telegram_id = DEFAULT_ADMIN_TELEGRAM_ID
            logger.debug(f"Đang kiểm tra và chèn người dùng admin mặc định (telegram_id: {default_user_telegram_id})")
            # Sửa lần 2: Thêm các cột mới với giá trị mặc định khi chèn admin
            cursor.execute(''' 
                INSERT OR IGNORE INTO Users (
                    telegram_id, username, user_role, daily_new_limit, score, 
                    current_mode, default_mode, timezone_offset,
                    notification_target_set_id, enable_morning_brief, last_morning_brief_sent_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, NULL) 
            ''', (default_user_telegram_id, 'default_admin', 'admin', DAILY_LIMIT_VIP, 0, 
                  DEFAULT_LEARNING_MODE, DEFAULT_LEARNING_MODE, DEFAULT_TIMEZONE_OFFSET))
            logger.debug("Đã thực thi INSERT OR IGNORE cho admin (với các cột thông báo mới).")
            
            cursor.execute("SELECT user_id FROM Users WHERE telegram_id = ?", (default_user_telegram_id,))
            admin_user_row = cursor.fetchone()
            admin_user_id = None
            if admin_user_row:
                try:
                    admin_user_id = admin_user_row['user_id']
                except (IndexError, TypeError):
                    admin_user_id = admin_user_row[0]
                logger.debug(f"Tìm thấy user_id của admin: {admin_user_id}")
            else:
                logger.error(f"Không thể tìm thấy user_id cho admin telegram_id {default_user_telegram_id} sau khi INSERT OR IGNORE!")

            if admin_user_id:
                sample_set_title = "Bộ từ mẫu: Màu sắc"
                sample_set_description = "Các màu sắc cơ bản bằng tiếng Anh và tiếng Việt."
                logger.debug(f"Kiểm tra và thêm bộ từ mẫu: '{sample_set_title}' (creator_user_id={admin_user_id})")
                cursor.execute("SELECT set_id FROM VocabularySets WHERE title = ?", (sample_set_title,))
                existing_set = cursor.fetchone()
                if existing_set is None:
                    logger.info(f"Bộ từ mẫu '{sample_set_title}' chưa tồn tại. Đang thêm...")
                    cursor.execute( """INSERT INTO VocabularySets (title, description, creator_user_id, is_public) VALUES (?, ?, ?, ?)""", (sample_set_title, sample_set_description, admin_user_id, 1) )
                    sample_set_id = cursor.lastrowid
                    logger.info(f"Đã thêm bộ từ mẫu với set_id: {sample_set_id}")
                    sample_flashcards = [
                        (sample_set_id, "Red", "Màu đỏ", "en:Red", "vi:Màu đỏ", None, None, None),
                        (sample_set_id, "Green", "Màu xanh lá cây", "en:Green", "vi:Màu xanh lá cây", None, None, None),
                        (sample_set_id, "Blue", "Màu xanh dương", "en:Blue", "vi:Màu xanh dương", None, None, None),
                        (sample_set_id, "Yellow", "Màu vàng", "en:Yellow", "vi:Màu vàng", None, None, None),
                        (sample_set_id, "Black", "Màu đen", "en:Black", "vi:Màu đen", None, None, None),
                        (sample_set_id, "White", "Màu trắng", "en:White", "vi:Màu trắng", None, None, None),
                        (sample_set_id, "Orange", "Màu cam", "en:Orange", "vi:Màu cam", None, None, None),
                        (sample_set_id, "Purple", "Màu tím", "en:Purple", "vi:Màu tím", None, None, None),
                    ]
                    logger.debug(f"Đang thêm {len(sample_flashcards)} flashcard mẫu cho set_id: {sample_set_id}")
                    cursor.executemany( """INSERT INTO Flashcards (set_id, front, back, front_audio_content, back_audio_content, front_img, back_img, notification_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", sample_flashcards )
                    logger.info(f"Đã thêm {len(sample_flashcards)} flashcard mẫu.")
                else:
                    existing_set_id_val = 0
                    try:
                        existing_set_id_val = existing_set['set_id']
                    except (IndexError, TypeError):
                        existing_set_id_val = existing_set[0] if existing_set else 0
                    if existing_set_id_val > 0:
                        logger.info(f"Bộ từ mẫu '{sample_set_title}' đã tồn tại (set_id: {existing_set_id_val}). Bỏ qua việc thêm dữ liệu mẫu.")
                    else:
                        logger.warning(f"Bộ từ mẫu '{sample_set_title}' tồn tại nhưng không lấy được set_id.")
            else:
                logger.warning("Không tìm thấy admin_user_id, không thể thêm bộ từ mẫu.")

        logger.info("Khởi tạo/Xác nhận database schema và dữ liệu ban đầu thành công.")
    except sqlite3.Error as e:
        logger.error(f"Lỗi SQLite trong quá trình khởi tạo database: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Lỗi không mong muốn trong quá trình khởi tạo database: {e}", exc_info=True)
        raise
