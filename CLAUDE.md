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