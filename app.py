# app.py Главный файл
from flask import Flask, render_template, redirect, url_for, request, flash, send_file, send_from_directory
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
#from flask_bootstrap import Bootstrap  # Импортируем Bootstrap5
from flask_migrate import Migrate      # Миграция данных БД
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
from models import User, PersonData, EditHistory, Relative, RelativeHistory, Award, RuRecord, AwardHistory
#import logging
#logging.basicConfig(level=logging.DEBUG)

# Создаем приложение
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'запасной-ключ-только-для-разработки')

# # Настройки Bootstrap
# app.config['BOOTSTRAP_SERVE_LOCAL'] = True  # Загружать Bootstrap локально
# bootstrap = Bootstrap(app)  # Инициализируем Bootstrap
#
# # Добавляем bootstrap в контекст всех шаблонов
# @app.context_processor
# def inject_bootstrap():
#     return dict(bootstrap=bootstrap)

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

# ИНИЦИАЛИЗАЦИЯ MIGRATE
migrate = Migrate(app, db)

# Импортируем модели ПОСЛЕ инициализации db
from models import User, PersonData, EditHistory

# Загрузка сканов
# Конфигурация для загрузки файлов
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'scans')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'bmp', 'tiff'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Максимальный размер файла 16MB

# Создаем папку для загрузок, если её нет
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Декоратор для проверки прав администратора
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Доступ запрещен. Требуются права администратора.','warning')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id)) #User.query.get(int(user_id))

def save_edit_history(record_id, user_id, changes):
    """
    Сохраняет историю изменений
    changes - словарь вида {'field_name': {'old': old_value, 'new': new_value}}
    """
    for field_name, values in changes.items():
        # Не сохраняем пустые изменения
        if values['old'] != values['new']:
            history_entry = EditHistory(
                record_id=record_id,
                user_id=user_id,
                field_name=field_name,
                old_value=str(values['old']) if values['old'] else '',
                new_value=str(values['new']) if values['new'] else ''
            )
            db.session.add(history_entry)
    db.session.commit()

@app.route('/records')
@login_required
def all_records():
    """Страница со ВСЕМИ записями для всех пользователей с поиском"""
    # Базовый запрос
    query = PersonData.query

    # Поиск по фамилии
    search_last_name = request.args.get('search_last_name', '')
    if search_last_name:
        query = query.filter(PersonData.last_name.ilike(f'%{search_last_name}%'))

    # Поиск по пользователю (автору)
    search_user = request.args.get('search_user', '')
    if search_user:
        query = query.join(PersonData.author).filter(User.full_name.ilike(f'%{search_user}%'))

    # Поиск по дате рождения (точная дата)
    search_birth_date = request.args.get('search_birth_date', '')
    if search_birth_date:
        try:
            birth_date = datetime.strptime(search_birth_date, '%Y-%m-%d').date()
            query = query.filter(PersonData.birth_date == birth_date)
        except ValueError:
            flash('Неверный формат даты рождения','warning')

    # Получаем отфильтрованные записи
    records = query.order_by(PersonData.created_at.desc()).all()

    # Статистика (только то, что нужно)
    total_all_records = PersonData.query.count()  # Общее количество ВСЕХ записей
    current_records = len(records)                # Количество записей по текущему поиску

    return render_template(
        'all_records.html',
        records=records,
        search_last_name=search_last_name,
        search_user=search_user,
        search_birth_date=search_birth_date,
        total_all_records=total_all_records,
        current_records=current_records
    )

@app.route('/record/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_record(record_id):
    """Редактирование существующей записи - доступно всем пользователям"""
    record = PersonData.query.get_or_404(record_id)

    # Убрали проверку на владельца - теперь любой может редактировать любую запись
    if request.method == 'POST':
        def get_date(field_name):
            date_str = request.form.get(field_name)
            #print(f"📅 get_date для {field_name}: '{date_str}'")
            if date_str:
                try:
                    parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    #print(f"  -> преобразовано в {parsed_date}")
                    return parsed_date
                except (ValueError, TypeError) as e:
                    #print(f"  ❌ ошибка: {e}")
                    return None
            #print(f"  -> пустое значение")
            return None

        # Собираем изменения
        changes = {}

        # Функция для проверки изменений
        def check_change(field, form_value, cast_func=None):
            old = getattr(record, field)
            if cast_func:
                new = cast_func(form_value)
            else:
                new = form_value if form_value else None

            if old != new:
                changes[field] = {'old': old, 'new': new}
            return new

        # Общие данные
        record.last_name = check_change('last_name', request.form.get('last_name'))
        record.first_name = check_change('first_name', request.form.get('first_name'))
        record.middle_name = check_change('middle_name', request.form.get('middle_name'))
        # Исправление даты рождения
        birth_date_from_form = request.form.get('birth_date')
        if birth_date_from_form:
            new_birth_date = get_date('birth_date')
            if new_birth_date != record.birth_date:
                changes['birth_date'] = {'old': record.birth_date, 'new': new_birth_date}
                record.birth_date = new_birth_date

        #Исправление Даты2
        date2_from_form = request.form.get('date2')
        if date2_from_form:
            new_date2 = get_date('date2')
            if new_date2 != record.date2:
                changes['date2'] = {'old': record.date2, 'new': new_date2}
                record.date2 = new_date2

        record.place2 = check_change('place2', request.form.get('place2'))

        # Обработка категории (единое поле)
        category_value = request.form.get('category')
        if category_value == 'other':
            category_value = request.form.get('category_other')
        elif category_value:
            category_value = f"Параметр {category_value}"

        record.category = check_change('category', category_value)
        #record.category_custom = check_change('category_custom', category_custom)

        # Остальные поля
        record.position = check_change('position', request.form.get('position'))
        record.rank = check_change('rank', request.form.get('rank'))
        record.number = check_change('number', request.form.get('number'))
        record.lp = check_change('lp', request.form.get('lp'))
        record.lp_reason = check_change('lp_reason', request.form.get('lp_reason'))
        record.place = check_change('place', request.form.get('place'))
        record.ppr = check_change('ppr', request.form.get('ppr'))
        record.place2_field = check_change('place2_field', request.form.get('place2_field'))

        #record.date4 = check_change('date4', request.form.get('date4'), get_date)
        # ИСПРАВЛЕНИЕ ДЛЯ ДАТЫ 4
        date4_from_form = request.form.get('date4')
        if date4_from_form:
            new_date4 = get_date('date4')
            if new_date4 != record.date4:
                changes['date4'] = {'old': record.date4, 'new': new_date4}
                record.date4 = new_date4

        #record.ee = check_change('ee', request.form.get('ee'), get_date)
        # ИСПРАВЛЕНИЕ ДЛЯ ЭЭ
        ee_from_form = request.form.get('ee')
        if ee_from_form:
            new_ee = get_date('ee')
            if new_ee != record.ee:
                changes['ee'] = {'old': record.ee, 'new': new_ee}
                record.ee = new_ee

        #record.ee4 = check_change('ee4', request.form.get('ee4'), get_date)
        # ИСПРАВЛЕНИЕ ДЛЯ ЭЭ4
        ee4_from_form = request.form.get('ee4')
        if ee4_from_form:
            new_ee4 = get_date('ee4')
            if new_ee4 != record.ee4:
                changes['ee4'] = {'old': record.ee4, 'new': new_ee4}
                record.ee4 = new_ee4

        # Особые отметки
        record.special_notes = check_change('special_notes', request.form.get('special_notes'))

        # Если есть изменения - сохраняем
        if changes:
            # Обновляем время изменения
            record.updated_at = datetime.now()
            db.session.commit()

            # Сохраняем историю изменений
            save_edit_history(record.id, current_user.id, changes)

            #flash(f'Запись #{record.id} успешно обновлена! Изменено полей: {len(changes)}', 'success')
            #мои правки
            if request.form.get('redirect_to') == 'relatives':
                #flash('Данные успешно сохранены!', 'success')
                return redirect(url_for('manage_relatives', person_id=record.id))
        else:
            # Мое изменение в случае Нет проверяем, куда редиректить
            if request.form.get('redirect_to') == 'relatives':
                return redirect(url_for('manage_relatives', person_id=record.id))
            #flash('Нет изменений для сохранения', 'success')

        return redirect(url_for('all_records'))

    return render_template('edit_record.html', record=record)

#
@app.route('/record/history/<int:record_id>')
# @login_required
# def record_history(record_id):
#     """Просмотр истории изменений записи - доступно всем"""
#     record = PersonData.query.get_or_404(record_id)
#
#     # Убрали проверку на владельца - теперь любой может смотреть историю любой записи
#     history = EditHistory.query.filter_by(record_id=record_id).order_by(EditHistory.edited_at.desc()).all()
#     return render_template('record_history.html', record=record, history=history)

@app.route('/record/history/<int:record_id>')
@login_required
def record_history(record_id):
    """Просмотр истории изменений записи с группировкой по коммитам"""
    record = PersonData.query.get_or_404(record_id)

    # Получаем все изменения для этой записи
    history = EditHistory.query.filter_by(record_id=record_id) \
        .order_by(EditHistory.edited_at.desc()).all()

    # Группируем изменения по времени (с точностью до секунды)
    grouped = {}
    for entry in history:
        # Ключ - строка с датой-временем + пользователь
        time_key = entry.edited_at.strftime('%Y-%m-%d %H:%M:%S')
        user_key = entry.user_id
        group_key = f"{time_key}_{user_key}"

        if group_key not in grouped:
            grouped[group_key] = {
                'edited_at': entry.edited_at,
                'user_name': entry.user.full_name or entry.user.username,
                'user_id': entry.user_id,
                'changes': []
            }

        # Формируем текст изменения
        field_names = {
            'last_name': 'Фамилия',
            'first_name': 'Имя',
            'middle_name': 'Отчество',
            'birth_date': 'Дата рождения',
            'date2': 'Дата 2',
            'place2': 'Место 2',
            'category': 'Категория',
            'position': 'Должность',
            'rank': 'Звание',
            'number': 'Номер',
            'lp': 'ЛП',
            'lp_reason': 'Причина ЛП',
            'place': 'Место',
            'ppr': 'ППР',
            'place2_field': 'Место 2',
            'date4': 'Дата 4',
            'ee': 'ЭЭ',
            'ee4': 'ЭЭ4'
        }

        field_rus = field_names.get(entry.field_name, entry.field_name)
        old_val = entry.old_value if entry.old_value else 'пусто'
        new_val = entry.new_value if entry.new_value else 'пусто'

        grouped[group_key]['changes'].append({
            'field': field_rus,
            'old': old_val,
            'new': new_val,
            'display': f"{field_rus}: {old_val} → {new_val}",
            'short': f"{field_rus}: {old_val} → {new_val}"[:50]
        })

    # Преобразуем в список для шаблона
    grouped_history = []
    for group in grouped.values():
        grouped_history.append(group)

    # Сортируем по дате (сначала новые)
    grouped_history.sort(key=lambda x: x['edited_at'], reverse=True)

    return render_template('record_history.html',
                           record=record,
                           grouped_history=grouped_history)

def save_relative_history(relative_id, user_id, changes):
    """
    Сохраняет историю изменений родственника
    changes - словарь вида {'field_name': {'old': old_value, 'new': new_value}}
    """
    for field_name, values in changes.items():
        if values['old'] != values['new']:
            history_entry = RelativeHistory(
                relative_id=relative_id,
                user_id=user_id,
                field_name=field_name,
                old_value=str(values['old']) if values['old'] else '',
                new_value=str(values['new']) if values['new'] else ''
            )
            db.session.add(history_entry)
    db.session.commit()

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
            flash(f'Пользователь с именем {username} уже существует!', 'success')
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
        flash(f'Пользователь {username} успешно создан!', 'success')
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
        flash('Вы не можете редактировать свою учетную запись через эту страницу.', 'warning')
        return redirect(url_for('user_list'))

    if request.method == 'POST':
        user.full_name = request.form.get('full_name')
        user.role = request.form.get('role')

        # Если ввели новый пароль - обновляем
        new_password = request.form.get('new_password')
        if new_password:
            user.password = generate_password_hash(new_password, method='pbkdf2:sha256')

        db.session.commit()
        flash(f'Пользователь {user.username} обновлен!', 'success')
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
        flash('Вы не можете удалить свою учетную запись!', 'success')
        return redirect(url_for('user_list'))

    # Не даем удалить последнего админа
    admin_count = User.query.filter_by(role='admin').count()
    if user.role == 'admin' and admin_count <= 1:
        flash('Нельзя удалить последнего администратора!', 'success')
        return redirect(url_for('user_list'))

    db.session.delete(user)
    db.session.commit()
    flash(f'Пользователь {user.username} удален!', 'success')
    return redirect(url_for('user_list'))

# --- СМЕНА ПАРОЛЯ ДЛЯ ОБЫЧНЫХ ПОЛЬЗОВАТЕЛЕЙ ---

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_password():
    """Смена пароля для текущего пользователя"""
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Проверяем старый пароль
        if not check_password_hash(current_user.password, old_password):
            flash('Неверный текущий пароль!','error')
            return redirect(url_for('change_password'))

        # Проверяем, что новый пароль подтвержден
        if new_password != confirm_password:
            flash('Новый пароль и подтверждение не совпадают!','error')
            return redirect(url_for('change_password'))

        # Обновляем пароль
        current_user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
        db.session.commit()
        flash('Пароль успешно изменен!','success')
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
            flash('Неверное имя пользователя или пароль','error')

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

        # Обработка категории (единое поле)
        category = request.form.get('category')
        if category == 'other':
            category = request.form.get('category_other')
        elif category:
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
            #category_custom=category_custom,

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
        #flash('Данные успешно сохранены!','success')
        #return redirect(url_for('input_data'))  # Остаемся на той же странице
        # ПОСЛЕ СОХРАНЕНИЯ ПЕРЕХОДИМ В РЕЖИМ РЕДАКТИРОВАНИЯ
        flash(f'✅ Запись успешно создана! Теперь вы можете добавить другие данные.', 'success')
        return redirect(url_for('edit_record', record_id=new_entry.id))

    return render_template('input_form.html')

@app.route('/person/<int:person_id>/relatives', methods=['GET', 'POST'])
@login_required
def manage_relatives(person_id):
    """Управление родственниками для конкретной записи"""
    person = PersonData.query.get_or_404(person_id)
    #relatives = Relative.query.filter_by(person_data_id=person.id).all()
    #return render_template('relatives.html', person=person, relatives=relatives)

    if request.method == 'POST':
        # # Отладка
        # print("=" * 50)
        # print("ПОЛУЧЕН POST ЗАПРОС НА ДОБАВЛЕНИЕ РОДСТВЕННИКА")
        # print("Форма данные:")
        # for key, value in request.form.items():
        #     print(f"  {key}: {value}")
        # print("Файлы:")
        # for key, file in request.files.items():
        #     if file.filename:
        #         print(f"  {key}: {file.filename}")
        # print("=" * 50)
        # Функция для получения даты
        def get_date(field_name):
            date_str = request.form.get(field_name)
            if date_str:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return None
            return None
            # КОНЕЦ ФУНКЦИИ get_date - отступ возвращается на уровень if request.method

        # Обработка загрузки файла скана - С ПОДРОБНОЙ ОТЛАДКОЙ
        # print("\n" + "=" * 60)
        # print("🔍 ЗАГРУЗКА ФАЙЛА СКАНА")
        # print(f"request.files: {request.files}")
        # print(f"Ключи в request.files: {list(request.files.keys())}")
        # #
        scan_path = None
        if 'scan_file' in request.files:
            file = request.files['scan_file']
            # Проверяем расширение файла
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                # Добавляем timestamp для уникальности
                new_filename = f"relative_new_{name}_{timestamp}{ext}"
                # Полный путь для сохранения
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                # Создаем папку если её нет
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                # Сохраняем файл
                file.save(file_path)
                # Сохраняем относительный путь в БД
                scan_path = f"uploads/scans/{new_filename}"
                # print(f"✅ Файл сохранен: {scan_path}")

        # Обработка степени родства с поддержкой "Другое"
        relation_degree = request.form.get('relation_degree')
        if relation_degree == 'other':
            relation_degree = request.form.get('other_relation')

        # Создаем нового родственника со всеми полями
        relative = Relative(
            person_data_id=person.id,

            # Основные данные
            last_name=request.form.get('last_name'),
            first_name=request.form.get('first_name'),
            middle_name=request.form.get('middle_name'),
            birth_date=get_date('birth_date'),  # ИСПРАВЛЕНО
            registration_address=request.form.get('registration_address'),
            actual_address=request.form.get('actual_address'),
            phone=request.form.get('phone'),
            relation_degree=relation_degree,
            size=request.form.get('size'),

            # 98 У (П1)
            p1_in_number=request.form.get('p1_in_number'),
            p1_in_date=get_date('p1_in_date'),                                      # ИСПРАВЛЕНО
            p1_out_number=request.form.get('p1_out_number'),
            p1_out_date=get_date('p1_out_date'),                                    # ИСПРАВЛЕНО
            p1_pay_date=get_date('p1_pay_date'),                                    # ИСПРАВЛЕНО
            p1_size=request.form.get('p1_size'),
            p1_period_from=get_date('p1_period_from'),                              # ИСПРАВЛЕНО
            p1_period_to=get_date('p1_period_to'),                                  # ИСПРАВЛЕНО
            p1_period_indefinite=request.form.get('p1_period_indefinite') == 'true',
            p1_track_number=request.form.get('p1_track_number'),                     # НОВОЕ
            p1_track_date=get_date('p1_track_date'),                                 # НОВОЕ

            # 755-П2
            p2_in_number=request.form.get('p2_in_number'),
            p2_in_date=get_date('p2_in_date'),  # ИСПРАВЛЕНО
            p2_out_number=request.form.get('p2_out_number'),
            p2_out_date=get_date('p2_out_date'),  # ИСПРАВЛЕНО
            p2_pay_date=get_date('p2_pay_date'),  # ИСПРАВЛЕНО
            p2_size=request.form.get('p2_size'),
            p2_period_from=get_date('p2_period_from'),  # ИСПРАВЛЕНО
            p2_period_to=get_date('p2_period_to'),  # ИСПРАВЛЕНО
            p2_period_indefinite=request.form.get('p2_period_indefinite') == 'true',
            p2_track_number=request.form.get('p2_track_number'),  # НОВОЕ
            p2_track_date=get_date('p2_track_date'),              # НОВОЕ

            # 665()-П3
            p3_in_number=request.form.get('p3_in_number'),
            p3_in_date=get_date('p3_in_date'),  # ИСПРАВЛЕНО
            p3_out_number=request.form.get('p3_out_number'),
            p3_out_date=get_date('p3_out_date'),  # ИСПРАВЛЕНО
            p3_pay_date=get_date('p3_pay_date'),  # ИСПРАВЛЕНО
            p3_size=request.form.get('p3_size'),
            p3_period_from=get_date('p3_period_from'),  # ИСПРАВЛЕНО
            p3_period_to=get_date('p3_period_to'),  # ИСПРАВЛЕНО
            p3_period_indefinite=request.form.get('p3_period_indefinite') == 'true',
            p3_track_number=request.form.get('p3_track_number'),                  # НОВОЕ
            p3_track_date=get_date('p3_track_date'),                              # НОВОЕ

            # ДД-П4
            p4_in_number=request.form.get('p4_in_number'),
            p4_in_date=get_date('p4_in_date'),  # ИСПРАВЛЕНО
            p4_out_number=request.form.get('p4_out_number'),
            p4_out_date=get_date('p4_out_date'),  # ИСПРАВЛЕНО
            p4_pay_date=get_date('p4_pay_date'),  # ИСПРАВЛЕНО
            p4_size=request.form.get('p4_size'),
            p4_period_from=get_date('p4_period_from'),  # ИСПРАВЛЕНО
            p4_period_to=get_date('p4_period_to'),  # ИСПРАВЛЕНО
            p4_period_indefinite=request.form.get('p4_period_indefinite') == 'true',
            p4_track_number=request.form.get('p4_track_number'),                    # НОВОЕ
            p4_track_date=get_date('p4_track_date'),                                # НОВОЕ

            # К-П5
            p5_in_number=request.form.get('p5_in_number'),
            p5_in_date=get_date('p5_in_date'),  # ИСПРАВЛЕНО
            p5_out_number=request.form.get('p5_out_number'),
            p5_out_date=get_date('p5_out_date'),  # ИСПРАВЛЕНО
            p5_pay_date=get_date('p5_pay_date'),  # ИСПРАВЛЕНО
            p5_size=request.form.get('p5_size'),
            p5_period_from=get_date('p5_period_from'),  # ИСПРАВЛЕНО
            p5_period_to=get_date('p5_period_to'),  # ИСПРАВЛЕНО
            p5_period_indefinite=request.form.get('p5_period_indefinite') == 'true',
            p5_track_number=request.form.get('p5_track_number'),                   # НОВОЕ
            p5_track_date=get_date('p5_track_date'),                               # НОВОЕ

            # # Трек-номер
            # track_number=request.form.get('track_number'),
            # track_date=get_date('track_date'),  # ИСПРАВЛЕНО

            # Сканы
            scan_number=request.form.get('scan_number'),
            scan_date=get_date('scan_date'),  # ИСПРАВЛЕНО
            scan_path=scan_path
        )

        db.session.add(relative)
        db.session.commit()
        flash('✅ Родственник добавлен!', 'success')
        return redirect(url_for('manage_relatives', person_id=person.id))

    # Получаем всех родственников для этой записи
    relatives = Relative.query.filter_by(person_data_id=person.id).all()

    return render_template('relatives.html', person=person, relatives=relatives)

@app.route('/relative/edit/<int:relative_id>', methods=['GET', 'POST'])
@login_required
def edit_relative(relative_id):
    """Редактирование конкретного родственника"""
    relative = Relative.query.get_or_404(relative_id)
    person = relative.main_person

    if request.method == 'POST':
        # Функция для получения даты
        def get_date(field_name):
            date_str = request.form.get(field_name)
            if date_str:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return None
            return None

        # Собираем изменения
        changes = {}

        # Функция для проверки изменений с отладкой
        def check_change(field, form_value, cast_func=None):
            old = getattr(relative, field)
            if cast_func:
                new = cast_func(form_value)
            else:
                new = form_value if form_value else None

            print(f"🔍 Поле '{field}': старое='{old}' (тип: {type(old)}), новое='{new}' (тип: {type(new)})")

            if old != new:
                print(f"✅ ИЗМЕНЕНИЕ в поле '{field}'")
                changes[field] = {'old': old, 'new': new}
            else:
                print(f"⏺️ Без изменений в поле '{field}'")

            return new

        # Обновляем существующие данные
        relative.last_name = check_change('last_name', request.form.get('last_name'))
        relative.first_name = check_change('first_name', request.form.get('first_name'))
        relative.middle_name = check_change('middle_name', request.form.get('middle_name'))

        # Исправление для даты рождения
        birth_date_from_form = request.form.get('birth_date')
        if birth_date_from_form:
            new_birth_date = get_date('birth_date')
            if new_birth_date != relative.birth_date:
                changes['birth_date'] = {'old': relative.birth_date, 'new': new_birth_date}
                relative.birth_date = new_birth_date

        relative.registration_address = check_change('registration_address', request.form.get('registration_address'))
        relative.actual_address = check_change('actual_address', request.form.get('actual_address'))
        relative.phone = check_change('phone', request.form.get('phone'))

        # Обработка степени родства
        relation_degree = request.form.get('relation_degree')
        if relation_degree == 'other':
            relation_degree = request.form.get('other_relation')
        relative.relation_degree = check_change('relation_degree', relation_degree)

        relative.size = check_change('size', request.form.get('size'))

        # НОВЫЕ ПОЛЯ: 98 У (П1)
        relative.p1_in_number = check_change('p1_in_number', request.form.get('p1_in_number'))
        relative.p1_out_number = check_change('p1_out_number', request.form.get('p1_out_number'))
        relative.p1_size = check_change('p1_size', request.form.get('p1_size'))
        relative.p1_period_indefinite = request.form.get('p1_period_indefinite') == 'true'
        relative.p1_track_number = check_change('p1_track_number', request.form.get('p1_track_number'))  # НОВОЕ

        for field in ['p1_in_date', 'p1_out_date', 'p1_pay_date', 'p1_period_from', 'p1_period_to','p1_track_date']:
            value_from_form = request.form.get(field)
            if value_from_form:
                new_value = get_date(field)
                old_value = getattr(relative, field)
                if new_value != old_value:
                    changes[field] = {'old': old_value, 'new': new_value}
                    setattr(relative, field, new_value)

        # НОВЫЕ ПОЛЯ: 755-П2
        relative.p2_in_number = check_change('p2_in_number', request.form.get('p2_in_number'))
        relative.p2_out_number = check_change('p2_out_number', request.form.get('p2_out_number'))
        relative.p2_size = check_change('p2_size', request.form.get('p2_size'))
        relative.p2_period_indefinite = request.form.get('p2_period_indefinite') == 'true'
        relative.p2_track_number = check_change('p2_track_number', request.form.get('p2_track_number'))  # НОВОЕ


        for field in ['p2_in_date', 'p2_out_date', 'p2_pay_date', 'p2_period_from', 'p2_period_to','p2_track_date']:
            value_from_form = request.form.get(field)
            if value_from_form:
                new_value = get_date(field)
                old_value = getattr(relative, field)
                if new_value != old_value:
                    changes[field] = {'old': old_value, 'new': new_value}
                    setattr(relative, field, new_value)

        # НОВЫЕ ПОЛЯ: 665()-П3
        relative.p3_in_number = check_change('p3_in_number', request.form.get('p3_in_number'))
        relative.p3_out_number = check_change('p3_out_number', request.form.get('p3_out_number'))
        relative.p3_size = check_change('p3_size', request.form.get('p3_size'))
        relative.p3_period_indefinite = request.form.get('p3_period_indefinite') == 'true'
        relative.p3_track_number = check_change('p3_track_number', request.form.get('p3_track_number'))  # НОВОЕ


        for field in ['p3_in_date', 'p3_out_date', 'p3_pay_date', 'p3_period_from', 'p3_period_to','p3_track_date']:
            value_from_form = request.form.get(field)
            if value_from_form:
                new_value = get_date(field)
                old_value = getattr(relative, field)
                if new_value != old_value:
                    changes[field] = {'old': old_value, 'new': new_value}
                    setattr(relative, field, new_value)

        # НОВЫЕ ПОЛЯ: ДД-П4
        relative.p4_in_number = check_change('p4_in_number', request.form.get('p4_in_number'))
        relative.p4_out_number = check_change('p4_out_number', request.form.get('p4_out_number'))
        relative.p4_size = check_change('p4_size', request.form.get('p4_size'))
        relative.p4_period_indefinite = request.form.get('p4_period_indefinite') == 'true'
        relative.p4_track_number = check_change('p4_track_number', request.form.get('p4_track_number'))  # НОВОЕ


        for field in ['p4_in_date', 'p4_out_date', 'p4_pay_date', 'p4_period_from', 'p4_period_to','p4_track_date']:
            value_from_form = request.form.get(field)
            if value_from_form:
                new_value = get_date(field)
                old_value = getattr(relative, field)
                if new_value != old_value:
                    changes[field] = {'old': old_value, 'new': new_value}
                    setattr(relative, field, new_value)

        # НОВЫЕ ПОЛЯ: К-П5
        relative.p5_in_number = check_change('p5_in_number', request.form.get('p5_in_number'))
        relative.p5_out_number = check_change('p5_out_number', request.form.get('p5_out_number'))
        relative.p5_size = check_change('p5_size', request.form.get('p5_size'))
        relative.p5_period_indefinite = request.form.get('p5_period_indefinite') == 'true'
        relative.p5_track_number = check_change('p5_track_number', request.form.get('p5_track_number'))  # НОВОЕ


        for field in ['p5_in_date', 'p5_out_date', 'p5_pay_date', 'p5_period_from', 'p5_period_to','p5_track_date']:
            value_from_form = request.form.get(field)
            if value_from_form:
                new_value = get_date(field)
                old_value = getattr(relative, field)
                if new_value != old_value:
                    changes[field] = {'old': old_value, 'new': new_value}
                    setattr(relative, field, new_value)

        # # НОВЫЕ ПОЛЯ: Трек-номер
        # relative.track_number = check_change('track_number', request.form.get('track_number'))
        # track_date_from_form = request.form.get('track_date')
        # if track_date_from_form:
        #     new_track_date = get_date('track_date')
        #     if new_track_date != relative.track_date:
        #         changes['track_date'] = {'old': relative.track_date, 'new': new_track_date}
        #         relative.track_date = new_track_date

        # НОВЫЕ ПОЛЯ: Сканы
        relative.scan_number = check_change('scan_number', request.form.get('scan_number'))
        scan_date_from_form = request.form.get('scan_date')
        if scan_date_from_form:
            new_scan_date = get_date('scan_date')
            if new_scan_date != relative.scan_date:
                changes['scan_date'] = {'old': relative.scan_date, 'new': new_scan_date}
                relative.scan_date = new_scan_date

        # ОБРАБОТКА ЗАГРУЗКИ ФАЙЛА СКАНА - ВЫНЕСЕНА ИЗ БЛОКА scan_date
        # print("\n" + "=" * 70)
        # print("🔍 НАЧАЛО ОБРАБОТКИ ФАЙЛА СКАНА")
        # print(f"Все ключи в request.files: {list(request.files.keys())}")
        # print(f"Все ключи в request.form: {list(request.form.keys())}")

        if 'scan_file' in request.files:
            file = request.files['scan_file']
            # print(f"✅ Поле scan_file найдено")
            # print(f"  - filename: {file.filename}")

            if file and file.filename:
                # print(f"✅ Файл выбран: '{file.filename}'")

                # Проверяем размер файла
                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
                # print(f"  - размер файла: {file_size} байт")

                if allowed_file(file.filename):
                    # print(f"✅ Разрешенный тип файла")

                    filename = secure_filename(file.filename)
                    # print(f"  - безопасное имя: {filename}")

                    name, ext = os.path.splitext(filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    new_filename = f"relative_{relative.id}_{name}_{timestamp}{ext}"
                    # print(f"  - новое имя: {new_filename}")

                    # print(f"  - папка UPLOAD_FOLDER: {app.config['UPLOAD_FOLDER']}")
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    # print(f"  - папка создана/существует")

                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                    # print(f"  - полный путь: {file_path}")

                    try:
                        file.save(file_path)
                        # print(f"✅ Файл сохранен")

                        if os.path.exists(file_path):
                            file_size_saved = os.path.getsize(file_path)
                            # print(f"✅ Файл существует на диске, размер: {file_size_saved} байт")

                            old_path = relative.scan_path
                            relative.scan_path = f"uploads/scans/{new_filename}"
                            # print(f"  - старый путь: {old_path}")
                            # print(f"  - новый путь: {relative.scan_path}")

                            changes['scan_path'] = {'old': old_path, 'new': relative.scan_path}
                            # print(f"✅ Изменение добавлено в changes")
                        else:
                            print(f"❌ Файл НЕ найден на диске после сохранения!")

                    except Exception as e:
                        print(f"❌ ИСКЛЮЧЕНИЕ при сохранении файла: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    # print(f"❌ Недопустимый тип файла: {file.filename}")
                    # print(f"  - разрешенные типы: {ALLOWED_EXTENSIONS}")
                    flash('Недопустимый тип файла. Разрешены: png, jpg, jpeg, gif, pdf', 'warning')
            else:
                print(f"❌ Файл не выбран (filename пустой)")
        else:
            print(f"❌ Поле 'scan_file' ОТСУТСТВУЕТ в request.files")
            print(f"  - Возможно, форма не имеет enctype=multipart/form-data")
            print(f"  - Или имя поля другое")

        # print("=" * 70 + "\n")

        # Если есть изменения - сохраняем
        if changes:
            db.session.commit()
            save_relative_history(relative.id, current_user.id, changes)
            flash(f'✅ Данные родственника обновлены! Изменено полей: {len(changes)}', 'success')
        else:
            flash('Нет изменений для сохранения', 'info')

        return redirect(url_for('manage_relatives', person_id=person.id))

    return render_template('edit_relative.html', relative=relative, person=person)

@app.route('/uploads/<path:filename>')
@login_required
def download_file(filename):
    """Скачивание загруженного файла"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/relative/history/<int:relative_id>')
@login_required
@admin_required  # Только для администратора
def relative_history(relative_id):
    """Просмотр истории изменений родственника"""
    relative = Relative.query.get_or_404(relative_id)
    person = relative.main_person

    # Получаем все изменения для этого родственника
    history = RelativeHistory.query.filter_by(relative_id=relative_id) \
        .order_by(RelativeHistory.edited_at.desc()).all()

    # Группируем изменения по времени (с точностью до секунды)
    grouped = {}
    for entry in history:
        time_key = entry.edited_at.strftime('%Y-%m-%d %H:%M:%S')
        user_key = entry.user_id
        group_key = f"{time_key}_{user_key}"

        if group_key not in grouped:
            grouped[group_key] = {
                'edited_at': entry.edited_at,
                'user_name': entry.user.full_name or entry.user.username,
                'user_id': entry.user_id,
                'changes': []
            }

        # Формируем текст изменения
        field_names = {
            'last_name': 'Фамилия',
            'first_name': 'Имя',
            'middle_name': 'Отчество',
            'birth_date': 'Дата рождения',
            'registration_address': 'Адрес регистрации',
            'actual_address': 'Адрес проживания',
            'phone': 'Телефон',
            'relation_degree': 'Степень родства',
            'size': 'Размер',
            'period_assignment': 'Период назначения'
        }

        field_rus = field_names.get(entry.field_name, entry.field_name)
        old_val = entry.old_value if entry.old_value else 'пусто'
        new_val = entry.new_value if entry.new_value else 'пусто'

        grouped[group_key]['changes'].append({
            'field': field_rus,
            'old': old_val,
            'new': new_val,
            'display': f"{field_rus}: {old_val} → {new_val}",
            'short': f"{field_rus}: {old_val} → {new_val}"[:50]
        })

    # Преобразуем в список для шаблона
    grouped_history = []
    for group in grouped.values():
        grouped_history.append(group)

    # Сортируем по дате (сначала новые)
    grouped_history.sort(key=lambda x: x['edited_at'], reverse=True)

    return render_template('relative_history.html',
                           relative=relative,
                           person=person,
                           grouped_history=grouped_history)

@app.route('/relative/delete/<int:relative_id>', methods=['POST'])
@login_required
def delete_relative(relative_id):
    """Удаление родственника"""
    relative = Relative.query.get_or_404(relative_id)
    person_id = relative.person_data_id

    db.session.delete(relative)
    db.session.commit()
    flash('Родственник удален!', 'success')
    return redirect(url_for('manage_relatives', person_id=person_id))


@app.route('/person/<int:person_id>/awards', methods=['GET', 'POST'])
@login_required
def manage_awards(person_id):
    """Управление наградами для конкретной записи"""
    person = PersonData.query.get_or_404(person_id)
    relatives = Relative.query.filter_by(person_data_id=person.id).all()

    if request.method == 'POST':
        def get_date(field_name):
            date_str = request.form.get(field_name)
            if date_str:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return None
            return None

        award = Award(
            person_data_id=person.id,
            name=request.form.get('name'),
            number=request.form.get('number'),
            decree_number=request.form.get('decree_number'),
            decree_date=get_date('decree_date'),
            transferred_to=request.form.get('transferred_to'),
            transfer_date=get_date('transfer_date'),
            certificate_number=request.form.get('certificate_number'),
            certificate_transferred_to=request.form.get('certificate_transferred_to'),
            certificate_transfer_date=get_date('certificate_transfer_date')
        )

        db.session.add(award)
        db.session.commit()
        flash('✅ Награда добавлена!', 'success')
        return redirect(url_for('manage_awards', person_id=person.id))

    awards = Award.query.filter_by(person_data_id=person.id).all()
    return render_template('awards.html', person=person, relatives=relatives, awards=awards)

@app.route('/award/edit/<int:award_id>', methods=['GET', 'POST'])
@login_required
def edit_award(award_id):
    """Редактирование награды"""
    award = Award.query.get_or_404(award_id)
    person = award.person
    relatives = Relative.query.filter_by(person_data_id=person.id).all()

    if request.method == 'POST':
        def get_date(field_name):
            date_str = request.form.get(field_name)
            if date_str:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return None
            return None

        changes = {}

        # Функция для проверки изменений текстовых полей
        def check_change(field, form_value):
            old = getattr(award, field)
            new = form_value if form_value else None
            if old != new:
                changes[field] = {'old': old, 'new': new}
            return new

        # Функция для проверки изменений дат
        def check_date_change(field):
            old = getattr(award, field)
            new = get_date(field)
            if old != new:
                changes[field] = {'old': old, 'new': new}
                setattr(award, field, new)

        # Текстовые поля
        award.name = check_change('name', request.form.get('name'))
        award.number = check_change('number', request.form.get('number'))
        award.decree_number = check_change('decree_number', request.form.get('decree_number'))
        award.transferred_to = check_change('transferred_to', request.form.get('transferred_to'))
        award.certificate_number = check_change('certificate_number', request.form.get('certificate_number'))
        award.certificate_transferred_to = check_change('certificate_transferred_to', request.form.get('certificate_transferred_to'))

        # Даты - используем check_date_change
        check_date_change('decree_date')
        check_date_change('transfer_date')
        check_date_change('certificate_transfer_date')

        if changes:
            db.session.commit()
            # TODO: добавить историю для наград
            if not request.form.get('silent_save'):
                save_award_history(award.id, current_user.id, changes)
                flash(f'✅ Награда обновлена! Изменено полей: {len(changes)}', 'success')
        else:
            if not request.form.get('silent_save'):
                flash('Нет изменений для сохранения', 'info')

        return redirect(url_for('manage_awards', person_id=person.id))

    return render_template('edit_award.html', award=award, person=person, relatives=relatives)

@app.route('/award/delete/<int:award_id>', methods=['POST'])
@login_required
def delete_award(award_id):
    """Удаление награды"""
    award = Award.query.get_or_404(award_id)
    person_id = award.person_data_id

    db.session.delete(award)
    db.session.commit()
    flash('✅ Награда удалена!', 'success')
    return redirect(url_for('manage_awards', person_id=person_id))

def save_award_history(award_id, user_id, changes):
    """Сохраняет историю изменений награды"""
    for field_name, values in changes.items():
        if values['old'] != values['new']:
            history_entry = AwardHistory(
                award_id=award_id,
                user_id=user_id,
                field_name=field_name,
                old_value=str(values['old']) if values['old'] else '',
                new_value=str(values['new']) if values['new'] else ''
            )
            db.session.add(history_entry)
    db.session.commit()

@app.route('/person/<int:person_id>/ru', methods=['GET', 'POST'])
@login_required
def manage_ru(person_id):
    """Управление записью РУ (только одна запись)"""
    person = PersonData.query.get_or_404(person_id)
    relatives = Relative.query.filter_by(person_data_id=person.id).all()

    # Проверяем, есть ли уже запись
    ru_record = RuRecord.query.filter_by(person_data_id=person.id).first()

    if request.method == 'POST':
        def get_date(field_name):
            date_str = request.form.get(field_name)
            if date_str:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return None
            return None

        # Получаем ID выбранного родственника
        executor_id = request.form.get('executor')
        if executor_id:
            executor_id = int(executor_id)

        # Если записи нет - создаем новую
        if not ru_record:
            ru_record = RuRecord(
                person_data_id=person.id,
                executor_id=executor_id,
                executor_text=None,  # Больше не используется
                amount=float(request.form.get('amount')) if request.form.get('amount') else None,
                document_number=request.form.get('document_number'),
                document_date=get_date('document_date')
            )
            db.session.add(ru_record)
            db.session.commit()
            flash('✅ Запись РУ создана!', 'success')
        else:
            # Если запись есть - обновляем
            changes = {}

            # Проверяем изменения исполнителя
            if ru_record.executor_id != executor_id:
                old_executor = ru_record.executor_id
                ru_record.executor_id = executor_id
                changes['executor_id'] = {'old': old_executor, 'new': executor_id}

            # Сумма
            amount_str = request.form.get('amount')
            new_amount = float(amount_str) if amount_str else None
            if ru_record.amount != new_amount:
                changes['amount'] = {'old': ru_record.amount, 'new': new_amount}
                ru_record.amount = new_amount

            # Номер документа
            if ru_record.document_number != request.form.get('document_number'):
                changes['document_number'] = {'old': ru_record.document_number,
                                              'new': request.form.get('document_number')}
                ru_record.document_number = request.form.get('document_number')

            # Дата документа
            new_date = get_date('document_date')
            if ru_record.document_date != new_date:
                changes['document_date'] = {'old': ru_record.document_date, 'new': new_date}
                ru_record.document_date = new_date

            if changes:
                db.session.commit()
                flash(f'✅ Запись РУ обновлена! Изменено полей: {len(changes)}', 'success')
            else:
                flash('Нет изменений для сохранения', 'info')

        return redirect(url_for('manage_ru', person_id=person.id))

    return render_template('ru_records.html', person=person, relatives=relatives, ru_record=ru_record)

@app.route('/ru/edit/<int:ru_id>', methods=['GET', 'POST'])
@login_required
def edit_ru(ru_id):
    """Редактирование записи РУ"""
    ru = RuRecord.query.get_or_404(ru_id)
    person = ru.person

    if request.method == 'POST':
        def get_date(field_name):
            date_str = request.form.get(field_name)
            if date_str:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return None
            return None

        changes = {}

        def check_change(field, form_value):
            old = getattr(ru, field)
            new = form_value if form_value else None
            if old != new:
                changes[field] = {'old': old, 'new': new}
            return new

        def check_date_change(field):
            old = getattr(ru, field)
            new = get_date(field)
            if old != new:
                changes[field] = {'old': old, 'new': new}
                setattr(ru, field, new)

        ru.executor = check_change('executor', request.form.get('executor'))
        ru.document_number = check_change('document_number', request.form.get('document_number'))

        amount_str = request.form.get('amount')
        if amount_str:
            ru.amount = float(amount_str)
        else:
            ru.amount = None

        check_date_change('document_date')

        if changes:
            db.session.commit()
            flash(f'✅ Запись РУ обновлена! Изменено полей: {len(changes)}', 'success')
        else:
            flash('Нет изменений для сохранения', 'info')

        return redirect(url_for('manage_ru', person_id=person.id))

    return render_template('edit_ru.html', ru=ru, person=person)

@app.route('/ru/delete/<int:ru_id>', methods=['POST'])
@login_required
def delete_ru(ru_id):
    """Удаление записи РУ"""
    ru = RuRecord.query.get_or_404(ru_id)
    person_id = ru.person_data_id

    db.session.delete(ru)
    db.session.commit()
    flash('✅ Запись РУ удалена!', 'success')
    return redirect(url_for('manage_ru', person_id=person_id))

# ОТЧЕТЫ
@app.route('/report/r2026')
@login_required
def report_r2026():
    """Отчет Р2026 с данными основных записей и их родственников"""
    entries = PersonData.query.order_by(PersonData.id).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Отчет Р2026"

    # Заголовки
    headers = [
        '№ п/п',
        'Звание',
        'Должность',
        'Категория',
        'ФИО',
        'Номер',
        'Дата рождения',
        'Дата 2',
        'Дата 4',
        'Место 2',
        'ППР',
        'Степень родства',
        'ФИО родственника',
        'Дата рождения родственника',
        'Адрес регистрации',
        'Адрес проживания',
        'Телефон',
        '98 У (П1) Исх.',
        '98 У (П1) Вх.'
    ]
    ws.append(headers)

    row_counter = 1

    for entry in entries:
        # Получаем всех родственников для этой записи
        relatives = Relative.query.filter_by(person_data_id=entry.id).all()

        if relatives:
            # Для каждого родственника создаем отдельную строку
            for relative in relatives:
                # Формируем ФИО основной записи
                full_name = f"{entry.last_name or ''} {entry.first_name or ''} {entry.middle_name or ''}".strip()

                # Формируем ФИО родственника
                relative_full_name = f"{relative.last_name or ''} {relative.first_name or ''} {relative.middle_name or ''}".strip()

                # Формируем поля 98 У (П1)
                p1_out = f"{relative.p1_out_number or ''} {relative.p1_out_date.strftime('%d.%m.%Y') if relative.p1_out_date else ''}".strip()
                p1_in = f"{relative.p1_in_number or ''} {relative.p1_in_date.strftime('%d.%m.%Y') if relative.p1_in_date else ''}".strip()

                row = [
                    row_counter,  # № п/п
                    entry.rank or '',  # Звание
                    entry.position or '',  # Должность
                    entry.category or '',  # Категория
                    full_name,  # ФИО основной записи
                    entry.number or '',  # Номер
                    entry.birth_date.strftime('%d.%m.%Y') if entry.birth_date else '',  # Дата рождения
                    entry.date2.strftime('%d.%m.%Y') if entry.date2 else '',  # Дата 2
                    entry.date4.strftime('%d.%m.%Y') if entry.date4 else '',  # Дата 4
                    entry.place2 or '',  # Место 2
                    entry.ppr or '',  # ППР
                    relative.relation_degree or '',  # Степень родства
                    relative_full_name,  # ФИО родственника
                    relative.birth_date.strftime('%d.%m.%Y') if relative.birth_date else '',
                    # Дата рождения родственника
                    relative.registration_address or '',  # Адрес регистрации
                    relative.actual_address or '',  # Адрес проживания
                    relative.phone or '',  # Телефон
                    p1_out,  # 98 У (П1) Исх.
                    p1_in  # 98 У (П1) Вх.
                ]
                ws.append(row)
                row_counter += 1
        else:
            # Если нет родственников, создаем одну строку с пустыми полями родственника
            full_name = f"{entry.last_name or ''} {entry.first_name or ''} {entry.middle_name or ''}".strip()

            row = [
                row_counter,
                entry.rank or '',
                entry.position or '',
                entry.category or '',
                full_name,
                entry.number or '',
                entry.birth_date.strftime('%d.%m.%Y') if entry.birth_date else '',
                entry.date2.strftime('%d.%m.%Y') if entry.date2 else '',
                entry.date4.strftime('%d.%m.%Y') if entry.date4 else '',
                entry.place2 or '',
                entry.ppr or '',
                '',  # Степень родства
                '',  # ФИО родственника
                '',  # Дата рождения родственника
                '',  # Адрес регистрации
                '',  # Адрес проживания
                '',  # Телефон
                '',  # 98 У (П1) Исх.
                ''  # 98 У (П1) Вх.
            ]
            ws.append(row)
            row_counter += 1

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
        download_name=f'Р2026_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/report/t392')
@login_required
def report_t392():
    """Отчет Т-392 (заглушка)"""
    flash('Отчет Т-392 находится в разработке','warning')
    return redirect(url_for('dashboard'))


@app.route('/report/otchet66')
@login_required
def report_otchet66():
    """Отчет 66 (заглушка)"""
    flash('Отчет 66 находится в разработке','warning')
    return redirect(url_for('dashboard'))

@app.route('/report/form')
@login_required
def report_form():
    """Отчет Форма (заглушка)"""
    flash('Отчет Форма находится в разработке','warning')
    return redirect(url_for('dashboard'))

@app.route('/report/flag')
@login_required
def report_flag():
    """Отчет Флаг (заглушка)"""
    flash('Отчет Флаг находится в разработке','warning')
    return redirect(url_for('dashboard'))

@app.route('/report/zayavka')
@login_required
def report_zayavka():
    """Отчет Заявка (заглушка)"""
    flash('Отчет Заявка находится в разработке','warning')
    return redirect(url_for('dashboard'))

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