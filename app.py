from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
import datetime, os, re
from sqlalchemy.orm import joinedload
from internal.log import log_info, log_warning, log_error
from datetime import datetime, timedelta
from backend.extensions import db, login_manager
from backend.models import User, Post, Like, Repost, Comment, Subscription, Message
from flask_login import login_required, current_user, login_user, logout_user

app = Flask(__name__)

# Configure your app (e.g., secret key, database URI, etc.)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///social.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

# ---------------------
# Filtre Jinja2 pour formater les commentaires
# Transforme les hashtags (#tag) et mentions (@username) en liens cliquables
# ---------------------
def parse_comment(content):
    content = re.sub(r"#(\w+)", r'<a href="/hashtag/\1">#\1</a>', content)
    content = re.sub(r"@(\w+)", r'<a href="/profile/\1">@\1</a>', content)
    return content

app.jinja_env.filters['parse_comment'] = parse_comment

def compute_post_score(post):
    likes_count = len(post.likes)
    followers_count = post.author.subscribers.count()
    score = likes_count * 1.1 + followers_count * 1.25
    # Call datetime.now() to get current time instance
    if post.author.verified and (datetime.now() - post.timestamp < timedelta(days=1)):
        score += 0.5
    return score

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
    posts = Post.query.filter_by(public=True).all()
    posts.sort(key=lambda post: (compute_post_score(post), post.timestamp), reverse=True)
    return render_template('index.html', posts=posts)

@app.route('/request_verification', methods=['POST'])
@login_required
def request_verification():
    if not current_user.verified:
        if not current_user.verification_requested:
            current_user.verification_requested = True
            db.session.commit()
            flash("Votre demande de vérification a été envoyée.")
        else:
            flash("Vous avez déjà demandé la vérification.")
    else:
        flash("Vous êtes déjà vérifié.")
    return redirect(request.referrer or url_for('profile', username=current_user.username))

@app.route('/verify/<int:user_id>', methods=['POST'])
@login_required
def verify_user(user_id):
    if current_user.username != 'admin':
        flash("Seul l'administrateur peut vérifier des utilisateurs.")
        return redirect(request.referrer or url_for('index'))
    user = User.query.get_or_404(user_id)
    user.verified = True
    user.verification_requested = False
    db.session.commit()
    flash(f"Utilisateur {user.username} a été vérifié.")
    return redirect(request.referrer or url_for('profile', username=user.username))

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

    # Language: Python
@app.route('/api/v1/posts', methods=['GET'])
def api_posts():
    posts = Post.query.filter_by(public=True).all()
    posts_json = []
    for post in posts:
        posts_json.append({
            'id': post.id,
            'author': post.author.username,
            'content_text': post.content_text,
            'timestamp': post.timestamp.isoformat(),
            'likes': len(post.likes),
            'comments': len(post.comments)
        })
    return jsonify(posts=posts_json)

@app.route('/api/v1/profile/<username>', methods=['GET'])
def api_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    user_data = {
        "id": user.id,
        "username": user.username,
        "verified": user.verified,
        "subscriber_count": user.subscribers.count(),
        "subscription_count": user.subscriptions.count(),
        "posts": [{
            "id": post.id,
            "content_text": post.content_text,
            "timestamp": post.timestamp.isoformat(),
            "likes": len(post.likes),
            "comments": len(post.comments)
        } for post in user.posts]
    }
    return jsonify(profile=user_data)

@app.route('/api/v1/login', methods=['POST'])
def api_login():
    username = request.form['username'].strip()
    password = request.form['password']
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        login_user(user)
        return jsonify({"status": "success", "message": "Connecté avec succès."})
    else:
        return jsonify({"status": "error", "message": "Nom d’utilisateur ou mot de passe incorrect."}), 400

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
        public = 'public' in request.form
        if not content:
            flash("Le contenu ne peut être vide.")
            return redirect(request.referrer or url_for('index'))
        post = Post(content_text=content, author_id=current_user.id, public=public)
        db.session.add(post)
        db.session.commit()
        flash("Post créé.")
        return redirect(url_for('index'))
    return render_template('new_post.html')

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if like:
        db.session.delete(like)
        flash("Like retiré.")
    else:
        like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(like)
        flash("Post liké.")
    db.session.commit()
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
    posts = Post.query.options(joinedload(Post.author)).filter_by(author_id=user.id).order_by(Post.timestamp.desc()).all()
    subscriber_count = user.subscribers.count()
    subscription_count = user.subscriptions.count()
    return render_template('profile.html', user=user, is_following=is_following, posts=posts, subscriber_count=subscriber_count, subscription_count=subscription_count)

@app.route('/hashtag/<tag>')
def hashtag(tag):
    search = f"%#{tag}%"
    comments = Comment.query.options(joinedload(Comment.author), joinedload(Comment.post)).filter(Comment.content.like(search)).order_by(Comment.timestamp.desc()).all()
    return render_template('hashtag.html', tag=tag, comments=comments)

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    recipient_username = request.form['recipient']
    body = request.form['body']
    recipient = User.query.filter_by(username=recipient_username).first()
    if recipient:
        message = Message(sender_id=current_user.id, recipient_id=recipient.id, body=body)
        db.session.add(message)
        db.session.commit()
        flash('Message sent successfully!', 'success')
    else:
        flash('Recipient not found.', 'danger')
    return redirect(url_for('index'))

@app.route('/messages')
@login_required
def messages():
    received_messages = Message.query.filter_by(recipient_id=current_user.id).order_by(Message.timestamp.desc()).all()
    sent_messages = Message.query.filter_by(sender_id=current_user.id).order_by(Message.timestamp.desc()).all()
    return render_template('messages.html', received_messages=received_messages, sent_messages=sent_messages)

@app.route('/verified_requests')
@login_required
def verified_requests():
    if current_user.username != 'admin':
        flash("Seul l'administrateur peut accéder à cette page.")
        return redirect(url_for('index'))
    requests = User.query.filter_by(verification_requested=True, verified=False).all()
    return render_template('verified_requests.html', requests=requests)

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