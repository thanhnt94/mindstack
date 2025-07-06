flashcard_bot/
├── main.py 
├── config.py 
├── database/
│ ├── __init__.py
│ ├── db_handler.py 
│ └── queries.py 
├── handlers/
│ ├── __init__.py
│ ├── admin.py 
│ ├── audio.py 
│ ├── core.py 
│ ├── export_import.py 
│ ├── notes.py 
│ ├── review.py 
│ ├── settings.py 
│ ├── stats.py 
│ └── notifications.py 
├── services/
│ ├── __init__.py
│ ├── audio_service.py 
│ ├── excel_service.py 
│ ├── notification_service.py 
│ └── review_logic.py 
├── utils/
│ ├── __init__.py
│ ├── helpers.py 
│ └── telegram_ui.py 
├── audio_cache/ 
│ └── ...
├── database/ 
│ └── flashcard.db
└── .env 
└── requirements.txt 