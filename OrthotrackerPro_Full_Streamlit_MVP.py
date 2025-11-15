# OrthotrackerPro_Full_Streamlit_MVP.py

from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import streamlit as st
import plotly.express as px

# -------------------------
# Database setup
# -------------------------
DATABASE_URL = "sqlite:///orthotracker.db"  # or use secrets.toml for production
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -------------------------
# Models
# -------------------------
class Representative(Base):
    __tablename__ = "representatives"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    region = Column(String(50), nullable=True)
    reports = relationship("Report", back_populates="rep")

class Procedure(Base):
    __tablename__ = "procedures"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    max_cap = Column(Float, nullable=True)
    reports = relationship("Report", back_populates="procedure")
    attachments = relationship("Attachment", back_populates="procedure")

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    rep_id = Column(Integer, ForeignKey("representatives.id"))
    procedure_id = Column(Integer, ForeignKey("procedures.id"))
    cases_done = Column(Integer, nullable=False)
    income_generated = Column(Float, nullable=False)
    reported_at = Column(DateTime, default=datetime.utcnow)

    rep = relationship("Representative", back_populates="reports")
    procedure = relationship("Procedure", back_populates="reports")

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    procedure_id = Column(Integer, ForeignKey('procedures.id'))
    filename = Column(String)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    procedure = relationship("Procedure", back_populates="attachments")

# -------------------------
# Initialize DB
# -------------------------
def init_db():
    Base.metadata.create_all(bind=engine)

# -------------------------
# Streamlit App
# -------------------------
def main():
    st.set_page_config(page_title="Orthotracker Dashboard", layout="wide", page_icon="💉")
    st.title("🦴 Orthotracker MVP Dashboard")
    menu = ["Dashboard", "Add Representative", "Add Procedure", "Add Report", "Add Attachment", "View Data"]
    choice = st.sidebar.selectbox("Menu", menu)
    session = SessionLocal()

    # -------------------------
    # DASHBOARD
    # -------------------------
    if choice == "Dashboard":
        st.subheader("Overview & Insights")
        # Fetch data
        reports = pd.read_sql(session.query(Report).statement, engine)
        reps = pd.read_sql(session.query(Representative).statement, engine)
        procs = pd.read_sql(session.query(Procedure).statement, engine)

        if reports.empty:
            st.info("No reports available yet.")
        else:
            # KPIs
            total_cases = reports['cases_done'].sum()
            total_income = reports['income_generated'].sum()
            avg_income_per_case = total_income / total_cases if total_cases > 0 else 0
            st.markdown(
                f"""
                <div style="display:flex; gap:20px;">
                    <div style='background-color:#FFB347; padding:20px; border-radius:10px; flex:1;'>
                        <h3>Total Cases</h3>
                        <h2>{total_cases}</h2>
                    </div>
                    <div style='background-color:#77DD77; padding:20px; border-radius:10px; flex:1;'>
                        <h3>Total Income (KSh)</h3>
                        <h2>{total_income:,.0f}</h2>
                    </div>
                    <div style='background-color:#89CFF0; padding:20px; border-radius:10px; flex:1;'>
                        <h3>Avg Income per Case</h3>
                        <h2>{avg_income_per_case:,.0f}</h2>
                    </div>
                </div>
                """, unsafe_allow_html=True
            )

            # Income by procedure
            income_proc = reports.groupby('procedure_id')['income_generated'].sum().reset_index()
            income_proc = income_proc.merge(procs[['id', 'name']], left_on='procedure_id', right_on='id')
            fig_proc = px.bar(income_proc, x='name', y='income_generated', color='income_generated',
                              color_continuous_scale='Viridis', labels={'name':'Procedure', 'income_generated':'Income'})
            st.plotly_chart(fig_proc, use_container_width=True)

            # Cases per rep
            cases_rep = reports.groupby('rep_id')['cases_done'].sum().reset_index()
            cases_rep = cases_rep.merge(reps[['id', 'name']], left_on='rep_id', right_on='id')
            fig_rep = px.pie(cases_rep, names='name', values='cases_done', title="Cases Distribution per Representative")
            st.plotly_chart(fig_rep, use_container_width=True)

            # Simple projection (next month)
            st.subheader("Projection / Forecast")
            avg_monthly_cases = reports['cases_done'].mean()
            avg_monthly_income = reports['income_generated'].mean()
            st.metric("Projected Cases Next Month", int(avg_monthly_cases))
            st.metric("Projected Income Next Month (KSh)", int(avg_monthly_income))

    # -------------------------
    # ADD REPRESENTATIVE
    # -------------------------
    elif choice == "Add Representative":
        st.subheader("Add a Representative")
        with st.form("add_rep"):
            rep_name = st.text_input("Representative Name")
            region = st.text_input("Region")
            submitted = st.form_submit_button("Add Representative")
            if submitted:
                new_rep = Representative(name=rep_name, region=region)
                session.add(new_rep)
                session.commit()
                st.success(f"Added representative {rep_name}")

    # -------------------------
    # ADD PROCEDURE
    # -------------------------
    elif choice == "Add Procedure":
        st.subheader("Add a Procedure")
        with st.form("add_proc"):
            proc_name = st.text_input("Procedure Name (Trauma / Arthro)")
            max_cap = st.number_input("Maximum Cap (optional)", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Add Procedure")
            if submitted:
                new_proc = Procedure(name=proc_name, max_cap=max_cap if max_cap > 0 else None)
                session.add(new_proc)
                session.commit()
                st.success(f"Added procedure {proc_name}")

    # -------------------------
    # ADD REPORT
    # -------------------------
    elif choice == "Add Report":
        st.subheader("Add a Report")
        reps = session.query(Representative).all()
        procs = session.query(Procedure).all()
        if not reps or not procs:
            st.warning("Add at least one representative and one procedure first.")
        else:
            with st.form("add_report"):
                rep_select = st.selectbox("Representative", reps, format_func=lambda x: x.name)
                proc_select = st.selectbox("Procedure", procs, format_func=lambda x: x.name)
                cases_done = st.number_input("Number of Cases Done", min_value=0, step=1)
                income_generated = st.number_input("Income Generated (KSh)", min_value=0.0, step=1.0)
                submitted = st.form_submit_button("Add Report")
                if submitted:
                    new_report = Report(
                        rep_id=rep_select.id,
                        procedure_id=proc_select.id,
                        cases_done=cases_done,
                        income_generated=income_generated
                    )
                    session.add(new_report)
                    session.commit()
                    st.success(f"Added report for {rep_select.name} ({proc_select.name})")

    # -------------------------
    # ADD ATTACHMENT
    # -------------------------
    elif choice == "Add Attachment":
        st.subheader("Add Attachment")
        procs = session.query(Procedure).all()
        if not procs:
            st.warning("Add at least one procedure first.")
        else:
            with st.form("add_attachment"):
                proc_select = st.selectbox("Procedure", procs, format_func=lambda x: x.name)
                file = st.file_uploader("Upload File")
                submitted = st.form_submit_button("Upload Attachment")
                if submitted and file is not None:
                    new_attachment = Attachment(
                        procedure_id=proc_select.id,
                        filename=file.name
                    )
                    session.add(new_attachment)
                    session.commit()
                    st.success(f"Uploaded {file.name} for {proc_select.name}")

    # -------------------------
    # VIEW DATA
    # -------------------------
    elif choice == "View Data":
        st.subheader("All Reports")
        reports = session.query(Report).all()
        if reports:
            for r in reports:
                st.write(f"{r.rep.name} | {r.procedure.name} | Cases: {r.cases_done} | "
                         f"Income: KSh {r.income_generated} | Reported: {r.reported_at}")
        else:
            st.info("No reports recorded yet.")

    session.close()

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    init_db()
    main()
