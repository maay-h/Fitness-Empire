import json
import os
import re
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, send_file, session
import io
from datetime import datetime, timedelta, date
from database import get_db, init_db
from werkzeug.security import generate_password_hash, check_password_hash
from whatsapp.sender import send_welcome_message, send_expiry_reminder, send_balance_reminder
from mail.sender import send_welcome_email, send_expiry_reminder_email, send_balance_reminder_email, load_config as load_mail_config

load_mail_config()

SITE_PASSWORD = os.getenv('SITE_PASSWORD', 'gym@123')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fitness-empire-secret-key-2024')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

def normalize_phone(phone):
    if not phone:
        return phone
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('91') and len(digits) == 12:
        return digits
    if len(digits) == 10:
        return '91' + digits
    return phone

def load_admin_password_hash():
    try:
        with open(CONFIG_PATH, 'r') as f:
            cfg = json.load(f)
        return cfg.get('admin_password_hash', '')
    except:
        return ''

def save_admin_password_hash(hash):
    try:
        with open(CONFIG_PATH, 'r') as f:
            cfg = json.load(f)
        cfg['admin_password_hash'] = hash
        with open(CONFIG_PATH, 'w') as f:
            json.dump(cfg, f, indent=4)
        return True
    except:
        return False

@app.before_request
def update_expired_status():
    conn = get_db()
    conn.execute("UPDATE members SET status='expired' WHERE expiry_date < CURRENT_DATE AND status='active'")
    conn.commit()
    conn.close()

@app.before_request
def require_site_login():
    if request.path.startswith('/static/') or request.path.startswith('/login'):
        return
    if not session.get('site_authenticated'):
        return redirect(url_for('site_login'))

@app.route('/login', methods=['GET', 'POST'])
def site_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == SITE_PASSWORD:
            session['site_authenticated'] = True
            return redirect(url_for('index'))
        flash('Wrong password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def site_logout():
    session.pop('site_authenticated', None)
    return redirect(url_for('site_login'))

@app.after_request
def add_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

@app.template_filter('date_format')
def date_format(value):
    if value:
        try:
            if isinstance(value, str):
                dt = datetime.strptime(value, '%Y-%m-%d')
            else:
                dt = value
            return dt.strftime('%d %b %Y')
        except:
            return str(value) if value else ''
    return ''

@app.template_filter('phone_format')
def phone_format(value):
    if value and value.startswith('91') and len(value) == 12:
        return '+' + value
    return value or ''

@app.template_filter('days_remaining')
def days_remaining(value):
    if value:
        try:
            if isinstance(value, str):
                expiry = datetime.strptime(value, '%Y-%m-%d').date()
            else:
                expiry = value
            delta = (expiry - date.today()).days
            return delta
        except:
            return 0
    return 0

ALLOWED_ADMIN_ENDPOINTS = {'admin', 'admin_sales_data', 'download_sales_pdf', 'download_members_pdf', 'verify_admin', 'static'}

@app.before_request
def startup():
    init_db()
    if request.endpoint and request.endpoint not in ALLOWED_ADMIN_ENDPOINTS:
        session.pop('admin_verified', None)

@app.context_processor
def inject_globals():
    return {'admin_password_set': bool(load_admin_password_hash())}

@app.route('/')
def index():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) as cnt FROM members').fetchone()['cnt']
    active = conn.execute("SELECT COUNT(*) as cnt FROM members WHERE status='active'").fetchone()['cnt']
    expired = conn.execute("SELECT COUNT(*) as cnt FROM members WHERE status='expired'").fetchone()['cnt']
    expiring_soon = conn.execute(
        "SELECT COUNT(*) as cnt FROM members WHERE expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7 AND status='active'"
    ).fetchone()['cnt']
    pending_balances = conn.execute(
        "SELECT COUNT(*) as cnt FROM members WHERE balance_amount > 0 AND balance_amount IS NOT NULL"
    ).fetchone()['cnt']
    conn.close()
    return render_template('dashboard.html', total=total, active=active, expired=expired, expiring_soon=expiring_soon, pending_balances=pending_balances)

@app.route('/members')
def members():
    status_filter = request.args.get('status', '')
    plan_filter = request.args.get('plan', '')
    search_query = request.args.get('q', '').strip()
    query = 'SELECT * FROM members WHERE 1=1'
    params = []
    if search_query:
        query += " AND (name LIKE %s OR phone LIKE %s OR email LIKE %s OR bill_number LIKE %s)"
        like = f'%{search_query}%'
        params.extend([like, like, like, like])
    if status_filter:
        if status_filter == 'expiring':
            query += " AND status='active' AND expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7"
        else:
            query += ' AND status=%s'
            params.append(status_filter)
    if plan_filter:
        query += ' AND plan=%s'
        params.append(plan_filter)
    query += ' ORDER BY id DESC'
    conn = get_db()
    members_list = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('members.html', members=members_list, selected_status=status_filter, selected_plan=plan_filter, search_query=search_query)

@app.route('/member/<int:member_id>')
def member_detail(member_id):
    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    history = conn.execute(
        'SELECT * FROM membership_history WHERE member_id = %s ORDER BY renewed_at DESC',
        (member_id,)
    ).fetchall()
    payments = conn.execute(
        'SELECT * FROM payments WHERE member_id = %s ORDER BY payment_date DESC',
        (member_id,)
    ).fetchall()
    conn.close()
    if not member:
        flash('Member not found', 'danger')
        return redirect(url_for('members'))
    return render_template('member_detail.html', member=member, history=history, payments=payments)

@app.route('/member/<int:member_id>/notes', methods=['POST'])
def update_notes(member_id):
    notes = request.form.get('notes', '').strip()
    conn = get_db()
    conn.execute('UPDATE members SET notes = %s WHERE id = %s', (notes, member_id))
    conn.commit()
    conn.close()
    flash('Note updated successfully', 'success')
    return redirect(url_for('member_detail', member_id=member_id))

@app.route('/members/add', methods=['GET', 'POST'])
def add_member():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        phone = normalize_phone(request.form.get('phone', '').strip())
        plan = request.form['plan']
        joining_date = request.form.get('joining_date', '').strip()
        expiry_date = request.form.get('expiry_date', '').strip()
        bill_number = request.form.get('bill_number', '').strip()
        trainer = request.form.get('trainer', '').strip()
        price = float(request.form.get('price', 0) or 0)
        payment_mode = request.form.get('payment_mode', 'Cash')
        paid_date = request.form.get('paid_date', '').strip()
        if payment_mode == 'Both':
            cash_amount = float(request.form.get('cash_amount', 0) or 0)
            online_amount = float(request.form.get('online_amount', 0) or 0)
            amount_paid = cash_amount + online_amount
        else:
            cash_amount = float(request.form.get('amount_paid', 0) or 0) if payment_mode == 'Cash' else 0
            online_amount = float(request.form.get('amount_paid', 0) or 0) if payment_mode == 'Online' else 0
            amount_paid = float(request.form.get('amount_paid', 0) or 0)
        auto_balance = max(0, price - amount_paid)
        has_balance = request.form.get('has_balance') == 'yes' or auto_balance > 0
        balance_amount = max(auto_balance, float(request.form.get('balance_amount', 0) or 0))
        balance_due_date = request.form.get('balance_due_date', '') if has_balance else ''
        joining_date = joining_date or None
        expiry_date = expiry_date or None
        paid_date = paid_date or None
        balance_due_date = balance_due_date or None

        if not name or not plan:
            flash('Name and Plan are required', 'danger')
            return render_template('add_member.html')

        if joining_date and expiry_date and expiry_date < joining_date:
            flash('Expiry date cannot be before joining date', 'danger')
            return render_template('add_member.html')

        if not has_balance:
            amount_paid = price
            auto_balance = 0
            balance_amount = 0

        if expiry_date and expiry_date < str(date.today()):
            status = 'expired'
        else:
            status = 'active'

        conn = get_db()
        cur = conn.execute(
            '''INSERT INTO members (name, email, phone, plan, joining_date, expiry_date,
               price, amount_paid, balance_amount, balance_due_date, status, bill_number, trainer,
               payment_mode, paid_date, cash_amount, online_amount)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id''',
            (name, email, phone, plan, joining_date, expiry_date,
             price, amount_paid, balance_amount, balance_due_date, status, bill_number, trainer,
             payment_mode, paid_date, cash_amount, online_amount)
        )
        member_id = cur.fetchone()['id']
        conn.execute(
            '''INSERT INTO membership_history (member_id, plan, start_date, expiry_date,
               price, amount_paid, balance_amount, balance_due_date,
               payment_mode, paid_date, cash_amount, online_amount)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
             (member_id, plan, joining_date, expiry_date, price, amount_paid, balance_amount, balance_due_date,
             payment_mode, paid_date, cash_amount, online_amount)
        )
        if amount_paid > 0:
            conn.execute(
                'INSERT INTO payments (member_id, amount, payment_date, payment_mode, plan) VALUES (%s, %s, %s, %s, %s)',
                (member_id, amount_paid, paid_date or joining_date or str(date.today()), payment_mode, plan)
            )
        conn.commit()
        conn.close()

        if status == 'active' and phone:
            msgs = []
            wa_ok, wa_msg = send_welcome_message(
                phone=phone, name=name, plan=plan,
                joining_date=joining_date, expiry_date=expiry_date
            )
            msgs.append(f'WhatsApp: {wa_msg}')
            if email:
                mail_ok, mail_msg = send_welcome_email(email, name, plan, joining_date, expiry_date)
                msgs.append(f'Email: {mail_msg}')
            flash('Member added successfully! ' + ' | '.join(msgs), 'success' if wa_ok else 'warning')
        else:
            flash('Member added successfully!', 'success')

        return redirect(url_for('members'))

    return render_template('add_member.html')

@app.route('/members/edit/<int:member_id>', methods=['GET', 'POST'])
def edit_member(member_id):
    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    if not member:
        flash('Member not found', 'danger')
        return redirect(url_for('members'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        phone = normalize_phone(request.form.get('phone', '').strip())
        plan = request.form['plan']
        joining_date = request.form.get('joining_date', '').strip()
        expiry_date = request.form.get('expiry_date', '').strip()
        bill_number = request.form.get('bill_number', '').strip()
        trainer = request.form.get('trainer', '').strip()
        price = float(request.form.get('price', 0) or 0)
        payment_mode = request.form.get('payment_mode', 'Cash')
        paid_date = request.form.get('paid_date', '').strip()
        if payment_mode == 'Both':
            cash_amount = float(request.form.get('cash_amount', 0) or 0)
            online_amount = float(request.form.get('online_amount', 0) or 0)
            amount_paid = cash_amount + online_amount
        else:
            cash_amount = float(request.form.get('amount_paid', 0) or 0) if payment_mode == 'Cash' else 0
            online_amount = float(request.form.get('amount_paid', 0) or 0) if payment_mode == 'Online' else 0
            amount_paid = float(request.form.get('amount_paid', 0) or 0)
        has_balance = request.form.get('has_balance') == 'yes'
        balance_amount = float(request.form.get('balance_amount', 0) or 0) if has_balance else 0
        balance_due_date = request.form.get('balance_due_date', '') if has_balance else ''
        joining_date = joining_date or None
        expiry_date = expiry_date or None
        paid_date = paid_date or None
        balance_due_date = balance_due_date or None
        status = request.form.get('status', member['status'])

        if joining_date and expiry_date and expiry_date < joining_date:
            flash('Expiry date cannot be before joining date', 'danger')
            return render_template('edit_member.html', member=member)

        if not has_balance:
            amount_paid = price
            balance_amount = 0

        if expiry_date:
            status = 'expired' if expiry_date < str(date.today()) else 'active'

        conn.execute(
            '''UPDATE members SET name=%s, email=%s, phone=%s, plan=%s, joining_date=%s,
               expiry_date=%s, price=%s, amount_paid=%s, balance_amount=%s,
               balance_due_date=%s, status=%s, bill_number=%s, trainer=%s,
               payment_mode=%s, paid_date=%s, cash_amount=%s, online_amount=%s WHERE id=%s''',
            (name, email, phone, plan, joining_date, expiry_date,
             price, amount_paid, balance_amount, balance_due_date, status, bill_number, trainer,
             payment_mode, paid_date, cash_amount, online_amount, member_id)
        )
        existing = conn.execute(
            'SELECT id FROM payments WHERE member_id = %s ORDER BY id ASC LIMIT 1',
            (member_id,)
        ).fetchone()
        pay_date = paid_date or joining_date or str(date.today())
        if existing:
            conn.execute(
                'UPDATE payments SET amount=%s, payment_date=%s, payment_mode=%s WHERE id=%s',
                (amount_paid, pay_date, payment_mode, existing['id'])
            )
        elif amount_paid > 0:
            conn.execute(
                'INSERT INTO payments (member_id, amount, payment_date, payment_mode, plan) VALUES (%s, %s, %s, %s, %s)',
                (member_id, amount_paid, pay_date, payment_mode, plan)
            )
        conn.commit()
        conn.close()
        flash('Member updated successfully!', 'success')
        return redirect(url_for('member_detail', member_id=member_id))

    conn.close()
    return render_template('edit_member.html', member=member)

@app.route('/members/renew/<int:member_id>', methods=['GET', 'POST'])
def renew_member(member_id):
    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    if not member:
        flash('Member not found', 'danger')
        return redirect(url_for('members'))

    if request.method == 'POST':
        new_plan = request.form['plan']
        start_date = request.form['start_date'] or None
        new_expiry = request.form['expiry_date'] or None
        price = float(request.form.get('price', 0) or 0)
        amount_paid = float(request.form.get('amount_paid', 0) or 0)
        auto_balance = max(0, price - amount_paid)
        has_balance = request.form.get('has_balance') == 'yes' or auto_balance > 0
        balance_amount = max(auto_balance, float(request.form.get('balance_amount', 0) or 0))
        balance_due_date = request.form.get('balance_due_date', '') if has_balance else ''
        balance_due_date = balance_due_date or None
        payment_mode = request.form.get('payment_mode', 'Cash')
        paid_date = request.form.get('paid_date', '').strip() or None

        if new_expiry < start_date:
            flash('New expiry date cannot be before start date', 'danger')
            return render_template('renew_member.html', member=member)

        if not has_balance:
            amount_paid = price
            auto_balance = 0
            balance_amount = 0

        new_status = 'expired' if new_expiry < str(date.today()) else 'active'
        conn.execute(
            '''UPDATE members SET plan=%s, joining_date=%s, expiry_date=%s, price=%s,
               amount_paid=%s, balance_amount=%s, balance_due_date=%s, status=%s,
               payment_mode=%s, paid_date=%s
               WHERE id=%s''',
            (new_plan, start_date, new_expiry, price, amount_paid,
             balance_amount, balance_due_date, new_status, payment_mode, paid_date, member_id)
        )
        conn.execute(
            '''INSERT INTO membership_history (member_id, plan, start_date, expiry_date,
               price, amount_paid, balance_amount, balance_due_date,
               payment_mode, paid_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (member_id, new_plan, start_date, new_expiry, price, amount_paid, balance_amount, balance_due_date,
             payment_mode, paid_date)
        )
        if amount_paid > 0:
            conn.execute(
                'INSERT INTO payments (member_id, amount, payment_date, payment_mode, plan) VALUES (%s, %s, %s, %s, %s)',
                (member_id, amount_paid, paid_date or start_date or str(date.today()), payment_mode, new_plan)
            )
        conn.commit()
        conn.close()
        flash('Membership renewed successfully!', 'success')
        return redirect(url_for('member_detail', member_id=member_id))

    conn.close()
    return render_template('renew_member.html', member=member)

@app.route('/members/delete/<int:member_id>', methods=['POST'])
def delete_member(member_id):
    conn = get_db()
    conn.execute('DELETE FROM members WHERE id = %s', (member_id,))
    conn.commit()
    conn.close()
    flash('Member deleted successfully!', 'success')
    return redirect(url_for('members'))

@app.route('/expiring')
def expiring_members():
    conn = get_db()
    members_list = conn.execute(
        "SELECT * FROM members WHERE expiry_date BETWEEN CURRENT_DATE - 1 AND CURRENT_DATE + 7 AND status='active' ORDER BY expiry_date ASC"
    ).fetchall()
    conn.close()
    return render_template('expiring.html', members=members_list)

@app.route('/expired')
def expired_members():
    conn = get_db()
    members_list = conn.execute(
        "SELECT * FROM members WHERE status='expired' ORDER BY expiry_date DESC"
    ).fetchall()
    conn.close()
    return render_template('expired.html', members=members_list)

@app.route('/balances')
def balance_list():
    conn = get_db()
    members_list = conn.execute(
        "SELECT * FROM members WHERE balance_amount > 0 AND balance_amount IS NOT NULL ORDER BY balance_due_date ASC"
    ).fetchall()
    conn.close()
    return render_template('balances.html', members=members_list, today=date.today())

@app.route('/pay-balance/<int:member_id>', methods=['POST'])
def pay_balance(member_id):
    amount = float(request.form.get('amount', 0) or 0)
    payment_date = request.form.get('payment_date', '').strip() or None
    payment_mode = request.form.get('payment_mode', 'Cash')
    if amount <= 0:
        flash('Invalid payment amount', 'danger')
        return redirect(url_for('balance_list'))

    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    if not member:
        flash('Member not found', 'danger')
        conn.close()
        return redirect(url_for('balance_list'))

    current_balance = member['balance_amount'] or 0
    if amount > current_balance:
        flash('Amount exceeds the pending balance', 'danger')
        conn.close()
        return redirect(url_for('balance_list'))

    new_paid = (member['amount_paid'] or 0) + amount
    new_balance = current_balance - amount

    # Record payment in payments table
    conn.execute(
        'INSERT INTO payments (member_id, amount, payment_date, payment_mode, plan) VALUES (%s, %s, %s, %s, %s)',
        (member_id, amount, payment_date, payment_mode, member['plan'])
    )

    # Update the latest membership_history row with the new payment info
    conn.execute(
        '''UPDATE membership_history SET amount_paid = amount_paid + %s,
           balance_amount = %s, payment_mode = %s, paid_date = %s
           WHERE id = (SELECT id FROM membership_history WHERE member_id = %s ORDER BY renewed_at DESC LIMIT 1)''',
        (amount, new_balance, payment_mode, payment_date, member_id)
    )

    if new_balance <= 0:
        conn.execute(
            'UPDATE members SET amount_paid=%s, balance_amount=0, balance_due_date=NULL WHERE id=%s',
            (new_paid, member_id)
        )
        flash(f'Payment of ₹{amount} received. Balance fully cleared!', 'success')
    else:
        conn.execute(
            'UPDATE members SET amount_paid=%s, balance_amount=%s WHERE id=%s',
            (new_paid, new_balance, member_id)
        )
        flash(f'Payment of ₹{amount} received. Remaining balance: ₹{new_balance}', 'success')

    conn.commit()
    conn.close()
    return redirect(url_for('balance_list'))

@app.route('/send-welcome/<int:member_id>', methods=['POST'])
def send_welcome(member_id):
    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    conn.close()
    if not member:
        return jsonify({'error': 'Member not found'}), 404

    _, url = send_welcome_message(
        phone=member['phone'],
        name=member['name'],
        plan=member['plan'],
        joining_date=member['joining_date'],
        expiry_date=member['expiry_date'],
        return_url=True
    )
    return jsonify({'url': url})

@app.route('/send-welcome-email/<int:member_id>', methods=['POST'])
def send_welcome_email_route(member_id):
    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    conn.close()
    if not member:
        flash('Member not found', 'danger')
        return redirect(url_for('members'))
    if not member['email']:
        flash('No email address for this member', 'warning')
        return redirect(url_for('member_detail', member_id=member_id))

    ok, msg = send_welcome_email(
        member['email'], member['name'], member['plan'],
        member['joining_date'], member['expiry_date']
    )
    flash(f'Email welcome sent to {member["name"]}: {msg}', 'success' if ok else 'warning')
    return redirect(url_for('member_detail', member_id=member_id))

@app.route('/send-reminder/<int:member_id>', methods=['POST'])
def send_reminder(member_id):
    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    conn.close()
    if not member:
        return jsonify({'error': 'Member not found'}), 404

    days_left = ((datetime.strptime(member['expiry_date'], '%Y-%m-%d').date() if isinstance(member['expiry_date'], str) else member['expiry_date']) - date.today()).days
    _, url = send_expiry_reminder(
        phone=member['phone'],
        name=member['name'],
        plan=member['plan'],
        expiry_date=member['expiry_date'],
        days_remaining=days_left,
        return_url=True
    )
    return jsonify({'url': url})

@app.route('/send-reminder-email/<int:member_id>', methods=['POST'])
def send_reminder_email_route(member_id):
    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    conn.close()
    if not member:
        flash('Member not found', 'danger')
        return redirect(url_for('members'))
    if not member['email']:
        flash('No email address for this member', 'warning')
        return redirect(url_for('member_detail', member_id=member_id))
    if not member['expiry_date']:
        flash('No expiry date for this member', 'warning')
        return redirect(url_for('member_detail', member_id=member_id))

    days_left = ((datetime.strptime(member['expiry_date'], '%Y-%m-%d').date() if isinstance(member['expiry_date'], str) else member['expiry_date']) - date.today()).days
    ok, msg = send_expiry_reminder_email(
        member['email'], member['name'], member['plan'],
        member['expiry_date'], days_left
    )
    flash(f'Email reminder sent to {member["name"]}: {msg}', 'success' if ok else 'warning')
    return redirect(url_for('member_detail', member_id=member_id))

@app.route('/send-balance-reminder/<int:member_id>', methods=['POST'])
def send_balance_reminder_route(member_id):
    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    conn.close()
    if not member:
        return jsonify({'error': 'Member not found'}), 404
    _, url = send_balance_reminder(
        phone=member['phone'],
        name=member['name'],
        amount=member['balance_amount'] or 0,
        due_date=member['balance_due_date'] or 'N/A',
        return_url=True
    )
    return jsonify({'url': url})

@app.route('/send-balance-reminder-email/<int:member_id>', methods=['POST'])
def send_balance_reminder_email_route(member_id):
    conn = get_db()
    member = conn.execute('SELECT * FROM members WHERE id = %s', (member_id,)).fetchone()
    conn.close()
    if not member:
        flash('Member not found', 'danger')
        return redirect(url_for('members'))
    if not member['email']:
        flash('No email address for this member', 'warning')
        return redirect(url_for('member_detail', member_id=member_id))
    if not member['balance_amount'] or member['balance_amount'] <= 0:
        flash('No pending balance for this member', 'warning')
        return redirect(url_for('member_detail', member_id=member_id))
    ok, msg = send_balance_reminder_email(
        member['email'], member['name'],
        member['balance_amount'] or 0,
        member['balance_due_date'] or 'N/A'
    )
    flash(f'Balance reminder email sent to {member["name"]}: {msg}', 'success' if ok else 'warning')
    return redirect(url_for('member_detail', member_id=member_id))

@app.route('/send-all-email-reminders', methods=['POST'])
def send_all_email_reminders():
    conn = get_db()
    members_list = conn.execute(
        "SELECT * FROM members WHERE expiry_date BETWEEN CURRENT_DATE - 1 AND CURRENT_DATE + 7 AND status='active' ORDER BY expiry_date ASC"
    ).fetchall()
    conn.close()

    sent = 0
    failed = 0
    last_error = ''
    for member in members_list:
        if not member['email'] or not member['expiry_date']:
            continue
        days_left = ((datetime.strptime(member['expiry_date'], '%Y-%m-%d').date() if isinstance(member['expiry_date'], str) else member['expiry_date']) - date.today()).days
        ok, err = send_expiry_reminder_email(
            member['email'], member['name'], member['plan'],
            member['expiry_date'], days_left
        )
        if ok:
            sent += 1
        else:
            failed += 1
            last_error = err

    if sent:
        flash(f'Email reminders sent to {sent} member(s)', 'success')
    if failed:
        flash(f'Email failed for {failed} member(s). Last error: {last_error}', 'danger')
    return redirect(url_for('expiring_members'))

@app.route('/admin/verify', methods=['POST'])
def verify_admin():
    pwd = request.form.get('password', '').strip()
    stored_hash = load_admin_password_hash()
    if stored_hash and check_password_hash(stored_hash, pwd):
        session['admin_verified'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Incorrect password'})

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/settings/change-password', methods=['POST'])
def change_password():
    current = request.form.get('current_password', '').strip()
    new = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm_password', '').strip()

    if not new or len(new) < 4:
        flash('New password must be at least 4 characters', 'danger')
        return redirect(url_for('settings'))

    if new != confirm:
        flash('New passwords do not match', 'danger')
        return redirect(url_for('settings'))

    stored_hash = load_admin_password_hash()
    if stored_hash and not check_password_hash(stored_hash, current):
        flash('Current password is incorrect', 'danger')
        return redirect(url_for('settings'))

    new_hash = generate_password_hash(new)
    if save_admin_password_hash(new_hash):
        session['admin_verified'] = False
        flash('Password updated successfully', 'success')
    else:
        flash('Failed to save password', 'danger')
    return redirect(url_for('settings'))

@app.route('/admin')
def admin():
    year = request.args.get('year', str(datetime.now().year))
    try:
        year_val = int(year)
    except:
        year_val = datetime.now().year
    conn = get_db()
    month_names = ['January','February','March','April','May','June','July','August','September','October','November','December']
    monthly_data = []
    grand_total = 0
    for m in range(1, 13):
        month_str = f"{year_val:04d}-{m:02d}"
        pay = conn.execute(
            '''SELECT COUNT(DISTINCT member_id) as cnt, COALESCE(SUM(amount), 0) as total
               FROM payments WHERE TO_CHAR(payment_date::DATE, 'YYYY-MM') = %s''',
            (month_str,)
        ).fetchone()
        cnt = pay['cnt'] or 0
        total_paid = pay['total'] or 0
        monthly_data.append({'month': m, 'month_name': month_names[m-1], 'count': cnt, 'total': total_paid})
        grand_total += total_paid
    conn.close()
    return render_template('admin.html', admin_verified=session.get('admin_verified', False),
                           monthly_data=monthly_data, year=year_val, grand_total=grand_total)

@app.route('/admin/sales-data')
def admin_sales_data():
    month = request.args.get('month', '')
    if not month:
        return jsonify({'error': 'Month required'}), 400
    try:
        year, mon = month.split('-')
        year, mon = int(year), int(mon)
    except:
        return jsonify({'error': 'Invalid month'}), 400

    conn = get_db()
    pay_rows = conn.execute(
        '''SELECT p.member_id as id, m.name, p.plan, p.amount as amount_paid, p.payment_date as paid_date
           FROM payments p JOIN members m ON p.member_id = m.id
           WHERE TO_CHAR(p.payment_date::DATE, 'YYYY-MM') = %s
           ORDER BY p.payment_date DESC''',
        (month,)
    ).fetchall()

    total_paid = sum(r['amount_paid'] or 0 for r in pay_rows)
    conn.close()

    members_data = []
    for r in pay_rows:
        members_data.append({
            'id': r['id'],
            'name': r['name'],
            'plan': r['plan'],
            'amount_paid': r['amount_paid'] or 0,
            'joining_date': r['paid_date'] or ''
        })

    return jsonify({'total_paid': total_paid, 'members': members_data, 'count': len(members_data)})

@app.route('/admin/download-sales-pdf')
def download_sales_pdf():
    year = request.args.get('year', str(datetime.now().year))
    try:
        year_val = int(year)
    except:
        flash('Invalid year', 'danger')
        return redirect(url_for('admin'))

    conn = get_db()
    monthly_totals = []
    grand_total = 0
    for m in range(1, 13):
        month_str = f"{year_val:04d}-{m:02d}"
        pay = conn.execute(
            '''SELECT COALESCE(SUM(amount), 0) as total FROM payments
               WHERE TO_CHAR(payment_date::DATE, 'YYYY-MM') = %s''',
            (month_str,)
        ).fetchone()
        total = pay['total'] or 0
        monthly_totals.append((m, total))
        grand_total += total
    conn.close()

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=20, textColor=colors.HexColor('#1a1a2e'), spaceAfter=6, alignment=TA_CENTER, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#666666'), spaceAfter=16, alignment=TA_CENTER)

    elements.append(Paragraph(f"Fitness Empire - Annual Sales Report ({year_val})", title_style))
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%d %b %Y, %I:%M %p')}", subtitle_style))
    elements.append(Spacer(1, 4*mm))

    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    header = ['#', 'Month', 'Total Sales']
    table_data = [header]
    for idx, (m, total) in enumerate(monthly_totals, 1):
        table_data.append([str(idx), month_names[m-1], f"Rs. {total:,.2f}"])
    table_data.append(['', 'Grand Total', f"Rs. {grand_total:,.2f}"])

    col_widths = [20*mm, 80*mm, 60*mm]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-2), 0.4, colors.HexColor('#dee2e6')),
        ('FONTNAME', (0,1), (-1,-2), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-2), 10),
        ('ALIGN', (0,1), (0,-1), 'CENTER'),
        ('ALIGN', (2,1), (2,-1), 'RIGHT'),
        # Grand total row
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0,-1), (-1,-1), colors.white),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('LINEABOVE', (0,-1), (-1,-1), 1.5, colors.HexColor('#1a1a2e')),
    ])
    tbl.setStyle(style)
    elements.append(tbl)
    doc.build(elements)
    buffer.seek(0)
    filename = f"annual_sales_{year_val}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

@app.route('/members/download-pdf')
def download_members_pdf():
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    status_filter = request.args.get('status', '')
    plan_filter = request.args.get('plan', '')

    query = 'SELECT * FROM members WHERE 1=1'
    params = []
    if status_filter:
        if status_filter == 'expiring':
            query += " AND status='active' AND expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7"
        else:
            query += ' AND status=%s'
            params.append(status_filter)
    if plan_filter:
        query += ' AND plan=%s'
        params.append(plan_filter)
    query += ' ORDER BY id DESC'

    conn = get_db()
    members_list = conn.execute(query, params).fetchall()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=15*mm
    )

    styles = getSampleStyleSheet()
    elements = []

    # Title
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Title'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        spaceAfter=12,
        alignment=TA_CENTER
    )

    elements.append(Paragraph("Fitness Empire - Member List", title_style))

    filter_desc = []
    if status_filter:
        filter_desc.append(f"Status: {status_filter.title()}")
    if plan_filter:
        filter_desc.append(f"Plan: {plan_filter}")
    filter_text = " | ".join(filter_desc) if filter_desc else "All Members"
    generated_on = datetime.now().strftime("%d %b %Y, %I:%M %p")
    elements.append(Paragraph(f"{filter_text} &nbsp;|&nbsp; Generated on {generated_on} &nbsp;|&nbsp; Total: {len(members_list)}", subtitle_style))
    elements.append(Spacer(1, 4*mm))

    def fmt_date(d):
        if d:
            try:
                if isinstance(d, str):
                    return datetime.strptime(d, '%Y-%m-%d').strftime('%d %b %Y')
                return d.strftime('%d %b %Y')
            except:
                return str(d) if d else '-'
        return '-'

    today = date.today()
    enriched = []
    for m in members_list:
        raw_status = m['status'] or 'active'
        expiry_str = m['expiry_date']
        days_left = 0
        if expiry_str:
            try:
                expiry = datetime.strptime(expiry_str, '%Y-%m-%d').date() if isinstance(expiry_str, str) else expiry_str
                days_left = (expiry - today).days
            except:
                pass
        if raw_status == 'active' and 0 < days_left <= 7:
            status_label = f"Expiring ({days_left}d)"
        else:
            status_label = raw_status.title()
        enriched.append({**m, 'days_left': days_left, 'status_label': status_label})

    header = ['#', 'Name', 'Phone', 'Joining Date', 'Expiry Date', 'Plan', 'Status']
    table_data = [header]
    for e in enriched:
        table_data.append([
            f"#{e['id']}", e['name'] or '-', e['phone'] or '-',
            fmt_date(e['joining_date']), fmt_date(e['expiry_date']),
            e['plan'] or '-', e['status_label']
        ])

    col_widths = [18*mm, 55*mm, 38*mm, 38*mm, 38*mm, 32*mm, 32*mm]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

    HEADER_BG   = colors.HexColor('#1a1a2e')
    HEADER_FG   = colors.white
    ROW_EVEN    = colors.HexColor('#f8f9ff')
    ROW_ODD     = colors.white
    ACTIVE_FG   = colors.HexColor('#155724')
    ACTIVE_BG   = colors.HexColor('#d4edda')
    EXPIRED_FG  = colors.HexColor('#721c24')
    EXPIRED_BG  = colors.HexColor('#f8d7da')
    EXPIRING_FG = colors.HexColor('#856404')
    EXPIRING_BG = colors.HexColor('#fff3cd')
    GRID_COLOR  = colors.HexColor('#dee2e6')

    style = TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR',     (0, 0), (-1, 0), HEADER_FG),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 9),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ('GRID',          (0, 0), (-1, -1), 0.4, GRID_COLOR),
        ('LINEBELOW',     (0, 0), (-1, 0), 1.5, HEADER_BG),
        ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 1), (-1, -1), 8),
        ('ALIGN',         (0, 1), (0, -1), 'CENTER'),
        ('ALIGN',         (3, 1), (4, -1), 'CENTER'),
        ('ALIGN',         (5, 1), (6, -1), 'CENTER'),
    ])

    for row_idx, e in enumerate(enriched, start=1):
        bg = ROW_EVEN if row_idx % 2 == 0 else ROW_ODD
        style.add('BACKGROUND', (0, row_idx), (-2, row_idx), bg)
        if e['status'] == 'active' and 0 < e['days_left'] <= 7:
            style.add('BACKGROUND', (6, row_idx), (6, row_idx), EXPIRING_BG)
            style.add('TEXTCOLOR',  (6, row_idx), (6, row_idx), EXPIRING_FG)
            style.add('FONTNAME',   (6, row_idx), (6, row_idx), 'Helvetica-Bold')
        elif e['status'] == 'expired':
            style.add('BACKGROUND', (6, row_idx), (6, row_idx), EXPIRED_BG)
            style.add('TEXTCOLOR',  (6, row_idx), (6, row_idx), EXPIRED_FG)
            style.add('FONTNAME',   (6, row_idx), (6, row_idx), 'Helvetica-Bold')
        else:
            style.add('BACKGROUND', (6, row_idx), (6, row_idx), ACTIVE_BG)
            style.add('TEXTCOLOR',  (6, row_idx), (6, row_idx), ACTIVE_FG)
            style.add('FONTNAME',   (6, row_idx), (6, row_idx), 'Helvetica-Bold')

    tbl.setStyle(style)
    elements.append(tbl)

    doc.build(elements)
    buffer.seek(0)

    filename = f"members_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
