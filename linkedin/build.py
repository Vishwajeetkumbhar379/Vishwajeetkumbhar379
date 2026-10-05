#!/usr/bin/env python3
"""Topic file in -> carousel PDF + caption out. Nothing is ever posted from here.

    python3 linkedin/build.py linkedin/content/my-topic.json

Writes linkedin/out/<slug>/: carousel.pdf, carousel.html, caption.txt, preview/*.png
Uses only the Python standard library, headless Chromium (for the PDF) and
pdftoppm (for the preview images).
"""
import argparse
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TINTS = ["purple", "teal", "coral"]

# Characters and patterns that must never reach a public post or repo.
BAD_CHARS = "—–‘’“”…​‌‍⁠﻿­ "
SECRET_PATTERNS = [
    r"hooks\.zapier\.com", r"https?://[^\s]*webhook", r"\bsk-[A-Za-z0-9_-]{16,}",
    r"\bBearer\s+[A-Za-z0-9._-]{16,}", r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*\S{8,}",
    r"\bAKIA[0-9A-Z]{16}\b", r"\bghp_[A-Za-z0-9]{20,}",
]


class BuildError(Exception):
    pass


def words(text):
    return len(re.findall(r"\S+", text))


def esc(text):
    """Escape for HTML, then allow **bold** and *italic* for emphasis."""
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\*(.+?)\*", r"<em>\1</em>", out)
    return out


def load_config():
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    handle = os.environ.get("LINKEDIN_HANDLE") or cfg["handle"]
    return {"handle": handle if handle.startswith("@") else "@" + handle}


# ---------------------------------------------------------------- checks

def slide_text(slide):
    parts = []
    for key, val in slide.items():
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            for item in val:
                parts.extend(item.values() if isinstance(item, dict) else [item])
    return parts


def check(topic):
    """Return a list of problems. An empty list means the content is clean."""
    problems = []
    slides = topic.get("slides", [])
    if not 8 <= len(slides) <= 12:
        problems.append(f"Need 8 to 12 slides, found {len(slides)}.")
    if slides and slides[0].get("kind") != "cover":
        problems.append("Slide 1 must be kind 'cover'.")
    if slides and slides[-1].get("kind") != "cta":
        problems.append("The last slide must be kind 'cta'.")

    for n, s in enumerate(slides, 1):
        title = s.get("title", "")
        limit = 6 if s.get("kind") == "cover" else 8
        if title and words(title) > limit:
            problems.append(f"Slide {n}: headline has {words(title)} words, max {limit}.")
        for field in ("body", "fix", "sub"):
            if field in s and words(s[field]) > 30:
                problems.append(f"Slide {n}: '{field}' has {words(s[field])} words, max 30. Split the slide.")

    caption = "\n".join(topic.get("caption", []))
    if not caption.strip():
        problems.append("Caption is empty.")
    if not re.search(r"save this", caption, re.I):
        problems.append("Caption needs a 'save this' call to action.")
    if caption.strip() and not caption.strip().endswith("?"):
        problems.append("Caption must end with one open question.")
    if caption.count("?") != 1:
        problems.append(f"Caption should hold exactly one question, found {caption.count('?')}.")
    if len(caption) > 3000:
        problems.append("Caption is over LinkedIn's 3000 character limit.")

    blob = "\n".join(t for s in slides for t in slide_text(s)) + "\n" + caption
    for ch in BAD_CHARS:
        if ch in blob:
            problems.append(f"Found a character AI text often leaves behind: U+{ord(ch):04X}. Use plain punctuation.")
    if "{{" in blob:
        problems.append("A {{placeholder}} is still in the text. Fill it in or remove it.")
    for pat in SECRET_PATTERNS:
        if re.search(pat, blob):
            problems.append("Text looks like it contains a secret or webhook URL. Remove it.")
            break
    slop = os.path.join(HERE, "..", ".claude", "skills", "li-human", "slop.json")
    if os.path.exists(slop):
        lex = json.load(open(slop, encoding="utf-8"))
        for entry in lex.get("words", []) + lex.get("phrases", []):
            if re.search(r"\b" + re.escape(entry["find"]) + r"\b", blob, re.I):
                problems.append(f"AI-sounding word: '{entry['find']}'. Try '{entry['replace'] or 'deleting it'}'.")
    return problems


# ---------------------------------------------------------------- rendering

def badge(text, soft=False):
    if not text:
        return ""
    return f'<div class="badge{" soft" if soft else ""}"><span class="dot"></span>{esc(text)}</div>'


def render_slide(i, total, s, cfg):
    tint = s.get("tint") or TINTS[(i - 1) % 3]
    kind = s["kind"]
    inner = []
    if kind == "cover":
        inner += [badge(s.get("badge")), '<div class="spacer"></div>', f'<h1>{esc(s["title"])}</h1>',
                  f'<p class="sub">{esc(s["sub"])}</p>', '<div class="spacer"></div>',
                  '<div class="swipe">Swipe &rarr;</div>']
    elif kind in ("stake", "point"):
        inner += [badge(s.get("badge")), f'<h2>{esc(s["title"])}</h2>', f'<p class="body">{esc(s["body"])}</p>']
        if s.get("demo"):
            drows = "".join(f'<div class="row two small"><div class="k">{esc(r["k"])}</div><div class="v">{esc(r["v"])}</div></div>'
                            for r in s["demo"])
            inner += ['<div class="spacer"></div>', f'<div class="demo"><div class="demo-label">Illustration</div>{drows}</div>']
        if s.get("fix"):
            inner += [' <div class="spacer"></div>' if not s.get("demo") else '',
                      f'<div class="box"><div class="label">{esc(s.get("fix_label", "The fix"))}</div>'
                      f'<div class="text">{esc(s["fix"])}</div></div>']
        elif s.get("source"):
            inner += ['<div class="spacer"></div>', f'<p class="source">{esc(s["source"])}</p>']
    elif kind == "stack":
        rows = "".join(f'<div class="row"><div class="arrow">&rarr;</div><div>{esc(t)}</div></div>' for t in s["items"])
        inner += [badge(s.get("badge")), f'<h2>{esc(s["title"])}</h2>', f'<div class="rows">{rows}</div>']
        if s.get("body"):
            inner += ['<div class="spacer"></div>', f'<p class="body">{esc(s["body"])}</p>']
    elif kind == "recap":
        rows = "".join(f'<div class="row two"><div class="k">{esc(r["k"])}</div><div class="v">{esc(r["v"])}</div></div>'
                       for r in s["rows"])
        inner += [badge(s.get("badge")), f'<h2>{esc(s["title"])}</h2>', f'<div class="rows">{rows}</div>']
        if s.get("source"):
            inner += ['<div class="spacer"></div>', f'<p class="source">{esc(s["source"])}</p>']
    elif kind == "cta":
        inner += [badge(s.get("badge")), '<div class="spacer"></div>', f'<h1>{esc(s["title"])}</h1>',
                  f'<p class="sub">{esc(s["sub"])}</p>', '<div class="spacer"></div>',
                  f'<div class="cta-pill">{esc(s["button"])}</div>']
    else:
        raise BuildError(f"Slide {i}: unknown kind '{kind}'.")
    return (f'<section class="slide"><div class="top"><div class="handle"><div class="avatar">'
            f'{esc(cfg["handle"][1:2].upper())}</div>{esc(cfg["handle"])}</div>'
            f'<div class="counter"><b>{i:02d}</b> / {total:02d}</div></div>'
            f'<div class="card tint-{tint}">{"".join(inner)}</div></section>')


def render_html(topic, cfg, fonts_dir):
    css = open(os.path.join(HERE, "theme.css"), encoding="utf-8").read().replace("FONTS", fonts_dir)
    slides = topic["slides"]
    body = "".join(render_slide(i, len(slides), s, cfg) for i, s in enumerate(slides, 1))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(topic["topic"])}</title>'
            f'<style>{css}</style></head><body>{body}</body></html>')


def find_chrome():
    for path in [os.environ.get("CHROME_PATH", "")] + glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"):
        if path and os.path.exists(path):
            return path
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    raise BuildError("Chromium not found. Set CHROME_PATH to its location.")


def make_pdf(html_path, pdf_path):
    profile = tempfile.mkdtemp(prefix="chrome-")
    try:
        cmd = [find_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
               f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}", "file://" + os.path.abspath(html_path)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not os.path.exists(pdf_path):
        raise BuildError("Chromium did not produce a PDF.")


def make_previews(pdf_path, out_dir):
    if not shutil.which("pdftoppm"):
        return
    prev = os.path.join(out_dir, "preview")
    os.makedirs(prev, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", "72", "-png", pdf_path, os.path.join(prev, "slide")], check=True, stderr=subprocess.DEVNULL)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("topic_file")
    ap.add_argument("--out", help="output folder (default linkedin/out/<slug>)")
    ap.add_argument("--no-pdf", action="store_true", help="only check the content and write HTML + caption")
    args = ap.parse_args(argv)

    topic = json.load(open(args.topic_file, encoding="utf-8"))
    problems = check(topic)
    if problems:
        print("Fix these first:")
        for p in problems:
            print("  -", p)
        return 1

    cfg = load_config()
    out = args.out or os.path.join(HERE, "out", topic["slug"])
    os.makedirs(out, exist_ok=True)
    html_path = os.path.join(out, "carousel.html")
    fonts = "file://" + os.path.join(HERE, "fonts")
    open(html_path, "w", encoding="utf-8").write(render_html(topic, cfg, fonts))
    open(os.path.join(out, "caption.txt"), "w", encoding="utf-8").write("\n".join(topic["caption"]) + "\n")
    if not args.no_pdf:
        pdf = os.path.join(out, "carousel.pdf")
        make_pdf(html_path, pdf)
        make_previews(pdf, out)
    print(f"Done. Open {out}/")
    print("Nothing was posted. Review carousel.pdf and caption.txt, then post by hand.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as e:
        print("Error:", e)
        sys.exit(2)
