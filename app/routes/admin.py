from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from app.forms.auth import LoginForm
from app.models.user import User, ScanHistory
from app.models.arbitrage import ArbitrageOpportunity
from app.models.admin import AdminRole, SiteSettings
from app.models.subscription import SubscriptionRequest
from app.config.config_manager import ConfigManager
from app.database import db
from app.services.background_scanner import background_scanner

bp = Blueprint('admin', __name__, url_prefix='/admin')
config_manager = ConfigManager()

def is_admin_user(user: User) -> bool:
    if not user:
        return False
    return AdminRole.query.filter_by(user_id=user.id).first() is not None

def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login', next=request.url))
        if not is_admin_user(current_user):
            flash('Admin access required', 'error')
            return redirect(url_for('dashboard.index'))
        return func(*args, **kwargs)
    return wrapper

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and is_admin_user(current_user):
        return redirect(url_for('admin.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password', 'error')
            return redirect(url_for('admin.login'))
        if not is_admin_user(user):
            flash('You do not have admin access', 'error')
            return redirect(url_for('admin.login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next') or url_for('admin.index')
        return redirect(next_page)
    return render_template('admin/login.html', form=form)

@bp.route('/logout')
@login_required
@admin_required
def logout():
    logout_user()
    return redirect(url_for('admin.login'))

@bp.route('/')
@login_required
@admin_required
def index():
    last_24h = datetime.utcnow() - timedelta(days=1)
    last_week = datetime.utcnow() - timedelta(days=7)

    total_users = User.query.count()
    active_users = User.query.filter(User._is_active == True).count()
    scans_24h = db.session.query(func.count(ScanHistory.id)).filter(ScanHistory.created_at >= last_24h).scalar() or 0
    active_opps = ArbitrageOpportunity.query.filter_by(is_active=True).count()
    opps_week = ArbitrageOpportunity.query.filter(ArbitrageOpportunity.timestamp >= last_week).count()

    best_pairs = (ArbitrageOpportunity.query
                  .filter(ArbitrageOpportunity.timestamp >= last_week)
                  .order_by(ArbitrageOpportunity.net_profit_percent.desc())
                  .limit(10).all())

    profit_week = db.session.query(func.sum(ArbitrageOpportunity.profit_on_1000)).filter(ArbitrageOpportunity.timestamp >= last_week).scalar() or 0.0

    scanner_status = background_scanner.get_status()

    return render_template(
        'admin/index.html',
        stats={
            'total_users': total_users,
            'active_users': active_users,
            'scans_24h': scans_24h,
            'active_opportunities': active_opps,
            'opportunities_week': opps_week,
            'profit_week_approx': profit_week,
        },
        best_pairs=best_pairs,
        scanner_status=scanner_status
    )

@bp.route('/scanner/status')
@login_required
@admin_required
def scanner_status():
    return jsonify({'success': True, 'status': background_scanner.get_status()})

@bp.route('/users')
@login_required
@admin_required
def users():
    q = request.args.get('q', '').strip()
    query = User.query
    if q:
        ilike = f"%{q}%"
        query = query.filter(db.or_(User.username.ilike(ilike), User.email.ilike(ilike)))
    users = query.order_by(User.created_at.desc()).limit(200).all()
    admin_ids = set(r.user_id for r in AdminRole.query.all())
    return render_template('admin/users.html', users=users, admin_ids=admin_ids)

@bp.route('/users/<int:user_id>/update', methods=['POST'])
@login_required
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    is_active = request.form.get('is_active') == 'on'

    if username and username != user.username:
        existing = User.query.filter_by(username=username).first()
        if existing and existing.id != user.id:
            flash('Username already taken', 'error')
            return redirect(url_for('admin.users'))
        user.username = username

    if email and email != user.email:
        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != user.id:
            flash('Email already registered', 'error')
            return redirect(url_for('admin.users'))
        user.email = email

    user.is_active = is_active
    db.session.commit()
    flash('User updated', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/users/<int:user_id>/subscription', methods=['POST'])
@login_required
@admin_required
def update_subscription(user_id):
    user = User.query.get_or_404(user_id)
    tier = request.form.get('subscription_tier', '').strip()
    tier_info = config_manager.get_subscription_tier(tier)
    if not tier_info:
        flash('Invalid subscription tier', 'error')
        return redirect(url_for('admin.users'))
    user.subscription_tier = tier
    db.session.commit()
    flash('Subscription updated', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/users/<int:user_id>/make-admin', methods=['POST'])
@login_required
@admin_required
def make_admin(user_id):
    if AdminRole.query.filter_by(user_id=user_id).first() is None:
        db.session.add(AdminRole(user_id=user_id))
        db.session.commit()
    flash('Admin role granted', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/users/<int:user_id>/remove-admin', methods=['POST'])
@login_required
@admin_required
def remove_admin(user_id):
    role = AdminRole.query.filter_by(user_id=user_id).first()
    if role:
        db.session.delete(role)
        db.session.commit()
    flash('Admin role removed', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    if request.method == 'POST':
        scanner_interval = int(request.form.get('scanner_interval', '300') or 300)
        min_dollar_profit = float(request.form.get('min_dollar_profit', '10') or 10)
        maintenance_mode = bool(request.form.get('maintenance_mode'))
        announcement = request.form.get('announcement', '').strip()
        wallet_tokens = request.form.getlist('wallet_token[]')
        wallet_labels = request.form.getlist('wallet_label[]')
        wallet_addresses = request.form.getlist('wallet_address[]')
        wallet_cg_ids = request.form.getlist('wallet_coingecko_id[]')
        wallets = {}
        for i in range(0, len(wallet_tokens)):
            tok = (wallet_tokens[i] or '').strip()
            lbl = (wallet_labels[i] or '').strip()
            addr = (wallet_addresses[i] or '').strip()
            cg = (wallet_cg_ids[i] or '').strip() if i < len(wallet_cg_ids) else ''
            if tok:
                entry = {'label': lbl or tok, 'address': addr}
                if cg:
                    entry['coingecko_id'] = cg
                wallets[tok] = entry

        SiteSettings.set('scanner_interval', {'value': scanner_interval})
        SiteSettings.set('min_dollar_profit', {'value': min_dollar_profit})
        SiteSettings.set('maintenance_mode', {'value': maintenance_mode})
        SiteSettings.set('announcement', {'value': announcement})
        if wallets:
            SiteSettings.set('payment_wallets', wallets)

        background_scanner.scan_interval = scanner_interval
        background_scanner.min_dollar_profit = min_dollar_profit

        flash('Settings updated', 'success')
        return redirect(url_for('admin.settings'))

    scanner_interval = SiteSettings.get('scanner_interval', {'value': background_scanner.scan_interval})['value']
    min_dollar_profit = SiteSettings.get('min_dollar_profit', {'value': background_scanner.min_dollar_profit})['value']
    maintenance_mode = SiteSettings.get('maintenance_mode', {'value': False})['value']
    announcement = SiteSettings.get('announcement', {'value': ''})['value']
    wallets = SiteSettings.get('payment_wallets', {
        'BTC': {'address': '', 'label': 'Bitcoin', 'coingecko_id': 'bitcoin'},
        'ETH': {'address': '', 'label': 'Ethereum', 'coingecko_id': 'ethereum'},
        'USDT-ERC20': {'address': '', 'label': 'USDT (ERC20)', 'coingecko_id': 'tether'},
        'USDT-TRC20': {'address': '', 'label': 'USDT (TRC20)', 'coingecko_id': 'tether'},
        'SOL': {'address': '', 'label': 'Solana', 'coingecko_id': 'solana'}
    })

    return render_template('admin/settings.html',
                           scanner_interval=scanner_interval,
                           min_dollar_profit=min_dollar_profit,
                           maintenance_mode=maintenance_mode,
                           announcement=announcement,
                           wallets=wallets)

@bp.route('/subscriptions')
@login_required
@admin_required
def subscriptions():
    requests = SubscriptionRequest.query.order_by(SubscriptionRequest.created_at.desc()).limit(200).all()
    return render_template('admin/subscriptions.html', requests=requests)

@bp.route('/subscriptions/<int:req_id>/verify', methods=['POST'])
@login_required
@admin_required
def verify_subscription(req_id):
    req = SubscriptionRequest.query.get_or_404(req_id)
    user = User.query.get(req.user_id)
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin.subscriptions'))
    user.subscription_tier = req.tier_requested
    req.status = 'verified'
    req.verified_at = datetime.utcnow()
    db.session.commit()
    flash('Subscription upgraded', 'success')
    return redirect(url_for('admin.subscriptions'))

@bp.route('/subscriptions/<int:req_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_subscription(req_id):
    req = SubscriptionRequest.query.get_or_404(req_id)
    req.status = 'rejected'
    req.rejected_at = datetime.utcnow()
    db.session.commit()
    flash('Subscription request rejected', 'warning')
    return redirect(url_for('admin.subscriptions'))
