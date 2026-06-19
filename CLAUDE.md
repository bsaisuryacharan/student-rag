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

## Challenges log (`CHALLENGES.md`)

This repo keeps a `CHALLENGES.md` that records problems found during development
and the solutions we landed on. Maintain it continuously, per these rules:

**Content rule (strict):** `CHALLENGES.md` holds ONLY the actual problems and their
solutions. No meta-content — no process notes, triggers, or "how to maintain"
instructions inside the doc. Those rules live here in `CLAUDE.md`.

**When to edit `CHALLENGES.md`:**
1. When a problem is **identified and confirmed** to be real and worth tracking
   (after discussion agrees it matters — not the instant it's first noticed) → add it.
2. When we **agree on a solution** → add the solution to that problem's entry.
3. When problem or solution **details change** → revise the existing entry.

**Sections:** "Resolved Challenges" for solved items; "Future Problems" for items
agreed worth solving but deferred.

Do this proactively without being re-asked.