# OrthotrackerPro_Full_Streamlit_MVP.py

from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import streamlit as st

# -------------------------
# Database setup
# -------------------------
DATABASE_URL = "sqlite:///orthotracker.db"  # change if using Postgres/MySQL

engine = create_engine(DATABASE_URL, echo=True)
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
    st.title("Orthotracker MVP App")
    menu = ["Add Representative", "Add Procedure", "Add Report", "Add Attachment", "View Data"]
    choice = st.sidebar.selectbox("Menu", menu)
    session = SessionLocal()

    if choice == "Add Representative":
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

if __name__ == "__main__":
    init_db()
    main()
