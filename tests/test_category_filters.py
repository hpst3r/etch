"""Source-regression tests for the metadata-derived homepage category filters
(feat/category-filters).

These are *source* (text) regression tests: they assert on the committed source of
the Hugo templates, JS and CSS that make up the homepage category filters. They are
intentionally regex-based and whitespace tolerant so formatting-only edits do not
break them. No network, no rendering, and no production/content file is touched.

Contract under test
-------------------
* ``layouts/partials/posts.html`` renders the filter UI only when categories exist.
* Filter labels come from the real Hugo category taxonomy / post metadata and are
  never hard-coded names.
* An ``All`` control is always present alongside the real categories.
* Controls are native ``<button type="button">``, carry ``data-category-filter``
  and expose ``aria-pressed``.
* Post rows expose normalized ``data-categories`` membership.
* The JS is gated / a no-op when the filter UI is absent, filters rows by category
  membership, keeps exactly one control ``aria-pressed="true"``, and never uses
  ``innerHTML`` / ``eval``.
* ``.category-filters`` is styled as plain text controls: transparent background,
  no border box, no border-radius/pill, visible keyboard focus, an active underline
  drawn directly under the text via ``text-decoration`` + ``underline-offset``, and
  wrapping on narrow screens.
* No content/front-matter file is changed by this feature.

The tests deliberately allow either architecture: the JS may live inside
``posts.html`` or in a new ``layouts/partials/category-filter.html`` partial.

Run:  python3 -m unittest -v tests/test_category_filters.py
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

POSTS = "layouts/partials/posts.html"
CATEGORY_FILTER_PARTIAL = "layouts/partials/category-filter.html"
MAIN_CSS = "assets/css/main.css"
LI = "layouts/_default/li.html"
CONTENT_ROOT = "exampleSite/content"

# The filter architecture may keep its markup/JS in posts.html directly or extract
# it into a dedicated partial; both are acceptable.
FILTER_SOURCES = (POSTS, CATEGORY_FILTER_PARTIAL, LI)


def slurp(rel_path):
    """Return the text of a required source file, failing (not erroring) if absent."""
    path = REPO_ROOT / rel_path
    if not path.is_file():
        raise AssertionError("required source file is missing: %s" % rel_path)
    return path.read_text(encoding="utf-8")


def flat(text):
    """Collapse runs of whitespace so regexes can ignore formatting-only edits."""
    return re.sub(r"\s+", " ", text)


def filter_source_text():
    """Concatenated text of every file that may legitimately carry filter markup/JS."""
    parts = []
    for rel in FILTER_SOURCES:
        path = REPO_ROOT / rel
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def css_rules(css):
    """Yield (selector, body) pairs for flat CSS rules; nested selectors stay as-is."""
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)
    ]


def category_filter_rules(css):
    """Every CSS rule whose selector targets the category-filter controls."""
    return [(sel, body) for sel, body in css_rules(css) if "category-filter" in sel]


class RequiredSources(unittest.TestCase):
    """Every file the category-filter contract spans must be present on disk."""

    def test_posts_partial_exists(self):
        self.assertTrue(
            (REPO_ROOT / POSTS).is_file(),
            "layouts/partials/posts.html must exist",
        )

    def test_main_css_exists(self):
        self.assertTrue(
            (REPO_ROOT / MAIN_CSS).is_file(),
            "assets/css/main.css must exist",
        )


class FilterUiGating(unittest.TestCase):
    """The filter UI is rendered only when the site actually has categories."""

    def setUp(self):
        self.text = slurp(POSTS)
        self.flat = flat(self.text)

    def test_ui_is_conditional_on_categories(self):
        # The guard may be written inline over categories, or (as here) bound to a
        # boolean variable such as `$showFilters := and $isHome (gt (len $categories) 0)`
        # and then used by an `if $showFilters` block. Both are accepted.
        binding = re.search(
            r"""\$showFilters\s*:=[^\n]{0,120}?\band\b[^\n]{0,40}?\$isHome"""
            r"""[^\n]{0,60}?\bgt\b[^\n]{0,60}?\blen\b[^\n]{0,60}?\$categories""",
            self.flat,
        )
        inline_guard = re.search(
            r"""\bif\b[^\n]*?(?:\bcategor\w*\b|\btaxonomies\b)""",
            self.text,
            re.I,
        )
        guard = binding or inline_guard
        self.assertIsNotNone(
            guard,
            "posts.html must guard the filter UI with an `if` over the real "
            "category taxonomy / collected categories (e.g. "
            "`$showFilters := and $isHome (gt (len $categories) 0)` followed by "
            "`if $showFilters`)",
        )
        conditional = re.search(
            r"""\bif\b[^\n]{0,40}?\$showFilters\b""",
            self.flat,
        )
        if conditional is None:
            self.fail(
                "the bound visibility flag must actually gate rendering via "
                "`if $showFilters`"
            )
        controls = re.search(r"""data-category-filter""", self.text)
        if controls is None:
            self.fail("posts.html must render the category filter controls")
        self.assertLess(
            conditional.start(),
            controls.start(),
            "the `if $showFilters` gate must come before the filter controls",
        )

    def test_no_ui_when_no_categories(self):
        # There must be an else/end structure so a category-less site renders nothing,
        # i.e. the guard wraps the whole filter block rather than a single label.
        self.assertRegex(
            self.text,
            r"""\{\{-?\s*else\b|\{\{-?\s*end\b""",
            "the categories guard must close with `end` (or carry an `else`) so the "
            "filter UI is simply absent when no categories exist",
        )

    def test_all_control_present(self):
        self.assertRegex(
            self.flat,
            r"""(?:data-category-filter\s*=\s*["']__all__["']|data-category-filter\s*=\s*"all"|>\s*All\s*<)""",
            "posts.html must render an `All` control for the category filters, "
            "addressed by the `__all__` sentinel",
        )
        self.assertRegex(
            self.flat,
            r"""posts\.filter\.all""",
            "the `All` control label must come from the posts.filter.all i18n "
            "string, not a hard-coded literal",
        )


class LabelDerivation(unittest.TestCase):
    """Labels come from Hugo taxonomy/post metadata, never hard-coded names."""

    def setUp(self):
        self.text = slurp(POSTS)

    def test_labels_derive_from_taxonomy_or_post_metadata(self):
        derives = re.search(
            r"""(?:\.Site\.Taxonomies|\.GetTerms|\.Terms|\.Params\.categories|"""
            r"""\bcategor\w*[^\n]{0,60}?\brange\b|\brange\b[^\n]{0,80}?\bcategor\w*)""",
            self.text,
            re.I,
        )
        self.assertIsNotNone(
            derives,
            "posts.html must derive filter labels from the Hugo category taxonomy "
            "or post metadata (e.g. `.Site.Taxonomies.categories`, `.GetTerms`, "
            "`.Params.categories`), not from a literal list",
        )

    def test_no_hard_coded_category_names(self):
        # A hard-coded literal category name would mean the labels are not derived
        # from metadata. Guard against an obvious literal label list. The `__all__`
        # sentinel (and the older `all` sentinel) are reserved control tokens, not
        # category names, so they are exempt.
        hard_coded = re.search(
            r"""data-category-filter\s*=\s*["'](?!__all__["']|all["'])\w+["']""",
            self.text,
            re.I,
        )
        self.assertIsNone(
            hard_coded,
            "filter labels must not be hard-coded; found a literal "
            "data-category-filter value instead of a templated label",
        )


class ControlMarkup(unittest.TestCase):
    """Controls are native, accessible buttons exposing the filter contract."""

    def setUp(self):
        self.text = filter_source_text()
        self.flat = flat(self.text)

    def test_controls_are_native_type_button(self):
        buttons = re.findall(r"""<button\b[^>]*>""", self.flat, re.I)
        self.assertTrue(buttons, "filter controls must be native <button> elements")
        filtered = [
            b for b in buttons
            if re.search(r"""data-category-filter""", b)
        ]
        self.assertTrue(
            filtered,
            "at least one <button> must carry data-category-filter",
        )
        for button in filtered:
            with self.subTest(button=button):
                self.assertRegex(
                    button,
                    r"""type\s*=\s*["']button["']""",
                    "filter controls must be <button type=\"button\"> so they never "
                    "submit a form",
                )

    def test_controls_expose_data_category_filter(self):
        self.assertRegex(
            self.flat,
            r"""data-category-filter\s*=""",
            "filter controls must carry a data-category-filter attribute",
        )

    def test_controls_expose_aria_pressed(self):
        buttons = re.findall(r"""<button\b[^>]*>""", self.flat, re.I)
        filtered = [b for b in buttons if "data-category-filter" in b]
        self.assertTrue(filtered, "expected at least one data-category-filter button")
        unpressed = [b for b in filtered if not re.search(r"""aria-pressed""", b)]
        self.assertEqual(
            [],
            unpressed,
            "every filter control must expose aria-pressed; missing on: %r" % unpressed,
        )

    def test_live_status_exists_before_interaction(self):
        self.assertRegex(
            self.flat,
            r"""role\s*=\s*["']status["'][^>]*aria-live\s*=\s*["']polite["']""",
            "a polite status region must exist in the initial DOM",
        )

    def test_no_script_fallback_links_to_categories(self):
        self.assertRegex(
            self.flat,
            r"""<noscript>.*?/categories/.*?</noscript>""",
            "the no-JavaScript fallback must link to Hugo's category pages",
        )


class PostRowMetadata(unittest.TestCase):
    """Post rows expose normalized data-categories membership."""

    def setUp(self):
        self.text = filter_source_text()
        self.flat = flat(self.text)

    def test_row_container_targets_data_categories(self):
        self.assertRegex(
            self.flat,
            r"""data-categories\s*=""",
            "post rows / the JS must key off a data-categories attribute",
        )

    def test_categories_normalized_lowercase(self):
        # Normalization (lowercase + join) is what lets membership matching work.
        normalizes = re.search(
            r"""\.categories\b[^\n]{0,120}?\blower\b|\blower\b[^\n]{0,40}?\bcategor\w*|"""
            r"""(?:delimit|join)\b[^\n]{0,80}?\bcategor\w*|\bcategor\w*[^\n]{0,80}?"""
            r"""(?:delimit|join)\b""",
            self.flat,
            re.I,
        )
        self.assertIsNotNone(
            normalizes,
            "data-categories values must be normalized (lowercased and/or joined "
            "into a stable membership string)",
        )


class FilterScript(unittest.TestCase):
    """The filter JS is gated, membership-based, and free of innerHTML/eval."""

    def setUp(self):
        self.text = filter_source_text()
        self.flat = flat(self.text)

    def test_script_is_gated_on_presence_of_filter_ui(self):
        guarded = re.search(
            r"""(?:querySelector(?:All)?\s*\(\s*["'][^"']*\.category-filters|"""
            r"""getElementById\s*\(\s*["'][^"']*["']|"""
            r"""if\s*\(\s*!\s*\w*(?:el|root|container|filters?))""",
            self.flat,
            re.I,
        )
        self.assertIsNotNone(
            guarded,
            "the filter script must gate itself on the filter UI being present "
            "(an early return / `if (!root) return;` guard) so it is a no-op "
            "elsewhere",
        )

    def test_filters_rows_by_membership(self):
        membership = re.search(
            r"""(?:includes\s*\(|\bsplit\s*\(|indexOf\s*\(|\bhas\s*\()""",
            self.flat,
        )
        self.assertIsNotNone(
            membership,
            "the filter script must test category membership of a row's "
            "data-categories (e.g. split + includes/indexOf)",
        )
        self.assertRegex(
            self.flat,
            r"""data-categories""",
            "the filter script must read data-categories off the rows it filters",
        )

    def test_updates_aria_pressed_for_one_active_control(self):
        self.assertRegex(
            self.flat,
            r"""aria-pressed""",
            "the filter script must update aria-pressed on the controls",
        )
        # Exactly one active control => a single-active bookkeeping/loop pattern.
        single_active = re.search(
            r"""(?:forEach|for\s*\(|find\s*\(|filter\s*\()""",
            self.flat,
        )
        self.assertIsNotNone(
            single_active,
            "the filter script must iterate the controls so exactly one is "
            "aria-pressed=\"true\" at a time",
        )

    def test_no_innerhtml_or_eval(self):
        forbidden = (
            r"""\.innerHTML\b""",
            r"""\beval\s*\(""",
            r"""document\.write\b""",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertNotRegex(
                    self.flat,
                    pattern,
                    "the filter script must not use %s; build nodes with "
                    "createElement/textContent instead" % pattern,
                )

    def test_updates_live_status_with_text_content(self):
        self.assertRegex(
            self.flat,
            r"""(?:filter-status|role\s*=\s*["']status).*?textContent""",
            "the filter script must announce changed result counts through textContent",
        )

    def test_active_state_uses_aria_pressed_true(self):
        # The script may write the state literally, or (as here) conditionally while
        # iterating: setAttribute('aria-pressed', button === matched[0] ? 'true' : 'false')
        self.assertRegex(
            self.flat,
            r"""setAttribute\(\s*["']aria-pressed["']\s*,[^;]{0,200}?"""
            r"""["'](?:true|false)["']""",
            "the filter script must set aria-pressed to true/false (not a class "
            "only) when a control becomes active",
        )
        self.assertRegex(
            self.flat,
            r"""["']true["'][\s\S]{0,80}?["']false["']""",
            "the aria-pressed update must resolve to both a true and a false state",
        )


class CategoryFiltersCss(unittest.TestCase):
    """.category-filters reads as plain text controls, not pills or buttons."""

    def setUp(self):
        self.css = slurp(MAIN_CSS)
        self.rules = css_rules(self.css)
        self.filter_rules = category_filter_rules(self.css)

    def test_rules_exist(self):
        self.assertTrue(
            self.filter_rules,
            "main.css must style .category-filters (found no matching rule)",
        )

    def test_transparent_background(self):
        self.assertTrue(
            any(
                re.search(r"""background(?:-color)?\s*:\s*(?:transparent|none)""", body)
                for _, body in self.filter_rules
            ),
            ".category-filters must have a transparent background",
        )

    def test_no_border_box(self):
        offenders = []
        for sel, body in self.filter_rules:
            for decl in re.finditer(r"""(border|border\w*)\s*:\s*([^;}]*)""", body):
                prop, value = decl.group(1), decl.group(2).strip()
                if value in ("0", "none", "0 none"):
                    continue
                # border-bottom used only for the active underline is allowed.
                if prop == "border-bottom" and re.search(
                    r"""none|transparent|0\b""", value
                ):
                    continue
                offenders.append((sel, prop, value))
        # A border box around the control itself is forbidden; the active underline
        # must be drawn with text-decoration, not a border.
        control_borders = [
            (sel, prop, value)
            for sel, prop, value in offenders
            if "::" not in sel and re.search(r"""\.category-filters\b""", sel)
        ]
        self.assertEqual(
            [],
            control_borders,
            ".category-filters must have no border box (the active underline must "
            "use text-decoration, not a border); found %r" % control_borders,
        )

    def test_no_border_radius_or_pill(self):
        offenders = []
        for sel, body in self.filter_rules:
            if re.search(
                r"""border-radius\s*:(?!(?:\s*0(?:px)?\b|\s*0\s*;))[^;}]+""",
                body,
            ):
                offenders.append((sel, "border-radius"))
            if re.search(r"""\bpill\b""", body, re.I):
                offenders.append((sel, "pill"))
        self.assertEqual(
            [],
            offenders,
            ".category-filters must not use border-radius or a pill shape; found %r"
            % offenders,
        )

    def test_hidden_rows_are_not_displayed(self):
        matches = [
            body
            for sel, body in self.rules
            if ".post[hidden]" in sel
            and re.search(r"display\s*:\s*none", body)
        ]
        self.assertTrue(
            matches,
            "hidden filtered post rows must explicitly use display:none so the "
            "author display:grid rule cannot override the native hidden style",
        )

    def test_visible_keyboard_focus(self):
        focus_rules = [
            (sel, body)
            for sel, body in self.filter_rules
            if ":focus-visible" in sel or ":focus" in sel
        ]
        self.assertTrue(
            focus_rules,
            ".category-filters must define a visible keyboard focus style "
            "(:focus-visible / :focus)",
        )
        self.assertTrue(
            any(
                re.search(r"""outline\s*:""", body)
                or re.search(r"""text-decoration\s*:""", body)
                or re.search(r"""box-shadow\s*:""", body)
                or re.search(r"""border-bottom\s*:\s*[^;}]*\b(?!0\b)""", body)
                for _, body in focus_rules
            ),
            "the keyboard focus style for .category-filters must be visible "
            "(outline, text-decoration, box-shadow, or a real underline)",
        )

    def test_active_underline_under_text(self):
        underline = [
            (sel, body)
            for sel, body in self.filter_rules
            if re.search(r"""text-decoration\s*:\s*[^;}]*underline""", body)
        ]
        self.assertTrue(
            underline,
            ".category-filters must draw the active underline with "
            "text-decoration: underline",
        )
        with_offset = [
            (sel, body)
            for sel, body in self.filter_rules
            if re.search(r"""text-decoration\s*:\s*[^;}]*underline""", body)
            and re.search(r"""text-underline-offset\s*:\s*[^;}]+""", body)
        ]
        self.assertTrue(
            with_offset,
            "the active underline must sit directly under the text via "
            "text-underline-offset; got %r" % [sel for sel, _ in underline],
        )

    def test_mobile_wrapping(self):
        wraps = [
            (sel, body)
            for sel, body in self.filter_rules
            if re.search(r"""flex-wrap\s*:\s*wrap""", body)
            or re.search(r"""\bwrap\b""", body)
            or re.search(r"""white-space\s*:\s*(?:normal|nowrap)""", body)
        ]
        self.assertTrue(
            wraps,
            ".category-filters must wrap on narrow screens (flex-wrap: wrap or "
            "equivalent)",
        )


class ContentUntouched(unittest.TestCase):
    """This feature is metadata-derived: no content/front-matter file may change."""

    def test_no_filter_metadata_added_to_content(self):
        root = REPO_ROOT / CONTENT_ROOT
        if not root.is_dir():
            self.skipTest("exampleSite/content is not present")
        offenders = []
        for path in sorted(root.rglob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"""(?:category-filter|data-categories|categoryFilters)""", text):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(
            [],
            offenders,
            "the category filter must derive from existing front matter; these "
            "content files were modified for the feature: %r" % offenders,
        )


class IntegratedCategoryContract(unittest.TestCase):
    """Cross-file contract: the pieces above must actually line up end to end."""

    def setUp(self):
        self.posts = flat(slurp(POSTS))
        self.li = flat(slurp(LI))
        self.i18n = slurp("i18n/en.toml")

    def test_main_sections_not_params_main_sections(self):
        self.assertRegex(
            self.posts,
            r"""site\.MainSections\b""",
            "posts.html must select its section set with site.MainSections",
        )
        self.assertNotRegex(
            self.posts,
            r"""site\.Params\.mainSections\b""",
            "posts.html must not read site.Params.mainSections",
        )

    def test_filter_visibility_requires_home_and_categories(self):
        visibility = re.search(
            r"""\band\b[^\n]{0,60}\$isHome\b[^\n]{0,120}\bgt\b[^\n]{0,40}"""
            r"""\blen\b[^\n]{0,40}\$categories""",
            self.posts,
        )
        self.assertIsNotNone(
            visibility,
            "the filter visibility condition must combine `.IsHome` with a "
            "non-empty category list (e.g. `and $isHome (gt (len $categories) 0)`)",
        )
        self.assertRegex(
            self.posts,
            r"""\$isHome\s*:=\s*\.IsHome\b""",
            "posts.html must bind .IsHome before the visibility condition uses it",
        )

    def test_exact_identity_from_relpermalink_and_all_sentinel(self):
        # Identity must match exactly between the button token and the row token,
        # so both sides have to use the taxonomy term's .RelPermalink.
        for name, text in ((POSTS, self.posts), (LI, self.li)):
            with self.subTest(source=name):
                self.assertRegex(
                    text,
                    r"""\.RelPermalink\b""",
                    "%s must derive category identity from .RelPermalink" % name,
                )
        self.assertRegex(
            self.posts,
            r"""data-category-filter\s*=\s*"__all__"|['"]__all__['"]""",
            "the All sentinel must be exactly `__all__` in posts.html",
        )

    def test_status_placeholders_and_js_substitution(self):
        status = re.search(
            r'\[posts\.filter\.status\]\s*other\s*=\s*"([^"]*)"',
            self.i18n,
        )
        self.assertIsNotNone(
            status, "i18n/en.toml must define posts.filter.status"
        )
        value = status.group(1)
        self.assertIn("{visible}", value, "status string must carry {visible}")
        self.assertIn("{total}", value, "status string must carry {total}")

        # Each placeholder must be independently substituted by the posts JS. The
        # two replacements are asserted separately (and by escaping each literal
        # placeholder) rather than by relying on a fixed distance between them,
        # which would break on any formatting-only edit.
        self.assertRegex(
            self.posts,
            r"""replace\s*\(\s*/\s*\\\{visible\\\}/g""",
            "the posts JS must substitute the {visible} placeholder",
        )
        self.assertRegex(
            self.posts,
            r"""replace\s*\(\s*/\s*\\\{total\\\}/g""",
            "the posts JS must substitute the {total} placeholder",
        )
        self.assertRegex(
            self.posts,
            r"""status\.textContent\s*=""",
            "the posts JS must write the rendered status through textContent",
        )

    def test_noscript_browse_and_language_relative_link(self):
        self.assertRegex(
            self.posts,
            r"""<noscript>[\s\S]*?posts\.filter\.browse[\s\S]*?</noscript>""",
            "the noscript fallback must use the posts.filter.browse i18n string",
        )
        self.assertRegex(
            self.posts,
            r'relLangURL\s*"/categories/"',
            "the noscript categories link must be language-relative (relLangURL)",
        )


if __name__ == "__main__":
    unittest.main()
