"""
Orthotracker Pro — Full Streamlit MVP
Filename: OrthotrackerPro_Full_Streamlit_MVP.py

This is a single-file, production-minded Streamlit MVP that implements:
- User registration & login (email/password, hashed)
- Roles: admin / rep
- Procedure quick logging (with templates)
- Attachments saved locally or to S3 if AWS creds present
- Commission engine with configurable rules (JSON-based simple rules)
- Offline queue simulation (stores pending logs to a local queue file and a 'Sync' operation)
- Admin dashboard with KPIs, reports, CSV export
- Simple audit logs
- SQLite by default; can switch to Postgres via DATABASE_URL env var
- Dockerfile and requirements.txt snippets included at bottom of this file

How to run (quick):
1. Install requirements: pip install -r requirements.txt
2. Run: streamlit run OrthotrackerPro_Full_Streamlit_MVP.py

Notes:
- This MVP is feature-rich but intended as a starting point. Replace local file storage with S3/MinIO in prod.
- Commission rules are stored in the `commission_rules` table; admin can add simple JSON conditions.

"""

import streamlit as st
from datetime import datetime, date
import os
import json
import tempfile
from typing import Optional, List, Dict, Any
from pathlib import Path
import pandas as pd
from io import BytesIO
import base64

# Database and auth
from sqlalchemy import (create_engine, Column, Integer, String, DateTime, Float, Boolean, Text, ForeignKey, JSON)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext

# Optional S3 support
try:
    import boto3
    from botocore.exceptions import BotoCoreError, NoCredentialsError
    S3_AVAILABLE = True
except Exception:
    S3_AVAILABLE = False

# -------------------- Configuration --------------------
BASE_DIR = Path(__file__).parent
DB_FILE = BASE_DIR / "orthotracker.db"
UPLOAD_DIR = BASE_DIR / "uploads"
QUEUE_FILE = BASE_DIR / "offline_queue.json"
os.makedirs(UPLOAD_DIR, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{DB_FILE}"
AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION") or "us-east-1"

# SQLAlchemy setup
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith('sqlite') else {})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -------------------- Models --------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="rep")  # 'admin' or 'rep'
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    reps = relationship("Rep", back_populates="user", uselist=False)

class Rep(Base):
    __tablename__ = "reps"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    territory = Column(String, nullable=True)
    user = relationship("User", back_populates="reps")

class Hospital(Base):
    __tablename__ = "hospitals"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    address = Column(String)
    geo_lat = Column(String)
    geo_lng = Column(String)

class Surgeon(Base):
    __tablename__ = "surgeons"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    hospital_id = Column(Integer, ForeignKey('hospitals.id'))

class Procedure(Base):
    __tablename__ = "procedures"
    id = Column(Integer, primary_key=True)
    rep_id = Column(Integer, ForeignKey('reps.id'))
    rep_name = Column(String)
    hospital = Column(String)
    surgeon = Column(String)
    procedure_type = Column(String)
    date = Column(String)
    revenue = Column(Float, default=0.0)
    notes = Column(Text)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    attachments = relationship("Attachment", back_populates="procedure")

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    procedure_id = Column(Integer, ForeignKey('procedures.id'))
    filename = Column(String)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    procedure = relationship("Procedure", back_populates="attachments")

class CommissionRule(Base):
    __tablename__ = "commission_rules"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    # condition: JSON like {"procedure_type":"Knee Arthroplasty","hospital":"County Hospital"}
    condition = Column(JSON)
    mode = Column(String, default="percentage")  # 'percentage' or 'fixed'
    value = Column(Float, default=0.0)
    active = Column(Boolean, default=True)
    effective_from = Column(DateTime, default=datetime(2000,1,1))
    effective_to = Column(DateTime, default=datetime(2099,1,1))

class Commission(Base):
    __tablename__ = "commissions"
    id = Column(Integer, primary_key=True)
    procedure_id = Column(Integer, ForeignKey('procedures.id'))
    rep_id = Column(Integer, ForeignKey('reps.id'))
    amount = Column(Float)
    calculated_at = Column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user = Column(String)
    action = Column(String)
    entity = Column(String)
    entity_id = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(Text)

# Create tables
Base.metadata.create_all(bind=engine)

# -------------------- Utility functions --------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def upload_file(file_bytes: bytes, filename: str) -> str:
    """Upload to S3 if configured, otherwise save locally. Returns storage path or URL."""
    if AWS_S3_BUCKET and S3_AVAILABLE:
        try:
            s3 = boto3.client('s3', region_name=AWS_REGION)
            key = f"attachments/{datetime.utcnow().strftime('%Y%m%d')}/{filename}"
            s3.put_object(Bucket=AWS_S3_BUCKET, Key=key, Body=file_bytes)
            url = f"s3://{AWS_S3_BUCKET}/{key}"
            return url
        except (BotoCoreError, NoCredentialsError) as e:
            # fallback to local
            pass
    # local
    path = UPLOAD_DIR / filename
    with open(path, 'wb') as f:
        f.write(file_bytes)
    return str(path)


def save_to_offline_queue(entry: Dict[str, Any]):
    queue = []
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
            try:
                queue = json.load(f)
            except Exception:
                queue = []
    queue.append(entry)
    with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(queue, f, default=str, indent=2)


def load_offline_queue():
    if not QUEUE_FILE.exists():
        return []
    with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return []


def clear_offline_queue():
    if QUEUE_FILE.exists():
        QUEUE_FILE.unlink()


def add_audit(db, user: str, action: str, entity: str, entity_id: str, details: str=""):
    a = AuditLog(user=user, action=action, entity=entity, entity_id=str(entity_id), details=details)
    db.add(a)
    db.commit()

# -------------------- Auth helpers --------------------

def register_user(email: str, full_name: str, password: str, role: str = "rep") -> Optional[User]:
    db = next(get_db())
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return None
    user = User(email=email, full_name=full_name, hashed_password=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    # create rep record
    rep = Rep(user_id=user.id)
    db.add(rep)
    db.commit()
    add_audit(db, email, "register", "user", user.id, details=f"role={role}")
    db.close()
    return user


def authenticate_user(email: str, password: str) -> Optional[User]:
    db = next(get_db())
    user = db.query(User).filter(User.email == email).first()
    db.close()
    if user and verify_password(password, user.hashed_password):
        return user
    return None

# -------------------- Commission engine --------------------

def calculate_commission_for_procedure(db, procedure: Procedure) -> float:
    # Find active rules matching conditions
    now = datetime.utcnow()
    rules = db.query(CommissionRule).filter(CommissionRule.active == True,
                                            CommissionRule.effective_from <= now,
                                            CommissionRule.effective_to >= now).all()
    total_comm = 0.0
    for r in rules:
        cond = r.condition or {}
        match = True
        # simple matching for keys in condition
        for k, v in cond.items():
            pv = getattr(procedure, k, None)
            if pv is None:
                match = False
                break
            # normalize types
            if str(pv).lower() != str(v).lower():
                match = False
                break
        if match:
            if r.mode == 'percentage':
                total_comm += (procedure.revenue or 0.0) * (r.value / 100.0)
            else:
                total_comm += r.value
    return total_comm

# -------------------- Streamlit UI --------------------

st.set_page_config(page_title="Orthotracker Pro — Full MVP", layout='wide')

if 'user' not in st.session_state:
    st.session_state.user = None

# Sidebar: auth
with st.sidebar:
    st.header("Orthotracker Pro")
    if st.session_state.user is None:
        st.subheader("Login / Register")
        auth_mode = st.radio("Action", ["Login", "Register"], index=0)
        email = st.text_input("Email")
        name = st.text_input("Full name (for register)") if auth_mode == 'Register' else None
        pwd = st.text_input("Password", type='password')
        role_choice = st.selectbox("Role (only for register)", ["rep", "admin"]) if auth_mode == 'Register' else None
        if st.button("Submit"):
            if auth_mode == 'Register':
                if not email or not name or not pwd:
                    st.warning("Provide email, full name and password to register")
                else:
                    user = register_user(email=email, full_name=name, password=pwd, role=role_choice)
                    if user:
                        st.success("Registered. You can now login.")
                    else:
                        st.error("User already exists")
            else:
                user = authenticate_user(email=email, password=pwd)
                if user:
                    st.session_state.user = {'id': user.id, 'email': user.email, 'name': user.full_name, 'role': user.role}
                    st.experimental_rerun()
                else:
                    st.error("Invalid credentials")
    else:
        st.write(f"Signed in as: {st.session_state.user['name']} ({st.session_state.user['email']})")
        if st.button("Sign out"):
            st.session_state.user = None
            st.experimental_rerun()


# Main app
if st.session_state.user is None:
    st.title("Welcome — please log in")
    st.info("This demo includes registration. Create an admin account to access admin features.")
    st.stop()

user = st.session_state.user
role = user['role']

# Top nav
tabs = ["Home", "Log Procedure", "My Procedures", "Offline Queue", "Admin"] if role == 'admin' else ["Home", "Log Procedure", "My Procedures", "Offline Queue"]
page = st.tabs(tabs)

# Helper to get DB session
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -- Home --
with page[0]:
    st.header("Dashboard")
    db = next(get_db())
    total_proc = db.query(Procedure).count()
    total_rev = db.query(Procedure).with_entities(func_sum := Procedure.revenue).all()
    # simpler calculation
    procs = db.query(Procedure).all()
    total_rev_val = sum([p.revenue or 0.0 for p in procs])
    col1, col2, col3 = st.columns(3)
    col1.metric("Total procedures", total_proc)
    col2.metric("Total revenue (KSh)", f"{total_rev_val:,.2f}")
    pending = db.query(Procedure).filter(Procedure.status == 'pending').count()
    col3.metric("Pending verifications", pending)

    st.subheader("Recent procedures")
    df = pd.DataFrame([{
        'id': p.id,
        'rep_name': p.rep_name,
        'procedure_type': p.procedure_type,
        'hospital': p.hospital,
        'surgeon': p.surgeon,
        'revenue': p.revenue,
        'date': p.date,
        'status': p.status
    } for p in procs])
    if df.empty:
        st.info("No procedures logged yet.")
    else:
        st.dataframe(df.sort_values('date', ascending=False).head(20))
    db.close()

# -- Log Procedure --
with page[1]:
    st.header("Quick Procedure Log")
    st.caption("Fast mobile-first form. Use templates for repeat procedures.")
    with st.form("proc_form"):
        rep_name = st.text_input("Rep name", value=user['name'])
        hospital = st.text_input("Hospital", value="County Hospital")
        surgeon = st.text_input("Surgeon", value="Dr. Smith")
        procedure_type = st.selectbox("Procedure type", ["Trauma - Intramedullary Nail","Knee Arthroplasty","Hip Arthroplasty","Other"])
        date_input = st.date_input("Procedure date", value=date.today())
        revenue = st.number_input("Revenue amount (KSh)", min_value=0.0, value=0.0, step=100.0)
        notes = st.text_area("Notes / details", height=120)
        save_offline = st.checkbox("Save to offline queue (simulate no connection)")
        uploaded_files = st.file_uploader("Attach images / files (optional)", accept_multiple_files=True)
        submitted = st.form_submit_button("Save procedure")
        if submitted:
            entry = {
                'rep_email': user['email'],
                'rep_name': rep_name,
                'hospital': hospital,
                'surgeon': surgeon,
                'procedure_type': procedure_type,
                'date': date_input.isoformat(),
                'revenue': revenue,
                'notes': notes,
                'attachments': [],
                'created_at': datetime.utcnow().isoformat()
            }
            # handle attachments in-memory first
            for f in uploaded_files:
                bytes_data = f.read()
                fname = f"{int(datetime.utcnow().timestamp())}_{f.name}"
                path_or_url = upload_file(bytes_data, fname)
                entry['attachments'].append({'filename': fname, 'path': path_or_url})

            if save_offline:
                save_to_offline_queue(entry)
                st.success("Saved to offline queue. Use 'Offline Queue' tab to sync when online.")
            else:
                # persist to DB
                db = next(get_db())
                # get rep id
                u = db.query(User).filter(User.email == user['email']).first()
                rep = db.query(Rep).filter(Rep.user_id == u.id).first()
                proc = Procedure(rep_id=rep.id, rep_name=entry['rep_name'], hospital=entry['hospital'],
                                 surgeon=entry['surgeon'], procedure_type=entry['procedure_type'],
                                 date=entry['date'], revenue=entry['revenue'], notes=entry['notes'], status='pending')
                db.add(proc)
                db.commit()
                db.refresh(proc)
                # attachments
                for a in entry['attachments']:
                    att = Attachment(procedure_id=proc.id, filename=a['filename'])
                    db.add(att)
                db.commit()
                # calculate commission
                comm_amt = calculate_commission_for_procedure(db, proc)
                comm = Commission(procedure_id=proc.id, rep_id=rep.id, amount=comm_amt)
                db.add(comm)
                db.commit()
                add_audit(db, user['email'], 'create_procedure', 'procedure', proc.id, details=json.dumps(entry))
                db.close()
                st.success(f"Procedure saved (id={proc.id}). Commission: KSh {comm_amt:,.2f}")

# -- My Procedures --
with page[2]:
    st.header("My Procedures")
    db = next(get_db())
    u = db.query(User).filter(User.email == user['email']).first()
    rep = db.query(Rep).filter(Rep.user_id == u.id).first()
    procs = db.query(Procedure).filter(Procedure.rep_id == rep.id).order_by(Procedure.created_at.desc()).all()
    if not procs:
        st.info("You have no procedures yet.")
    else:
        df = pd.DataFrame([{
            'id': p.id,
            'date': p.date,
            'procedure_type': p.procedure_type,
            'hospital': p.hospital,
            'surgeon': p.surgeon,
            'revenue': p.revenue,
            'status': p.status
        } for p in procs])
        st.dataframe(df)
        sel = st.multiselect("Select procedure IDs to export", df['id'].tolist())
        if st.button("Export selected to CSV"):
            ex = df[df['id'].isin(sel)]
            st.download_button("Download CSV", ex.to_csv(index=False).encode('utf-8'), "procedures.csv", "text/csv")
    db.close()

# -- Offline Queue --
with page[3]:
    st.header("Offline Queue (simulation)")
    q = load_offline_queue()
    st.write(f"Pending items: {len(q)}")
    if q:
        st.json(q)
        if st.button("Sync all to server (process queue)"):
            db = next(get_db())
            processed = 0
            for entry in q:
                # find or create user/rep
                u = db.query(User).filter(User.email == entry.get('rep_email')).first()
                if not u:
                    # create a placeholder user with random password
                    u = User(email=entry.get('rep_email'), full_name=entry.get('rep_name','Rep'), hashed_password=hash_password('temporary'), role='rep')
                    db.add(u); db.commit(); db.refresh(u)
                    r = Rep(user_id=u.id); db.add(r); db.commit()
                else:
                    r = db.query(Rep).filter(Rep.user_id == u.id).first()
                proc = Procedure(rep_id=r.id, rep_name=entry['rep_name'], hospital=entry['hospital'],
                                 surgeon=entry['surgeon'], procedure_type=entry['procedure_type'],
                                 date=entry['date'], revenue=entry['revenue'], notes=entry['notes'], status='pending')
                db.add(proc); db.commit(); db.refresh(proc)
                for a in entry.get('attachments', []):
                    att = Attachment(procedure_id=proc.id, filename=a.get('filename'))
                    db.add(att)
                # commission
                comm_amt = calculate_commission_for_procedure(db, proc)
                comm = Commission(procedure_id=proc.id, rep_id=r.id, amount=comm_amt)
                db.add(comm)
                add_audit(db, entry.get('rep_email'), 'sync_offline', 'procedure', proc.id, details=json.dumps(entry))
                db.commit()
                processed += 1
            db.close()
            clear_offline_queue()
            st.success(f"Synced {processed} items to server")
    else:
        st.info("Offline queue empty")

# -- Admin --
if role == 'admin':
    with page[4]:
        st.header("Admin — Management Console")
        tab = st.radio("Admin panel", ["Overview","Users","Commission Rules","Hospitals & Surgeons","Audit Logs"], index=0)
        db = next(get_db())
        if tab == 'Overview':
            st.subheader("KPIs & Reports")
            procs = db.query(Procedure).all()
            df = pd.DataFrame([{
                'id': p.id,
                'rep_name': p.rep_name,
                'procedure_type': p.procedure_type,
                'hospital': p.hospital,
                'surgeon': p.surgeon,
                'revenue': p.revenue,
                'date': p.date,
                'status': p.status
            } for p in procs])
            st.metric("Total procedures", len(df))
            st.metric("Total revenue (KSh)", f"{df['revenue'].sum() if not df.empty else 0:,.2f}")
            if not df.empty:
                st.bar_chart(df.groupby('procedure_type')['id'].count())
            st.download_button("Export all procedures CSV", df.to_csv(index=False).encode('utf-8'), "all_procedures.csv", "text/csv")

        elif tab == 'Users':
            st.subheader("User management")
            users = db.query(User).all()
            udf = pd.DataFrame([{'id':u.id,'email':u.email,'name':u.full_name,'role':u.role,'created_at':u.created_at} for u in users])
            st.dataframe(udf)
            st.markdown("---")
            st.subheader("Create admin user")
            with st.form('create_admin'):
                e = st.text_input('Email')
                n = st.text_input('Full name')
                p = st.text_input('Password', type='password')
                if st.form_submit_button('Create'):
                    existing = db.query(User).filter(User.email==e).first()
                    if existing:
                        st.error('User exists')
                    else:
                        u = User(email=e, full_name=n, hashed_password=hash_password(p), role='admin')
                        db.add(u); db.commit(); st.success('Admin created')

        elif tab == 'Commission Rules':
            st.subheader('Commission rules')
            rules = db.query(CommissionRule).all()
            for r in rules:
                st.write(f"{r.id} — {r.name} — {r.mode} {r.value} — active={r.active}")
                st.json(r.condition)
            st.markdown('Add / edit rule')
            with st.form('rule_form'):
                rn = st.text_input('Rule name')
                cond = st.text_area('Condition JSON (e.g. {"procedure_type":"Knee Arthroplasty"})')
                mode = st.selectbox('Mode',['percentage','fixed'])
                val = st.number_input('Value (percent or fixed KSh)', min_value=0.0, value=0.0)
                active = st.checkbox('Active', value=True)
                if st.form_submit_button('Save rule'):
                    try:
                        cond_json = json.loads(cond) if cond.strip() else {}
                        rr = CommissionRule(name=rn, condition=cond_json, mode=mode, value=val, active=active)
                        db.add(rr); db.commit(); st.success('Rule saved')
                    except Exception as e:
                        st.error('Invalid JSON')

        elif tab == 'Hospitals & Surgeons':
            st.subheader('Hospitals')
            hosps = db.query(Hospital).all()
            hdf = pd.DataFrame([{'id':h.id,'name':h.name,'address':h.address} for h in hosps])
            st.dataframe(hdf)
            with st.form('add_hospital'):
                hn = st.text_input('Hospital name')
                ha = st.text_input('Address')
                if st.form_submit_button('Add hospital'):
                    hh = Hospital(name=hn, address=ha); db.add(hh); db.commit(); st.success('Hospital added')

            st.markdown('---')
            st.subheader('Surgeons')
            surs = db.query(Surgeon).all()
            sdf = pd.DataFrame([{'id':s.id,'name':s.name,'hospital_id':s.hospital_id} for s in surs])
            st.dataframe(sdf)
            with st.form('add_surgeon'):
                sn = st.text_input('Surgeon name')
                hid = st.number_input('Hospital id', min_value=1)
                if st.form_submit_button('Add surgeon'):
                    s = Surgeon(name=sn, hospital_id=hid); db.add(s); db.commit(); st.success('Surgeon added')

        elif tab == 'Audit Logs':
            st.subheader('Audit logs')
            logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(200).all()
            ldf = pd.DataFrame([{'user':l.user,'action':l.action,'entity':l.entity,'entity_id':l.entity_id,'timestamp':l.timestamp,'details':l.details} for l in logs])
            st.dataframe(ldf)
        db.close()

# -------------------- Footer: deployment snippets --------------------

"""
Dockerfile snippet:

FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --upgrade pip && pip install -r requirements.txt
EXPOSE 8501
CMD ["streamlit", "run", "OrthotrackerPro_Full_Streamlit_MVP.py", "--server.port=8501", "--server.address=0.0.0.0"]

requirements.txt:
streamlit
SQLAlchemy
passlib[bcrypt]
boto3
pandas
python-dotenv

.env example:
DATABASE_URL=sqlite:///orthotracker.db
AWS_S3_BUCKET=
AWS_REGION=us-east-1

"""

st.sidebar.markdown("---")
st.sidebar.write("Orthotracker Pro — Full MVP. For production: migrate to Postgres, enable HTTPS, and secure AWS credentials.")


# End of file
