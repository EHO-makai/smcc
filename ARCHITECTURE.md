# SMCC — State Management of Compiled Context

## Architecture

### Status

This document defines the architecture and implementation boundaries for SMCC.

It incorporates the initial architecture and the bootstrap architecture decisions of 2026-09-30. Where this document and earlier drafts disagree, this document is authoritative for the initial vertical slice.

The immediate objective is to build the first usable vertical slice while preserving the architectural properties needed for later cloud and local coding-agent integrations.

SMCC should begin using its own discipline during implementation. The `smcc` repository is therefore the first SMCC-managed project.

This is the canonical root architecture document: `ARCHITECTURE.md`.

---

# 1. Purpose

SMCC is a typed, versioned, dependency-aware project-state system for coding agents.

Its purpose is to replace reliance on accumulated conversational context with explicit, durable project state and task-specific compiled context.

The initial system is deliberately **not** an autonomous multi-agent framework.

The first version will support:

* one coding agent;
* explicit authoritative project state;
* a task DAG;
* deterministic task-specific context compilation;
* structured task results;
* proposed state changes;
* human acceptance or rejection of consequential state transitions;
* dependency-aware invalidation;
* repository-visible provenance.

The primary design objective is:

> Give coding agents exactly the authoritative state needed for the current task while preserving human control over consequential project-state changes.

---

# 2. Core architectural principles

## 2.1 State is authoritative

Important project knowledge must not exist only in model context, chat history, prompts, or human memory.

SMCC maintains explicit durable state. The v1 authoritative state types are:

* Goal
* Requirement
* Constraint
* Decision
* Question
* Finding

Tasks, Results, Proposals, Contexts, and Artifacts are SMCC objects, but they do not live under the authoritative `state/` hierarchy.

Deliberately deferred concepts:

* **Assumption** and **Risk** are deferred unless the vertical slice exposes a concrete requirement for them.
* **TestResult** lives inside structured task Results for v1.

Other concepts may be introduced when demonstrated by the workflow.

Agents consume this state. They do not recreate the project model from conversation history.

---

## 2.2 Context is compiled, not accumulated

Each task receives a task-specific context package compiled from authoritative project state.

Conceptually:

```text
authoritative project state
        +
task/node state
        +
dependency outputs
        +
relevant decisions and constraints
        +
selected artifacts
        ↓
context compiler
        ↓
task-specific context package
        ↓
coding agent
```

The compiler should include only state relevant to the task.

This is both:

* a reliability mechanism; and
* an inference-efficiency mechanism.

The system should reduce repeated reconstruction of history, stale context, unnecessary context tokens, and state drift between coding sessions.

---

## 2.3 Agents propose; authoritative state transitions are explicit

An agent saying something does not make it project truth.

The intended transition is:

```text
agent performs task
        ↓
structured result
        ↓
proposed state change
        ↓
validation / human review
        ↓
accepted authoritative state transition
```

Consequential project state must not silently change because an agent emitted prose or modified a file.

**Enforcement honesty.** During initial bootstrap, the separation between "agent proposes" and "human accepts" is primarily a workflow convention. An agent with repository write access is technically capable of modifying `.smcc/state/` directly. Do not claim otherwise. The first implementation nevertheless makes the intended path concrete:

```text
agent result
    ↓
proposal file
    ↓
human review
    ↓
smcc proposal accept | reject
    ↓
authoritative state transition
```

Hand editing remains acceptable while bootstrapping components that do not yet exist.

---

## 2.4 Human supervision is part of the architecture

SMCC is designed for supervised coding-agent workflows rather than maximum autonomy.

The human remains explicitly involved in:

* confirming project goals;
* approving architectural changes;
* accepting important new requirements or constraints;
* reviewing broad-impact state changes;
* reviewing security-sensitive changes;
* accepting or rejecting proposed authoritative state updates;
* accepting completed task results where appropriate.

Routine execution should not require unnecessary ceremony.

---

## 2.5 Execution environment does not define project state

SMCC must support different coding-agent environments without coupling its state model to any one of them.

Initial targets include:

```text
SMCC core
   |
   +-- CLI
   |
   +-- VS Code / GitHub Copilot integration
   |
   +-- future MCP adapter
   |
   +-- Anuenue / local-model adapter
```

VS Code / GitHub Copilot is an early practical target.

Anuenue does not need feature equivalence with the cloud workflow, but it must be able to consume the same SMCC project-state model and compiled context.

Transport adapters must not define SMCC semantics.

---

# 3. Repository model

## 3.1 Canonical repository

The canonical repository is:

```text
smcc
```

It contains the complete implementation and canonical definition of SMCC.

Likely top-level structure:

```text
smcc/
├── src/
│   └── smcc/
├── tests/
├── templates/
├── docs/
├── .smcc/
├── ARCHITECTURE.md
└── pyproject.toml
```

The exact structure may evolve during implementation.

---

## 3.2 Project sidecar

Every SMCC-managed project contains a `.smcc/` directory alongside the project's normal source tree.

For example:

```text
some-project/
├── src/
├── tests/
├── ...
└── .smcc/
```

`.smcc/` is the project's sidecar state directory.

It contains project-specific SMCC state rather than a copied implementation of SMCC.

The v1 structure is:

```text
.smcc/
├── project.yaml
├── state/
│   ├── goals/
│   ├── requirements/
│   ├── constraints/
│   ├── decisions/
│   ├── questions/
│   └── findings/
├── tasks/
│   └── TASK-001/
│       ├── task.yaml
│       └── results/
│           ├── RESULT-001.yaml
│           └── RESULT-002.yaml
├── contexts/
├── proposals/
├── artifacts/
└── history/
```

This layout may evolve, but changes to it are architectural decisions, not implementation details.

---

# 4. Canonical SMCC versus project-owned state

Four categories must remain distinct.

## 4.1 SMCC core-owned assets

These belong to the canonical `smcc` repository:

* Python implementation;
* schemas and types;
* state-store logic;
* DAG logic;
* context compiler;
* validators;
* proposal / transition logic;
* invalidation logic;
* CLI;
* templates;
* migrations when eventually required;
* tests.

These should not be copied and independently modified inside every participating project.

---

## 4.2 Bootstrap / transportable assets

These are canonical templates that SMCC can instantiate into another repository.

Examples include:

* initial `.smcc/` directory layout;
* base project configuration;
* starter state files;
* schema-version metadata;
* generated-file conventions.

A future command may resemble:

```text
smcc init
```

Its purpose is to instantiate an SMCC project, not to copy the SMCC implementation into that project.

---

## 4.3 Project-owned mutable state

After initialization, project-specific state belongs to that project.

Examples:

* project goal;
* requirements;
* constraints;
* architecture decisions;
* tasks;
* accepted findings;
* task results;
* proposals;
* review history.

SMCC upgrades must not overwrite this state.

---

## 4.4 Generated or ephemeral assets

Examples include:

* compiled context packages;
* caches;
* validation output;
* temporary execution metadata.

**Compiled contexts are committed to Git in v1.** They are retained because they form the inspectable record of exactly what context was supplied to an agent. This decision may be revisited after deterministic reconstruction has been demonstrated reliably.

Whether each *other* generated artifact is committed to Git should be decided deliberately rather than assumed.

---

# 5. SMCC will manage its own implementation

The `smcc` repository is the first SMCC project.

Therefore it contains its own:

```text
smcc/.smcc/
```

Initially, humans may manually create or maintain SMCC state because the software needed to automate the process does not yet exist.

This is intentional.

**The first bootstrap step precedes all implementation code:** hand-author the `.smcc/` fixture for the `smcc` repository itself — its goal, established constraints and decisions, and the first vertical-slice tasks. This forces the first schemas and repository layout to confront real SMCC content before implementation begins. If a primitive feels awkward while representing SMCC itself, it is fixed at near-zero cost.

Development should progressively replace manual SMCC mechanics with implemented SMCC functionality.

Expected bootstrap progression:

```text
manual authoritative state
        ↓
typed state implementation
        ↓
state validation and persistence
        ↓
working context compiler
        ↓
SMCC-generated context drives later SMCC tasks
        ↓
structured result handling
        ↓
state-change proposal workflow
        ↓
accept/reject transitions
        ↓
dependency invalidation and recompilation
```

Do not distort the architecture merely to maximize self-hosting.

Manual operation is acceptable until the corresponding subsystem is ready.

---

# 6. Implementation language and storage

## 6.1 Languages

Primary implementation language:

```text
Python
```

TypeScript may be used where it provides a concrete advantage, particularly for VS Code integration.

Other programming languages should not be introduced without a compelling reason.

---

## 6.2 Serialization and storage

Initial authoritative state uses:

```text
YAML / JSON files
```

Do not introduce a database in the initial implementation unless a demonstrated requirement makes the file-backed model untenable.

The repository/filesystem is intentionally the first persistence and transport mechanism because it is:

* transparent;
* human-readable;
* diffable;
* version-controllable;
* portable;
* easy for coding agents to access;
* usable in cloud and local workflows.

---

# 7. Schema discipline

## 7.1 Typed state

State objects are typed.

**Use Pydantic for schema definition and validation.** Hand-edited YAML during bootstrap makes validation-on-load a first-class requirement, not an option.

Serialized state must include an explicit schema version.

State objects should generally be able to represent metadata such as:

```text
id
type
schema_version
version
status
created_at
updated_at
source
dependencies / references
supersedes
```

This applies to **every persisted SMCC object** — including Task, Result, and Proposal, not only the authoritative `state/` types. Each carries at least `schema_version`, `id`, and whatever version/status metadata is meaningful for that object type. Without this, provenance fields such as `task_version` have no authoritative source.

Do not create a large ontology before the first workflow is operational.

Prefer the smallest schema that correctly expresses the vertical slice.

Schema migration infrastructure can be added later, but the initial serialization format must leave room for migration.

---

## 7.2 State-object versioning

Authoritative state objects are stored as **one current file per object**.

Updating an existing object:

* mutates that file;
* increments its monotonic integer `version`;
* does not create another versioned state file.

Git provides historical file versions.

---

## 7.3 Supersession

`supersedes` does **not** mean "previous version of this object."

It means that one object semantically replaces another distinct object.

Example:

```yaml
id: DEC-007
version: 1
supersedes:
  - DEC-003
```

Ordinary editing of `DEC-003` simply increments `DEC-003.version`.

For v1, whether an object has been superseded is derivable from the superseding relationship rather than requiring an atomic mutation of both objects.

---

## 7.4 Identifiers

Use readable sequential IDs for the initial single-agent implementation:

```text
GOAL-001
REQ-001
CON-001
DEC-001
QUESTION-001
FINDING-001
TASK-001
RESULT-001
PROP-001
```

These IDs are repository-local identifiers.

The v1 scheme does not claim collision-free concurrent allocation across branches.

ID generation may be replaced later without changing the logical object model.

---

# 8. Task DAG

Work is represented as an explicit directed acyclic graph.

## 8.1 Two kinds of dependencies

Tasks distinguish task-DAG dependencies from state/context dependencies:

```yaml
task_dependencies:
  - TASK-001

context_refs:
  - REQ-001
  - DEC-003
```

* `task_dependencies` express ordering and dependency-result relationships.
* `context_refs` express authoritative state required for the task.

Compiled-context provenance records the exact object and version actually consumed.

## 8.2 Task shape

A task will likely include fields resembling:

```yaml
id:
type:
schema_version:
version:
title:
goal:
status:
task_dependencies:
context_refs:
constraints:
acceptance_criteria:
assigned_agent:
outputs:
accepted_result:
proposed_state_changes:
review_state:
```

When a task reaches `accepted`, `accepted_result` names the single authoritative Result for that task (e.g., `RESULT-002` when retries produced multiple results). Dependency-output resolution is then deterministic:

```text
TASK-003 → TASK-001 → accepted_result → RESULT-002
```

Exact fields should be refined during implementation.

Likely task states include:

```text
proposed
ready
in_progress
blocked
review
accepted
rejected
superseded
```

Ordering and dependencies must be represented explicitly rather than inferred from prose.

---

# 9. Context compiler

The context compiler is a core SMCC component.

## 9.1 Selection policy

Context relevance is **explicit** in v1.

Do not implement automatic relevance inference, tag matching, embeddings, semantic search, or LLM-selected context.

A compiled task context contains:

1. the task itself;
2. its acceptance criteria and task-local constraints;
3. the project goal;
4. project-scoped constraints;
5. authoritative objects named by the task's `context_refs`;
6. the accepted Result of each of its `task_dependencies`.

A constraint declares its own scope in the constraint itself (`scope: project`); project-scoped constraints are always included. There is no separate constraint list in `project.yaml`. Future scopes can emerge naturally without redesign.

A dependency's accepted output is the Result named by the dependency task's `accepted_result` field (§8.2). No inference over multiple results.

This selection policy is deterministic and inspectable.

## 9.2 Output format

Initial output is a Markdown context package.

Example conceptual structure:

```markdown
# SMCC Context: TASK-003

## Task

## Goal

## Acceptance Criteria

## Project Goal

## Relevant Requirements

## Relevant Constraints

## Relevant Decisions

## Dependency Outputs

## Relevant Artifacts

## Known Findings

## Open Questions

## Execution Instructions
```

Markdown is intentionally the first format because it is both human-readable and directly consumable by coding agents.

Headings with no selected content are omitted from compiled output. In particular, v1 has no `artifact_refs`; artifact reference semantics are deferred until a first real need defines them.

## 9.3 Provenance frontmatter

Compiled Markdown contexts must include YAML frontmatter recording the versions of all authoritative state and dependency results used to produce the context.

Conceptually:

```yaml
---
task_id: TASK-003
task_version: 2
compiler_version: 0.1

state_refs:
  - id: GOAL-001
    version: 1
  - id: REQ-003
    version: 2
  - id: DEC-004
    version: 1

dependency_results:
  - task_id: TASK-001
    result_id: RESULT-001

content_hash: ...
compiled_at: ...
---
```

A separate context-manifest file is **not** required in v1. The frontmatter serves the immediate machine-readable provenance requirement.

Likely future uses include:

* context caching;
* stale-context detection;
* provenance inspection;
* debugging why a state object entered a context;
* deterministic context hashing.

## 9.4 Deterministic compilation

For v1, deterministic compilation means:

> Given the same task version, same referenced state-object versions, same accepted dependency results, same compiler version, and same selection rules, SMCC produces the same semantic context and `content_hash`.

Generated content must use stable ordering.

`content_hash` is calculated from canonical generated content while excluding volatile fields, including:

```text
compiled_at
content_hash
```

A timestamp may remain in frontmatter for audit purposes without affecting deterministic identity.

## 9.5 Retention

Compiled contexts are committed to Git in v1 (see §4.4).

---

# 10. Structured agent result

The coding agent receives:

* task goal;
* acceptance criteria;
* compiled context;
* relevant repository files;
* permitted tools.

Agent results are structured YAML validated by Pydantic.

Results are persistent and must not be silently overwritten by retries.

Storage organization:

```text
.smcc/
    tasks/
        TASK-001/
            task.yaml
            results/
                RESULT-001.yaml
                RESULT-002.yaml
```

A Result distinguishes at minimum:

```text
work performed
artifacts / files changed
tests run
test results
findings
unresolved questions
proposed state changes
suggested follow-up tasks
Git provenance where available
```

Agent output must distinguish:

```text
what happened
```

from:

```text
what should become authoritative project state
```

---

# 11. State-change proposals

A proposed state change is an explicit SMCC object.

Example lifecycle:

```text
proposed
    ↓
reviewed
    ↓
accepted | rejected
```

## 11.1 Atomicity

**One proposal represents one change to one authoritative state object.**

A task Result may produce zero or more Proposals.

Each Proposal can therefore be independently accepted or rejected.

Do not implement grouped proposal transactions or partial acceptance semantics in v1.

## 11.2 Operations

Proposal operations should eventually distinguish actions such as:

```text
create
update
supersede
```

Acceptance of an `update` must verify the expected current object version and produce exactly the next version.

## 11.3 Effects of acceptance

Acceptance may:

* create new authoritative state;
* create a new version of existing state;
* supersede previous state;
* invalidate dependent task context.

Rejected proposals remain inspectable as history but do not become authoritative state.

---

# 12. Dependency invalidation and staleness

SMCC must detect when accepted state changes affect downstream tasks.

Example:

```text
Decision A changes
        ↓
Task B depends on Decision A
        ↓
Task B context is stale
        ↓
downstream state may also require invalidation
```

## 12.1 Staleness definition

A compiled context is stale when any recorded input version or accepted dependency result no longer matches the currently authoritative input.

The system should be able to identify **which** changed input caused staleness.

Do not use inferred semantic relevance for invalidation in v1.

## 12.2 Scope of invalidation

The design supports:

* dependency-aware invalidation;
* stale-context detection;
* selective recompilation;
* explicit supersession.

Do not blindly invalidate or rebuild the entire project when dependency information permits a narrower response.

---

# 13. Validation

`smcc validate` is part of the early vertical slice.

It validates properties that can be established from current repository state, including:

* Pydantic schema validity;
* unique object IDs;
* valid object types;
* valid status values;
* resolvable references;
* resolvable task dependencies;
* DAG acyclicity;
* valid context provenance structure.

State-transition code, rather than snapshot validation, is responsible for enforcing version increments during accepted updates.

---

# 14. Git integration

Git integration is **Level 1: provenance**, not state-machine coupling.

SMCC may record information such as:

```yaml
base_commit:
resulting_commit:
changed_files:
diff_reference:
```

or represent a commit as an artifact.

Git answers:

> What changed in the repository?

SMCC answers:

> What does the project currently consider authoritative, why, and through what reviewed state transition?

These are related but distinct.

A Git commit does not imply that an SMCC task or state transition has been accepted.

An accepted SMCC state transition may also occur without a code commit.

Do not make Git commits the transactional mechanism for SMCC state.

---

# 15. Core service boundary

SMCC semantics should live behind an application/service layer rather than inside the CLI or editor integration.

Conceptually, operations may eventually resemble:

```python
project.get_goal()
task.get("TASK-003")
context.compile("TASK-003")
result.submit(...)
proposal.accept(...)
proposal.reject(...)
```

These names are illustrative.

The important rule is:

> CLI, VS Code integration, MCP, and local-model adapters call the SMCC core rather than implementing their own SMCC semantics.

---

# 16. Initial interface sequence

Implementation order:

```text
core Python library
        ↓
minimal CLI
        ↓
early VS Code / GitHub Copilot integration
        ↓
future MCP and local-model adapters
```

"CLI first" is an implementation sequencing decision.

It does **not** mean VS Code integration is a distant feature.

A usable VS Code / GitHub Copilot workflow is an early project requirement.

---

# 17. First vertical slice

The first complete workflow is:

```text
hand-author bootstrap state (schema fixture)
        ↓
define project goal
        ↓
create two or three DAG tasks
        ↓
compile context for one task
        ↓
run coding agent
        ↓
return structured result
        ↓
propose state change
        ↓
human accepts or rejects
        ↓
invalidate / recompile dependent context
```

`smcc validate` is in scope for this slice (§13).

This vertical slice should drive implementation priorities.

Infrastructure that does not contribute to this path should generally be deferred.

---

# 18. Definition of success for the first prototype

The first prototype succeeds when:

1. a project has explicit authoritative state;
2. tasks are represented in a dependency graph;
3. a task receives a deterministic compiled context package;
4. a coding agent can perform work using that package;
5. its output can be represented as a structured result;
6. proposed state changes do not automatically become authoritative;
7. a human can accept or reject proposed changes;
8. accepted changes update authoritative state versions;
9. dependent task contexts are marked stale or recompiled;
10. the lifecycle is inspectable in the repository.

---

# 19. Explicitly deferred work

Do not implement these merely because they may eventually be useful:

* multi-agent orchestration;
* autonomous planning;
* sophisticated model routing;
* remote service architecture;
* vector databases;
* elaborate policy engines;
* production MCP integration;
* full UI;
* database-backed state;
* generalized distributed execution;
* sophisticated migration infrastructure;
* automatic context-relevance inference (embeddings, tag matching, LLM selection);
* grouped proposal transactions and partial acceptance;
* collision-free distributed ID allocation.

Build the complete state lifecycle first.

---

# 20. Initial engineering priorities

During the initial high-capability-model implementation window, prioritize correctness of the architectural foundations:

```text
state model and schema boundaries
        ↓
core service boundaries
        ↓
file-backed persistence semantics
        ↓
task DAG semantics
        ↓
context compilation semantics
        ↓
result and proposal semantics
        ↓
state-transition semantics
        ↓
dependency invalidation
```

Once these contracts are sound, implementation plumbing can be performed by less expensive coding models without giving those models freedom to redefine the architecture.

---

# 21. Design stance

SMCC is not intended to maximize agent autonomy.

Optimize for:

```text
state coherence
inspectability
controlled authority
efficient context
reliable task completion
human supervision
portable execution
```

A useful SMCC system should make a capable coding model more effective because it receives better-structured state, not because the model is allowed to operate with less supervision.

The north-star efficiency measure is closer to:

> useful accepted task completion per unit of inference

than to raw tokens per second or maximum agent activity.
