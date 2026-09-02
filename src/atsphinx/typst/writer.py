"""Writer and relative classes.

Order of definitions.

1. Write about docutils elements.
   They are declared in order to
   `Element Reference <https://docutils.sourceforge.io/docs/ref/doctree.html#element-reference>`_.
2. Write about Spinx elements.
"""
# TODO: Write docstrings after.
# ruff: noqa: D101, D102, D107

from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from docutils import nodes
from rst2typst.writer import TypstTranslator as BaseTypstTranslator
from rst2typst.writer import escape
from sphinx import addnodes
from sphinx.errors import ExtensionError
from sphinx.util.docutils import SphinxTranslator
from sphinx.util.index_entries import split_index_msg
from sphinx.util.logging import getLogger

if TYPE_CHECKING:
    from sphinx.builders import Builder


logger = getLogger(__name__)


# TODO: It should be defined in rst2typst.
def _typst_local_package_fullname(name: str, version: str | None = None) -> str:
    if version is None:
        version = metadata.version(name)
    return f"@local/{name}:{version}"


# Characters that only need escaping inside a signature. There, markup sits
# directly next to Typst code expressions (``#strong[...]``,
# ``#link(<...>)[...]``); a bare "(" or "[" right after one is parsed as that
# call's argument list or as a trailing content block instead of as text.
_SIGNATURE_ESCAPE_TARGET = "()[]"


def _escape_signature(text: str) -> str:
    text = escape(text)
    for char in _SIGNATURE_ESCAPE_TARGET:
        text = text.replace(char, f"\\{char}")
    # Typst turns "..." into a typographic ellipsis; break the run so that a
    # C++ pack expansion stays three periods wide.
    return text.replace("...", ".\\..")


def _doc_label(docname: str) -> str:
    # Merged into one Typst file, so labels need a per-document namespace
    # to avoid id collisions (e.g. two "Installation" sections).
    return docname.replace("/", ":")


# Typst label identifiers only allow [A-Za-z0-9_.:\->]; everything else
# (spaces, ~, (, ), [, ], \, comma, ...) produces an "unclosed label" error.
# Sphinx domains — notably C++ — attach raw human-readable ids to nodes
# without normalising them the way docutils.nodes.make_id() would, so we
# must do the same job the LaTeX builder's idescape() does: replace every
# invalid character with a safe substitute.
# '_' is chosen because it is already valid, is never produced by the
# substitution rule itself, and therefore cannot introduce new collisions
# between two previously distinct node ids.
_INVALID_LABEL_CHARS = re.compile(r"[^A-Za-z0-9_.:\-]")


def _sanitize_label_id(node_id: str) -> str:
    """Replace characters that are invalid in a Typst label identifier with ``_``.

    Typst labels allow ``[A-Za-z0-9_.:\\->]``.  Any other character — for
    example ``~`` in a C++ destructor id, ``<``/``>`` in a C++ template
    specialisation, or plain spaces — must be replaced.  We use ``_`` as the
    replacement (same convention as the Sphinx LaTeX builder's ``idescape()``).
    """
    return _INVALID_LABEL_CHARS.sub("_", node_id)


class TypstTranslator(SphinxTranslator, BaseTypstTranslator):
    """Custom translator that has converter from dotctree to Typst syntax."""

    # NOTE: If you found ``NotImplementedError`` for node visitor/departure,
    #   add node name into ``optional`` and implement after.
    optional = [
        # "legend",  # Alredy added, but translator does not find.
        "mermaid",  # Optional mermaid support
    ]

    def __init__(self, document: nodes.document, builder: Builder) -> None:
        super().__init__(document, builder)
        super(BaseTypstTranslator, self).__init__(document)
        # Set to avoid rendering root hedering text.
        self._section_level = -1
        self.document.settings.no_import_local_package = False
        self.context = {
            "has_index": False,
        }
        # Current document, for namespacing labels (like LaTeX's curfilestack).
        self.curfilestack = [document["docname"]]
        # One entry per open ``desc``: whether its ``signatures:`` tuple is
        # still open. Nested ``desc`` nodes are normal (methods in a class).
        self._desc_signatures_open: list[bool] = []
        # One entry per open parameter list, see _visit_sig_parameter_list().
        self._sig_params: list[dict[str, Any]] = []
        # Depth of nested ``desc_signature`` nodes, see _escape_signature().
        self._signature_depth = 0

    # ------
    # visit/departuer methods
    # ------
    def visit_Text(self, node: nodes.Text):
        if not self._signature_depth:
            return super().visit_Text(node)
        self.body.append(_escape_signature(node.astext()))

    def visit_document(self, node: nodes.document):
        super().visit_document(node)
        self._write_anchor(_doc_label(self.curfilestack[-1]))

    def visit_title(self, node: nodes.title):
        if isinstance(node.parent, nodes.section) and self._section_level < 1:
            raise nodes.SkipNode

        # ids[0] (the heading's own slug) is anchored inline in depart_title;
        # ids[1:] (explicit labels above the heading) anchor here, before
        # the heading, so a :ref: lands at the section's top.
        if isinstance(node.parent, nodes.section):
            docname = _doc_label(self.curfilestack[-1])
            for node_id in node.parent.get("ids", [])[1:]:
                self._write_anchor(f"{docname}:{_sanitize_label_id(node_id)}")

        super().visit_title(node)

    def depart_title(self, node: nodes.title):
        """Add a label to section titles for cross-referencing."""
        docname = _doc_label(self.curfilestack[-1])
        if isinstance(node.parent, nodes.section):
            ids = node.parent.get("ids", [])
        else:
            ids = []

        if ids:
            # Label goes after the title text, before the newline: == Title <label>
            self.body.append(f" <{docname}:{_sanitize_label_id(ids[0])}>")

        super().depart_title(node)

    # TODO: It should separate transform and translate.
    def visit_container(self, node: nodes.container):
        if node.get("literal_block"):
            self.body.append(f"{self._hi.prefix}#figure(\n")
            self._hi.push("  ")
            literal = node.children.pop()
            node.children.insert(0, literal)

    def depart_container(self, node: nodes.container):
        if node.get("literal_block"):
            self._hi.pop()
            self.body.append(f"{self._hi.indent})\n")

    def visit_image(self, node: nodes.image):
        uri = node["uri"]
        source = Path(self.document["source"])
        uri_path = source.parent / uri
        uri_dest = self.builder._images_dir / uri_path.relative_to(
            self.builder.srcdir
        )
        uri_map = uri_dest.relative_to(self.builder.outdir)
        self.builder.images.setdefault(uri_path, uri_dest)
        node["uri"] = uri_map
        super().visit_image(node)

    def visit_reference(self, node: nodes.reference):
        # NOTE: It may be should implement in rst2typst.
        # Key off refid/refuri directly (like Sphinx's LaTeX writer), not
        # ``internal``: plain anchor refs (RST `Title`_, MyST #anchor) get
        # refid without Sphinx ever setting ``internal``.
        if "refid" in node:
            uri = f"{_doc_label(self.curfilestack[-1])}:{_sanitize_label_id(node['refid'])}"
        elif node.get("internal", False):
            # Sphinx-resolved cross-doc reference, shaped "docname" or
            # "docname#labelid".
            if "refuri" not in node:
                raise ExtensionError(
                    "<reference> requires 'refuri' or 'refid' attribute"
                )
            docname, _, labelid = node["refuri"].partition("#")
            uri = _doc_label(docname)
            if labelid:
                uri += f":{_sanitize_label_id(labelid)}"
        else:
            # Plain external hyperlink - nothing to namespace.
            return super().visit_reference(node)
        return self.body.append(f"#link(<{uri}>)[")

    def visit_target(self, node: nodes.target) -> None:
        docname = _doc_label(self.curfilestack[-1])

        if not node.get("ids") and node.get("refid"):
            # PropagateTargets forwarded this target's id onto whatever
            # followed it (section, paragraph, desc, ...), clearing our
            # own ids. Walk past chained targets to find that node, like
            # LaTeX's visit_target does.
            next_node = node.next_node(ascend=True)
            while isinstance(next_node, nodes.target):
                next_node = next_node.next_node(ascend=True)

            if isinstance(next_node, nodes.section):
                # Already anchored by visit_title/depart_title's ids loop.
                raise nodes.SkipNode

            # Forwarded onto a node with no id-handling of its own (e.g. a
            # paragraph, or a desc - depart_desc_signature only anchors the
            # signature's own ids). Nothing else emits this, so do it here.
            self._write_anchor(f"{docname}:{_sanitize_label_id(node['refid'])}")
            raise nodes.SkipNode

        # A standalone target PropagateTargets left untouched (e.g. one at
        # the end of a document) - anchor it directly, like ids[1:] above.
        target_id = node["ids"][0] if node.get("ids") else None
        if target_id:
            self._write_anchor(f"{docname}:{_sanitize_label_id(target_id)}")
        raise nodes.SkipNode

    # Implements for Sphinx's nodes
    # =============================
    def visit_pending_xref(self, node: addnodes.pending_xref):
        # resolve_references() already replaced resolvable pending_xrefs
        # with plain reference nodes; only unresolved ones reach here.
        pass

    def depart_pending_xref(self, node: addnodes.pending_xref):
        pass

    # Object descriptions
    # -------------------
    # A ``desc`` holds one or more ``desc_signature`` children (overloads
    # share a single body) followed by an optional ``desc_content``, so the
    # Typst side takes the signatures as a tuple rather than one argument.

    def visit_desc(self, node: addnodes.desc):
        self.packages.add(_typst_local_package_fullname("atsphinx-typst"), "desc")
        self.body.append(f"{self._hi.prefix}#desc(\n")
        self._hi.push("  ")
        self.body.append(f"{self._hi.indent}signatures: (\n")
        self._hi.push("  ")
        self._desc_signatures_open.append(True)

    def depart_desc(self, node: addnodes.desc):
        self._close_desc_signatures()
        self._desc_signatures_open.pop()
        self._hi.pop()
        self.body.append(f"{self._hi.indent})\n")

    def _close_desc_signatures(self) -> None:
        """Close the ``signatures:`` tuple opened by :meth:`visit_desc`.

        Called by whichever comes first: the ``desc_content`` node, or the
        end of the ``desc`` when it has no content (``.. cpp:member::``
        without a body, for instance).
        """
        if not self._desc_signatures_open[-1]:
            return
        self._desc_signatures_open[-1] = False
        self._hi.pop()
        self.body.append(f"{self._hi.indent}),\n")

    def visit_desc_signature(self, node: addnodes.desc_signature):
        # A signature is inline-only, so keep it on one output line: a
        # newline inside Typst markup would render as a space.
        self.body.append(f"{self._hi.indent}[")
        self._signature_depth += 1

    def depart_desc_signature(self, node: addnodes.desc_signature):
        # Namespaced like section headings, see depart_title().
        docname = _doc_label(self.curfilestack[-1])
        ids = node.get("ids", [])
        if ids:
            self.body.append(f" <{docname}:{_sanitize_label_id(ids[0])}>")
        # Secondary ids need their own invisible anchor, and it has to stay
        # *inside* the signature's content block - the enclosing ``#desc(``
        # argument list is Typst code, where markup labels are not allowed.
        # Each gets its own ``#metadata`` element: a bare label attaches to
        # whatever precedes it, so chaining them would label one element
        # repeatedly ("content labelled multiple times").
        for node_id in ids[1:]:
            self.body.append(f"#metadata(none) <{docname}:{_sanitize_label_id(node_id)}>")
        self.body.append("],\n")
        self._signature_depth -= 1

    def visit_desc_signature_line(self, node: addnodes.desc_signature_line):
        pass

    def depart_desc_signature_line(self, node: addnodes.desc_signature_line):
        # ``is_multiline`` signatures (C++ templates, long declarations) are
        # split into one ``desc_signature_line`` per rendered line.
        parent = node.parent
        if parent is not None and node is not parent.children[-1]:
            self.body.append("#linebreak()")

    def visit_desc_content(self, node: addnodes.desc_content):
        if not node.children:
            # ``.. cpp:member::`` and friends without a body still get an
            # (empty) desc_content; leaving it out avoids a stray indent.
            raise nodes.SkipNode
        self._close_desc_signatures()
        self.body.append(f"{self._hi.indent}content: [\n")
        self._hi.push("  ")

    def depart_desc_content(self, node: addnodes.desc_content):
        self._hi.pop()
        self.body.append(f"{self._hi.indent}],\n")

    @classmethod
    def get_gap_containers(cls) -> tuple:
        """Extend gap containers to include desc_content (Sphinx node)."""
        return BaseTypstTranslator.get_gap_containers() + (addnodes.desc_content,)

    def visit_desc_inline(self, node: addnodes.desc_inline):
        self.packages.add(_typst_local_package_fullname("atsphinx-typst"), "mono")
        self.body.append("#mono[")

    def depart_desc_inline(self, node: addnodes.desc_inline):
        self.body.append("]")

    # Structure inside a signature
    # ----------------------------

    def visit_desc_name(self, node: addnodes.desc_name):
        self.body.append("#strong(delta: 400)[")

    def depart_desc_name(self, node: addnodes.desc_name):
        self.body.append("]")

    def visit_desc_addname(self, node: addnodes.desc_addname):
        # The "MyModule." / "Namespace::" prefix: plain text next to the name.
        pass

    def depart_desc_addname(self, node: addnodes.desc_addname):
        pass

    def visit_desc_annotation(self, node: addnodes.desc_annotation):
        # "class ", "static ", "typedef ", ... - already spelled out by the
        # domain, including its trailing space.
        pass

    def depart_desc_annotation(self, node: addnodes.desc_annotation):
        pass

    def visit_desc_type(self, node: addnodes.desc_type):
        pass

    def depart_desc_type(self, node: addnodes.desc_type):
        pass

    def visit_desc_returns(self, node: addnodes.desc_returns):
        # Typst escape for U+2192 RIGHTWARDS ARROW.
        self.body.append(r" \u{2192} ")

    def depart_desc_returns(self, node: addnodes.desc_returns):
        pass

    # Parameter lists
    # ---------------
    # Ported from Sphinx's HTML5 writer (single-line branch) so that optional
    # groups read the way the domains intend: ``foo([a, ]b, c[, d])``.
    # ``multi_line_parameter_list`` is deliberately ignored - Typst wraps the
    # signature itself, using the hanging indent set by the ``desc`` package.
    # State is a stack because a parameter may itself hold a parameter list
    # (a C++ function-pointer argument).

    def _visit_sig_parameter_list(
        self,
        node: nodes.Element,
        parameter_group: type[nodes.Element],
        opening: str,
        closing: str,
    ) -> None:
        # A "parameter group" is either a required parameter or a set of
        # contiguous optional ones.
        is_required = [isinstance(c, parameter_group) for c in node.children]
        self._sig_params.append(
            {
                "separator": node.child_text_separator,
                "is_required": is_required,
                "required_left": sum(is_required),
                "group_index": 0,
                "optional_level": 0,
                "closing": closing,
                "first": True,
            }
        )
        self.body.append(opening)

    def _depart_sig_parameter_list(self, node: nodes.Element) -> None:
        self.body.append(self._sig_params.pop()["closing"])

    def visit_desc_parameterlist(self, node: addnodes.desc_parameterlist):
        self._visit_sig_parameter_list(node, addnodes.desc_parameter, "\\(", "\\)")

    def depart_desc_parameterlist(self, node: addnodes.desc_parameterlist):
        self._depart_sig_parameter_list(node)

    def visit_desc_type_parameter_list(self, node: addnodes.desc_type_parameter_list):
        # Brackets are escaped: an unbalanced one would end the Typst content
        # block that holds the signature.
        self._visit_sig_parameter_list(node, addnodes.desc_type_parameter, "\\[", "\\]")

    def depart_desc_type_parameter_list(self, node: addnodes.desc_type_parameter_list):
        self._depart_sig_parameter_list(node)

    def _visit_sig_parameter(self, node: nodes.Element) -> None:
        if not self._sig_params:
            return
        state = self._sig_params[-1]
        if state["first"]:
            state["first"] = False
        elif not state["required_left"]:
            # Only optional groups are left, so the separator belongs before
            # the parameter (inside the bracket): ``foo(a, b[, c])``.
            self.body.append(state["separator"])
        if state["optional_level"] == 0:
            state["required_left"] -= 1

    def _depart_sig_parameter(self, node: nodes.Element) -> None:
        if not self._sig_params:
            return
        state = self._sig_params[-1]
        if state["required_left"]:
            # Required parameters are still to come, so the separator goes
            # after this one (outside the bracket): ``foo([a, ]b)``.
            self.body.append(state["separator"])
        if (
            state["group_index"] < len(state["is_required"])
            and state["is_required"][state["group_index"]]
        ):
            state["group_index"] += 1

    visit_desc_parameter = _visit_sig_parameter
    depart_desc_parameter = _depart_sig_parameter
    visit_desc_type_parameter = _visit_sig_parameter
    depart_desc_type_parameter = _depart_sig_parameter

    def visit_desc_optional(self, node: addnodes.desc_optional):
        if self._sig_params:
            self._sig_params[-1]["optional_level"] += 1
        self.body.append("\\[")

    def depart_desc_optional(self, node: addnodes.desc_optional):
        self.body.append("\\]")
        if not self._sig_params:
            return
        state = self._sig_params[-1]
        state["optional_level"] -= 1
        if state["optional_level"] == 0:
            state["group_index"] += 1

    def visit_glossary(self, node: addnodes.glossary):
        pass

    def depart_glossary(self, node: addnodes.glossary):
        pass

    def depart_term(self, node: nodes.term):
        # Glossary terms carry an id (e.g. "term-alpha") used by :term: xrefs.
        # Emit a Typst label so those links have a target, namespaced per document
        # the same way section and desc_signature labels are.
        ids = node.get("ids", [])
        if ids:
            docname = _doc_label(self.curfilestack[-1])
            self.body.append(f" <{docname}:{_sanitize_label_id(ids[0])}>")
            for node_id in ids[1:]:
                self._write_anchor(f"{docname}:{_sanitize_label_id(node_id)}")

    def visit_index(self, node: addnodes.index):
        # NOTE: This is very simple implementation.
        #   There may be a more correct implementation.
        # TODO: Implement other cases.

        def _escape(txt: str) -> str:
            return txt.replace("\\", "\\\\").replace('"', '\\"')

        self.packages.add("@preview/in-dexter:0.7.2")
        self.context["has_index"] = True
        for entry in node.get("entries", []):
            entrytype, entryname, _target, _ignored, _key = entry
            if entrytype not in {"single", "pair"}:
                logger.info("Currently, it only suports 'single' and 'pair' typed entries.")
                continue

            parts = split_index_msg(entrytype, entryname)
            if entrytype == "single":
                index_name = parts[0]
                index_path = f'"{_escape(index_name)}"'
            else:
                index_name, index_group = parts
                index_path = f'"{_escape(index_group)}", "{_escape(index_name)}"'
            self.body.append(f"#index({index_path}, apply-casing: false)")

    def depart_index(self, node: addnodes.index):
        pass

    # Admonition-like and structural Sphinx nodes
    # -------------------------------------------

    # ``seealso`` has no theme of its own in the rst2typst package, so it
    # falls back to the "note" styling there.
    visit_seealso, depart_seealso = BaseTypstTranslator._enclose_admonition(
        "seealso", "See also"
    )

    def visit_versionmodified(self, node: addnodes.versionmodified):
        # The directive already spelled the lead-in out into the body
        # ("Deprecated since version 1.2: ..."), so only the paragraphs
        # inside matter - they just need to stand as their own block.
        self.body.append(self._hi.prefix)

    def depart_versionmodified(self, node: addnodes.versionmodified):
        self.body.append("\n\n")

    def visit_centered(self, node: addnodes.centered):
        self.body.append(f"{self._hi.prefix}#align(center)[")

    def depart_centered(self, node: addnodes.centered):
        self.body.append("]\n\n")

    def visit_rubric(self, node: nodes.rubric):
        # Not a Sphinx node, but autodoc/napoleon lean on it heavily inside
        # ``desc_content`` and rst2typst has no visitor for it.
        self.body.append(f"{self._hi.prefix}#strong[")

    def depart_rubric(self, node: nodes.rubric):
        self.body.append("]\n\n")

    def visit_acks(self, node: addnodes.acks):
        # A bullet list in the source, rendered as a running sentence - the
        # same shortcut the LaTeX writer takes.
        names = ", ".join(item.astext() for item in node[0])
        self.body.append(f"{self._hi.prefix}{escape(names)}.\n\n")
        raise nodes.SkipNode

    def visit_hlist(self, node: addnodes.hlist):
        self.packages.add(_typst_local_package_fullname("atsphinx-typst"), "hlist")
        self.body.append(f"{self._hi.prefix}#hlist(\n")
        self._hi.push("  ")
        self.body.append(f"{self._hi.indent}columns: {max(len(node.children), 1)},\n")

    def depart_hlist(self, node: addnodes.hlist):
        self._hi.pop()
        self.body.append(f"{self._hi.indent})\n\n")

    def visit_hlistcol(self, node: addnodes.hlistcol):
        self.body.append(f"{self._hi.indent}[\n")
        self._hi.push("  ")

    def depart_hlistcol(self, node: addnodes.hlistcol):
        self._hi.pop()
        self.body.append(f"{self._hi.indent}],\n")

    def visit_productionlist(self, node: addnodes.productionlist):
        self.packages.add(
            _typst_local_package_fullname("atsphinx-typst"), "productionlist"
        )
        self.body.append(f"{self._hi.prefix}#productionlist(\n")
        self._hi.push("  ")

    def depart_productionlist(self, node: addnodes.productionlist):
        self._hi.pop()
        self.body.append(f"{self._hi.indent})\n\n")

    def visit_production(self, node: addnodes.production):
        # Three grid cells per rule; a continuation line has no token name
        # and so no "::=" either.
        name = node["tokenname"]
        definition = "::=" if name else ""
        self.body.append(f"{self._hi.indent}[{escape(name)}], [{definition}], [")

    def depart_production(self, node: addnodes.production):
        self.body.append("],\n")

    # Inline Sphinx nodes
    # -------------------

    def visit_manpage(self, node: addnodes.manpage):
        self.packages.add(_typst_local_package_fullname("atsphinx-typst"), "mono")
        self.body.append("#mono[")

    def depart_manpage(self, node: addnodes.manpage):
        self.body.append("]")

    def visit_download_reference(self, node: addnodes.download_reference):
        # There is nothing to download from a PDF, so only the label shows.
        pass

    def depart_download_reference(self, node: addnodes.download_reference):
        pass

    def visit_tabular_col_spec(self, node: addnodes.tabular_col_spec):
        # LaTeX-only column specification.
        raise nodes.SkipNode

    def visit_toctree(self, node: addnodes.toctree):
        # ``assemble_doctree()`` inlines every toctree it can reach; whatever
        # is left points outside this Typst document.
        raise nodes.SkipNode

    def mermaid_render_to_svg(self, code: str, mermaid_options: Any, mermaid_cmd:str) -> tuple[Any | None, Any | None]:
        """Render a Mermaid diagram to SVG using ``sphinxcontrib.mermaid``.

        Temporarily patches the builder's ``mermaid_cmd``, ``imagedir``, and
        ``imgpath`` attributes so that :func:`sphinxcontrib.mermaid.render_mm`
        writes output files into the builder's ``_images_dir``.  All patched
        attributes are restored in a ``finally`` block regardless of success or
        failure.

        If ``mermaid_cmd`` is a relative path it is resolved against the
        project's ``confdir`` first, then ``confdir/_static``, falling back to
        the ``confdir``-relative path when neither location exists on disk.

        Args:
            code: Raw Mermaid diagram source to render.
            mermaid_options: Options dict forwarded verbatim to
                :func:`~sphinxcontrib.mermaid.render_mm`.
            mermaid_cmd: Path to the Mermaid CLI executable.  Relative paths
                are resolved as described above before being applied.

        Returns:
            A ``(relfn, outfn)`` tuple as returned by
            :func:`~sphinxcontrib.mermaid.render_mm`, where *relfn* is the
            relative path to the generated SVG file and *outfn* is the
            absolute path.  Both elements are ``None`` when rendering fails.

        Raises:
            ImportError: If ``sphinxcontrib-mermaid`` is not installed.
        """
        from sphinxcontrib.mermaid import render_mm  # may throw ImportError
        from sphinxcontrib.mermaid.exceptions import MermaidError

        builder: Builder = self.builder

        confdir = Path(builder.app.confdir)
        # Temporarily set mermaid_cmd to absolute path if it is relative path
        if isinstance(mermaid_cmd, str) and not Path(mermaid_cmd).is_absolute():
            mermaid_cmd_path = Path(mermaid_cmd)
            confdir_cmd = confdir / mermaid_cmd_path
            static_cmd = confdir / "_static" / mermaid_cmd_path

            if confdir_cmd.exists():
                builder.config.mermaid_cmd = str(confdir_cmd)
            elif static_cmd.exists():
                builder.config.mermaid_cmd = str(static_cmd)
            else:
                builder.config.mermaid_cmd = str(confdir_cmd)

        # Temporarily set imagedir using builder's _images_dir so render_mm creates files there
        original_imagedir = getattr(builder, 'imagedir', None)
        original_imgpath = getattr(builder, 'imgpath', None)
        images_dir_name = builder._images_dir.name
        builder.imagedir = images_dir_name
        builder.imgpath = images_dir_name

        try:
            relfn, outfn = render_mm(
                self, code, mermaid_options, _fmt="svg", prefix="mermaid"
            )
        except MermaidError as exc:
            raise
        finally:
            builder.config.mermaid_cmd = mermaid_cmd
            # Restore original values
            if original_imagedir is not None:
                builder.imagedir = original_imagedir
            else:
                delattr(builder, 'imagedir')
            if original_imgpath is not None:
                builder.imgpath = original_imgpath
            else:
                delattr(builder, 'imgpath')
        return relfn, outfn



    def visit_mermaid(self, node):
        """Handle mermaid node - render to SVG using sphinxcontrib.mermaid."""
        try:
            from sphinxcontrib.mermaid.exceptions import MermaidError

            code = node["code"]
            options = node.get("options", {})
            mermaid_cmd = self.builder.config.mermaid_cmd


            relative_filename, output_filename = self.mermaid_render_to_svg(code, options, mermaid_cmd)

            if relative_filename and output_filename:
                # render_mm created file directly in _images_dir
                # No need to register for copying - file is already in final location
                img_node = nodes.image()
                img_node['uri'] = relative_filename  # Already points to images_dir/filename.svg
                img_node['alt'] = node.get('alt', 'Mermaid diagram')
                if 'align' in node:
                    img_node['align'] = node['align']
                # Use parent class to render (skip our visit_image path processing)
                super(TypstTranslator, self).visit_image(img_node)
                super(TypstTranslator, self).depart_image(img_node)
        except ImportError:
            logger.warning(
                "sphinxcontrib.mermaid not installed. Skipping mermaid diagram.",
                location=node,
            )
        except nodes.SkipNode:
            raise
        except MermaidError as exc:
            logger.warning("mermaid diagram failed to render: \n" + str(exc), location=node)
        except Exception as e:
            logger.warning(f"Mermaid rendering failed: {e}. Skipping diagram.", location=node)

        raise nodes.SkipNode

    def depart_mermaid(self, node):
        """Empty, unused visitor method for mermaid blocks"""
        pass

    def visit_start_of_file(self, node: addnodes.start_of_file):
        docname = node["docname"]
        self.curfilestack.append(docname)
        self._write_anchor(_doc_label(docname))

    def depart_start_of_file(self, node: addnodes.start_of_file):
        self.curfilestack.pop()

    def _write_anchor(self, label: str) -> None:
        # An invisible label not attached to any visible content - for
        # document-level anchors and for ids that can't share a heading's
        # own label (see depart_title()).
        self.body.append(f"#metadata(none) <{label}>\n")
