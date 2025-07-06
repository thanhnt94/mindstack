"""
Module định nghĩa các lớp Exception tùy chỉnh cho ứng dụng Flashcard Bot.
Việc sử dụng các exception tùy chỉnh giúp phân loại lỗi rõ ràng hơn
và cho phép xử lý lỗi cụ thể ở các tầng cao hơn (handlers, API).
"""
class AppException(Exception):
    def __init__(self, message="Lỗi ứng dụng không xác định."):
        self.message = message
        super().__init__(self.message)
class DatabaseError(AppException):
    def __init__(self, message="Lỗi cơ sở dữ liệu.", original_exception=None):
        self.original_exception = original_exception
        full_message = f"{message} ({type(original_exception).__name__}: {original_exception})" if original_exception else message
        super().__init__(full_message)
class NotFoundError(AppException):
    def __init__(self, message="Không tìm thấy tài nguyên."):
        super().__init__(message)
class UserNotFoundError(NotFoundError):
    def __init__(self, identifier=None, message="Không tìm thấy người dùng."):
        if identifier:
            message = f"Không tìm thấy người dùng với định danh: {identifier}"
        super().__init__(message)
class SetNotFoundError(NotFoundError):
    def __init__(self, set_id=None, message="Không tìm thấy bộ từ vựng."):
        if set_id:
            message = f"Không tìm thấy bộ từ vựng với ID: {set_id}"
        super().__init__(message)
class NoteNotFoundError(NotFoundError):
    def __init__(self, note_id=None, message="Không tìm thấy ghi chú."):
        if note_id:
            message = f"Không tìm thấy ghi chú với ID: {note_id}"
        super().__init__(message)
class ProgressNotFoundError(NotFoundError):
    def __init__(self, progress_id=None, message="Không tìm thấy tiến trình học."):
        if progress_id:
            message = f"Không tìm thấy tiến trình học với ID: {progress_id}"
        super().__init__(message)
class CardNotFoundError(NotFoundError):
    def __init__(self, card_id=None, message="Không tìm thấy thẻ flashcard."):
        if card_id:
            message = f"Không tìm thấy thẻ flashcard với ID: {card_id}"
        super().__init__(message)
class DuplicateError(AppException):
    def __init__(self, message="Dữ liệu bị trùng lặp.", conflicting_field=None, conflicting_value=None):
        if conflicting_field and conflicting_value:
             message = f"Dữ liệu bị trùng lặp cho trường '{conflicting_field}' với giá trị '{conflicting_value}'."
        elif conflicting_field:
             message = f"Dữ liệu bị trùng lặp cho trường '{conflicting_field}'."
        super().__init__(message)
class PermissionsError(AppException):
    def __init__(self, message="Không có quyền thực hiện hành động này.", required_permission=None):
        if required_permission:
            message = f"Không có quyền '{required_permission}' để thực hiện hành động này."
        super().__init__(message)
class ValidationError(AppException):
    def __init__(self, message="Dữ liệu đầu vào không hợp lệ.", field_name=None, details=None):
        if field_name:
            message = f"Dữ liệu không hợp lệ cho trường '{field_name}'."
        if details:
             message = f"{message} Chi tiết: {details}"
        super().__init__(message)
class ServiceError(AppException):
    def __init__(self, message="Lỗi xử lý nghiệp vụ.", service_name=None):
        if service_name:
            message = f"Lỗi trong service '{service_name}': {message}"
        super().__init__(message)
class ExternalServiceError(ServiceError):
    def __init__(self, message="Lỗi dịch vụ bên ngoài.", service_name="External", original_exception=None):
        self.original_exception = original_exception
        full_message = f"Lỗi gọi dịch vụ '{service_name}'. {message}"
        if original_exception:
             full_message = f"{full_message} ({type(original_exception).__name__}: {original_exception})"
        super().__init__(message=full_message, service_name=service_name)
class FileProcessingError(AppException):
     def __init__(self, message="Lỗi xử lý file.", filename=None):
        if filename:
            message = f"Lỗi xử lý file '{filename}': {message}"
        super().__init__(message)
class InvalidFileFormatError(FileProcessingError):
    def __init__(self, message="Định dạng file không hợp lệ.", filename=None, expected_format=None):
         full_message = message
         if expected_format:
             full_message = f"{message}. Định dạng mong muốn: {expected_format}"
         super().__init__(message=full_message, filename=filename)
class ExcelImportError(FileProcessingError):
    def __init__(self, message="Lỗi import Excel.", filename=None, sheet_name=None, row_number=None, details=""):
         context = []
         if sheet_name: context.append(f"Sheet '{sheet_name}'")
         if row_number: context.append(f"Dòng {row_number}")
         context_str = f" ({', '.join(context)})" if context else ""
         full_message = f"{message}{context_str}: {details}"
         super().__init__(message=full_message, filename=filename)