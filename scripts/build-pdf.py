#!/usr/bin/env python3
"""Compile a drafted application folder into submission-ready PDFs.

    python scripts/build-pdf.py applications/flipkart-2026-07-25

Produces resume_<company>.pdf from the drafted .tex, and cover_letter_<company>.pdf
by pouring the drafted markdown letter into config/cover-letter-template.tex.
Needs pdflatex on PATH (MiKTeX or TeX Live). Stdlib only.
"""
import os
import re
import shutil
import subprocess
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUX_EXT = (".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".synctex.gz")


def have_pdflatex():
    return shutil.which("pdflatex") is not None


def tex_escape(text):
    """Escape the characters LaTeX treats as markup."""
    repl = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(repl.get(c, c) for c in text)


def markdown_to_tex_body(md):
    """Turn the drafted markdown letter into LaTeX body paragraphs.

    Handles the small subset the drafter actually emits: an optional heading,
    **bold**, and blank-line-separated paragraphs.
    """
    lines = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("#"):          # drop the markdown title
            continue
        lines.append(line)
    text = "\n".join(lines).strip()

    out_paragraphs = []
    for para in re.split(r"\n\s*\n", text):
        segs = [s.strip() for s in para.splitlines() if s.strip()]
        if not segs:
            continue
        # Prose is hard-wrapped and should reflow, but blocks of short lines
        # (a signature, an address) are meant to stay on separate lines.
        if len(segs) > 1 and all(len(s) < 60 for s in segs):
            para = "@@BREAK@@".join(segs)
        else:
            para = " ".join(segs)
        # Capture bold spans before escaping, then restore them as \textbf.
        bolds = []

        def stash(m):
            bolds.append(m.group(1))
            return f"@@BOLD{len(bolds) - 1}@@"

        para = re.sub(r"\*\*(.+?)\*\*", stash, para)
        para = tex_escape(para)
        for i, content in enumerate(bolds):
            para = para.replace(f"@@BOLD{i}@@", r"\textbf{" + tex_escape(content) + "}")
        para = para.replace("@@BREAK@@", "\\\\\n")
        out_paragraphs.append(para)
    return "\n\n".join(out_paragraphs)


def contact_line():
    """Pull the contact details out of the user's real resume, if present."""
    resume = os.path.join(ROOT, "config", "resume.md")
    name, contact = "", ""
    if os.path.exists(resume):
        with open(resume, encoding="utf-8") as f:
            head = f.read(1200)
        m = re.search(r"^#\s*Resume\s*[-—–]\s*(.+)$", head, re.M)
        if m:
            name = m.group(1).strip()
        parts = []
        m = re.search(r"(\+?\d[\d\s\-()]{7,})", head)
        if m:
            parts.append(m.group(1).strip())
        m = re.search(r"([\w.\-+]+@[\w.\-]+\.\w+)", head)
        if m:
            parts.append(r"\href{mailto:%s}{%s}" % (m.group(1), m.group(1)))
        contact = r" $|$ ".join(parts)
    return name or "Your Name", contact or ""


def run_pdflatex(tex_path, folder):
    """Compile twice so hyperref/outline references settle."""
    for _ in range(2):
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", os.path.basename(tex_path)],
            cwd=folder, capture_output=True, text=True)
    pdf = os.path.splitext(tex_path)[0] + ".pdf"
    if not os.path.exists(pdf):
        tail = "\n".join((proc.stdout or "").splitlines()[-25:])
        raise RuntimeError(f"pdflatex produced no PDF for {os.path.basename(tex_path)}:\n{tail}")
    return pdf


def build(folder):
    """Compile every draftable file in folder. Returns (pdf_paths, notes)."""
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise SystemExit(f"not a folder: {folder}")
    if not have_pdflatex():
        raise SystemExit("pdflatex not found on PATH. Install MiKTeX or TeX Live, "
                         "or paste the .tex into overleaf.com instead.")

    pdfs, notes = [], []
    names = sorted(os.listdir(folder))

    for name in names:
        if name.startswith("resume_") and name.endswith(".tex"):
            pdfs.append(run_pdflatex(os.path.join(folder, name), folder))

    for name in names:
        if name.startswith("cover_letter_") and name.endswith(".md"):
            slug = name[len("cover_letter_"):-len(".md")]
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                body = markdown_to_tex_body(f.read())
            with open(os.path.join(ROOT, "config", "cover-letter-template.tex"),
                      encoding="utf-8") as f:
                tpl = f.read()
            person, contact = contact_line()
            tex = (tpl.replace("__NAME__", tex_escape(person))
                      .replace("__CONTACT__", contact)
                      .replace("__DATE__", date.today().strftime("%d %B %Y"))
                      .replace("__BODY__", body))
            tex_path = os.path.join(folder, f"cover_letter_{slug}.tex")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(tex)
            pdfs.append(run_pdflatex(tex_path, folder))

    # Clean LaTeX's scratch files so the folder only holds things worth opening.
    for name in os.listdir(folder):
        if name.endswith(AUX_EXT):
            os.remove(os.path.join(folder, name))

    for pdf in pdfs:
        if os.path.basename(pdf).startswith("resume_"):
            pages = page_count(pdf)
            if pages and pages > 1:
                notes.append(f"{os.path.basename(pdf)} is {pages} pages — recruiters "
                             f"expect a 1-page resume at this experience level; "
                             f"trim the least relevant bullets.")
    return pdfs, notes


def page_count(pdf_path):
    """Count pages without a PDF library: /Type /Page occurrences."""
    try:
        with open(pdf_path, "rb") as f:
            data = f.read()
        n = len(re.findall(rb"/Type\s*/Page[^s]", data))
        return n or None
    except OSError:
        return None


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    pdfs, notes = build(sys.argv[1])
    for p in pdfs:
        print(f"built {os.path.relpath(p, ROOT)}")
    for n in notes:
        print(f"NOTE: {n}")
    if not pdfs:
        print("nothing to build (no resume_*.tex or cover_letter_*.md found)")


if __name__ == "__main__":
    main()
