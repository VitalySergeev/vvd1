# upgrade_to_head.py
from migrate_new import app
from flask_migrate import upgrade
import os

with app.app_context():
    migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
    print("Обновляем до последней версии...")
    upgrade(directory=migrations_dir, revision='head')
    print("✅ Миграции применены")