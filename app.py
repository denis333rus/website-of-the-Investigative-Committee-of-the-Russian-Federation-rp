from datetime import datetime
import os
import requests

from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, current_app
from sqlalchemy import text
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart



BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'site.db')


def create_app():
	app = Flask(__name__)
	app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret-key')
	app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
	app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
	app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads')
	app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

	db.init_app(app)

	with app.app_context():
		db.create_all()
		ensure_schema_updates()
		os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
		ensure_initial_admin()
		ensure_site_info()

	register_routes(app)
	return app


db = SQLAlchemy()


class AdminUser(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	username = db.Column(db.String(80), unique=True, nullable=False)
	password_hash = db.Column(db.String(255), nullable=False)
	role = db.Column(db.String(50), default='investigator', nullable=False)
	full_name = db.Column(db.String(150), nullable=True)
	position = db.Column(db.String(100), nullable=True)
	rank = db.Column(db.String(100), nullable=True)

	def set_password(self, password: str) -> None:
		self.password_hash = generate_password_hash(password)

	def check_password(self, password: str) -> bool:
		return check_password_hash(self.password_hash, password)


class News(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	title = db.Column(db.String(200), nullable=False)
	content = db.Column(db.Text, nullable=False)
	is_published = db.Column(db.Boolean, default=True, nullable=False)
	image_url = db.Column(db.String(255), nullable=True)
	parent_id = db.Column(db.Integer, nullable=True)
	created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
	updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SiteInfo(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	leader_first_name = db.Column(db.String(100), nullable=True)
	leader_last_name = db.Column(db.String(100), nullable=True)
	leader_rank = db.Column(db.String(150), nullable=True)
	leader_position = db.Column(db.String(150), nullable=True)
	leader_photo_url = db.Column(db.String(255), nullable=True)


class Feedback(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	full_name = db.Column(db.String(150), nullable=False)
	email = db.Column(db.String(150), nullable=True)
	phone = db.Column(db.String(50), nullable=True)
	message = db.Column(db.Text, nullable=False)
	status = db.Column(db.String(20), default='new', nullable=False)  # new, in_progress, done
	created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Notification(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	title = db.Column(db.String(200), nullable=False)
	message = db.Column(db.Text, nullable=False)
	is_read = db.Column(db.Boolean, default=False, nullable=False)
	created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
	feedback_id = db.Column(db.Integer, nullable=True)  # Link to feedback if applicable


class JobApplication(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	full_name = db.Column(db.String(150), nullable=False)
	desired_username = db.Column(db.String(80), nullable=False)
	desired_password = db.Column(db.String(255), nullable=False)
	question1 = db.Column(db.Text, nullable=False)  # Почему хотите работать в СК РФ?
	question2 = db.Column(db.Text, nullable=False)  # Опыт работы
	question3 = db.Column(db.Text, nullable=False)  # Дополнительная информация
	question4 = db.Column(db.Text, nullable=True)  # Образование
	question5 = db.Column(db.Text, nullable=True)  # Навыки и компетенции
	question6 = db.Column(db.Text, nullable=True)  # Мотивация и цели
	question7 = db.Column(db.Text, nullable=True)  # Готовность к командировкам
	question8 = db.Column(db.Text, nullable=True)  # Дополнительные вопросы
	status = db.Column(db.String(20), default='pending', nullable=False)  # pending, approved, rejected
	created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Review(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	author_name = db.Column(db.String(150), nullable=False)
	rating = db.Column(db.Integer, nullable=False)  # 1-5 звезд
	title = db.Column(db.String(200), nullable=False)
	content = db.Column(db.Text, nullable=False)
	status = db.Column(db.String(20), default='pending', nullable=False)  # pending, approved, rejected
	created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Document(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	title = db.Column(db.String(200), nullable=False)
	content = db.Column(db.Text, nullable=False)
	document_type = db.Column(db.String(50), nullable=False)  # постановление, протокол, и т.д.
	author_id = db.Column(db.Integer, db.ForeignKey('admin_user.id'), nullable=False)
	status = db.Column(db.String(20), default='pending', nullable=False)  # pending, approved, rejected
	file_url = db.Column(db.String(255), nullable=True)  # ссылка на файл
	approved_by_id = db.Column(db.Integer, db.ForeignKey('admin_user.id'), nullable=True)
	created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
	approved_at = db.Column(db.DateTime, nullable=True)
	
	# Relationships
	author = db.relationship('AdminUser', foreign_keys=[author_id], backref='authored_documents')
	approved_by = db.relationship('AdminUser', foreign_keys=[approved_by_id], backref='approved_documents')


def ensure_initial_admin() -> None:
	if not AdminUser.query.first():
		admin = AdminUser(username='denis333rus')
		admin.set_password('qmzpal12')
		admin.role = 'admin'
		admin.full_name = 'ИВАНОВ ИВАН ИВАНОВИЧ'
		admin.position = 'Руководитель следственного управления'
		admin.rank = 'Полковник юстиции'
		db.session.add(admin)
		db.session.commit()
	else:
		# Ensure existing admin has proper data
		admin = AdminUser.query.filter_by(username='denis333rus').first()
		if admin and not admin.full_name:
			admin.full_name = 'ИВАНОВ ИВАН ИВАНОВИЧ'
			admin.position = 'Руководитель следственного управления'
			admin.rank = 'Полковник юстиции'
			db.session.commit()


def ensure_site_info() -> None:
	if not SiteInfo.query.first():
		db.session.add(SiteInfo())
		db.session.commit()


def ensure_schema_updates() -> None:
	"""Apply minimal in-place schema updates for SQLite when models change.

	Currently ensures `leader_photo_url` exists on `site_info`.
	"""
	# Ensure the table exists before introspection
	db.session.execute(text('CREATE TABLE IF NOT EXISTS site_info (id INTEGER PRIMARY KEY)'))
	# Inspect current columns for site_info
	pragma_rows = db.session.execute(text('PRAGMA table_info(site_info)')).all()
	existing_columns = {row[1] for row in pragma_rows}
	# Add missing column without dropping data
	if 'leader_photo_url' not in existing_columns:
		db.session.execute(text('ALTER TABLE site_info ADD COLUMN leader_photo_url VARCHAR(255)'))
		db.session.commit()

	# Ensure News.image_url exists
	db.session.execute(text('CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY)'))
	news_cols = db.session.execute(text('PRAGMA table_info(news)')).all()
	news_existing = {row[1] for row in news_cols}
	if 'image_url' not in news_existing:
		db.session.execute(text('ALTER TABLE news ADD COLUMN image_url VARCHAR(255)'))
		db.session.commit()
	if 'parent_id' not in news_existing:
		db.session.execute(text('ALTER TABLE news ADD COLUMN parent_id INTEGER'))
		db.session.commit()

	# Ensure feedback table exists (create_all will also handle, but be explicit)
	db.session.execute(text('CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT, message TEXT, status TEXT, created_at TEXT)'))
	
	# Ensure notification table exists
	db.session.execute(text('CREATE TABLE IF NOT EXISTS notification (id INTEGER PRIMARY KEY, title TEXT, message TEXT, is_read BOOLEAN, created_at TEXT, feedback_id INTEGER)'))
	
	# Ensure job_application table exists
	db.session.execute(text('CREATE TABLE IF NOT EXISTS job_application (id INTEGER PRIMARY KEY, full_name TEXT, desired_username TEXT, desired_password TEXT, question1 TEXT, question2 TEXT, question3 TEXT, status TEXT, created_at TEXT)'))
	
	# Add new question columns to job_application table
	job_app_cols = db.session.execute(text('PRAGMA table_info(job_application)')).all()
	job_app_existing = {row[1] for row in job_app_cols}
	if 'question4' not in job_app_existing:
		db.session.execute(text('ALTER TABLE job_application ADD COLUMN question4 TEXT'))
		db.session.commit()
	if 'question5' not in job_app_existing:
		db.session.execute(text('ALTER TABLE job_application ADD COLUMN question5 TEXT'))
		db.session.commit()
	if 'question6' not in job_app_existing:
		db.session.execute(text('ALTER TABLE job_application ADD COLUMN question6 TEXT'))
		db.session.commit()
	if 'question7' not in job_app_existing:
		db.session.execute(text('ALTER TABLE job_application ADD COLUMN question7 TEXT'))
		db.session.commit()
	if 'question8' not in job_app_existing:
		db.session.execute(text('ALTER TABLE job_application ADD COLUMN question8 TEXT'))
		db.session.commit()
	
	# Ensure review table exists
	db.session.execute(text('CREATE TABLE IF NOT EXISTS review (id INTEGER PRIMARY KEY, author_name TEXT, rating INTEGER, title TEXT, content TEXT, status TEXT, created_at TEXT)'))
	
	# Ensure document table exists
	db.session.execute(text('CREATE TABLE IF NOT EXISTS document (id INTEGER PRIMARY KEY, title TEXT, content TEXT, document_type TEXT, author_id INTEGER, status TEXT, file_url TEXT, approved_by_id INTEGER, created_at TEXT, approved_at TEXT)'))

	# Ensure AdminUser.role exists
	db.session.execute(text('CREATE TABLE IF NOT EXISTS admin_user (id INTEGER PRIMARY KEY)'))
	admin_cols = db.session.execute(text('PRAGMA table_info(admin_user)')).all()
	admin_existing = {row[1] for row in admin_cols}
	if 'role' not in admin_existing:
		db.session.execute(text("ALTER TABLE admin_user ADD COLUMN role VARCHAR(50) DEFAULT 'investigator'"))
		db.session.commit()
	if 'full_name' not in admin_existing:
		db.session.execute(text('ALTER TABLE admin_user ADD COLUMN full_name VARCHAR(150)'))
		db.session.commit()
	if 'position' not in admin_existing:
		db.session.execute(text('ALTER TABLE admin_user ADD COLUMN position VARCHAR(100)'))
		db.session.commit()
	if 'rank' not in admin_existing:
		db.session.execute(text('ALTER TABLE admin_user ADD COLUMN rank VARCHAR(100)'))
		db.session.commit()


def send_notification_to_all_roles(feedback_item):
	"""Send notification about new feedback to all admin users"""
	try:
		# Create internal notification for all users
		notification = Notification(
			title=f"Новое заявление #{feedback_item.id}",
			message=f"Поступило заявление от {feedback_item.full_name}",
			feedback_id=feedback_item.id
		)
		db.session.add(notification)
		db.session.commit()
		
		# Optional: External notifications (if configured)
		# Email notification (if configured)
		email_enabled = os.environ.get('SMTP_ENABLED', 'false').lower() == 'true'
		if email_enabled:
			users = AdminUser.query.all()
			send_email_notification(feedback_item, users)
		
		# Discord webhook (if configured)
		discord_webhook = os.environ.get('DISCORD_WEBHOOK_URL')
		if discord_webhook:
			send_discord_notification(feedback_item, discord_webhook)
		
		# Telegram bot (if configured)
		telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
		telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
		if telegram_bot_token and telegram_chat_id:
			send_telegram_notification(feedback_item, telegram_bot_token, telegram_chat_id)
			
	except Exception as e:
		print(f"Notification error: {e}")


def send_email_notification(feedback_item, users):
	"""Send email notification to all users"""
	try:
		smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
		smtp_port = int(os.environ.get('SMTP_PORT', '587'))
		smtp_username = os.environ.get('SMTP_USERNAME')
		smtp_password = os.environ.get('SMTP_PASSWORD')
		
		if not smtp_username or not smtp_password:
			return
			
		msg = MIMEMultipart()
		msg['From'] = smtp_username
		msg['Subject'] = f"Новое заявление #{feedback_item.id} - СК РФ"
		
		body = f"""
Новое заявление в интернет-приёмной СК РФ

ID: {feedback_item.id}
ФИО: {feedback_item.full_name}
Email: {feedback_item.email or 'не указан'}
Телефон: {feedback_item.phone or 'не указан'}
Дата: {feedback_item.created_at.strftime('%d.%m.%Y %H:%M')}

Текст заявления:
{feedback_item.message}

Для просмотра: {request.url_root}admin/feedback/{feedback_item.id}
		"""
		
		msg.attach(MIMEText(body, 'plain', 'utf-8'))
		
		# Send to all users (you might want to add email field to AdminUser)
		user_emails = [user.username + '@example.com' for user in users]  # Placeholder
		
		server = smtplib.SMTP(smtp_server, smtp_port)
		server.starttls()
		server.login(smtp_username, smtp_password)
		
		for email in user_emails:
			msg['To'] = email
			server.send_message(msg)
			del msg['To']
		
		server.quit()
	except Exception as e:
		print(f"Email notification error: {e}")


def send_discord_notification(feedback_item, webhook_url):
	"""Send Discord webhook notification"""
	try:
		embed = {
			"title": f"Новое заявление #{feedback_item.id}",
			"color": 0xff0000,  # Red color
			"fields": [
				{"name": "ФИО", "value": feedback_item.full_name, "inline": True},
				{"name": "Дата", "value": feedback_item.created_at.strftime('%d.%m.%Y %H:%M'), "inline": True},
				{"name": "Текст", "value": feedback_item.message[:1000] + ("..." if len(feedback_item.message) > 1000 else ""), "inline": False}
			],
			"footer": {"text": "СК РФ - Интернет-приёмная"}
		}
		
		payload = {"embeds": [embed]}
		requests.post(webhook_url, json=payload, timeout=10)
	except Exception as e:
		print(f"Discord notification error: {e}")


def send_telegram_notification(feedback_item, bot_token, chat_id):
	"""Send Telegram notification"""
	try:
		message = f"""🚨 *Новое заявление #{feedback_item.id}*

👤 *ФИО:* {feedback_item.full_name}
📅 *Дата:* {feedback_item.created_at.strftime('%d.%m.%Y %H:%M')}

📝 *Текст:*
{feedback_item.message[:1000]}{"..." if len(feedback_item.message) > 1000 else ""}

🔗 [Открыть в админке]({request.url_root}admin/feedback/{feedback_item.id})
		"""
		
		url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
		payload = {
			"chat_id": chat_id,
			"text": message,
			"parse_mode": "Markdown"
		}
		requests.post(url, json=payload, timeout=10)
	except Exception as e:
		print(f"Telegram notification error: {e}")


def send_review_notification_to_all_roles(review_item):
	"""Send notification about new review to all admin users"""
	try:
		# Create internal notification for all users
		notification = Notification(
			title=f"Новый отзыв #{review_item.id}",
			message=f"Поступил отзыв от {review_item.author_name} (оценка: {review_item.rating}/5)",
			feedback_id=None  # Reviews don't have feedback_id
		)
		db.session.add(notification)
		db.session.commit()
		
		# Optional: External notifications (if configured)
		# Email notification (if configured)
		email_enabled = os.environ.get('SMTP_ENABLED', 'false').lower() == 'true'
		if email_enabled:
			users = AdminUser.query.all()
			send_review_email_notification(review_item, users)
		
		# Discord webhook (if configured)
		discord_webhook = os.environ.get('DISCORD_WEBHOOK_URL')
		if discord_webhook:
			send_review_discord_notification(review_item, discord_webhook)
		
		# Telegram bot (if configured)
		telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
		telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
		if telegram_bot_token and telegram_chat_id:
			send_review_telegram_notification(review_item, telegram_bot_token, telegram_chat_id)
			
	except Exception as e:
		print(f"Review notification error: {e}")


def send_review_email_notification(review_item, users):
	"""Send email notification about new review to all users"""
	try:
		# Email configuration
		smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
		smtp_port = int(os.environ.get('SMTP_PORT', '587'))
		smtp_username = os.environ.get('SMTP_USERNAME')
		smtp_password = os.environ.get('SMTP_PASSWORD')
		
		if not all([smtp_username, smtp_password]):
			return
		
		# Create message
		msg = MIMEMultipart()
		msg['From'] = smtp_username
		msg['Subject'] = f"Новый отзыв на сайте СК РФ"
		
		body = f"""
		Поступил новый отзыв:
		
		Автор: {review_item.author_name}
		Оценка: {review_item.rating}/5
		Заголовок: {review_item.title}
		Содержание: {review_item.content}
		
		Дата: {review_item.created_at.strftime('%d.%m.%Y %H:%M')}
		"""
		
		msg.attach(MIMEText(body, 'plain', 'utf-8'))
		
		# Send to all users
		for user in users:
			if user.username:  # Assuming email is stored in username or separate field
				msg['To'] = user.username
				server = smtplib.SMTP(smtp_server, smtp_port)
				server.starttls()
				server.login(smtp_username, smtp_password)
				server.send_message(msg)
				server.quit()
				
	except Exception as e:
		print(f"Review email notification error: {e}")


def send_review_discord_notification(review_item, webhook_url):
	"""Send Discord webhook notification about new review"""
	try:
		embed = {
			"title": "Новый отзыв на сайте СК РФ",
			"description": f"**Автор:** {review_item.author_name}\n**Оценка:** {review_item.rating}/5 ⭐\n**Заголовок:** {review_item.title}",
			"color": 0x00ff00,  # Green color
			"fields": [
				{
					"name": "Содержание",
					"value": review_item.content[:1000] + "..." if len(review_item.content) > 1000 else review_item.content,
					"inline": False
				}
			],
			"footer": {
				"text": f"Дата: {review_item.created_at.strftime('%d.%m.%Y %H:%M')}"
			}
		}
		
		payload = {"embeds": [embed]}
		response = requests.post(webhook_url, json=payload)
		response.raise_for_status()
		
	except Exception as e:
		print(f"Review Discord notification error: {e}")


def send_review_telegram_notification(review_item, bot_token, chat_id):
	"""Send Telegram notification about new review"""
	try:
		message = f"""
🆕 *Новый отзыв на сайте СК РФ*

👤 *Автор:* {review_item.author_name}
⭐ *Оценка:* {review_item.rating}/5
📝 *Заголовок:* {review_item.title}

📄 *Содержание:*
{review_item.content}

📅 *Дата:* {review_item.created_at.strftime('%d.%m.%Y %H:%M')}
		"""
		
		url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
		payload = {
			"chat_id": chat_id,
			"text": message,
			"parse_mode": "Markdown"
		}
		
		response = requests.post(url, json=payload)
		response.raise_for_status()
		
	except Exception as e:
		print(f"Review Telegram notification error: {e}")


def send_document_notification_to_all_roles(document_item):
	"""Send notification about new document to all admin users"""
	try:
		# Create internal notification for all users
		notification = Notification(
			title=f"Новый документ #{document_item.id}",
			message=f"Поступил документ '{document_item.title}' от {document_item.author.full_name}",
			feedback_id=None  # Documents don't have feedback_id
		)
		db.session.add(notification)
		db.session.commit()
		
		# Optional: External notifications (if configured)
		# Email notification (if configured)
		email_enabled = os.environ.get('SMTP_ENABLED', 'false').lower() == 'true'
		if email_enabled:
			users = AdminUser.query.all()
			send_document_email_notification(document_item, users)
		
		# Discord webhook (if configured)
		discord_webhook = os.environ.get('DISCORD_WEBHOOK_URL')
		if discord_webhook:
			send_document_discord_notification(document_item, discord_webhook)
		
		# Telegram bot (if configured)
		telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
		telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
		if telegram_bot_token and telegram_chat_id:
			send_document_telegram_notification(document_item, telegram_bot_token, telegram_chat_id)
			
	except Exception as e:
		print(f"Document notification error: {e}")


def send_document_email_notification(document_item, users):
	"""Send email notification about new document to all users"""
	try:
		# Email configuration
		smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
		smtp_port = int(os.environ.get('SMTP_PORT', '587'))
		smtp_username = os.environ.get('SMTP_USERNAME')
		smtp_password = os.environ.get('SMTP_PASSWORD')
		
		if not all([smtp_username, smtp_password]):
			return
		
		# Create message
		msg = MIMEMultipart()
		msg['From'] = smtp_username
		msg['Subject'] = f"Новый документ в СК РФ"
		
		body = f"""
		Поступил новый документ:
		
		Название: {document_item.title}
		Тип: {document_item.document_type}
		Автор: {document_item.author.full_name}
		Содержание: {document_item.content[:200]}...
		
		Дата: {document_item.created_at.strftime('%d.%m.%Y %H:%M')}
		"""
		
		msg.attach(MIMEText(body, 'plain', 'utf-8'))
		
		# Send to all users
		for user in users:
			if user.username:  # Assuming email is stored in username or separate field
				msg['To'] = user.username
				server = smtplib.SMTP(smtp_server, smtp_port)
				server.starttls()
				server.login(smtp_username, smtp_password)
				server.send_message(msg)
				server.quit()
				
	except Exception as e:
		print(f"Document email notification error: {e}")


def send_document_discord_notification(document_item, webhook_url):
	"""Send Discord webhook notification about new document"""
	try:
		embed = {
			"title": "Новый документ в СК РФ",
			"description": f"**Название:** {document_item.title}\n**Тип:** {document_item.document_type}\n**Автор:** {document_item.author.full_name}",
			"color": 0x0066cc,  # Blue color
			"fields": [
				{
					"name": "Содержание",
					"value": document_item.content[:1000] + "..." if len(document_item.content) > 1000 else document_item.content,
					"inline": False
				}
			],
			"footer": {
				"text": f"Дата: {document_item.created_at.strftime('%d.%m.%Y %H:%M')}"
			}
		}
		
		payload = {"embeds": [embed]}
		response = requests.post(webhook_url, json=payload)
		response.raise_for_status()
		
	except Exception as e:
		print(f"Document Discord notification error: {e}")


def send_document_telegram_notification(document_item, bot_token, chat_id):
	"""Send Telegram notification about new document"""
	try:
		message = f"""
📄 *Новый документ в СК РФ*

📝 *Название:* {document_item.title}
📋 *Тип:* {document_item.document_type}
👤 *Автор:* {document_item.author.full_name}

📄 *Содержание:*
{document_item.content[:500]}{'...' if len(document_item.content) > 500 else ''}

📅 *Дата:* {document_item.created_at.strftime('%d.%m.%Y %H:%M')}
		"""
		
		url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
		payload = {
			"chat_id": chat_id,
			"text": message,
			"parse_mode": "Markdown"
		}
		
		response = requests.post(url, json=payload)
		response.raise_for_status()
		
	except Exception as e:
		print(f"Document Telegram notification error: {e}")


def login_required(view_func):
	def wrapper(*args, **kwargs):
		if not session.get('admin_logged_in'):
			flash('Требуется вход в админ-панель', 'warning')
			return redirect(url_for('admin_login', next=request.path))
		return view_func(*args, **kwargs)
	wrapper.__name__ = view_func.__name__
	return wrapper


def register_routes(app: Flask) -> None:
	@app.context_processor
	def inject_site_info():
		site = SiteInfo.query.first()
		# Get unread notifications count for logged in users
		unread_count = 0
		current_user = None
		if session.get('admin_logged_in'):
			unread_count = Notification.query.filter_by(is_read=False).count()
			username = session.get('admin_username')
			current_user = AdminUser.query.filter_by(username=username).first()
		return dict(site=site, unread_notifications=unread_count, current_user=current_user)

	@app.route('/')
	def index():
		news = News.query.filter_by(is_published=True, parent_id=None).order_by(News.created_at.desc()).all()
		return render_template('index.html', news=news)

	@app.route('/feedback', methods=['GET', 'POST'])
	def feedback():
		if request.method == 'POST':
			full_name = request.form.get('full_name', '').strip()
			email = request.form.get('email', '').strip() or None
			phone = request.form.get('phone', '').strip() or None
			message = request.form.get('message', '').strip()
			if not full_name or not message:
				flash('Укажите ФИО и текст заявления', 'warning')
				return render_template('feedback.html', full_name=full_name, email=email, phone=phone, message=message)
			item = Feedback(full_name=full_name, email=email, phone=phone, message=message)
			db.session.add(item)
			db.session.commit()
			# Send notifications to all roles
			send_notification_to_all_roles(item)
			flash('Заявление отправлено. Мы свяжемся с вами при необходимости.', 'success')
			return redirect(url_for('feedback'))
		return render_template('feedback.html')

	@app.route('/job-application', methods=['GET', 'POST'])
	def job_application():
		if request.method == 'POST':
			full_name = request.form.get('full_name', '').strip()
			desired_username = request.form.get('desired_username', '').strip()
			desired_password = request.form.get('desired_password', '').strip()
			question1 = request.form.get('question1', '').strip()
			question2 = request.form.get('question2', '').strip()
			question3 = request.form.get('question3', '').strip()
			question4 = request.form.get('question4', '').strip()
			question5 = request.form.get('question5', '').strip()
			question6 = request.form.get('question6', '').strip()
			question7 = request.form.get('question7', '').strip()
			question8 = request.form.get('question8', '').strip()
			
			if not all([full_name, desired_username, desired_password, question1, question2, question3]):
				flash('Заполните все обязательные поля', 'warning')
				return render_template('job_application.html', 
					full_name=full_name, desired_username=desired_username, 
					question1=question1, question2=question2, question3=question3,
					question4=question4, question5=question5, question6=question6,
					question7=question7, question8=question8)
			
			# Check if username already exists
			if AdminUser.query.filter_by(username=desired_username).first():
				flash('Пользователь с таким логином уже существует', 'danger')
				return render_template('job_application.html', 
					full_name=full_name, desired_username=desired_username, 
					question1=question1, question2=question2, question3=question3)
			
			application = JobApplication(
				full_name=full_name,
				desired_username=desired_username,
				desired_password=desired_password,
				question1=question1,
				question2=question2,
				question3=question3,
				question4=question4 if question4 else None,
				question5=question5 if question5 else None,
				question6=question6 if question6 else None,
				question7=question7 if question7 else None,
				question8=question8 if question8 else None
			)
			db.session.add(application)
			db.session.commit()
			
			# Create notification for admins
			notification = Notification(
				title=f"Новая заявка на работу #{application.id}",
				message=f"Заявка от {full_name} на должность с логином {desired_username}",
				feedback_id=None
			)
			db.session.add(notification)
			db.session.commit()
			
			flash('Заявка на работу отправлена. Мы рассмотрим её в ближайшее время. Вы можете отслеживать статус заявки по логину.', 'success')
			return redirect(url_for('track_application'))
		
		return render_template('job_application.html')

	@app.route('/track-application', methods=['GET', 'POST'])
	def track_application():
		if request.method == 'POST':
			username = request.form.get('username', '').strip()
			if not username:
				flash('Введите логин для отслеживания', 'warning')
				return render_template('track_application.html')
			
			# Find application by desired username
			application = JobApplication.query.filter_by(desired_username=username).first()
			if not application:
				flash('Заявка с таким логином не найдена', 'danger')
				return render_template('track_application.html')
			
			return render_template('track_application.html', application=application)
		
		return render_template('track_application.html')

	@app.route('/news/<int:news_id>')
	def news_detail(news_id: int):
		item = News.query.get_or_404(news_id)
		if not item.is_published and not session.get('admin_logged_in'):
			abort(404)
		# Latest other top-level news for the left column
		recent_news = (
			News.query.filter(News.id != news_id, News.is_published == True, News.parent_id == None)
			.order_by(News.created_at.desc())
			.limit(8)
			.all()
		)
		# Subnews of this item
		subnews = News.query.filter_by(parent_id=item.id, is_published=True).order_by(News.created_at.asc()).all()
		return render_template('news_detail.html', item=item, recent_news=recent_news, subnews=subnews)

	@app.route('/admin/login', methods=['GET', 'POST'])
	def admin_login():
		if request.method == 'POST':
			username = request.form.get('username', '').strip()
			password = request.form.get('password', '')
			user = AdminUser.query.filter_by(username=username).first()
			if user and user.check_password(password):
				# Ensure built-in admin always has 'admin' role
				if user.username == 'admin' and getattr(user, 'role', None) != 'admin':
					user.role = 'admin'
					db.session.commit()
				session['admin_logged_in'] = True
				session['admin_username'] = user.username
				session['admin_user_id'] = user.id
				next_url = request.args.get('next') or url_for('admin_dashboard')
				flash('Вы успешно вошли', 'success')
				return redirect(next_url)
			flash('Неверные учетные данные', 'danger')
		return render_template('admin/login.html')

	@app.route('/admin/logout')
	def admin_logout():
		session.clear()
		flash('Вы вышли из админ-панели', 'info')
		return redirect(url_for('index'))

	@app.route('/admin')
	@login_required
	def admin_dashboard():
		# Check user role and redirect accordingly
		username = session.get('admin_username')
		user = AdminUser.query.filter_by(username=username).first()
		
		if user and user.role == 'admin':
			# Full admin dashboard
			total_news = News.query.count()
			published_news = News.query.filter_by(is_published=True).count()
			new_feedback = Feedback.query.filter_by(status='new').count()
			notifications = Notification.query.order_by(Notification.created_at.desc()).limit(10).all()
			return render_template('admin/dashboard.html', total_news=total_news, published_news=published_news, new_feedback=new_feedback, notifications=notifications)
		else:
			# Investigator dashboard
			my_news = News.query.filter_by(is_published=True).order_by(News.created_at.desc()).limit(5).all()
			notifications = Notification.query.order_by(Notification.created_at.desc()).limit(5).all()
			return render_template('Sledovatel.html', my_news=my_news, notifications=notifications)

	def require_admin_role():
		username = session.get('admin_username')
		user = AdminUser.query.filter_by(username=username).first()
		if not user:
			abort(403)
		# Self-heal: promote built-in admin if role not set
		if user.username == 'admin' and getattr(user, 'role', None) != 'admin':
			user.role = 'admin'
			db.session.commit()
		if user.role != 'admin':
			abort(403)
		return user

	@app.route('/admin/site', methods=['GET', 'POST'])
	@login_required
	def admin_site_settings():
		site = SiteInfo.query.first()
		if request.method == 'POST':
			site.leader_first_name = request.form.get('leader_first_name', '').strip() or None
			site.leader_last_name = request.form.get('leader_last_name', '').strip() or None
			site.leader_rank = request.form.get('leader_rank', '').strip() or None
			site.leader_position = request.form.get('leader_position', '').strip() or None
			site.leader_photo_url = request.form.get('leader_photo_url', '').strip() or None
			db.session.commit()
			flash('Информация о лидере обновлена', 'success')
			return redirect(url_for('admin_site_settings'))
		return render_template('admin/site.html', site=site)

	@app.route('/admin/news')
	@login_required
	def admin_news_list():
		items = News.query.order_by(News.created_at.desc()).all()
		return render_template('admin/news_list.html', items=items)

	# Roles dictionary for UI labels
	roles_choices = [
		('junior_investigator', 'Мл. следователь'),
		('investigator', 'Следователь'),
		('duty_investigator', 'Дежурный следователь'),
		('senior_investigator', 'Ст. следователь'),
		('deputy_head', 'Зам. отделения СК РФ'),
		('admin', 'Начальник отделения СК РФ'),
	]
	role_labels = {v: l for v, l in roles_choices}

	@app.route('/admin/users')
	@login_required
	def admin_users_list():
		require_admin_role()
		users = AdminUser.query.order_by(AdminUser.username.asc()).all()
		return render_template('admin/users_list.html', users=users, role_labels=role_labels)

	@app.route('/admin/users/new', methods=['GET', 'POST'])
	@login_required
	def admin_users_new():
		require_admin_role()
		roles = roles_choices
		if request.method == 'POST':
			username = request.form.get('username', '').strip()
			password = request.form.get('password', '')
			role = request.form.get('role', 'investigator')
			full_name = request.form.get('full_name', '').strip()
			position = request.form.get('position', '').strip()
			rank = request.form.get('rank', '').strip()
			if not username or not password:
				flash('Укажите логин и пароль', 'warning')
				return render_template('admin/user_form.html', action='new', roles=roles)
			if AdminUser.query.filter_by(username=username).first():
				flash('Пользователь с таким логином уже существует', 'danger')
				return render_template('admin/user_form.html', action='new', roles=roles)
			u = AdminUser(username=username, role=role, full_name=full_name, position=position, rank=rank)
			u.set_password(password)
			db.session.add(u)
			db.session.commit()
			flash('Пользователь создан', 'success')
			return redirect(url_for('admin_users_list'))
		return render_template('admin/user_form.html', action='new', roles=roles)

	@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
	@login_required
	def admin_users_edit(user_id: int):
		require_admin_role()
		roles = roles_choices
		user = AdminUser.query.get_or_404(user_id)
		if request.method == 'POST':
			user.username = request.form.get('username', '').strip()
			role = request.form.get('role', user.role)
			user.role = role
			user.full_name = request.form.get('full_name', '').strip()
			user.position = request.form.get('position', '').strip()
			user.rank = request.form.get('rank', '').strip()
			new_password = request.form.get('password', '')
			if new_password:
				user.set_password(new_password)
			if not user.username:
				flash('Логин обязателен', 'warning')
				return render_template('admin/user_form.html', action='edit', roles=roles, user=user)
			db.session.commit()
			flash('Пользователь обновлён', 'success')
			return redirect(url_for('admin_users_list'))
		return render_template('admin/user_form.html', action='edit', roles=roles, user=user)

	@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
	@login_required
	def admin_users_delete(user_id: int):
		require_admin_role()
		user = AdminUser.query.get_or_404(user_id)
		if user.username == 'denis333rus':
			flash('Нельзя удалить базового администратора', 'warning')
			return redirect(url_for('admin_users_list'))
		
		# Проверяем, есть ли связанные документы
		authored_documents = Document.query.filter_by(author_id=user_id).count()
		approved_documents = Document.query.filter_by(approved_by_id=user_id).count()
		
		if authored_documents > 0:
			# Переносим документы к администратору
			admin_user = AdminUser.query.filter_by(role='admin').first()
			if admin_user:
				Document.query.filter_by(author_id=user_id).update({'author_id': admin_user.id})
				flash(f'Документы пользователя перенесены к администратору {admin_user.full_name}', 'info')
			else:
				flash('Нельзя удалить пользователя: у него есть документы, а администратор не найден', 'danger')
				return redirect(url_for('admin_users_list'))
		
		# Обнуляем approved_by_id для документов, которые одобрил этот пользователь
		if approved_documents > 0:
			Document.query.filter_by(approved_by_id=user_id).update({'approved_by_id': None})
		
		# Удаляем пользователя
		db.session.delete(user)
		db.session.commit()
		flash('Пользователь удалён', 'info')
		return redirect(url_for('admin_users_list'))

	@app.route('/admin/notifications')
	@login_required
	def admin_notifications():
		notifications = Notification.query.order_by(Notification.created_at.desc()).all()
		return render_template('admin/notifications.html', notifications=notifications)

	@app.route('/admin/notifications/<int:notif_id>/read', methods=['POST'])
	@login_required
	def mark_notification_read(notif_id):
		notification = Notification.query.get_or_404(notif_id)
		notification.is_read = True
		db.session.commit()
		return redirect(url_for('admin_notifications'))

	@app.route('/admin/notifications/mark-all-read', methods=['POST'])
	@login_required
	def mark_all_notifications_read():
		Notification.query.update({'is_read': True})
		db.session.commit()
		return redirect(url_for('admin_notifications'))

	@app.route('/admin/job-applications')
	@login_required
	def admin_job_applications():
		applications = JobApplication.query.order_by(JobApplication.created_at.desc()).all()
		return render_template('admin/job_applications.html', applications=applications)

	@app.route('/admin/job-applications/<int:app_id>', methods=['GET', 'POST'])
	@login_required
	def admin_job_application_detail(app_id):
		application = JobApplication.query.get_or_404(app_id)
		if request.method == 'POST':
			action = request.form.get('action')
			if action == 'approve':
				# Create user account
				user = AdminUser(
					username=application.desired_username, 
					role='investigator',
					full_name=application.full_name,
					position='Следователь',
					rank='Лейтенант юстиции'
				)
				user.set_password(application.desired_password)
				db.session.add(user)
				
				# Update application status
				application.status = 'approved'
				db.session.commit()
				
				flash(f'Пользователь {application.desired_username} создан и заявка одобрена', 'success')
			elif action == 'reject':
				application.status = 'rejected'
				db.session.commit()
				flash('Заявка отклонена', 'info')
			
			return redirect(url_for('admin_job_application_detail', app_id=app_id))
		
		return render_template('admin/job_application_detail.html', application=application)

	@app.route('/admin/feedback')
	@login_required
	def admin_feedback_list():
		items = Feedback.query.order_by(Feedback.created_at.desc()).all()
		return render_template('admin/feedback_list.html', items=items)

	@app.route('/admin/feedback/<int:fb_id>', methods=['GET', 'POST'])
	@login_required
	def admin_feedback_detail(fb_id: int):
		item = Feedback.query.get_or_404(fb_id)
		if request.method == 'POST':
			item.status = request.form.get('status', item.status)
			db.session.commit()
			flash('Статус обновлён', 'success')
			return redirect(url_for('admin_feedback_detail', fb_id=item.id))
		return render_template('admin/feedback_detail.html', item=item)

	@app.route('/admin/news/new', methods=['GET', 'POST'])
	@login_required
	def admin_news_new():
		if request.method == 'POST':
			title = request.form.get('title', '').strip()
			content = request.form.get('content', '').strip()
			is_published = bool(request.form.get('is_published'))
			image_url = request.form.get('image_url', '').strip() or None
			parent_id_raw = request.form.get('parent_id')
			parent_id = int(parent_id_raw) if parent_id_raw and parent_id_raw.isdigit() else None
			image_file = request.files.get('image_file')
			if image_file and image_file.filename:
				filename = secure_filename(image_file.filename)
				name, ext = os.path.splitext(filename)
				unique_name = f"{name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"
				file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
				image_file.save(file_path)
				image_url = url_for('static', filename=f"uploads/{unique_name}")
			if not title or not content:
				flash('Заполните заголовок и содержание', 'warning')
				parents = News.query.order_by(News.created_at.desc()).all()
				return render_template('admin/news_form.html', action='new', parents=parents)
			item = News(title=title, content=content, is_published=is_published, image_url=image_url, parent_id=parent_id)
			db.session.add(item)
			db.session.commit()
			flash('Новость создана', 'success')
			return redirect(url_for('admin_news_list'))
		parents = News.query.order_by(News.created_at.desc()).all()
		return render_template('admin/news_form.html', action='new', parents=parents)

	@app.route('/admin/news/<int:news_id>/edit', methods=['GET', 'POST'])
	@login_required
	def admin_news_edit(news_id: int):
		item = News.query.get_or_404(news_id)
		if request.method == 'POST':
			item.title = request.form.get('title', '').strip()
			item.content = request.form.get('content', '').strip()
			item.is_published = bool(request.form.get('is_published'))
			new_url = request.form.get('image_url', '').strip() or None
			parent_id_raw = request.form.get('parent_id')
			item.parent_id = int(parent_id_raw) if parent_id_raw and parent_id_raw.isdigit() else None
			image_file = request.files.get('image_file')
			if image_file and image_file.filename:
				filename = secure_filename(image_file.filename)
				name, ext = os.path.splitext(filename)
				unique_name = f"{name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"
				file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
				image_file.save(file_path)
				item.image_url = url_for('static', filename=f"uploads/{unique_name}")
			elif new_url is not None:
				item.image_url = new_url or None
			if not item.title or not item.content:
				flash('Заполните заголовок и содержание', 'warning')
				parents = News.query.filter(News.id != item.id).order_by(News.created_at.desc()).all()
				return render_template('admin/news_form.html', action='edit', item=item, parents=parents)
			db.session.commit()
			flash('Новость обновлена', 'success')
			return redirect(url_for('admin_news_list'))
		parents = News.query.filter(News.id != item.id).order_by(News.created_at.desc()).all()
		return render_template('admin/news_form.html', action='edit', item=item, parents=parents)

	@app.route('/admin/news/<int:news_id>/delete', methods=['POST'])
	@login_required
	def admin_news_delete(news_id: int):
		item = News.query.get_or_404(news_id)
		db.session.delete(item)
		db.session.commit()
		flash('Новость удалена', 'info')
		return redirect(url_for('admin_news_list'))

	@app.route('/reviews', methods=['GET', 'POST'])
	def reviews():
		if request.method == 'POST':
			author_name = request.form.get('author_name', '').strip()
			rating = request.form.get('rating', type=int)
			title = request.form.get('title', '').strip()
			content = request.form.get('content', '').strip()
			
			if not all([author_name, rating, title, content]):
				flash('Все поля обязательны для заполнения', 'danger')
				return render_template('reviews.html')
			
			if rating < 1 or rating > 5:
				flash('Оценка должна быть от 1 до 5', 'danger')
				return render_template('reviews.html')
			
			# Create new review
			review = Review(
				author_name=author_name.upper(),
				rating=rating,
				title=title,
				content=content
			)
			db.session.add(review)
			db.session.commit()
			
			# Send notification to admins
			send_review_notification_to_all_roles(review)
			
			flash('Отзыв успешно отправлен!', 'success')
			return redirect(url_for('reviews'))
		
		# Get all reviews for display (no admin approval needed)
		all_reviews = Review.query.order_by(Review.created_at.desc()).all()
		return render_template('reviews.html', reviews=all_reviews)

	@app.route('/admin/reviews')
	@login_required
	def admin_reviews():
		reviews = Review.query.order_by(Review.created_at.desc()).all()
		return render_template('admin/reviews_list.html', reviews=reviews)

	@app.route('/admin/reviews/<int:review_id>')
	@login_required
	def admin_review_detail(review_id: int):
		review = Review.query.get_or_404(review_id)
		return render_template('admin/review_detail.html', review=review)

	@app.route('/admin/reviews/<int:review_id>/approve', methods=['POST'])
	@login_required
	def admin_review_approve(review_id: int):
		review = Review.query.get_or_404(review_id)
		review.status = 'approved'
		db.session.commit()
		flash('Отзыв одобрен', 'success')
		return redirect(url_for('admin_review_detail', review_id=review_id))

	@app.route('/admin/reviews/<int:review_id>/reject', methods=['POST'])
	@login_required
	def admin_review_reject(review_id: int):
		review = Review.query.get_or_404(review_id)
		review.status = 'rejected'
		db.session.commit()
		flash('Отзыв отклонен', 'info')
		return redirect(url_for('admin_review_detail', review_id=review_id))

	@app.route('/documents', methods=['GET', 'POST'])
	@login_required
	def documents():
		if request.method == 'POST':
			title = request.form.get('title', '').strip()
			content = request.form.get('content', '').strip()
			document_type = request.form.get('document_type', '').strip()
			file_url = request.form.get('file_url', '').strip()
			
			if not all([title, content, document_type]):
				flash('Все поля обязательны для заполнения', 'danger')
				return render_template('documents.html')
			
			# Get current user
			current_user_id = session.get('admin_user_id')
			if not current_user_id:
				flash('Ошибка авторизации', 'danger')
				return redirect(url_for('admin_login'))
			
			# Create new document
			document = Document(
				title=title,
				content=content,
				document_type=document_type,
				author_id=current_user_id,
				file_url=file_url if file_url else None
			)
			db.session.add(document)
			db.session.commit()
			
			# Send notification to admins
			send_document_notification_to_all_roles(document)
			
			flash('Документ успешно отправлен на одобрение!', 'success')
			return redirect(url_for('documents'))
		
		# Get current user's documents
		current_user_id = session.get('admin_user_id')
		user_documents = Document.query.filter_by(author_id=current_user_id).order_by(Document.created_at.desc()).all()
		
		# Get all approved documents for display
		approved_documents = Document.query.filter_by(status='approved').order_by(Document.approved_at.desc()).all()
		
		return render_template('documents.html', user_documents=user_documents, approved_documents=approved_documents)

	@app.route('/admin/documents')
	@login_required
	def admin_documents():
		documents = Document.query.order_by(Document.created_at.desc()).all()
		return render_template('admin/documents_list.html', documents=documents)

	@app.route('/admin/documents/<int:document_id>')
	@login_required
	def admin_document_detail(document_id: int):
		document = Document.query.get_or_404(document_id)
		return render_template('admin/document_detail.html', document=document)

	@app.route('/admin/documents/<int:document_id>/approve', methods=['POST'])
	@login_required
	def admin_document_approve(document_id: int):
		document = Document.query.get_or_404(document_id)
		document.status = 'approved'
		document.approved_by_id = session.get('admin_user_id')
		document.approved_at = datetime.utcnow()
		db.session.commit()
		flash('Документ одобрен', 'success')
		return redirect(url_for('admin_document_detail', document_id=document_id))

	@app.route('/admin/documents/<int:document_id>/reject', methods=['POST'])
	@login_required
	def admin_document_reject(document_id: int):
		document = Document.query.get_or_404(document_id)
		document.status = 'rejected'
		document.approved_by_id = session.get('admin_user_id')
		db.session.commit()
		flash('Документ отклонен', 'info')
		return redirect(url_for('admin_document_detail', document_id=document_id))


app = create_app()


if __name__ == '__main__':
	app.run(host='0.0.0.0', port=5000, debug=True)


