import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import sessionmaker, scoped_session, relationship, declarative_base
import plotly.express as px
import io

# -------------------------------
# Database Setup
# -------------------------------
Base = declarative_base()
DB_FILE = "orthotracker.db"
engine = create_engine(f"sqlite:///{DB_FILE}", echo=False, connect_args={"check_same_thread": False})
# expire_on_commit=False prevents objects from being expired which helps with Streamlit re-runs
SessionLocal = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))

# -------------------------------
# Models
# -------------------------------
class Representative(Base):
    __tablename__ = "representatives"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    reports = relationship("Report", back_populates="rep", cascade="all, delete-orphan")

class Procedure(Base):
    __tablename__ = "procedures"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    attachments = relationship("Attachment", back_populates="procedure", cascade="all, delete-orphan")

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    rep_id = Column(Integer, ForeignKey('representatives.id'))
    procedure_id = Column(Integer, ForeignKey('procedures.id'))
    cases_done = Column(Integer)
    income_generated = Column(Float)
    reported_at = Column(DateTime, default=datetime.utcnow)

    rep = relationship("Representative", back_populates="reports")
    procedure = relationship("Procedure")  # backref not required here

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    procedure_id = Column(Integer, ForeignKey('procedures.id'))
    filename = Column(String)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    procedure = relationship("Procedure", back_populates="attachments")

# Create tables
Base.metadata.create_all(engine)

# -------------------------------
# Utility Functions
# -------------------------------
def get_session():
    return SessionLocal()

@st.cache_data(show_spinner=False)
def _fetch_reports_serialized():
    """
    Internal cached fetch. Cache will be invalidated by calling function with a key change.
    We serialize to a plain list-of-dicts so caching is safe.
    """
    db = get_session()
    try:
        reports = db.query(Report).all()
        data = [{
            "rep": r.rep.name if r.rep else "Unknown",
            "procedure": r.procedure.name if r.procedure else "Unknown",
            "cases": r.cases_done or 0,
            "income": r.income_generated or 0.0,
            "date": r.reported_at
        } for r in reports]
        return data
    finally:
        db.close()

def get_all_reports(force_refresh: bool = False):
    """
    Returns a dataframe of all reports.
    If force_refresh=True, we include a varying param to invalidate cached _fetch_reports_serialized() call.
    """
    # trick: include timestamp as cache key by calling the cached function directly (st.cache_data handles it)
    data = _fetch_reports_serialized()
    df = pd.DataFrame(data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df

def seed_defaults():
    """Helper to create initial reps/procedures if none exist."""
    db = get_session()
    try:
        if db.query(Representative).count() == 0:
            db.add_all([Representative(name="Erick Ochieng"), Representative(name="Naomi")])
        if db.query(Procedure).count() == 0:
            db.add_all([Procedure(name="TKR"), Procedure(name="PFNA"), Procedure(name="Interlocking Nail")])
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

# -------------------------------
# Main App
# -------------------------------
def main():
    st.set_page_config(page_title="OrthoTracker Pro", page_icon="🏥", layout="wide")
    st.title("🦴 OrthoTracker Pro Dashboard")

    seed_defaults()  # ensure there is at least some data to start with

    menu = ["Dashboard", "Insights", "Projections", "Add Data"]
    choice = st.sidebar.selectbox("Menu", menu)

    # Fetch dataframe (not cached over-adds because we commit then rerun)
    df = get_all_reports()

    # ---------- Dashboard ----------
    if choice == "Dashboard":
        st.subheader("📊 Dashboard Overview")
        if df.empty:
            st.info("No reports available yet.")
        else:
            st.dataframe(df.sort_values("date", ascending=False).reset_index(drop=True))

            # Cases per Representative
            cases_by_rep = df.groupby("rep", as_index=False)["cases"].sum()
            fig_cases = px.bar(
                cases_by_rep,
                x="rep", y="cases",
                title="Total Cases by Representative",
                color="cases",
                color_continuous_scale="Viridis"
            )
            st.plotly_chart(fig_cases, use_container_width=True)

            # Income over time (monthly)
            income_time = df.groupby(df["date"].dt.to_period("M"))["income"].sum().reset_index()
            if not income_time.empty:
                income_time["date"] = income_time["date"].dt.to_timestamp()
                fig_income = px.line(
                    income_time,
                    x="date", y="income",
                    title="Income Over Time",
                    markers=True,
                    line_shape="spline"
                )
                st.plotly_chart(fig_income, use_container_width=True)

            # CSV export
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download CSV", data=csv, file_name="ortho_reports.csv", mime="text/csv")

    # ---------- Insights ----------
    elif choice == "Insights":
        st.subheader("🔍 Insights")
        if df.empty:
            st.info("No data available for insights.")
        else:
            top_reps = df.groupby("rep", as_index=False)["cases"].sum().sort_values("cases", ascending=False).head(10)
            top_procs = df.groupby("procedure", as_index=False)["income"].sum().sort_values("income", ascending=False).head(10)

            st.write("### Top Representatives by Cases")
            fig_top_reps = px.pie(top_reps, names="rep", values="cases", title="Top Reps by Cases")
            st.plotly_chart(fig_top_reps, use_container_width=True)

            st.write("### Top Procedures by Income")
            fig_top_procs = px.pie(top_procs, names="procedure", values="income", title="Top Procedures by Income")
            st.plotly_chart(fig_top_procs, use_container_width=True)

            # simple KPI
            st.metric("Total Income (KSh)", f"{df['income'].sum():,.0f}")
            st.metric("Total Cases", int(df['cases'].sum()))

    # ---------- Projections ----------
    elif choice == "Projections":
        st.subheader("📈 Income Projections")
        if df.empty:
            st.info("No data available for projections.")
        else:
            monthly = df.groupby(df["date"].dt.to_period("M"))["income"].sum().reset_index()
            monthly["date"] = monthly["date"].dt.to_timestamp()
            fig_proj = px.line(monthly, x="date", y="income", title="Monthly Income", markers=True, line_shape="spline")
            st.plotly_chart(fig_proj, use_container_width=True)

            projected_annual = monthly["income"].mean() * 12
            st.success(f"Projected Annual Income: KSh {projected_annual:,.0f}")

    # ---------- Add Data ----------
    elif choice == "Add Data":
        st.subheader("➕ Add New Report / Entities")
        db = get_session()
        try:
            reps = [r.name for r in db.query(Representative).order_by(Representative.name).all()]
            procs = [p.name for p in db.query(Procedure).order_by(Procedure.name).all()]
        finally:
            db.close()

        col1, col2 = st.columns(2)
        with col1:
            if reps:
                rep_name = st.selectbox("Representative", reps)
            else:
                rep_name = None
                st.warning("No representatives found. Add one below.")

            new_rep = st.text_input("Or add new Representative (type a name and press +)", key="new_rep")
            if st.button("➕ Add Representative"):
                if new_rep.strip():
                    db = get_session()
                    try:
                        if db.query(Representative).filter_by(name=new_rep.strip()).first():
                            st.warning("Representative already exists.")
                        else:
                            db.add(Representative(name=new_rep.strip()))
                            db.commit()
                            st.success("Representative added.")
                            st.experimental_rerun()
                    except Exception as e:
                        db.rollback()
                        st.error("Failed to add representative.")
                        st.error(str(e))
                    finally:
                        db.close()

        with col2:
            if procs:
                proc_name = st.selectbox("Procedure", procs)
            else:
                proc_name = None
                st.warning("No procedures found. Add one below.")

            new_proc = st.text_input("Or add new Procedure (type a name and press +)", key="new_proc")
            if st.button("➕ Add Procedure"):
                if new_proc.strip():
                    db = get_session()
                    try:
                        if db.query(Procedure).filter_by(name=new_proc.strip()).first():
                            st.warning("Procedure already exists.")
                        else:
                            db.add(Procedure(name=new_proc.strip()))
                            db.commit()
                            st.success("Procedure added.")
                            st.experimental_rerun()
                    except Exception as e:
                        db.rollback()
                        st.error("Failed to add procedure.")
                        st.error(str(e))
                    finally:
                        db.close()

        st.markdown("---")
        st.write("Add a report (choose existing rep/procedure or add new ones above).")
        # fallback: if no existing reps/procs, require manual name
        rep_name_final = rep_name if rep_name else st.text_input("Representative name (required if none above)")
        proc_name_final = proc_name if proc_name else st.text_input("Procedure name (required if none above)")

        cases = st.number_input("Cases Done", min_value=0, step=1, value=0)
        income = st.number_input("Income Generated (KSh)", min_value=0.0, step=100.0, value=0.0)
        report_date = st.date_input("Reported Date", value=datetime.utcnow().date())
        uploaded_file = st.file_uploader("Attach file (optional)", type=["pdf", "png", "jpg", "jpeg"])

        if st.button("Submit Report"):
            if not rep_name_final or not proc_name_final:
                st.error("Representative and Procedure are required.")
            else:
                db = get_session()
                try:
                    # get or create rep
                    rep = db.query(Representative).filter_by(name=rep_name_final.strip()).first()
                    if not rep:
                        rep = Representative(name=rep_name_final.strip())
                        db.add(rep)
                        db.flush()  # assign id

                    proc = db.query(Procedure).filter_by(name=proc_name_final.strip()).first()
                    if not proc:
                        proc = Procedure(name=proc_name_final.strip())
                        db.add(proc)
                        db.flush()

                    dt = datetime.combine(report_date, datetime.utcnow().time())
                    new_report = Report(rep=rep, procedure=proc, cases_done=int(cases), income_generated=float(income), reported_at=dt)
                    db.add(new_report)
                    db.commit()

                    # handle attachment
                    if uploaded_file is not None:
                        # store file on disk (simple approach) - consider storing in object storage for production
                        filename = uploaded_file.name
                        save_path = f"uploads/{filename}"
                        with open(save_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        att = Attachment(procedure_id=proc.id, filename=save_path)
                        db.add(att)
                        db.commit()

                    st.success("✅ Report added successfully!")
                    # clear cached reports and rerun to reflect new data
                    _fetch_reports_serialized.clear()
                    st.experimental_rerun()
                except Exception as e:
                    db.rollback()
                    st.error("Failed to save report.")
                    st.error(str(e))
                finally:
                    db.close()

if __name__ == "__main__":
    main()
