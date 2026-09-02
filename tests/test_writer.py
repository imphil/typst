# TODO: Write docstrings after.
# ruff: noqa: D101, D102, D106, D107
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from docutils import nodes

from atsphinx.typst import builders as t

if TYPE_CHECKING:
    from pytest_mock import MockFixture
    from sphinx.testing.util import SphinxTestApp


class Test_TypstTranslator:
    class Test_visit_mermaid:
        @pytest.mark.sphinx("typst", testroot="with-mermaid-nodep")
        def test__no_sphinxcontrib_mermaid(self, app: SphinxTestApp):
            """Build succeeds when sphinxcontrib.mermaid is not installed.

            The ``with-mermaid-nodep`` testroot does not load ``sphinxcontrib.mermaid``
            so the ``.. mermaid::`` directive is unknown and produces no node - the
            translator's ``visit_mermaid`` is never reached, but the build must still
            complete and emit a ``.typ`` file.
            """
            app.build()
            out = app.outdir / "index.typ"
            assert out.exists()

        @pytest.mark.sphinx("typst", testroot="with-mermaid", freshenv=True)
        def test__render_produces_image(self, app: SphinxTestApp, mocker: MockFixture):
            """When render_mm succeeds the SVG is embedded as an image directive."""
            import atsphinx.typst.writer as w

            fake_relfn = "_images/mermaid-abc123.svg"
            fake_outfn = "/tmp/mermaid-abc123.svg"
            mocker.patch.object(
                w.TypstTranslator,
                "mermaid_render_to_svg",
                return_value=(fake_relfn, fake_outfn),
            )
            app.build()
            out = app.outdir / "index.typ"
            assert out.exists()
            content = out.read_text()
            # The SVG path should appear in the generated Typst source
            assert "mermaid-abc123.svg" in content

        @pytest.mark.sphinx("typst", testroot="with-mermaid", freshenv=True)
        def test__render_failure_is_skipped(
            self, app: SphinxTestApp, mocker: MockFixture
        ):
            """A render error is caught, logged as a warning, and build still succeeds."""
            import atsphinx.typst.writer as w

            mocker.patch.object(
                w.TypstTranslator,
                "mermaid_render_to_svg",
                side_effect=RuntimeError("mmdc crashed"),
            )
            mock_logger = mocker.patch.object(w, "logger")
            app.build()
            out = app.outdir / "index.typ"
            assert out.exists()
            mock_logger.warning.assert_called_once()

    class Test_glossary:
        @pytest.mark.sphinx("typst", testroot="with-glossary")
        def test__build_succeeds(self, app):
            """Building a doc with a ``.. glossary::`` must not raise NotImplementedError."""
            app.build()
            assert (app.outdir / "index.typ").exists()

        @pytest.mark.sphinx("typst", testroot="with-glossary")
        def test__term_text_appears(self, app):
            """Glossary term text must be present in the Typst output."""
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert "Alpha" in content
            assert "Beta" in content

        @pytest.mark.sphinx("typst", testroot="with-glossary")
        def test__term_labels_are_emitted(self, app):
            """Each glossary term must emit a Typst label so ``:term:`` links resolve."""
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert "<index:term-Alpha>" in content
            assert "<index:term-Beta>" in content

        @pytest.mark.sphinx("typst", testroot="with-glossary")
        def test__term_references_link_to_labels(self, app):
            """``:term:`` roles must produce ``#link`` calls pointing at the term labels."""
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert "#link(<index:term-Alpha>)" in content
            assert "#link(<index:term-Beta>)" in content

        @pytest.mark.sphinx("typst", testroot="with-glossary")
        def test__glossary_build_emits_no_non_pair_index_warning(self, app, capsys):
            """Glossary builds must not log the unsupported non-pair index-entry warning."""
            app.build()
            captured = capsys.readouterr()
            assert (
                "Currently, it only suports 'pair' typed entries." not in captured.out
            )

    class Test_apidoc:
        """Sphinx's ``addnodes`` for API documentation (autodoc, breathe, ...)."""

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__build_succeeds(self, app: SphinxTestApp):
            """A doc full of domain directives must not raise NotImplementedError."""
            app.build()
            assert (app.outdir / "index.typ").exists()

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__multiline_signature_is_broken(self, app: SphinxTestApp):
            """``desc_signature_line`` children must be separated by a linebreak.

            A C++ template declaration is an ``is_multiline`` signature: the
            ``template<...>`` part and the declaration itself are separate
            ``desc_signature_line`` nodes and must not run together.
            """
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert (
                "template\\<typename #strong(delta: 400)[T], "
                "int #strong(delta: 400)[N]\\>#linebreak()"
                "class #strong(delta: 400)[MyClass]"
            ) in content

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__parameter_list_is_parenthesised(self, app: SphinxTestApp):
            """Parameters must be wrapped in parentheses and comma-separated.

            The parentheses are escaped: an unescaped ``(`` directly after the
            ``#strong(...)[...]`` of ``desc_name`` would be read by Typst as
            that call's argument list.
            """
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert (
                "#strong(delta: 400)[spam]\\(eggs, ham\\=None, \\*args, "
                "\\*\\*kwargs\\)"
            ) in content

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__optional_parameters_keep_comma_placement(self, app: SphinxTestApp):
            """Optional groups render as ``lead([a, ]b, c[, d])``.

            The comma moves inside the bracket once no required parameter is
            left, the way Sphinx's own writers place it.
            """
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert "#strong(delta: 400)[lead]\\(\\[a, \\]b, c\\[, d\\]\\)" in content

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__type_parameter_list_uses_brackets(self, app: SphinxTestApp):
            """PEP 695 type parameters render in brackets, before the parameters."""
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert "#strong(delta: 400)[generic]\\[T\\]\\(x: T\\)" in content

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__return_annotation_is_an_arrow(self, app: SphinxTestApp):
            """``desc_returns`` renders as a rightwards arrow."""
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert "\\(x: T\\) \\u{2192} T" in content

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__overloads_share_one_content_block(self, app: SphinxTestApp):
            """Several ``desc_signature`` children go into one ``signatures`` tuple.

            ``#desc`` takes the signatures as a tuple precisely so that
            overloads sharing a single body stay one call.
            """
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert (
                "    [#strong(delta: 400)[over]\\(a: int\\) \\u{2192} int"
                " <index:over>],\n"
                "    [#strong(delta: 400)[over]\\(a: str\\) \\u{2192} str],\n"
                "  ),\n"
                "  content: [\n"
            ) in content

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__signature_ids_are_labelled(self, app: SphinxTestApp):
            """Every signature id gets a namespaced Typst label.

            The first id labels the signature itself; the rest need their own
            invisible anchor, written *inside* the content block because the
            surrounding ``#desc(`` argument list is Typst code.

            Order matters: a bare label attaches to whatever precedes it, so
            the signature's own label has to come before the anchors or Typst
            warns that the same content is labelled multiple times.
            """
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert (
                " <index:_CPPv4I0_iE7MyClass>"
                "#metadata(none) <index:_CPPv3I0_iE7MyClass>"
                "#metadata(none) <index:_CPPv2I0_iE7MyClass>],"
            ) in content

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__empty_desc_content_is_dropped(self, app: SphinxTestApp):
            """A directive with no body must not emit an empty ``content:``."""
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert "content: [\n  ],\n" not in content

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__ellipsis_run_is_escaped(self, app: SphinxTestApp):
            """A C++ pack expansion must stay three periods, not an ellipsis."""
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert "template\\<typename .\\.." in content

        @pytest.mark.sphinx("typst", testroot="with-apidoc")
        def test__other_sphinx_nodes_are_rendered(self, app: SphinxTestApp):
            """``seealso``/``hlist``/``centered``/``productionlist``/``acks``/``manpage``."""
            app.build()
            content = (app.outdir / "index.typ").read_text()
            assert '#admonition(\n  "seealso", "See also",' in content
            assert "#hlist(\n  columns: 2," in content
            assert "#align(center)[Centered text]" in content
            assert "#productionlist(\n" in content
            assert "[try\\_stmt], [::=], [" in content
            assert "Someone." in content
            assert "#mono[ls(1)]" in content
            assert "Deprecated since version 1.2" in content

        @pytest.mark.sphinx("typstpdf", testroot="with-apidoc")
        def test__compiles_to_pdf(self, app: SphinxTestApp):
            """The emitted Typst must actually compile.

            Signatures put markup right next to Typst code expressions, so a
            missing escape shows up as a compile error rather than as bad
            output.
            """
            app.build()
            assert (app.outdir / "index.pdf").exists()
