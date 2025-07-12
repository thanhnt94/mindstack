# flashcard-web/web_app/models.py
from .db_instance import db
from sqlalchemy.dialects.sqlite import TIMESTAMP
from sqlalchemy import func
import logging
from .config import DEFAULT_QUIZ_MODE

logger = logging.getLogger(__name__)

# ========================== User ==========================
class User(db.Model):
    __tablename__ = 'Users'
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    telegram_id = db.Column(db.Integer, unique=True, nullable=True)
    current_set_id = db.Column(db.Integer, db.ForeignKey('VocabularySets.set_id', ondelete='SET NULL'))
    current_question_set_id = db.Column(db.Integer, db.ForeignKey('QuestionSets.set_id', ondelete='SET NULL'))
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
    current_quiz_mode = db.Column(db.String, default=DEFAULT_QUIZ_MODE)
    default_mode = db.Column(db.String, default='sequential_interspersed')
    notification_target_set_id = db.Column(db.Integer, db.ForeignKey('VocabularySets.set_id', ondelete='SET NULL'))
    enable_morning_brief = db.Column(db.Integer, default=1)
    last_morning_brief_sent_date = db.Column(db.String)

    created_sets = db.relationship('VocabularySet', backref='creator', lazy=True, foreign_keys='VocabularySet.creator_user_id')
    progresses = db.relationship('UserFlashcardProgress', backref='user', lazy=True, cascade="all, delete-orphan")
    notes = db.relationship('FlashcardNote', backref='user', lazy=True, cascade="all, delete-orphan")
    score_logs = db.relationship('ScoreLog', backref='user', lazy=True, cascade="all, delete-orphan")
    created_question_sets = db.relationship('QuestionSet', backref='creator', lazy=True, foreign_keys='QuestionSet.creator_user_id')
    quiz_progresses = db.relationship('UserQuizProgress', backref='user', lazy=True, cascade="all, delete-orphan")
    quiz_notes = db.relationship('QuizQuestionNote', backref='user', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
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

    flashcards = db.relationship('Flashcard', backref='vocabulary_set', lazy=True, cascade="all, delete-orphan")
    users_using_as_current = db.relationship('User', backref='current_vocabulary_set', lazy=True, foreign_keys='User.current_set_id')
    users_receiving_notifications = db.relationship('User', backref='notification_target_set', lazy=True, foreign_keys='User.notification_target_set_id')

    def __repr__(self):
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

    progresses = db.relationship('UserFlashcardProgress', backref='flashcard', lazy=True, cascade="all, delete-orphan")
    notes = db.relationship('FlashcardNote', backref='flashcard', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
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
        return f"<Progress User:{self.user_id} Card:{self.flashcard_id} Due:{self.due_time}>"

# ========================== FlashcardNote ==========================
class FlashcardNote(db.Model):
    __tablename__ = 'FlashcardNotes'
    note_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    flashcard_id = db.Column(db.Integer, db.ForeignKey('Flashcards.flashcard_id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id', ondelete='CASCADE'), nullable=False)
    note = db.Column(db.Text)

    def __repr__(self):
        return f"<Note ID:{self.note_id} Card:{self.flashcard_id} User:{self.user_id}>"

# ========================== ScoreLog ==========================
class ScoreLog(db.Model):
    __tablename__ = 'ScoreLogs'
    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id', ondelete='CASCADE'), nullable=False)
    score_change = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String)
    source_type = db.Column(db.String(50)) # flashcard, quiz, etc.

    def __repr__(self):
        return f"<ScoreLog User:{self.user_id} Change:{self.score_change}>"

# ========================== QuestionSet ==========================
class QuestionSet(db.Model):
    __tablename__ = 'QuestionSets'
    set_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    creator_user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id', ondelete='SET NULL'))
    creation_date = db.Column(TIMESTAMP, default=func.current_timestamp())
    is_public = db.Column(db.Integer, default=1)

    questions = db.relationship('QuizQuestion', backref='question_set', lazy=True, cascade="all, delete-orphan")
    users_using_as_current = db.relationship('User', backref='current_question_set', lazy=True, foreign_keys='User.current_question_set_id')

    def __repr__(self):
        return f"<QuestionSet {self.title}>"

# ========================== QuizQuestion ==========================
class QuizQuestion(db.Model):
    __tablename__ = 'QuizQuestions'
    question_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    set_id = db.Column(db.Integer, db.ForeignKey('QuestionSets.set_id', ondelete='CASCADE'), nullable=False)
    pre_question_text = db.Column(db.Text)
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String, nullable=False)
    option_b = db.Column(db.String, nullable=False)
    option_c = db.Column(db.String, nullable=False)
    option_d = db.Column(db.String, nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False) # 'A', 'B', 'C', 'D'
    guidance = db.Column(db.Text)
    question_image_file = db.Column(db.String)
    question_audio_file = db.Column(db.String)

    progresses = db.relationship('UserQuizProgress', backref='question', lazy=True, cascade="all, delete-orphan")
    notes = db.relationship('QuizQuestionNote', backref='question', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<QuizQuestion {self.question_id} - {self.question[:20]}>"

# ========================== UserQuizProgress ==========================
class UserQuizProgress(db.Model):
    __tablename__ = 'UserQuizProgress'
    progress_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id', ondelete='CASCADE'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('QuizQuestions.question_id', ondelete='CASCADE'), nullable=False)
    
    last_answered = db.Column(db.Integer)
    times_correct = db.Column(db.Integer, default=0, nullable=False)
    times_incorrect = db.Column(db.Integer, default=0, nullable=False)
    # --- BẮT ĐẦU THÊM MỚI ---
    correct_streak = db.Column(db.Integer, default=0, nullable=False)
    # --- KẾT THÚC THÊM MỚI ---
    is_mastered = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'question_id', name='_user_question_uc'),)

    def __repr__(self):
        return f"<UserQuizProgress User:{self.user_id} Question:{self.question_id}>"

# ========================== QuizQuestionNote ==========================
class QuizQuestionNote(db.Model):
    __tablename__ = 'QuizQuestionNotes'
    note_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    question_id = db.Column(db.Integer, db.ForeignKey('QuizQuestions.question_id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id', ondelete='CASCADE'), nullable=False)
    note = db.Column(db.Text)

    __table_args__ = (db.UniqueConstraint('user_id', 'question_id', name='_user_question_note_uc'),)

    def __repr__(self):
        return f"<QuizNote ID:{self.note_id} Question:{self.question_id} User:{self.user_id}>"
