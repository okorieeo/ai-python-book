# Chapter 6 — System Architecture for Beginners: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Qualities a System Must Balance › Turning vague wishes into measurable targets

| **Vague** | **Measurable** |
|---|---|
| "It should be fast" | 95% of API requests answered in under 300 ms; first AI token within 2 s |
| "It should be reliable" | Failed AI calls are retried; if all fail, the user sees a clear message and nothing is lost |
| "It should scale" | Supports 2,000 daily active users at launch; designed so 20,000 needs only more containers |
| "It should be cheap" | Monthly server bill under a set budget; AI cost per user tracked and capped by plan |


## Scalability and Back-of-the-Envelope Estimates › Estimating load with simple arithmetic

Before building, do a rough calculation. This takes five minutes and prevents both under- and over-engineering. Suppose we launch an AI chat app with these **assumptions** (all illustrative; replace them with your own):

| **Assumption** | **Value** |
|---|---|
| Daily active users | 2,000 |
| Messages per user per day | 15 |
| Tokens per message (prompt + history + answer) | about 1,900 (1,500 in, 400 out) |
| Time to generate one answer | about 8 seconds |
| Peak traffic compared with the daily average | 10 times |

| **Calculation** | **Result** |
|---|---|
| Messages per day: 2,000 x 15 | 30,000 |
| Average rate: 30,000 / 86,400 seconds | about 0.35 messages per second |
| Peak rate: 0.35 x 10 | about 3.5 messages per second |
| Concurrent streaming answers at peak: 3.5 x 8 seconds | about 28 open connections |
| Tokens per day: 30,000 x 1,900 | about 57 million |

What the numbers tell us: **28 concurrent connections is trivial** for one modest server, so no need for a cluster or microservices. But **57 million tokens per day** is a real cost; multiply by your provider’s current price per million tokens to get the daily bill, and you see immediately why per-plan limits, caching and token tracking belong in the design from day one. (The concurrency estimate uses the idea that concurrent work = arrival rate x duration of each job.) Always check current provider pricing; it changes.


## Architecture of the Four Capstone Projects

Each capstone reuses the same skeleton and adds specialized pieces. Reading this table now shows you where the book is heading.

| **Project** | **Sync / API** | **Real-time (Channels)** | **Background (Celery)** |
|---|---|---|---|
| **AI Chat Assistant SaaS** | Auth, conversations, plans | Streaming answers | Usage reports, subscription checks |
| **Document Q&A (RAG)** | Uploads, search, citations | Ingestion progress, streaming | Text extraction, chunking, embeddings |
| **Smart Farm Monitor** | Roles, devices, readings | Live sensor dashboards, alerts | Scheduled reports, AI insights |
| **AI Productivity Assistant** | Tasks, calendar | Assistant replies, reminders | Reminders, agent actions |
