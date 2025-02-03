from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, login_user, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import os
from webdav3.client import Client

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key'  # Change this for production!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///social.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Setup Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Configure the WebDAV client for your Hetzner server
webdav_options = {
    'webdav_hostname': "https://u441636.your-storagebox.de/",  # e.g. https://webdav.yourserver.com
    'webdav_login': "u441636",
    'webdav_password': "Hetzner1234",  # Change this to your actual password
}
webdav_client = Client(webdav_options)

# ---------------------
# Database Models
# ---------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    posts = db.relationship('Post', backref='author', lazy=True)
    likes = db.relationship('Like', backref='user', lazy=True)
    reposts = db.relationship('Repost', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # This field stores the remote file path on the WebDAV server where the post content is saved.
    content_file = db.Column(db.String(256), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    likes = db.relationship('Like', backref='post', lazy=True)
    reposts = db.relationship('Repost', backref='original_post', lazy=True)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Repost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    original_post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------------
# Routes
# ---------------------

@app.route('/')
def index():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    posts_data = []
    for post in posts:
        try:
            # Download post content from the WebDAV server to a temporary file.
            local_path = f"temp_{post.id}.txt"
            webdav_client.download_sync(remote_path=post.content_file, local_path=local_path)
            with open(local_path, 'r') as f:
                content = f.read()
            os.remove(local_path)
        except Exception as e:
            content = "[Error loading content]"
        posts_data.append({
            'id': post.id,
            'content': content,
            'author': post.author.username,
            'timestamp': post.timestamp,
            'like_count': len(post.likes),
            'repost_count': len(post.reposts)
        })
    return render_template('index.html', posts=posts_data)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('register'))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.')
    return redirect(url_for('index'))

@app.route('/new_post', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        content = request.form['content']
        # Create a unique filename for this post content.
        filename = f"posts/{current_user.id}_{int(datetime.datetime.utcnow().timestamp())}.txt"
        
        # Optionally, ensure the remote directory exists.
        remote_dir = filename.rsplit('/', 1)[0]
        try:
            if not webdav_client.check(remote_dir):
                webdav_client.mkdir(remote_dir)
        except Exception as e:
            # Log or handle the error as needed.
            print("Error ensuring directory exists:", e)
        
        # Save content to a temporary file locally.
        local_temp_path = f"temp_{current_user.id}.txt"
        with open(local_temp_path, 'w') as f:
            f.write(content)
            
        # Upload the temporary file to the WebDAV server.
        try:
            webdav_client.upload_sync(remote_path=filename, local_path=local_temp_path)
        except Exception as e:
            flash("Error uploading post content.")
            os.remove(local_temp_path)
            return redirect(url_for('new_post'))
        
        os.remove(local_temp_path)
        
        # Save the post record (which holds the remote file path) to the database.
        post = Post(content_file=filename, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash("Post created successfully.")
        return redirect(url_for('index'))
    return render_template('new_post.html')

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    # Check if the current user has already liked the post.
    if Like.query.filter_by(user_id=current_user.id, post_id=post_id).first():
        flash("You already liked this post.")
    else:
        like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(like)
        db.session.commit()
        flash("Post liked.")
    return redirect(url_for('index'))

@app.route('/repost/<int:post_id>', methods=['POST'])
@login_required
def repost(post_id):
    original_post = Post.query.get_or_404(post_id)
    # Optionally check if already reposted.
    if Repost.query.filter_by(user_id=current_user.id, original_post_id=post_id).first():
        flash("You already reposted this post.")
    else:
        repost = Repost(user_id=current_user.id, original_post_id=post_id)
        db.session.add(repost)
        db.session.commit()
        flash("Post reposted.")
    return redirect(url_for('index'))

# ---------------------
# Run the App
# ---------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
