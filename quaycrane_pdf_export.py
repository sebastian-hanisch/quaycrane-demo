"""PDF-Export des Kran-Einsatzplans (fpdf2, Helvetica-Kernfont)."""

import time


def generate_crane_plan_pdf(label, instance, result):
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Containerbruecken-Einsatzplan", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Methode: {label}  -  Erstellt: {time.strftime('%d.%m.%Y %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Zusammenfassung", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    summary_rows = [
        ("Schiffslänge (Bays)", str(instance.n_bays)),
        ("Anzahl Containerbrücken", str(instance.n_cranes)),
        ("Liegezeit (Makespan)", f"{result['makespan']:.1f} min"),
        ("Wartezeit durch Interferenz", f"{result['total_wait_time']:.1f} min"),
        ("Fahrzeit gesamt", f"{result['total_travel_time']:.1f} min"),
        ("Lastungleichgewicht", f"{result['load_imbalance']:.1f} min"),
        ("Sicherheitsabstand", f"{instance.safety_margin} Bay(s)"),
    ]
    for label_text, value_text in summary_rows:
        pdf.cell(80, 7, label_text, border=0)
        pdf.cell(0, 7, value_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Aufgaben je Bay", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "B", 9)
    headers = ["Bay", "Kran", "Moves", "Start (min)", "Ende (min)"]
    widths = [25, 25, 25, 35, 35]
    pdf.set_fill_color(230, 230, 230)
    for header, width in zip(headers, widths):
        pdf.cell(width, 7, header, border=1, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(7)

    pdf.set_font("Helvetica", "", 9)
    for bay in sorted(result["tasks"].keys()):
        t = result["tasks"][bay]
        row = [str(bay), f"Kran {t.crane + 1}", str(instance.bays[bay].moves), f"{t.start:.1f}", f"{t.end:.1f}"]
        for value, width in zip(row, widths):
            pdf.cell(width, 7, value, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(7)

    return bytes(pdf.output())
