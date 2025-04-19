# app.py - Main application file
import streamlit as st
from streamlit_option_menu import option_menu
import hashlib
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import base64
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import numpy as np
from PIL import Image
import os  # <- Fixed the typo here

# Database setup
def init_db():
    conn = sqlite3.connect('lab_manager.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, full_name TEXT, email TEXT, role TEXT)''')
    
    # Reagents table
    c.execute('''CREATE TABLE IF NOT EXISTS reagents
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, cas_number TEXT, 
                 supplier TEXT, quantity REAL, unit TEXT, concentration REAL, 
                 concentration_unit TEXT, location TEXT, date_received TEXT, 
                 expiry_date TEXT, hazard_class TEXT, owner TEXT)''')
    
    # Protocols table
    c.execute('''CREATE TABLE IF NOT EXISTS protocols
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, protocol_type TEXT, 
                 description TEXT, steps TEXT, created_by TEXT, created_date TEXT, 
                 last_modified TEXT)''')
    
    # Calendar events table
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT, 
                 start_date TEXT, end_date TEXT, event_type TEXT, frequency TEXT, 
                 created_by TEXT, completed INTEGER DEFAULT 0)''')
    
    # Experiment logs table
    c.execute('''CREATE TABLE IF NOT EXISTS experiment_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, experiment_type TEXT, 
                 date TEXT, protocol_id INTEGER, results TEXT, observations TEXT, 
                 created_by TEXT, data_file TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

# Authentication functions
def create_user(username, password, full_name, email, role):
    conn = sqlite3.connect('lab_manager.db')
    c = conn.cursor()
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    try:
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", 
                 (username, hashed_pw, full_name, email, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(username, password):
    conn = sqlite3.connect('lab_manager.db')
    c = conn.cursor()
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", 
              (username, hashed_pw))
    user = c.fetchone()
    conn.close()
    return user

# Utility functions
def get_table_download_link(df, filename="data.csv", text="Download CSV"):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}">{text}</a>'

def create_pdf(content, filename="report.pdf"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    for item in content:
        if isinstance(item, str):
            story.append(Paragraph(item, styles["Normal"]))
            story.append(Spacer(1, 12))
        elif isinstance(item, pd.DataFrame):
            table_data = [item.columns.tolist()] + item.values.tolist()
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(table)
            story.append(Spacer(1, 12))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# Page functions
def login_page():
    st.title("Lab Management System - Login")
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        menu = option_menu(None, ["Login", "Register"], 
                          icons=['box-arrow-in-right', 'person-plus'], 
                          menu_icon="cast", default_index=0, orientation="horizontal")
        
        if menu == "Login":
            with st.form("Login Form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Login")
                
                if submit:
                    user = verify_user(username, password)
                    if user:
                        st.session_state.logged_in = True
                        st.session_state.user = {
                            "username": user[0],
                            "full_name": user[2],
                            "role": user[4]
                        }
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
        
        elif menu == "Register":
            with st.form("Register Form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                full_name = st.text_input("Full Name")
                email = st.text_input("Email")
                role = st.selectbox("Role", ["Researcher", "Technician", "Student", "PI"])
                submit = st.form_submit_button("Register")
                
                if submit:
                    if password != confirm_password:
                        st.error("Passwords do not match!")
                    else:
                        if create_user(username, password, full_name, email, role):
                            st.success("Registration successful! Please login.")
                        else:
                            st.error("Username already exists!")
    else:
        st.success(f"Welcome back, {st.session_state.user['full_name']}!")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()

def dashboard_page():
    st.title(" 📊Lab Dashboard")
    
    # Get data from various tables
    conn = sqlite3.connect('lab_manager.db')
    
    # Today's tasks
    today = datetime.now().strftime("%Y-%m-%d")
    events_today = pd.read_sql(f"""
        SELECT title, event_type, start_date, end_date 
        FROM events 
        WHERE date(start_date) <= date('{today}') 
        AND date(end_date) >= date('{today}')
        AND completed = 0
        ORDER BY start_date
    """, conn)
    
    # Recent reagents
    recent_reagents = pd.read_sql("""
        SELECT name, quantity, unit, date_received, expiry_date 
        FROM reagents 
        ORDER BY date_received DESC 
        LIMIT 5
    """, conn)
    
    # Recent protocols
    recent_protocols = pd.read_sql("""
        SELECT title, protocol_type, created_date 
        FROM protocols 
        ORDER BY created_date DESC 
        LIMIT 5
    """, conn)
    
    conn.close()
    
    # Dashboard layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Today's Tasks")
        if not events_today.empty:
            st.dataframe(events_today)
            if st.button("View All Tasks"):
                st.session_state.current_page = "Lab Planner"
                st.rerun()
        else:
            st.info("No tasks scheduled for today")
    
    with col2:
        st.subheader("Recent Reagents")
        if not recent_reagents.empty:
            st.dataframe(recent_reagents)
            if st.button("View Reagent Inventory"):
                st.session_state.current_page = "Reagent Tracker"
                st.rerun()
        else:
            st.info("No reagents in inventory")
    
    st.subheader("Recent Protocols")
    if not recent_protocols.empty:
        st.dataframe(recent_protocols)
        if st.button("View All Protocols"):
            st.session_state.current_page = "Protocol Generator"
            st.rerun()
    else:
        st.info("No protocols available")
    
    # Download/Print options
    st.markdown("### Export Options")
    if st.button("Generate Dashboard Report (PDF)"):
        report_content = [
            "Lab Dashboard Report",
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "\nToday's Tasks:",
            events_today,
            "\nRecent Reagents:",
            recent_reagents,
            "\nRecent Protocols:",
            recent_protocols
        ]
        pdf_buffer = create_pdf(report_content, "dashboard_report.pdf")
        st.download_button(
            label="Download PDF Report",
            data=pdf_buffer,
            file_name="dashboard_report.pdf",
            mime="application/pdf"
        )

def dilution_calculator_page():
    st.title("⚗️ Dilution Calculator")
    
    with st.expander("How to use this calculator"):
        st.markdown("""
        This calculator helps you prepare diluted solutions from stock solutions.
        
        1. Enter your stock solution concentration and volume
        2. Enter your desired final concentration and volume
        3. The calculator will determine how much stock solution and diluent you need
        
        You can also use it to calculate concentrations after serial dilutions.
        """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Simple Dilution Calculator")
        c1 = st.number_input("Stock Concentration (C1)", min_value=0.0, value=1.0, step=0.1)
        v1 = st.number_input("Volume to prepare (V2)", min_value=0.0, value=100.0, step=1.0)
        c2 = st.number_input("Desired Concentration (C2)", min_value=0.0, value=0.1, step=0.01)
        
        if c1 > 0 and v1 > 0 and c2 > 0:
            v2 = (c2 * v1) / c1
            st.markdown(f"""
            **Dilution Instructions:**
            - Take **{v2:.2f}** units of stock solution
            - Add **{(v1 - v2):.2f}** units of diluent
            - Total volume will be **{v1:.2f}** units at **{c2:.2f}** concentration
            
            *Dilution factor: {c1/c2:.2f}-fold*
            """)
    
    with col2:
        st.subheader("Serial Dilution Calculator")
        initial_conc = st.number_input("Initial Concentration", min_value=0.0, value=10.0, step=1.0)
        dilution_factor = st.number_input("Dilution Factor", min_value=1.1, value=2.0, step=0.1)
        num_dilutions = st.number_input("Number of Dilutions", min_value=1, max_value=10, value=5, step=1)
        final_volume = st.number_input("Final Volume per Dilution", min_value=1.0, value=100.0, step=1.0)
        
        if st.button("Calculate Serial Dilutions"):
            concentrations = []
            volumes = []
            
            current_conc = initial_conc
            for i in range(num_dilutions):
                concentrations.append(current_conc)
                v_stock = final_volume / dilution_factor
                volumes.append(v_stock)
                current_conc = current_conc / dilution_factor
            
            df = pd.DataFrame({
                "Step": range(1, num_dilutions + 1),
                "Concentration": concentrations,
                "Stock Volume": volumes,
                "Diluent Volume": [final_volume - v for v in volumes]
            })
            
            st.dataframe(df)
            
            fig = px.line(df, x="Step", y="Concentration", 
                         title="Serial Dilution Concentration Curve",
                         markers=True, log_y=True)
            st.plotly_chart(fig)
            
            st.markdown(get_table_download_link(df, "serial_dilution.csv"), unsafe_allow_html=True)

def solution_preparation_page():
    st.title("Solution Preparation Helper")
    
    method = st.radio("Preparation Method", 
                     ["From Solid", "From Liquid Stock", "By Molarity"])
    
    if method == "From Solid":
        st.subheader("Prepare Solution from Solid")
        
        col1, col2 = st.columns(2)
        
        with col1:
            formula_weight = st.number_input("Formula Weight (g/mol)", min_value=0.01, value=58.44)
            desired_volume = st.number_input("Desired Volume (L)", min_value=0.001, value=1.0, step=0.1)
        
        with col2:
            desired_conc = st.number_input("Desired Concentration (M)", min_value=0.001, value=0.1, step=0.01)
            purity = st.number_input("Purity (%)", min_value=0.1, max_value=100.0, value=100.0, step=0.1)
        
        if st.button("Calculate"):
            mass = (desired_conc * desired_volume * formula_weight) / (purity / 100)
            st.success(f"""
            **Preparation Instructions:**
            
            1. Weigh out **{mass:.4f} g** of the compound
            2. Add to a volumetric flask
            3. Add solvent to **{desired_volume} L** mark
            
            *Final concentration will be {desired_conc} M*
            """)
    
    elif method == "From Liquid Stock":
        st.subheader("Prepare Solution from Liquid Stock")
        
        col1, col2 = st.columns(2)
        
        with col1:
            stock_conc = st.number_input("Stock Concentration (M)", min_value=0.001, value=1.0, step=0.1)
            desired_conc = st.number_input("Desired Concentration (M)", min_value=0.001, value=0.1, step=0.01)
        
        with col2:
            desired_volume = st.number_input("Desired Volume (L)", min_value=0.001, value=1.0, step=0.1)
            stock_density = st.number_input("Stock Density (g/mL)", min_value=0.1, value=1.0, step=0.1)
        
        if st.button("Calculate"):
            volume_stock = (desired_conc * desired_volume) / stock_conc
            mass_stock = volume_stock * 1000 * stock_density  # Convert L to mL and multiply by density
            
            st.success(f"""
            **Preparation Instructions:**
            
            1. Measure **{volume_stock:.4f} L** ({volume_stock*1000:.2f} mL) of stock solution
            2. Add to a volumetric flask
            3. Add solvent to **{desired_volume} L** mark
            
            *This contains {mass_stock:.2f} g of solute*
            """)
    
    elif method == "By Molarity":
        st.subheader("Prepare Solution by Molarity")
        
        col1, col2 = st.columns(2)
        
        with col1:
            formula_weight = st.number_input("Formula Weight (g/mol)", min_value=0.01, value=58.44)
            desired_molarity = st.number_input("Desired Molarity (M)", min_value=0.001, value=0.1, step=0.01)
        
        with col2:
            desired_volume = st.number_input("Desired Volume (L)", min_value=0.001, value=1.0, step=0.1)
            percent_purity = st.number_input("Purity (%)", min_value=0.1, max_value=100.0, value=100.0, step=0.1)
        
        if st.button("Calculate"):
            mass_needed = (desired_molarity * desired_volume * formula_weight) / (percent_purity / 100)
            
            st.success(f"""
            **Preparation Instructions:**
            
            1. Weigh out **{mass_needed:.4f} g** of the compound
            2. Dissolve in **{desired_volume} L** of solvent
            
            *Final concentration will be {desired_molarity} M*
            """)

def buffer_composition_page():
    st.title("🧪 Buffer Composition Helper")
    
    buffer_type = st.selectbox("Select Buffer Type", 
                             ["Tris", "Phosphate", "Acetate", "HEPES", "MOPS", "Custom"])
    
    if buffer_type == "Tris":
        st.subheader("Tris Buffer Preparation")
        
        col1, col2 = st.columns(2)
        
        with col1:
            desired_ph = st.slider("Desired pH", 7.0, 9.0, 8.0, 0.1)
            concentration = st.number_input("Concentration (M)", min_value=0.01, value=0.1, step=0.01)
            volume = st.number_input("Volume (L)", min_value=0.01, value=1.0, step=0.1)
        
        with col2:
            temp = st.number_input("Temperature (°C)", min_value=0, value=25, step=1)
            salt = st.checkbox("Add NaCl", value=True)
            salt_conc = st.number_input("NaCl Concentration (M)", min_value=0.0, value=0.15, step=0.01) if salt else 0
        
        if st.button("Calculate Tris Buffer Composition"):
            tris_mass = 121.14 * concentration * volume
            hcl_vol = (8.0 - desired_ph) * 10  # Approximation
            
            st.success(f"""
            **Tris Buffer Preparation (pH {desired_ph}, {concentration} M):**
            
            1. Dissolve **{tris_mass:.2f} g** Tris base in **{volume*0.8:.2f} L** water
            2. Add ~**{hcl_vol:.1f} mL** concentrated HCl (adjust while monitoring pH)
            3. {"Add " + str(salt_conc * 58.44 * volume) + " g NaCl and " if salt else ""}adjust volume to **{volume} L** with water
            4. Check and fine-tune pH at **{temp}°C**
            
            *Tris has optimal buffering range pH 7.0-9.0*
            """)
    
    elif buffer_type == "Phosphate":
        st.subheader("Phosphate Buffer Preparation")
        
        col1, col2 = st.columns(2)
        
        with col1:
            desired_ph = st.slider("Desired pH", 5.8, 8.0, 7.4, 0.1)
            concentration = st.number_input("Concentration (M)", min_value=0.01, value=0.1, step=0.01)
            volume = st.number_input("Volume (L)", min_value=0.01, value=1.0, step=0.1)
        
        with col2:
            buffer_type = st.radio("Phosphate Type", ["Monobasic/Dibasic", "Dibasic/Tribasic"])
            nacl = st.checkbox("Add NaCl (for PBS)", value=True)
            kcl = st.checkbox("Add KCl (for PBS)", value=True)
        
        if st.button("Calculate Phosphate Buffer Composition"):
            if buffer_type == "Monobasic/Dibasic":
                # NaH2PO4 and Na2HPO4
                if desired_ph < 6.0:
                    ratio = 9.0
                elif desired_ph > 7.5:
                    ratio = 0.1
                else:
                    ratio = 10**(7.2 - desired_ph)  # Approximation
                
                total_moles = concentration * volume
                na2hpo4_moles = total_moles / (1 + ratio)
                nah2po4_moles = total_moles - na2hpo4_moles
                
                na2hpo4_mass = na2hpo4_moles * 141.96
                nah2po4_mass = nah2po4_moles * 119.98
                
                st.success(f"""
                **Phosphate Buffer Preparation (pH {desired_ph}, {concentration} M):**
                
                1. Dissolve **{na2hpo4_mass:.2f} g Na₂HPO₄** and **{nah2po4_mass:.2f} g NaH₂PO₄** in **{volume*0.8:.2f} L** water
                2. {"Add 8.77 g NaCl and 0.2 g KCl" if nacl and kcl else ""}
                3. Adjust volume to **{volume} L** with water
                4. Check and adjust pH if needed
                
                *Optimal buffering range pH 5.8-8.0*
                """)
    
    elif buffer_type == "Custom":
        st.subheader("Custom Buffer Preparation")
        
        col1, col2 = st.columns(2)
        
        with col1:
            components = st.text_area("Buffer Components (one per line)", 
                                    "Component1, MW, pKa\nComponent2, MW, pKa")
            desired_ph = st.number_input("Desired pH", min_value=0.0, max_value=14.0, value=7.4, step=0.1)
            ionic_strength = st.number_input("Ionic Strength (M)", min_value=0.0, value=0.1, step=0.01)
        
        with col2:
            total_conc = st.number_input("Total Buffer Concentration (M)", min_value=0.001, value=0.1, step=0.01)
            volume = st.number_input("Volume (L)", min_value=0.001, value=1.0, step=0.1)
            temp = st.number_input("Temperature (°C)", min_value=0, value=25, step=1)
        
        if st.button("Calculate Custom Buffer Composition"):
            try:
                # Parse components
                comp_lines = [line.strip() for line in components.split('\n') if line.strip()]
                comp_data = []
                for line in comp_lines[1:]:  # Skip header
                    name, mw, pka = [x.strip() for x in line.split(',')]
                    comp_data.append({
                        'name': name,
                        'mw': float(mw),
                        'pka': float(pka)
                    })
                
                if len(comp_data) == 2:
                    # Henderson-Hasselbalch approximation for 2 components
                    pka_diff = desired_ph - comp_data[0]['pka']
                    ratio = 10**pka_diff
                    
                    total_moles = total_conc * volume
                    acid_moles = total_moles / (1 + ratio)
                    base_moles = total_moles - acid_moles
                    
                    acid_mass = acid_moles * comp_data[0]['mw']
                    base_mass = base_moles * comp_data[1]['mw']
                    
                    st.success(f"""
                    **Custom Buffer Preparation (pH {desired_ph}, {total_conc} M):**
                    
                    1. Dissolve **{acid_mass:.2f} g {comp_data[0]['name']}** and **{base_mass:.2f} g {comp_data[1]['name']}** in **{volume*0.8:.2f} L** water
                    2. Adjust ionic strength to {ionic_strength} M with salt if needed
                    3. Adjust volume to **{volume} L** with water
                    4. Check and fine-tune pH at **{temp}°C**
                    """)
                else:
                    st.warning("Currently only supports two-component buffers. For complex buffers, please use specialized software.")
            
            except Exception as e:
                st.error(f"Error calculating buffer composition: {str(e)}")

def lab_planner_page():
    st.title("📅 Lab Planner & Event Manager")
    
    tab1, tab2, tab3 = st.tabs(["Add New Task", "View Tasks", "Calendar View"])
    
    with tab1:
        with st.form("Task Form"):
            title = st.text_input("Task Title")
            description = st.text_area("Description")
            
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", datetime.now())
                frequency = st.selectbox("Frequency", ["One-time", "Daily", "Weekly", "Monthly"])
            with col2:
                end_date = st.date_input("End Date", datetime.now() + timedelta(days=1))
                event_type = st.selectbox("Task Type", ["Experiment", "Meeting", "Maintenance", "Order", "Other"])
            
            submit = st.form_submit_button("Add Task")
            
            if submit:
                conn = sqlite3.connect('lab_manager.db')
                c = conn.cursor()
                c.execute("INSERT INTO events (title, description, start_date, end_date, event_type, frequency, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (title, description, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), event_type, frequency, st.session_state.user['username']))
                conn.commit()
                conn.close()
                st.success("Task added successfully!")
    
    with tab2:
        view_option = st.radio("View Tasks", ["All", "Pending", "Completed", "By Type"])
        
        conn = sqlite3.connect('lab_manager.db')
        
        if view_option == "All":
            tasks = pd.read_sql("SELECT * FROM events ORDER BY start_date", conn)
        elif view_option == "Pending":
            tasks = pd.read_sql("SELECT * FROM events WHERE completed = 0 ORDER BY start_date", conn)
        elif view_option == "Completed":
            tasks = pd.read_sql("SELECT * FROM events WHERE completed = 1 ORDER BY start_date", conn)
        elif view_option == "By Type":
            event_type = st.selectbox("Select Task Type", ["Experiment", "Meeting", "Maintenance", "Order", "Other"])
            tasks = pd.read_sql(f"SELECT * FROM events WHERE event_type = '{event_type}' ORDER BY start_date", conn)
        
        if not tasks.empty:
            st.dataframe(tasks)
            
            # Task management
            selected_task = st.selectbox("Select Task to Manage", tasks['title'])
            task_id = tasks[tasks['title'] == selected_task]['id'].values[0]
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Mark as Completed"):
                    c = conn.cursor()
                    c.execute("UPDATE events SET completed = 1 WHERE id = ?", (task_id,))
                    conn.commit()
                    st.success("Task marked as completed!")
                    st.rerun()
            with col2:
                if st.button("Delete Task"):
                    c = conn.cursor()
                    c.execute("DELETE FROM events WHERE id = ?", (task_id,))
                    conn.commit()
                    st.success("Task deleted!")
                    st.rerun()
            
            st.markdown(get_table_download_link(tasks, "lab_tasks.csv"), unsafe_allow_html=True)
        else:
            st.info("No tasks found")
        
        conn.close()
    
    with tab3:
        st.subheader("Calendar View")
        conn = sqlite3.connect('lab_manager.db')
        events = pd.read_sql("""
            SELECT id, title, start_date, end_date, event_type, completed 
            FROM events 
            WHERE date(end_date) >= date('now', '-1 month')
            ORDER BY start_date
        """, conn)
        conn.close()
        
        if not events.empty:
            # Create a calendar-like display
            min_date = pd.to_datetime(events['start_date']).min().date()
            max_date = pd.to_datetime(events['end_date']).max().date()
            
            # Create a date range for the calendar
            date_range = pd.date_range(min_date, max_date)
            
            # Create a calendar dataframe
            calendar_df = pd.DataFrame(index=date_range, columns=["Events"])
            
            for date in date_range:
                day_events = events[
                    (pd.to_datetime(events['start_date']) <= date) & 
                    (pd.to_datetime(events['end_date']) >= date)
                ]
                if not day_events.empty:
                    calendar_df.loc[date, "Events"] = "<br>".join(
                        f"{row['title']} ({row['event_type']})" 
                        for _, row in day_events.iterrows()
                    )
            
            # Display the calendar
            st.markdown("### Lab Calendar")
            for date, row in calendar_df.iterrows():
                if pd.notna(row["Events"]):
                    with st.expander(f"{date.strftime('%A, %B %d, %Y')}"):
                        st.markdown(row["Events"], unsafe_allow_html=True)
        else:
            st.info("No upcoming events in the calendar")

def protocol_generator_page():
    st.title("📋 Experiment Protocol Generator")
    
    tab1, tab2 = st.tabs(["Create Protocol", "Protocol Library"])
    
    with tab1:
        with st.form("Protocol Form"):
            title = st.text_input("Protocol Title")
            protocol_type = st.selectbox("Protocol Type", 
                                       ["DNA/RNA", "Protein", "Cell Culture", "Biochemistry", "Other"])
            
            description = st.text_area("Brief Description")
            steps = st.text_area("Detailed Steps (one step per line)", 
                               "Step 1: Prepare materials\nStep 2: ...")
            
            submit = st.form_submit_button("Save Protocol")
            
            if submit:
                conn = sqlite3.connect('lab_manager.db')
                c = conn.cursor()
                c.execute("""
                    INSERT INTO protocols (title, protocol_type, description, steps, created_by, created_date, last_modified)
                    VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """, (title, protocol_type, description, steps, st.session_state.user['username']))
                conn.commit()
                conn.close()
                st.success("Protocol saved successfully!")
    
    with tab2:
        search_term = st.text_input("Search Protocols")
        filter_type = st.selectbox("Filter by Type", ["All"] + ["DNA/RNA", "Protein", "Cell Culture", "Biochemistry", "Other"])
        
        conn = sqlite3.connect('lab_manager.db')
        
        query = "SELECT * FROM protocols"
        conditions = []
        if search_term:
            conditions.append(f"(title LIKE '%{search_term}%' OR description LIKE '%{search_term}%')")
        if filter_type != "All":
            conditions.append(f"protocol_type = '{filter_type}'")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY created_date DESC"
        
        protocols = pd.read_sql(query, conn)
        
        if not protocols.empty:
            selected_protocol = st.selectbox("Select Protocol", protocols['title'])
            protocol_details = protocols[protocols['title'] == selected_protocol].iloc[0]
            
            st.subheader(protocol_details['title'])
            st.markdown(f"**Type:** {protocol_details['protocol_type']}")
            st.markdown(f"**Created by:** {protocol_details['created_by']} on {protocol_details['created_date']}")
            
            st.markdown("### Description")
            st.write(protocol_details['description'])
            
            st.markdown("### Protocol Steps")
            steps = protocol_details['steps'].split('\n')
            for i, step in enumerate(steps, 1):
                st.markdown(f"{i}. {step}")
            
            # Export options
            st.markdown("### Export Protocol")
            if st.button("Generate PDF"):
                report_content = [
                    f"Protocol: {protocol_details['title']}",
                    f"Type: {protocol_details['protocol_type']}",
                    f"Created by: {protocol_details['created_by']} on {protocol_details['created_date']}",
                    "\nDescription:",
                    protocol_details['description'],
                    "\nProtocol Steps:"
                ]
                report_content.extend(steps)
                
                pdf_buffer = create_pdf(report_content, f"{protocol_details['title']}_protocol.pdf")
                st.download_button(
                    label="Download PDF",
                    data=pdf_buffer,
                    file_name=f"{protocol_details['title']}_protocol.pdf",
                    mime="application/pdf"
                )
            
            st.markdown(get_table_download_link(pd.DataFrame([protocol_details]), f"{protocol_details['title']}_protocol.csv"), unsafe_allow_html=True)
        else:
            st.info("No protocols found")
        
        conn.close()

def reagent_tracker_page():
    st.title("🏷️ Reagent Inventory Tracker")
    
    tab1, tab2, tab3 = st.tabs(["Add Reagent", "View Inventory", "Expiry Alerts"])
    
    with tab1:
        with st.form("Reagent Form"):
            col1, col2 = st.columns(2)
            
            with col1:
                name = st.text_input("Reagent Name")
                cas_number = st.text_input("CAS Number")
                supplier = st.text_input("Supplier")
                quantity = st.number_input("Quantity", min_value=0.0, value=1.0, step=0.1)
                unit = st.selectbox("Unit", ["g", "mg", "L", "mL", "µL", "pcs"])
            
            with col2:
                concentration = st.number_input("Concentration", min_value=0.0, value=1.0, step=0.1)
                concentration_unit = st.text_input("Concentration Unit", value="M")
                location = st.text_input("Storage Location")
                date_received = st.date_input("Date Received", datetime.now())
                expiry_date = st.date_input("Expiry Date", datetime.now() + timedelta(days=365))
                hazard_class = st.selectbox("Hazard Class", 
                                           ["None", "Flammable", "Corrosive", "Toxic", "Health Hazard", "Environmental Hazard"])
            
            submit = st.form_submit_button("Add Reagent")
            
            if submit:
                conn = sqlite3.connect('lab_manager.db')
                c = conn.cursor()
                c.execute("""
                    INSERT INTO reagents 
                    (name, cas_number, supplier, quantity, unit, concentration, concentration_unit, 
                    location, date_received, expiry_date, hazard_class, owner)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, cas_number, supplier, quantity, unit, concentration, concentration_unit,
                     location, date_received.strftime("%Y-%m-%d"), expiry_date.strftime("%Y-%m-%d"), 
                     hazard_class, st.session_state.user['username']))
                conn.commit()
                conn.close()
                st.success("Reagent added to inventory!")
    
    with tab2:
        search_term = st.text_input("Search Reagents")
        
        conn = sqlite3.connect('lab_manager.db')
        
        query = "SELECT * FROM reagents"
        if search_term:
            query += f" WHERE name LIKE '%{search_term}%' OR cas_number LIKE '%{search_term}%'"
        
        query += " ORDER BY name"
        
        reagents = pd.read_sql(query, conn)
        
        if not reagents.empty:
            st.dataframe(reagents)
            
            # Reagent usage tracking
            selected_reagent = st.selectbox("Select Reagent to Update", reagents['name'])
            reagent_id = reagents[reagents['name'] == selected_reagent]['id'].values[0]
            
            with st.form("Update Reagent"):
                new_quantity = st.number_input("Update Quantity", 
                                             min_value=0.0, 
                                             value=float(reagents[reagents['name'] == selected_reagent]['quantity'].values[0]),
                                             step=0.1)
                update_reason = st.text_input("Reason for Update (optional)")
                
                submit_update = st.form_submit_button("Update Quantity")
                
                if submit_update:
                    c = conn.cursor()
                    c.execute("UPDATE reagents SET quantity = ? WHERE id = ?", (new_quantity, reagent_id))
                    conn.commit()
                    st.success("Quantity updated!")
                    st.rerun()
            
            st.markdown(get_table_download_link(reagents, "reagent_inventory.csv"), unsafe_allow_html=True)
        else:
            st.info("No reagents found in inventory")
        
        conn.close()
    
    with tab3:
        st.subheader("Reagents Nearing Expiry")
        conn = sqlite3.connect('lab_manager.db')
        
        # Reagents expiring in next 30 days
        expiring_soon = pd.read_sql("""
            SELECT name, quantity, unit, expiry_date, location 
            FROM reagents 
            WHERE date(expiry_date) BETWEEN date('now') AND date('now', '+30 days')
            ORDER BY expiry_date
        """, conn)
        
        if not expiring_soon.empty:
            st.warning(f"{len(expiring_soon)} reagents expiring in the next 30 days!")
            st.dataframe(expiring_soon)
            
            # Visualization
            expiring_soon['days_to_expiry'] = (pd.to_datetime(expiring_soon['expiry_date']) - pd.Timestamp.now()).dt.days
            fig = px.bar(expiring_soon, x='name', y='days_to_expiry', 
                         color='days_to_expiry',
                         title="Days Until Reagent Expiry",
                         labels={'name': 'Reagent', 'days_to_expiry': 'Days Until Expiry'})
            st.plotly_chart(fig)
        else:
            st.info("No reagents expiring in the next 30 days")
        
        # Low quantity reagents
        low_quantity = pd.read_sql("""
            SELECT name, quantity, unit, location 
            FROM reagents 
            WHERE quantity < 5
            ORDER BY quantity
        """, conn)
        
        if not low_quantity.empty:
            st.warning(f"{len(low_quantity)} reagents with low quantity!")
            st.dataframe(low_quantity)
        else:
            st.info("No reagents with critically low quantity")
        
        conn.close()

def data_visualizer_page():
    st.title("📈Experiment Data Visualizer")
    
    # File upload
    uploaded_file = st.file_uploader("Upload your experimental data (CSV or Excel)", 
                                   type=['csv', 'xlsx'])
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.success("Data loaded successfully!")
            st.dataframe(df.head())
            
            # Data visualization options
            st.subheader("Visualization Options")
            
            plot_type = st.selectbox("Select Plot Type", 
                                   ["Line Plot", "Scatter Plot", "Bar Plot", "Histogram", "Box Plot", "Violin Plot"])
            
            col1, col2 = st.columns(2)
            
            with col1:
                x_axis = st.selectbox("X-axis", df.columns)
                y_axis = st.selectbox("Y-axis", df.columns) if plot_type != "Histogram" else None
                color_by = st.selectbox("Color by", [None] + list(df.columns))
            
            with col2:
                if plot_type in ["Scatter Plot", "Line Plot"]:
                    trendline = st.checkbox("Add trendline")
                else:
                    trendline = False
                
                if plot_type == "Histogram":
                    bins = st.slider("Number of bins", 5, 100, 20)
                else:
                    bins = None
            
            # Generate plot
            if st.button("Generate Plot"):
                try:
                    if plot_type == "Line Plot":
                        fig = px.line(df, x=x_axis, y=y_axis, color=color_by, 
                                     title=f"{y_axis} vs {x_axis}")
                        if trendline:
                            fig.update_traces(mode='markers+lines')
                    elif plot_type == "Scatter Plot":
                        fig = px.scatter(df, x=x_axis, y=y_axis, color=color_by,
                                       title=f"{y_axis} vs {x_axis}")
                        if trendline:
                            fig.update_traces(mode='markers')
                            fig.add_traces(px.scatter(df, x=x_axis, y=y_axis, trendline="ols").data[1:])
                    elif plot_type == "Bar Plot":
                        fig = px.bar(df, x=x_axis, y=y_axis, color=color_by,
                                   title=f"{y_axis} by {x_axis}")
                    elif plot_type == "Histogram":
                        fig = px.histogram(df, x=x_axis, color=color_by,
                                         nbins=bins, title=f"Distribution of {x_axis}")
                    elif plot_type == "Box Plot":
                        fig = px.box(df, x=x_axis, y=y_axis, color=color_by,
                                   title=f"Box Plot of {y_axis} by {x_axis}")
                    elif plot_type == "Violin Plot":
                        fig = px.violin(df, x=x_axis, y=y_axis, color=color_by,
                                       title=f"Violin Plot of {y_axis} by {x_axis}")
                    
                    st.plotly_chart(fig)
                    
                    # Export options
                    st.markdown("### Export Options")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown(get_table_download_link(df, "processed_data.csv"), unsafe_allow_html=True)
                    
                    with col2:
                        plot_filename = st.text_input("Plot filename", value="experiment_plot.html")
                        if st.button("Export Plot"):
                            fig.write_html(plot_filename)
                            st.success(f"Plot saved as {plot_filename}")
                
                except Exception as e:
                    st.error(f"Error generating plot: {str(e)}")
        
        except Exception as e:
            st.error(f"Error loading file: {str(e)}")
    else:
        st.info("Please upload your experimental data file to begin visualization")

def help_page():
    st.title("📝 Biochemistry Help Section")
    
    topic = st.selectbox("Select a Topic", 
                        ["Buffer Preparation", "Molarity Calculations", 
                         "Dilution Techniques", "Lab Safety", "Common Protocols"])
    
    if topic == "Buffer Preparation":
        st.markdown("""
        ### Buffer Preparation Guidelines
        
        **What is a buffer?**
        A buffer is a solution that resists changes in pH when small amounts of acid or base are added.
        
        **Key Concepts:**
        - **pKa**: The pH at which the acid and conjugate base are in equal concentrations
        - **Buffering capacity**: The amount of acid/base a buffer can neutralize before pH changes significantly
        - **Optimal range**: Buffers are most effective within ±1 pH unit of their pKa
        
        **Common Biological Buffers:**
        
        | Buffer | pKa (25°C) | Effective pH Range |
        |--------|-----------|--------------------|
        | Acetate | 4.76 | 3.8-5.8 |
        | Citrate | 3.13, 4.76, 6.40 | 3.0-6.2 |
        | Phosphate | 2.15, 7.20, 12.33 | 5.8-8.0 |
        | Tris | 8.06 | 7.0-9.0 |
        | HEPES | 7.48 | 6.8-8.2 |
        """)
        
        st.image("https://www.aatbio.com/uploads/media-library/Biological-buffers-table.png", 
                caption="Common biological buffers and their properties", width=600)
    
    elif topic == "Molarity Calculations":
        st.markdown("""
        ### Molarity Calculations
        
        **Molarity (M)** is defined as the number of moles of solute per liter of solution.
        
        **Formula:**
        ```
        Molarity (M) = moles of solute / liters of solution
        ```
        
        **Calculating mass from molarity:**
        ```
        mass (g) = molarity (M) × volume (L) × molecular weight (g/mol)
        ```
        
        **Example:**
        To prepare 500 mL of 0.5 M NaCl solution:
        - Molecular weight of NaCl = 58.44 g/mol
        - Volume = 0.5 L
        - Mass = 0.5 M × 0.5 L × 58.44 g/mol = 14.61 g
        
        **Temperature Considerations:**
        - Molarity is temperature-dependent because volume changes with temperature
        - For precise work, prepare solutions at the temperature they'll be used
        """)
    
    elif topic == "Dilution Techniques":
        st.markdown("""
        ### Dilution Techniques
        
        **Dilution Formula:**
        ```
        C₁V₁ = C₂V₂
        Where:
        C₁ = initial concentration
        V₁ = initial volume
        C₂ = final concentration
        V₂ = final volume
        ```
        
        **Serial Dilutions:**
        1. Prepare a series of tubes with equal volumes of diluent
        2. Transfer a fixed volume from stock to first tube (e.g., 1:10 dilution)
        3. Mix well, then transfer same volume from first tube to next
        4. Repeat for desired number of dilutions
        
        **Advantages:**
        - Allows creation of very dilute solutions from concentrated stocks
        - More accurate than attempting large single dilutions
        - Common in microbiology, ELISA, PCR
        
        **Example Serial Dilution Scheme:**
        """)
        
        # Create example serial dilution table
        df = pd.DataFrame({
            "Tube": [1, 2, 3, 4, 5],
            "Dilution": ["1:10", "1:100", "1:1,000", "1:10,000", "1:100,000"],
            "Concentration (M)": [1.0, 0.1, 0.01, 0.001, 0.0001]
        })
        st.table(df)
    
    elif topic == "Lab Safety":
        st.markdown("""
        ### Laboratory Safety Guidelines
        
        **General Rules:**
        1. Always wear appropriate PPE (lab coat, gloves, eye protection)
        2. Know emergency procedures (eyewash, shower, fire extinguisher locations)
        3. Never work alone in the lab
        4. Label all containers with contents, concentration, date, and hazards
        
        **Chemical Safety:**
        - Consult SDS (Safety Data Sheets) before using any chemical
        - Use fume hood for volatile or toxic substances
        - Never return unused chemicals to stock bottles
        
        **Biological Safety:**
        - Follow appropriate biosafety level (BSL) procedures
        - Autoclave all biohazardous waste
        - Disinfect work surfaces before and after use
        
        **Waste Disposal:**
        - Separate chemical, biological, and sharps waste
        - Use designated containers for each waste type
        - Never pour chemicals down the drain unless approved
        """)
    
    elif topic == "Common Protocols":
        st.markdown("""
        ### Common Biochemistry Protocols
        
        **Protein Quantification (Bradford Assay):**
        1. Prepare protein standards (BSA 0-2000 µg/mL)
        2. Add Bradford reagent to samples and standards
        3. Incubate 5-10 minutes at room temperature
        4. Measure absorbance at 595 nm
        5. Generate standard curve and calculate protein concentration
        
        **DNA Extraction (Phenol-Chloroform):**
        1. Lyse cells in appropriate buffer
        2. Add phenol:chloroform:isoamyl alcohol (25:24:1)
        3. Centrifuge to separate phases
        4. Transfer aqueous phase (contains DNA)
        5. Precipitate DNA with ethanol
        6. Wash pellet with 70% ethanol
        7. Resuspend in TE buffer or water
        
        **SDS-PAGE:**
        1. Prepare acrylamide gel (appropriate % for protein size)
        2. Load samples (mix with loading buffer)
        3. Run gel at constant voltage (100-200V)
        4. Stain with Coomassie or transfer for Western blot
        """)

# Main app
def main():
    st.set_page_config(
        page_title="Biochemistry Lab Manager",
        page_icon=":microscope:",
        layout="wide"
    )
    
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "Login"
    
    # Sidebar navigation
    if st.session_state.get('logged_in', False):
        with st.sidebar:
            st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Alpha_helix_transparent.png/800px-Alpha_helix_transparent.png", 
                   width=150)
            st.title(f"Welcome, {st.session_state.user['full_name']}")
            
            menu = option_menu(
                None,
                ["Dashboard", "Dilution Calculator", "Solution Preparation", 
                 "Buffer Helper", "Lab Planner", "Protocol Generator", 
                 "Reagent Tracker", "Data Visualizer", "Help"],
                icons=['speedometer', 'calculator', 'droplet', 
                      'eyedropper', 'calendar', 'file-text', 
                      'box-seam', 'graph-up', 'question-circle'],
                default_index=0
            )
            
            st.session_state.current_page = menu
            
            st.markdown("---")
            if st.button("Logout"):
                st.session_state.logged_in = False
                st.session_state.user = None
                st.session_state.current_page = "Login"
                st.rerun()
    
    # Page routing
    if st.session_state.current_page == "Login":
        login_page()
    elif st.session_state.current_page == "Dashboard":
        dashboard_page()
    elif st.session_state.current_page == "Dilution Calculator":
        dilution_calculator_page()
    elif st.session_state.current_page == "Solution Preparation":
        solution_preparation_page()
    elif st.session_state.current_page == "Buffer Helper":
        buffer_composition_page()
    elif st.session_state.current_page == "Lab Planner":
        lab_planner_page()
    elif st.session_state.current_page == "Protocol Generator":
        protocol_generator_page()
    elif st.session_state.current_page == "Reagent Tracker":
        reagent_tracker_page()
    elif st.session_state.current_page == "Data Visualizer":
        data_visualizer_page()
    elif st.session_state.current_page == "Help":
        help_page()

if __name__ == "__main__":
    main()
