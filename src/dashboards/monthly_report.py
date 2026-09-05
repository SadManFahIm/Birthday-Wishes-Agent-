import sqlite3
from pathlib import Path
from datetime import datetime
from collections import Counter

import matplotlib.pyplot as plt

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak,
)

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter

DB_FILE = Path("agent_history.db")

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

styles = getSampleStyleSheet()


def query_db(query, params=()):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(query, params)
            return cur.fetchall()
    except Exception as e:
        print("DB Error:", e)
        return []


# ---------------------------------------------------
# BASIC STATS
# ---------------------------------------------------

def get_basic_stats():
    stats = {}

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()

            tables = [
                "memory",
                "followups",
                "engagement",
                "connections",
                "campaigns",
            ]

            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    stats[table] = cur.fetchone()[0]
                except:
                    stats[table] = 0

    except Exception as e:
        print(e)

    return stats


# ---------------------------------------------------
# ACTIVITY CHART
# ---------------------------------------------------

def build_activity_chart():
    chart_path = REPORT_DIR / "activity_chart.png"

    rows = query_db("""
        SELECT DATE(created_at) as day
        FROM connections
        WHERE created_at IS NOT NULL
    """)

    if not rows:
        return None

    counts = Counter([r["day"] for r in rows])

    x = list(counts.keys())
    y = list(counts.values())

    plt.figure(figsize=(8, 4))
    plt.plot(x, y)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(chart_path)
    plt.close()

    return str(chart_path)


# ---------------------------------------------------
# TOP CONNECTIONS
# ---------------------------------------------------

def get_top_connections(limit=10):
    rows = query_db("""
        SELECT contact_name, strength_score
        FROM tracker
        ORDER BY strength_score DESC
        LIMIT ?
    """, (limit,))

    return rows


# ---------------------------------------------------
# MISSED BIRTHDAYS
# ---------------------------------------------------

def get_missed_birthdays():
    rows = query_db("""
        SELECT contact_name, platform, missed_date
        FROM missed_birthdays
        ORDER BY missed_date DESC
        LIMIT 20
    """)

    return rows


# ---------------------------------------------------
# CAMPAIGN STATS
# ---------------------------------------------------

def get_campaign_stats():
    rows = query_db("""
        SELECT campaign_name, messages_sent, replies_received
        FROM campaigns
        ORDER BY messages_sent DESC
        LIMIT 10
    """)

    return rows


# ---------------------------------------------------
# PDF GENERATOR
# ---------------------------------------------------

def generate_monthly_report():

    now = datetime.now()

    filename = REPORT_DIR / f"monthly_report_{now.strftime('%Y_%m')}.pdf"

    doc = SimpleDocTemplate(
        str(filename),
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=30,
    )

    elements = []

    title = f"Birthday Wishes Agent Monthly Report - {now.strftime('%B %Y')}"

    elements.append(Paragraph(title, styles['Title']))
    elements.append(Spacer(1, 20))

    # ------------------------------------------------
    # SUMMARY
    # ------------------------------------------------

    elements.append(Paragraph("Admin Summary", styles['Heading1']))

    stats = get_basic_stats()

    summary_data = [["Metric", "Value"]]

    for k, v in stats.items():
        summary_data.append([k, str(v)])

    summary_table = Table(summary_data, colWidths=[250, 150])

    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # ------------------------------------------------
    # CHART
    # ------------------------------------------------

    chart = build_activity_chart()

    if chart:
        elements.append(Paragraph("Activity Analytics", styles['Heading1']))
        elements.append(Image(chart, width=450, height=220))
        elements.append(Spacer(1, 20))

    # ------------------------------------------------
    # TOP CONNECTIONS
    # ------------------------------------------------

    elements.append(Paragraph("Top Connections", styles['Heading1']))

    top_connections = get_top_connections()

    tc_data = [["Contact", "Strength Score"]]

    for row in top_connections:
        tc_data.append([
            row["contact_name"],
            str(row["strength_score"]),
        ])

    tc_table = Table(tc_data)

    tc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(tc_table)
    elements.append(Spacer(1, 20))

    # ------------------------------------------------
    # MISSED BIRTHDAYS
    # ------------------------------------------------

    elements.append(Paragraph("Missed Birthdays", styles['Heading1']))

    missed = get_missed_birthdays()

    missed_data = [["Contact", "Platform", "Date"]]

    for row in missed:
        missed_data.append([
            row["contact_name"],
            row["platform"],
            row["missed_date"],
        ])

    missed_table = Table(missed_data)

    missed_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.red),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(missed_table)
    elements.append(PageBreak())

    # ------------------------------------------------
    # CAMPAIGN STATS
    # ------------------------------------------------

    elements.append(Paragraph("Campaign Performance", styles['Heading1']))

    campaigns = get_campaign_stats()

    campaign_data = [["Campaign", "Messages", "Replies"]]

    for row in campaigns:
        campaign_data.append([
            row["campaign_name"],
            str(row["messages_sent"]),
            str(row["replies_received"]),
        ])

    campaign_table = Table(campaign_data)

    campaign_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.green),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(campaign_table)

    doc.build(elements)

    print(f"Monthly report generated: {filename}")

    return filename


if __name__ == "__main__":
    generate_monthly_report()