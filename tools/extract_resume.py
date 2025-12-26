# tools/extract_resume.py
# resume.pdf -> resume_raw.json (text) + resume.json (structured)

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "resume.pdf"
RAW_JSON = ROOT / "resume_raw.json"
OUT_JSON = ROOT / "resume.json"

MONTH_RE = re.compile(
    r"\b(Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
BULLET_PREFIXES = ("■", "◼", "•", "-", "–", "—")


def normalize_heading(s: str) -> str:
    # Keep only letters, numbers; uppercase
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def find_heading_index(lines, heading: str):
    target = normalize_heading(heading)
    for idx, ln in enumerate(lines):
        if normalize_heading(ln) == target:
            return idx
    return None


def extract_text_by_words(pdf_path: Path) -> str:
    """More stable than page.extract_text(): rebuild lines from extracted words."""
    parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=True)
            if not words:
                # fallback
                txt = page.extract_text() or ""
                parts.append(txt)
                continue

            # sort by (top, x0)
            words.sort(key=lambda w: (w["top"], w["x0"]))

            lines = []
            cur = []
            cur_top = None

            for w in words:
                t = w["top"]
                text = (w.get("text") or "").strip()
                if not text:
                    continue

                if cur_top is None:
                    cur_top = t
                    cur = [text]
                    continue

                # new line if vertical gap is large
                if abs(t - cur_top) > 3.0:
                    lines.append(" ".join(cur).strip())
                    cur = [text]
                    cur_top = t
                else:
                    cur.append(text)

            if cur:
                lines.append(" ".join(cur).strip())

            page_text = "\n".join([ln for ln in lines if ln])
            parts.append(page_text)

    text = "\n".join(parts)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def split_name_if_needed(name: str) -> str:
    # "ZhengshuZhang" -> "Zhengshu Zhang"
    if " " not in name and re.search(r"[a-z][A-Z]", name):
        name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return name.strip()


def parse_contact(lines):
    phone = email = linkedin = location = ""
    # look in first few lines for a pipe contact line
    for ln in lines[0:8]:
        if "|" in ln:
            parts = [p.strip() for p in ln.split("|")]
            for p in parts:
                if "@" in p:
                    email = p
                elif "linkedin.com" in p:
                    linkedin = p
                elif re.search(r"\+?\d[\d\s-]{8,}", p):
                    phone = p.replace(" ", "")
                else:
                    location = p
            break
    return phone, email, linkedin, location


def block(lines, start_idx, end_idx):
    if start_idx is None:
        return []
    s = start_idx + 1
    e = end_idx if end_idx is not None else len(lines)
    return [ln for ln in lines[s:e] if ln.strip()]


def parse_education(edu_lines):
    entries = []
    buf = []

    def flush(buf_):
        if not buf_:
            return
        school = buf_[0].strip()
        degree = " ".join(buf_[1:]).strip() if len(buf_) > 1 else ""
        # cleanup: remove trailing duplicated spaces
        school = re.sub(r"\s{2,}", " ", school)
        degree = re.sub(r"\s{2,}", " ", degree)
        entries.append({"school": school, "degree": degree})

    for ln in edu_lines:
        # new school line heuristic
        if re.search(r"\b(University|College|Institute)\b", ln) and not re.search(
            r"\b(Master|Bachelor|PhD|Doctor)\b", ln, re.IGNORECASE
        ):
            flush(buf)
            buf = [ln]
        else:
            if not buf:
                buf = [ln]
            else:
                buf.append(ln)

    flush(buf)
    # keep top 2
    return entries[:2]


def parse_projects(proj_lines):
    projects = []
    cur = None

    def flush():
        nonlocal cur
        if cur:
            cur["bullets"] = [b for b in cur["bullets"] if b.strip()]
            projects.append(cur)
        cur = None

    for ln in proj_lines:
        s = ln.strip()
        if not s:
            continue

        is_bullet = s.startswith(BULLET_PREFIXES)
        has_date = bool(MONTH_RE.search(s) and YEAR_RE.search(s))

        # header line (project name + date range)
        if (not is_bullet) and has_date:
            flush()
            # split header: everything before first month = name
            m = MONTH_RE.search(s)
            name = s[: m.start()].strip(" -–—\t") if m else s
            time = s[m.start():].strip() if m else ""
            cur = {"name": name, "time": time, "bullets": []}
            continue

        # bullet
        if is_bullet and cur:
            b = s.lstrip("".join(BULLET_PREFIXES)).strip()
            cur["bullets"].append(b)
        else:
            # continuation lines
            if cur and cur["bullets"]:
                cur["bullets"][-1] = (cur["bullets"][-1] + " " + s).strip()

    flush()
    return projects[:6]


def parse_skills(skill_lines):
    text = "\n".join(skill_lines)

    def grab(label: str):
        # match "Languages: xxx" even if bullet in front
        m = re.search(rf"{label}\s*:\s*(.+)", text, re.IGNORECASE)
        if not m:
            return []
        val = m.group(1).strip()
        # stop if it accidentally eats next line label
        val = re.split(r"\n\s*[\u25A0\u25FC■◼•-]", val)[0].strip()
        return [x.strip() for x in val.split(",") if x.strip()]

    languages = grab("Languages")
    frameworks = grab("Frameworks\s*&\s*Libraries|Frameworks\s*/\s*Libraries|Frameworks")
    db = grab("Databases\s*&\s*Caching|Databases")
    cloud = grab("Cloud\s*&\s*DevOps|Cloud")
    tools = grab("Tools\s*&\s*Testing|Tools")

    merged_tools = db + cloud + tools
    return {
        "languages": languages,
        "frameworks": frameworks,
        "tools": merged_tools,
    }


def main():
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"Cannot find {PDF_PATH}")

    text = extract_text_by_words(PDF_PATH)

    RAW_JSON.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "resume.pdf",
                "text": text,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    name = split_name_if_needed(raw_lines[0] if raw_lines else "Your Name")
    phone, email, linkedin, location = parse_contact(raw_lines)

    idx_sum = find_heading_index(raw_lines, "SUMMARY")
    idx_edu = find_heading_index(raw_lines, "EDUCATION")
    idx_proj = find_heading_index(raw_lines, "PROJECTS")
    idx_skill = find_heading_index(raw_lines, "TECHNICAL SKILLS")

    summary = " ".join(block(raw_lines, idx_sum, idx_edu)).strip()

    education = parse_education(block(raw_lines, idx_edu, idx_proj))
    projects = parse_projects(block(raw_lines, idx_proj, idx_skill))
    skills = parse_skills(block(raw_lines, idx_skill, None))

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "resume.pdf",
        "name": name,
        "subtitle": "Software Engineer • USC MS Spatial Data Science • Los Angeles",
        "summary": summary,
        "resumeUrl": "./resume.pdf",
        "contact": {
            "phone": phone,
            "email": email,
            "linkedin": linkedin,
            "github": "https://github.com/forestzs",
            "location": location,
        },
        "education": education,
        "projects": projects,
        "skills": skills,
    }

    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
