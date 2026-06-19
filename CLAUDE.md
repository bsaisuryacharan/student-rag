## Graph-first repo navigation

This repo has a prebuilt knowledge graph in `graphify-out/`.

Before reading broad source files, use graphify:

- For architecture or codebase questions:
  `graphify query "<question>"`

- For a focused concept:
  `graphify explain "<concept>"`

- For relationships between two things:
  `graphify path "<A>" "<B>"`

Only read raw files after graphify has identified the relevant files, symbols, or source locations.

Important files:
- `graphify-out/graph.json` - raw graph
- `graphify-out/GRAPH_REPORT.md` - architecture/audit summary
- `graphify-out/graph.html` - interactive visual graph

After changing code, run:

```bash
graphify update .
```

## Challenges log (`CHALLENGES.txt`)

This repo keeps a plain-text `CHALLENGES.txt` that records problems found during
development and the solutions we landed on. Maintain it continuously, per these rules:

**Format:** plain text, no markdown formatting (no tables/bold/headers). Each entry is a
short problem (~2 lines) and a short solution (~3-4 lines), with the entry id and, when
resolved, the commit/files. Keep it easy to scan.

**Describe generically:** state the underlying problem and the general solution, NOT the one
example that surfaced it. (e.g. "a query targeting a specific page can cite the wrong page",
not "Part B Set 2 cited page 1".) The example may guide your wording, but the entry must read
as a general issue that applies broadly.

**Content rule (strict):** `CHALLENGES.txt` holds ONLY the actual problems and their
solutions. No meta-content — no process notes, triggers, or "how to maintain"
instructions inside the file. Those rules live here in `CLAUDE.md`.

**When to edit `CHALLENGES.md`:**
1. When a problem is **identified and confirmed** to be real and worth tracking
   (after discussion agrees it matters — not the instant it's first noticed) → add it.
   Do this **without asking for permission** — log it as soon as it's confirmed.
2. When we **agree on a solution** → add the solution to that problem's entry.
3. When the problem or solution **changes** — details revised, scope altered, or we
   decide to **skip/defer** it → update, re-scope, or move the existing entry to match.
   Consider the intent behind what's said, not just the literal words.

**Sections:** "Open Challenges" for confirmed-but-unsolved; "Resolved Challenges" for
solved items (with solution); "Future Problems" for items agreed worth solving but deferred.

Do this proactively throughout development without being re-asked.