/*
* Render Sphinx specific nodes.
*
* Refs: https://www.sphinx-doc.org/en/master/extdev/nodes.html
*/

// Signatures are code, so they are set in the same face as code blocks.
// This is not a new font: it is Typst's own default for `raw`, which Typst
// bundles, so it matches out of the box and adds no font dependency. Note
// that a document-level `#set text(font: ..)` (the typst_documents[].font
// setting) does not reach `raw`, and so does not reach signatures either.
//
// A theme that restyles code blocks should keep signatures in step by
// rebinding these in its layout.typ, which the template includes after the
// package imports:
//
//     #show raw: set text(font: "Fira Code")
//     #let desc = desc.with(font: "Fira Code")
//     #let mono = mono.with(font: "Fira Code")
#let sig-font = ("DejaVu Sans Mono",)

/*
* Inline monospace fragment, used for <desc_inline> and <manpage>.
*
* This is deliberately not `raw`: `raw` takes a *string*, and both of these
* nodes can hold content. `:cpp:texpr:`std::vector<Widget>`` resolves the
* type to a cross-reference, and `:manpage:` wraps its text in a link once
* `manpages_url` is configured - neither survives inside a raw block. Where
* the content really is a string (<literal>), rst2typst already emits raw.
*/
#let mono(body, font: sig-font) = {
  // Signatures are code: "'x'" must not turn into a typographic quote, and
  // "..." must not turn into an ellipsis.
  set smartquote(enabled: false)
  text(font: font, size: 0.85em, ligatures: false, body)
}

/*
* Render <desc> node in Sphinx.
*
* A description holds one or more signatures (overloads share a single
* body) followed by an optional content block.
*/
#let desc(
  signatures: (),
  content: none,
  font: sig-font,
) = {
  block(width: 100%, above: 1em, below: 1em)[
    #for signature in signatures {
      block(
        width: 100%,
        breakable: false,
        above: 0.2em,
        below: 0.2em,
        {
          set par(hanging-indent: 2em, justify: false)
          set smartquote(enabled: false)
          set text(font: font, size: 0.85em, ligatures: false)
          signature
        },
      )
    }
    #if content != none {
      pad(left: 1.5em, top: 0.4em, block(width: 100%, content))
    }
  ]
}

/*
* Render <hlist> node in Sphinx: a bullet list laid out in N columns.
*/
#let hlist(columns: 1, ..cells) = block(width: 100%)[
  #grid(columns: columns, column-gutter: 1em, ..cells)
]

/*
* Render <productionlist> node in Sphinx: a BNF-style grammar table.
*/
#let productionlist(..rows, font: sig-font) = block(width: 100%)[
  #set smartquote(enabled: false)
  #set text(font: font, size: 0.85em)
  #grid(columns: (auto, auto, 1fr), column-gutter: 0.6em, row-gutter: 0.4em, ..rows)
]
