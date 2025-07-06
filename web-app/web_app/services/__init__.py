# web_app/services/__init__.py
from .learning_logic import LearningLogicService
from .user_service import UserService
from .stats_service import StatsService
from .audio_service import AudioService # THÊM: Import AudioService

# Khởi tạo các service để có thể import và sử dụng trực tiếp
learning_logic_service = LearningLogicService()
user_service = UserService()
stats_service = StatsService()
audio_service = AudioService() # THÊM: Khởi tạo AudioService

# Bạn có thể thêm các biến khác hoặc logic khởi tạo chung ở đây nếu cần
