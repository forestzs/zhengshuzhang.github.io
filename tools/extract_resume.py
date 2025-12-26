# tools/extract_resume.py
import json
import os
import re
import subprocess
from datetime import datetime, timezone

RE_SPACES = re.compile(r"[ \t]+")

def run_pdftotext(pdf_path: str) -> str:
    # Poppler pdftotext gives better layout than most pure-python libs
    # -layout keeps columns/spacing more readable for resumes
    cmd = ["pdftotext", "-layout", pdf_path, "-"]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    return out.decode("utf-8", errors="ignore")

def run_pypdf(pdf_path: str) -> str:
    # fallback if pdftotext not available
    try:
        from pypdf import PdfReader
    except Exception:
        from PyPDF2 import PdfReader  # older fallback

    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages)

def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # normalize spaces but keep line breaks
    lines = []
    for line in text.split("\n"):
        line = RE_SPACES.sub(" ", line).strip()
        # remove super-noisy empty lines (keep a single blank line)
        lines.append(line)
    # collapse many blank lines
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pdf_path = os.path.join(repo_root, "resume.pdf")
    out_json = os.path.join(repo_root, "resume.json")

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"resume.pdf not found at {pdf_path}")

    # Try pdftotext first; fallback to pypdf
    text_raw = ""
    try:
        text_raw = run_pdftotext(pdf_path)
    except Exception:
        text_raw = run_pypdf(pdf_path)

    text = clean_text(text_raw)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "resume.pdf",
        "text": text,
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_json} ({len(text)} chars)")

if __name__ == "__main__":
    main()

