import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
import plotly.express as px

# -------------------------------
# Database Setup
# -------------------------------
Base = declarative_base()
DB_FILE = "orthotracker.db"
engine = create_engine(f"sqlite:///{DB_FILE}", echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# -------------------------------
# Models
# -------------------------------
class Representative(Base):
    __tablename__ = "representatives"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    reports = relationship("Report", back_populates="rep")

class Procedure(Base):
    __tablename__ = "procedures"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    attachments = relationship("Attachment", back_populates="procedure")

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    rep_id = Column(Integer, ForeignKey('representatives.id'))
    procedure_id = Column(Integer, ForeignKey('procedures.id'))
    cases_done = Column(Integer)
    income_generated = Column(Float)
    reported_at = Column(DateTime, default=datetime.utcnow)

    rep = relationship("Representative", back_populates="reports")
    procedure = relationship("Procedure")

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    procedure_id = Column(Integer, ForeignKey('procedures.id'))
    filename = Column(String)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    procedure = relationship("Procedure", back_populates="attachments")

# Create all tables
Base.metadata.create_all(engine)

# -------------------------------
# Utility Functions
# -------------------------------
@st.cache_data
def get_all_reports():
    try:
        reports = session.query(Report).all()
        data = [{
            "rep": r.rep.name,
            "procedure": r.procedure.name,
            "cases": r.cases_done,
            "income": r.income_generated,
            "date": r.reported_at
        } for r in reports]
        df = pd.DataFrame(data)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        st.error("⚠️ Could not fetch reports. Check database initialization.")
        st.error(str(e))
        return pd.DataFrame()

# -------------------------------
# Main App
# -------------------------------
def main():
    st.set_page_config(page_title="OrthoTracker Pro", page_icon="🏥", layout="wide")
    st.title("🦴 OrthoTracker Pro Dashboard")

    # Sidebar Menu
    menu = ["Dashboard", "Insights", "Projections", "Add Data"]
    choice = st.sidebar.selectbox("Menu", menu)

    df = get_all_reports()

    # -------------------------------
    # Dashboard
    # -------------------------------
    if choice == "Dashboard":
        st.subheader("📊 Dashboard Overview")
        if not df.empty:
            st.dataframe(df)

            # Cases per Representative
            fig_cases = px.bar(
                df.groupby("rep")["cases"].sum().reset_index(),
                x="rep", y="cases",
                title="Total Cases by Representative",
                color="cases",
                color_continuous_scale="Viridis"
            )
            st.plotly_chart(fig_cases, use_container_width=True)

            # Income over time
            income_time = df.groupby(df["date"].dt.to_period("M"))["income"].sum().reset_index()
            income_time["date"] = income_time["date"].dt.to_timestamp()
            fig_income = px.line(
                income_time,
                x="date", y="income",
                title="Income Over Time",
                markers=True,
                line_shape="spline"
            )
            st.plotly_chart(fig_income, use_container_width=True)
        else:
            st.info("No reports available yet.")

    # -------------------------------
    # Insights
    # -------------------------------
    elif choice == "Insights":
        st.subheader("🔍 Insights")
        if not df.empty:
            top_reps = df.groupby("rep")["cases"].sum().sort_values(ascending=False).head(10).reset_index()
            top_procs = df.groupby("procedure")["income"].sum().sort_values(ascending=False).head(10).reset_index()

            st.write("### Top Representatives by Cases")
            fig_top_reps = px.pie(top_reps, names="rep", values="cases", title="Top Reps by Cases")
            st.plotly_chart(fig_top_reps, use_container_width=True)

            st.write("### Top Procedures by Income")
            fig_top_procs = px.pie(top_procs, names="procedure", values="income", title="Top Procedures by Income")
            st.plotly_chart(fig_top_procs, use_container_width=True)
        else:
            st.info("No data available for insights.")

    # -------------------------------
    # Projections
    # -------------------------------
    elif choice == "Projections":
        st.subheader("📈 Income Projections")
        if not df.empty:
            monthly = df.groupby(df["date"].dt.to_period("M"))["income"].sum()
            fig_proj = px.line(
                monthly.reset_index(),
                x="date", y="income",
                title="Monthly Income",
                markers=True,
                line_shape="spline"
            )
            st.plotly_chart(fig_proj, use_container_width=True)
            projected = monthly.mean() * 12
            st.success(f"Projected Annual Income: KSh {projected:,.0f}")
        else:
            st.info("No data available for projections.")

    # -------------------------------
    # Add Data
    # -------------------------------
    elif choice == "Add Data":
        st.subheader("➕ Add New Report")
        reps = [r.name for r in session.query(Representative).all()]
        procs = [p.name for p in session.query(Procedure).all()]

        rep_name = st.selectbox("Representative", reps)
        proc_name = st.selectbox("Procedure", procs)
        cases = st.number_input("Cases Done", min_value=0, step=1)
        income = st.number_input("Income Generated (KSh)", min_value=0.0, step=100.0)

        if st.button("Submit Report"):
            rep = session.query(Representative).filter_by(name=rep_name).first()
            proc = session.query(Procedure).filter_by(name=proc_name).first()
            new_report = Report(rep=rep, procedure=proc, cases_done=cases, income_generated=income)
            session.add(new_report)
            session.commit()
            st.success("✅ Report added successfully!")
            st.experimental_rerun()  # Refresh dashboard

# -------------------------------
# Run App
# -------------------------------
if __name__ == "__main__":
    main()
