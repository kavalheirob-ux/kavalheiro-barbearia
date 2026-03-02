from flask import Flask, request, jsonify, render_template, redirect, url_for, session, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import os

APP_NAME = "KAVALHEIRO BARBEARIA"

app = Flask(__name__)

# Banco compatível com Render (Postgres via DATABASE_URL ou fallback SQLite em /tmp)
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url or "sqlite:////tmp/kavalheiro.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="barber")

    approved = db.Column(db.Boolean, default=False)
    can_manage_clients = db.Column(db.Boolean, default=False)
    can_manage_services = db.Column(db.Boolean, default=False)
    can_view_finance = db.Column(db.Boolean, default=False)
    can_view_all_agendas = db.Column(db.Boolean, default=False)
    can_approve_bookings = db.Column(db.Boolean, default=False)

    commission_percent = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pwd: str):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd: str) -> bool:
        return check_password_hash(self.password_hash, pwd)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    price = db.Column(db.Float, nullable=True)
    duration_min = db.Column(db.Integer, default=30)
    commission_percent = db.Column(db.Float, default=None, nullable=True)

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lunch_start = db.Column(db.String(5), default="13:00")
    lunch_end = db.Column(db.String(5), default="14:00")
    open_time = db.Column(db.String(5), default="08:00")
    close_time = db.Column(db.String(5), default="21:00")
    slot_min = db.Column(db.Integer, default=30)

class ScheduleOverride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), unique=True, nullable=False)
    closed = db.Column(db.Boolean, default=False)
    lunch_start = db.Column(db.String(5), nullable=True)
    lunch_end = db.Column(db.String(5), nullable=True)

class Block(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barber_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    start_at = db.Column(db.DateTime, nullable=False, index=True)
    end_at = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barber_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    barber_name = db.Column(db.String(120), nullable=False)
    start_at = db.Column(db.DateTime, nullable=False, index=True)
    end_at = db.Column(db.DateTime, nullable=False)
    client_name = db.Column(db.String(120), nullable=False)
    client_phone = db.Column(db.String(50), nullable=True)
    service_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Agendado")
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.String(30), default="staff")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    actor_user_id = db.Column(db.Integer, nullable=True)
    actor_username = db.Column(db.String(60), nullable=True)
    action = db.Column(db.String(60), nullable=False)
    entity = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return User.query.get(uid)

def login_required(fn):
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u:
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper

def require_admin():
    u = current_user()
    if not u or u.role != "admin":
        abort(403)

def require_perm(attr: str):
    u = current_user()
    if not u:
        abort(401)
    if u.role == "admin":
        return
    if not u.approved:
        abort(403)
    if not getattr(u, attr, False):
        abort(403)

def can_approve(u: User) -> bool:
    return (u.role == "admin") or (u.approved and u.can_approve_bookings)

def log(action, entity, entity_id=None, details=None):
    u = current_user()
    entry = AuditLog(
        actor_user_id=u.id if u else None,
        actor_username=u.username if u else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details
    )
    db.session.add(entry)
    db.session.commit()

def iso(dt: datetime):
    return dt.isoformat(timespec="minutes")

def parse_dt(s: str):
    return datetime.fromisoformat(s)

def parse_time_hhmm(s: str):
    hh, mm = s.split(":")
    return int(hh), int(mm)

def day_key(dt: datetime):
    return dt.date().isoformat()

def get_cfg():
    cfg = Config.query.first()
    if not cfg:
        cfg = Config()
        db.session.add(cfg); db.session.commit()
    return cfg

def get_day_schedule(day_iso: str):
    cfg = get_cfg()
    ov = ScheduleOverride.query.filter_by(day=day_iso).first()
    open_time = cfg.open_time
    close_time = cfg.close_time
    slot_min = cfg.slot_min
    lunch_start = cfg.lunch_start
    lunch_end = cfg.lunch_end
    closed = False
    if ov:
        closed = bool(ov.closed)
        if ov.lunch_start: lunch_start = ov.lunch_start
        if ov.lunch_end: lunch_end = ov.lunch_end
    return open_time, close_time, slot_min, lunch_start, lunch_end, closed

def in_lunch(start_at: datetime, end_at: datetime, lunch_start: str, lunch_end: str):
    sh, sm = parse_time_hhmm(lunch_start)
    eh, em = parse_time_hhmm(lunch_end)
    ls = datetime(start_at.year, start_at.month, start_at.day, sh, sm)
    le = datetime(start_at.year, start_at.month, start_at.day, eh, em)
    return (start_at < le) and (end_at > ls)

def in_open_hours(start_at: datetime, end_at: datetime, open_time: str, close_time: str):
    oh, om = parse_time_hhmm(open_time)
    ch, cm = parse_time_hhmm(close_time)
    o = datetime(start_at.year, start_at.month, start_at.day, oh, om)
    c = datetime(start_at.year, start_at.month, start_at.day, ch, cm)
    return (start_at >= o) and (end_at <= c)

def has_block(barber_id: int, start_at: datetime, end_at: datetime):
    q = Block.query.filter(
        Block.start_at < end_at,
        Block.end_at > start_at,
        or_(Block.barber_id == None, Block.barber_id == barber_id)
    )
    return q.first()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", app_name=APP_NAME, next=request.args.get("next") or "/")
    data = request.form
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    u = User.query.filter(func.lower(User.username) == username).first()
    if not u or not u.check_password(password):
        return render_template("login.html", app_name=APP_NAME, next=data.get("next") or "/", error="Usuário ou senha inválidos.")
    session["uid"] = u.id
    return redirect(data.get("next") or "/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    u = current_user()
    return render_template("index.html", app_name=APP_NAME, me=serialize_me(u))

@app.route("/profile/password", methods=["GET", "POST"])
@login_required
def profile_password():
    u = current_user()
    if request.method == "GET":
        return render_template("profile_password.html", app_name=APP_NAME, me=serialize_me(u))
    old = request.form.get("old_password") or ""
    new = request.form.get("new_password") or ""
    if not u.check_password(old):
        return render_template("profile_password.html", app_name=APP_NAME, me=serialize_me(u), error="Senha atual incorreta.")
    if len(new) < 6:
        return render_template("profile_password.html", app_name=APP_NAME, me=serialize_me(u), error="Nova senha muito curta (mín. 6).")
    u.set_password(new)
    db.session.commit()
    log("update", "user", u.id, "changed own password")
    return render_template("profile_password.html", app_name=APP_NAME, me=serialize_me(u), ok="Senha atualizada!")

@app.route("/admin/users")
@login_required
def admin_users_page():
    require_admin()
    return render_template("admin_users.html", app_name=APP_NAME, me=serialize_me(current_user()))

@app.route("/admin/config")
@login_required
def admin_config_page():
    require_admin()
    return render_template("admin_config.html", app_name=APP_NAME, me=serialize_me(current_user()))

@app.route("/admin/overrides")
@login_required
def admin_overrides_page():
    require_admin()
    return render_template("admin_overrides.html", app_name=APP_NAME, me=serialize_me(current_user()))

@app.route("/admin/logs")
@login_required
def admin_logs_page():
    require_admin()
    return render_template("admin_logs.html", app_name=APP_NAME, me=serialize_me(current_user()))

@app.route("/admin/pending")
@login_required
def pending_page():
    u = current_user()
    if not can_approve(u):
        abort(403)
    return render_template("admin_pending.html", app_name=APP_NAME, me=serialize_me(u))

@app.route("/blocks")
@login_required
def blocks_page():
    u = current_user()
    if u.role != "admin" and not u.approved:
        abort(403)
    return render_template("blocks.html", app_name=APP_NAME, me=serialize_me(u))

@app.route("/book")
def book_page():
    return render_template("public_book.html", app_name=APP_NAME)

def serialize_me(u: User):
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "role": u.role,
        "approved": bool(u.approved),
        "perms": {
            "can_manage_clients": bool(u.can_manage_clients),
            "can_manage_services": bool(u.can_manage_services),
            "can_view_finance": bool(u.can_view_finance),
            "can_view_all_agendas": bool(u.can_view_all_agendas),
            "can_approve_bookings": bool(u.can_approve_bookings),
        },
        "commission_percent": float(u.commission_percent or 0.0)
    }

@app.route("/api/me")
@login_required
def api_me():
    return jsonify(serialize_me(current_user()))

@app.route("/api/schedule")
@login_required
def api_schedule():
    day = request.args.get("day") or date.today().isoformat()
    open_time, close_time, slot_min, lunch_start, lunch_end, closed = get_day_schedule(day)
    return jsonify({"day": day,"open_time": open_time,"close_time": close_time,"slot_min": slot_min,"lunch_start": lunch_start,"lunch_end": lunch_end,"closed": bool(closed)})

@app.route("/api/public/schedule")
def api_public_schedule():
    day = request.args.get("day") or date.today().isoformat()
    open_time, close_time, slot_min, lunch_start, lunch_end, closed = get_day_schedule(day)
    return jsonify({"day": day,"open_time": open_time,"close_time": close_time,"slot_min": slot_min,"lunch_start": lunch_start,"lunch_end": lunch_end,"closed": bool(closed)})

@app.route("/api/config", methods=["GET", "PUT"])
@login_required
def api_config():
    require_admin()
    cfg = get_cfg()
    if request.method == "GET":
        return jsonify({"open_time": cfg.open_time,"close_time": cfg.close_time,"slot_min": cfg.slot_min,"lunch_start": cfg.lunch_start,"lunch_end": cfg.lunch_end})
    data = request.get_json(force=True)
    cfg.open_time = (data.get("open_time") or cfg.open_time)
    cfg.close_time = (data.get("close_time") or cfg.close_time)
    cfg.slot_min = int(data.get("slot_min") or cfg.slot_min)
    cfg.lunch_start = (data.get("lunch_start") or cfg.lunch_start)
    cfg.lunch_end = (data.get("lunch_end") or cfg.lunch_end)
    db.session.commit()
    log("update", "config", cfg.id, "updated business hours/lunch/slot")
    return jsonify({"ok": True})

@app.route("/api/overrides", methods=["GET", "POST", "DELETE"])
@login_required
def api_overrides():
    require_admin()
    if request.method == "GET":
        items = ScheduleOverride.query.order_by(ScheduleOverride.day.asc()).all()
        return jsonify([{"id": o.id, "day": o.day, "closed": bool(o.closed),"lunch_start": o.lunch_start, "lunch_end": o.lunch_end} for o in items])
    if request.method == "POST":
        data = request.get_json(force=True)
        day = (data.get("day") or "").strip()
        if not day:
            return jsonify({"error": "Informe a data (YYYY-MM-DD)."}), 400
        o = ScheduleOverride.query.filter_by(day=day).first()
        if not o:
            o = ScheduleOverride(day=day)
            db.session.add(o)
        o.closed = bool(data.get("closed", False))
        o.lunch_start = (data.get("lunch_start") or None)
        o.lunch_end = (data.get("lunch_end") or None)
        db.session.commit()
        log("update", "override", o.id, f"override day={day}")
        return jsonify({"id": o.id}), 200
    oid = request.args.get("id", type=int)
    o = ScheduleOverride.query.get(oid)
    if not o:
        return jsonify({"error": "Override não encontrado."}), 404
    db.session.delete(o); db.session.commit()
    log("delete", "override", oid, "deleted override")
    return jsonify({"ok": True})

@app.route("/api/users", methods=["GET", "POST", "PUT"])
@login_required
def api_users():
    require_admin()
    if request.method == "GET":
        users = User.query.order_by(User.role.asc(), User.display_name.asc()).all()
        return jsonify([{"id": u.id,"username": u.username,"display_name": u.display_name,"role": u.role,"approved": bool(u.approved),
            "can_manage_clients": bool(u.can_manage_clients),"can_manage_services": bool(u.can_manage_services),"can_view_finance": bool(u.can_view_finance),
            "can_view_all_agendas": bool(u.can_view_all_agendas),"can_approve_bookings": bool(u.can_approve_bookings),
            "commission_percent": float(u.commission_percent or 0.0)} for u in users])
    if request.method == "POST":
        data = request.get_json(force=True)
        username = (data.get("username") or "").strip().lower()
        display_name = (data.get("display_name") or "").strip()
        password = (data.get("password") or "").strip()
        role = (data.get("role") or "barber").strip()
        if not username or not display_name or not password:
            return jsonify({"error": "username, display_name e password são obrigatórios."}), 400
        if role not in ("admin", "barber"):
            return jsonify({"error": "role inválido"}), 400
        if User.query.filter(func.lower(User.username) == username).first():
            return jsonify({"error": "username já existe"}), 409
        u = User(username=username, display_name=display_name, role=role)
        u.set_password(password)
        if role == "admin":
            u.approved = True; u.can_manage_clients = True; u.can_manage_services = True; u.can_view_finance = True; u.can_view_all_agendas = True; u.can_approve_bookings = True
        db.session.add(u); db.session.commit()
        log("create", "user", u.id, f"created user {username} role={role}")
        return jsonify({"id": u.id}), 201
    data = request.get_json(force=True)
    uid = int(data.get("id") or 0)
    u = User.query.get(uid)
    if not u:
        return jsonify({"error": "usuário não encontrado"}), 404
    if "display_name" in data and data["display_name"]:
        u.display_name = data["display_name"].strip()
    if "approved" in data:
        u.approved = bool(data["approved"])
    for k in ("can_manage_clients","can_manage_services","can_view_finance","can_view_all_agendas","can_approve_bookings"):
        if k in data:
            setattr(u, k, bool(data[k]))
    if "commission_percent" in data and data["commission_percent"] is not None:
        try: u.commission_percent = float(data["commission_percent"])
        except: pass
    if "password" in data and data["password"]:
        u.set_password(data["password"])
    db.session.commit()
    log("update", "user", u.id, "updated permissions/settings")
    return jsonify({"ok": True})

@app.route("/api/services", methods=["GET", "POST", "DELETE"])
@login_required
def services():
    u = current_user()
    if request.method == "GET":
        items = Service.query.order_by(Service.name.asc()).all()
        return jsonify([{"id": s.id, "name": s.name, "price": s.price, "duration_min": s.duration_min, "commission_percent": s.commission_percent} for s in items])
    if u.role != "admin":
        require_perm("can_manage_services")
    if request.method == "POST":
        data = request.get_json(force=True)
        name = (data.get("name") or "").strip()
        price = data.get("price", None)
        duration_min = data.get("duration_min", 30)
        comm = data.get("commission_percent", None)
        if not name:
            return jsonify({"error": "Serviço é obrigatório."}), 400
        existing = Service.query.filter(func.lower(Service.name) == name.lower()).first()
        if existing:
            if price not in (None, ""): existing.price = float(price)
            if duration_min: existing.duration_min = int(duration_min)
            if comm not in (None, ""): existing.commission_percent = float(comm)
            db.session.commit()
            log("update", "service", existing.id, f"updated service {name}")
            return jsonify({"id": existing.id}), 200
        s = Service(name=name, price=float(price) if price not in (None, "") else None, duration_min=int(duration_min or 30))
        if comm not in (None, ""): s.commission_percent = float(comm)
        db.session.add(s); db.session.commit()
        log("create", "service", s.id, f"created service {name}")
        return jsonify({"id": s.id}), 201
    sid = request.args.get("id", type=int)
    if not sid: return jsonify({"error": "Informe id"}), 400
    s = Service.query.get(sid)
    if not s: return jsonify({"error": "Serviço não encontrado"}), 404
    db.session.delete(s); db.session.commit()
    log("delete", "service", sid, "deleted service")
    return jsonify({"ok": True})

@app.route("/api/clients", methods=["GET", "POST", "DELETE"])
@login_required
def clients():
    u = current_user()
    if request.method == "GET":
        q = request.args.get("q", "").strip().lower()
        query = Client.query
        if q: query = query.filter(func.lower(Client.name).contains(q))
        items = query.order_by(Client.name.asc()).limit(200).all()
        return jsonify([{"id": c.id, "name": c.name, "phone": c.phone} for c in items])
    if u.role != "admin":
        require_perm("can_manage_clients")
    if request.method == "POST":
        data = request.get_json(force=True)
        name = (data.get("name") or "").strip()
        phone = (data.get("phone") or "").strip() or None
        if not name: return jsonify({"error": "Nome é obrigatório."}), 400
        existing = Client.query.filter(func.lower(Client.name) == name.lower()).first()
        if existing:
            if phone: existing.phone = phone; db.session.commit()
            log("update", "client", existing.id, "upsert client")
            return jsonify({"id": existing.id}), 200
        c = Client(name=name, phone=phone)
        db.session.add(c); db.session.commit()
        log("create", "client", c.id, "created client")
        return jsonify({"id": c.id}), 201
    cid = request.args.get("id", type=int)
    if not cid: return jsonify({"error": "Informe id"}), 400
    c = Client.query.get(cid)
    if not c: return jsonify({"error": "Cliente não encontrado"}), 404
    db.session.delete(c); db.session.commit()
    log("delete", "client", cid, "deleted client")
    return jsonify({"ok": True})

@app.route("/api/barbers", methods=["GET"])
@login_required
def barbers():
    u = current_user()
    q = User.query.filter(User.role == "barber")
    if u.role != "admin" and not u.can_view_all_agendas:
        q = q.filter(User.id == u.id)
    items = q.order_by(User.display_name.asc()).all()
    return jsonify([{"id": b.id, "name": b.display_name, "approved": bool(b.approved)} for b in items])

@app.route("/api/public/barbers")
def public_barbers():
    items = User.query.filter(User.role=="barber", User.approved==True).order_by(User.display_name.asc()).all()
    return jsonify([{"id": b.id, "name": b.display_name} for b in items])

@app.route("/api/public/services")
def public_services():
    items = Service.query.order_by(Service.name.asc()).all()
    return jsonify([{"name": s.name, "price": s.price, "duration_min": s.duration_min} for s in items])

@app.route("/api/blocks", methods=["GET", "POST", "DELETE"])
@login_required
def api_blocks():
    u = current_user()
    if u.role != "admin" and not u.approved:
        abort(403)
    if request.method == "GET":
        start = request.args.get("start")
        end = request.args.get("end")
        q = Block.query
        if start: q = q.filter(Block.start_at >= parse_dt(start))
        if end: q = q.filter(Block.start_at < parse_dt(end))
        if u.role != "admin":
            q = q.filter(or_(Block.barber_id == None, Block.barber_id == u.id))
        items = q.order_by(Block.start_at.asc()).limit(2000).all()
        return jsonify([{"id": b.id,"barber_id": b.barber_id,"start_at": iso(b.start_at),"end_at": iso(b.end_at),"reason": b.reason} for b in items])
    if request.method == "POST":
        data = request.get_json(force=True)
        start_at = parse_dt(data.get("start_at"))
        end_at = parse_dt(data.get("end_at"))
        reason = (data.get("reason") or "").strip() or None
        req_barber_id = data.get("barber_id", None)
        if end_at <= start_at:
            return jsonify({"error":"Fim deve ser depois do início."}), 400
        if u.role == "admin":
            barber_id = None if (req_barber_id in (None, "", "all", 0, "0")) else int(req_barber_id)
        else:
            barber_id = u.id
        b = Block(barber_id=barber_id, start_at=start_at, end_at=end_at, reason=reason)
        db.session.add(b); db.session.commit()
        log("block", "block", b.id, f"created block barber_id={barber_id} {iso(start_at)}-{iso(end_at)} reason={reason}")
        return jsonify({"id": b.id}), 201
    bid = request.args.get("id", type=int)
    b = Block.query.get(bid)
    if not b: return jsonify({"error":"Bloqueio não encontrado."}), 404
    if u.role != "admin" and b.barber_id not in (None, u.id):
        return jsonify({"error":"Sem permissão."}), 403
    db.session.delete(b); db.session.commit()
    log("delete", "block", bid, "deleted block")
    return jsonify({"ok": True})

def validate_schedule(barber_id: int, start_at: datetime, end_at: datetime):
    open_time, close_time, slot_min, lunch_start, lunch_end, closed = get_day_schedule(day_key(start_at))
    if closed: return "Dia bloqueado/fechado."
    if not in_open_hours(start_at, end_at, open_time, close_time): return "Fora do horário de atendimento."
    if lunch_start and lunch_end and in_lunch(start_at, end_at, lunch_start, lunch_end): return "Horário de almoço bloqueado."
    if slot_min and (start_at.minute % int(slot_min) != 0): return f"Horário deve ser de {slot_min} em {slot_min} minutos."
    if has_block(barber_id, start_at, end_at): return "Horário bloqueado (folga/intervalo)."
    return None

def check_overlap(barber_id: int, start_at: datetime, end_at: datetime, exclude_id=None):
    q = Appointment.query.filter(
        Appointment.barber_id == barber_id,
        Appointment.status != "Cancelado",
        Appointment.start_at < end_at,
        Appointment.end_at > start_at
    )
    if exclude_id:
        q = q.filter(Appointment.id != exclude_id)
    return q.first()

@app.route("/api/appointments", methods=["GET", "POST"])
@login_required
def appointments():
    u = current_user()
    if request.method == "GET":
        start = request.args.get("start"); end = request.args.get("end")
        status = request.args.get("status")
        barber_id = request.args.get("barber_id", type=int)
        q = Appointment.query
        if start: q = q.filter(Appointment.start_at >= parse_dt(start))
        if end: q = q.filter(Appointment.start_at < parse_dt(end))
        if status and status != "Todos": q = q.filter(Appointment.status == status)
        if u.role == "admin":
            if barber_id: q = q.filter(Appointment.barber_id == barber_id)
        else:
            if u.can_view_all_agendas and barber_id: q = q.filter(Appointment.barber_id == barber_id)
            else: q = q.filter(Appointment.barber_id == u.id)
        items = q.order_by(Appointment.start_at.asc()).limit(5000).all()
        return jsonify([{"id": a.id,"barber_id": a.barber_id,"barber_name": a.barber_name,"start_at": iso(a.start_at),"end_at": iso(a.end_at),
            "client_name": a.client_name,"client_phone": a.client_phone,"service_name": a.service_name,"price": a.price,"payment_method": a.payment_method,
            "status": a.status,"notes": a.notes,"created_by": a.created_by} for a in items])
    if u.role != "admin" and not u.approved:
        return jsonify({"error": "Seu usuário ainda não foi aprovado pelo administrador."}), 403
    data = request.get_json(force=True)
    start_at = parse_dt(data["start_at"])
    duration_min = int(data.get("duration_min") or 30)
    end_at = start_at + timedelta(minutes=duration_min)
    requested_barber_id = int(data.get("barber_id") or 0)
    barber_id = requested_barber_id or u.id if u.role=="admin" else u.id
    err = validate_schedule(barber_id, start_at, end_at)
    if err: return jsonify({"error": err}), 400
    client_name = (data.get("client_name") or "").strip()
    client_phone = (data.get("client_phone") or "").strip() or None
    service_name = (data.get("service_name") or "").strip()
    status = (data.get("status") or "Agendado").strip()
    payment_method = (data.get("payment_method") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None
    b = User.query.get(barber_id)
    barber_name = b.display_name if b else u.display_name
    price = data.get("price", None)
    if price in (None, ""):
        svc = Service.query.filter(func.lower(Service.name) == service_name.lower()).first() if service_name else None
        price = svc.price if svc else None
    else:
        price = float(price)
    if not client_name: return jsonify({"error": "Cliente é obrigatório."}), 400
    if not service_name: return jsonify({"error": "Serviço é obrigatório."}), 400
    if check_overlap(barber_id, start_at, end_at): return jsonify({"error": "Conflito de horário para esse barbeiro."}), 409
    a = Appointment(barber_id=barber_id, barber_name=barber_name, start_at=start_at, end_at=end_at,
        client_name=client_name, client_phone=client_phone, service_name=service_name, price=price,
        payment_method=payment_method, status=status, notes=notes, created_by="staff")
    db.session.add(a)
    if u.role == "admin" or u.can_manage_clients:
        existing = Client.query.filter(func.lower(Client.name) == client_name.lower()).first()
        if not existing: db.session.add(Client(name=client_name, phone=client_phone))
    db.session.commit()
    log("create", "appointment", a.id, f"created staff appt {client_name} {service_name} {iso(start_at)} barber={barber_id}")
    return jsonify({"id": a.id}), 201

@app.route("/api/appointments/<int:aid>", methods=["PUT", "DELETE"])
@login_required
def appointment_one(aid: int):
    u = current_user()
    a = Appointment.query.get(aid)
    if not a: return jsonify({"error": "Agendamento não encontrado."}), 404
    if u.role != "admin":
        if not u.approved: return jsonify({"error": "Seu usuário ainda não foi aprovado."}), 403
        if a.barber_id != u.id: return jsonify({"error": "Sem permissão para editar agendamentos de outro barbeiro."}), 403
    if request.method == "DELETE":
        db.session.delete(a); db.session.commit()
        log("delete", "appointment", aid, "deleted appointment")
        return jsonify({"ok": True})
    data = request.get_json(force=True)
    if u.role == "admin" and "barber_id" in data and data["barber_id"]:
        a.barber_id = int(data["barber_id"])
        b = User.query.get(a.barber_id)
        if b: a.barber_name = b.display_name
    if "start_at" in data and data["start_at"]:
        start_at = parse_dt(data["start_at"])
        duration_min = int(data.get("duration_min") or int((a.end_at - a.start_at).total_seconds()//60))
        end_at = start_at + timedelta(minutes=duration_min)
    else:
        start_at, end_at = a.start_at, a.end_at
    err = validate_schedule(a.barber_id, start_at, end_at)
    if err: return jsonify({"error": err}), 400
    client_name = (data.get("client_name") or a.client_name).strip()
    client_phone = (data.get("client_phone") if "client_phone" in data else a.client_phone)
    client_phone = (client_phone or "").strip() or None
    service_name = (data.get("service_name") or a.service_name).strip()
    status = (data.get("status") or a.status).strip()
    payment_method = (data.get("payment_method") if "payment_method" in data else a.payment_method)
    payment_method = (payment_method or "").strip() or None
    notes = (data.get("notes") if "notes" in data else a.notes)
    notes = (notes or "").strip() or None
    price = data.get("price") if "price" in data else a.price
    if price in (None, ""):
        svc = Service.query.filter(func.lower(Service.name) == service_name.lower()).first()
        price = svc.price if svc else None
    else:
        price = float(price)
    if check_overlap(a.barber_id, start_at, end_at, exclude_id=a.id): return jsonify({"error": "Conflito de horário para esse barbeiro."}), 409
    a.start_at = start_at; a.end_at = end_at; a.client_name = client_name; a.client_phone = client_phone
    a.service_name = service_name; a.price = price; a.payment_method = payment_method; a.status = status; a.notes = notes
    db.session.commit()
    log("update", "appointment", a.id, f"updated appt status={status} {iso(start_at)}")
    return jsonify({"ok": True})

@app.route("/api/public/slots")
def public_slots():
    day = request.args.get("day") or date.today().isoformat()
    barber_id = request.args.get("barber_id", type=int)
    service_name = (request.args.get("service_name") or "").strip()
    if not barber_id: return jsonify({"error": "Informe barber_id"}), 400
    open_time, close_time, slot_min, lunch_start, lunch_end, closed = get_day_schedule(day)
    if closed: return jsonify({"day": day, "slots": []})
    dur = 30
    if service_name:
        svc = Service.query.filter(func.lower(Service.name) == service_name.lower()).first()
        if svc and svc.duration_min: dur = int(svc.duration_min)
    start_dt = datetime.fromisoformat(f"{day}T{open_time}")
    end_dt = datetime.fromisoformat(f"{day}T{close_time}")
    slots = []; cur = start_dt
    while cur + timedelta(minutes=dur) <= end_dt:
        cand_end = cur + timedelta(minutes=dur)
        if lunch_start and lunch_end and in_lunch(cur, cand_end, lunch_start, lunch_end):
            cur += timedelta(minutes=slot_min); continue
        if has_block(barber_id, cur, cand_end):
            cur += timedelta(minutes=slot_min); continue
        if not check_overlap(barber_id, cur, cand_end):
            slots.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=slot_min)
    return jsonify({"day": day, "slots": slots, "slot_min": slot_min, "duration_min": dur})

@app.route("/api/public/book", methods=["POST"])
def public_book():
    data = request.get_json(force=True)
    day = (data.get("day") or "").strip()
    time_hhmm = (data.get("time") or "").strip()
    barber_id = int(data.get("barber_id") or 0)
    service_name = (data.get("service_name") or "").strip()
    client_name = (data.get("client_name") or "").strip()
    client_phone = (data.get("client_phone") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None
    if not day or not time_hhmm or not barber_id or not service_name or not client_name:
        return jsonify({"error":"Preencha data, horário, barbeiro, serviço e nome."}), 400
    svc = Service.query.filter(func.lower(Service.name) == service_name.lower()).first()
    dur = int(svc.duration_min) if svc and svc.duration_min else 30
    price = svc.price if svc else None
    start_at = datetime.fromisoformat(f"{day}T{time_hhmm}")
    end_at = start_at + timedelta(minutes=dur)
    err = validate_schedule(barber_id, start_at, end_at)
    if err: return jsonify({"error": err}), 400
    b = User.query.get(barber_id)
    if not b or b.role != "barber" or not b.approved:
        return jsonify({"error":"Barbeiro inválido."}), 400
    if check_overlap(barber_id, start_at, end_at):
        return jsonify({"error":"Esse horário acabou de ser ocupado. Escolha outro."}), 409
    a = Appointment(barber_id=barber_id, barber_name=b.display_name, start_at=start_at, end_at=end_at,
        client_name=client_name, client_phone=client_phone, service_name=service_name, price=price,
        payment_method=None, status="Pendente", notes=notes, created_by="public")
    db.session.add(a); db.session.commit()
    entry = AuditLog(actor_user_id=None, actor_username=None, action="create", entity="appointment", entity_id=a.id,
                     details=f"public booking pending {client_name} {service_name} {iso(start_at)} barber={barber_id}")
    db.session.add(entry); db.session.commit()
    return jsonify({"ok": True, "id": a.id})

@app.route("/api/pending", methods=["GET"])
@login_required
def pending_list():
    u = current_user()
    if not can_approve(u): abort(403)
    q = Appointment.query.filter(Appointment.status=="Pendente")
    if u.role != "admin":
        q = q.filter(Appointment.barber_id == u.id)
    items = q.order_by(Appointment.start_at.asc()).limit(500).all()
    return jsonify([{"id": a.id,"start_at": iso(a.start_at),"end_at": iso(a.end_at),"barber_id": a.barber_id,"barber_name": a.barber_name,
        "client_name": a.client_name,"client_phone": a.client_phone,"service_name": a.service_name,"price": a.price,"notes": a.notes} for a in items])

@app.route("/api/pending/<int:aid>/approve", methods=["POST"])
@login_required
def pending_approve(aid: int):
    u = current_user()
    if not can_approve(u): abort(403)
    a = Appointment.query.get(aid)
    if not a or a.status != "Pendente": return jsonify({"error":"Agendamento não encontrado."}), 404
    if u.role != "admin" and a.barber_id != u.id: return jsonify({"error":"Sem permissão."}), 403
    if check_overlap(a.barber_id, a.start_at, a.end_at, exclude_id=a.id):
        a.status = "Cancelado"; db.session.commit()
        log("approve", "appointment", a.id, "auto-cancelled due to overlap on approve")
        return jsonify({"error":"Conflito ao aprovar (já ocupado). Foi cancelado."}), 409
    err = validate_schedule(a.barber_id, a.start_at, a.end_at)
    if err:
        a.status = "Cancelado"; db.session.commit()
        log("approve", "appointment", a.id, f"auto-cancelled due to schedule/block: {err}")
        return jsonify({"error":f"Não foi possível aprovar: {err}. Foi cancelado."}), 409
    a.status = "Agendado"; db.session.commit()
    log("approve", "appointment", a.id, "approved public booking -> Agendado")
    return jsonify({"ok": True})

@app.route("/api/pending/<int:aid>/reject", methods=["POST"])
@login_required
def pending_reject(aid: int):
    u = current_user()
    if not can_approve(u): abort(403)
    a = Appointment.query.get(aid)
    if not a or a.status != "Pendente": return jsonify({"error":"Agendamento não encontrado."}), 404
    if u.role != "admin" and a.barber_id != u.id: return jsonify({"error":"Sem permissão."}), 403
    a.status = "Cancelado"; db.session.commit()
    log("approve", "appointment", a.id, "rejected public booking -> Cancelado")
    return jsonify({"ok": True})

@app.route("/api/stats")
@login_required
def stats():
    u = current_user()
    if u.role != "admin":
        require_perm("can_view_finance")
    start = request.args.get("start"); end = request.args.get("end")
    barber_id = request.args.get("barber_id", type=int)
    q = Appointment.query
    if start: q = q.filter(Appointment.start_at >= parse_dt(start))
    if end: q = q.filter(Appointment.start_at < parse_dt(end))
    if u.role == "admin":
        if barber_id: q = q.filter(Appointment.barber_id == barber_id)
    else:
        if u.can_view_all_agendas and barber_id: q = q.filter(Appointment.barber_id == barber_id)
        else: q = q.filter(Appointment.barber_id == u.id)
    total_done = q.filter(Appointment.status == "Concluído").with_entities(func.coalesce(func.sum(Appointment.price), 0.0)).scalar() or 0.0
    count_done = q.filter(Appointment.status == "Concluído").count()
    ticket = (total_done / count_done) if count_done else 0.0
    by_status = q.with_entities(Appointment.status, func.count(Appointment.id)).group_by(Appointment.status).all()
    by_pay = q.filter(Appointment.status=="Concluído").with_entities(Appointment.payment_method, func.count(Appointment.id), func.coalesce(func.sum(Appointment.price),0.0)).group_by(Appointment.payment_method).all()
    comm_rows = []
    if u.role == "admin":
        done = q.filter(Appointment.status=="Concluído").all()
        svc_map = {s.name.lower(): s.commission_percent for s in Service.query.all()}
        user_map = {b.id: b for b in User.query.all()}
        by_barber = {}
        for a in done:
            b = user_map.get(a.barber_id)
            base = float(a.price or 0.0)
            pct = svc_map.get(a.service_name.lower()) if a.service_name else None
            if pct is None:
                pct = float(b.commission_percent or 0.0) if b else 0.0
            comm = base * (float(pct or 0.0) / 100.0)
            if a.barber_id not in by_barber:
                by_barber[a.barber_id] = {"barber_id": a.barber_id, "barber_name": a.barber_name, "total": 0.0, "commission": 0.0}
            by_barber[a.barber_id]["total"] += base
            by_barber[a.barber_id]["commission"] += comm
        comm_rows = list(by_barber.values())
    return jsonify({"total_done": float(total_done),"count_done": int(count_done),"ticket": float(ticket),
        "by_status": [{"status": s, "count": int(c)} for s,c in by_status],
        "by_payment": [{"payment_method": (p or "—"), "count": int(c), "total": float(t)} for p,c,t in by_pay],
        "commissions": comm_rows})

@app.route("/api/logs")
@login_required
def api_logs():
    require_admin()
    limit = request.args.get("limit", type=int) or 200
    items = AuditLog.query.order_by(AuditLog.at.desc()).limit(min(limit, 1000)).all()
    return jsonify([{"at": a.at.isoformat(timespec="seconds"),"actor": a.actor_username or "public","action": a.action,"entity": a.entity,"entity_id": a.entity_id,"details": a.details} for a in items])

def seed_defaults():
    if Config.query.count() == 0:
        db.session.add(Config()); db.session.commit()
    if User.query.count() == 0:
        admin = User(username="admin", display_name="Administrador", role="admin",
                     approved=True, can_manage_clients=True, can_manage_services=True,
                     can_view_finance=True, can_view_all_agendas=True, can_approve_bookings=True,
                     commission_percent=0.0)
        admin.set_password("admin123")
        b2 = User(username="barbeiro2", display_name="Barbeiro 2", role="barber",
                  approved=False, can_manage_clients=False, can_manage_services=False,
                  can_view_finance=False, can_view_all_agendas=False, can_approve_bookings=True,
                  commission_percent=40.0)
        b2.set_password("barber123")
        db.session.add(admin); db.session.add(b2); db.session.commit()
    if Service.query.count() == 0:
        defaults = [("Corte",35.0,30,40.0),("Barba",30.0,30,40.0),("Corte + Barba",60.0,60,45.0),("Sobrancelha",15.0,30,50.0),("Pezinho",10.0,30,50.0)]
        for name, price, dur, comm in defaults:
            db.session.add(Service(name=name, price=price, duration_min=dur, commission_percent=comm))
        db.session.commit()

def init_db():
    """Cria tabelas e insere dados iniciais (admin/serviços) ao subir o servidor."""
    with app.app_context():
        db.create_all()
        try:
            seed_defaults()
        except Exception as e:
            # Não derruba o app se o seed falhar (ex.: duplicado)
            print("seed_defaults() falhou:", e)

# Executa na inicialização (funciona com gunicorn no Render)
init_db()


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_defaults()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
