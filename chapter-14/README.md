# Chapter 14 — Real-Time Features with Django Channels

*Part III: Backend Development with Django*

Companion material for Chapter 14 of *Building AI-Powered Apps*.

| Folder / file | What it is |
|---|---|
| `code/` | Code for this chapter (`chat`, `config`, `core`, `env.example`, `examples`, `reconnecting-socket.js` …) |
| `listings/` | 4 complete listings that the printed chapter points to |
| `EXTENDED.md` | Material moved out of the print edition |

**About the code.** The files in `code/` were assembled from the listings printed in the chapter. Where a chapter built a file in several steps, the steps are joined in order or kept as `*.excerpt*` files. They were syntax-checked (Python and JSON) but have not been run as a complete project; compare them with the chapter text.

## Running it

```bash
cd chapter-14/code
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

See the chapter for the exact commands, environment variables and expected output.
