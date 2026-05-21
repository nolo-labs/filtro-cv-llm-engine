"""Convierte docs/integration.md a docs/integration.pdf con formato razonable.

Uso: python scripts/md_to_pdf.py
Requiere: fpdf2
"""
import re
import sys
from pathlib import Path

from fpdf import FPDF

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "docs" / "integration.md"
DST = REPO / "docs" / "integration.pdf"

# Reemplazos para caracteres fuera de latin-1
UNICODE_REPLACEMENTS = {
    "→": "->",
    "←": "<-",
    "↓": "v",
    "↑": "^",
    "—": "--",
    "–": "-",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "…": "...",
    "•": "-",
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
}


def sanitize(text: str) -> str:
    for bad, good in UNICODE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class PDF(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"Pagina {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)


def render_inline(pdf: FPDF, text: str, base_size: float = 10.5):
    """Renderiza una linea con soporte para **bold** y `code` inline."""
    # tokeniza por marcadores
    tokens = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text)
    for tok in tokens:
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**"):
            pdf.set_font("Helvetica", "B", base_size)
            pdf.write(5.5, sanitize(tok[2:-2]))
            pdf.set_font("Helvetica", "", base_size)
        elif tok.startswith("`") and tok.endswith("`"):
            pdf.set_font("Courier", "", base_size - 0.5)
            pdf.set_text_color(180, 30, 60)
            pdf.write(5.5, sanitize(tok[1:-1]))
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", base_size)
        else:
            pdf.set_font("Helvetica", "", base_size)
            pdf.write(5.5, sanitize(tok))
    pdf.ln(5.5)


def render_code_block(pdf: FPDF, lines: list[str]):
    pdf.ln(1)
    pdf.set_fill_color(245, 245, 247)
    pdf.set_font("Courier", "", 8.5)
    pdf.set_text_color(40, 40, 60)
    for ln in lines:
        pdf.cell(0, 4.5, sanitize(ln), ln=1, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


def render_heading(pdf: FPDF, level: int, text: str):
    sizes = {1: 18, 2: 14, 3: 11.5}
    spacing_before = {1: 2, 2: 5, 3: 3}
    spacing_after = {1: 3, 2: 2, 3: 1}
    pdf.ln(spacing_before.get(level, 2))
    pdf.set_font("Helvetica", "B", sizes.get(level, 11))
    pdf.multi_cell(0, sizes.get(level, 11) * 0.55, sanitize(text))
    if level == 1:
        # subrayado decorativo
        y = pdf.get_y()
        pdf.set_draw_color(180, 180, 180)
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(spacing_after.get(level, 1))


def md_to_pdf(md_text: str, out_path: Path):
    pdf = PDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=18, top=18, right=18)
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10.5)

    lines = md_text.splitlines()
    i = 0
    in_code = False
    code_buf: list[str] = []

    while i < len(lines):
        line = lines[i]

        # code fences
        if line.strip().startswith("```"):
            if in_code:
                render_code_block(pdf, code_buf)
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # horizontal rule
        if re.fullmatch(r"-{3,}", line.strip()):
            pdf.ln(2)
            y = pdf.get_y()
            pdf.set_draw_color(210, 210, 210)
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(3)
            i += 1
            continue

        # headings
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            render_heading(pdf, level, m.group(2).strip())
            i += 1
            continue

        # blockquote
        if line.startswith("> "):
            pdf.set_fill_color(250, 248, 235)
            pdf.set_draw_color(220, 200, 120)
            x0 = pdf.l_margin
            y0 = pdf.get_y()
            text = line[2:].strip()
            pdf.set_x(x0 + 3)
            pdf.set_font("Helvetica", "I", 10)
            pdf.multi_cell(0, 5.5, sanitize(text), fill=True)
            y1 = pdf.get_y()
            pdf.set_draw_color(200, 160, 50)
            pdf.set_line_width(0.8)
            pdf.line(x0, y0, x0, y1)
            pdf.set_line_width(0.2)
            pdf.ln(1)
            i += 1
            continue

        # bullet list
        m = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if m:
            indent = len(m.group(1)) // 2
            content = m.group(2)
            pdf.set_x(pdf.l_margin + 3 + indent * 5)
            pdf.set_font("Helvetica", "", 10.5)
            pdf.write(5.5, sanitize("- "))
            render_inline(pdf, content)
            i += 1
            continue

        # blank line
        if not line.strip():
            pdf.ln(2)
            i += 1
            continue

        # default paragraph
        render_inline(pdf, line)
        i += 1

    if in_code and code_buf:
        render_code_block(pdf, code_buf)

    pdf.output(str(out_path))


def main():
    if not SRC.exists():
        print(f"ERROR: no existe {SRC}", file=sys.stderr)
        sys.exit(1)
    md_text = SRC.read_text(encoding="utf-8")
    md_to_pdf(md_text, DST)
    print(f"OK -> {DST}")


if __name__ == "__main__":
    main()
