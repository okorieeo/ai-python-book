"""A guided tour that prints real output for each tool in this chapter: python -m rag.tour"""
import json
from pathlib import Path

from prompts.llm import ScriptedLLM
from prompts.registry import PromptRegistry

from .chunking import chunk_stats, fixed_size_chunks, markdown_chunks, paragraph_chunks
from .demo import CASES, DOCS, POISONED_DOCS, build_demo, demo_answer_model
from .embeddings import HashingEmbedder, cosine
from .evaluate import evaluate_retrieval, format_comparison
from .fusion import reciprocal_rank_fusion
from .ingest import ingest_document
from .lexical import BM25Index
from .pipeline import answer_question
from .retrieval import Retriever

LIBRARY = Path(__file__).resolve().parent / "prompt_library"


def title(text):
    print(f"\n== {text}")


def main():
    registry = PromptRegistry(LIBRARY)
    retriever, store = build_demo()

    title("1. The same text, three ways (about 300 characters per chunk)")
    text = "\n\n".join(DOCS[d][1] for d in ("refunds", "plans", "security", "uploads"))
    for name, chunker in [("fixed", lambda t: fixed_size_chunks(t, 300, 40)), ("paragraph", lambda t: paragraph_chunks(t, 300)),
                          ("markdown", lambda t: markdown_chunks(t, 300))]:
        chunks = chunker(text)
        print(f"{name:<10} {chunk_stats(chunks)}")
        if name == "markdown":
            for c in chunks[:4]:
                print(f"           #{c.index} {' > '.join(c.heading_path):<42} {c.text[:34]!r}")
    chunk = markdown_chunks(text, 300)[2]
    print(f"\nchunk #{chunk.index}: path={chunk.heading_path} chars {chunk.start}-{chunk.end}")
    print("source slice equals chunk text:", text[chunk.start:chunk.end] == chunk.text)

    title("2. Similarity with the toy embedder (cosine, 1.0 = same direction)")
    embedder = HashingEmbedder()
    texts = ["How do I get a refund?", "reimbursement policy", "Upload a PDF file"]
    vectors = embedder.embed_documents(texts)
    for i in (1, 2):
        print(f"{texts[0]!r} vs {texts[i]!r}: {cosine(vectors[0], vectors[i]):.2f}")

    title("3. Keyword search finds an exact identifier")
    index = BM25Index()
    for key, (_, body) in DOCS.items():
        index.add(key, body)
    for key, score in index.search("ERR_4021", k=3):
        print(f"{key:<10} score={score:.2f}")

    title("4. Reciprocal rank fusion, worked example (k = 60)")
    vector_list, keyword_list = ["plans", "security", "languages"], ["plans", "languages", "export"]
    for key, score in reciprocal_rank_fusion([vector_list, keyword_list]):
        print(f"{key:<10} {score:.4f}   vector rank {vector_list.index(key) + 1 if key in vector_list else '-'}, "
              f"keyword rank {keyword_list.index(key) + 1 if key in keyword_list else '-'}")

    title("5. One question, three retrieval modes: 'Is single sign-on available?'")
    for mode in ("vector", "keyword", "hybrid"):
        docs = [h.record.doc_id for h in retriever.search("Is single sign-on available?", "acme", mode=mode)]
        print(f"{mode:<8} {docs}")

    title("6. Retrieval evaluation on 15 questions (hit rate and MRR at 3)")
    print(format_comparison([evaluate_retrieval(retriever, CASES, k=3, mode=m) for m in ("vector", "keyword", "hybrid")]))

    title("7. A grounded answer, a refusal and an invented quote")
    llm = ScriptedLLM(demo_answer_model)
    ask = lambda q, model=llm, owner="acme": answer_question(q, owner_id=owner, retriever=retriever, registry=registry, llm=model)
    result = ask("When do approved refunds appear on my card?")
    print("answer :", result.answer)
    for c in result.citations:
        print(f"cite   : [{c.source_id}] {c.section} -> \"{c.quote}\" (characters {c.start}-{c.end})")
    result = ask("What is the airspeed of a swallow?")
    print(f"refused: found={result.found} reason={result.refused_reason} model_calls={len(llm.calls) - 1}")
    liar = ScriptedLLM([json.dumps({"found": True, "answer": "Refunds are instant [S1].",
                                    "citations": [{"source_id": "S1", "quote": "refunds are always instant"}]})])
    result = ask("How long do refunds take to arrive?", liar)
    print(f"invented quote: found={result.found} reason={result.refused_reason}")
    print("problem:", result.problems[0])

    title("8. A poisoned document is flagged at ingestion and kept out of answers")
    doc_title, body = POISONED_DOCS["release_notes"]
    report = ingest_document(doc_id="release_notes", owner_id="acme", title=doc_title, text=body, embedder=embedder, store=store)
    print(f"ingested chunks={report.chunks} flagged={report.flagged}")
    lenient = Retriever(embedder, store, max_injection_risk="high")
    print("default retriever :", [h.record.doc_id for h in retriever.search("release notes version 2.4 export bug", "acme")])
    print("lenient retriever :", [h.record.doc_id for h in lenient.search("release notes version 2.4 export bug", "acme")])

    title("9. Two customers, one index")
    question = "When is the Project Falcon launch date?"
    for owner in ("acme", "globex"):
        result = ask(question, owner=owner)
        print(f"{owner:<7} found={result.found} sources={[h.record.doc_id for h in result.hits]}")


if __name__ == "__main__":
    main()
