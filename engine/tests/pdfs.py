"""Builds small, valid PDFs with real text (Helvetica, Latin-1) for parser tests."""

from collections.abc import Sequence


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


Line = str | tuple[str, float]
"""A text line, optionally with its font size (default 11 pt)."""


def make_pdf(pages: Sequence[Sequence[Line]], info: dict[str, str] | None = None) -> bytes:
    """Each page is a list of text lines, drawn top to bottom."""
    objects: list[str] = []

    def add(body: str) -> int:
        objects.append(body)
        return len(objects)

    catalog = add("")  # filled in once the page tree number is known
    page_tree = add("")
    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_refs: list[int] = []
    for lines in pages:
        ops = ["BT", "/F1 11 Tf", "14 TL", "72 760 Td"]
        for line in lines:
            text, size = (line, 11.0) if isinstance(line, str) else line
            ops.append(f"/F1 {size} Tf {size * 1.3:.1f} TL ({_escape(text)}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops)
        content = add(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
        page_refs.append(
            add(
                f"<< /Type /Page /Parent {page_tree} 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>"
            )
        )
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {page_tree} 0 R >>"
    kids = " ".join(f"{ref} 0 R" for ref in page_refs)
    objects[page_tree - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_refs)} >>"
    info_ref = None
    if info:
        entries = " ".join(f"/{k} ({_escape(v)})" for k, v in info.items())
        info_ref = add(f"<< {entries} >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    trailer = f"/Size {len(objects) + 1} /Root {catalog} 0 R"
    if info_ref:
        trailer += f" /Info {info_ref} 0 R"
    out += f"trailer\n<< {trailer} >>\nstartxref\n{xref_at}\n%%EOF\n".encode("latin-1")
    return bytes(out)


SLEEP_PAPER_PAGES = [
    [
        "Sleep and Memory Consolidation in Adults",
        "Journal of Test Studies",
        "doi:10.1234/jts.2021.0042",
        "Abstract. We studied how sleep affects memory consolidation in healthy adults.",
        "Participants who slept after learning recalled more word pairs than those who stayed",
        "awake. The effect was strongest for emotionally neutral material.",
        "Page 1",
    ],
    [
        "Journal of Test Studies",
        "Methods. Forty participants learned word pairs in the evening. Half of them slept for",
        "eight hours while the other half remained awake under supervision.",
        "Page 2",
    ],
    [
        "Journal of Test Studies",
        "Results. Recall improved by 21 percent after sleep. Critics argue that circadian",
        "timing, not sleep itself, explains the improvement.",
        "Page 3",
    ],
]

CLIMATE_PAPER_PAGES = [
    [
        "Crop Yields under Rising Temperatures",
        "Abstract. Rising temperatures reduce wheat and maize yields in most regions.",
        "We combine field trials with satellite data from twenty countries to estimate the",
        "effect of heat waves on agriculture. Yields fell by six percent per degree of warming.",
        "Adaptation through irrigation and new varieties offsets part of the loss.",
    ],
]
