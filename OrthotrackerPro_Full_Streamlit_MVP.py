import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import plotly.express as px
import plotly.graph_objects as go
import random
from typing import List, Tuple

# --- Configuration for the assumed current user (Representative) ---
if 'current_rep_id' not in st.session_state:
    st.session_state['current_rep_id'] = None
    st.session_state['current_rep_name'] = "Unselected"

# -----------------------------
# DATABASE SETUP
# -----------------------------
DATABASE_URL = "sqlite:///orthotracker.db"
# CRITICAL FIX for Streamlit/SQLite concurrency errors
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Function to get session
def get_session():
    return SessionLocal()

# -----------------------------
# MODELS
# -----------------------------
class Representative(Base):
    __tablename__ = "representatives"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    reports = relationship("Report", back_populates="rep")
    def __repr__(self):
        return self.name 

class Procedure(Base):
    __tablename__ = "procedures"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    reports = relationship("Report", back_populates="procedure")
    def __repr__(self):
        return self.name

class Doctor(Base):
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    reports = relationship("Report", back_populates="doctor")
    def __repr__(self):
        return self.name

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    
    # Required Foreign Keys
    rep_id = Column(Integer, ForeignKey("representatives.id"))
    procedure_id = Column(Integer, ForeignKey("procedures.id"))
    doctor_id = Column(Integer, ForeignKey("doctors.id")) 
    
    # Quantifiable Data
    cases_done = Column(Integer, default=0)
    income_generated = Column(Float, default=0.0)
    
    # NEW QUALITATIVE/INVENTORY DATA
    implants_used = Column(String, nullable=True)     # To track implant inventory/type
    challenges = Column(String, nullable=True)        # To log surgical challenges
    recommendation = Column(String, nullable=True)    # To suggest next steps or follow-up
    
    reported_at = Column(DateTime, default=datetime.utcnow)

    rep = relationship("Representative", back_populates="reports")
    procedure = relationship("Procedure", back_populates="reports")
    doctor = relationship("Doctor", back_populates="reports")

# -----------------------------
# INIT DATABASE
# -----------------------------
# This creates all tables *if they don't exist*. It WILL NOT update existing tables.
Base.metadata.create_all(engine)

# -----------------------------
# DATA UTILITY FUNCTIONS
# -----------------------------
@st.cache_data(ttl=600)
def get_select_data() -> Tuple[List[Representative], List[Procedure], List[Doctor]]:
    """Fetches all Reps, Procedures, and Doctors for selectboxes."""
    session = get_session()
    try:
        reps = session.query(Representative).order_by(Representative.name).all()
        procedures = session.query(Procedure).order_by(Procedure.name).all()
        doctors = session.query(Doctor).order_by(Doctor.name).all()
        return reps, procedures, doctors
    except Exception:
        # This will catch errors if the schema is wrong
        return [], [], []
    finally:
        session.close()

@st.cache_data(ttl=60)
def get_all_reports() -> pd.DataFrame:
    """Fetches all reports for the dashboard and returns a DataFrame."""
    session = get_session()
    try:
        reports = session.query(Report).all()
        if not reports:
            return pd.DataFrame()
        
        # This list comprehension will fail if the .db file doesn't have the new columns
        df = pd.DataFrame([{
            "rep": r.rep.name,
            "procedure": r.procedure.name,
            "doctor": r.doctor.name,
            "cases": r.cases_done,
            "income": r.income_generated,
            "implants_used": r.implants_used,
            "challenges": r.challenges,
            "recommendation": r.recommendation,
            "date": r.reported_at
        } for r in reports])
        df["date"] = pd.to_datetime(df["date"])
        return df
    finally:
        session.close()

def generate_test_data_200():
    """Generates 5 Reps, 5 Procedures, 5 Doctors, and 200 random reports."""
    session = get_session()
    
    try:
        st.write("Starting test data generation...")
        rep_names = ["Rep Alice", "Rep Bob", "Rep Charlie", "Rep Dave", "Rep Eve"]
        doctor_names = ["Dr. Adams", "Dr. Baker", "Dr. Cooper", "Dr. Diana", "Dr. Evan"]
        procedure_names = ["TKR", "ACL Reconstruction", "Spinal Fusion", "Rotator Cuff Repair", "Hip Arthroscopy"]

        # Insert static data using session.merge to avoid unique constraint errors
        reps = [session.merge(Representative(name=name)) for name in rep_names]
        procedures = [session.merge(Procedure(name=name)) for name in procedure_names]
        doctors = [session.merge(Doctor(name=name)) for name in doctor_names]
            
        session.commit()
        
        reps = session.query(Representative).all()
        procedures = session.query(Procedure).all()
        doctors = session.query(Doctor).all()
        
        st.write("Generating 200 Random Reports...")
        reports_to_add = []
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=180) # Last 6 months
        time_diff = end_date - start_date
        
        for _ in range(200):
            random_rep = random.choice(reps)
            random_proc = random.choice(procedures)
            random_doc = random.choice(doctors)
            
            # Cases/Income logic
            if "TKR" in random_proc.name or "Fusion" in random_proc.name:
                cases = random.randint(1, 4)
                income = round(random.uniform(250000, 500000) * cases, -3)
                sample_implants = random.choice(["Cemented Femoral Stem", "Uncemented Femoral Stem", "Tibial Tray and Polyethylene"])
            else:
                cases = random.randint(3, 10)
                income = round(random.uniform(50000, 150000) * cases, -3)
                sample_implants = random.choice(["PEEK Suture Anchor", "Titanium Screws 4.5mm (x6)", "Bio-composite Graft"])

            sample_challenges = random.choice(["None", "Calcified tissue removal", "Minor bleeding control issues", "Anesthesia issues noted"])
            sample_recommendations = random.choice(["Order more 3.0mm drills.", "Follow up with Dr. X next week.", "Good case. No action needed.", "Discuss next week's inventory with clinic staff."])
                
            random_seconds = random.randrange(int(time_diff.total_seconds()))
            reported_at = start_date + timedelta(seconds=random_seconds)
            
            report = Report(
                rep_id=random_rep.id,
                procedure_id=random_proc.id,
                doctor_id=random_doc.id,
                cases_done=cases,
                income_generated=income,
                implants_used=sample_implants,
                challenges=sample_challenges,
                recommendation=sample_recommendations,
                reported_at=reported_at
            )
            reports_to_add.append(report)
            
        session.add_all(reports_to_add)
        session.commit()
        st.success("Test data generation complete! **200 reports** added.")
        
    finally:
        session.close()

# -----------------------------
# STREAMLIT APP
# -----------------------------
st.set_page_config(page_title="Orthotracker Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("🏥 Orthotracker Dashboard")

reps, procedures, doctors = get_select_data() 

# -----------------------------
## Rep Control & Data Entry
# -----------------------------
st.sidebar.header("Rep Control & Data Entry")

# Rep Selection (Acts as simple login/user context)
with st.sidebar.expander("👤 Select Your Identity"):
    if reps:
        st.write(f"**Current Rep:** **{st.session_state['current_rep_name']}**")
        
        # Determine the default index safely
        try:
            default_index = reps.index(next(r for r in reps if r.id == st.session_state['current_rep_id']))
        except (StopIteration, ValueError):
            default_index = 0
            
        rep_selection = st.selectbox(
            "Select your Representative Name", 
            reps, 
            format_func=lambda x: x.name,
            index=default_index
        )
        if rep_selection:
            st.session_state['current_rep_id'] = rep_selection.id
            st.session_state['current_rep_name'] = rep_selection.name
    else:
        st.warning("Please add Representatives first (Admin section below).")
        
st.sidebar.markdown("---")


## Add Doctor
with st.sidebar.expander("👨‍⚕️ Add Doctor"):
    doc_name = st.text_input("Doctor Name", key="new_doc_name")
    if st.button("Add Doctor"):
        session = get_session()
        try:
            if not doc_name: st.error("Doctor name cannot be empty.")
            else:
                existing_doc = session.query(Doctor).filter_by(name=doc_name).first()
                if existing_doc: st.warning(f"Doctor **{doc_name}** already exists!")
                else:
                    doc = Doctor(name=doc_name)
                    session.add(doc)
                    session.commit()
                    st.success(f"Doctor **{doc_name}** added!")
                    get_select_data.clear() # Clear cache
        finally:
            session.close()

## Add Report using st.form (Rep's Report)
with st.sidebar.expander("📝 Add New Report"):
    
    if st.session_state['current_rep_id'] is None:
        st.error("Please select your Rep Identity above before adding a report.")
    elif not procedures or not doctors:
        st.warning("Please add at least one Procedure and one Doctor first.")
    else:
        with st.form("add_report_form", clear_on_submit=True):
            
            proc_sel = st.selectbox("Select Procedure", procedures, format_func=lambda x: x.name, key="report_proc_sel")
            doc_sel = st.selectbox("Select Performing Doctor", doctors, format_func=lambda x: x.name, key="report_doc_sel")
            
            st.markdown("---")
            st.subheader("Details & Inventory")
            
            implants_used = st.text_area("Implants Used (Specify Type/Serial #)", key="report_implants", height=80)
            challenges = st.text_area("Surgical Challenges/Notes", key="report_challenges", height=80)
            recommendation = st.text_area("Follow-up/Sales Recommendation", key="report_recommendation", height=80)
            
            st.markdown("---")
            st.subheader("Financial & Count")
            cases_done = st.number_input("Cases Done", min_value=1, step=1, key="report_cases", value=1)
            income = st.number_input("Income Generated (KSh)", min_value=0.0, step=1000.0, key="report_income")
            
            submitted = st.form_submit_button(f"Log Report for {st.session_state['current_rep_name']}")

            if submitted:
                if cases_done <= 0:
                     st.error("Cases done must be at least 1.")
                else:
                    session = get_session()
                    try:
                        report = Report(
                            rep_id=st.session_state['current_rep_id'],
                            procedure_id=proc_sel.id,
                            doctor_id=doc_sel.id,
                            cases_done=cases_done,
                            income_generated=income,
                            implants_used=implants_used,
                            challenges=challenges,
                            recommendation=recommendation
                        )
                        session.add(report)
                        session.commit()
                        st.success(f"Report logged successfully by **{st.session_state['current_rep_name']}**.")
                        get_all_reports.clear() # Clear cache
                    finally:
                        session.close()

st.sidebar.markdown("---")

## Add Rep & Procedure (Admin functions)
with st.sidebar.expander("🔑 Admin: Add Rep & Procedure"):
    rep_name = st.text_input("New Rep Name", key="admin_rep_name")
    if st.button("Add Rep", key="admin_add_rep"):
        session = get_session()
        try:
            if not rep_name: st.error("Representative name cannot be empty.")
            else:
                existing_rep = session.query(Representative).filter_by(name=rep_name).first()
                if existing_rep: st.warning(f"Representative **{rep_name}** already exists!")
                else:
                    rep = Representative(name=rep_name)
                    session.add(rep)
                    session.commit()
                    st.success(f"Representative **{rep_name}** added!")
                    get_select_data.clear()
        finally:
            session.close()

    st.markdown("---")
    proc_name = st.text_input("New Procedure Name", key="admin_proc_name")
    if st.button("Add Procedure", key="admin_add_proc"):
        session = get_session()
        try:
            if not proc_name: st.error("Procedure name cannot be empty.")
            else:
                existing_proc = session.query(Procedure).filter_by(name=proc_name).first()
                if existing_proc: st.warning(f"Procedure **{proc_name}** already exists!")
                else:
                    proc = Procedure(name=proc_name)
                    session.add(proc)
                    session.commit()
                    st.success(f"Procedure **{proc_name}** added!")
                    get_select_data.clear()
        finally:
            session.close()


if st.sidebar.button("Generate Test Data (200 Reports) 🧪"):
    st.cache_data.clear() # Clear ALL caches
    generate_test_data_200()
    st.rerun() # Rerun the app to load the new data

# -----------------------------
## DASHBOARD & INSIGHTS
# -----------------------------
st.header("📊 Insights & Projections")

df = get_all_reports()

if not df.empty:
    
    # -------------------------
    ## Filter Options
    # -------------------------
    st.subheader("Filter Reports")
    col_rep, col_proc, col_doc = st.columns(3)
    
    reps_list = ["All"] + sorted(df["rep"].unique().tolist())
    proc_list = ["All"] + sorted(df["procedure"].unique().tolist())
    doc_list = ["All"] + sorted(df["doctor"].unique().tolist())

    with col_rep:
        rep_filter = st.selectbox("Filter by Rep", reps_list)
    with col_proc:
        proc_filter = st.selectbox("Filter by Procedure", proc_list)
    with col_doc:
        doc_filter = st.selectbox("Filter by Doctor", doc_list)

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    
    date_range = st.date_input(
        "Select Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    df_filtered = df.copy()
    
    # Apply filters
    if rep_filter != "All":
        df_filtered = df_filtered[df_filtered["rep"] == rep_filter]
    if proc_filter != "All":
        df_filtered = df_filtered[df_filtered["procedure"] == proc_filter]
    if doc_filter != "All":
        df_filtered = df_filtered[df_filtered["doctor"] == doc_filter]

    # Apply date filter
    if len(date_range) == 2:
        start_date, end_date = date_range
        if start_date > end_date: start_date, end_date = end_date, start_date
            
        df_filtered = df_filtered[
            (df_filtered["date"].dt.date >= start_date) & 
            (df_filtered["date"].dt.date <= end_date)
        ]

    if df_filtered.empty:
        st.warning("No reports match the current filters.")
        st.stop()
        
    # -------------------------
    ## KPIs
    # -------------------------
    total_cases = df_filtered["cases"].sum()
    total_income = df_filtered["income"].sum()
    avg_income_per_report = df_filtered["income"].mean()

    st.subheader("Key Performance Indicators (KPIs)")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Cases Logged", total_cases)
    kpi2.metric("Total Income (KSh)", f"{total_income:,.2f}")
    kpi3.metric("Avg Income per Report", f"{avg_income_per_report:,.2f}")
    
    st.markdown("---")

    # -------------------------
    ## Reports Table & Export
    # -------------------------
    st.subheader("Reports Table")
    # Displaying all fields including the new qualitative ones
    st.dataframe(df_filtered.sort_values("date", ascending=False), use_container_width=True)

    csv = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button(label="📥 Download Filtered CSV", data=csv, file_name="filtered_reports.csv", mime="text/csv")

    st.markdown("---")
    
    # -------------------------
    ## Charts & Insights
    # -------------------------
    st.subheader("Performance Analysis")
    
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.write("**Income by Doctor**")
        fig_doc = px.bar(df_filtered.groupby("doctor")["income"].sum().reset_index(),
                         x="doctor", y="income",
                         color="income", color_continuous_scale="Reds",
                         title="Income by Performing Doctor")
        st.plotly_chart(fig_doc, use_container_width=True)

    with col_chart2:
        st.write("**Cases by Representative**")
        fig_rep = px.pie(df_filtered.groupby("rep")["cases"].sum().reset_index(),
                         names="rep", values="cases",
                         color_discrete_sequence=px.colors.qualitative.Pastel,
                         title="Case Count Share by Representative")
        st.plotly_chart(fig_rep, use_container_width=True)
        
    st.subheader("Value Assessment: Income vs. Cases")
    
    df_agg_proc = df_filtered.groupby("procedure").agg(
        total_cases=('cases', 'sum'),
        total_income=('income', 'sum')
    ).reset_index()

    fig_scatter = px.scatter(
        df_agg_proc,
        x="total_cases",
        y="total_income",
        size="total_income",
        color="procedure",
        hover_name="procedure",
        title="Income vs. Cases by Procedure (Value)",
        labels={"total_cases": "Total Cases", "total_income": "Total Income (KSh)"}
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown("---")

    # -------------------------
    ## Trend Lines & Projections
    # -------------------------
    st.subheader("Trends & Projections")

    df_filtered["month"] = df_filtered["date"].dt.to_period("M").astype(str)
    
    if df_filtered["month"].nunique() > 1:
        monthly_cases = df_filtered.groupby("month")["cases"].sum().reset_index()
        monthly_income = df_filtered.groupby("month")["income"].sum().reset_index()

        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(x=monthly_cases["month"], y=monthly_cases["cases"], mode="lines+markers", name="Cases", line=dict(color="blue")))
        fig_trend.add_trace(go.Scatter(x=monthly_income["month"], y=monthly_income["income"], mode="lines+markers", name="Income", yaxis="y2", line=dict(color="green")))
        
        fig_trend.update_layout(
            title="Monthly Cases & Income Trends",
            xaxis_title="Month", 
            yaxis=dict(title="Cases Count", showgrid=False, color="blue"),
            yaxis2=dict(title="Income (KSh)", overlaying="y", side="right", showgrid=False, color="green"),
            template="plotly_white",
            legend=dict(x=0, y=1.1, orientation="h")
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        st.info(f"📅 **Projected Monthly Cases:** {monthly_cases['cases'].mean():.1f}")
        st.info(f"💰 **Projected Monthly Income:** KSh {monthly_income['income'].mean():,.2f}")
    else:
        st.info("Need reports spanning more than one month to show trend analysis.")

else:
    st.warning("No reports yet. Please use the sidebar to add data or generate test data.")
