import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import plotly.express as px
import plotly.graph_objects as go
import random
from typing import List, Tuple

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

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    rep_id = Column(Integer, ForeignKey("representatives.id"))
    procedure_id = Column(Integer, ForeignKey("procedures.id"))
    cases_done = Column(Integer, default=0)
    income_generated = Column(Float, default=0.0)
    reported_at = Column(DateTime, default=datetime.utcnow)

    rep = relationship("Representative", back_populates="reports")
    procedure = relationship("Procedure", back_populates="reports")

# -----------------------------
# INIT DATABASE
# -----------------------------
Base.metadata.create_all(engine)

# -----------------------------
# DATA UTILITY FUNCTIONS
# -----------------------------
@st.cache_data(ttl=600) # Cache for 10 minutes
def get_reps_and_procs() -> Tuple[List[Representative], List[Procedure]]:
    """Fetches all Reps and Procedures for selectboxes."""
    session = get_session()
    try:
        reps = session.query(Representative).all()
        procedures = session.query(Procedure).all()
        return reps, procedures
    except Exception as e:
        # st.error(f"Database error during fetch: {e}") # Keep this commented out for deployment
        return [], []
    finally:
        session.close()

@st.cache_data(ttl=60) # Cache for 1 minute
def get_all_reports() -> pd.DataFrame:
    """Fetches all reports for the dashboard and returns a DataFrame."""
    session = get_session()
    try:
        reports = session.query(Report).all()
        if not reports:
            return pd.DataFrame()
        
        df = pd.DataFrame([{
            "rep": r.rep.name,
            "procedure": r.procedure.name,
            "cases": r.cases_done,
            "income": r.income_generated,
            "date": r.reported_at
        } for r in reports])
        df["date"] = pd.to_datetime(df["date"])
        return df
    finally:
        session.close()

def generate_test_data_200():
    """Generates 5 Reps, 5 Procedures, and 200 random reports."""
    session = get_session()
    
    try:
        st.write("Starting test data generation...")
        rep_names = ["Dr. Smith", "Dr. Johnson", "Dr. Achieng", "Dr. Mwangi", "Dr. Chen"]
        procedure_names = [
            "Total Knee Replacement (TKR)", 
            "ACL Reconstruction", 
            "Spinal Fusion (L4-L5)", 
            "Rotator Cuff Repair", 
            "Hip Arthroscopy"
        ]

        # Insert static data
        reps = []
        for name in rep_names:
            rep = session.query(Representative).filter_by(name=name).first()
            if not rep:
                rep = Representative(name=name)
                session.add(rep)
            reps.append(rep)
        
        procedures = []
        for name in procedure_names:
            proc = session.query(Procedure).filter_by(name=name).first()
            if not proc:
                proc = Procedure(name=name)
                session.add(proc)
            procedures.append(proc)
            
        session.commit()
        
        # Re-fetch the actual objects with IDs
        reps = session.query(Representative).all()
        procedures = session.query(Procedure).all()
        
        # Generate 200 Random Reports
        st.write("Generating 200 Random Reports...")
        reports_to_add = []
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=180) # Last 6 months
        time_diff = end_date - start_date
        
        for _ in range(200):
            random_rep = random.choice(reps)
            random_proc = random.choice(procedures)
            
            # Cases/Income logic
            if "Replacement" in random_proc.name or "Fusion" in random_proc.name:
                cases = random.randint(1, 4)
                income = round(random.uniform(250000, 500000) * cases, -3)
            else:
                cases = random.randint(3, 10)
                income = round(random.uniform(50000, 150000) * cases, -3)
                
            random_seconds = random.randrange(int(time_diff.total_seconds()))
            reported_at = start_date + timedelta(seconds=random_seconds)
            
            report = Report(
                rep_id=random_rep.id,
                procedure_id=random_proc.id,
                cases_done=cases,
                income_generated=income,
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

# --- Fetch cached objects for sidebar forms ---
reps, procedures = get_reps_and_procs() 

# -----------------------------
# SIDEBAR - Add Data & Testing
# -----------------------------
st.sidebar.header("Add Data")

## Add Representative
with st.sidebar.expander("➕ Add Representative"):
    rep_name = st.text_input("Rep Name", key="new_rep_name")
    if st.button("Add Rep"):
        session = get_session()
        try:
            if not rep_name:
                st.error("Representative name cannot be empty.")
            else:
                existing_rep = session.query(Representative).filter_by(name=rep_name).first()
                if existing_rep:
                    st.warning(f"Representative **{rep_name}** already exists!")
                else:
                    rep = Representative(name=rep_name)
                    session.add(rep)
                    session.commit()
                    st.success(f"Representative **{rep_name}** added!")
                    get_reps_and_procs.clear() # Clear cache
                    get_all_reports.clear() # Clear cache
        finally:
            session.close()

## Add Procedure
with st.sidebar.expander("➕ Add Procedure"):
    proc_name = st.text_input("Procedure Name", key="new_proc_name")
    if st.button("Add Procedure"):
        session = get_session()
        try:
            if not proc_name:
                st.error("Procedure name cannot be empty.")
            else:
                existing_proc = session.query(Procedure).filter_by(name=proc_name).first()
                if existing_proc:
                    st.warning(f"Procedure **{proc_name}** already exists!")
                else:
                    proc = Procedure(name=proc_name)
                    session.add(proc)
                    session.commit()
                    st.success(f"Procedure **{proc_name}** added!")
                    get_reps_and_procs.clear() # Clear cache
                    get_all_reports.clear() # Clear cache
        finally:
            session.close()

## Add Report using st.form
with st.sidebar.expander("📝 Add Report"):
    with st.form("add_report_form", clear_on_submit=True):
        
        if not reps or not procedures:
            st.warning("Please add at least one Representative and one Procedure first.")
            submitted = False 
        else:
            rep_sel = st.selectbox("Select Rep", reps, format_func=lambda x: x.name, key="report_rep_sel")
            proc_sel = st.selectbox("Select Procedure", procedures, format_func=lambda x: x.name, key="report_proc_sel")
            cases_done = st.number_input("Cases Done", min_value=0, step=1, key="report_cases")
            income = st.number_input("Income Generated (KSh)", min_value=0.0, step=1000.0, key="report_income")
            
            submitted = st.form_submit_button("Add Report")

        if submitted and reps and procedures:
            if cases_done < 0 or income < 0:
                 st.error("Cases done and income must be non-negative values.")
            else:
                session = get_session()
                try:
                    report = Report(rep_id=rep_sel.id, procedure_id=proc_sel.id, cases_done=cases_done, income_generated=income)
                    session.add(report)
                    session.commit()
                    st.success(f"Report for **{rep_sel.name}** added successfully!")
                    get_all_reports.clear() # Clear cache
                finally:
                    session.close()
                    
st.sidebar.markdown("---")
if st.sidebar.button("Generate Test Data (200 Reports) 🧪"):
    st.cache_data.clear() # Clear ALL caches
    generate_test_data_200()
    st.rerun()

# -----------------------------
# DASHBOARD & INSIGHTS
# -----------------------------
st.header("📊 Insights & Projections")

df = get_all_reports()

if not df.empty:
    
    # -------------------------
    # Filter Options
    # -------------------------
    st.subheader("Filter Reports")
    col_rep, col_proc = st.columns(2)
    
    reps_list = ["All"] + sorted(df["rep"].unique().tolist())
    proc_list = ["All"] + sorted(df["procedure"].unique().tolist())

    with col_rep:
        rep_filter = st.selectbox("Filter by Rep", reps_list)
    with col_proc:
        proc_filter = st.selectbox("Filter by Procedure", proc_list)

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

    # Apply date filter
    if len(date_range) == 2:
        start_date, end_date = date_range
        if start_date > end_date:
            start_date, end_date = end_date, start_date
            
        df_filtered = df_filtered[
            (df_filtered["date"].dt.date >= start_date) & 
            (df_filtered["date"].dt.date <= end_date)
        ]

    if df_filtered.empty:
        st.warning("No reports match the current filters.")
        st.stop()
        
    # -------------------------
    # KPIs (Calculated after filtering)
    # -------------------------
    total_cases = df_filtered["cases"].sum()
    total_income = df_filtered["income"].sum()
    avg_income = df_filtered["income"].mean()

    st.subheader("Key Performance Indicators (KPIs)")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Cases", total_cases)
    kpi2.metric("Total Income (KSh)", f"{total_income:,.2f}")
    kpi3.metric("Avg Income per Report", f"{avg_income:,.2f}")
    
    st.markdown("---")

    # -------------------------
    # Reports Table & Export
    # -------------------------
    st.subheader("Reports Table")
    st.dataframe(df_filtered.sort_values("date", ascending=False), use_container_width=True)

    csv = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button(label="📥 Download Filtered CSV", data=csv, file_name="filtered_reports.csv", mime="text/csv")

    st.markdown("---")
    
    # -------------------------
    # Charts & Insights
    # -------------------------
    st.subheader("Distribution Analysis")
    
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.write("**Cases by Procedure**")
        fig_proc = px.bar(df_filtered.groupby("procedure")["cases"].sum().reset_index(),
                         x="procedure", y="cases",
                         color="cases", color_continuous_scale="Viridis",
                         title="Total Cases by Procedure")
        st.plotly_chart(fig_proc, use_container_width=True)

    with col_chart2:
        st.write("**Income by Representative**")
        fig_rep = px.pie(df_filtered.groupby("rep")["income"].sum().reset_index(),
                         names="rep", values="income",
                         color_discrete_sequence=px.colors.qualitative.Pastel,
                         title="Income Share by Representative")
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
        title="Income vs. Cases by Procedure (Procedure Value)",
        labels={"total_cases": "Total Cases", "total_income": "Total Income (KSh)"}
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown("---")

    # -------------------------
    # Trend Lines & Projections
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
