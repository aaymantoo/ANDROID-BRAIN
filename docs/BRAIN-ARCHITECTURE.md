Redesign the Brain enrichment pipeline to support incremental, phase-by-phase persistence instead of generating the entire Brain in a single run.
Current problem:
Large PRDs require processing the entire document before saving. If the AI times out, fails, or loses context, all progress can be lost.
Goal:
Persist Brain artifacts after every completed phase and feature so enrichment is resumable, fault-tolerant, and scalable to very large PRDs.
Target structure:
brain/
│
├── project.json
│
├── features/
│   ├── auth/
│   │   ├── feature.json
│   │   ├── screens.json
│   │   ├── business_rules.json
│   │   ├── state_machines.json
│   │   ├── repositories.json
│   │   ├── usecases.json
│   │   └── tests.json
│   │
│   ├── profile/
│   │   └── ...
│   │
│   ├── booking/
│   │   └── ...
│   │
│   └── payments/
│
├── roadmap/
│   ├── roadmap.json
│   └── phases.json
│
├── graphs/
│   ├── dependency_graph.json
│   ├── navigation_graph.json
│   ├── architecture_graph.json
│   └── impact_graph.json
│
├── generation/
│   ├── status.json
│   ├── history.json
│   └── sessions.json
│
└── cache/
    └── aggregated_brain.json
Required behavior:
Parse PRD into phases first.
Process one phase at a time.
Process one feature at a time inside a phase.
Save feature artifacts immediately after successful extraction.
Run audit_brain()(yet to be build AUDIT-BRAIN.md) for that feature before marking it complete.
Update roadmap and generation status after every feature.
Support resume after interruption.
Never require full PRD regeneration when only one feature changes.
Allow:
brain enrich-phase auth
brain enrich-feature booking
brain resume
Generate aggregated_brain.json as a derived cache, never as the primary source of truth.
Implement checkpointing:
Phase ↓ Feature ↓ Save Feature Brain ↓ Validate ↓ Update Status ↓ Continue
If failure occurs:
brain resume
must continue from the last successfully completed feature instead of restarting enrichment.
Provide:
architecture design
migration strategy from current monolithic enrichment
checkpoint design
status tracking design
resume algorithm
file formats
MCP tools required
code changes required
impact on existing generation pipeline
token savings estimate
failure recovery design
The objective is to make enrichment deterministic, resumable, and safe for very large PRDs while minimizing changes to the existing generation and validation pipeline.
