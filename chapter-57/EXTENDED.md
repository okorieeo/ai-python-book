# Chapter 57 — Project 2: Document Q&A (RAG) Platform: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Data Model › Three details that bite later

- **The dimension is part of the schema.** VectorField(dimensions=1024) fixes the vector size in the column type. A different embedding model with another size means a new column (or table) and re-embedding **every** chunk. That is why Document records the model name: vectors from two models are not comparable, and mixing them silently ruins search.
- **The index must match the query.** An HNSW index is built for one distance measure. We use cosine, so the index uses vector_cosine_ops and the query uses CosineDistance. A mismatch compiles and runs, but ignores the index and scans every row.
- **The extension comes first.** The first migration in the app enables the extension (VectorExtension()). It must run before the migration that creates Chunk, and the database user needs permission to create extensions.

## Uploads: Trust Nothing

An upload endpoint accepts files from strangers and hands them to parsers, which are among the most attacked pieces of software there are. So the endpoint is a series of checks, cheapest first, and the file is not stored until it has passed the ones that need no parsing.

*(figure: see the printed book)*

| **Order** | **Check** | **Why it is there** |
|---|---|---|
| 1 | Authenticated, throttled | Anonymous uploads are free storage for attackers |
| 2 | Plan limits: document count and file size | Refuse before reading a 2 GB file into memory |
| 3 | **Magic bytes**, not the file name or Content-Type | A Windows program renamed invoice.pdf must not get as far as a PDF parser. We check that PDFs start with %PDF- and Word files with the zip signature, and that the extension matches the contents |
| 4 | **Hash** the content, look for a duplicate | The same file again costs nothing: return the existing document |
| 5 | Store in a **private** bucket | Never a public one: documents are customers’ secrets |
| 6 | Queue the ingestion **after the transaction commits** | Otherwise the worker can start before the row exists |
| 7 | Respond 202 Accepted immediately | The user sees the document appear as "processing" |

**python docuask/views.py (the upload view, shortened)**

```python
def post(self, request):
    upload = request.FILES.get("file")
    plan = plan_of(request.user)
    check_upload(plan, upload.size, Document.objects.filter(owner=request.user).count())   # 429 if over a limit
    data = upload.read()
    sniff_type(data, upload.name)                                  # 400 for the wrong kind of file
    digest = hashlib.sha256(data).hexdigest()
    existing = Document.objects.filter(owner=request.user, sha256=digest).first()
    if existing:
        return Response(DocumentSerializer(existing).data, status=200)
    with transaction.atomic():
        doc = Document.objects.create(owner=request.user, ..., sha256=digest)
        transaction.on_commit(lambda: ingest_document.delay(doc.id))
    return Response(DocumentSerializer(doc).data, status=202)
```

Notice what the view does **not** do: it does not parse the file. Parsing happens in the worker, where a crash or a slow file cannot take the web server down, and where a time limit applies.

> **Viruses and malicious documents**
>
> We never execute anything inside an uploaded file, and we only extract text. That removes most of the danger, but it is not the same as scanning for malware. If your customers will download documents again, or share them with other people, add a malware scan to the pipeline (a scanning service or ClamAV) and keep the file out of reach until it passes. Chapter 16 covers storage rules; Chapter 17 covers upload limits.


## Extracting Text › Format by format

| **Format** | **How we read it** | **Page numbers** | **Known limits** |
|---|---|---|---|
| **PDF** | pypdf, one page at a time | Real page numbers | Scans have no text and are refused with a message about OCR. Tables and multi-column layouts can come out in a confusing order |
| **Word (.docx)** | python-docx: paragraphs, then each table row with a vertical bar between its cells | None (Word has no fixed pages) | Text boxes, headers and comments are not read. Citations show the document title without a page |
| **.txt and .md** | UTF-8, with a fallback for old Windows encodings | A form feed character starts a new page, otherwise none | Markdown is read as plain text |


## Extracting Text › Failing in a way the user can act on

Every failure raises an ExtractionError whose message is **written for the user**, never an internal error. These are the cases the tests cover, using real files created on the fly:

| **File** | **What the user is told** |
|---|---|
| A PDF with only images (a scan) | "This PDF has no selectable text (it looks like a scan). Run OCR on it first, then upload it again." |
| A password-protected PDF | "This PDF is password protected. Remove the password and upload it again." |
| A damaged PDF | "This PDF could not be read. It may be damaged; try printing it to a new PDF." |
| More pages than the plan allows | "This PDF has 700 pages; the limit is 500." |
| An executable renamed to .pdf | "This file type is not supported..." |
| A zip bomb saved as .docx | "This Word file expands to an unreasonable size and was rejected." |

The last one deserves a sentence. A .docx file is a zip archive, and a few kilobytes can decompress to gigabytes. The extractor adds up the declared uncompressed sizes **before** any parser opens the file and refuses anything above the limit. The test builds a 5 MB file of zeros that compresses to a few kilobytes and checks that it is rejected.


## Chunking › Our rules

1. **A chunk never crosses a page.** Then every citation has an exact page number. The cost is that a sentence that continues over a page break is split. That is the right trade for a citation product.
2. **A chunk ends at a sentence boundary.** A cited passage should read like a quotation, not start in the middle of a word.
3. **Neighbouring chunks overlap by one sentence.** An answer that straddles a boundary is still found by at least one chunk.
4. **A tiny chunk at the end of a page is merged** into the previous one when it fits, so we do not index fragments such as a lone footer line.
5. **A "sentence" that is longer than the maximum** (a table row, a list run together) is cut at word boundaries, so no chunk can exceed the limit.
Here is the real output on the handbook page of the sample corpus (small chunks, so you can see the overlap):

**text verified output: chunks of the sample handbook**

```text
3 pages
chunk 0 page 1 ~45 tokens: Acme Employee Handbook Working hours and leave Full-time employees work 40 hours per week. Core...
chunk 1 page 1 ~51 tokens: Core hours are 10:00 to 15:00, when everyone is expected to be available for meetings. Outside ...
chunk 2 page 1 ~53 tokens: Annual leave is 25 days per year and accrues monthly. You may carry over up to 5 unused days in...
chunk 3 page 1 ~40 tokens: Sick leave is 10 paid days per year. A doctor's note is required after 3 consecutive days of ab...
```

Notice that the first chunk contains the title and the heading glued to the first sentence, because our chunker does not understand headings. That is a real limitation. A heading-aware chunker that stores the section title with each chunk, and prepends it to the text that is embedded, often improves retrieval noticeably. It is an exercise in 57.12.

The tests check the properties that matter, not exact output: no chunk exceeds the limit, chunks never cross pages, every sentence of the input appears in some chunk, the overlap really repeats the previous sentence, a giant unpunctuated run is cut up, empty pages produce no chunks, and the hash is stable so that identical text can be recognised.


## Embeddings › Using Voyage AI

Anthropic’s documentation states that it does not offer its own embedding model and points to Voyage AI. The relevant facts for our code are these:

- You create an API key and use the voyageai package. The default output size of the current model family is 1024 dimensions, with smaller and larger options.
- Voyage takes an **input type**: "document" when you index text, "query" when you search. The two are processed slightly differently so that questions match answers. **Always set it.** Forgetting it is a common quiet quality loss.
- The vectors are normalised to length 1, so the dot product equals the cosine similarity.
- There are also reranking models, which re-score the top results for even better ordering. We leave them out to keep the project focused; they are a good upgrade once you have an evaluation to prove that they help.
Model names and dimensions change, so read Anthropic’s embeddings page and the provider’s documentation before you pick. The code takes the name and size from settings.


## Embeddings › One interface, two implementations

**python docuask_core/embeddings.py (the interface)**

```python
class Embedder(Protocol):
    dimensions: int
    model_name: str
    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]: ...
    def embed_query(self, text: str) -> List[float]: ...
```

The project has two implementations. **VoyageEmbedder** is the real one. **HashingEmbedder** is a stand-in for tests: it hashes each word into one of a few hundred slots and normalises the result. It is deterministic and runs offline, but it is **not semantic**: it knows "leave" and "leaves" are related (it strips common endings) and nothing about synonyms. That is exactly what we want in a test, since the result never changes, and exactly what we must never ship.


## Embeddings › Batching, retries and the free lunch

A 300-page document is several hundred chunks. Calling the provider once per chunk would be slow and would hit rate limits, so embed_in_batches groups texts by **count and by total size**. It also retries temporary failures (rate limits, timeouts, 5xx) with exponential backoff: wait 1, 2, 4, 8 seconds, then give up. The tests cover the batching boundaries, the exact delays of the retry, giving up after the last attempt, **not** retrying a permanent error such as invalid input, and detecting a provider that returns the wrong number of vectors.

> **Your data leaves your server**
>
> Embedding and answering send your customers’ text to third-party APIs. Tell your customers which providers you use, check each provider’s retention and training terms (many offer terms under which API data is not used for training), and put this in your privacy policy (Chapter 34). If a customer’s data must not leave a region or a network, you need a self-hosted embedding model and a different answer model, and this architecture still works: the Embedder interface is the seam.


## The Ingestion Task

Now we connect the steps into a Celery task (Chapter 15). It looks long, but every line exists to survive one specific failure.

**python docuask/tasks.py (the structure of ingest_document)**

```python
@shared_task(bind=True, acks_late=True, autoretry_for=(TransientEmbeddingError,), retry_backoff=True,
             retry_backoff_max=300, retry_jitter=True, max_retries=5, soft_time_limit=900, time_limit=960)
def ingest_document(self, document_id):
    with transaction.atomic():
        doc = Document.objects.select_for_update().select_related("owner").get(pk=document_id)
        if doc.status == Document.Status.READY:
            return                                         # a duplicate delivery: nothing to do
        doc.status = Document.Status.PROCESSING
        doc.save(update_fields=["status", "error_message", "updated_at"])
    try:
        pages = extract_pages(file_bytes, doc.original_filename, max_pages=plan.max_pages_per_file)
        usage.consume(doc.owner, plan, "pages", needed - doc.pages_charged)      # charge once, even on retry
        chunks = chunk_pages(pages)
        vectors = embed_in_batches(get_embedder(), [c.text for c in chunks])
    except ExtractionError as exc:
        _fail(doc, str(exc)); return                       # the user's file is the problem: do not retry
    ...
    with transaction.atomic():
        Chunk.objects.filter(document=doc).delete()        # idempotent: a retry starts clean
        Chunk.objects.bulk_create([...], batch_size=200)
        Chunk.objects.filter(document=doc).update(search_vector=SearchVector("text", config="english"))
        Document.objects.filter(pk=doc.pk).update(status="ready", page_count=..., chunk_count=...)
```

| **Line** | **The failure it prevents** |
|---|---|
| acks_late=True | If the worker dies mid-task, the job is delivered again instead of being lost |
| select_for_update and the READY check | Two deliveries of the same job cannot both run, and a repeat of a finished job does nothing |
| Delete old chunks, then insert | Running the task twice never leaves duplicate or half-old chunks. The status flips to ready in the **same transaction** as the chunks, so nobody sees a ready document without its chunks |
| ExtractionError is not retried | A scanned PDF will still be a scanned PDF in five minutes. Retrying only wastes the queue |
| autoretry_for=(TransientEmbeddingError,) with backoff and jitter | A rate limit from the provider resolves itself. Jitter prevents all retries from landing at the same second |
| pages_charged and the refund in _fail | A document that fails does not cost the customer their quota, and a retry does not charge twice |
| soft_time_limit and time_limit | A pathological file cannot occupy a worker forever |
| A separate queue (ingest) | A flood of uploads does not delay the Celery tasks of the rest of the app |
| User-safe messages only | The error saved on the document is shown to the customer. Stack traces go to the logs, never to the screen |

Run the worker with its own queue and a memory limit per child process (PDF parsing can be memory hungry), for example celery -A config worker -Q ingest -c 2 --max-tasks-per-child=50. In Dokploy (Chapter 54) this is one more service in the Compose file, using the same image as the API.


## The Frontend › States to design on purpose

| **State** | **What to show** |
|---|---|
| No documents yet | An empty state with the upload box and a sample question |
| Processing | The document in the list with a spinner and "Processing", and the ask box limited to ready documents |
| Failed | The reason, in the server’s words, and a button to delete or retry |
| Refusal | The fixed sentence, plus a hint: "Try different words, or check that the right document is uploaded" |
| Ungrounded | The answer with the amber warning |
| Over the limit | The limit message with the reset date and an upgrade button (Chapters 35 to 38), not a generic error |
| Connection lost | A reconnect, and the current question stays in the box |


## Evaluating Quality

You will change the chunk size, the prompt, the embedding model, the fusion method. Each change might help, hurt or do nothing, and you cannot tell by trying three questions. So we build a **small, repeatable test of retrieval** now, before the project grows. Chapter 33 covers evaluation in general; this is the version for this product.


### The evaluation set

A list of questions, each with the document and page where the answer lives, plus some questions that **cannot** be answered from the documents. The chapter’s code has 25 questions over three short sample documents: 20 answerable and 5 not.

**json tests/fixtures/eval_cases.json (two entries)**

```json
{"question": "How many days of annual leave do I get?", "doc": "employee_handbook.txt", "page": 1, "answerable": true}
{"question": "What is the CEO's salary?", "doc": null, "page": null, "answerable": false}
```


### The metrics

| **Metric** | **Means** | **Why it matters** |
|---|---|---|
| **hit@k** | The right page is in the top k results | If it is not retrieved, the model cannot use it. hit@5 is the ceiling for answer quality |
| **MRR** (mean reciprocal rank) | The average of 1 divided by the rank of the right result | Rewards putting the right passage first, which matters when the token budget allows few passages |
| **No-answer separation** | The best similarity of answerable questions versus unanswerable ones | Tells you where to put the refusal threshold |


### Running it

**bash terminal**

```bash
python3 -m docuask_core.evals
```

**text verified output: the sample corpus with the stand-in embedder**

```text
26 chunks from 3 documents, 25 questions (embedder: hashing-bow)

mode       hit@1  hit@3  hit@5     MRR
vector      0.95   1.00   1.00    0.97
keyword     0.90   1.00   1.00    0.95
hybrid      1.00   1.00   1.00    1.00

No-answer gate: best similarity for answerable questions 0.17 to 0.66; for unanswerable 0.00 to 0.21
Best threshold on this set: 0.17 (classifies 96% of questions correctly)
```

> **Do not be impressed by these numbers**
>
> They come from three short documents with 26 chunks, questions written by the same person who wrote the documents (so they share vocabulary), and a stand-in embedder that is lexical. Real documents are longer, messier and full of near-duplicates, and real questions are vaguer. The numbers show that the **harness works** and that hybrid is not worse than either half. They do **not** show how your product performs. Build the set from **your customers’ real documents and real questions**, aim for at least 50 questions, and expect much lower numbers.


### Using it well

- **Run it with the real embedder:** python3 -m docuask_core.evals --embedder voyage (with VOYAGE_API_KEY set) and point --corpus and --cases at your own folders. Then compare the modes, and choose the refusal threshold from **your** distribution of similarities.
- **Change one thing at a time,** and keep a log: chunk size, overlap, fusion, embedding model, with the numbers before and after.
- **Look at the misses.** The harness prints the questions it failed. Each one teaches you something: a paraphrase the keyword search cannot find, a chunk boundary that split the answer, a table the extractor garbled.
- **Add every real failure to the set.** When a customer reports a wrong answer, add that question with its correct page. The set grows into your regression test.
- **Make it a gate** in CI (Chapter 42): fail the build if hit@3 drops below the bar.

### Beyond retrieval

Retrieval quality is necessary, not sufficient. Also sample real answers and check three things by hand each week: is the answer **supported** by the cited passage, is it **complete**, and was a **refusal** justified. For scale, an LLM can grade answers against the passages (Chapter 33), but calibrate the grader against your own judgement first. Track the share of ungrounded answers, the share of refusals, and the thumbs-down rate as production metrics (Chapter 55).


## Deploying DocuAsk

The deployment follows Chapters 53 and 54, with five differences.

| **Topic** | **What changes** |
|---|---|
| **The database** | Create the PostgreSQL Dokploy Database from a pgvector image (pin the tag), not the plain PostgreSQL image. The first migration enables the extension, which needs a user that may create extensions: the image’s main user does |
| **A worker service** | Add a Compose service for ingestion: celery -A config worker -Q ingest -c 2 --max-tasks-per-child=50, from the same image, with its own memory limit. Keep the default worker for the other queues |
| **Secrets** | Add ANTHROPIC_API_KEY and VOYAGE_API_KEY (and model names) to the Environment tab, with spending limits set in each provider’s dashboard |
| **Uploads** | Use a private S3-compatible bucket for files (Chapter 16), not the container’s disk, so files survive redeploys. Check the maximum request size your proxy allows |
| **Backups** | The database backup now includes vectors, so it is larger. Restore it in the drill and run a test search afterwards. The index is rebuilt on restore, which can take a while for large tables |

**yaml docker-compose.prod.yml (an extra service for Chapter 54's file)**

```yaml
  docs-ingest:
    image: chat-backend:${GIT_SHA:-prod}
    command: celery -A config worker -Q ingest -c 2 --max-tasks-per-child=50 -l info
    environment: *backend-env
    restart: unless-stopped
    networks: [dokploy-network]
```

Do not forget to add the new variables to the .env example, so that the compose linter from Chapter 54 keeps working. Add a **queue length** check to your monitoring (Chapter 55): a growing ingestion queue means uploads are waiting, and the user who just uploaded a file notices before you do.


### Changing the embedding model later

You will eventually want a better model. The safe procedure is: add a second vector column (or a new table) for the new model, re-embed in a background job while the old column keeps serving, run the evaluation on both, switch the search to the new column, and drop the old one after a week. Document.embedding_model tells you which documents are done. Never overwrite vectors in place while searching: for a while, queries and chunks would be in different spaces.
