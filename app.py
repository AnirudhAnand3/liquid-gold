import os
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

from dotenv import load_dotenv
from flask import (Flask, jsonify, redirect, url_for, render_template,
                   flash, session, request, abort, current_app)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_required,
                         login_user, logout_user, current_user)
import requests

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///liquidgold.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['OAUTH2_PROVIDERS'] = {
    'google': {
        'client_id': os.environ.get('GOOGLE_CLIENT_ID'),
        'client_secret': os.environ.get('GOOGLE_CLIENT_SECRET'),
        'authorize_url': 'https://accounts.google.com/o/oauth2/auth',
        'token_url': 'https://accounts.google.com/o/oauth2/token',
        'userinfo': {
            'url': 'https://www.googleapis.com/oauth2/v3/userinfo',
            'email': lambda j: j['email'],
            'name': lambda j: j.get('name', j['email'].split('@')[0]),
        },
        'scopes': ['https://www.googleapis.com/auth/userinfo.email',
                   'https://www.googleapis.com/auth/userinfo.profile'],
    },
    'github': {
        'client_id': os.environ.get('GITHUB_CLIENT_ID'),
        'client_secret': os.environ.get('GITHUB_CLIENT_SECRET'),
        'authorize_url': 'https://github.com/login/oauth/authorize',
        'token_url': 'https://github.com/login/oauth/access_token',
        'userinfo': {
            'url': 'https://api.github.com/user/emails',
            'email': lambda j: next(e['email'] for e in j if e['primary']),
            'name': lambda j: next(e['email'] for e in j if e['primary']).split('@')[0],
        },
        'scopes': ['user:email'],
    },
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'index'


# ── Models ─────────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id               = db.Column(db.Integer, primary_key=True)
    username         = db.Column(db.String(64), nullable=False)
    email            = db.Column(db.String(320), unique=True, nullable=False)
    balance          = db.Column(db.Float, default=1000.0, nullable=False)
    savings_balance  = db.Column(db.Float, default=0.0, nullable=False)
    account_number   = db.Column(db.String(20), unique=True)
    bio              = db.Column(db.String(200), default='')
    phone            = db.Column(db.String(20), default='')
    tier             = db.Column(db.String(20), default='bronze')
    xp               = db.Column(db.Integer, default=0)
    streak           = db.Column(db.Integer, default=0)
    last_login       = db.Column(db.Date)
    total_sent       = db.Column(db.Float, default=0.0)
    total_received   = db.Column(db.Float, default=0.0)
    total_txn_count  = db.Column(db.Integer, default=0)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    transactions_sent = db.relationship(
        'Transaction', foreign_keys='Transaction.sender_id',
        backref='sender', lazy='dynamic', cascade='all, delete-orphan')
    transactions_received = db.relationship(
        'Transaction', foreign_keys='Transaction.receiver_id',
        backref='receiver', lazy='dynamic')
    notifications    = db.relationship('Notification', backref='user',
                                       lazy='dynamic', cascade='all, delete-orphan')
    savings_goals    = db.relationship('SavingsGoal', backref='user',
                                       lazy='dynamic', cascade='all, delete-orphan')
    budget_categories = db.relationship('BudgetCategory', backref='user',
                                        lazy='dynamic', cascade='all, delete-orphan')
    contacts_owned   = db.relationship('Contact', foreign_keys='Contact.user_id',
                                       backref='owner', lazy='dynamic',
                                       cascade='all, delete-orphan')
    scheduled_payments = db.relationship('ScheduledPayment',
                                         foreign_keys='ScheduledPayment.sender_id',
                                         backref='sender_user', lazy='dynamic',
                                         cascade='all, delete-orphan')
    activity_logs    = db.relationship('ActivityLog', backref='user',
                                       lazy='dynamic', cascade='all, delete-orphan')

    def award_xp(self, points):
        self.xp += points
        tiers = [('diamond', 5000), ('platinum', 2000), ('gold', 800), ('silver', 200)]
        self.tier = 'bronze'
        for name, threshold in tiers:
            if self.xp >= threshold:
                self.tier = name
                break

    def to_dict(self):
        return {
            'id': self.id, 'username': self.username, 'email': self.email,
            'balance': round(self.balance, 2), 'savings_balance': round(self.savings_balance, 2),
            'account_number': self.account_number, 'tier': self.tier,
            'xp': self.xp, 'streak': self.streak,
            'total_sent': round(self.total_sent, 2),
            'total_received': round(self.total_received, 2),
            'total_txn_count': self.total_txn_count,
        }


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id          = db.Column(db.Integer, primary_key=True)
    sender_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    amount      = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), default='')
    type        = db.Column(db.String(20), default='transfer')
    category    = db.Column(db.String(50), default='other')
    reference   = db.Column(db.String(30), unique=True)
    fee         = db.Column(db.Float, default=0.0)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def serialize(self, current_uid=None):
        return {
            'id': self.id, 'amount': round(self.amount, 2),
            'description': self.description, 'type': self.type,
            'category': self.category, 'reference': self.reference,
            'fee': self.fee,
            'sender_id': self.sender_id, 'receiver_id': self.receiver_id,
            'sender_name': self.sender.username if self.sender else None,
            'receiver_name': self.receiver.username if self.receiver else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None,
        }


class Notification(db.Model):
    __tablename__ = 'notifications'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title      = db.Column(db.String(100), nullable=False)
    message    = db.Column(db.String(300), nullable=False)
    type       = db.Column(db.String(20), default='info')
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'message': self.message,
            'type': self.type, 'is_read': self.is_read,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None,
        }


class SavingsGoal(db.Model):
    __tablename__ = 'savings_goals'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    target     = db.Column(db.Float, nullable=False)
    current    = db.Column(db.Float, default=0.0)
    emoji      = db.Column(db.String(5), default='🎯')
    deadline   = db.Column(db.String(20), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        pct = min((self.current / self.target * 100) if self.target > 0 else 0, 100)
        return {
            'id': self.id, 'name': self.name, 'target': self.target,
            'current': self.current, 'emoji': self.emoji,
            'deadline': self.deadline, 'pct': round(pct, 1),
        }


class BudgetCategory(db.Model):
    __tablename__ = 'budget_categories'
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name          = db.Column(db.String(50), nullable=False)
    monthly_limit = db.Column(db.Float, default=500.0)
    color         = db.Column(db.String(10), default='#D4AF37')
    emoji         = db.Column(db.String(5), default='💰')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)


class Contact(db.Model):
    __tablename__ = 'contacts'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    nickname   = db.Column(db.String(50), default='')
    added_at   = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'contact_id'),)

    contact_user = db.relationship('User', foreign_keys=[contact_id])


class ScheduledPayment(db.Model):
    __tablename__ = 'scheduled_payments'
    id          = db.Column(db.Integer, primary_key=True)
    sender_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), default='')
    frequency   = db.Column(db.String(20), default='monthly')
    next_date   = db.Column(db.String(20), nullable=False)
    active      = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    receiver_user = db.relationship('User', foreign_keys=[receiver_id])


class SplitBill(db.Model):
    __tablename__ = 'split_bills'
    id           = db.Column(db.Integer, primary_key=True)
    creator_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title        = db.Column(db.String(100), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    description  = db.Column(db.String(200), default='')
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    creator  = db.relationship('User', foreign_keys=[creator_id])
    members  = db.relationship('SplitBillMember', backref='bill',
                                cascade='all, delete-orphan')


class SplitBillMember(db.Model):
    __tablename__ = 'split_bill_members'
    id          = db.Column(db.Integer, primary_key=True)
    bill_id     = db.Column(db.Integer, db.ForeignKey('split_bills.id'), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount_owed = db.Column(db.Float, nullable=False)
    paid        = db.Column(db.Boolean, default=False)
    paid_at     = db.Column(db.DateTime)

    member_user = db.relationship('User', foreign_keys=[user_id])


class ActivityLog(db.Model):
    __tablename__ = 'activity_log'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action     = db.Column(db.String(100), nullable=False)
    details    = db.Column(db.String(200), default='')
    ip         = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


# ── Helpers ────────────────────────────────────────────────────────────────────

def gen_account_number():
    return 'LG' + str(int(time.time()))[-8:] + secrets.token_hex(2).upper()

def gen_reference():
    return 'TXN' + secrets.token_hex(6).upper()

def add_notification(user, title, message, ntype='info'):
    n = Notification(user_id=user.id, title=title, message=message, type=ntype)
    db.session.add(n)

def log_activity(user, action, details=''):
    a = ActivityLog(user_id=user.id, action=action, details=details,
                    ip=request.remote_addr)
    db.session.add(a)

def seed_budget_categories(user):
    defaults = [
        ('Food & Dining', '🍔', '#e74c3c', 500),
        ('Transport',     '🚗', '#3498db', 300),
        ('Shopping',      '🛍️', '#9b59b6', 800),
        ('Entertainment', '🎬', '#f39c12', 400),
        ('Health',        '💊', '#2ecc71', 300),
        ('Other',         '💰', '#D4AF37', 500),
    ]
    for name, emoji, color, limit in defaults:
        db.session.add(BudgetCategory(
            user_id=user.id, name=name, emoji=emoji, color=color, monthly_limit=limit))


# ── Auth ───────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/authorize/<provider>')
def oauth2_authorize(provider):
    if not current_user.is_anonymous:
        return redirect(url_for('dashboard'))
    provider_data = current_app.config['OAUTH2_PROVIDERS'].get(provider)
    if not provider_data:
        abort(404)
    if not provider_data.get('client_id'):
        flash(f'{provider.title()} OAuth is not configured. Add credentials to .env')
        return redirect(url_for('index'))
    session['oauth2_state'] = secrets.token_urlsafe(16)
    qs = urlencode({
        'client_id': provider_data['client_id'],
        'redirect_uri': url_for('oauth2_callback', provider=provider, _external=True),
        'response_type': 'code',
        'scope': ' '.join(provider_data['scopes']),
        'state': session['oauth2_state'],
    })
    return redirect(provider_data['authorize_url'] + '?' + qs)


@app.route('/callback/<provider>')
def oauth2_callback(provider):
    if not current_user.is_anonymous:
        return redirect(url_for('dashboard'))
    provider_data = current_app.config['OAUTH2_PROVIDERS'].get(provider)
    if not provider_data:
        abort(404)
    if 'error' in request.args:
        flash('OAuth error: ' + request.args.get('error_description', request.args['error']))
        return redirect(url_for('index'))
    if request.args.get('state') != session.get('oauth2_state'):
        abort(401)

    token_resp = requests.post(provider_data['token_url'], data={
        'client_id': provider_data['client_id'],
        'client_secret': provider_data['client_secret'],
        'code': request.args['code'],
        'grant_type': 'authorization_code',
        'redirect_uri': url_for('oauth2_callback', provider=provider, _external=True),
    }, headers={'Accept': 'application/json'})
    if token_resp.status_code != 200:
        abort(401)
    access_token = token_resp.json().get('access_token')

    user_resp = requests.get(provider_data['userinfo']['url'],
                             headers={'Authorization': 'Bearer ' + access_token,
                                      'Accept': 'application/json'})
    if user_resp.status_code != 200:
        abort(401)

    email    = provider_data['userinfo']['email'](user_resp.json())
    username = provider_data['userinfo']['name'](user_resp.json())

    user = db.session.scalar(db.select(User).where(User.email == email))
    today = datetime.utcnow().date()

    if user is None:
        user = User(email=email, username=username, balance=1000.0,
                    account_number=gen_account_number(), last_login=today)
        db.session.add(user)
        db.session.flush()  # get user.id before commit
        user.award_xp(100)
        seed_budget_categories(user)
        add_notification(user, '🎉 Welcome to Liquid Gold!',
                         f'Hello {username}! Your account starts with ₹1,000 bonus. Explore all features!',
                         'success')
        log_activity(user, 'Account Created', f'via {provider}')
        db.session.commit()
        flash(f'Welcome, {username}! Your account is ready with ₹1,000.00.')
    else:
        # Login streak logic
        yesterday = today - timedelta(days=1)
        if user.last_login == yesterday:
            user.streak = (user.streak or 0) + 1
            user.award_xp(10)
            if user.streak % 7 == 0:
                add_notification(user, f'🔥 {user.streak}-Day Streak!',
                                 f'You\'ve logged in {user.streak} days in a row! Bonus XP!', 'success')
                user.award_xp(50)
        elif user.last_login != today:
            user.streak = 1
        user.last_login = today
        log_activity(user, 'Login', f'via {provider}')
        db.session.commit()
        flash(f'Welcome back, {user.username}!')

    login_user(user)
    return redirect(url_for('dashboard'))


@app.route('/logout')
@login_required
def logout():
    log_activity(current_user, 'Logout')
    db.session.commit()
    logout_user()
    return redirect(url_for('index'))


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    uid = current_user.id
    txns = Transaction.query.filter(
        (Transaction.sender_id == uid) | (Transaction.receiver_id == uid)
    ).order_by(Transaction.created_at.desc()).limit(10).all()

    notifications = Notification.query.filter_by(user_id=uid)\
        .order_by(Notification.created_at.desc()).limit(20).all()
    unread_count = Notification.query.filter_by(user_id=uid, is_read=False).count()

    goals = SavingsGoal.query.filter_by(user_id=uid)\
        .order_by(SavingsGoal.created_at.desc()).all()

    contacts = Contact.query.filter_by(user_id=uid).all()

    scheduled = ScheduledPayment.query.filter_by(sender_id=uid, active=True)\
        .order_by(ScheduledPayment.next_date).all()

    # Budget with this-month spending
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    budget_cats = BudgetCategory.query.filter_by(user_id=uid).all()
    budget_data = []
    for cat in budget_cats:
        spent = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))\
            .filter(Transaction.sender_id == uid,
                    Transaction.category == cat.name,
                    Transaction.created_at >= month_start).scalar()
        pct = min((spent / cat.monthly_limit * 100) if cat.monthly_limit > 0 else 0, 100)
        budget_data.append({
            'id': cat.id, 'name': cat.name, 'emoji': cat.emoji, 'color': cat.color,
            'monthly_limit': cat.monthly_limit, 'spent': round(spent, 2), 'pct': round(pct, 1)
        })

    # 7-day chart data
    daily = []
    for i in range(6, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        spent = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))\
            .filter(Transaction.sender_id == uid,
                    db.func.date(Transaction.created_at) == day.isoformat(),
                    Transaction.type.in_(['transfer', 'withdrawal'])).scalar()
        daily.append({'date': day.strftime('%m/%d'), 'total': round(spent, 2)})

    # Split bills user is part of
    my_memberships = SplitBillMember.query.filter_by(user_id=uid)\
        .join(SplitBill).order_by(SplitBill.created_at.desc()).limit(5).all()

    # Leaderboard
    leaderboard = User.query.order_by(User.xp.desc()).limit(5).all()

    activity = ActivityLog.query.filter_by(user_id=uid)\
        .order_by(ActivityLog.created_at.desc()).limit(10).all()

    total_users = User.query.count()

    return render_template('dashboard.html',
        user=current_user,
        transactions=txns,
        notifications=notifications,
        unread_count=unread_count,
        savings_goals=goals,
        contacts=contacts,
        scheduled=scheduled,
        budgets=budget_data,
        daily=daily,
        bills=my_memberships,
        activity=activity,
        leaderboard=leaderboard,
        total_users=total_users,
    )


# ── API: Balance & Money ───────────────────────────────────────────────────────

@app.route('/api/balance')
@login_required
def api_balance():
    return jsonify({
        'balance': round(current_user.balance, 2),
        'savings_balance': round(current_user.savings_balance, 2),
        'xp': current_user.xp, 'tier': current_user.tier,
        'streak': current_user.streak,
    })


@app.route('/api/deposit', methods=['POST'])
@login_required
def api_deposit():
    data = request.get_json() or {}
    amount = data.get('amount', 0)
    method = data.get('method', 'UPI')
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400
    if amount <= 0 or amount > 100000:
        return jsonify({'error': 'Amount must be between ₹1 and ₹1,00,000'}), 400

    current_user.balance += amount
    current_user.total_received += amount
    ref = gen_reference()
    t = Transaction(receiver_id=current_user.id, amount=amount,
                    description=f'Deposit via {method}', type='deposit', reference=ref)
    db.session.add(t)
    current_user.award_xp(5)
    add_notification(current_user, '💰 Deposit Successful',
                     f'₹{amount:,.2f} added to your wallet. Ref: {ref}', 'success')
    log_activity(current_user, 'Deposit', f'₹{amount} via {method}')
    db.session.commit()
    return jsonify({'success': True, 'balance': round(current_user.balance, 2), 'reference': ref})


@app.route('/api/withdraw', methods=['POST'])
@login_required
def api_withdraw():
    data = request.get_json() or {}
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400
    if amount <= 0:
        return jsonify({'error': 'Amount must be positive'}), 400
    if current_user.balance < amount:
        return jsonify({'error': 'Insufficient balance'}), 400

    current_user.balance -= amount
    current_user.total_sent += amount
    ref = gen_reference()
    t = Transaction(sender_id=current_user.id, amount=amount,
                    description='Withdrawal to bank', type='withdrawal', reference=ref)
    db.session.add(t)
    add_notification(current_user, '🏦 Withdrawal Initiated',
                     f'₹{amount:,.2f} will reach your bank in 2-3 days. Ref: {ref}', 'info')
    log_activity(current_user, 'Withdrawal', f'₹{amount}')
    db.session.commit()
    return jsonify({'success': True, 'balance': round(current_user.balance, 2), 'reference': ref})


@app.route('/api/transfer', methods=['POST'])
@login_required
def api_transfer():
    data = request.get_json() or {}
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400

    identifier = str(data.get('identifier', '')).strip()
    description = str(data.get('description', '')).strip()
    category = str(data.get('category', 'other')).strip()

    if amount <= 0:
        return jsonify({'error': 'Amount must be positive'}), 400
    if amount > 50000:
        return jsonify({'error': 'Single transfer limit is ₹50,000'}), 400
    if not identifier:
        return jsonify({'error': 'Recipient email or account number required'}), 400

    receiver = db.session.scalar(
        db.select(User).where(
            (User.email == identifier) | (User.account_number == identifier)
        )
    )
    if not receiver:
        return jsonify({'error': 'No user found with that email or account number'}), 404
    if receiver.id == current_user.id:
        return jsonify({'error': 'Cannot transfer to yourself'}), 400

    fee = round(amount * 0.001, 2) if amount > 1000 else 0.0
    total_deduct = amount + fee

    if current_user.balance < total_deduct:
        return jsonify({'error': f'Insufficient balance. Need ₹{total_deduct:.2f} (incl. ₹{fee:.2f} fee)'}), 400

    current_user.balance -= total_deduct
    current_user.total_sent += amount
    current_user.total_txn_count += 1
    receiver.balance += amount
    receiver.total_received += amount
    receiver.total_txn_count += 1

    ref = gen_reference()
    t = Transaction(sender_id=current_user.id, receiver_id=receiver.id,
                    amount=amount, description=description or f'Transfer to {receiver.username}',
                    type='transfer', category=category, reference=ref, fee=fee)
    db.session.add(t)

    current_user.award_xp(15)
    add_notification(receiver, '💸 Money Received!',
                     f'You received ₹{amount:,.2f} from {current_user.username}. Ref: {ref}', 'success')
    add_notification(current_user, '✅ Transfer Successful',
                     f'₹{amount:,.2f} sent to {receiver.username}. Ref: {ref}', 'success')
    log_activity(current_user, 'Transfer Sent', f'₹{amount} to {receiver.username}')

    # Auto-save contact
    existing = Contact.query.filter_by(user_id=current_user.id, contact_id=receiver.id).first()
    if not existing:
        db.session.add(Contact(user_id=current_user.id, contact_id=receiver.id))

    db.session.commit()
    return jsonify({'success': True, 'balance': round(current_user.balance, 2),
                    'reference': ref, 'fee': fee, 'receiver_name': receiver.username})


# ── API: User Lookup ───────────────────────────────────────────────────────────

@app.route('/api/user/lookup')
@login_required
def api_lookup():
    q = request.args.get('q', '').strip()
    if len(q) < 3:
        return jsonify({'error': 'Too short'}), 400
    u = db.session.scalar(
        db.select(User).where((User.email == q) | (User.account_number == q))
    )
    if not u:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'id': u.id, 'username': u.username,
                    'account_number': u.account_number, 'tier': u.tier})


@app.route('/api/user')
@login_required
def api_user():
    return jsonify(current_user.to_dict())


# ── API: Transactions ──────────────────────────────────────────────────────────

@app.route('/api/transactions')
@login_required
def api_transactions():
    page = int(request.args.get('page', 1))
    uid = current_user.id
    txns = Transaction.query.filter(
        (Transaction.sender_id == uid) | (Transaction.receiver_id == uid)
    ).order_by(Transaction.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return jsonify([t.serialize(uid) for t in txns.items])


@app.route('/api/analytics')
@login_required
def api_analytics():
    uid = current_user.id
    days_data = []
    for i in range(29, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).date()
        spent = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))\
            .filter(Transaction.sender_id == uid,
                    db.func.date(Transaction.created_at) == day.isoformat(),
                    Transaction.type.in_(['transfer', 'withdrawal'])).scalar()
        received = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))\
            .filter(Transaction.receiver_id == uid,
                    db.func.date(Transaction.created_at) == day.isoformat(),
                    Transaction.type.in_(['transfer', 'deposit'])).scalar()
        days_data.append({'date': day.strftime('%m/%d'),
                          'spent': round(spent, 2), 'received': round(received, 2)})

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    cats = db.session.query(Transaction.category,
                             db.func.sum(Transaction.amount).label('total'))\
        .filter(Transaction.sender_id == uid,
                Transaction.created_at >= month_start,
                Transaction.type == 'transfer')\
        .group_by(Transaction.category).all()

    return jsonify({
        'daily': days_data,
        'categories': [{'category': c[0], 'total': round(c[1], 2)} for c in cats]
    })


# ── API: Savings ───────────────────────────────────────────────────────────────

@app.route('/api/savings/create', methods=['POST'])
@login_required
def api_savings_create():
    data = request.get_json() or {}
    name = str(data.get('name', '')).strip()
    try:
        target = float(data.get('target', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid target'}), 400
    emoji = str(data.get('emoji', '🎯'))
    deadline = str(data.get('deadline', ''))

    if not name or target <= 0:
        return jsonify({'error': 'Name and target amount required'}), 400

    g = SavingsGoal(user_id=current_user.id, name=name, target=target,
                    emoji=emoji, deadline=deadline)
    db.session.add(g)
    current_user.award_xp(20)
    add_notification(current_user, f'{emoji} Goal Created!',
                     f'"{name}" — Target ₹{target:,.0f}. You got this!', 'info')
    db.session.commit()
    return jsonify({'success': True, 'goal': g.to_dict()})


@app.route('/api/savings/deposit', methods=['POST'])
@login_required
def api_savings_deposit():
    data = request.get_json() or {}
    goal_id = data.get('goal_id')
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400

    g = SavingsGoal.query.filter_by(id=goal_id, user_id=current_user.id).first()
    if not g:
        return jsonify({'error': 'Goal not found'}), 404
    if amount <= 0 or current_user.balance < amount:
        return jsonify({'error': 'Insufficient balance or invalid amount'}), 400

    current_user.balance -= amount
    current_user.savings_balance += amount
    g.current += amount
    ref = gen_reference()
    db.session.add(Transaction(sender_id=current_user.id, amount=amount,
                               description=f'Savings: {g.name}', type='savings', reference=ref))
    current_user.award_xp(10)
    if g.current >= g.target:
        add_notification(current_user, '🏆 Goal Achieved!',
                         f'You\'ve hit your "{g.name}" target of ₹{g.target:,.0f}!', 'success')
        current_user.award_xp(100)
    db.session.commit()
    return jsonify({'success': True, 'balance': round(current_user.balance, 2),
                    'goal': g.to_dict()})


@app.route('/api/savings/withdraw', methods=['POST'])
@login_required
def api_savings_withdraw():
    data = request.get_json() or {}
    goal_id = data.get('goal_id')
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400

    g = SavingsGoal.query.filter_by(id=goal_id, user_id=current_user.id).first()
    if not g or g.current < amount:
        return jsonify({'error': 'Insufficient savings'}), 400

    current_user.balance += amount
    current_user.savings_balance -= amount
    g.current -= amount
    db.session.commit()
    return jsonify({'success': True, 'balance': round(current_user.balance, 2),
                    'goal': g.to_dict()})


@app.route('/api/savings/delete/<int:goal_id>', methods=['DELETE'])
@login_required
def api_savings_delete(goal_id):
    g = SavingsGoal.query.filter_by(id=goal_id, user_id=current_user.id).first()
    if not g:
        return jsonify({'error': 'Not found'}), 404
    if g.current > 0:
        current_user.balance += g.current
        current_user.savings_balance -= g.current
    db.session.delete(g)
    db.session.commit()
    return jsonify({'success': True})


# ── API: Notifications ─────────────────────────────────────────────────────────

@app.route('/api/notifications')
@login_required
def api_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).limit(30).all()
    return jsonify([n.to_dict() for n in notifs])


@app.route('/api/notifications/read', methods=['POST'])
@login_required
def api_notif_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


# ── API: Contacts ──────────────────────────────────────────────────────────────

@app.route('/api/contacts/add', methods=['POST'])
@login_required
def api_contact_add():
    data = request.get_json() or {}
    identifier = str(data.get('identifier', '')).strip()
    nickname = str(data.get('nickname', '')).strip()
    if not identifier:
        return jsonify({'error': 'Identifier required'}), 400

    u = db.session.scalar(
        db.select(User).where((User.email == identifier) | (User.account_number == identifier))
    )
    if not u:
        return jsonify({'error': 'User not found'}), 404
    if u.id == current_user.id:
        return jsonify({'error': 'Cannot add yourself'}), 400

    existing = Contact.query.filter_by(user_id=current_user.id, contact_id=u.id).first()
    if existing:
        return jsonify({'error': 'Already in contacts'}), 400

    db.session.add(Contact(user_id=current_user.id, contact_id=u.id, nickname=nickname))
    db.session.commit()
    return jsonify({'success': True, 'username': u.username})


@app.route('/api/contacts/delete/<int:cid>', methods=['DELETE'])
@login_required
def api_contact_delete(cid):
    c = Contact.query.filter_by(id=cid, user_id=current_user.id).first()
    if not c:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(c)
    db.session.commit()
    return jsonify({'success': True})


# ── API: Scheduled Payments ────────────────────────────────────────────────────

@app.route('/api/scheduled/create', methods=['POST'])
@login_required
def api_sched_create():
    data = request.get_json() or {}
    identifier = str(data.get('identifier', '')).strip()
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400
    frequency = str(data.get('frequency', 'monthly'))
    next_date = str(data.get('next_date', ''))
    description = str(data.get('description', ''))

    if not identifier or amount <= 0 or not next_date:
        return jsonify({'error': 'All fields required'}), 400

    receiver = db.session.scalar(
        db.select(User).where((User.email == identifier) | (User.account_number == identifier))
    )
    if not receiver:
        return jsonify({'error': 'Recipient not found'}), 404

    sp = ScheduledPayment(sender_id=current_user.id, receiver_id=receiver.id,
                          amount=amount, description=description,
                          frequency=frequency, next_date=next_date)
    db.session.add(sp)
    current_user.award_xp(10)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/scheduled/delete/<int:sid>', methods=['DELETE'])
@login_required
def api_sched_delete(sid):
    sp = ScheduledPayment.query.filter_by(id=sid, sender_id=current_user.id).first()
    if not sp:
        return jsonify({'error': 'Not found'}), 404
    sp.active = False
    db.session.commit()
    return jsonify({'success': True})


# ── API: Split Bills ───────────────────────────────────────────────────────────

@app.route('/api/split/create', methods=['POST'])
@login_required
def api_split_create():
    data = request.get_json() or {}
    title = str(data.get('title', '')).strip()
    try:
        total = float(data.get('total_amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400
    members_raw = data.get('members', [])
    description = str(data.get('description', ''))

    if not title or total <= 0 or not members_raw:
        return jsonify({'error': 'Title, amount and members required'}), 400

    bill = SplitBill(creator_id=current_user.id, title=title,
                     total_amount=total, description=description)
    db.session.add(bill)
    db.session.flush()

    # Creator marked as paid with 0
    db.session.add(SplitBillMember(bill_id=bill.id, user_id=current_user.id,
                                   amount_owed=0, paid=True))
    for m in members_raw:
        u = db.session.scalar(
            db.select(User).where(
                (User.email == m['identifier']) | (User.account_number == m['identifier'])
            )
        )
        if u:
            db.session.add(SplitBillMember(bill_id=bill.id, user_id=u.id,
                                           amount_owed=float(m['amount'])))
            add_notification(u, '🧾 Split Bill',
                             f'{current_user.username} added you to "{title}". You owe ₹{m["amount"]:.2f}',
                             'warning')

    current_user.award_xp(15)
    db.session.commit()
    return jsonify({'success': True, 'bill_id': bill.id})


@app.route('/api/split/pay/<int:bill_id>', methods=['POST'])
@login_required
def api_split_pay(bill_id):
    membership = SplitBillMember.query.filter_by(
        bill_id=bill_id, user_id=current_user.id, paid=False).first()
    if not membership:
        return jsonify({'error': 'Nothing to pay or already paid'}), 400

    bill = db.session.get(SplitBill, bill_id)
    amount = membership.amount_owed

    if current_user.balance < amount:
        return jsonify({'error': 'Insufficient balance'}), 400

    current_user.balance -= amount
    creator = db.session.get(User, bill.creator_id)
    creator.balance += amount

    ref = gen_reference()
    db.session.add(Transaction(sender_id=current_user.id, receiver_id=bill.creator_id,
                               amount=amount, description=f'Split: {bill.title}',
                               type='split', reference=ref))
    membership.paid = True
    membership.paid_at = datetime.utcnow()
    add_notification(creator, '💸 Split Payment',
                     f'{current_user.username} paid ₹{amount:.2f} for "{bill.title}"', 'success')
    db.session.commit()
    return jsonify({'success': True, 'balance': round(current_user.balance, 2)})


# ── API: Budget ────────────────────────────────────────────────────────────────

@app.route('/api/budget/update', methods=['POST'])
@login_required
def api_budget_update():
    data = request.get_json() or {}
    cat = BudgetCategory.query.filter_by(id=data.get('id'), user_id=current_user.id).first()
    if not cat:
        return jsonify({'error': 'Not found'}), 404
    try:
        cat.monthly_limit = float(data.get('monthly_limit', cat.monthly_limit))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid limit'}), 400
    db.session.commit()
    return jsonify({'success': True})


# ── API: Profile ───────────────────────────────────────────────────────────────

@app.route('/api/profile/update', methods=['POST'])
@login_required
def api_profile_update():
    data = request.get_json() or {}
    username = str(data.get('username', '')).strip()
    if not username:
        return jsonify({'error': 'Username required'}), 400
    current_user.username = username
    current_user.bio = str(data.get('bio', '')).strip()
    current_user.phone = str(data.get('phone', '')).strip()
    log_activity(current_user, 'Profile Updated')
    db.session.commit()
    return jsonify({'success': True})


# ── API: Delete Account ────────────────────────────────────────────────────────

@app.route('/api/account/delete', methods=['DELETE'])
@login_required
def api_delete_account():
    user = current_user
    logout_user()
    # relationships with cascade='all, delete-orphan' handle most cleanup
    # but we manually clean transactions referencing this user as receiver
    Transaction.query.filter_by(receiver_id=user.id).delete()
    # Clean up split bill memberships
    SplitBillMember.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})


# ── Boot ───────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
