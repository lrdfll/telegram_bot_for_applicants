import os
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
import logging
import time
from threading import Thread, Lock
from collections import defaultdict
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
import sys
from datetime import datetime
import telebot
from telebot import types
from keys import Keys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Константы
TOKEN = Keys.TOKEN
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Инициализация бота
bot = telebot.TeleBot(TOKEN, parse_mode='HTML', threaded=True)

# Переменные для управления состоянием бота
bot_running = False
bot_thread = None

# Настройки подключения к базе данных с пулом соединений
DB_CONFIG = {
    'host': 'localhost',
    'database': 'bot',
    'user': 'root',
    'password': '0704',
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_general_ci',
    'pool_name': 'bot_pool',
    'pool_size': 10
}

# Инициализация пула соединений
try:
    db_pool = MySQLConnectionPool(**DB_CONFIG)
    logger.info("Пул соединений с базой данных успешно создан")
except Error as e:
    logger.error(f"Ошибка создания пула соединений: {e}")
    db_pool = None

# Базовая директория для изображений и документов
IMAGE_DIR = r'C:\Users\User\Desktop\bot\image'
DOC_DIR = r'C:\Users\User\Desktop\bot\docs'

# Пути к картинкам и документам
IMAGES = {
    'main': os.path.join(IMAGE_DIR, 'main_image.png'),
    'admission': os.path.join(IMAGE_DIR, 'admission.jpg'),
    'payment': os.path.join(IMAGE_DIR, 'payment.jpg'),
    'dormitory': os.path.join(IMAGE_DIR, 'dormitory.jpg'),
    'faq': os.path.join(IMAGE_DIR, 'faq.jpg'),
    'code_specialty': os.path.join(IMAGE_DIR, 'Код и наименование специальности.jpg'),
    'training_duration': os.path.join(IMAGE_DIR, 'Срок обучения по специальности.jpg'),
    'entrance_exams': os.path.join(IMAGE_DIR, 'Вступительные испытания.jpg'),
    'admission_places': os.path.join(IMAGE_DIR, 'Количество мест на бюджет и платку.jpg'),
    'admission_benefits': os.path.join(IMAGE_DIR, 'Льготы при поступлении.jpg'),
    'tuition_cost': os.path.join(IMAGE_DIR, 'Стоимость в год.jpg'),
    'payment_methods': os.path.join(IMAGE_DIR, 'Способы оплаты.jpg'),
    'payment_periods': os.path.join(IMAGE_DIR, 'Периоды оплаты.jpg'),
    'contract': os.path.join(IMAGE_DIR, 'Образец договора.jpg'),
    'dormitory_location': os.path.join(IMAGE_DIR, 'Расположение общежития.jpg'),
    'dormitory_cost': os.path.join(IMAGE_DIR, 'Стоимость проживания.jpg'),
    'dormitory_checkin': os.path.join(IMAGE_DIR, 'Порядок заселения.jpg')
}

DOCUMENTS = {
    'entrance_exams_9': os.path.join(DOC_DIR, 'Информация о формах проведения вступительных испытаний при приеме в ВятГУ.pdf'),
    'entrance_exams_11': os.path.join(DOC_DIR, 'Информация о формах проведения вступительных испытаний при приеме в ВятГУ.pdf'),
    'admission_places': os.path.join(DOC_DIR, 'Общее количество мест для приема по каждой специальности.pdf'),
    'contract_2side': os.path.join(DOC_DIR, 'Образец договора об оказании платных образовательных услуг - двухсторонний договор.pdf'),
    'contract_3side': os.path.join(DOC_DIR, 'Образец договора об оказании платных образовательных услуг - трехсторонний договор.pdf'),
    'dormitory_info': os.path.join(DOC_DIR, 'Информация по общежитию, необходимых документов и порядке заселения.pdf'),
    'dormitory_places': os.path.join(DOC_DIR, 'Информация о наличии общежития и количестве мест.pdf'),
    'admission_rules': os.path.join(DOC_DIR, 'Правила приема.pdf'),
}

# Загрузка картинок
images = {}
for key, path in IMAGES.items():
    try:
        with open(path, 'rb') as f:
            images[key] = f.read()
        logger.info(f"Картинка {key} успешно загружена")
    except Exception as error:
        logger.error(f"Ошибка загрузки картинки {key}: {error}")
        images[key] = None

# Хранение состояния пользователей
user_states = defaultdict(lambda: {
    'current_menu': 'main_menu',
    'grade': None,
    'section': None,
    'faq_index': -1,
    'search_results': None,
    'specialty_id': None,
    'menu_stack': []
})
user_states_lock = Lock()

class BotMenus:
    @staticmethod
    def create_menu(buttons):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for btn in buttons:
            markup.add(types.KeyboardButton(btn))
        return markup

    MAIN_MENU_BUTTONS = [
        "1. Информация для поступающих",
        "2. Информация об оплате",
        "3. Информация об общежитии",
        "4. Информация в рамках определённых специальностей",
        "5. Часто задаваемые вопросы"
    ]
    GRADE_MENU_BUTTONS = ["По окончании 9 классов", "По окончании 11 классов", "Назад"]
    ADMISSION_MENU_BUTTONS = [
        "1.1. Код и наименование специальности",
        "1.2. Срок обучения по специальностям",
        "1.3. Вступительные испытания",
        "1.4. Количество мест на бюджетной и платной основе",
        "1.5. Льготы, учитывающиеся при поступлении",
        "1.6. Нормативный документ с общими правилами приема",
        "Назад"
    ]
    PAYMENT_MENU_BUTTONS = [
        "2.1. Стоимость обучения в год",
        "2.2. Способы оплаты обучения",
        "2.3. Периоды оплаты",
        "2.4. Образец договора об оказании платных образовательных услуг",
        "Назад"
    ]
    DORMITORY_MENU_BUTTONS = [
        "3.1 Расположение общежития",
        "3.2 Стоимость проживания",
        "3.3 Порядок заселения",
        "3.4 Нормативные документы по заселению в общежитие",
        "Назад"
    ]

    MAIN_MENU = create_menu.__func__(MAIN_MENU_BUTTONS)
    GRADE_MENU = create_menu.__func__(GRADE_MENU_BUTTONS)
    ADMISSION_MENU = create_menu.__func__(ADMISSION_MENU_BUTTONS)
    PAYMENT_MENU = create_menu.__func__(PAYMENT_MENU_BUTTONS)
    DORMITORY_MENU = create_menu.__func__(DORMITORY_MENU_BUTTONS)
    NEXT_MENU = create_menu.__func__(["Далее", "Назад"])
    END_FAQ_MENU = create_menu.__func__(["Назад"])
    START_MENU = create_menu.__func__(["Начать"])

    MENU_TRANSITIONS = {
        'main_menu': {
            'next': None,
            'text': "🎉 Главное меню\n\nЕсли есть вопросы по использованию бота, используйте команду /help 🚀",
            'image': 'main',
            'section': None
        },
        'grade_menu': {
            'next': 'main_menu',
            'text': "🎓 Хотите узнать о поступлении или специальностях? Выберите класс:",
            'image': 'admission',
            'section': None
        },
        'admission_menu': {
            'next': 'grade_menu',
            'text': "📚 Всё о поступлении! Выберите интересующий раздел:",
            'image': 'admission',
            'section': 'admission'
        },
        'payment_menu': {
            'next': 'main_menu',
            'text': "💰 Всё об оплате обучения! Выберите раздел:",
            'image': 'payment',
            'section': 'payment'
        },
        'dormitory_menu': {
            'next': 'main_menu',
            'text': "🏠 Узнайте всё о жизни в общежитии! Выберите раздел:",
            'image': 'dormitory',
            'section': 'dormitory'
        },
        'search_menu': {
            'next': 'grade_menu',
            'text': "🎓 Выберите специальность для получения полной информации:",
            'image': 'admission',
            'section': 'search'
        },
        'specialty_info_menu': {
            'next': 'search_menu',
            'text': "🎓 Полная информация по специальности:",
            'image': None,
            'section': 'search'
        },
        'faq_menu': {
            'next': 'main_menu',
            'text': "❓ Ответы на популярные вопросы! Нажмите 'Далее' для первого вопроса",
            'image': 'faq',
            'section': 'faq'
        },
        'end_faq_menu': {
            'next': 'main_menu',
            'text': "🎉 Все вопросы рассмотрены!",
            'image': 'faq',
            'section': 'faq'
        }
    }

    MENU_OBJECTS = {
        'main_menu': MAIN_MENU,
        'grade_menu': GRADE_MENU,
        'admission_menu': ADMISSION_MENU,
        'payment_menu': PAYMENT_MENU,
        'dormitory_menu': DORMITORY_MENU,
        'search_menu': None,
        'specialty_info_menu': create_menu.__func__(["Назад"]),
        'faq_menu': NEXT_MENU,
        'end_faq_menu': END_FAQ_MENU,
        'start_menu': START_MENU
    }

class DatabaseHandler:
    @staticmethod
    def get_connection():
        try:
            connection = db_pool.get_connection()
            if connection.is_connected():
                return connection
        except Error as e:
            logger.error(f"Ошибка получения соединения из пула: {e}")
            return None
        return None

    @staticmethod
    def release_connection(connection, cursor):
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    @staticmethod
    def get_specialties(grade=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            if specialty_id:
                query = "SELECT Название_специальности, Код_специальности FROM специальности WHERE id_специальности = %s AND Класс = %s"
                cursor.execute(query, (specialty_id, grade))
            else:
                query = "SELECT Название_специальности, Код_специальности FROM специальности"
                if grade:
                    query += " WHERE Класс = %s"
                    cursor.execute(query, (grade,))
                else:
                    cursor.execute(query)
            result = cursor.fetchall()
            if not result:
                return "😕 Специальности пока не найдены!"
            response_text = "<b>Коды и названия специальностей</b> 🎓\n\n"
            for row in result:
                response_text += (
                    f"<b>Специальность:</b> {row[0]} 📚\n"
                    f"<b>Код:</b> {row[1]} 🔢\n"
                    "──────────\n"
                )
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_specialties: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_training_duration(grade=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            if specialty_id:
                query = """
                    SELECT s.Название_специальности, p.Срок_обучения 
                    FROM поступление p 
                    JOIN специальности s ON p.id_специальности = s.id_специальности
                    WHERE s.id_специальности = %s AND s.Класс = %s
                """
                cursor.execute(query, (specialty_id, grade))
            else:
                query = """
                    SELECT s.Название_специальности, p.Срок_обучения 
                    FROM поступление p 
                    JOIN специальности s ON p.id_специальности = s.id_специальности
                """
                if grade:
                    query += " WHERE s.Класс = %s"
                    cursor.execute(query, (grade,))
                else:
                    cursor.execute(query)
            result = cursor.fetchall()
            if not result:
                return "😕 Данные о сроках обучения пока не найдены!"
            response_text = "<b>Сроки обучения</b> ⏳\n\n"
            for row in result:
                response_text += (
                    f"<b>Специальность:</b> {row[0]} 🎓\n"
                    f"<b>Срок:</b> {row[1]} 📅\n"
                    "──────────\n"
                )
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_training_duration: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_entrance_exams(grade=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            if specialty_id:
                query = """
                    SELECT s.Название_специальности, e.Дата_вступительных, e.Проходной_балл 
                    FROM вступительные e 
                    JOIN специальности s ON e.id_специальности = s.id_специальности
                    WHERE s.id_специальности = %s AND s.Класс = %s
                """
                cursor.execute(query, (specialty_id, grade))
            else:
                query = """
                    SELECT s.Название_специальности, e.Дата_вступительных, e.Проходной_балл 
                    FROM вступительные e 
                    JOIN специальности s ON e.id_специальности = s.id_специальности
                """
                if grade:
                    query += " WHERE s.Класс = %s"
                    cursor.execute(query, (grade,))
                else:
                    cursor.execute(query)
            result = cursor.fetchall()
            if not result:
                return "<b>Вступительные испытания</b> 📝\n\nПо данной специальности вступительные испытания не проводятся.\n"
            response_text = "<b>Вступительные испытания</b> 📝\n\n"
            for row in result:
                date = row[1] if row[1] else 'Не указано'
                score = row[2] if row[2] else 'Не указано'
                response_text += (
                    f"<b>Специальность:</b> {row[0]} 🎓\n"
                    f"<b>Дата:</b> {date} 📅\n"
                    f"<b>Проходной балл:</b> {score} ⭐\n"
                    "──────────\n"
                )
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_entrance_exams: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_admission_places(grade=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            if grade == 11:
                if specialty_id:
                    query = "SELECT Название_специальности FROM специальности WHERE id_специальности = %s AND Класс = %s"
                    cursor.execute(query, (specialty_id, grade))
                else:
                    query = "SELECT Название_специальности FROM специальности WHERE Класс = %s"
                    cursor.execute(query, (grade,))
                result = cursor.fetchall()
                if not result:
                    return "😕 Данные о местах пока не найдены!"
                response_text = "<b>Места для поступления 🏫</b>\n\n"
                for row in result:
                    response_text += (
                        f"<b>Специальность:</b> {row[0]} 🎓\n"
                        f"<b>Бюджетных мест:</b> 0 🆓\n"
                        f"<b>Средний балл:</b> отсутствует ⭐️\n"
                        f"<b>Стипендия:</b> Нет 💸\n"
                        "──────────\n"
                    )
                return response_text
            else:
                if specialty_id:
                    query = """
                        SELECT s.Название_специальности, p.Количество_мест_на_бюджет, p.Средний_балл, p.Наличие_стипендии 
                        FROM поступление p 
                        JOIN специальности s ON p.id_специальности = s.id_специальности
                        WHERE s.id_специальности = %s AND s.Класс = %s
                    """
                    cursor.execute(query, (specialty_id, grade))
                else:
                    query = """
                        SELECT s.Название_специальности, p.Количество_мест_на_бюджет, p.Средний_балл, p.Наличие_стипендии 
                        FROM поступление p 
                        JOIN специальности s ON p.id_специальности = s.id_специальности
                    """
                    if grade:
                        query += " WHERE s.Класс = %s"
                        cursor.execute(query, (grade,))
                    else:
                        query.execute(query)
                result = cursor.fetchall()
                if not result:
                    return "😕 Данные о местах пока не найдены!"
                response_text = "<b>Места для поступления 🏫</b>\n\n"
                for row in result:
                    budget_places = row[1]
                    avg_score = row[2]
                    if avg_score is None or avg_score.strip() == '-' or avg_score.strip().lower() == 'не указано':
                        avg_score_display = 'отсутствует'
                    else:
                        try:
                            avg_score_clean = avg_score.replace(',', '.')
                            avg_score_float = float(avg_score_clean)
                            avg_score_display = f"{avg_score_float:.2f}".replace('.', ',')
                        except (ValueError, TypeError):
                            avg_score_display = 'отсутствует'
                    scholarship = row[3] if row[3] else 'Нет'
                    if row[0].lower().startswith("преподавание в начальных классах"):
                        scholarship = "Да"
                    response_text += (
                        f"<b>Специальность:</b> {row[0]} 🎓\n"
                        f"<b>Бюджетных мест:</b> {budget_places} 🆓\n"
                        f"<b>Средний балл:</b> {avg_score_display} ⭐️\n"
                        f"<b>Стипендия:</b> {scholarship} 💸\n"
                        "──────────\n"
                    )
                return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_admission_places: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_admission_benefits(grade=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT Ответ FROM вопросы WHERE Вопрос = 'Какие льготы есть при поступлении?'")
            result = cursor.fetchone()
            if not result:
                return "😕 Льготы для поступающих пока не найдены!"
            response_text = "<b>Льготы для поступающих</b> 🎉\n\n"
            benefits = result[0].split('; ')
            for benefit in benefits:
                response_text += f"✅ {benefit}\n"
            response_text += "──────────\n"
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_admission_benefits: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_tuition_cost(chat_id=None, specialty_id=None, ignore_specialty_id=False):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            query = """
                SELECT DISTINCT s.Название_специальности, c.Стоимость_в_год 
                FROM стоимость c 
                JOIN специальности s ON c.id_специальности = s.id_специальности
            """
            if specialty_id and not ignore_specialty_id:
                query += " WHERE c.id_специальности = %s"
                cursor.execute(query, (specialty_id,))
            else:
                cursor.execute(query)
            result = cursor.fetchall()
            if not result:
                return "😕 Данные о стоимости обучения пока не найдены!"
            response_text = "<b>Стоимость обучения</b> 💰\n\n"
            for row in result:
                response_text += (
                    f"<b>Специальность:</b> {row[0]} 🎓\n"
                    f"<b>Стоимость в год:</b> {row[1]} руб. 💸\n"
                    "──────────\n"
                )
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_tuition_cost: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_payment_methods(chat_id=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT DISTINCT Способы_оплаты FROM стоимость LIMIT 1")
            result = cursor.fetchone()
            if not result:
                return "😕 Данные о способах оплаты пока не найдены!"
            response_text = "<b>Как оплатить обучение</b> 💳\n\n"
            methods = result[0].split('; ')
            for method in methods:
                response_text += f"✅ {method}\n"
            response_text += "──────────\n"
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_payment_methods: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_payment_periods(chat_id=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT DISTINCT Период_оплаты FROM стоимость LIMIT 1")
            result = cursor.fetchone()
            if not result:
                return "😕 Данные о периодах оплаты пока не найдены!"
            response_text = "<b>Периоды оплаты</b> 📅\n\n"
            response_text += (
                f"<b>Вариант:</b> {result[0]} ⏰\n"
                "──────────\n"
            )
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_payment_periods: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_dormitory_location(chat_id=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT Расположение FROM общежитие LIMIT 1")
            result = cursor.fetchone()
            if not result:
                return "😕 Данные о расположении общежития пока не найдены!"
            response_text = "<b>Где находится общежитие</b> 🏠\n\n"
            response_text += f"<b>Адрес:</b> {result[0]} 📍\n──────────\n"
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_dormitory_location: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_dormitory_cost(chat_id=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT Стоимость FROM общежитие LIMIT 1")
            result = cursor.fetchone()
            if not result:
                return "😕 Данные о стоимости проживания пока не найдены!"
            response_text = "<b>Стоимость проживания</b> 💰\n\n"
            response_text += f"<b>Стоимость:</b> {result[0]} 🏠\n──────────\n"
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_dormitory_cost: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_dormitory_checkin_rules(chat_id=None, specialty_id=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return "😔 Ошибка подключения к базе данных. Попробуйте позже!"
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT Условия_предоставления FROM порядок_заселения LIMIT 1")
            result = cursor.fetchone()
            if not result:
                return "😕 Данные о порядке заселения пока не найдены!"
            response_text = "<b>Как заселиться в общежитие</b> 🏠\n\n"
            condition = result[0] if result[0] else "Нет данных"
            formatted_condition = (
                "<b>Условия предоставления общежития</b>\n\n"
                "Место в общежитии предоставляется:\n"
                "✅ Иногородним студентам, проживающим более чем в 50 км от г. Кирова.\n"
                "✅ Студентам, проживающим более чем в 30 км от г. Кирова при отсутствии прямого транспортного сообщения.\n\n"
                "Для получения места необходимо указать потребность в общежитии при подаче заявления.\n"
                "──────────\n"
            )
            response_text += formatted_condition
            return response_text
        except Error as e:
            logger.error(f"Ошибка SQL в get_dormitory_checkin_rules: {e}")
            return f"😔 Произошла ошибка при загрузке данных. Попробуйте снова!"
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_faq_list():
        connection = DatabaseHandler.get_connection()
        if not connection:
            return []
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT Вопрос, Ответ FROM вопросы")
            result = cursor.fetchall()
            if not result:
                return []
            faq_list = [(row[0], row[1]) for row in result]
            return faq_list
        except Error as e:
            logger.error(f"Ошибка при получении FAQ: {e}")
            return []
        finally:
            DatabaseHandler.release_connection(connection, cursor)

    @staticmethod
    def get_all_specialties(grade=None):
        connection = DatabaseHandler.get_connection()
        if not connection:
            return []
        cursor = None
        try:
            cursor = connection.cursor()
            query = "SELECT id_специальности, Название_специальности, Код_специальности, Класс FROM специальности"
            if grade:
                query += " WHERE Класс = %s"
                cursor.execute(query, (grade,))
            else:
                cursor.execute(query)
            result = cursor.fetchall()
            return [(row[0], row[1], row[2], row[3]) for row in result]
        except Error as e:
            logger.error(f"Ошибка при получении списка специальностей: {e}")
            return []
        finally:
            DatabaseHandler.release_connection(connection, cursor)

class BotHandler:
    @staticmethod
    def check_file_size(file_path):
        try:
            size = os.path.getsize(file_path)
            if size > MAX_FILE_SIZE:
                logger.warning(f"Файл слишком большой: {size} байт ({file_path})")
                return False
            return True
        except Exception as e:
            logger.error(f"Ошибка проверки размера файла: {e}")
            return False

    @staticmethod
    def split_text(text, max_length=4096):
        parts = []
        current_part = ""
        for line in text.split("\n"):
            if len(current_part) + len(line) + 1 <= max_length:
                current_part += line + "\n"
            else:
                if current_part:
                    parts.append(current_part.strip())
                current_part = line + "\n"
        if current_part:
            parts.append(current_part.strip())
        return parts

    @staticmethod
    def get_full_specialty_info(chat_id, specialty_id, grade):
        info = []
        info.append(DatabaseHandler.get_specialties(grade, specialty_id))
        info.append(DatabaseHandler.get_training_duration(grade, specialty_id))
        info.append(DatabaseHandler.get_entrance_exams(grade, specialty_id))
        info.append(DatabaseHandler.get_admission_places(grade, specialty_id))
        info.append(DatabaseHandler.get_admission_benefits(grade, specialty_id))
        info.append(DatabaseHandler.get_tuition_cost(chat_id, specialty_id))
        return "\n".join(info)

    @staticmethod
    def create_search_menu(specialties):
        buttons = [spec[1] for spec in specialties] + ["Назад"]
        return BotMenus.create_menu(buttons)

    @staticmethod
    def send_document_with_retry(chat_id, document_path, menu=None, retries=3, initial_delay=2):
        delay = initial_delay
        loading_message = bot.send_message(
            chat_id,
            "⌛ Пожалуйста, подождите, идет загрузка документа...",
            reply_markup=None
        )
        for attempt in range(retries):
            try:
                if not BotHandler.check_file_size(document_path):
                    bot.delete_message(chat_id, loading_message.message_id)
                    bot.send_message(
                        chat_id,
                        f"⚠ Файл слишком большой: {os.path.basename(document_path)}\nМаксимальный размер: 50MB",
                        reply_markup=menu
                    )
                    return False
                with open(document_path, 'rb') as doc:
                    bot.send_document(
                        chat_id,
                        doc,
                        timeout=30,
                        caption=f"📄 {os.path.basename(document_path)}"
                    )
                    logger.info(f"Документ {document_path} успешно отправлен")
                    bot.delete_message(chat_id, loading_message.message_id)
                    return True
            except Exception as e:
                logger.error(f"Попытка {attempt + 1}/{retries}: Ошибка при отправке документа {document_path}: {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    bot.delete_message(chat_id, loading_message.message_id)
                    bot.send_message(
                        chat_id,
                        f"⚠ Не удалось отправить документ. Попробуйте позже!\nФайл: {os.path.basename(document_path)}",
                        reply_markup=menu
                    )
                    return False
        bot.delete_message(chat_id, loading_message.message_id)
        return False

    @staticmethod
    def send_message_with_image(message, text, image, menu):
        try:
            if image:
                bot.send_photo(message.chat.id, image, caption=text, reply_markup=menu)
            else:
                bot.send_message(message.chat.id, text, reply_markup=menu)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения с изображением: {e}")
            try:
                bot.send_message(message.chat.id, text, reply_markup=menu)
            except Exception as e2:
                logger.error(f"Не удалось отправить даже текстовое сообщение: {e2}")

    @staticmethod
    def send_message_with_attachment(message, text, image=None, document_path=None, menu=None):
        chat_id = message.chat.id
        text_parts = BotHandler.split_text(text, max_length=4096)
        try:
            if image and len(text) <= 1024:
                bot.send_photo(chat_id, image, caption=text, reply_markup=menu)
            else:
                for part in text_parts:
                    bot.send_message(chat_id, part, reply_markup=menu)
            if document_path:
                if callable(document_path):
                    document_path = document_path(chat_id)
                if isinstance(document_path, list):
                    for doc in document_path:
                        BotHandler.send_document_with_retry(chat_id, doc, menu)
                else:
                    BotHandler.send_document_with_retry(chat_id, document_path, menu)
        except Exception as e:
            logger.error(f"Критическая ошибка при отправке сообщения: {e}")
            try:
                bot.send_message(chat_id, "⚠ Произошла ошибка. Попробуйте позже!", reply_markup=menu)
            except:
                logger.critical("Не удалось отправить даже сообщение об ошибке")

    @staticmethod
    def send_message_with_documents(message, text, image, document_paths, menu=None):
        chat_id = message.chat.id
        try:
            BotHandler.send_message_with_attachment(message, text, image, None, menu)
            if callable(document_paths):
                document_paths = document_paths(chat_id)
            if isinstance(document_paths, list):
                for doc_path in document_paths:
                    BotHandler.send_document_with_retry(chat_id, doc_path, menu)
            else:
                BotHandler.send_document_with_retry(chat_id, document_paths, menu)
        except Exception as e:
            logger.error(f"Ошибка при отправке документов: {e}")

    @staticmethod
    def send_dormitory_location(chat_id, text, image, menu):
        try:
            bot.send_photo(chat_id, image, caption=text, reply_markup=menu)
            twogis_link = "https://2gis.ru/kirov/geo/8163302605632622"
            bot.send_message(chat_id, f"🗺️ Посмотрите точное расположение общежития №1 на карте:\n<a href='{twogis_link}'>Открыть в 2GIS</a>")
            logger.info("Ссылка на 2GIS отправлена")
        except Exception as e:
            logger.error(f"Ошибка при отправке расположения общежития: {e}")
            bot.send_message(chat_id, text, reply_markup=menu)

# Определение ответов
response = {
    "1. Информация для поступающих": {
        "text": "🎓 Хотите узнать о поступлении? Выберите класс:",
        "image": images['admission'],
        "menu": 'grade_menu',
        "section": "admission"
    },
    "2. Информация об оплате": {
        "text": "💰 Всё об оплате обучения! Выберите раздел:",
        "image": images['payment'],
        "menu": 'payment_menu',
        "section": "payment"
    },
    "3. Информация об общежитии": {
        "text": "🏠 Узнайте всё о жизни в общежитии! Выберите раздел:",
        "image": images['dormitory'],
        "menu": 'dormitory_menu',
        "section": "dormitory"
    },
    "4. Информация в рамках определённых специальностей": {
        "text": "🎓 Ищете информацию по специальностям? Выберите класс:",
        "menu": 'grade_menu',
        "section": "search"
    },
    "5. Часто задаваемые вопросы": {
        "text": "❓ Ответы на популярные вопросы! Нажмите 'Далее' для первого вопроса",
        "image": images['faq'],
        "menu": 'faq_menu',
        "section": "faq"
    },
    "1.1. Код и наименование специальности": {
        "text": lambda chat_id: DatabaseHandler.get_specialties(user_states[chat_id].get('grade'), user_states[chat_id].get('specialty_id')),
        "image": images['code_specialty'],
        "menu": 'admission_menu'
    },
    "1.2. Срок обучения по специальностям": {
        "text": lambda chat_id: DatabaseHandler.get_training_duration(user_states[chat_id].get('grade'), user_states[chat_id].get('specialty_id')),
        "image": images['training_duration'],
        "menu": 'admission_menu'
    },
    "1.3. Вступительные испытания": {
        "text": lambda chat_id: DatabaseHandler.get_entrance_exams(user_states[chat_id].get('grade'), user_states[chat_id].get('specialty_id')),
        "image": images['entrance_exams'],
        "document": lambda chat_id: DOCUMENTS['entrance_exams_9'] if user_states[chat_id].get('grade') == 9 else DOCUMENTS['entrance_exams_11'],
        "menu": 'admission_menu'
    },
    "1.4. Количество мест на бюджетной и платной основе": {
        "text": lambda chat_id: DatabaseHandler.get_admission_places(user_states[chat_id].get('grade'), user_states[chat_id].get('specialty_id')),
        "image": images['admission_places'],
        "document": DOCUMENTS['admission_places'],
        "menu": 'admission_menu'
    },
    "1.5. Льготы, учитывающиеся при поступлении": {
        "text": lambda chat_id: DatabaseHandler.get_admission_benefits(user_states[chat_id].get('grade'), user_states[chat_id].get('specialty_id')),
        "image": images['admission_benefits'],
        "menu": 'admission_menu'
    },
    "1.6. Нормативный документ с общими правилами приема": {
        "text": "<b>Правила приема</b> 📜\n\nОзнакомьтесь с официальным документом ниже!\n──────────\n",
        "document": DOCUMENTS['admission_rules'],
        "menu": 'admission_menu'
    },
    "2.1. Стоимость обучения в год": {
        "text": lambda chat_id: DatabaseHandler.get_tuition_cost(chat_id, ignore_specialty_id=True),
        "image": images['tuition_cost'],
        "menu": 'payment_menu'
    },
    "2.2. Способы оплаты обучения": {
        "text": lambda chat_id: DatabaseHandler.get_payment_methods(chat_id, user_states[chat_id].get('specialty_id')),
        "image": images['payment_methods'],
        "menu": 'payment_menu'
    },
    "2.3. Периоды оплаты": {
        "text": lambda chat_id: DatabaseHandler.get_payment_periods(chat_id, user_states[chat_id].get('specialty_id')),
        "image": images['payment_periods'],
        "menu": 'payment_menu'
    },
    "2.4. Образец договора об оказании платных образовательных услуг": {
        "text": "<b>Образец договора</b> 📝\n\n✅ Двухсторонний договор\n✅ Трехсторонний договор\n──────────\n",
        "image": images['contract'],
        "documents": [
            DOCUMENTS['contract_2side'],
            DOCUMENTS['contract_3side']
        ],
        "menu": 'payment_menu'
    },
    "3.1 Расположение общежития": {
        "text": lambda chat_id: DatabaseHandler.get_dormitory_location(chat_id),
        "image": images['dormitory_location'],
        "menu": 'dormitory_menu',
        "special": "location"
    },
    "3.2 Стоимость проживания": {
        "text": lambda chat_id: DatabaseHandler.get_dormitory_cost(chat_id),
        "image": images['dormitory_cost'],
        "menu": 'dormitory_menu'
    },
    "3.3 Порядок заселения": {
        "text": lambda chat_id: DatabaseHandler.get_dormitory_checkin_rules(chat_id),
        "image": images['dormitory_checkin'],
        "menu": 'dormitory_menu'
    },
    "3.4 Нормативные документы по заселению в общежитие": {
        "text": "<b>Документы по общежитию</b> 🏠\n\nОзнакомьтесь с правилами заселения ниже!\n──────────\n",
        "documents": [
            DOCUMENTS['dormitory_info'],
            DOCUMENTS['dormitory_places']
        ],
        "menu": 'dormitory_menu'
    }
}

# Обработчики команд
@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    with user_states_lock:
        user_states[chat_id] = {
            'current_menu': 'main_menu',
            'grade': None,
            'section': None,
            'faq_index': -1,
            'search_results': None,
            'specialty_id': None,
            'menu_stack': []
        }
    welcome_text = (
        "🎉 Добро пожаловать в бот ВятГУ! Выберите раздел, чтобы узнать всё о поступлении, оплате или общежитии!\n\n"
        "Если есть вопросы по использованию бота, используйте команду /help 🚀"
    )
    BotHandler.send_message_with_image(message, welcome_text, images['main'], BotMenus.MENU_OBJECTS['main_menu'])
    logger.info(f"Пользователь {chat_id} вызвал команду /start")

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """
    <b>Команды бота</b> 🤖
    /start — Начать работу
    /stop — Завершить работу бота

    <b>Как пользоваться</b> 📋
    ✅ Выберите раздел в главном меню
    ✅ Для поступления укажите класс (9 или 11)
    ✅ Для поиска специальностей выберите класс и специальность
    ✅ Нажмите "Назад" для возврата
    ✅ Используйте /stop для завершения
    """
    bot.send_message(message.chat.id, help_text, reply_markup=BotMenus.MENU_OBJECTS['main_menu'])

@bot.message_handler(commands=['stop'])
def stop_command(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "👋 Работа завершена. До встречи!")
    bot.send_message(chat_id, "Нажмите 'Начать', чтобы вернуться", reply_markup=BotMenus.MENU_OBJECTS['start_menu'])
    with user_states_lock:
        if chat_id in user_states:
            del user_states[chat_id]

@bot.message_handler(func=lambda m: m.text == "Начать")
def restart(message):
    chat_id = message.chat.id
    with user_states_lock:
        user_states[chat_id] = {
            'current_menu': 'main_menu',
            'grade': None,
            'section': None,
            'faq_index': -1,
            'search_results': None,
            'specialty_id': None,
            'menu_stack': []
        }
    welcome_text = (
        "🎉 Добро пожаловать в бот ВятГУ! Выберите раздел, чтобы узнать всё о поступлении, оплате или общежитии!\n\n"
        "Если есть вопросы по использованию бота, используйте команду /help 🚀"
    )
    BotHandler.send_message_with_image(message, welcome_text, images['main'], BotMenus.MENU_OBJECTS['main_menu'])
    logger.info(f"Пользователь {chat_id} перезапустил бота через кнопку 'Начать'")

@bot.message_handler(func=lambda m: m.text in ["По окончании 9 классов", "По окончании 11 классов"])
def handle_grade_selection(message):
    chat_id = message.chat.id
    with user_states_lock:
        if chat_id not in user_states:
            user_states[chat_id] = {
                'current_menu': 'main_menu',
                'grade': None,
                'section': None,
                'faq_index': -1,
                'search_results': None,
                'specialty_id': None,
                'menu_stack': []
            }
        state = user_states[chat_id]
    
    grade = 9 if message.text == "По окончании 9 классов" else 11
    state['grade'] = grade
    section = state.get('section')
    logger.info(f"Пользователь {chat_id} выбрал класс {grade}, текущий раздел: {section}")

    if section == "admission":
        state['current_menu'] = 'admission_menu'
        state['menu_stack'] = ['main_menu', 'grade_menu']
        state['specialty_id'] = None
        state['search_results'] = None
        BotHandler.send_message_with_image(
            message,
            BotMenus.MENU_TRANSITIONS['admission_menu']['text'],
            images['admission'],
            BotMenus.MENU_OBJECTS['admission_menu']
        )
    elif section == "search":
        all_specialties = DatabaseHandler.get_all_specialties(grade)
        if not all_specialties:
            bot.send_message(chat_id, "😕 Специальности для этого класса пока не найдены.", reply_markup=BotMenus.MENU_OBJECTS['main_menu'])
            with user_states_lock:
                user_states[chat_id] = {
                    'current_menu': 'main_menu',
                    'grade': None,
                    'section': None,
                    'faq_index': -1,
                    'search_results': None,
                    'specialty_id': None,
                    'menu_stack': []
                }
            logger.warning(f"Специальности для класса {grade} не найдены")
            return
        state['search_results'] = all_specialties
        state['current_menu'] = 'search_menu'
        state['menu_stack'] = ['main_menu', 'grade_menu']
        state['specialty_id'] = None
        search_menu = BotHandler.create_search_menu(all_specialties)
        BotMenus.MENU_OBJECTS['search_menu'] = search_menu
        BotHandler.send_message_with_image(
            message,
            BotMenus.MENU_TRANSITIONS['search_menu']['text'],
            images['admission'],
            search_menu
        )
        logger.info(f"Меню специальностей для класса {grade} отправлено")
    else:
        state['section'] = "admission"
        state['current_menu'] = 'admission_menu'
        state['menu_stack'] = ['main_menu', 'grade_menu']
        state['specialty_id'] = None
        state['search_results'] = None
        BotHandler.send_message_with_image(
            message,
            BotMenus.MENU_TRANSITIONS['admission_menu']['text'],
            images['admission'],
            BotMenus.MENU_OBJECTS['admission_menu']
        )
        logger.info(f"Открыт раздел admission для пользователя {chat_id}")

@bot.message_handler(func=lambda m: m.text == "Назад")
def handle_back(message):
    chat_id = message.chat.id
    with user_states_lock:
        if chat_id not in user_states:
            user_states[chat_id] = {
                'current_menu': 'main_menu',
                'grade': None,
                'section': None,
                'faq_index': -1,
                'search_results': None,
                'specialty_id': None,
                'menu_stack': []
            }
        state = user_states[chat_id]
    
    current_menu = state['current_menu']

    if current_menu == 'specialty_info_menu':
        next_menu_key = 'search_menu'
        state['current_menu'] = next_menu_key
        state['menu_stack'] = ['main_menu', 'grade_menu']
        state['specialty_id'] = None
        search_menu = BotHandler.create_search_menu(state['search_results'])
        BotMenus.MENU_OBJECTS['search_menu'] = search_menu
        BotHandler.send_message_with_image(
            message,
            BotMenus.MENU_TRANSITIONS[next_menu_key]['text'],
            images[BotMenus.MENU_TRANSITIONS[next_menu_key]['image']],
            search_menu
        )
        return

    if current_menu == 'search_menu':
        next_menu_key = 'grade_menu'
        state['current_menu'] = next_menu_key
        state['menu_stack'] = ['main_menu']
        state['grade'] = None
        state['search_results'] = None
        state['specialty_id'] = None
        BotHandler.send_message_with_image(
            message,
            BotMenus.MENU_TRANSITIONS[next_menu_key]['text'],
            images[BotMenus.MENU_TRANSITIONS[next_menu_key]['image']],
            BotMenus.MENU_OBJECTS[next_menu_key]
        )
        return

    if current_menu in ['faq_menu', 'end_faq_menu']:
        next_menu_key = 'main_menu'
        state['current_menu'] = next_menu_key
        state['menu_stack'] = []
        state['faq_index'] = -1
        state['section'] = None
        state['grade'] = None
        state['specialty_id'] = None
        state['search_results'] = None
        BotHandler.send_message_with_image(
            message,
            BotMenus.MENU_TRANSITIONS[next_menu_key]['text'],
            images[BotMenus.MENU_TRANSITIONS[next_menu_key]['image']],
            BotMenus.MENU_OBJECTS[next_menu_key]
        )
        return

    menu_info = BotMenus.MENU_TRANSITIONS.get(current_menu)
    if not menu_info or not menu_info['next']:
        with user_states_lock:
            user_states[chat_id] = {
                'current_menu': 'main_menu',
                'grade': None,
                'section': None,
                'faq_index': -1,
                'search_results': None,
                'specialty_id': None,
                'menu_stack': []
            }
        BotHandler.send_message_with_image(
            message,
            BotMenus.MENU_TRANSITIONS['main_menu']['text'],
            images[BotMenus.MENU_TRANSITIONS['main_menu']['image']],
            BotMenus.MENU_OBJECTS['main_menu']
        )
        return

    next_menu_key = menu_info['next']
    next_menu_info = BotMenus.MENU_TRANSITIONS[next_menu_key]
    state['current_menu'] = next_menu_key
    state['section'] = next_menu_info['section']

    if next_menu_key in ['main_menu', 'grade_menu']:
        state['grade'] = None
        state['specialty_id'] = None
        state['search_results'] = None
        state['faq_index'] = -1
        state['menu_stack'] = [] if next_menu_key == 'main_menu' else ['main_menu']

    image_key = next_menu_info['image']
    BotHandler.send_message_with_image(
        message,
        next_menu_info['text'],
        images[image_key] if image_key else None,
        BotMenus.MENU_OBJECTS[next_menu_key]
    )

@bot.message_handler(func=lambda m: m.text == "Далее" and user_states.get(m.chat.id, {}).get('section') == "faq")
def handle_faq_next(message):
    chat_id = message.chat.id
    with user_states_lock:
        state = user_states[chat_id]
    faq_list = DatabaseHandler.get_faq_list()
    if not faq_list:
        bot.send_message(chat_id, "😕 Вопросы не найдены.", reply_markup=BotMenus.MENU_OBJECTS['main_menu'])
        with user_states_lock:
            user_states[chat_id] = {
                'current_menu': 'main_menu',
                'grade': None,
                'section': None,
                'faq_index': -1,
                'search_results': None,
                'specialty_id': None,
                'menu_stack': []
            }
        return
    state['faq_index'] += 1
    current_index = state['faq_index']
    if current_index < len(faq_list):
        question, answer = faq_list[current_index]
        response_text = f"<b>❓ Вопрос:</b> {question}\n<b>✅ Ответ:</b> {answer}\n──────────\n"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(types.KeyboardButton("Далее"), types.KeyboardButton("Назад"))
        BotHandler.send_message_with_image(message, response_text, images['faq'], markup)
    else:
        end_text = (
            "🎉 Все вопросы рассмотрены!\n\n"
            "Остались вопросы? Звоните в приемную комиссию:\n"
            "📞 +7 (8332) 742-400\n"
            "📧 pk@vyatsu.ru\n"
            "──────────\n"
        )
        state['current_menu'] = 'end_faq_menu'
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(types.KeyboardButton("Назад"))
        BotHandler.send_message_with_image(message, end_text, images['faq'], markup)

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    try:
        chat_id = message.chat.id
        text = message.text

        with user_states_lock:
            if chat_id not in user_states:
                user_states[chat_id] = {
                    'current_menu': 'main_menu',
                    'grade': None,
                    'section': None,
                    'faq_index': -1,
                    'search_results': None,
                    'specialty_id': None,
                    'menu_stack': []
                }
            state = user_states[chat_id]

        if state['current_menu'] == 'search_menu' and state['section'] == 'search' and text != "Назад":
            specialties = state.get('search_results', [])
            selected_specialty = next((spec for spec in specialties if spec[1] == text), None)
            if selected_specialty:
                specialty_id, specialty_name, _, _ = selected_specialty
                state['specialty_id'] = specialty_id
                state['current_menu'] = 'specialty_info_menu'
                state['menu_stack'] = ['main_menu', 'grade_menu', 'search_menu']
                full_info = BotHandler.get_full_specialty_info(chat_id, specialty_id, state['grade'])
                BotHandler.send_message_with_attachment(
                    message,
                    full_info,
                    None,
                    None,
                    BotMenus.MENU_OBJECTS['specialty_info_menu']
                )
                logger.info(f"Полная информация по специальности '{specialty_name}' отправлена")
                return
            else:
                bot.send_message(chat_id, "🤔 Пожалуйста, выберите специальность из списка!", reply_markup=BotMenus.MENU_OBJECTS['search_menu'])
                return

        if text in response:
            data = response[text]
            state['section'] = data.get('section')

            if text == "5. Часто задаваемые вопросы":
                state['faq_index'] = -1
                state['current_menu'] = data['menu']
                state['menu_stack'] = ['main_menu']
                BotHandler.send_message_with_image(message, data['text'], data['image'], BotMenus.MENU_OBJECTS[data['menu']])
                return

            if text == "1. Информация для поступающих":
                state['current_menu'] = data['menu']
                state['menu_stack'] = ['main_menu']
                state['grade'] = None
                state['specialty_id'] = None
                state['search_results'] = None
                BotHandler.send_message_with_image(message, data['text'], data['image'], BotMenus.MENU_OBJECTS[data['menu']])
                return

            if text == "4. Информация в рамках определённых специальностей":
                state['current_menu'] = data['menu']
                state['menu_stack'] = ['main_menu']
                state['grade'] = None
                state['specialty_id'] = None
                state['search_results'] = None
                bot.send_message(chat_id, data['text'], reply_markup=BotMenus.MENU_OBJECTS[data['menu']])
                return

            if text.startswith('1.') and not state['grade']:
                bot.send_message(chat_id, "📚 Пожалуйста, выберите класс (9 или 11).", reply_markup=BotMenus.MENU_OBJECTS['grade_menu'])
                return

            response_text = data['text'](chat_id) if callable(data['text']) else data['text']
            current_menu = data.get('menu')

            if text.startswith('1.') and text != "1. Информация для поступающих":
                state['menu_stack'] = ['main_menu', 'grade_menu', 'admission_menu']
            else:
                state['menu_stack'] = ['main_menu'] if current_menu in ['payment_menu', 'dormitory_menu', 'faq_menu'] else state['menu_stack']

            state['current_menu'] = current_menu

            if 'special' in data and data['special'] == 'location':
                BotHandler.send_dormitory_location(chat_id, response_text, data.get('image'), BotMenus.MENU_OBJECTS[current_menu])
            elif 'documents' in data:
                BotHandler.send_message_with_documents(message, response_text, data.get('image'), data['documents'], BotMenus.MENU_OBJECTS[current_menu])
            else:
                document_path = data.get('document')
                if callable(document_path):
                    document_path = document_path(chat_id)
                BotHandler.send_message_with_attachment(message, response_text, data.get('image'), document_path, BotMenus.MENU_OBJECTS[current_menu])

        else:
            bot.send_message(chat_id, "🤔 Пожалуйста, выберите раздел из меню!", reply_markup=BotMenus.MENU_OBJECTS['main_menu'])
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения для пользователя {chat_id}: {e}")
        try:
            bot.send_message(
                chat_id,
                "😔 Произошла ошибка. Попробуйте позже!",
                reply_markup=BotMenus.MENU_OBJECTS['main_menu']
            )
        except:
            logger.critical("Не удалось отправить даже сообщение об ошибке")

def run_bot():
    global bot_running
    bot_running = True
    logger.info("Бот запущен")
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        logger.error(f"Ошибка в работе бота: {e}")
    finally:
        bot_running = False
        logger.info("Бот остановлен")

def stop_bot():
    global bot_running, bot_thread
    if bot_running and bot_thread:
        bot.stop_polling()
        bot_running = False
        if bot_thread.is_alive():
            bot_thread.join(timeout=5)
        with user_states_lock:
            user_states.clear()  # Очистка всех состояний пользователей
        logger.info("Бот успешно остановлен и состояния пользователей очищены")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Управление Telegram-ботом")
        self.setFixedSize(900, 600)
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #F7B3FDFF, stop: 1 #FFA318FF
                );
            }
        """)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        icon_path = r"C:\Users\User\Desktop\bot\image\icon.jpg"
        self.setWindowIcon(QIcon(icon_path))
        screen = QApplication.desktop().screenGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
        self.start_button = QPushButton("Включить бота", self)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: green;
                color: white;
                font-size: 16px;
                border-radius: 100px;
                border: none;
            }
            QPushButton:hover {
                background-color: #006400;
            }
            QPushButton:pressed {
                background-color: darkgreen;
            }
        """)
        self.start_button.setFixedSize(200, 200)
        self.start_button.move(150, 250)
        self.start_button.clicked.connect(self.start_bot)
        self.stop_button = QPushButton("Выключить бота", self)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: red;
                color: white;
                font-size: 16px;
                border-radius: 100px;
                border: none;
            }
            QPushButton:hover {
                background-color: #8B0000;
            }
            QPushButton:pressed {
                background-color: darkred;
            }
        """)
        self.stop_button.setFixedSize(200, 200)
        self.stop_button.move(550, 250)
        self.stop_button.clicked.connect(self.stop_bot)
        self.status_label = QLabel("Бот выключен", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 25px; color: red; font-weight: bold;")
        self.status_label.setGeometry(0, 50, 900, 50)
        self.time_label = QLabel("Последнее действие: -", self)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("font-size: 20px; color: black;")
        self.time_label.setGeometry(0, 100, 900, 50)

    def start_bot(self):
        global bot_running, bot_thread
        if not bot_running:
            if bot_thread and bot_thread.is_alive():
                stop_bot()
            bot_thread = Thread(target=run_bot)
            bot_thread.daemon = True
            bot_thread.start()
            self.status_label.setText("Бот запущен")
            self.status_label.setStyleSheet("font-size: 25px; color: green; font-weight: bold;")
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.time_label.setText(f"Бот включен: {current_time}")
            logger.info("Бот запущен через интерфейс")
        else:
            logger.info("Бот уже запущен")

    def stop_bot(self):
        global bot_running, bot_thread
        if bot_running:
            self.status_label.setText("Бот останавливается...")
            self.status_label.setStyleSheet("font-size: 25px; color: orange; font-weight: bold;")
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.time_label.setText(f"Остановка начата: {current_time}")
            QApplication.processEvents()
            stop_bot()
            time.sleep(2)
            self.status_label.setText("Бот выключен")
            self.status_label.setStyleSheet("font-size: 25px; color: red; font-weight: bold;")
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.time_label.setText(f"Бот выключен: {current_time}")
            logger.info("Бот остановлен через интерфейс")
            bot_thread = None
        else:
            logger.info("Бот уже остановлен")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())