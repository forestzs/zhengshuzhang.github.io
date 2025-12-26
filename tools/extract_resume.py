#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extract text from resume.pdf and generate:
- resume_raw.json: {generated_at, source, text}
- resume.json: structured fields used by your website

Run:
  python tools/extract_resume.py
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple


DEFAULT_GITHUB = "https://github.com/forestzs"
DEFAULT_SUBTITLE = "Software Engineer • USC MS Spatial Data Science • Los Angeles"


# -----------------------------
# Utils
# -----------------------------
def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: str, obj: Dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Fix hyphenation across line breaks: "data-\nintensive" -> "data-intensive"
    text = re.sub(r"(\w)-\n(\w)", r"\1-\2", text)

    # Normalize bullets to ■
    for b in ["•", "◼", "◾", "▪", "●", "–", "—"]:
        text = text.replace(b, "■")

    # Strip trailing spaces per line
    text = "\n".join([ln.rstrip() for ln in text.split("\n")])

    # Reduce multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def lines_nonempty(text: str) -> List[str]:
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def norm_key(s: str) -> str:
    # uppercase, remove all non-alnum for robust header matching
    return re.sub(r"[^A-Z0-9]+", "", s.upper())


def unique_preserve(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        t = x.strip()
        if not t:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


# -----------------------------
# PDF extraction (IMPORTANT FIX)
# -----------------------------
def extract_text_pymupdf_words(pdf_path: str) -> str:
    """
    Most robust: use PyMuPDF words and rebuild lines with spaces.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    all_lines: List[str] = []

    for page in doc:
        words = page.get_text("words")  # x0,y0,x1,y1,word,block,line,word_no
        if not words:
            # fallback for this page
            all_lines.append(page.get_text("text") or "")
            continue

        # sort words top-to-bottom, left-to-right
        words.sort(key=lambda w: (w[5], w[6], w[1], w[0]))  # block,line,y,x

        cur_key: Optional[Tuple[int, int]] = None
        cur_line: List[str] = []

        def flush():
            nonlocal cur_line
            if cur_line:
                all_lines.append(" ".join(cur_line).strip())
                cur_line = []

        for w in words:
            word = str(w[4]).strip()
            block = int(w[5])
            line = int(w[6])
            key = (block, line)

            if cur_key is None:
                cur_key = key

            if key != cur_key:
                flush()
                cur_key = key

            if word:
                cur_line.append(word)

        flush()

        # page separator (helps keep structure)
        all_lines.append("")

    return "\n".join(all_lines)


def extract_text_from_pdf(pdf_path: str) -> str:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Cannot find PDF: {pdf_path}")

    # 1) PyMuPDF words (BEST)
    try:
        t = extract_text_pymupdf_words(pdf_path)
        if t and t.strip():
            return t
    except Exception:
        pass

    # 2) pdfplumber (layout mode)
    try:
        import pdfplumber
        chunks: List[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text(layout=True) or page.extract_text() or ""
                chunks.append(txt)
        t = "\n".join(chunks)
        if t and t.strip():
            return t
    except Exception:
        pass

    # 3) pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        chunks = []
        for p in reader.pages:
            chunks.append(p.extract_text() or "")
        t = "\n".join(chunks)
        if t and t.strip():
            return t
    except Exception:
        pass

    return ""


# -----------------------------
# Section slicing (robust headers)
# -----------------------------
SECTION_HEADERS = [
    "SUMMARY",
    "EDUCATION",
    "EXPERIENCE",
    "PROJECTS",
    "TECHNICAL SKILLS",
    "SKILLS",
]

SECTION_KEYS = [norm_key(h) for h in SECTION_HEADERS]


def find_header_index(lines: List[str], header: str) -> int:
    target = norm_key(header)
    for idx, ln in enumerate(lines):
        if norm_key(ln) == target:
            return idx
        # allow "TECHNICALSKILLS" style
        if norm_key(ln).startswith(target) and len(norm_key(ln)) <= len(target) + 2:
            return idx
    return -1


def is_any_header_line(line: str) -> bool:
    k = norm_key(line)
    return k in SECTION_KEYS


def slice_section(lines: List[str], header: str) -> List[str]:
    start = find_header_index(lines, header)
    if start < 0:
        return []
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if is_any_header_line(lines[j]):
            end = j
            break
    return lines[start + 1 : end]


# -----------------------------
# Parse basics
# -----------------------------
PHONE_RE = re.compile(r"(\+?\d[\d\-\s\(\)]{7,}\d)")
EMAIL_RE = re.compile(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.IGNORECASE)
URL_RE = re.compile(r"(https?://[^\s|]+)", re.IGNORECASE)


def parse_name(lines: List[str]) -> str:
    return lines[0].strip() if lines else ""


def parse_contact_line(lines: List[str]) -> Dict[str, str]:
    contact = {"phone": "", "email": "", "linkedin": "", "github": "", "location": ""}

    if len(lines) < 2:
        contact["github"] = DEFAULT_GITHUB
        return contact

    line = lines[1]
    parts = [p.strip() for p in line.split("|")]

    m = PHONE_RE.search(line)
    if m:
        contact["phone"] = m.group(1).strip()

    m = EMAIL_RE.search(line)
    if m:
        contact["email"] = m.group(1).strip()

    urls = URL_RE.findall(line)
    for u in urls:
        ul = u.lower()
        if "linkedin.com" in ul:
            contact["linkedin"] = u.strip()
        elif "github.com" in ul:
            contact["github"] = u.strip()

    # location: pick the last part that is not phone/email/url
    for p in reversed(parts):
        if not p:
            continue
        if EMAIL_RE.search(p):
            continue
        if URL_RE.search(p):
            continue
        if PHONE_RE.search(p) and len(p) <= 25:
            continue
        contact["location"] = re.sub(r"\s+", " ", p).strip()
        break

    if not contact["github"]:
        contact["github"] = DEFAULT_GITHUB

    return contact


def parse_summary(lines: List[str]) -> str:
    sec = slice_section(lines, "SUMMARY")
    if not sec:
        return ""
    txt = " ".join(sec)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


# -----------------------------
# Education
# -----------------------------
def parse_education(lines: List[str]) -> List[Dict[str, str]]:
    sec = slice_section(lines, "EDUCATION")
    if not sec:
        return []

    items: List[Dict[str, str]] = []
    i = 0
    while i < len(sec):
        school = sec[i].strip()
        degree = sec[i + 1].strip() if i + 1 < len(sec) else ""
        items.append({"school": school, "degree": degree})
        i += 2

    # cleanup
    cleaned = []
    for it in items:
        if it["school"] or it["degree"]:
            cleaned.append(it)
    return cleaned


# -----------------------------
# Projects
# -----------------------------
MONTH_RE = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t)?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
PROJ_TIME_RE = re.compile(rf"^(.*?)(\b{MONTH_RE}\b.*\b\d{{4}}\b.*)$", re.IGNORECASE)
BULLET_RE = re.compile(r"^[■\-\*]\s*(.+)$")


def parse_projects(lines: List[str]) -> List[Dict[str, object]]:
    sec = slice_section(lines, "PROJECTS")
    if not sec:
        return []

    projects: List[Dict[str, object]] = []
    cur: Optional[Dict[str, object]] = None

    def push():
        nonlocal cur
        if not cur:
            return
        bullets = cur.get("bullets", [])
        if isinstance(bullets, list):
            cur["bullets"] = [b.strip() for b in bullets if str(b).strip()]
        projects.append(cur)
        cur = None

    for ln in sec:
        ln = ln.strip()

        m = PROJ_TIME_RE.match(ln)
        if m:
            push()
            title = m.group(1).strip(" -–—|")
            time = m.group(2).strip()
            cur = {"title": title, "time": time, "bullets": []}
            continue

        bm = BULLET_RE.match(ln)
        if bm and cur is not None:
            cur["bullets"].append(bm.group(1).strip())
            continue

        # continuation lines (wrap)
        if cur is not None:
            if cur["bullets"]:
                cur["bullets"][-1] = (cur["bullets"][-1] + " " + ln).strip()
            else:
                cur["bullets"].append(ln)

    push()
    return projects


# -----------------------------
# Skills
# -----------------------------
def split_csvish(s: str) -> List[str]:
    parts = re.split(r"[;,]", s)
    return [p.strip() for p in parts if p.strip()]


def parse_skills(lines: List[str]) -> Dict[str, List[str]]:
    sec = slice_section(lines, "TECHNICAL SKILLS")
    if not sec:
        sec = slice_section(lines, "SKILLS")
    if not sec:
        return {"languages": [], "frameworks": [], "tools": []}

    text = "\n".join(sec)

    def grab(label_pattern: str) -> List[str]:
        pat = rf"(?:^|\n)\s*[■\-\*]?\s*(?:{label_pattern})\s*:\s*([^\n]+)"
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            return []
        val = (m.group(1) or "").strip()
        if not val:
            return []
        return split_csvish(val)

    languages = grab(r"Languages?")
    frameworks = grab(r"Frameworks\s*&\s*Libraries|Frameworks\s*/\s*Libraries|Frameworks|Libraries")
    db = grab(r"Databases\s*&\s*Cach(?:e|ing)|Databases|Database")
    cloud = grab(r"Cloud\s*&\s*DevOps|Cloud|DevOps")
    tools_testing = grab(r"Tools\s*&\s*Testing|Tools|Testing")

    tools = unique_preserve(db + cloud + tools_testing)

    return {
        "languages": unique_preserve(languages),
        "frameworks": unique_preserve(frameworks),
        "tools": tools,
    }


# -----------------------------
# Build output
# -----------------------------
def build_structured(raw_text: str) -> Dict[str, object]:
    ln = lines_nonempty(raw_text)

    name = parse_name(ln) or "Zhengshu Zhang"
    contact = parse_contact_line(ln)
    summary = parse_summary(ln)
    education = parse_education(ln)
    projects = parse_projects(ln)
    skills = parse_skills(ln)

    return {
        "generated_at": iso_now(),
        "source": "resume.pdf",
        "name": name,
        "subtitle": DEFAULT_SUBTITLE,
        "summary": summary,
        "resumeUrl": "./resume.pdf",
        "contact": contact,
        "education": education,
        "projects": projects,
        "skills": skills,
    }


def main() -> None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pdf_path = os.path.join(repo_root, "resume.pdf")

    raw = extract_text_from_pdf(pdf_path)
    raw = normalize_text(raw)

    raw_out = {"generated_at": iso_now(), "source": "resume.pdf", "text": raw}
    structured = build_structured(raw)

    write_json(os.path.join(repo_root, "resume_raw.json"), raw_out)
    write_json(os.path.join(repo_root, "resume.json"), structured)

    print("✅ Generated resume_raw.json and resume.json")


if __name__ == "__main__":
    main()
