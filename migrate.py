# migrate.py
import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from pathlib import Path

# Создаем минимальное приложение
app = Flask(__name__)
app.config['SECRET_KEY'] = 'migration-key'

# Настройки БД
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / 'database' / 'app.db'
DB_PATH.parent.mkdir(exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Импортируем модели
from models import User, PersonData, EditHistory, Relative, RelativeHistory

# Инициализация
from extensions import db, login_manager

db.init_app(app)
login_manager.init_app(app)
migrate = Migrate(app, db)

if __name__ == '__main__':
    with app.app_context():
        # Создаем папку migrations если её нет
        if not os.path.exists('migrations'):
            from flask_migrate import init

            init()
            print("✅ Миграции инициализированы")

        # Создаем миграцию
        from flask_migrate import migrate

        migrate(message="автоматическая миграция")
        print("✅ Миграция создана")

        # Применяем миграцию
        from flask_migrate import upgrade

        upgrade()
        print("✅ Миграция применена")