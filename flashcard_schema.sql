--- Bảng: CardReports
CREATE TABLE CardReports (report_id INTEGER PRIMARY KEY AUTOINCREMENT, flashcard_id INTEGER NOT NULL, reporter_user_id INTEGER NOT NULL, creator_user_id INTEGER, set_id INTEGER, report_text TEXT, reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'pending', resolved_at TIMESTAMP, resolver_user_id INTEGER, FOREIGN KEY (flashcard_id) REFERENCES Flashcards (flashcard_id) ON DELETE CASCADE, FOREIGN KEY (reporter_user_id) REFERENCES Users (user_id) ON DELETE CASCADE, FOREIGN KEY (creator_user_id) REFERENCES Users (user_id) ON DELETE SET NULL, FOREIGN KEY (set_id) REFERENCES VocabularySets (set_id) ON DELETE SET NULL, FOREIGN KEY (resolver_user_id) REFERENCES Users (user_id) ON DELETE SET NULL);

--- Bảng: DailyReviewLog
CREATE TABLE "DailyReviewLog" ( "log_id" INTEGER PRIMARY KEY AUTOINCREMENT, "user_id" INTEGER NOT NULL, "flashcard_id" INTEGER NOT NULL, "set_id" INTEGER, "review_timestamp" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "response" INTEGER NOT NULL, "score_change" INTEGER DEFAULT 0, FOREIGN KEY ("user_id") REFERENCES "Users"("user_id") ON DELETE CASCADE, FOREIGN KEY ("flashcard_id") REFERENCES "Flashcards"("flashcard_id") ON DELETE CASCADE, FOREIGN KEY ("set_id") REFERENCES "VocabularySets"("set_id") ON DELETE SET NULL );

--- Bảng: FlashcardNotes
CREATE TABLE "FlashcardNotes" ( "note_id" INTEGER PRIMARY KEY AUTOINCREMENT, "flashcard_id" INTEGER NOT NULL, "user_id" INTEGER NOT NULL, "note" TEXT, "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP, image_path TEXT, FOREIGN KEY ("flashcard_id") REFERENCES "Flashcards"("flashcard_id") ON DELETE CASCADE, FOREIGN KEY ("user_id") REFERENCES "Users"("user_id") ON DELETE CASCADE );

--- Bảng: Flashcards
CREATE TABLE "Flashcards" ( "flashcard_id" INTEGER PRIMARY KEY AUTOINCREMENT, "set_id" INTEGER NOT NULL, "front" TEXT NOT NULL, "back" TEXT NOT NULL, "front_audio_content" TEXT, "back_audio_content" TEXT, "front_img" TEXT, "back_img" TEXT, "notification_text" TEXT, FOREIGN KEY ("set_id") REFERENCES "VocabularySets"("set_id") ON DELETE CASCADE );

--- Bảng: UserFlashcardProgress
CREATE TABLE "UserFlashcardProgress" ( "progress_id" INTEGER PRIMARY KEY AUTOINCREMENT, "user_id" INTEGER NOT NULL, "flashcard_id" INTEGER NOT NULL, "last_reviewed" TIMESTAMP, "due_time" TIMESTAMP, "review_count" INTEGER DEFAULT 0, "learned_date" DATE, "correct_streak" INTEGER DEFAULT 0, "correct_count" INTEGER DEFAULT 0, "incorrect_count" INTEGER DEFAULT 0, "lapse_count" INTEGER DEFAULT 0, "is_skipped" INTEGER DEFAULT 0, FOREIGN KEY ("user_id") REFERENCES "Users"("user_id") ON DELETE CASCADE, FOREIGN KEY ("flashcard_id") REFERENCES "Flashcards"("flashcard_id") ON DELETE CASCADE );

--- Bảng: Users
CREATE TABLE "Users" (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER UNIQUE,
                current_set_id INTEGER, default_side INTEGER DEFAULT 0,
                daily_new_limit INTEGER DEFAULT 10, user_role TEXT DEFAULT 'user',
                timezone_offset INTEGER DEFAULT 7, username TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_seen TIMESTAMP, score INTEGER DEFAULT 0,
                password TEXT, front_audio INTEGER DEFAULT 1, back_audio INTEGER DEFAULT 1,
                front_image_enabled INTEGER DEFAULT 1, back_image_enabled INTEGER DEFAULT 1,
                is_notification_enabled INTEGER DEFAULT 0, notification_interval_minutes INTEGER DEFAULT 60,
                last_notification_sent_time TIMESTAMP, current_mode TEXT DEFAULT 'sequential_interspersed',
                default_mode TEXT DEFAULT 'sequential_interspersed'
            , "show_review_summary" INTEGER DEFAULT 1, notification_target_set_id INTEGER DEFAULT NULL REFERENCES VocabularySets(set_id) ON DELETE SET NULL, enable_morning_brief INTEGER DEFAULT 1, last_morning_brief_sent_date TEXT DEFAULT NULL);

--- Bảng: VocabularySets
CREATE TABLE "VocabularySets" ( "set_id" INTEGER PRIMARY KEY AUTOINCREMENT, "title" TEXT NOT NULL, "description" TEXT, "tags" TEXT, "creator_user_id" INTEGER, "creation_date" TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "is_public" INTEGER DEFAULT 1, FOREIGN KEY ("creator_user_id") REFERENCES "Users"("user_id") ON DELETE SET NULL );

