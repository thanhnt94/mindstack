# web_app/services/set_service.py
import logging
import openpyxl
import io
from ..models import db, VocabularySet, User, Flashcard, UserFlashcardProgress # Thêm UserFlashcardProgress để xóa liên quan

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

    def _process_excel_file(self, vocabulary_set, file_stream, sync_by_id=False):
        """
        Mô tả: Xử lý file Excel được tải lên để thêm hoặc đồng bộ hóa flashcard.
               Hỗ trợ thêm/cập nhật/xóa flashcard dựa trên flashcard_id.
        Args:
            vocabulary_set (VocabularySet): Đối tượng bộ thẻ.
            file_stream (file-like object): Stream của file Excel.
            sync_by_id (bool): Nếu True, sẽ đồng bộ hóa (cập nhật/xóa) các flashcard hiện có
                                dựa trên flashcard_id. Nếu False, chỉ thêm các flashcard mới.
        Raises:
            ValueError: Nếu file Excel thiếu các cột bắt buộc hoặc có lỗi dữ liệu.
        """
        log_prefix = f"[SET_SERVICE|ProcessExcel|Set:{vocabulary_set.set_id}]"
        
        file_content = file_stream.read()
        in_memory_file = io.BytesIO(file_content)
        workbook = openpyxl.load_workbook(in_memory_file)
        
        sheet = workbook.active
        
        headers = [str(cell.value).strip().lower() if cell.value is not None else "" for cell in sheet[1]]
        required_headers = ['front', 'back']
        
        missing_headers = [h for h in required_headers if h not in headers]
        if missing_headers:
            error_message = (f"File Excel thiếu các cột bắt buộc: {', '.join(missing_headers)}. "
                             f"Các cột tìm thấy trong file của bạn là: {', '.join(h for h in headers if h)}.")
            raise ValueError(error_message)
        
        column_map = {header: idx for idx, header in enumerate(headers)}
        
        flashcards_from_excel = [] # Sẽ lưu các dict dữ liệu flashcard từ Excel

        for row_index, row_cells in enumerate(sheet.iter_rows(min_row=2), start=2):
            row_values = [cell.value for cell in row_cells]
            
            # Lấy flashcard_id từ Excel (nếu có)
            flashcard_id_from_excel = None
            if 'flashcard_id' in column_map and row_values[column_map['flashcard_id']] is not None:
                try:
                    flashcard_id_from_excel = int(row_values[column_map['flashcard_id']])
                except ValueError:
                    logger.warning(f"{log_prefix} Hàng {row_index}: flashcard_id không hợp lệ. Coi là thẻ mới.")

            front = str(row_values[column_map['front']]).strip() if row_values[column_map['front']] is not None else ''
            back = str(row_values[column_map['back']]).strip() if row_values[column_map['back']] is not None else ''

            # BẮT ĐẦU THAY ĐỔI: Không bỏ qua thẻ nếu front hoặc back rỗng, nhưng cảnh báo
            if not front:
                logger.warning(f"{log_prefix} Hàng {row_index}: Cột 'front' rỗng. Thẻ có thể không hiển thị đúng.")
            if not back:
                logger.warning(f"{log_prefix} Hàng {row_index}: Cột 'back' rỗng. Thẻ có thể không hiển thị đúng.")
            # KẾT THÚC THAY ĐỔI

            card_data = {
                'flashcard_id': flashcard_id_from_excel, # Giữ lại ID để xử lý update/add
                'set_id': vocabulary_set.set_id, 
                'front': front, 
                'back': back
            }
            optional_columns = ['front_audio_content', 'back_audio_content', 'front_img', 'back_img', 'notification_text']
            for col_name in optional_columns:
                if col_name in column_map:
                    col_idx = column_map[col_name]
                    if col_idx < len(row_values):
                        value = row_values[col_idx]
                        card_data[col_name] = str(value).strip() if value is not None else None
            
            flashcards_from_excel.append(card_data)
        
        if sync_by_id:
            # Lấy tất cả các flashcard hiện có trong bộ này
            existing_flashcards_map = {f.flashcard_id: f for f in vocabulary_set.flashcards}
            excel_flashcard_ids = {f_data['flashcard_id'] for f_data in flashcards_from_excel if f_data['flashcard_id'] is not None}

            for f_data in flashcards_from_excel:
                f_id = f_data.pop('flashcard_id') # Lấy và xóa flashcard_id khỏi dict
                if f_id is not None and f_id in existing_flashcards_map:
                    # Cập nhật flashcard đã có
                    f_to_update = existing_flashcards_map[f_id]
                    for key, value in f_data.items():
                        setattr(f_to_update, key, value)
                    db.session.add(f_to_update)
                    logger.debug(f"{log_prefix} Cập nhật flashcard ID: {f_id}.")
                else:
                    # Thêm flashcard mới
                    new_flashcard = Flashcard(**f_data)
                    db.session.add(new_flashcard)
                    logger.debug(f"{log_prefix} Thêm flashcard mới từ Excel.")
            
            # Xóa các flashcard không còn trong file Excel
            flashcards_to_delete = [f for f_id, f in existing_flashcards_map.items() if f_id not in excel_flashcard_ids]
            for f in flashcards_to_delete:
                # Khi xóa flashcard, cần xóa cả UserFlashcardProgress liên quan
                UserFlashcardProgress.query.filter_by(flashcard_id=f.flashcard_id).delete()
                db.session.delete(f)
                logger.debug(f"{log_prefix} Xóa flashcard ID: {f.flashcard_id} không có trong Excel.")
            logger.info(f"{log_prefix} Đồng bộ hóa hoàn tất. Thêm/cập nhật {len(flashcards_from_excel)}, xóa {len(flashcards_to_delete)} flashcard.")
        else:
            # Chế độ thêm mới (không sync), chỉ thêm các flashcard mới từ Excel
            flashcards_to_add = []
            for f_data in flashcards_from_excel:
                f_data.pop('flashcard_id') # Loại bỏ flashcard_id vì đây là thêm mới
                new_flashcard = Flashcard(**f_data)
                flashcards_to_add.append(new_flashcard)
            
            if flashcards_to_add:
                db.session.bulk_save_objects(flashcards_to_add)
            logger.info(f"{log_prefix} Đã thêm {len(flashcards_to_add)} flashcard mới từ file.")


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
                self._process_excel_file(new_set, file_stream, sync_by_id=False) # Thêm mới, không sync theo ID
            
            db.session.commit()
            logger.info(f"{log_prefix} Tạo bộ thẻ '{new_set.title}' (ID: {new_set.set_id}) thành công.")
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
                self._process_excel_file(set_to_update, file_stream, sync_by_id=True) # Đồng bộ hóa theo ID

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

            # BẮT ĐẦU THAY ĐỔI: Thêm flashcard_id vào headers
            headers = ['flashcard_id', 'front', 'back', 'front_audio_content', 'back_audio_content', 'front_img', 'back_img', 'notification_text']
            # KẾT THÚC THAY ĐỔI
            sheet.append(headers)

            # Lấy tất cả thẻ và ghi vào file
            for card in set_to_export.flashcards:
                row_data = [
                    card.flashcard_id, # Thêm flashcard_id vào hàng xuất
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

