# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import MetaData

# Создаем MetaData
metadata = MetaData()

# Создаем объекты расширений с нашей metadata
db = SQLAlchemy(metadata=metadata)
login_manager = LoginManager()
