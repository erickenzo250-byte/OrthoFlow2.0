import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------
# DATABASE SETUP
# -----------------------------
DATABASE_URL = "sqlite:///orthotracker.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()
Base = declarative_base()

# -----------------------------
# MODELS
# -----------------------------
class Representative(Base):
    __tablename__ = "representatives"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    reports = relationship("Report", back_populates="rep")

class Procedure(Base):
    __tablename__ = "procedures"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    reports = relationship("Report", back_populates="procedure")

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

with st.sidebar.expander("Add Representative"):
    name = st.text_input("Rep Name")
    if st.button("Add Rep"):
        if name:
            rep = Representative(name=name)
            session.add(rep)
            session.commit()
            st.success(f"Representative {name} added!")

with st.sidebar.expander("Add Procedure"):
    pname = st.text_input("Procedure Name")
    if st.button("Add Procedure"):
        if pname:
            proc = Procedure(name=pname)
            session.add(proc)
            session.commit()
            st.success(f"Procedure {pname} added!")

with st.sidebar.expander("Add Report"):
    reps = session.query(Representative).all()
    procedures = session.query(Procedure).all()
    rep_sel = st.selectbox("Select Rep", reps, format_func=lambda x: x.name)
    proc_sel = st.selectbox("Select Procedure", procedures, format_func=lambda x: x.name)
    cases_done = st.number_input("Cases Done", min_value=0, step=1)
    income = st.number_input("Income Generated (KSh)", min_value=0.0, step=1000.0)

    if st.button("Add Report"):
        if rep_sel and proc_sel:
            report = Report(rep=rep_sel, procedure=proc_sel, cases_done=cases_done, income_generated=income)
            session.add(report)
            session.commit()
            st.success("Report added!")

# -----------------------------
# DASHBOARD & INSIGHTS
# -----------------------------
st.header("📊 Insights & Projections")

# Fetch data
reports = session.query(Report).all()
if reports:
    df = pd.DataFrame([{
        "rep": r.rep.name,
        "procedure": r.procedure.name,
        "cases": r.cases_done,
        "income": r.income_generated,
        "date": r.reported_at
    } for r in reports])

    # -------------------------
    # KPIs
    # -------------------------
    total_cases = df["cases"].sum()
    total_income = df["income"].sum()
    avg_income = df["income"].mean()

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Cases", total_cases)
    kpi2.metric("Total Income (KSh)", f"{total_income:,.2f}")
    kpi3.metric("Avg Income per Report", f"{avg_income:,.2f}")

    # -------------------------
    # Filter Options
    # -------------------------
    st.subheader("Filter Reports")
    reps_list = ["All"] + sorted(df["rep"].unique().tolist())
    proc_list = ["All"] + sorted(df["procedure"].unique().tolist())

    rep_filter = st.selectbox("Filter by Rep", reps_list)
    proc_filter = st.selectbox("Filter by Procedure", proc_list)

    df_filtered = df.copy()
    if rep_filter != "All":
        df_filtered = df_filtered[df_filtered["rep"] == rep_filter]
    if proc_filter != "All":
        df_filtered = df_filtered[df_filtered["procedure"] == proc_filter]

    # -------------------------
    # Reports Table
    # -------------------------
    st.subheader("Reports Table")
    st.dataframe(df_filtered.sort_values("date", ascending=False))

    # CSV / Excel Export
    csv = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button(label="📥 Download CSV", data=csv, file_name="reports.csv", mime="text/csv")

    # -------------------------
    # Charts & Insights
    # -------------------------
    st.subheader("Cases by Procedure")
    fig_proc = px.bar(df_filtered.groupby("procedure")["cases"].sum().reset_index(),
                      x="procedure", y="cases",
                      color="cases", color_continuous_scale="Viridis")
    st.plotly_chart(fig_proc, use_container_width=True)

    st.subheader("Income by Representative")
    fig_rep = px.pie(df_filtered.groupby("rep")["income"].sum().reset_index(),
                     names="rep", values="income",
                     color_discrete_sequence=px.colors.qualitative.Pastel)
    st.plotly_chart(fig_rep, use_container_width=True)

    # -------------------------
    # Trend Lines & Projections
    # -------------------------
    st.subheader("Trends & Projections")

    df_filtered["month"] = df_filtered["date"].dt.to_period("M").astype(str)
    monthly_cases = df_filtered.groupby("month")["cases"].sum().reset_index()
    monthly_income = df_filtered.groupby("month")["income"].sum().reset_index()

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(x=monthly_cases["month"], y=monthly_cases["cases"], mode="lines+markers", name="Cases", line=dict(color="blue")))
    fig_trend.add_trace(go.Scatter(x=monthly_income["month"], y=monthly_income["income"], mode="lines+markers", name="Income", line=dict(color="green")))
    fig_trend.update_layout(title="Monthly Cases & Income Trends", xaxis_title="Month", yaxis_title="Count / KSh", template="plotly_white")
    st.plotly_chart(fig_trend, use_container_width=True)

    # Projected monthly averages
    st.info(f"📅 Projected Monthly Cases: {monthly_cases['cases'].mean():.1f}")
    st.info(f"💰 Projected Monthly Income: KSh {monthly_income['income'].mean():,.2f}")

else:
    st.warning("No reports yet. Please add data to view insights.")
