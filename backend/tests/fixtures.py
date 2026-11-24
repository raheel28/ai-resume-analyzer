from __future__ import annotations

import io

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

GOOD_LINES = [
    "Jane Doe",
    "Dublin, Ireland | jane.doe@example.com | +353 87 123 4567 | linkedin.com/in/janedoe",
    "SUMMARY",
    "Software engineer focused on backend services and data pipelines, with two years of "
    "experience shipping production Python and TypeScript systems.",
    "EXPERIENCE",
    "Software Engineer Intern, Acme Labs — Jan 2025 - Dec 2025",
    "• Built an LLM support assistant that answered 3,000 customer queries a month with 92% accuracy",
    "• Reduced API latency by 40% by adding Redis caching to the product search service",
    "• Designed a scoring engine that ranks 500+ products against user preferences in under 50 ms",
    "• Migrated nightly batch jobs to Airflow, cutting failed runs from 12 to 1 per month",
    "PROJECTS",
    "• Developed a peer-to-peer chat app over WebRTC supporting 20 concurrent users per room",
    "• Implemented end-to-end encryption for messages using the Web Crypto API and ECDH keys",
    "EDUCATION",
    "MSc Computer Science, University College Dublin — Sep 2026 - Aug 2027",
    "B.Tech Computer Science, Manipal University Jaipur — Aug 2022 - May 2026",
    "SKILLS",
    "Python, C++, JavaScript, TypeScript, React, Node.js, FastAPI, MongoDB, PostgreSQL, Docker, Linux, Git",
]

GOOD_LINES[3] += " " + " ".join(["Comfortable owning features end to end."] * 30)


def good_docx() -> bytes:
    doc = Document()
    for line in GOOD_LINES:
        doc.add_paragraph(line)
    return _save(doc)


def bad_docx() -> bytes:
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = "bad.candidate@example.com | 087 765 4321"
    sect = doc.sections[0]._sectPr
    cols = sect.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sect.append(cols)
    cols.set(qn("w:num"), "2")

    for line in [
        "Bad Candidate",
        "MY JOURNEY:",
        "• Responsible for working on various tasks assigned by my manager in the team",
        "• I was involved in helping with the website and fixing some of the bugs",
        "• Worked on the database and other things that were needed by the company",
        "WHERE I STUDIED",
        "Some University, 2020 - 2024",
    ]:
        doc.add_paragraph(line)
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Python"
    table.rows[0].cells[1].text = "Java"
    return _save(doc)


def good_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 50
    for line in GOOD_LINES:
        words, row = line.split(), ""
        for w in words:
            if len(row) + len(w) > 95:
                c.drawString(40, y, row)
                y -= 14
                row = ""
            row += w + " "
        c.drawString(40, y, row)
        y -= 14
        if y < 50:
            c.showPage()
            y = height - 50
    c.save()
    return buf.getvalue()


def two_column_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 50
    for i in range(45):
        c.drawString(40, y, f"Left column skill item number {i}")
        c.drawString(width / 2 + 20, y, f"Right column experience line {i}")
        y -= 16
    c.save()
    return buf.getvalue()


def _save(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def dense_pdf_with_links() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    lines = [
        ("Alex Murphy", 14),
        ("Dublin, Ireland | alex.murphy@example.com | +353 87 000 0000 | GitHub | LinkedIn", 9),
        ("EXPERIENCE", 10),
        ("Software Engineering Intern, Brightline Labs — May 2025 - Dec 2025", 9),
    ]
    bullets = [
        "Built a customer support chatbot using an LLM API with tool calling, answering product questions from a MongoDB catalogue",
        "Wrote server-side validation for the model's tool calls to block malformed queries before they reached the database",
        "Designed a phone recommendation engine that scores products against user preferences and budget constraints",
        "Improved PostgreSQL query performance by about 15% by adding composite indexes to the orders table",
        "Implemented loading indicators on real-time dashboards using Angular, giving users clear data-loading status",
        "Displayed real-time order data as graphs using Java and Angular, helping the operations team analyse order flow",
        "Collected and analyzed 500+ consumer data records; findings fed into product prioritization decisions",
        "Developed a peer-to-peer chat app with WebRTC and Node.js supporting 20+ concurrent connections per room",
        "Built a maze-solving visualizer in JavaScript with a user-friendly interface and step-by-step animation",
        "Trained a semantic segmentation model that improved mIoU by 9.7% over the baseline on the validation set",
    ]
    c = canvas.Canvas(buf := io.BytesIO(), pagesize=A4)
    width, height = A4
    y = height - 40

    def text(s, size, x=40):
        nonlocal y
        c.setFont("Helvetica-Bold" if size >= 10 else "Helvetica", size)
        c.drawString(x, y, s)
        y -= size + 3.5

    text(*lines[0]); text(*lines[1])
    from reportlab.pdfbase.pdfmetrics import stringWidth
    contact, cy = lines[1][0], y + 12.5
    for word, url in (("GitHub", "https://github.com/alexm"), ("LinkedIn", "https://linkedin.com/in/alexm")):
        x0 = 40 + stringWidth(contact[:contact.index(word)], "Helvetica", 9)
        c.linkURL(url, (x0, cy - 2, x0 + stringWidth(word, "Helvetica", 9), cy + 8), relative=0)
    for block in range(3):
        text(["EXPERIENCE", "PROJECTS", "EXPERIENCE"][block] if block != 2 else "PROJECTS", 10) if block else text(*lines[2])
        text(lines[3][0] if block == 0 else f"Project group {block}", 9)
        for b in bullets[block * 3: block * 3 + 4]:
            text("• " + b, 9, x=46)
    text("EDUCATION", 10)
    text("MSc Computer Science, University College Dublin — Sep 2026 - Aug 2027", 9)
    text("B.Tech Computer Science and Engineering, Manipal University Jaipur — Aug 2022 - May 2026", 9)
    text("SKILLS", 10)
    text("C++, Python, JavaScript, Java, Node.js, Express, React, Angular, MongoDB, PostgreSQL,", 9)
    text("Git, Linux, Docker, WebRTC, Data structures and algorithms, OOP", 9)
    text("ACHIEVEMENTS", 10)
    text("• Solved 1000+ LeetCode problems in C++ with a contest rating of 1638", 9, x=46)
    c.save()
    return buf.getvalue()
