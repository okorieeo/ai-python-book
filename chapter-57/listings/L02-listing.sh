python3 - <<'PY'
from docuask_core.extract import extract_pages
from docuask_core.chunking import chunk_pages
data = open("YOUR_FILE.pdf", "rb").read()
pages = extract_pages(data, "YOUR_FILE.pdf")
chunks = chunk_pages(pages)
print(len(pages), "pages,", len(chunks), "chunks")
for c in chunks[:3]:
    print(c.page_start, c.tokens, c.text[:120])
PY
