# Design decisions

- **Python** keeps parsing, validation and analytics accessible and uses the installed local runtime.
- **Pandas** provides concise and reproducible latency percentiles and chart-ready query results.
- **SQLite** needs no server, supports constraints/transactions, and fits a local challenge project.
- **Streamlit** exposes a usable upload-and-review flow with little frontend code.
- **Pytest** makes important data rules repeatable with temporary databases.

The implementation favors a small set of explicit functions and parameterized SQL. SQLite uniqueness is the final guard against duplicate writes; a duplicate is persisted as quarantine metadata so each row is accounted once. Fingerprints are content-based and can conflate identical legitimate events; producers should send unique IDs when available. Naive timestamps assume UTC. Source schema versions are short hashes over sorted field names, enough to compare observed shapes without a schema registry. Additive columns are accepted and warned; missing required columns are rejected and warned. Batch commits make retry behavior explicit: failed batches roll back while earlier commits remain. The model has a run foreign key but no domain reference tables, so other reference-key validation would invent an entity. A larger deployment could add schema contracts, streaming reads, retention and stronger observability while retaining this flow.

The synthetic generator writes its expected per-line categories to a separate JSON sidecar, keeping test labels out of the source events.
