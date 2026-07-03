# Capabilities Index

One file per discrete capability. Phase mapping matches [`roadmap.md`](../roadmap.md).

## Capabilities in This Project

| Phase | Capability | File |
|-------|-----------|------|
| 1 | Dataset upload & auto-profile | [dataset_upload_profile.md](dataset_upload_profile.md) |
| 1 | Local code-execution sandbox | [code_execution_sandbox.md](code_execution_sandbox.md) |
| 1 | Analytical Q&A (plan→code→execute→answer) | [analytical_qa.md](analytical_qa.md) |
| 2 | Conversation & persistent sessions | [conversation_sessions.md](conversation_sessions.md) |
| 2 | Visual outputs (charts + tables) | [visual_outputs.md](visual_outputs.md) |
| 2 | Quality insights & cost transparency | [quality_insights.md](quality_insights.md) |
| 3 | Multi-dataset (files, joins, folders) | [multi_dataset.md](multi_dataset.md) |
| 3 | Data exports (cleaned CSV, chart images) | [data_exports.md](data_exports.md) |
| 3 | Report generation | [document_generation.md](document_generation.md) |

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer creates a new `<name>.md`, updates this index, flags dependencies, and self-reviews against the architecture and data model.
