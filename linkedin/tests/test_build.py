import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, ".."))
import build  # noqa: E402

SAMPLE = os.path.join(ROOT, "linkedin", "content", "llm-judge-bias.json")


def sample():
    return build.load_json(SAMPLE)


class CheckRules(unittest.TestCase):
    def test_sample_is_clean(self):
        self.assertEqual(build.check(sample()), [])

    def test_rejects_em_dash(self):
        t = sample()
        t["slides"][2]["body"] += " — oops"
        self.assertTrue(any("U+2014" in p for p in build.check(t)))

    def test_needs_save_this_and_one_question(self):
        t = sample()
        t["caption"] = ["Hello.", "Which one?", "And another?"]
        problems = " ".join(build.check(t))
        self.assertIn("save this", problems)
        self.assertIn("exactly one question", problems)

    def test_slide_count(self):
        t = sample()
        t["slides"] = t["slides"][:5] + [t["slides"][-1]]
        self.assertTrue(any("8 to 12" in p for p in build.check(t)))

    def test_blocks_secrets(self):
        t = sample()
        t["caption"].insert(0, "https://hooks.zapier.com/hooks/catch/123/abc/")
        self.assertTrue(any("secret" in p for p in build.check(t)))

    def test_blocks_placeholder(self):
        t = sample()
        t["slides"][1]["body"] = "We grew {{your number}}"
        self.assertTrue(any("placeholder" in p for p in build.check(t)))


class Rendering(unittest.TestCase):
    def test_style_is_locked(self):
        css = build.read(os.path.join(ROOT, "linkedin", "theme.css")).lower()
        for token in ("#7f77dd", "#f5f4ff", "#f0fbf6", "#fef6f3", "0.5px"):
            self.assertIn(token, css)

    def test_html_has_handle_counter_and_no_chat_bar(self):
        t = sample()
        out = build.render_html(t, {"handle": "@someone"}, "file:///fonts")
        self.assertEqual(out.count('class="slide"'), len(t["slides"]))
        self.assertIn("@someone", out)
        self.assertIn("<b>09</b> / 09", out)
        self.assertNotIn("<input", out)
        self.assertNotIn("<textarea", out)

    def test_html_escapes_text(self):
        t = copy.deepcopy(sample())
        t["slides"][1]["body"] = "<script>alert(1)</script>"
        out = build.render_html(t, {"handle": "@x"}, "file:///fonts")
        self.assertNotIn("<script>", out)

    def test_build_writes_files(self):
        with tempfile.TemporaryDirectory() as d:
            rc = build.main([SAMPLE, "--out", d, "--no-pdf"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "carousel.html")))
            self.assertTrue(os.path.exists(os.path.join(d, "caption.txt")))


class RepoIsSafeToPublish(unittest.TestCase):
    def test_no_secrets_in_linkedin_folder(self):
        pats = [re.compile(p) for p in build.SECRET_PATTERNS]
        for base, _dirs, files in os.walk(os.path.join(ROOT, "linkedin")):
            if "tests" in base or "fonts" in base or "out" in base.split(os.sep):
                continue
            for name in files:
                if name.endswith((".json", ".py", ".css", ".md", ".txt")):
                    text = build.read(os.path.join(base, name))
                    for pat in pats:
                        self.assertIsNone(pat.search(text), f"possible secret in {name}")


if __name__ == "__main__":
    unittest.main()
