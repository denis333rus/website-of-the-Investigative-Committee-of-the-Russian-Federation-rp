from datetime import datetime
import os

from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, current_app
from sqlalchemy import text
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


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


def ensure_initial_admin() -> None:
	if not AdminUser.query.first():
		admin = AdminUser(username='admin')
		admin.set_password('admin123')
		admin.role = 'admin'
		db.session.add(admin)
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

	# Ensure AdminUser.role exists
	db.session.execute(text('CREATE TABLE IF NOT EXISTS admin_user (id INTEGER PRIMARY KEY)'))
	admin_cols = db.session.execute(text('PRAGMA table_info(admin_user)')).all()
	admin_existing = {row[1] for row in admin_cols}
	if 'role' not in admin_existing:
		db.session.execute(text("ALTER TABLE admin_user ADD COLUMN role VARCHAR(50) DEFAULT 'investigator'"))
		db.session.commit()


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
		return dict(site=site)

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
			flash('Заявление отправлено. Мы свяжемся с вами при необходимости.', 'success')
			return redirect(url_for('feedback'))
		return render_template('feedback.html')

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
		total_news = News.query.count()
		published_news = News.query.filter_by(is_published=True).count()
		new_feedback = Feedback.query.filter_by(status='new').count()
		return render_template('admin/dashboard.html', total_news=total_news, published_news=published_news, new_feedback=new_feedback)

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
		('admin', 'Администратор'),
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
			if not username or not password:
				flash('Укажите логин и пароль', 'warning')
				return render_template('admin/user_form.html', action='new', roles=roles)
			if AdminUser.query.filter_by(username=username).first():
				flash('Пользователь с таким логином уже существует', 'danger')
				return render_template('admin/user_form.html', action='new', roles=roles)
			u = AdminUser(username=username, role=role)
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
		if user.username == 'admin':
			flash('Нельзя удалить базового администратора', 'warning')
			return redirect(url_for('admin_users_list'))
		db.session.delete(user)
		db.session.commit()
		flash('Пользователь удалён', 'info')
		return redirect(url_for('admin_users_list'))

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


app = create_app()


if __name__ == '__main__':
	app.run(host='0.0.0.0', port=5000, debug=True)


