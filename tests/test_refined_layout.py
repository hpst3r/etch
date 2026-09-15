"""Source-regression tests for the refined TOC layout work (feat/refine-toc-layout).

These are *source* (text) regression tests: they assert on the committed source of
the Hugo templates, JS and CSS that make up the refined TOC layout. They are
intentionally regex-based and whitespace tolerant so formatting-only edits do not
break them. No network, no rendering, no production file is touched.

Run:  python3 -m unittest -v tests/test_refined_layout.py
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MAIN_CSS = "assets/css/main.css"
WIDTH_CSS = "assets/css/width.css"
HAS_TOC = "layouts/partials/has-toc.html"
TOC = "layouts/partials/toc.html"
TOC_SCROLL = "layouts/partials/toc-scroll.html"
BASEOF = "layouts/_default/baseof.html"
SINGLE = "layouts/_default/single.html"

REQUIRED_FILES = (
    MAIN_CSS,
    WIDTH_CSS,
    HAS_TOC,
    TOC,
    TOC_SCROLL,
    BASEOF,
    SINGLE,
)


def slurp(rel_path):
    """Return the text of a required source file, failing (not erroring) if absent."""
    path = REPO_ROOT / rel_path
    if not path.is_file():
        raise AssertionError("required source file is missing: %s" % rel_path)
    return path.read_text(encoding="utf-8")


def css_rules(css):
    """Yield (selector, body) pairs for flat CSS rules; nested selectors are kept as-is."""
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)
    ]


def media_block(css, min_width_px):
    """Return the body of the first @media block declaring min-width: <N>px."""
    pattern = re.compile(
        r"@media[^{]*min-width\s*:\s*%dpx[^{]*\{(.*?)\n\}" % min_width_px, re.S
    )
    match = pattern.search(css)
    return match.group(1) if match else ""


class RequiredSources(unittest.TestCase):
    """Every file the layout contract spans must be present on disk."""

    def test_required_source_files_exist(self):
        missing = [name for name in REQUIRED_FILES if not (REPO_ROOT / name).is_file()]
        self.assertEqual([], missing, "missing required source files: %s" % missing)


class HasTocPartial(unittest.TestCase):
    """layouts/partials/has-toc.html gates the TOC on real heading count."""

    def test_counts_anchors_with_findre(self):
        text = slurp(HAS_TOC)
        self.assertRegex(
            text,
            r"findRE\s*(?:\(|\s)",
            "has-toc.html must count anchors with Hugo's findRE",
        )

    def test_threshold_is_at_least_three(self):
        text = slurp(HAS_TOC)
        self.assertRegex(
            text,
            r"\bge\s+.{0,120}?\b3\b",
            "has-toc.html must gate on 'ge ... 3' (the 3-anchor threshold)",
        )

    def test_respects_toc_false_param(self):
        text = slurp(HAS_TOC)
        self.assertRegex(
            text,
            r"\.Params\.toc",
            "has-toc.html must consult .Params.toc",
        )
        self.assertRegex(
            text,
            r"\.Params\.toc[^\n]*?false",
            "has-toc.html must treat .Params.toc == false as 'no TOC'",
        )


class HasTocCallSites(unittest.TestCase):
    """All three gated call sites delegate to the has-toc partial."""

    CALL_SITES = (TOC, TOC_SCROLL, BASEOF)

    def test_every_call_site_uses_has_toc_partial(self):
        pattern = re.compile(r'partial\s+"has-toc\.html"\s+\.')
        for rel in self.CALL_SITES:
            text = slurp(rel)
            self.assertRegex(
                text,
                pattern,
                '%s must gate on `partial "has-toc.html" .`' % rel,
            )


class TocMarkup(unittest.TestCase):
    """toc.html renders an accessible, labelled aside."""

    def test_aside_has_on_this_page_aria_label(self):
        text = slurp(TOC)
        self.assertRegex(
            text,
            r'aria-label\s*=\s*"On this page"',
            'toc.html must set aria-label="On this page" on the TOC aside',
        )

    def test_aside_has_visible_toc_label(self):
        text = slurp(TOC)
        self.assertRegex(
            text,
            r'class\s*=\s*"[^"]*\btoc-label\b[^"]*"[^>]*>\s*On this page',
            "toc.html must render a visible .toc-label reading 'On this page'",
        )

    def test_aside_element_present(self):
        text = slurp(TOC)
        self.assertRegex(text, r"<aside\b", "toc.html must render an <aside> for the TOC")


class SingleArticle(unittest.TestCase):
    """layouts/_default/single.html tags the article for wide-screen layout."""

    def test_article_has_post_article_class(self):
        text = slurp(SINGLE)
        self.assertRegex(
            text,
            r'<article[^>]*class\s*=\s*"[^"]*\bpost-article\b[^"]*"',
            'single.html must render <article class="post-article">',
        )


class TocScrollScript(unittest.TestCase):
    """toc-scroll.html uses scroll-position + hash history instead of IntersectionObserver."""

    REQUIRED_TOKENS = (
        "aria-current",
        "requestAnimationFrame",
        "hashchange",
        "popstate",
    )
    FORBIDDEN_TOKENS = (
        "IntersectionObserver",
        "centerTocVertically",
        "toc.style.top",
    )

    def test_required_js_tokens_present(self):
        text = slurp(TOC_SCROLL)
        for token in self.REQUIRED_TOKENS:
            with self.subTest(token=token):
                self.assertIn(
                    token,
                    text,
                    "toc-scroll.html JS must contain %r" % token,
                )

    def test_forbidden_js_tokens_absent(self):
        text = slurp(TOC_SCROLL)
        for token in self.FORBIDDEN_TOKENS:
            with self.subTest(token=token):
                self.assertNotIn(
                    token,
                    text,
                    "toc-scroll.html JS must no longer contain %r" % token,
                )


class MainCss(unittest.TestCase):
    """Reading-width, TOC and header/footer border rules in main.css."""

    def setUp(self):
        self.css = slurp(MAIN_CSS)
        self.rules = css_rules(self.css)

    def test_content_width_variable_is_710px(self):
        self.assertRegex(
            self.css,
            r"--content-width\s*:\s*710px",
            "main.css must declare --content-width: 710px",
        )

    def test_post_article_font_size_15px(self):
        matches = [
            body
            for sel, body in self.rules
            if re.search(r"\.post-article\b", sel)
            and re.search(r"font-size\s*:\s*15px", body)
        ]
        self.assertTrue(
            matches,
            "main.css must set .post-article { font-size: 15px; }",
        )

    def test_wide_toc_breakpoint_is_1280px(self):
        self.assertRegex(
            self.css,
            r"@media[^{]*min-width\s*:\s*1280px",
            "main.css must switch to the wide TOC layout at min-width: 1280px",
        )

    def test_wide_toc_width_is_220px(self):
        block = media_block(self.css, 1280)
        if not block:
            # Fall back to any .toc rule declaring the wide width.
            block = "\n".join(
                body
                for sel, body in self.rules
                if re.search(r"\.toc\b", sel)
                and re.search(r"width\s*:\s*220px", body)
            )
        self.assertRegex(
            block,
            r"width\s*:\s*220px",
            "the 1280px wide TOC breakpoint must size the TOC at width: 220px",
        )

    def test_active_toc_link_uses_heading_color_and_weight_500(self):
        active = [
            (sel, body)
            for sel, body in self.rules
            if re.search(r"\.toc-active\b", sel) and "::after" not in sel
        ]
        self.assertTrue(active, "main.css must style the active TOC link (.toc-active)")
        ok = [
            (sel, body)
            for sel, body in active
            if re.search(r"color\s*:\s*var\(\s*--heading-color\s*\)", body)
            and re.search(r"font-weight\s*:\s*500", body)
        ]
        self.assertTrue(
            ok,
            "active TOC link must use color: var(--heading-color) and font-weight: 500; "
            "got selectors %r" % [sel for sel, _ in active],
        )

    def test_active_toc_marker_after_uses_anchor_color(self):
        markers = [
            (sel, body)
            for sel, body in self.rules
            if re.search(r"\.toc-active\b", sel) and "::after" in sel
        ]
        self.assertTrue(
            markers,
            "main.css must draw an active TOC ::after marker (.toc-active::after)",
        )
        ok = [
            body
            for _, body in markers
            if re.search(r"var\(\s*--anchor-color\s*\)", body)
        ]
        self.assertTrue(
            ok,
            "the active TOC ::after marker must be coloured with var(--anchor-color)",
        )

    def test_narrow_toc_has_no_top_border(self):
        matches = [
            body
            for sel, body in self.rules
            if re.search(r"(?:^|[,\s])\.toc\b", sel)
            and re.search(r"border-top\s*:\s*0", body)
        ]
        self.assertTrue(
            matches,
            "narrow .toc must drop its top border (border-top: 0)",
        )

    def test_narrow_toc_has_bottom_border(self):
        matches = [
            body
            for sel, body in self.rules
            if re.search(r"(?:^|[,\s])\.toc\b", sel)
            and re.search(r"border-bottom\s*:\s*[^;}]+", body)
        ]
        self.assertTrue(
            matches,
            "narrow .toc must carry a bottom border (border-bottom: ...)",
        )

    def test_header_has_bottom_border(self):
        matches = [
            body
            for sel, body in self.rules
            if "post-header" not in sel
            and re.search(r"(?:^|[,\s])header(?![-\w])", sel)
            and re.search(r"border-bottom\s*:\s*[^;}]+", body)
        ]
        self.assertTrue(
            matches,
            "the page header must carry a bottom border",
        )

    def test_footer_has_no_top_border(self):
        matches = [
            (sel, body)
            for sel, body in self.rules
            if re.search(r"(?:^|[,\s])footer(?![-\w])", sel)
            and re.search(r"(?<![-a-z])border-top\s*:\s*(?!0\b|none\b)[^;}]+", body)
        ]
        self.assertEqual(
            [],
            [sel for sel, _ in matches],
            "the footer must not carry a top border",
        )


class WidthCss(unittest.TestCase):
    """width.css no longer keys widths off the body.has-toc class."""

    def test_width_css_has_no_body_has_toc(self):
        text = slurp(WIDTH_CSS)
        self.assertNotRegex(
            text,
            r"body\.has-toc",
            "width.css must not contain body.has-toc rules any more",
        )


if __name__ == "__main__":
    unittest.main()
