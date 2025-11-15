import streamlit as st
import pandas as pd
from datetime import datetime, date
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------
# DATABASE SETUP
# -----------------------------
DATABASE_URL = "sqlite:///orthotracker.db"
# Use check_same_thread=False for SQLite with Streamlit
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

    # Define a simple representation for Streamlit's format_func
    def __repr__(self):
        return self.name 

class Procedure(Base):
    __tablename__ = "procedures"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    reports = relationship("Report", back_populates="procedure")

    # Define a simple representation for Streamlit's format_func
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
# STREAMLIT APP
# -----------------------------
st.set_page_config(page_title="Orthotracker Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("🏥 Orthotracker Dashboard")

# -----------------------------
# SIDEBAR - Add Data
# -----------------------------
st.sidebar.header("Add Data")

## Add Representative
with st.sidebar.expander("➕ Add Representative"):
    rep_name = st.text_input("Rep Name", key="new_rep_name")
    if st.button("Add Rep"):
        session = get_session()
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
        session.close()

## Add Procedure
with st.sidebar.expander("➕ Add Procedure"):
    proc_name = st.text_input("Procedure Name", key="new_proc_name")
    if st.button("Add Procedure"):
        session = get_session()
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
        session.close()

## Add Report using st.form
with st.sidebar.expander("📝 Add Report"):
    session = get_session()
    reps = session.query(Representative).all()
    procedures = session.query(Procedure).all()
    session.close() # Close session after fetching objects for selectbox

    with st.form("add_report_form", clear_on_submit=True):
        
        if not reps or not procedures:
            st.warning("Please add at least one Representative and one Procedure first.")
            submitted = False 
        else:
            # FIX: Use format_func to display name but return the object
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
                # Use the ID of the selected object for the relationship
                report = Report(rep_id=rep_sel.id, procedure_id=proc_sel.id, cases_done=cases_done, income_generated=income)
                session.add(report)
                session.commit()
                session.close()
                st.success(f"Report for **{rep_sel.name}** added successfully!")

# -----------------------------
# DASHBOARD & INSIGHTS
# -----------------------------
st.header("📊 Insights & Projections")

# Fetch data
session = get_session()
reports = session.query(Report).all()
session.close() # Close session after fetching data

if reports:
    # --- Data Processing ---
    df = pd.DataFrame([{
        "rep": r.rep.name,
        "procedure": r.procedure.name,
        "cases": r.cases_done,
        "income": r.income_generated,
        "date": r.reported_at
    } for r in reports])

    df["date"] = pd.to_datetime(df["date"])

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

    # Date filter
    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    
    # FIX: Handle potential single date selection (e.g., date_range is a tuple with 1 element)
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
        # Ensure start_date <= end_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date
            
        df_filtered = df_filtered[
            (df_filtered["date"].dt.date >= start_date) & 
            (df_filtered["date"].dt.date <= end_date)
        ]

    # Handle case where filtering results in empty dataframe
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

    # -------------------------
    # Reports Table & Export
    # -------------------------
    st.subheader("Reports Table")
    st.dataframe(df_filtered.sort_values("date", ascending=False), use_container_width=True)

    csv = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button(label="📥 Download Filtered CSV", data=csv, file_name="filtered_reports.csv", mime="text/csv")

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


    # -------------------------
    # Trend Lines & Projections
    # -------------------------
    st.subheader("Trends & Projections")

    df_filtered["month"] = df_filtered["date"].dt.to_period("M").astype(str)
    
    # Check if there's enough data for meaningful trends (more than one unique month)
    if df_filtered["month"].nunique() > 1:
        monthly_cases = df_filtered.groupby("month")["cases"].sum().reset_index()
        monthly_income = df_filtered.groupby("month")["income"].sum().reset_index()

        fig_trend = go.Figure()
        
        # Add Cases trace (Primary Y-axis)
        fig_trend.add_trace(go.Scatter(x=monthly_cases["month"], y=monthly_cases["cases"], mode="lines+markers", name="Cases", line=dict(color="blue")))
        
        # Add Income trace (Secondary Y-axis)
        fig_trend.add_trace(go.Scatter(x=monthly_income["month"], y=monthly_income["income"], mode="lines+markers", name="Income", yaxis="y2", line=dict(color="green")))
        
        # FIX: Define Y-axes explicitly for dual-axis plot
        fig_trend.update_layout(
            title="Monthly Cases & Income Trends",
            xaxis_title="Month", 
            yaxis=dict(title="Cases Count", showgrid=False, color="blue"), # Primary Y-axis (y)
            yaxis2=dict(title="Income (KSh)", overlaying="y", side="right", showgrid=False, color="green"), # Secondary Y-axis (y2)
            template="plotly_white",
            legend=dict(x=0, y=1.1, orientation="h")
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        # Projected monthly averages
        st.info(f"📅 **Projected Monthly Cases:** {monthly_cases['cases'].mean():.1f}")
        st.info(f"💰 **Projected Monthly Income:** KSh {monthly_income['income'].mean():,.2f}")
    else:
        st.info("Need reports spanning more than one month to show trend analysis.")

else:
    st.warning("No reports yet. Please add data using the sidebar to view insights.")
