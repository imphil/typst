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

from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from docutils import nodes
from rst2typst.writer import TypstTranslator as BaseTypstTranslator
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


def _doc_label(docname: str) -> str:
    # Merged into one Typst file, so labels need a per-document namespace
    # to avoid id collisions (e.g. two "Installation" sections).
    return docname.replace("/", ":")


class TypstTranslator(SphinxTranslator, BaseTypstTranslator):
    """Custom translator that has converter from dotctree to Typst syntax."""

    # NOTE: If you found ``NotImplementedError`` for node visitor/departure,
    #   add node name into ``optional`` and implement after.
    optional = [
        # "legend",  # Alredy added, but translator does not find.
        # TODO: Require implements to support apidoc.
        "desc_addname",
        "desc_annotation",
        "desc_sig_space",
        "desc_sig_name",
        "desc_parameter",
        "desc_parameterlist",
        "desc_returns",
        "desc_sig_punctuation",
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

    # ------
    # visit/departuer methods
    # ------
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
                self._write_anchor(f"{docname}:{node_id}")

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
            self.body.append(f" <{docname}:{ids[0]}>")

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
            uri = f"{_doc_label(self.curfilestack[-1])}:{node['refid']}"
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
                uri += f":{labelid}"
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
            self._write_anchor(f"{docname}:{node['refid']}")
            raise nodes.SkipNode

        # A standalone target PropagateTargets left untouched (e.g. one at
        # the end of a document) - anchor it directly, like ids[1:] above.
        target_id = node["ids"][0] if node.get("ids") else None
        if target_id:
            self._write_anchor(f"{docname}:{target_id}")
        raise nodes.SkipNode

    # Implements for Sphinx's nodes
    # =============================
    def visit_pending_xref(self, node: addnodes.pending_xref):
        # resolve_references() already replaced resolvable pending_xrefs
        # with plain reference nodes; only unresolved ones reach here.
        pass

    def depart_pending_xref(self, node: addnodes.pending_xref):
        pass

    def visit_desc(self, node: addnodes.desc):
        self.packages.add(_typst_local_package_fullname("atsphinx-typst"), "desc")
        self.body.append(f"{self._hi.prefix}#desc(\n")
        self._hi.push("  ")

    def depart_desc(self, node: addnodes.desc):
        self._hi.pop()
        self.body.append(f"{self._hi.indent})\n")

    def visit_desc_signature(self, node: addnodes.desc_signature):
        self.body.append(f"{self._hi.prefix}[\n")
        self._hi.push("  ")

    def depart_desc_signature(self, node: addnodes.desc_signature):
        # Namespaced like section headings, see depart_title().
        docname = _doc_label(self.curfilestack[-1])
        ids = node.get("ids", [])
        if ids:
            self.body.append(f" <{docname}:{ids[0]}>")
        self._hi.pop()
        self.body.append(f"{self._hi.prefix}],\n")
        for node_id in ids[1:]:
            self._write_anchor(f"{docname}:{node_id}")

    def visit_desc_name(self, node: addnodes.desc_name):
        self.body.append(f"{self._hi.indent}#strong(delta: 400)[")

    def depart_desc_name(self, node: addnodes.desc_name):
        self.body.append("]")

    def visit_desc_content(self, node: addnodes.desc_content):
        self.body.append(f"{self._hi.prefix}[\n")
        self._hi.push("  ")

    def depart_desc_content(self, node: addnodes.desc_content):
        self._hi.pop()
        self.body.append(f"{self._hi.indent}],\n")

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
            if entrytype != "pair":
                logger.info("Currently, it only suports 'pair' typed entries.")
                continue

            parts = split_index_msg(entrytype, entryname)
            index_name, index_group = parts
            index_path = f'"{_escape(index_group)}", "{_escape(index_name)}"'
            self.body.append(f"#index({index_path}, apply-casing: false)")

    def depart_index(self, node: addnodes.index):
        pass


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
