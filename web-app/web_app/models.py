# flashcard-web/web_app/models.py
from .db_instance import db  # ✅ Import db từ db_instance thay vì __init__
from sqlalchemy.dialects.sqlite import TIMESTAMP
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

# ========================== User ==========================
class User(db.Model):
    __tablename__ = 'Users'
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # BẮT ĐẦU THAY ĐỔI: telegram_id không còn là nullable=False
    telegram_id = db.Column(db.Integer, unique=True, nullable=True)
    # KẾT THÚC THAY ĐỔI
    current_set_id = db.Column(db.Integer, db.ForeignKey('VocabularySets.set_id', ondelete='SET NULL'))
    default_side = db.Column(db.Integer, default=0)
    daily_new_limit = db.Column(db.Integer, default=10)
    user_role = db.Column(db.String, default='user')
    timezone_offset = db.Column(db.Integer, default=7)
    username = db.Column(db.String, unique=True)
    created_at = db.Column(TIMESTAMP, default=func.current_timestamp())
    last_seen = db.Column(db.Integer)
    score = db.Column(db.Integer, default=0)
    password = db.Column(db.String)
    front_audio = db.Column(db.Integer, default=1)
    back_audio = db.Column(db.Integer, default=1)
    front_image_enabled = db.Column(db.Integer, default=1)
    back_image_enabled = db.Column(db.Integer, default=1)
    is_notification_enabled = db.Column(db.Integer, default=0)
    notification_interval_minutes = db.Column(db.Integer, default=60)
    last_notification_sent_time = db.Column(db.Integer)
    show_review_summary = db.Column(db.Integer, default=1)
    current_mode = db.Column(db.String, default='sequential_interspersed')
    default_mode = db.Column(db.String, default='sequential_interspersed')
    notification_target_set_id = db.Column(db.Integer, db.ForeignKey('VocabularySets.set_id', ondelete='SET NULL'))
    enable_morning_brief = db.Column(db.Integer, default=1)
    last_morning_brief_sent_date = db.Column(db.String)

    created_sets = db.relationship('VocabularySet', backref='creator', lazy=True, foreign_keys='VocabularySet.creator_user_id')
    progresses = db.relationship('UserFlashcardProgress', backref='user', lazy=True)
    notes = db.relationship('FlashcardNote', backref='user', lazy=True)

    def __repr__(self):
        # Mô tả: Trả về một chuỗi đại diện cho đối tượng User, hữu ích cho việc debug.
        return f"<User {self.username or self.telegram_id}>"

# ========================== VocabularySet ==========================
class VocabularySet(db.Model):
    __tablename__ = 'VocabularySets'
    set_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    tags = db.Column(db.String)
    creator_user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id', ondelete='SET NULL'))
    creation_date = db.Column(TIMESTAMP, default=func.current_timestamp())
    is_public = db.Column(db.Integer, default=1)

    flashcards = db.relationship('Flashcard', backref='vocabulary_set', lazy=True)
    users_using_as_current = db.relationship('User', backref='current_vocabulary_set', lazy=True, foreign_keys='User.current_set_id')
    users_receiving_notifications = db.relationship('User', backref='notification_target_set', lazy=True, foreign_keys='User.notification_target_set_id')

    def __repr__(self):
        # Mô tả: Trả về một chuỗi đại diện cho đối tượng VocabularySet.
        return f"<VocabularySet {self.title}>"

# ========================== Flashcard ==========================
class Flashcard(db.Model):
    __tablename__ = 'Flashcards'
    flashcard_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    set_id = db.Column(db.Integer, db.ForeignKey('VocabularySets.set_id', ondelete='CASCADE'), nullable=False)
    front = db.Column(db.String, nullable=False)
    back = db.Column(db.String, nullable=False)
    front_audio_content = db.Column(db.String)
    back_audio_content = db.Column(db.String)
    front_img = db.Column(db.String)
    back_img = db.Column(db.String)
    notification_text = db.Column(db.String)

    progresses = db.relationship('UserFlashcardProgress', backref='flashcard', lazy=True)
    notes = db.relationship('FlashcardNote', backref='flashcard', lazy=True)

    def __repr__(self):
        # Mô tả: Trả về một chuỗi đại diện cho đối tượng Flashcard.
        return f"<Flashcard {self.flashcard_id} - {self.front[:20]}>"

# ========================== UserFlashcardProgress ==========================
class UserFlashcardProgress(db.Model):
    __tablename__ = 'UserFlashcardProgress'
    progress_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id', ondelete='CASCADE'), nullable=False)
    flashcard_id = db.Column(db.Integer, db.ForeignKey('Flashcards.flashcard_id', ondelete='CASCADE'), nullable=False)
    last_reviewed = db.Column(db.Integer)
    due_time = db.Column(db.Integer)
    review_count = db.Column(db.Integer, default=0)
    learned_date = db.Column(db.Integer)
    correct_streak = db.Column(db.Integer, default=0)
    correct_count = db.Column(db.Integer, default=0)
    incorrect_count = db.Column(db.Integer, default=0)
    lapse_count = db.Column(db.Integer, default=0)
    is_skipped = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint('user_id', 'flashcard_id', name='_user_flashcard_uc'),)

    def __repr__(self):
        # Mô tả: Trả về một chuỗi đại diện cho đối tượng UserFlashcardProgress.
        return f"<Progress User:{self.user_id} Card:{self.flashcard_id} Due:{self.due_time}>"

# ========================== FlashcardNote ==========================
class FlashcardNote(db.Model):
    __tablename__ = 'FlashcardNotes'
    note_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    flashcard_id = db.Column(db.Integer, db.ForeignKey('Flashcards.flashcard_id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id', ondelete='CASCADE'), nullable=False)
    # Mô tả: Định nghĩa cột 'note' để lưu nội dung ghi chú.
    # Đã sửa lỗi cú pháp: thêm kiểu dữ liệu db.Text cho cột.
    note = db.Column(db.Text)

    def __repr__(self):
        # Mô tả: Trả về một chuỗi đại diện cho đối tượng FlashcardNote.
        return f"<Note ID:{self.note_id} Card:{self.flashcard_id} User:{self.user_id}>"
