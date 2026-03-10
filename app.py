# app.py Главный файл
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl
from io import BytesIO
import os
from datetime import datetime
from pathlib import Path
# Импортируем расширения из отдельного файла
from extensions import db, login_manager
# Разграничение прав
from functools import wraps
import socket

# Создаем приложение
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'запасной-ключ-только-для-разработки')

# Создаем путь к папке database в той же директории, где находится app.py
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / 'database' / 'app.db'
# Убеждаемся, что папка существует
DB_PATH.parent.mkdir(exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database/app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализируем расширения с приложением
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

# Импортируем модели ПОСЛЕ инициализации db
from models import User, PersonData

# Декоратор для проверки прав администратора
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Доступ запрещен. Требуются права администратора.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ (ТОЛЬКО ДЛЯ АДМИНА) ---

@app.route('/users')
@login_required
@admin_required
def user_list():
    """Список всех пользователей"""
    users = User.query.all()
    return render_template('user_list.html', users=users)


@app.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def user_create():
    """Создание нового пользователя"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        role = request.form.get('role', 'user')

        # Проверяем, существует ли уже такой пользователь
        if User.query.filter_by(username=username).first():
            flash(f'Пользователь с именем {username} уже существует!')
            return redirect(url_for('user_create'))

        # Создаем нового пользователя
        new_user = User(
            username=username,
            password=generate_password_hash(password, method='pbkdf2:sha256'),
            full_name=full_name,
            role=role
        )
        db.session.add(new_user)
        db.session.commit()
        flash(f'Пользователь {username} успешно создан!')
        return redirect(url_for('user_list'))

    return render_template('user_create.html')

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def user_edit(user_id):
    """Редактирование пользователя"""
    user = User.query.get_or_404(user_id)

    # Не даем админу редактировать самого себя (чтобы случайно не лишить прав)
    if user.id == current_user.id:
        flash('Вы не можете редактировать свою учетную запись через эту страницу.')
        return redirect(url_for('user_list'))

    if request.method == 'POST':
        user.full_name = request.form.get('full_name')
        user.role = request.form.get('role')

        # Если ввели новый пароль - обновляем
        new_password = request.form.get('new_password')
        if new_password:
            user.password = generate_password_hash(new_password, method='pbkdf2:sha256')

        db.session.commit()
        flash(f'Пользователь {user.username} обновлен!')
        return redirect(url_for('user_list'))

    return render_template('user_edit.html', user=user)


@app.route('/users/delete/<int:user_id>')
@login_required
@admin_required
def user_delete(user_id):
    """Удаление пользователя"""
    user = User.query.get_or_404(user_id)

    # Не даем удалить самого себя
    if user.id == current_user.id:
        flash('Вы не можете удалить свою учетную запись!')
        return redirect(url_for('user_list'))

    # Не даем удалить последнего админа
    admin_count = User.query.filter_by(role='admin').count()
    if user.role == 'admin' and admin_count <= 1:
        flash('Нельзя удалить последнего администратора!')
        return redirect(url_for('user_list'))

    db.session.delete(user)
    db.session.commit()
    flash(f'Пользователь {user.username} удален!')
    return redirect(url_for('user_list'))

# --- СМЕНА ПАРОЛЯ ДЛЯ ОБЫЧНЫХ ПОЛЬЗОВАТЕЛЕЙ ---

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Смена пароля для текущего пользователя"""
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Проверяем старый пароль
        if not check_password_hash(current_user.password, old_password):
            flash('Неверный текущий пароль!')
            return redirect(url_for('change_password'))

        # Проверяем, что новый пароль подтвержден
        if new_password != confirm_password:
            flash('Новый пароль и подтверждение не совпадают!')
            return redirect(url_for('change_password'))

        # Обновляем пароль
        current_user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
        db.session.commit()
        flash('Пароль успешно изменен!')
        return redirect(url_for('dashboard'))

    return render_template('change_password.html')

# --- МАРШРУТЫ ---

@app.route('/')
def index():
    """Главная страница"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    logout_user()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    """Рабочий стол после входа"""
    return render_template('dashboard.html', name=current_user.full_name)

@app.route('/input', methods=['GET', 'POST'])
@login_required
def input_data():
    """Страница ввода данных"""
    if request.method == 'POST':
        # Функция-помощник для безопасного получения даты
        def get_date(field_name):
            date_str = request.form.get(field_name)
            if date_str:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return None
            return None

        # Обработка категории
        category = request.form.get('category')
        category_custom = None
        if category == '7':
            category = request.form.get('category_custom')
            category_custom = category  # сохраняем кастомное значение
        elif category:
            # Если выбрано 1-6, преобразуем в "Параметр 1", "Параметр 2" и т.д.
            category = f"Параметр {category}"

        # Создаем новую запись
        new_entry = PersonData(
            user_id=current_user.id,

            # Общие данные
            last_name=request.form.get('last_name'),
            first_name=request.form.get('first_name'),
            middle_name=request.form.get('middle_name'),
            birth_date=get_date('birth_date'),

            date2=get_date('date2'),
            place2=request.form.get('place2'),

            category=category,
            category_custom=category_custom,

            position=request.form.get('position'),
            rank=request.form.get('rank'),
            number=request.form.get('number'),
            lp=request.form.get('lp'),
            lp_reason=request.form.get('lp_reason'),
            place=request.form.get('place'),
            ppr=request.form.get('ppr'),
            place2_field=request.form.get('place2_field'),
            date4=get_date('date4'),
            ee=get_date('ee'),
            ee4=get_date('ee4')
        )

        db.session.add(new_entry)
        db.session.commit()
        flash('Данные успешно сохранены!')
        return redirect(url_for('dashboard'))

    return render_template('input_form.html')

@app.route('/report/simple')
@login_required
def generate_simple_report():
    """Генерирует подробный отчет в Excel"""
    entries = PersonData.query.all() #filter_by(user_id=current_user.id).

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Полный отчет"

    # Заголовки для всех полей
    headers = [
        'ID', 'Фамилия', 'Имя', 'Отчество', 'Дата рождения',
        'Дата 2', 'Место 2', 'Категория', 'Свой вариант',
        'Должность', 'Звание', 'Номер', 'ЛП', 'Причина ЛП',
        'Место', 'ППР', 'Место 2', 'Дата 4', 'ЭЭ', 'ЭЭ4',
        'Дата создания', 'Автор'
    ]
    ws.append(headers)

    # Данные
    for entry in entries:
        # Получаем имя автора
        #author_name = entry.author.full_name if entry.author.full_name else entry.author.username
        author_name = entry.author.full_name if entry.author and entry.author.full_name else (
            entry.author.username if entry.author else 'Неизвестно')

        row = [
            entry.id,
            entry.last_name,
            entry.first_name,
            entry.middle_name,
            entry.birth_date.strftime('%d.%m.%Y') if entry.birth_date else '',
            entry.date2.strftime('%d.%m.%Y') if entry.date2 else '',
            entry.place2,
            entry.category,
            entry.category_custom,
            entry.position,
            entry.rank,
            entry.number,
            entry.lp,
            entry.lp_reason,
            entry.place,
            entry.ppr,
            entry.place2_field,
            entry.date4.strftime('%d.%m.%Y') if entry.date4 else '',
            entry.ee.strftime('%d.%m.%Y') if entry.ee else '',
            entry.ee4.strftime('%d.%m.%Y') if entry.ee4 else '',
            entry.created_at.strftime('%d.%m.%Y %H:%M'),
            author_name
        ]
        ws.append(row)

    # Автоматическая ширина колонок
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f'отчет_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# ЕДИНСТВЕННЫЙ БЛОК В КОНЦЕ ФАЙЛА (замени то, что сейчас в строках 318-341)
if __name__ == '__main__':
    # Создаем папку для базы данных, если её нет
    os.makedirs('database', exist_ok=True)

    # Создаем таблицы и тестовых пользователей
    with app.app_context():

        # # Очищаем метаданные перед созданием (важно!)
        # db.metadata.clear()

        # СОЗДАЕМ ТАБЛИЦЫ (включая PersonData!)
        db.create_all()

        # Проверяем и создаем админа
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin123', method='pbkdf2:sha256'),
                full_name='Главный Администратор',
                role='admin'
            )
            db.session.add(admin)
            print("✅ Создан администратор: admin / admin123")

        # Проверяем и создаем обычного пользователя
        if not User.query.filter_by(username='user').first():
            user = User(
                username='user',
                password=generate_password_hash('user123', method='pbkdf2:sha256'),
                full_name='Обычный Пользователь',
                role='user'
            )
            db.session.add(user)
            print("✅ Создан пользователь: user / user123")

        db.session.commit()

        # Показываем какие таблицы созданы
        print("\n📊 ТАБЛИЦЫ В БАЗЕ:")
        for table in db.metadata.tables.keys():
            print(f"  - {table}")
        print("=" * 40)

    print("\n" + "=" * 50)
    print("🚀 СЕРВЕР ЗАПУЩЕН!")
    print("=" * 50)
    print("📌 Локальный доступ: http://127.0.0.1:5000")

    # Получаем локальный IP для доступа из сети
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"🌐 Доступ из локальной сети: http://{local_ip}:5000")
    except:
        print("🌐 Доступ из локальной сети: проверьте IP-адрес")

    print("=" * 50 + "\n")
    print("💡 Учетные записи:")
    print("   - admin / admin123 (администратор)")
    print("   - user / user123 (обычный пользователь)")
    print("=" * 50 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)