from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, login_user, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import datetime, os, re
from sqlalchemy.orm import joinedload
from internal.log import log_info, log_warning, log_error

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key'  # Changez cette clé en production
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///social.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuration de Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ---------------------
# Modèles de données
# ---------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    posts = db.relationship('Post', backref='author', lazy=True)
    likes = db.relationship('Like', backref='user', lazy=True)
    reposts = db.relationship('Repost', backref='user', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    
    # Abonnements (les utilisateurs que l'on suit)
    subscriptions = db.relationship('Subscription', foreign_keys='Subscription.subscriber_id', backref='follower', lazy='dynamic')
    # Nos abonnés (les utilisateurs qui nous suivent)
    subscribers = db.relationship('Subscription', foreign_keys='Subscription.subscribed_to_id', backref='followed', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    likes = db.relationship('Like', backref='post', lazy=True)
    reposts = db.relationship('Repost', backref='original_post', lazy=True)
    comments = db.relationship('Comment', backref='post', lazy=True)

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

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscribed_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

# ---------------------
# Filtre Jinja2 pour formater les commentaires
# Transforme les hashtags (#tag) et mentions (@username) en liens cliquables
# ---------------------
def parse_comment(content):
    content = re.sub(r"#(\w+)", r'<a href="/hashtag/\1">#\1</a>', content)
    content = re.sub(r"@(\w+)", r'<a href="/profile/\1">@\1</a>', content)
    return content

app.jinja_env.filters['parse_comment'] = parse_comment

# ---------------------
# User loader pour Flask-Login
# ---------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------------
# Routes de l'application
# ---------------------
@app.route('/')
def index():
    posts = Post.query.options(joinedload(Post.author)).order_by(Post.timestamp.desc()).all()
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash("Veuillez remplir tous les champs.")
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash("Nom d’utilisateur déjà utilisé.")
            return redirect(url_for('register'))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Inscription réussie. Veuillez vous connecter.")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Connecté avec succès.")
            return redirect(url_for('index'))
        else:
            flash("Nom d’utilisateur ou mot de passe incorrect.")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Déconnexion réussie.")
    return redirect(url_for('index'))

@app.route('/new_post', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        content = request.form['content']
        if not content:
            flash("Le contenu du post ne peut être vide.")
            return redirect(url_for('new_post'))
        post = Post(content=content, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash("Post créé avec succès.")
        return redirect(url_for('index'))
    return render_template('new_post.html')

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    if Like.query.filter_by(user_id=current_user.id, post_id=post_id).first():
        flash("Vous avez déjà liké ce post.")
    else:
        like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(like)
        db.session.commit()
        flash("Post liké.")
    return redirect(request.referrer or url_for('index'))

@app.route('/repost/<int:post_id>', methods=['POST'])
@login_required
def repost(post_id):
    post = Post.query.get_or_404(post_id)
    if Repost.query.filter_by(user_id=current_user.id, original_post_id=post_id).first():
        flash("Vous avez déjà reposté ce post.")
    else:
        repost = Repost(user_id=current_user.id, original_post_id=post_id)
        db.session.add(repost)
        db.session.commit()
        flash("Post reposté.")
    return redirect(request.referrer or url_for('index'))

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def comment(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form['comment']
    if not content:
        flash("Le commentaire ne peut être vide.")
        return redirect(request.referrer or url_for('index'))
    new_comment = Comment(content=content, user_id=current_user.id, post_id=post_id)
    db.session.add(new_comment)
    db.session.commit()
    flash("Commentaire ajouté.")
    return redirect(request.referrer or url_for('index'))

@app.route('/subscribe/<int:user_id>', methods=['POST'])
@login_required
def subscribe(user_id):
    if user_id == current_user.id:
        flash("Vous ne pouvez pas vous abonner à vous-même.")
        return redirect(request.referrer or url_for('index'))
    if Subscription.query.filter_by(subscriber_id=current_user.id, subscribed_to_id=user_id).first():
        flash("Vous êtes déjà abonné.")
    else:
        sub = Subscription(subscriber_id=current_user.id, subscribed_to_id=user_id)
        db.session.add(sub)
        db.session.commit()
        flash("Abonnement réussi.")
    return redirect(request.referrer or url_for('index'))

@app.route('/unsubscribe/<int:user_id>', methods=['POST'])
@login_required
def unsubscribe(user_id):
    sub = Subscription.query.filter_by(subscriber_id=current_user.id, subscribed_to_id=user_id).first()
    if sub:
        db.session.delete(sub)
        db.session.commit()
        flash("Désabonnement réussi.")
    else:
        flash("Vous n’êtes pas abonné à cet utilisateur.")
    return redirect(request.referrer or url_for('index'))

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    is_following = False
    if current_user.id != user.id:
        is_following = Subscription.query.filter_by(subscriber_id=current_user.id, subscribed_to_id=user.id).first() is not None
    posts = Post.query.options(joinedload(Post.author)).filter_by(user_id=user.id).order_by(Post.timestamp.desc()).all()
    subscriber_count = user.subscribers.count()
    subscription_count = user.subscriptions.count()
    return render_template('profile.html', user=user, is_following=is_following, posts=posts, subscriber_count=subscriber_count, subscription_count=subscription_count)

@app.route('/hashtag/<tag>')
def hashtag(tag):
    search = f"%#{tag}%"
    comments = Comment.query.options(joinedload(Comment.author), joinedload(Comment.post)).filter(Comment.content.like(search)).order_by(Comment.timestamp.desc()).all()
    return render_template('hashtag.html', tag=tag, comments=comments)

# ---------------------
# Lancement de l'application
# ---------------------
if __name__ == '__main__':
    log_info("Démarrage de l'application.")
    log_info("Démarrage de la base de données")
    with app.app_context():
        db.create_all()
    log_info("Démarrage du serveur web...")
    app.run(debug=False)