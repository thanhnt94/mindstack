# web-app/backfill_scores.py
import os
import sys
import logging
from datetime import datetime, timedelta, timezone

# Thiết lập để import từ thư mục gốc
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import các thành phần cần thiết
from web_app import create_app, db
from web_app.models import User, UserFlashcardProgress, ScoreLog
from web_app.config import SCORE_INCREASE_CORRECT, SCORE_INCREASE_NEW_CARD

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='[BACKFILL_SCRIPT] %(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backfill_score_data():
    """
    Tái tạo dữ liệu điểm số cũ dựa trên lịch sử ôn tập.
    Đảm bảo tổng điểm tái tạo khớp với điểm hiện tại.
    Chỉ chạy một lần sau khi thêm bảng ScoreLogs.
    """
    app = create_app()
    with app.app_context():
        logger.info("Bắt đầu quá trình tái tạo dữ liệu điểm số...")

        if ScoreLog.query.first():
            logger.warning("Bảng ScoreLogs đã có dữ liệu. Bỏ qua quá trình tái tạo.")
            return

        all_users = User.query.all()
        if not all_users:
            logger.info("Không có người dùng nào trong hệ thống. Kết thúc.")
            return

        total_logs_to_add = []
        for user in all_users:
            logger.info(f"Đang xử lý cho người dùng: {user.username or user.user_id} (Điểm hiện tại: {user.score})")
            
            explained_score = 0
            logs_for_this_user = []
            
            # Lấy tất cả tiến trình của người dùng
            user_progresses = UserFlashcardProgress.query.filter_by(user_id=user.user_id).all()

            for progress in user_progresses:
                # 1. Điểm học thẻ mới
                if progress.learned_date:
                    score = SCORE_INCREASE_NEW_CARD
                    explained_score += score
                    logs_for_this_user.append(ScoreLog(
                        user_id=user.user_id,
                        score_change=score,
                        timestamp=progress.learned_date,
                        reason='backfill_new_card'
                    ))

                # 2. Điểm ôn tập (giả định tất cả đều đúng)
                review_sessions_after_first = progress.review_count - 1
                if review_sessions_after_first > 0 and progress.last_reviewed:
                    score = review_sessions_after_first * SCORE_INCREASE_CORRECT
                    explained_score += score
                    logs_for_this_user.append(ScoreLog(
                        user_id=user.user_id,
                        score_change=score,
                        timestamp=progress.last_reviewed,
                        reason='backfill_review_sessions'
                    ))
            
            # 3. Tính toán và tạo bản ghi hiệu chỉnh
            discrepancy = (user.score or 0) - explained_score
            if discrepancy != 0:
                logger.info(f"  - Điểm đã giải thích: {explained_score}, Chênh lệch: {discrepancy}. Tạo bản ghi hiệu chỉnh.")
                logs_for_this_user.append(ScoreLog(
                    user_id=user.user_id,
                    score_change=discrepancy,
                    timestamp=int(user.created_at.timestamp()),
                    reason='backfill_adjustment'
                ))
            
            total_logs_to_add.extend(logs_for_this_user)

        if total_logs_to_add:
            logger.info(f"Chuẩn bị thêm {len(total_logs_to_add)} bản ghi log điểm ước tính vào database.")
            db.session.bulk_save_objects(total_logs_to_add)
            db.session.commit()
            logger.info("Tái tạo dữ liệu điểm số thành công!")
        else:
            logger.info("Không có log điểm nào được tạo.")

if __name__ == '__main__':
    backfill_score_data()
