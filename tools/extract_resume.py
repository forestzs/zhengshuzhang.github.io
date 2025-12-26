#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extract text from resume.pdf and generate:
- resume_raw.json: {generated_at, source, text}
- resume.json: structured fields used by your website

Usage:
  python tools/extract_resume.py
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple


# -----------------------------
# PDF text extraction (robust)
# -----------------------------
def extract_text_from_pdf(pdf_path: str) -> str:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Cannot find PDF: {pdf_path}")

    # 1) pdfplumber
    try:
        import pdfplumber  # type: ignore
        chunks: List[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                chunks.append(t)
        text = "\n".join(chunks)
        if text.strip():
            return text
    except Exception:
        pass

    # 2) PyMuPDF
    try:
        import fitz  # type: ignore
        doc = fitz.open(pdf_path)
        chunks = []
        for page in doc:
            chunks.append(page.get_text("text") or "")
        text = "\n".join(chunks)
        if text.strip():
            return text
    except Exception:
        pass

    # 3) pypdf
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(pdf_path)
        chunks = []
        for p in reader.pages:
            chunks.append(p.extract_text() or "")
        text = "\n".join(chunks)
        if text.strip():
            return text
    except Exception:
        pass

    return ""


def normalize_text(text: str) -> str:
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Fix hyphenation across line breaks: "data-\nintensive" -> "data-intensive"
    text = re.sub(r"(\w)-\n(\w)", r"\1-\2", text)

    # Normalize bullets
    text = text.replace("•", "■")
    text = text.replace("◼", "■").replace("◾", "■").replace("▪", "■").replace("●", "■")

    # Trim trailing spaces on each line
    text = "\n".join([ln.rstrip() for ln in text.split("\n")])

    # Reduce too many blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return text


def lines_nonempty(text: str) -> List[str]:
    out: List[str] = []
    for ln in text.split("\n"):
        s = ln.strip()
        if s:
            out.append(s)
    return out


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def unique_preserve(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        k = x.strip()
        if not k:
            continue
        if k.lower() in seen:
            continue
        seen.add(k.lower())
        out.append(k)
    return out


# -----------------------------
# Section helpers
# -----------------------------
SECTION_HEADERS = [
    "SUMMARY",
    "EDUCATION",
    "EXPERIENCE",
    "PROJECTS",
    "TECHNICAL SKILLS",
    "SKILLS",
]


def find_header_index(lines: List[str], header: str) -> int:
    header_u = header.upper().strip()
    for idx, ln in enumerate(lines):
        if ln.upper().strip() == header_u:
            return idx
    return -1


def slice_section(lines: List[str], header: str) -> List[str]:
    start = find_header_index(lines, header)
    if start < 0:
        return []

    # find next header
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].upper().strip() in SECTION_HEADERS:
            end = j
            break
    return lines[start + 1 : end]


# -----------------------------
# Parse basics (name, contact)
# -----------------------------
PHONE_RE = re.compile(r"(\+?\d[\d\-\s\(\)]{7,}\d)")
EMAIL_RE = re.compile(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.IGNORECASE)
URL_RE = re.compile(r"(https?://[^\s|]+)", re.IGNORECASE)


def parse_name(lines: List[str]) -> str:
    if not lines:
        return ""
    # usually first line is name
    return lines[0].strip()


def parse_contact_line(lines: List[str]) -> Dict[str, str]:
    """
    Typically second line:
      +1 323-... | email | linkedin | location ...
    """
    contact = {"phone": "", "email": "", "linkedin": "", "github": "", "location": ""}

    if len(lines) < 2:
        return contact

    line = lines[1]

    # phone
    m = PHONE_RE.search(line)
    if m:
        contact["phone"] = re.sub(r"\s+", "", m.group(1)).replace(")(", ") (")  # keep readable-ish

    # email
    m = EMAIL_RE.search(line)
    if m:
        contact["email"] = m.group(1).strip()

    # urls
    urls = URL_RE.findall(line)
    # classify linkedin/github
    for u in urls:
        ul = u.lower()
        if "linkedin.com" in ul:
            contact["linkedin"] = u.strip()
        elif "github.com" in ul:
            contact["github"] = u.strip()

    # location: remove known parts split by |
    parts = [p.strip() for p in line.split("|")]
    # take the last part that isn't email/url/phone
    for p in reversed(parts):
        if not p:
            continue
        if EMAIL_RE.search(p):
            continue
        if URL_RE.search(p):
            continue
        if PHONE_RE.search(p) and len(p) <= 25:
            continue
        # likely location
        contact["location"] = p.strip()
        break

    return contact


def parse_summary(lines: List[str]) -> str:
    sec = slice_section(lines, "SUMMARY")
    if not sec:
        return ""
    # join into paragraph
    txt = " ".join(sec)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


# -----------------------------
# Parse education
# -----------------------------
def parse_education(lines: List[str]) -> List[Dict[str, str]]:
    sec = slice_section(lines, "EDUCATION")
    if not sec:
        return []

    # Heuristic: education entries often appear as:
    # School ... Location
    # Degree ... Dates
    # Repeat
    items: List[Dict[str, str]] = []
    i = 0
    while i < len(sec):
        school = sec[i].strip()
        degree = ""
        if i + 1 < len(sec):
            degree = sec[i + 1].strip()

        # If the "school" line looks like it is actually a continuation (very rare),
        # skip it.
        if school.upper() in SECTION_HEADERS:
            break

        items.append({"school": school, "degree": degree})
        i += 2

    # Remove obviously empty pairs
    cleaned = []
    for it in items:
        if it["school"] or it["degree"]:
            cleaned.append(it)
    return cleaned


# -----------------------------
# Parse projects
# -----------------------------
MONTH_RE = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t)?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
PROJ_TIME_RE = re.compile(rf"^(.*?)(\b{MONTH_RE}\b.*\b\d{{4}}\b.*)$", re.IGNORECASE)
BULLET_RE = re.compile(r"^[■\-\*]\s*(.+)$")


def is_project_header(line: str) -> bool:
    # project header line usually contains a month+year range
    return PROJ_TIME_RE.match(line) is not None


def parse_projects(lines: List[str]) -> List[Dict[str, object]]:
    sec = slice_section(lines, "PROJECTS")
    if not sec:
        return []

    projects: List[Dict[str, object]] = []
    cur: Optional[Dict[str, object]] = None

    def push_current():
        nonlocal cur
        if not cur:
            return
        # normalize bullets
        bullets = cur.get("bullets", [])
        if isinstance(bullets, list):
            cur["bullets"] = [b.strip() for b in bullets if str(b).strip()]
        projects.append(cur)
        cur = None

    for ln in sec:
        ln = ln.strip()

        # New project header?
        m = PROJ_TIME_RE.match(ln)
        if m:
            push_current()
            title = m.group(1).strip(" -–—|")
            time = m.group(2).strip()
            cur = {"title": title, "time": time, "bullets": []}
            continue

        # Bullet line
        bm = BULLET_RE.match(ln)
        if bm and cur is not None:
            cur["bullets"].append(bm.group(1).strip())
            continue

        # Continuation line (wrap)
        if cur is not None:
            if cur["bullets"]:
                # append to last bullet
                cur["bullets"][-1] = (cur["bullets"][-1] + " " + ln).strip()
            else:
                # sometimes description without bullet (rare)
                cur["bullets"].append(ln)

    push_current()
    return projects


# -----------------------------
# Parse skills
# -----------------------------
def split_csvish(s: str) -> List[str]:
    # split by comma; also tolerate semicolon
    parts = re.split(r"[;,]", s)
    return [p.strip() for p in parts if p.strip()]


def parse_skills(lines: List[str]) -> Dict[str, List[str]]:
    """
    From TECHNICAL SKILLS section, expect lines like:
      ■ Languages: Java, ...
      ■ Frameworks & Libraries: Spring Boot, ...
      ■ Databases & Caching: PostgreSQL, ...
      ■ Cloud & DevOps: AWS..., Docker, ...
      ■ Tools & Testing: Git, JUnit, ...
    """
    sec = slice_section(lines, "TECHNICAL SKILLS")
    if not sec:
        # sometimes header is just "SKILLS"
        sec = slice_section(lines, "SKILLS")
    if not sec:
        return {"languages": [], "frameworks": [], "tools": []}

    text = "\n".join(sec)

    def grab(label_pattern: str) -> List[str]:
        """
        IMPORTANT:
        label_pattern may contain '|' alternatives.
        We wrap it in a non-capturing group to avoid group() confusion,
        and only capture the value part after ':'.
        """
        pat = rf"(?:^|\n)\s*[■\-\*]?\s*(?:{label_pattern})\s*:\s*([^\n]+)"
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            return []
        val = (m.group(1) or "").strip()
        if not val:
            return []
        return split_csvish(val)

    languages = grab(r"Languages?")
    frameworks = grab(r"Frameworks\s*&\s*Libraries|Frameworks\s*/\s*Libraries|Frameworks(?:\s*&\s*Libs)?|Libraries")
    db = grab(r"Databases\s*&\s*Cach(?:e|ing)|Databases|Database")
    cloud = grab(r"Cloud\s*&\s*DevOps|Cloud|DevOps")
    tools_testing = grab(r"Tools\s*&\s*Testing|Tools|Testing")

    # match your webpage groups: Data / Cloud / Tools
    tools_combined = unique_preserve(db + cloud + tools_testing)

    return {
        "languages": unique_preserve(languages),
        "frameworks": unique_preserve(frameworks),
        "tools": tools_combined,
    }


# -----------------------------
# Build structured resume.json
# -----------------------------
def build_structured(text: str) -> Dict[str, object]:
    ln = lines_nonempty(text)

    name = parse_name(ln)
    contact = parse_contact_line(ln)
    summary = parse_summary(ln)
    education = parse_education(ln)
    projects = parse_projects(ln)
    skills = parse_skills(ln)

    # Subtitle is usually not inside PDF; keep a stable default or empty.
    subtitle_default = "Software Engineer • USC MS Spatial Data Science • Los Angeles"

    out: Dict[str, object] = {
        "generated_at": iso_now(),
        "source": "resume.pdf",
        "name": name or "Zhengshu Zhang",
        "subtitle": subtitle_default,
        "summary": summary,
        "resumeUrl": "./resume.pdf",
        "contact": contact,
        "education": education,
        "projects": projects,
        "skills": skills,
    }
    return out


def write_json(path: str, obj: Dict[str, object]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main() -> None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pdf_path = os.path.join(repo_root, "resume.pdf")

    raw_text = normalize_text(extract_text_from_pdf(pdf_path))

    raw_out = {
        "generated_at": iso_now(),
        "source": "resume.pdf",
        "text": raw_text,
    }
    structured = build_structured(raw_text)

    write_json(os.path.join(repo_root, "resume_raw.json"), raw_out)
    write_json(os.path.join(repo_root, "resume.json"), structured)

    print("✅ Generated resume_raw.json and resume.json")


if __name__ == "__main__":
    main()
