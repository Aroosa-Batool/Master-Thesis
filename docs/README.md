# Documentation index

This directory separates user-facing setup instructions, design rationale,
implementation details, and thesis evidence. Start with the root
[`README.md`](../README.md) if you want to install or run the prototype.

| Document | Use it for |
| --- | --- |
| [`confluence_system_documentation.md`](confluence_system_documentation.md) | A single self-contained page designed to be copied from a rendered Markdown preview into Confluence. |
| [`codebase_guide.md`](codebase_guide.md) | Entry points, module ownership, runtime flows, state schemas, configuration, and current implementation caveats. |
| [`design_hld.md`](design_hld.md) | Product intent, consent model, requirements, privacy reasoning, trade-offs, and threat model. |
| [`technical_hld.md`](technical_hld.md) | Algorithms, thresholds, interfaces, concurrency, deployment, and source traceability. |
| [`algorithm_comparison.md`](algorithm_comparison.md) | Literature-backed comparison of the camera and voice algorithms and the measured benchmark results. |
| [`literature_review.md`](literature_review.md) | Research background, gaps, candidate thesis directions, and research questions. |
| [`../robot/bench/README.md`](../robot/bench/README.md) | Reproducing latency/memory benchmarks and collecting a labelled evaluation set. |

## Documentation boundaries

- The root README is the operator quick start.
- The codebase guide describes what the current source tree actually executes.
- The design HLD describes the intended privacy and interaction model.
- The technical HLD explains how that design is implemented and explicitly
  calls out deviations in the current prototype.
- The comparison and literature documents are thesis evidence; they are not
  required to operate the demo.

Runtime identity, consent, and reminder JSON files contain participant-related
data and are not documentation. See [Runtime data and schemas](codebase_guide.md#7-runtime-data-and-schemas)
before collecting data or sharing a checkout.
