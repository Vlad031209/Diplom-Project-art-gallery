from datetime import datetime
from flask import Flask, render_template, redirect, request, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.utils import secure_filename
import base64


app = Flask(__name__)

app.config['SECRET_KEY'] = b'qs7Opswchl2kU9tgGwfHQkViQUOdNFL5vY4dtC4xchk'

# First Database - Users
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(app.instance_path, 'users.db')}"

# Second Database - MyAccount
# Third Database - Artworks
app.config['SQLALCHEMY_BINDS'] = {
    'my_account': f"sqlite:///{os.path.join(app.instance_path, 'my_account.db')}",  # Bind for my_account.db
    'artworks': f"sqlite:///{os.path.join(app.instance_path, 'artworks.db')}",  # Bind for artworks.db
    'gallery': f"sqlite:///{os.path.join(app.instance_path, 'gallery.db')}"
}

db = SQLAlchemy(app)

# Users Table - Only username, password and id
class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

# MyAccount Table - Extended information, linked to Users via username
# Убираем внешний ключ, так как таблицы находятся в разных базах
class MyAccount(db.Model):
    __bind_key__ = 'my_account'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)  # Значение по умолчанию отсутствует
    phone = db.Column(db.String(20), nullable=True, default="No phone")
    instagram = db.Column(db.String(50), nullable=True, default="No Instagram")
    about_me = db.Column(db.Text, nullable=True, default="")
    art_type = db.Column(db.String(50), nullable=True, default="Any")
    iconic_artwork = db.Column(db.String(100), nullable=True)
    artwork_count = db.Column(db.Integer, nullable=False, default=0)
    profile_picture = db.Column(db.String(100), nullable=True)


# Artworks Table - хранит данные об изображениях
class Artworks(db.Model):
    __bind_key__ = 'artworks'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)  # Удалён db.ForeignKey(Users.username)
    artwork_image = db.Column(db.LargeBinary, nullable=True)  # Храним изображение как двоичные данные


class Gallery(db.Model):
    __bind_key__ = 'gallery'        # Привязываем к gallery.db
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    image_data = db.Column(db.LargeBinary, nullable=True)  # Сырые байты (BLOB)
    image_type = db.Column(db.String(50), nullable=True)   # MIME-тип (image/png и т.д.)
    filename = db.Column(db.String(200), nullable=True)    # Исходное имя файла (по желанию)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)  # Когда загружено



# Initialize databases and tables
@app.cli.command("init-db")
def init_db():
    db.create_all()  # Создает все таблицы из всех баз данных, согласно binds
    print("Databases and tables created successfully.")

@app.cli.command("reset-db")
def reset_db():
    # Drop tables independently to handle foreign key constraints
    db.drop_all()
    db.create_all()  # Recreate all tables
    db.session.commit()
    print("Databases and tables reset successfully.")

# Flash message function
def flash_message(message, category='info'):
    flash(message, category)

# Choose Account Route
@app.route('/')
def choose_account():
    return render_template('choose_account.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = Users.query.filter_by(username=username).first()

        # Check if username exists and if the password matches
        if user and user.password == password:
            session['username'] = username
            flash_message('Login was successful!', 'success')
            return redirect(url_for('main'))
        else:
            flash_message('Invalid username or password, please try again.', 'danger')
            return redirect(url_for('login'))  # Redirect to login page

    return render_template('login.html')

# Register Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if the username already exists
        if Users.query.filter_by(username=username).first():
            flash_message('Username already exists, please choose another one.', 'danger')
            return redirect(url_for('register'))  # Prevent duplicate username

        # Add the new user to the Users table
        new_user = Users(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()

        # Создаем запись в MyAccount
        new_account = MyAccount(username=username)
        db.session.add(new_account)

        # Создаем запись в Artworks
        new_artwork = Artworks(username=username)
        db.session.add(new_artwork)

        new_image_for_gallery = Gallery(username=username)
        db.session.add(new_image_for_gallery)

        db.session.commit()

        # Устанавливаем сессию, чтобы потом находить запись MyAccount
        session['username'] = username

        flash_message('Registration was successful!', 'success')
        return redirect(url_for('main'))

    return render_template('register.html')

@app.route('/upload_gallery', methods=['POST'])
def upload_gallery():
    # 1) Проверяем авторизацию
    if 'username' not in session:
        flash("You need to log in first!", "warning")
        return redirect(url_for('login'))

    # 2) Получаем файл из запроса
    file = request.files.get('gallery_image')
    if not file:
        flash("No file selected.", "danger")
        return redirect(url_for('my_account'))

    # 3) Проверяем формат
    if file and allowed_file(file.filename):
        # Считываем байты
        file_data = file.read()
        # Можно определить MIME-тип по расширению или через библиотеку
        mime_type = "image/png"

        # Создаём новую запись в Gallery
        new_entry = Gallery(
            username=session['username'],
            image_data=file_data,
            image_type=mime_type,
            filename=file.filename
        )

        db.session.add(new_entry)

        adding_my_artwork(file_data, session['username'])

        db.session.commit()

        flash("Artwork added to gallery!", "success")
    else:
        flash("Invalid file type!", "danger")

    return redirect(url_for('my_account'))

def adding_my_artwork(file_data, username):
    """
    Добавляет новую запись в таблицу Artworks (база artworks.db).
    Принимает бинарные данные изображения и имя пользователя.
    """
    new_artwork = Artworks(
        username=username,
        artwork_image=file_data
    )
    db.session.add(new_artwork)

# Main Page Route
@app.route('/main')
def main():
    if 'username' in session:
        username = session['username']
        return render_template('main.html', username=username)
    else:
        flash_message('You need to log in first!', 'warning')
        return redirect(url_for('login'))

# Logout Route
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash_message('You have been logged out!', 'info')
    return redirect(url_for('choose_account'))

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Allowed file extensions
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/my_account', methods=['GET', 'POST'])
def my_account():
    if 'username' not in session:
        flash("You need to log in first!", 'warning')
        return redirect(url_for('login'))

    account = MyAccount.query.filter_by(username=session['username']).first()
    if not account:
        flash("Account not found.", "danger")
        return redirect(url_for('main'))

    if request.method == 'POST':
        # Retrieve form data


        if request.method == 'POST':
            # Handle file upload
            if 'profile_picture' in request.files:
                profile_picture = request.files['profile_picture']
                if profile_picture.filename != '' and allowed_file(profile_picture.filename):
                    filename = secure_filename(profile_picture.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                    # Check if upload folder exists
                    if not os.path.exists(app.config['UPLOAD_FOLDER']):
                        os.makedirs(app.config['UPLOAD_FOLDER'])  # Create folder if it doesn't exist

                    print(f"Saving file to: {file_path}")
                    profile_picture.save(file_path)

                    # Update profile picture in the database
                    account.profile_picture = filename
                    db.session.commit()

                    flash("Profile picture uploaded successfully!", 'success')
                else:
                    flash("Invalid file type! Only .jpg, .jpeg, and .png are allowed.", 'danger')

            elif 'iconic_artwork' in request.files:
                iconic_artwork_file = request.files['iconic_artwork']
                if iconic_artwork_file.filename != '' and allowed_file(iconic_artwork_file.filename):
                    iconic_filename = secure_filename(iconic_artwork_file.filename)
                    iconic_file_path = os.path.join(app.config['UPLOAD_FOLDER'], iconic_filename)

                    if not os.path.exists(app.config['UPLOAD_FOLDER']):
                        os.makedirs(app.config['UPLOAD_FOLDER'])

                    print(f"Saving iconic artwork to: {iconic_file_path}")
                    iconic_artwork_file.save(iconic_file_path)

                    # Update iconic artwork in the database
                    account.iconic_artwork = iconic_filename
                    db.session.commit()

                    flash("Iconic artwork uploaded successfully!", 'success')
                else:
                    flash("Invalid file type for iconic artwork! Only .jpg, .jpeg, and .png are allowed.", 'danger')

            else:
                email = request.form.get('email', 'No email')
                phone = request.form.get('phone', 'No phone')
                instagram = request.form.get('instagram', 'No Instagram')
                about_me = request.form.get('about_me', '')
                art_type = request.form.get('art_type', 'Any')
                artwork_count = request.form.get('artwork_count', 0)

                # Update other user information
                account.email = email
                account.phone = phone
                account.instagram = instagram
                account.about_me = about_me
                account.art_type = art_type
                account.artwork_count = artwork_count
                db.session.commit()

        flash("Your information has been updated!", 'success')

    user_artworks_count = Gallery.query.filter_by(username=session['username']).count() - 1

    return render_template('my_account.html', account=account, artwork_count=user_artworks_count)


@app.route('/artists', methods=['GET'])
def artists():
    # 1) Grab the search query if present
    q = request.args.get('q', '').strip()

    # 2) Base query: order by username ascending (alphabetical)
    query = MyAccount.query.order_by(MyAccount.username.asc())

    # 3) If there's a search query, filter by partial match (case-insensitive)
    if q:
        query = query.filter(MyAccount.username.ilike(f'%{q}%'))

    # 4) Execute the query
    all_artists = query.all()

    # 5) Render the artists page, passing the list & the current search query
    return render_template('artists.html', all_artists=all_artists, q=q)


@app.route('/expanding_gallery')
def gallery():
    images = Gallery.query.order_by(Gallery.uploaded_at.desc()).all()
    gallery_items = []
    for img in images:
        if not img.image_data:
            continue
        # Кодируем image_data в base64
        encoded_data = base64.b64encode(img.image_data).decode('utf-8')

        # Находим pfp, если есть
        user_account = MyAccount.query.filter_by(username=img.username).first()
        pfp = user_account.profile_picture if user_account else None

        gallery_items.append({
            'username': img.username,
            'encoded_data': encoded_data,  # <-- Уже кодированная строка
            'image_type': img.image_type,
            'pfp': pfp
        })

    return render_template('gallery.html', gallery_items=gallery_items)

@app.route('/profile/<username>')
def view_user_profile(username):
    # Пытаемся найти профиль в MyAccount
    account = MyAccount.query.filter_by(username=username).first()
    if not account:
        flash("User not found!", "danger")
        return redirect(url_for('gallery'))  # или на главную, если хотите

    # Рендерим шаблон, в котором показываем данные пользователя
    user_artworks_count = Gallery.query.filter_by(username=username).count() - 1
    account.artwork_count = user_artworks_count

    return render_template('view_profile.html', account=account)


@app.route('/view_artworks')
def view_artworks():
    # 1) Check if user is logged in
    if 'username' not in session:
        flash("You need to log in first!", "warning")
        return redirect(url_for('login'))

    # 2) Query only the current user's images, sorted by newest first
    images = Gallery.query.filter_by(username=session['username']) \
        .order_by(Gallery.uploaded_at.desc()) \
        .all()

    # 3) Build gallery_items just like in gallery
    gallery_items = []
    for img in images:
        if not img.image_data:
            continue  # skip placeholder row or empty
        encoded_data = base64.b64encode(img.image_data).decode('utf-8')

        # If you want the user’s profile picture for the user-info block
        user_account = MyAccount.query.filter_by(username=img.username).first()
        pfp = user_account.profile_picture if user_account else None

        gallery_items.append({
            'username': img.username,
            'encoded_data': encoded_data,
            'image_type': img.image_type,
            'pfp': pfp
        })

    return render_template('view_artworks.html', gallery_items=gallery_items)


@app.route('/view_artworks/<username>')
def view_artworks_user(username):
    # 1) Optional: check if *any* user is logged in (if your site requires login to see artworks)
    if 'username' not in session:
        flash("You need to log in first!", "warning")
        return redirect(url_for('login'))

    # 2) Query the Gallery table for the specified username
    images = Gallery.query.filter_by(username=username) \
        .order_by(Gallery.uploaded_at.desc()) \
        .all()

    # 3) Convert to base64, build gallery_items
    import base64
    gallery_items = []
    for img in images:
        if not img.image_data:
            continue  # skip placeholder or empty row
        encoded_data = base64.b64encode(img.image_data).decode('utf-8')

        user_account = MyAccount.query.filter_by(username=username).first()
        pfp = user_account.profile_picture if user_account else None

        gallery_items.append({
            'username': username,
            'encoded_data': encoded_data,
            'image_type': img.image_type,
            'pfp': pfp
        })

    # 4) Render a template, e.g. "view_artworks_user.html" or reuse "view_artworks.html"
    return render_template('view_artworks_user.html', gallery_items=gallery_items, artist=username)


if __name__ == '__main__':
    app.run(debug=True)
