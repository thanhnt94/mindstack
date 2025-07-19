# web_app/routes/flashcard.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, request
import logging
import json
from sqlalchemy import func
from ..services import learning_logic_service, stats_service, note_service
from ..models import db, User, VocabularySet, Flashcard, UserFlashcardProgress
from ..config import LEARNING_MODE_DISPLAY_NAMES, MODE_AUTOPLAY_REVIEW, SETS_PER_PAGE, MODE_NEW_CARDS_ONLY, MODE_SEQUENTIAL_LEARNING, MODE_REVIEW_ALL_DUE, MODE_REVIEW_HARDEST
from .decorators import login_required

flashcard_bp = Blueprint('flashcard', __name__)
logger = logging.getLogger(__name__)

# BẮT ĐẦU THÊM MỚI: Lớp CustomPagination để phân trang thủ công
class CustomPagination:
    def __init__(self, page, per_page, total, items):
        self.page = page
        self.per_page = per_page
        self.total = total
        self.items = items
        self.pages = (total + per_page - 1) // per_page
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1
        self.next_num = page + 1
    
    def iter_pages(self, left_edge=1, right_edge=1, left_current=1, right_current=2):
        last_page = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last_page + 1 != num:
                    yield None
                yield num
                last_page = num
# KẾT THÚC THÊM MỚI

# BẮT ĐẦU THÊM MỚI: Hàm sắp xếp tùy chỉnh cho các bộ
def _sort_sets_by_progress(set_items, total_key, completed_key):
    """
    Mô tả: Sắp xếp danh sách các bộ (Flashcard Sets hoặc Question Sets) dựa trên tiến độ hoàn thành.
           Các bộ có phần trăm hoàn thành cao nhất sẽ được đưa lên đầu.
           Các bộ đã hoàn thành 100% sẽ được đưa xuống cuối danh sách.
           Nếu phần trăm hoàn thành bằng nhau, sẽ sắp xếp theo tiêu đề (alphabet).

    Args:
        set_items (list): Danh sách các đối tượng bộ.
        total_key (str): Tên thuộc tính chứa tổng số mục trong bộ.
        completed_key (str): Tên thuộc tính chứa số mục đã hoàn thành.

    Returns:
        list: Danh sách các bộ đã được sắp xếp.
    """
    def custom_sort_key(set_item):
        total = getattr(set_item, total_key, 0)
        completed = getattr(set_item, completed_key, 0)
        title = getattr(set_item, 'title', '')

        if total == 0:
            # Đặt các bộ không có mục nào xuống cuối cùng
            return (float('-inf'), title) 

        percentage = (completed * 100 / total)

        if percentage == 100:
            # Đặt các bộ đã hoàn thành 100% xuống cuối cùng
            return (0, title) 
        
        # Sắp xếp giảm dần theo phần trăm (sử dụng -percentage)
        # Nếu phần trăm bằng nhau, sắp xếp tăng dần theo title
        return (-percentage, title)

    return sorted(set_items, key=custom_sort_key)
# KẾT THÚC THÊM MỚI

def _serialize_flashcard(flashcard_obj):
    """
    Mô tả: Chuyển đổi đối tượng flashcard thành một dictionary để sử dụng trong JSON.
    Hàm này đảm bảo rằng chỉ các dữ liệu cần thiết được gửi xuống client.
    Args:
        flashcard_obj (Flashcard): Đối tượng flashcard từ model.
    Returns:
        dict: Một dictionary chứa các thuộc tính của flashcard.
    """
    if not flashcard_obj: return {}
    return {
        'flashcard_id': flashcard_obj.flashcard_id, 'front': flashcard_obj.front,
        'back': flashcard_obj.back, 'front_audio_content': flashcard_obj.front_audio_content,
        'back_audio_content': flashcard_obj.back_audio_content, 'front_img': flashcard_obj.front_img,
        'back_img': flashcard_obj.back_img, 'notification_text': flashcard_obj.notification_text,
        'set_id': flashcard_obj.set_id
    }

@flashcard_bp.route('/')
@login_required
def index():
    """
    Mô tả: Hiển thị trang chính cho phép người dùng chọn bộ thẻ để học.
    Phân trang các bộ thẻ đã học và các bộ thẻ mới.
    """
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    page_started = request.args.get('page_started', 1, type=int)
    page_new = request.args.get('page_new', 1, type=int)

    progressed_set_ids_query = db.session.query(Flashcard.set_id)\
        .join(UserFlashcardProgress)\
        .filter(UserFlashcardProgress.user_id == user_id)\
        .distinct()
    progressed_set_ids = {row[0] for row in progressed_set_ids_query.all()}

    started_sets_raw = VocabularySet.query.filter(VocabularySet.set_id.in_(progressed_set_ids)).all()

    started_sets_with_progress = []
    if started_sets_raw:
        set_ids = [s.set_id for s in started_sets_raw]
        
        total_cards_map = dict(db.session.query(Flashcard.set_id, func.count(Flashcard.flashcard_id))\
            .filter(Flashcard.set_id.in_(set_ids)).group_by(Flashcard.set_id).all())
            
        # BẮT ĐẦU SỬA LỖI: Đếm số thẻ duy nhất đã học (có learned_date)
        learned_cards_map = dict(db.session.query(Flashcard.set_id, func.count(db.distinct(UserFlashcardProgress.flashcard_id)))\
            .join(Flashcard).filter(UserFlashcardProgress.user_id == user_id, Flashcard.set_id.in_(set_ids), UserFlashcardProgress.learned_date.isnot(None))\
            .group_by(Flashcard.set_id).all())
        # KẾT THÚC SỬA LỖI

        for set_item in started_sets_raw:
            set_item.total_cards = total_cards_map.get(set_item.set_id, 0)
            set_item.learned_cards = learned_cards_map.get(set_item.set_id, 0)
            started_sets_with_progress.append(set_item)

    # BẮT ĐẦU SỬA LỖI VÀ TỐI ƯU: Sử dụng hàm sắp xếp chung và tạo đối tượng Pagination thủ công
    # Sắp xếp tùy chỉnh: Phần trăm cao nhất lên đầu, 100% xuống cuối
    # Sử dụng hàm _sort_sets_by_progress đã định nghĩa ở trên
    sorted_started_sets = _sort_sets_by_progress(started_sets_with_progress, 
                                                total_key='total_cards', 
                                                completed_key='learned_cards')

    # Phân trang thủ công sau khi sắp xếp
    total_items_started = len(sorted_started_sets)
    start_index_started = (page_started - 1) * SETS_PER_PAGE
    end_index_started = start_index_started + SETS_PER_PAGE
    paginated_started_sets_items = sorted_started_sets[start_index_started:end_index_started]

    started_sets_pagination = CustomPagination(
        page_started, SETS_PER_PAGE, total_items_started, paginated_started_sets_items
    )
    # KẾT THÚC SỬA LỖI VÀ TỐI ƯU

    # BẮT ĐẦU THAY ĐỔI: Sắp xếp bộ mới theo alphabet
    new_sets_query = VocabularySet.query.filter(VocabularySet.is_public == 1, VocabularySet.set_id.notin_(progressed_set_ids))\
        .order_by(VocabularySet.title.asc()) # Sắp xếp theo alphabet
    new_sets_pagination = new_sets_query.paginate(page=page_new, per_page=SETS_PER_PAGE, error_out=False)
    # KẾT THÚC THAY ĐỔI
    
    return render_template('flashcard/select_set.html', 
                           user=user, 
                           started_sets_pagination=started_sets_pagination,
                           new_sets_pagination=new_sets_pagination)

@flashcard_bp.route('/go-to-learn')
@login_required
def go_to_learn_page():
    """
    Mô tả: Chuyển hướng người dùng đến trang học của bộ thẻ hiện tại của họ.
    Nếu không có bộ thẻ hiện tại, chuyển hướng đến trang chọn bộ thẻ.
    """
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if user and user.current_set_id:
        logger.info(f"User {user_id} is going to current set {user.current_set_id}")
        return redirect(url_for('flashcard.learn_set', set_id=user.current_set_id))
    else:
        logger.info(f"User {user_id} has no current set, going to index.")
        return redirect(url_for('flashcard.index'))

# BẮT ĐẦU XÓA: Di chuyển route dashboard sang main.py
# @flashcard_bp.route('/dashboard')
# @login_required
# def dashboard():
#     """
#     Mô tả: Hiển thị trang thống kê (dashboard) cho người dùng.
#     """
#     user_id = session.get('user_id')
#     user = User.query.get(user_id)
#     dashboard_data = stats_service.get_dashboard_stats(user_id)
#     if not dashboard_data:
#         flash("Không thể tải dữ liệu thống kê.", "error")
#         return redirect(url_for('flashcard.index'))
#     dashboard_data_json = json.dumps(dashboard_data)
    
#     # BẮT ĐẦU THAY ĐỔI: Truyền current_question_set_id
#     current_question_set_id = user.current_question_set_id if user else None

#     # BẮT ĐẦU THÊM MỚI: Lấy dữ liệu bảng xếp hạng cho dashboard người dùng
#     # Lấy tham số sort_by và timeframe từ request, mặc định là 'total_score' và 'all_time'
#     sort_by = request.args.get('sort_by', 'total_score')
#     timeframe = request.args.get('timeframe', 'all_time')
    
#     leaderboard_data = stats_service.get_user_leaderboard_data(
#         sort_by=sort_by,
#         timeframe=timeframe,
#         limit=10 # Giới hạn 10 người dùng hàng đầu cho bảng xếp hạng
#     )
#     # KẾT THÚC THÊM MỚI

#     return render_template(
#         'dashboard.html', 
#         dashboard_data=dashboard_data,
#         dashboard_data_json=dashboard_data_json,
#         current_set_id=user.current_set_id,
#         current_question_set_id=current_question_set_id,
#         # BẮT ĐẦU THÊM MỚI: Truyền dữ liệu bảng xếp hạng vào template
#         leaderboard_data=leaderboard_data,
#         current_sort_by=sort_by,
#         current_timeframe=timeframe
#         # KẾT THÚC THÊM MỚI
#     )
# KẾT THÚC XÓA: Di chuyển route dashboard sang main.py

def _check_edit_permission(user, flashcard_obj):
    """
    Mô tả: Kiểm tra xem người dùng có quyền sửa một flashcard cụ thể hay không.
    Args:
        user (User): Đối tượng người dùng.
        flashcard_obj (Flashcard): Đối tượng flashcard.
    Returns:
        bool: True nếu có quyền, False nếu không.
    """
    if not user or not flashcard_obj:
        return False
    set_creator_id = flashcard_obj.vocabulary_set.creator_user_id
    return user.user_role == 'admin' or user.user_id == set_creator_id

@flashcard_bp.route('/learn/<int:set_id>')
@login_required
def learn_set(set_id):
    """
    Mô tả: Hiển thị thẻ tiếp theo để học trong một bộ thẻ cụ thể.
    """
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    selected_set = VocabularySet.query.get_or_404(set_id)
    
    user.current_set_id = set_id
    db.session.commit()

    flashcard_obj, progress_obj, wait_time_ts = learning_logic_service.get_next_card_for_review(user_id, set_id, user.current_mode)

    if not flashcard_obj:
        return render_template('flashcard/no_cards_message.html', set_id=set_id, wait_time_ts=wait_time_ts)

    session['current_progress_id'] = progress_obj.progress_id
    
    audio_url = url_for('api.get_card_audio', flashcard_id=flashcard_obj.flashcard_id, side='front') if flashcard_obj.front_audio_content else None
    
    # BẮT ĐẦU THAY ĐỔI: Lấy context_stats đầy đủ hơn
    context_stats = stats_service.get_user_stats_for_context(user_id, set_id)
    # KẾT THÚC THAY ĐỔI
    
    user_audio_settings = {'front_audio_enabled': user.front_audio == 1, 'back_audio_enabled': user.back_audio == 1}
    
    can_edit = _check_edit_permission(user, flashcard_obj)
    
    # --- BẮT ĐẦU THAY ĐỔI: Kiểm tra xem thẻ có ghi chú không ---
    note = note_service.get_note_by_flashcard_id(user_id, flashcard_obj.flashcard_id)
    has_note = note is not None
    # KẾT THÚC THAY ĐỔI ---

    return render_template(
        'flashcard/learn_card.html', user=user, flashcard=flashcard_obj, progress=progress_obj,
        context_stats=context_stats, is_front=True,
        flashcard_json_string=json.dumps(_serialize_flashcard(flashcard_obj)),
        user_audio_settings_json_string=json.dumps(user_audio_settings),
        is_autoplay_mode=(user.current_mode == MODE_AUTOPLAY_REVIEW),
        audio_url=audio_url, has_back_audio_content=bool(flashcard_obj.back_audio_content),
        can_edit=can_edit,
        has_note=has_note, # Truyền biến mới vào template
        # BẮT ĐẦU THÊM MỚI: Truyền các biến cần thiết cho Dynamic Island
        current_mode=user.current_mode,
        set_total_cards=context_stats['set_total_cards'],
        set_learned_cards=context_stats['set_learned_cards'],
        set_mastered_cards=context_stats['set_mastered_cards'],
        set_due_cards=context_stats['set_due_cards'] # THÊM MỚI: Truyền set_due_cards
        # KẾT THÚM THÊM MỚI
    )

@flashcard_bp.route('/flip/<int:progress_id>')
@login_required
def flip_card(progress_id):
    """
    Mô tả: Hiển thị mặt sau của một flashcard.
    """
    progress = UserFlashcardProgress.query.get_or_404(progress_id)
    if progress.user_id != session.get('user_id'):
        flash("Thẻ không hợp lệ.", "error")
        return redirect(url_for('flashcard.index'))

    user = User.query.get(session.get('user_id'))
    flashcard_obj = progress.flashcard
    
    audio_url = url_for('api.get_card_audio', flashcard_id=flashcard_obj.flashcard_id, side='back') if flashcard_obj.back_audio_content else None
    
    # BẮT ĐẦU THAY ĐỔI: Lấy context_stats đầy đủ hơn
    context_stats = stats_service.get_user_stats_for_context(user.user_id, flashcard_obj.set_id)
    # KẾT THÚC THAY ĐỔI
    
    user_audio_settings = {'front_audio_enabled': user.front_audio == 1, 'back_audio_enabled': user.back_audio == 1}

    can_edit = _check_edit_permission(user, flashcard_obj)
    
    # --- BẮT ĐẦU THAY ĐỔI: Kiểm tra xem thẻ có ghi chú không ---
    note = note_service.get_note_by_flashcard_id(user.user_id, flashcard_obj.flashcard_id)
    has_note = note is not None
    # --- KẾT THÚC THAY ĐỔI ---

    return render_template(
        'flashcard/learn_card.html', user=user, flashcard=flashcard_obj, progress=progress,
        context_stats=context_stats, is_front=False,
        flashcard_json_string=json.dumps(_serialize_flashcard(flashcard_obj)),
        user_audio_settings_json_string=json.dumps(user_audio_settings),
        is_autoplay_mode=(user.current_mode == MODE_AUTOPLAY_REVIEW),
        audio_url=audio_url, has_back_audio_content=bool(flashcard_obj.back_audio_content),
        can_edit=can_edit,
        has_note=has_note, # Truyền biến mới vào template
        # BẮT ĐẦU THÊM MỚI: Truyền các biến cần thiết cho Dynamic Island
        current_mode=user.current_mode,
        set_total_cards=context_stats['set_total_cards'],
        set_learned_cards=context_stats['set_learned_cards'],
        set_mastered_cards=context_stats['set_mastered_cards'],
        set_due_cards=context_stats['set_due_cards'] # THÊM MỚI: Truyền set_due_cards
        # KẾT THÚC THÊM MỚI
    )

@flashcard_bp.route('/rate/<int:progress_id>/<string:response_str>')
@login_required
def rate_card(progress_id, response_str):
    """
    Mô tả: Xử lý đánh giá của người dùng cho một thẻ và chuyển đến thẻ tiếp theo.
    """
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    progress = UserFlashcardProgress.query.get(progress_id)
    
    if not progress or progress.user_id != user_id:
        flash("Thẻ không hợp lệ.", "error")
        return redirect(url_for('flashcard.index'))

    current_set_id = progress.flashcard.set_id

    if user.current_mode == MODE_AUTOPLAY_REVIEW and response_str == 'next':
        return redirect(url_for('flashcard.learn_set', set_id=current_set_id))

    response_mapping = {'forget': -1, 'vague': 0, 'remember': 1, 'continue': 2}
    response = response_mapping.get(response_str)

    if response is not None:
        learning_logic_service.process_review_response(user_id, progress_id, response)
    else:
        flash("Phản hồi không hợp lệ.", "error")

    return redirect(url_for('flashcard.learn_set', set_id=current_set_id))

@flashcard_bp.route('/select_mode')
@login_required
def select_mode():
    """
    Mô tả: Hiển thị trang cho phép người dùng chọn chế độ học.
    """
    user = User.query.get(session.get('user_id'))
    return render_template('flashcard/select_mode.html', modes=LEARNING_MODE_DISPLAY_NAMES, current_mode=user.current_mode)

@flashcard_bp.route('/set_learning_mode/<string:mode_code>')
@login_required
def set_learning_mode(mode_code):
    """
    Mô tả: Cập nhật chế độ học của người dùng và chuyển hướng họ.
    """
    if mode_code not in LEARNING_MODE_DISPLAY_NAMES:
        flash("Chế độ học không hợp lệ.", "error")
        return redirect(url_for('flashcard.select_mode'))
    
    user = User.query.get(session.get('user_id'))
    user.current_mode = mode_code
    db.session.commit()
    flash(f"Chế độ học đã được thay đổi thành '{LEARNING_MODE_DISPLAY_NAMES[mode_code]}'.", "success")
    
    current_set_id = user.current_set_id 
    
    if current_set_id:
        return redirect(url_for('flashcard.learn_set', set_id=current_set_id))
    return redirect(url_for('flashcard.index'))

@flashcard_bp.route('/select_set_page')
@login_required
def select_set_page():
    """
    Mô tả: Một route tiện ích để chuyển hướng về trang chọn bộ thẻ.
    """
    return redirect(url_for('flashcard.index'))
