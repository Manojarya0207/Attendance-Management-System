from flask import Flask, render_template_string, request, redirect, url_for, send_file, flash
import csv, os, re, io
from datetime import date, datetime
import speech_recognition as sr
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = "secret123"

STUDENTS_FILE = "students.csv"
ATTENDANCE_FILE = "attendance.csv"

# Ensure CSV files exist
if not os.path.exists(STUDENTS_FILE):
    with open(STUDENTS_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Class", "RollNo"])

if not os.path.exists(ATTENDANCE_FILE):
    with open(ATTENDANCE_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Name", "Class", "RollNo", "Status"])

# ----------------- UTILITIES -----------------
def load_students():
    with open(STUDENTS_FILE, newline="") as f:
        return list(csv.DictReader(f))

def save_attendance(on_date, rollno, status):
    rows = []
    with open(ATTENDANCE_FILE, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    updated = False
    for r in rows:
        if r["Date"] == on_date and r["RollNo"] == rollno:
            r["Status"] = status
            updated = True

    if not updated:
        for s in load_students():
            if s["RollNo"] == rollno:
                rows.append({
                    "Date": on_date, "Name": s["Name"], "Class": s["Class"],
                    "RollNo": s["RollNo"], "Status": status
                })

    with open(ATTENDANCE_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Name", "Class", "RollNo", "Status"])
        writer.writeheader()
        writer.writerows(rows)

def load_attendance(on_date):
    data = []
    students = load_students()
    with open(ATTENDANCE_FILE, newline="") as f:
        rows = list(csv.DictReader(f))
    for s in students:
        found = [r for r in rows if r["Date"] == on_date and r["RollNo"] == s["RollNo"]]
        if found:
            data.append(found[0])
        else:
            data.append({"Date": on_date, "Name": s["Name"], "Class": s["Class"], "RollNo": s["RollNo"], "Status": "Not Marked"})
    return data

def get_month_report(month, year):
    report = {}
    with open(ATTENDANCE_FILE, newline="") as f:
        for r in csv.DictReader(f):
            try:
                d = datetime.strptime(r["Date"], "%Y-%m-%d")
            except:
                continue
            if d.month == month and d.year == year:
                key = (r["Name"], r["Class"])
                if key not in report:
                    report[key] = {"Name": r["Name"], "Class": r["Class"], "Present": 0, "Absent": 0, "Unclear": 0}
                if r["Status"] == "Present":
                    report[key]["Present"] += 1
                elif r["Status"] == "Absent":
                    report[key]["Absent"] += 1
                else:
                    report[key]["Unclear"] += 1
    return report

def get_month_details(month, year):
    details = []
    with open(ATTENDANCE_FILE, newline="") as f:
        for r in csv.DictReader(f):
            try:
                d = datetime.strptime(r["Date"], "%Y-%m-%d")
            except:
                continue
            if d.month == month and d.year == year:
                details.append(r)
    return details

def parse_month_year_from_query():
    today = date.today()
    month = request.args.get("month", type=int) or today.month
    year = request.args.get("year", type=int) or today.year
    return month, year

# ----------------- NLP COMMAND HANDLER -----------------
def process_nlp_command(query):
    query = query.lower()

    # Add Student
    match = re.search(r"add student (\w+) class (\w+) roll (\d+)", query)
    if match:
        name, cls, roll = match.groups()
        with open(STUDENTS_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([name.capitalize(), cls.upper(), roll])
        return False, f"✅ Student {name} added successfully (via NLP)!"

    # Mark Attendance
    match = re.search(r"mark (\w+) (present|absent|unclear)", query)
    if match:
        name, status = match.groups()
        today = str(date.today())
        students = load_students()
        roll = None
        for s in students:
            if s["Name"].lower() == name.lower():
                roll = s["RollNo"]
                break
        if roll:
            save_attendance(today, roll, status.capitalize())
            return False, f"✅ Attendance marked for {name} ({status}) via NLP!"
        else:
            return False, f"❌ Student {name} not found"

    # Show Report
    match = re.search(r"show report for (\w+)", query)
    if match:
        month_name = match.group(1).capitalize()
        try:
            month_num = datetime.strptime(month_name, "%B").month
            today = date.today()
            report = get_month_report(month_num, today.year)
            details = get_month_details(month_num, today.year)
            return True, render_template_string(MONTH_TEMPLATE, report=report, details=details, month=month_name, month_num=month_num, year=today.year)
        except:
            return False, "❌ Could not understand month in report query"
    
    # New NLP features
    if query == "show students":
        students = load_students()
        if not students:
            return False, "❌ No students found."
        html_list = f"""
        <h3>All Students:</h3>
        <div class="search-container">
            <input type="text" id="studentSearch" placeholder="Search for students..." onkeyup="filterStudents()">
            <span class="search-icon">🔍</span>
        </div>
        <ul id="studentList">
        """
        for s in students:
            html_list += f"<li>{s['Name']} (Class: {s['Class']}, Roll: {s['RollNo']})</li>"
        html_list += """
        </ul>
        <script>
        function filterStudents() {
            const input = document.getElementById('studentSearch');
            const filter = input.value.toLowerCase();
            const ul = document.getElementById('studentList');
            const li = ul.getElementsByTagName('li');
            for (let i = 0; i < li.length; i++) {
                const text = li[i].textContent || li[i].innerText;
                if (text.toLowerCase().indexOf(filter) > -1) {
                    li[i].style.display = "";
                } else {
                    li[i].style.display = "none";
                }
            }
        }
        </script>
        """
        return True, html_list

    match = re.search(r" (\d{4}-\d{2}-\d{2})", query)
    if match:
        date_str = match.group(1)
        records = load_attendance(date_str)
        html_table = f"<h3>Attendance for {date_str}:</h3><table><thead><tr><th>Name</th><th>Status</th></tr></thead><tbody>"
        for r in records:
            html_table += f"<tr><td>{r['Name']}</td><td>{r['Status']}</td></tr>"
        html_table += "</tbody></table>"
        return True, html_table

    match = re.search(r"delete student (\w+)", query)
    if match:
        name = match.group(1)
        students = load_students()
        student_to_delete = next((s for s in students if s['Name'].lower() == name.lower()), None)
        if student_to_delete:
            new_students = [s for s in students if s["Name"].lower() != name.lower()]
            with open(STUDENTS_FILE, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Name", "Class", "RollNo"])
                writer.writeheader()
                writer.writerows(new_students)
            return False, f"🗑️ Student {name} deleted successfully via NLP!"
        else:
            return False, f"❌ Student {name} not found."
    
    # New command to remove all students
    if query == "remove all students":
        with open(STUDENTS_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Class", "RollNo"])
        return False, "🗑️ All students have been removed."

    match = re.search(r"add class (\w+)", query)
    if match:
        file_path = match.group(1) + ".csv"
        if not os.path.exists(file_path):
            return False, f"❌ CSV file '{file_path}' not found."
        with open(file_path, newline="") as f:
            reader = csv.reader(f)
            new_students = list(reader)
        with open(STUDENTS_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(new_students)
        return False, f"✅ Students from class '{match.group(1)}' added successfully!"

    return False, "❌ Sorry, I could not understand your command"

# ----------------- ROUTES -----------------
@app.route("/")
def dashboard():
    today = str(date.today())
    records = load_attendance(today)
    nlp_text = request.args.get('nlp_text', None)
    return render_template_string(DASHBOARD_TEMPLATE, records=records, today=today, nlp_result="", nlp_text=nlp_text)

@app.route("/nlp_command", methods=["POST"])
def nlp_command():
    query = request.form.get("query", "")
    is_html, result = process_nlp_command(query)
    if is_html:
        today = str(date.today())
        records = load_attendance(today)
        return render_template_string(DASHBOARD_TEMPLATE, records=records, today=today, nlp_result=result, nlp_text=None)
    else:
        flash(result, "success" if "✅" in result or "🗑️" in result else "error")
        return redirect(url_for("dashboard"))

@app.route("/nlp_voice", methods=["POST"])
def nlp_voice():
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            audio = r.listen(source, timeout=5, phrase_time_limit=5)
        text = r.recognize_google(audio).lower()
        return redirect(url_for("dashboard", nlp_text=text))
    except Exception as e:
        flash(f"❌ Voice NLP error: {e}", "error")
        return redirect(url_for("dashboard"))

@app.route("/mark/<rollno>/<status>/<att_date>")
def mark_attendance(rollno, status, att_date):
    save_attendance(att_date, rollno, status)
    flash(f"✅ Attendance marked as {status} for RollNo {rollno}", "success")
    return redirect(url_for("dashboard"))

@app.route("/add_student", methods=["POST"])
def add_student():
    name = request.form["name"]
    cls = request.form["class"]
    rollno = request.form["rollno"]
    with open(STUDENTS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([name, cls, rollno])
    flash(f"✅ Student {name} added successfully!", "success")
    return redirect(url_for("dashboard"))

@app.route("/delete_student/<rollno>")
def delete_student(rollno):
    students = load_students()
    students = [s for s in students if s["RollNo"] != rollno]
    with open(STUDENTS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Name", "Class", "RollNo"])
        writer.writeheader()
        writer.writerows(students)
    flash(f"🗑️ Student RollNo {rollno} deleted", "success")
    return redirect(url_for("dashboard"))

@app.route("/month_report")
def month_report():
    today = date.today()
    report = get_month_report(today.month, today.year)
    details = get_month_details(today.month, today.year)
    return render_template_string(MONTH_TEMPLATE, report=report, details=details, month=today.strftime("%B"), month_num=today.month, year=today.year)

# ---------- Downloads ----------
@app.route("/download_csv")
def download_csv():
    month, year = parse_month_year_from_query()
    report = get_month_report(month, year)
    details = get_month_details(month, year)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Summary for", datetime(year, month, 1).strftime("%B %Y")])
    writer.writerow(["Name", "Class", "Present", "Absent", "Unclear"])
    for r in report.values():
        writer.writerow([r["Name"], r["Class"], r["Present"], r["Absent"], r["Unclear"]])
    writer.writerow([])
    writer.writerow(["Detailed Records"])
    writer.writerow(["Date", "Name", "Class", "RollNo", "Status"])
    for d in details:
        writer.writerow([d["Date"], d["Name"], d["Class"], d["RollNo"], d["Status"]])

    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    mem.seek(0)
    filename = f"attendance_{year}_{month:02d}.csv"
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=filename)

@app.route("/download_pdf")
def download_pdf():
    month, year = parse_month_year_from_query()
    report = get_month_report(month, year)
    details = get_month_details(month, year)

    mem = io.BytesIO()
    doc = SimpleDocTemplate(mem, pagesize=A4)
    elems = []
    styles = getSampleStyleSheet()

    title = Paragraph(f"<b>Attendance Report - {datetime(year, month, 1).strftime('%B %Y')}</b>", styles["Title"])
    elems.append(title)
    elems.append(Spacer(1, 12))

    # Summary table
    summary_data = [["Name", "Class", "Present", "Absent", "Unclear"]]
    for r in report.values():
        summary_data.append([r["Name"], r["Class"], r["Present"], r["Absent"], r["Unclear"]])

    tbl = Table(summary_data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.HexColor("#eef2ff")]),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (2,1), (-1,-1), "CENTER"),
    ]))
    elems.append(Paragraph("<b>Summary</b>", styles["Heading2"]))
    elems.append(tbl)
    elems.append(Spacer(1, 18))

    # Detailed table
    detail_data = [["Date", "Name", "Class", "RollNo", "Status"]]
    for d in details:
        detail_data.append([d["Date"], d["Name"], d["Class"], d["RollNo"], d["Status"]])

    dtbl = Table(detail_data, repeatRows=1)
    dtbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#16a34a")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.HexColor("#ecfdf5")]),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
    ]))
    elems.append(Paragraph("<b>Detailed Records</b>", styles["Heading2"]))
    elems.append(dtbl)

    doc.build(elems)
    mem.seek(0)
    filename = f"attendance_{year}_{month:02d}.pdf"
    return send_file(mem, mimetype="application/pdf", as_attachment=True, download_name=filename)

# ----------------- HTML -----------------
DASHBOARD_TEMPLATE = """
<!doctype html>
<html>
<head>
<title>Attendance Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<style>
:root {
  --bg-primary: #f0f4f8;
  --bg-card: #ffffff;
  --text-primary: #1a202c;
  --text-secondary: #4a5568;
  --border-color: #e2e8f0;
  --accent-main: #3498db;
  --accent-secondary: #2ecc71;
  --good: #27ae60;
  --bad: #e74c3c;
  --warn: #f39c12;
  --neutral: #7f8c8d;
}
.dark-mode {
  --bg-primary: #1a202c;
  --bg-card: #2d3748;
  --text-primary: #e2e8f0;
  --text-secondary: #a0aec0;
  --border-color: #4a5568;
  --accent-main: #63b3ed;
  --accent-secondary: #48bb78;
  --good: #2ecc71;
  --bad: #e74c3c;
  --warn: #f39c12;
  --neutral: #95a5a6;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
}
.container {
  max-width: 1200px;
  margin: 20px auto;
  padding: 0 20px;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background-color: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
}
.header h1 {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--accent-main);
}
.theme-toggle {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 50%;
  width: 40px;
  height: 40px;
  cursor: pointer;
  font-size: 1.2rem;
  color: var(--text-primary);
}
.dashboard-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}
.btn {
  padding: 10px 15px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  color: white;
  background-color: var(--accent-main);
  text-decoration: none;
  display: inline-block;
  white-space: nowrap;
}
.btn.secondary { background-color: var(--accent-secondary); }
.btn.warn { background-color: var(--warn); }
.btn.delete { background-color: var(--neutral); }
.btn:hover { opacity: 0.9; }
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
  margin-top: 20px;
}
.card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 20px;
}
.card h3 {
  font-size: 1.25rem;
  margin-bottom: 5px;
}
.card p {
  color: var(--text-secondary);
  font-size: 0.9rem;
}
.card .status-badge {
  display: inline-block;
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 0.8rem;
  color: white;
  margin-top: 10px;
}
.status-present { background-color: var(--good); }
.status-absent { background-color: var(--bad); }
.status-unclear { background-color: var(--warn); }
.status-not-marked { background-color: var(--neutral); }
.card-actions {
  margin-top: 15px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.card-actions a, .card-actions button {
  font-size: 0.8rem;
  padding: 6px 10px;
  border-radius: 6px;
}
.form-section {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 20px;
  margin-top: 20px;
}
.form-section h3 {
  margin-bottom: 15px;
}
.form-section form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.form-section input {
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background-color: transparent;
  color: var(--text-primary);
}
.form-section button {
  padding: 10px 15px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  color: white;
  background-color: var(--accent-main);
}
.flash-message {
  position: fixed;
  bottom: 20px;
  right: 20px;
  padding: 15px;
  border-radius: 8px;
  color: white;
  font-weight: bold;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  z-index: 1000;
}
.flash-message.success { background-color: var(--good); }
.flash-message.error { background-color: var(--bad); }
/* Modal Styles */
.modal {
  display: none;
  position: fixed;
  z-index: 1;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  overflow: auto;
  background-color: rgba(0,0,0,0.4);
  backdrop-filter: blur(5px);
  justify-content: center;
  align-items: center;
}
.modal-content {
  background-color: var(--bg-card);
  padding: 30px;
  border-radius: 10px;
  text-align: center;
  max-width: 400px;
  width: 90%;
  border: 1px solid var(--border-color);
}
.modal-content h4 {
  margin-bottom: 15px;
}
.modal-content .modal-buttons {
  display: flex;
  justify-content: center;
  gap: 10px;
}
.modal-buttons .btn {
  padding: 8px 16px;
}
.modal-buttons .btn.cancel {
  background-color: var(--neutral);
}
.nlp-result {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 20px;
  margin-top: 20px;
}
.nlp-result table { width: 100%; border-collapse: collapse; }
.nlp-result th, .nlp-result td { padding: 10px; border: 1px solid var(--border-color); text-align: left; }
.nlp-result ul { list-style-type: none; padding: 0; }
.nlp-result li { padding: 8px 0; border-bottom: 1px solid var(--border-color); }
.nlp-result li:last-child { border-bottom: none; }
.search-container {
    position: relative;
    width: 100%;
    margin-bottom: 15px;
}
.search-container input {
    width: 100%;
    padding: 10px 10px 10px 40px; /* Adjust padding for the icon */
    border: 1px solid var(--border-color);
    border-radius: 20px; /* Rounded corners for the input */
    background-color: var(--bg-primary);
    color: var(--text-primary);
    transition: all 0.3s ease;
}
.search-container input:focus {
    outline: none;
    border-color: var(--accent-main);
    box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
}
.search-container .search-icon {
    position: absolute;
    left: 15px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-secondary);
}
</style>
</head>
<body>
<div class="header">
  <h1>Attendance Dashboard</h1>
  <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle Theme">☀️</button>
</div>

<div class="container">
  <div class="dashboard-actions">
    <a href="/month_report" class="btn">📊 Monthly Report</a>
  </div>

  <section class="card-grid">
    {% for r in records %}
    <div class="card">
      <h3>{{r['Name']}} <span style="font-size:0.9em; font-weight:normal; color:var(--text-secondary);">({{r['Class']}} • Roll {{r['RollNo']}})</span></h3>
      {% if r['Status']=="Present" %}<span class="status-badge status-present">Present</span>
      {% elif r['Status']=="Absent" %}<span class="status-badge status-absent">Absent</span>
      {% elif r['Status']=="Unclear" %}<span class="status-badge status-unclear">Unclear</span>
      {% else %}<span class="status-badge status-not-marked">Not Marked</span>{% endif %}
      
      <div class="card-actions">
        <a href="/mark/{{r['RollNo']}}/Present/{{today}}" class="btn secondary">Present</a>
        <a href="/mark/{{r['RollNo']}}/Absent/{{today}}" class="btn warn">Absent</a>
        <a href="/mark/{{r['RollNo']}}/Unclear/{{today}}" class="btn">Unclear</a>
        <button class="btn delete" onclick="showModal('{{r['RollNo']}}', '{{r['Name']}}')">Delete</button>
      </div>
    </div>
    {% endfor %}
  </section>
  
  {% if nlp_result %}
  <div class="nlp-result">
    {{ nlp_result|safe }}
  </div>
  {% endif %}

  <section class="form-section">
    <h3>➕ Add Student</h3>
    <form method="POST" action="/add_student">
      <input name="name" placeholder="Name" required>
      <input name="class" placeholder="Class" required>
      <input name="rollno" placeholder="Roll No" required>
      <button class="btn">Add Student</button>
    </form>
  </section>

  <section class="form-section">
    <h3>🤖 NLP Commands</h3>
    <form method="POST" action="/nlp_command">
      <input name="query" placeholder="e.g., show students  OR  remove all students" required>
      <button class="btn">Run Command</button>
    </form>
    <form method="POST" action="/nlp_voice" style="margin-top:15px;">
      <button class="btn secondary">🎤 Speak Command</button>
    </form>
  </section>
</div>

<div id="deleteModal" class="modal">
  <div class="modal-content">
    <h4>Confirm Deletion</h4>
    <p>Are you sure you want to delete <span id="studentName"></span>?</p>
    <p>This action cannot be undone.</p>
    <div class="modal-buttons">
      <button class="btn cancel" onclick="hideModal('deleteModal')">Cancel</button>
      <a id="confirmDeleteBtn" class="btn red">Delete</a>
    </div>
  </div>
</div>

<div id="nlpConfirmModal" class="modal">
  <div class="modal-content">
    <h4>Confirm Command</h4>
    <p>Are you sure you want to run the command "<span id="nlpCommandText"></span>"?</p>
    <div class="modal-buttons">
      <button class="btn cancel" onclick="hideModal('nlpConfirmModal')">Cancel</button>
      <form id="nlpConfirmForm" method="POST" action="/nlp_command" style="display:inline;">
        <input type="hidden" name="query" id="nlpHiddenQuery">
        <button type="submit" class="btn secondary">Confirm</button>
      </form>
    </div>
  </div>
</div>

{% with messages = get_flashed_messages(with_categories=true) %}
{% if messages %}
  {% for category, message in messages %}
  <div class="flash-message {{ category }}">{{ message }}</div>
  {% endfor %}
{% endif %}
{% endwith %}

<script>
// Theme Toggle
function toggleTheme() {
    const body = document.body;
    body.classList.toggle('dark-mode');
    const isDark = body.classList.contains('dark-mode');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    document.querySelector('.theme-toggle').innerText = isDark ? '🌙' : '☀️';
}
document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('theme') === 'dark') {
        document.body.classList.add('dark-mode');
        document.querySelector('.theme-toggle').innerText = '🌙';
    }
});

// Modal for delete confirmation
function showModal(id) {
    document.getElementById(id).style.display = 'flex';
}
function hideModal(id) {
    document.getElementById(id).style.display = 'none';
}

// Logic for NLP voice command confirmation
window.onload = function() {
    const nlpText = "{{ nlp_text }}";
    if (nlpText && nlpText !== 'None') {
        const modal = document.getElementById('nlpConfirmModal');
        const commandText = document.getElementById('nlpCommandText');
        const hiddenQuery = document.getElementById('nlpHiddenQuery');

        commandText.innerText = nlpText;
        hiddenQuery.value = nlpText;
        showModal('nlpConfirmModal');
    }

    // Existing delete modal function
    window.showDeleteModal = function(rollNo, name) {
        document.getElementById('studentName').innerText = name;
        document.getElementById('confirmDeleteBtn').href = `/delete_student/${rollNo}`;
        showModal('deleteModal');
    };
    
    // Fix for the old function
    window.showModal = function(rollNo, name) {
        document.getElementById('studentName').innerText = name;
        document.getElementById('confirmDeleteBtn').href = `/delete_student/${rollNo}`;
        document.getElementById('deleteModal').style.display = 'flex';
    };
    window.hideModal = function(modalId) {
        document.getElementById(modalId).style.display = 'none';
    };
};
</script>
</body>
</html>
"""

MONTH_TEMPLATE = """
<!doctype html>
<html>
<head>
<title>Monthly Report</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root {
  --bg-primary: #f0f4f8;
  --bg-card: #ffffff;
  --text-primary: #1a202c;
  --text-secondary: #4a5568;
  --border-color: #e2e8f0;
  --accent-main: #3498db;
  --accent-secondary: #2ecc71;
  --good: #27ae60;
  --bad: #e74c3c;
  --warn: #f39c12;
  --neutral: #7f8c8d;
}
.dark-mode {
  --bg-primary: #1a202c;
  --bg-card: #2d3748;
  --text-primary: #e2e8f0;
  --text-secondary: #a0aec0;
  --border-color: #4a5568;
  --accent-main: #63b3ed;
  --accent-secondary: #48bb78;
  --good: #2ecc71;
  --bad: #e74c3c;
  --warn: #f39c12;
  --neutral: #95a5a6;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
}
.container {
  max-width: 1200px;
  margin: 20px auto;
  padding: 0 20px;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background-color: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
}
.header h1 {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--accent-main);
}
.theme-toggle {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 50%;
  width: 40px;
  height: 40px;
  cursor: pointer;
  font-size: 1.2rem;
  color: var(--text-primary);
}
.report-actions {
  display: flex;
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
}
.btn {
  padding: 10px 15px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  color: white;
  background-color: var(--accent-main);
  text-decoration: none;
  display: inline-block;
  white-space: nowrap;
}
.btn.green { background-color: var(--accent-secondary); }
.btn.red { background-color: var(--bad); }
.btn:hover { opacity: 0.9; }
.card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 20px;
  margin-top: 20px;
}
.card h3 {
  margin-bottom: 15px;
}
.card table {
  width: 100%;
  border-collapse: collapse;
}
.card th, .card td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}
.card th {
  background-color: rgba(52, 152, 219, 0.1);
  font-weight: 600;
}
.chart-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}
.chart-container label {
  color: var(--text-secondary);
  font-size: 0.9rem;
}
.chart-container select {
  padding: 8px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background-color: var(--bg-card);
  color: var(--text-primary);
}
.chart-box {
  width: min(450px, 90%);
}
</style>
</head>
<body>
<div class="header">
  <h1>Monthly Report ({{month}} {{year}})</h1>
  <button class="theme-toggle" onclick="toggleTheme()">☀️</button>
</div>

<div class="container">
  <div class="report-actions">
    <a href="/" class="btn">⬅️ Back</a>
    <a class="btn green" href="/download_csv?month={{month_num}}&year={{year}}">⬇️ Download CSV</a>
    <a class="btn red" href="/download_pdf?month={{month_num}}&year={{year}}">📄 Download PDF</a>
  </div>

  <div class="card">
    <div class="chart-container">
      <h3>Attendance Chart</h3>
      <label>Chart type:</label>
      <select id="chartType" onchange="renderChart()">
        <option value="pie">Pie</option>
        <option value="bar">Bar</option>
        <option value="doughnut">Doughnut</option>
      </select>
      <div class="chart-box">
        <canvas id="attendanceChart"></canvas>
      </div>
    </div>
  </div>

  <div class="card">
    <h3>Summary</h3>
    <table>
      <thead>
        <tr><th>Name</th><th>Class</th><th>Present</th><th>Absent</th><th>Unclear</th></tr>
      </thead>
      <tbody>
        {% for r in report.values() %}
        <tr>
          <td>{{r['Name']}}</td>
          <td>{{r['Class']}}</td>
          <td>{{r['Present']}}</td>
          <td>{{r['Absent']}}</td>
          <td>{{r['Unclear']}}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h3>Detailed Records</h3>
    <table>
      <thead>
        <tr><th>Date</th><th>Name</th><th>Class</th><th>Roll No</th><th>Status</th></tr>
      </thead>
      <tbody>
        {% for d in details %}
        <tr>
          <td>{{d['Date']}}</td><td>{{d['Name']}}</td><td>{{d['Class']}}</td><td>{{d['RollNo']}}</td><td>{{d['Status']}}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<script>
// Theme Toggle
function toggleTheme() {
    const body = document.body;
    body.classList.toggle('dark-mode');
    const isDark = body.classList.contains('dark-mode');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    document.querySelector('.theme-toggle').innerText = isDark ? '🌙' : '☀️';
    renderChart(); // Re-render chart to update colors
}
document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('theme') === 'dark') {
        document.body.classList.add('dark-mode');
        document.querySelector('.theme-toggle').innerText = '🌙';
    }
    renderChart();
});

// Chart.js
let chart;
function renderChart(){
  if(chart){ chart.destroy(); }
  const type = document.getElementById('chartType').value;
  const ctx = document.getElementById('attendanceChart').getContext('2d');
  const textColor = getComputedStyle(document.body).getPropertyValue('--text-primary');
  const data = {
    labels: ["Present","Absent","Unclear"],
    datasets: [{
      data: [{{report.values()|sum(attribute='Present')}}, {{report.values()|sum(attribute='Absent')}}, {{report.values()|sum(attribute='Unclear')}}],
      backgroundColor: ['#2ecc71', '#e74c3c', '#f39c12']
    }]
  };
  chart = new Chart(ctx, {
    type,
    data,
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: textColor } }
      },
      scales: (type === 'bar') ? {
        x: { ticks: { color: textColor }, grid: { color: 'rgba(127,140,141,0.2)' } },
        y: { ticks: { color: textColor }, grid: { color: 'rgba(127,140,141,0.2)' }, beginAtZero: true }
      } : {}
    }
  });
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True)
