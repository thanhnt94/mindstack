# flashcard-web/web_app/db_instance.py
from flask_sqlalchemy import SQLAlchemy

# Khởi tạo một đối tượng SQLAlchemy toàn cục, không gắn app tại đây
db = SQLAlchemy()
