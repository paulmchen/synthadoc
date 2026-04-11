# CJK Font Handling Notes

pypdf cannot decode PDF files that use fonts without embedded ToUnicode CMaps —
common in documents typeset with Chinese, Japanese, or Korean character sets.
In this case pypdf returns near-empty text (< 50 chars/page on average).

pdfminer.six uses its own CMap tables and handles these fonts correctly.
The threshold `_MIN_CHARS_PER_PAGE = 50` was chosen empirically.
