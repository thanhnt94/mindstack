# web_app/services/set_service.py
import logging
import openpyxl
import io
from ..models import db, VocabularySet, User, Flashcard

logger = logging.getLogger(__name__)

class SetService:
    """
    Mô tả: Lớp chứa các hàm xử lý logic nghiệp vụ liên quan đến bộ thẻ (VocabularySet).
    """
    def __init__(self):
        pass

    def get_all_sets_with_details(self):
        """
        Mô tả: Lấy tất cả các bộ thẻ cùng với thông tin chi tiết như người tạo và số lượng thẻ.
        Returns:
            list: Danh sách các đối tượng VocabularySet, mỗi đối tượng đã được bổ sung thông tin.
        """
        log_prefix = "[SET_SERVICE|GetAllSets]"
        logger.info(f"{log_prefix} Bắt đầu lấy danh sách tất cả bộ thẻ.")
        try:
            sets = db.session.query(
                VocabularySet,
                User.username.label('creator_username'),
                db.func.count(Flashcard.flashcard_id).label('flashcard_count')
            ).outerjoin(User, VocabularySet.creator_user_id == User.user_id)\
             .outerjoin(Flashcard, VocabularySet.set_id == Flashcard.set_id)\
             .group_by(VocabularySet.set_id)\
             .order_by(VocabularySet.title)\
             .all()
            
            logger.info(f"{log_prefix} Lấy thành công {len(sets)} bộ thẻ.")
            
            results = []
            for set_obj, creator_username, flashcard_count in sets:
                set_obj.creator_username = creator_username or "N/A"
                set_obj.flashcard_count = flashcard_count
                results.append(set_obj)
                
            return results
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi truy vấn danh sách bộ thẻ: {e}", exc_info=True)
            return []

    def get_set_by_id(self, set_id):
        """
        Mô tả: Lấy một bộ thẻ cụ thể bằng ID.
        Args:
            set_id (int): ID của bộ thẻ.
        Returns:
            VocabularySet: Đối tượng bộ thẻ nếu tìm thấy, ngược lại là None.
        """
        return VocabularySet.query.get(set_id)

    def create_set(self, data, creator_id, file_stream=None):
        """
        Mô tả: Tạo một bộ thẻ mới, có thể kèm theo các flashcard từ file Excel.
        Args:
            data (dict): Dữ liệu của bộ thẻ mới (title, description, etc.).
            creator_id (int): ID của người dùng tạo bộ thẻ.
            file_stream (file-like object, optional): Stream của file Excel được tải lên.
        Returns:
            tuple: (VocabularySet, "success") nếu thành công.
                   (None, "error_message") nếu thất bại.
        """
        log_prefix = f"[SET_SERVICE|CreateSet|User:{creator_id}]"
        logger.info(f"{log_prefix} Đang tạo bộ thẻ mới với dữ liệu: {data}")
        
        try:
            # Tạo đối tượng VocabularySet
            new_set = VocabularySet(
                title=data.get('title'),
                description=data.get('description'),
                tags=data.get('tags'),
                is_public=int(data.get('is_public', 1)),
                creator_user_id=creator_id
            )
            db.session.add(new_set)

            # Nếu có file Excel, xử lý nó
            if file_stream:
                # Flush để lấy set_id cho các flashcard sắp tạo
                db.session.flush()
                logger.info(f"{log_prefix} Flushed session to get new set ID: {new_set.set_id}")

                # --- BẮT ĐẦU SỬA LỖI: Chuyển file stream sang BytesIO ---
                file_content = file_stream.read()
                in_memory_file = io.BytesIO(file_content)
                workbook = openpyxl.load_workbook(in_memory_file)
                # --- KẾT THÚC SỬA LỖI ---
                
                sheet = workbook.active
                
                headers = [str(cell.value).strip().lower() for cell in sheet[1]]
                column_map = {header: idx for idx, header in enumerate(headers)}

                if 'front' not in column_map or 'back' not in column_map:
                    raise ValueError("File Excel phải chứa cột 'front' và 'back' trong dòng tiêu đề.")
                
                flashcards_to_add = []
                for row_index, row_cells in enumerate(sheet.iter_rows(min_row=2), start=2):
                    row_values = [cell.value for cell in row_cells]
                    
                    front = str(row_values[column_map['front']]).strip() if row_values[column_map['front']] is not None else ''
                    back = str(row_values[column_map['back']]).strip() if row_values[column_map['back']] is not None else ''

                    if not front or not back:
                        logger.warning(f"{log_prefix} Bỏ qua hàng {row_index} do thiếu dữ liệu 'front' hoặc 'back'.")
                        continue

                    card_data = {'set_id': new_set.set_id, 'front': front, 'back': back}
                    optional_columns = ['front_audio_content', 'back_audio_content', 'front_img', 'back_img', 'notification_text']
                    for col_name in optional_columns:
                        if col_name in column_map:
                            col_idx = column_map[col_name]
                            if col_idx < len(row_values):
                                value = row_values[col_idx]
                                card_data[col_name] = str(value).strip() if value is not None else None
                    
                    new_card = Flashcard(**card_data)
                    flashcards_to_add.append(new_card)
                
                if flashcards_to_add:
                    db.session.bulk_save_objects(flashcards_to_add)
                    logger.info(f"{log_prefix} Đã chuẩn bị {len(flashcards_to_add)} thẻ từ file Excel.")
            
            db.session.commit()
            logger.info(f"{log_prefix} Tạo bộ thẻ '{new_set.title}' (ID: {new_set.id}) thành công.")
            return new_set, "success"
        except ValueError as ve:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi dữ liệu: {ve}", exc_info=True)
            return None, str(ve)
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi tạo bộ thẻ: {e}", exc_info=True)
            if "zip" in str(e).lower():
                 return None, "Lỗi đọc file Excel. Vui lòng đảm bảo file có định dạng .xlsx hợp lệ."
            return None, str(e)

    def update_set(self, set_id, data, file_stream=None):
        """
        Mô tả: Cập nhật thông tin và nội dung của một bộ thẻ, có thể từ file Excel.
               Nếu có file Excel, nội dung bộ thẻ sẽ được đồng bộ hóa hoàn toàn.
        Args:
            set_id (int): ID của bộ thẻ cần cập nhật.
            data (dict): Dữ liệu mới cho bộ thẻ (title, description...).
            file_stream (file-like object, optional): Stream của file Excel để cập nhật nội dung.
        Returns:
            tuple: (VocabularySet, "success") nếu thành công.
                   (None, "error_message") nếu thất bại.
        """
        log_prefix = f"[SET_SERVICE|UpdateSet|Set:{set_id}]"
        logger.info(f"{log_prefix} Đang cập nhật bộ thẻ với dữ liệu: {data}")
        
        set_to_update = self.get_set_by_id(set_id)
        if not set_to_update:
            return None, "set_not_found"
            
        try:
            # Cập nhật thông tin cơ bản của bộ thẻ
            set_to_update.title = data.get('title', set_to_update.title)
            set_to_update.description = data.get('description', set_to_update.description)
            set_to_update.tags = data.get('tags', set_to_update.tags)
            set_to_update.is_public = int(data.get('is_public', set_to_update.is_public))
            
            # Nếu có file Excel, thực hiện logic đồng bộ hóa
            if file_stream:
                logger.info(f"{log_prefix} Phát hiện file Excel, bắt đầu đồng bộ hóa thẻ.")
                
                # --- BẮT ĐẦU SỬA LỖI: Chuyển file stream sang BytesIO ---
                file_content = file_stream.read()
                in_memory_file = io.BytesIO(file_content)
                workbook = openpyxl.load_workbook(in_memory_file)
                # --- KẾT THÚC SỬA LỖI ---

                sheet = workbook.active
                
                headers = [str(cell.value).strip().lower() for cell in sheet[1]]
                column_map = {header: idx for idx, header in enumerate(headers)}

                if 'front' not in column_map or 'back' not in column_map:
                    raise ValueError("File Excel phải chứa cột 'front' và 'back' trong dòng tiêu đề.")

                # Lấy các thẻ hiện có để so sánh
                existing_cards = {card.front: card for card in set_to_update.flashcards}
                excel_fronts = set()

                # Lặp qua file Excel để thêm hoặc cập nhật
                for row_index, row_cells in enumerate(sheet.iter_rows(min_row=2), start=2):
                    row_values = [cell.value for cell in row_cells]
                    
                    front = str(row_values[column_map['front']]).strip() if row_values[column_map['front']] is not None else ''
                    if not front: continue
                    
                    excel_fronts.add(front)
                    
                    card_data = {}
                    optional_columns = ['back', 'front_audio_content', 'back_audio_content', 'front_img', 'back_img', 'notification_text']
                    for col_name in optional_columns:
                        if col_name in column_map:
                            col_idx = column_map[col_name]
                            if col_idx < len(row_values):
                                value = row_values[col_idx]
                                card_data[col_name] = str(value).strip() if value is not None else None

                    if front in existing_cards:
                        # Cập nhật thẻ đã có
                        card_to_update = existing_cards[front]
                        for key, value in card_data.items():
                            setattr(card_to_update, key, value)
                        db.session.add(card_to_update)
                    else:
                        # Tạo thẻ mới
                        new_card = Flashcard(set_id=set_id, front=front, **card_data)
                        db.session.add(new_card)

                # Xóa các thẻ không còn trong file Excel
                cards_to_delete = [card for front, card in existing_cards.items() if front not in excel_fronts]
                if cards_to_delete:
                    logger.info(f"{log_prefix} Sẽ xóa {len(cards_to_delete)} thẻ không có trong file Excel.")
                    for card in cards_to_delete:
                        db.session.delete(card)

            db.session.commit()
            logger.info(f"{log_prefix} Cập nhật bộ thẻ '{set_to_update.title}' thành công.")
            return set_to_update, "success"
        except ValueError as ve:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi dữ liệu: {ve}", exc_info=True)
            return None, str(ve)
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi cập nhật bộ thẻ: {e}", exc_info=True)
            return None, str(e)

    def delete_set(self, set_id):
        """
        Mô tả: Xóa một bộ thẻ khỏi cơ sở dữ liệu.
        Args:
            set_id (int): ID của bộ thẻ cần xóa.
        Returns:
            tuple: (True, "success") nếu xóa thành công.
                   (False, "error_message") nếu thất bại.
        """
        log_prefix = f"[SET_SERVICE|DeleteSet|Set:{set_id}]"
        logger.info(f"{log_prefix} Đang cố gắng xóa bộ thẻ.")
        
        set_to_delete = self.get_set_by_id(set_id)
        if not set_to_delete:
            logger.warning(f"{log_prefix} Không tìm thấy bộ thẻ để xóa.")
            return False, "set_not_found"
            
        try:
            db.session.delete(set_to_delete)
            db.session.commit()
            logger.info(f"{log_prefix} Xóa bộ thẻ '{set_to_delete.title}' thành công.")
            return True, "success"
        except Exception as e:
            db.session.rollback()
            logger.error(f"{log_prefix} Lỗi khi xóa bộ thẻ: {e}", exc_info=True)
            return False, str(e)

    def export_set_to_excel(self, set_id):
        """
        Mô tả: Xuất tất cả các flashcard của một bộ thẻ ra file Excel trong bộ nhớ.
        Args:
            set_id (int): ID của bộ thẻ cần xuất.
        Returns:
            io.BytesIO: Một đối tượng stream chứa dữ liệu file Excel, hoặc None nếu lỗi.
        """
        log_prefix = f"[SET_SERVICE|ExportSet|Set:{set_id}]"
        logger.info(f"{log_prefix} Bắt đầu xuất bộ thẻ ra Excel.")
        
        set_to_export = self.get_set_by_id(set_id)
        if not set_to_export:
            logger.warning(f"{log_prefix} Không tìm thấy bộ thẻ để xuất.")
            return None

        try:
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.title = set_to_export.title[:30] # Giới hạn độ dài tên sheet

            # Định nghĩa tiêu đề
            headers = ['front', 'back', 'front_audio_content', 'back_audio_content', 'front_img', 'back_img', 'notification_text']
            sheet.append(headers)

            # Lấy tất cả thẻ và ghi vào file
            for card in set_to_export.flashcards:
                row_data = [
                    card.front,
                    card.back,
                    card.front_audio_content,
                    card.back_audio_content,
                    card.front_img,
                    card.back_img,
                    card.notification_text
                ]
                sheet.append(row_data)
            
            # Lưu vào stream trong bộ nhớ
            excel_stream = io.BytesIO()
            workbook.save(excel_stream)
            excel_stream.seek(0) # Đưa con trỏ về đầu stream
            
            logger.info(f"{log_prefix} Xuất {len(set_to_export.flashcards)} thẻ ra Excel thành công.")
            return excel_stream
        except Exception as e:
            logger.error(f"{log_prefix} Lỗi khi xuất bộ thẻ ra Excel: {e}", exc_info=True)
            return None
