# RepoLine

RepoLine is a voice interface for local coding agents. Its public product surface is for provider paths that can inspect or change the active repo through the user's local machine.

## Language

**Coding Agent Path**:
A RepoLine provider path whose assistant has local repo access in the active workdir.
_Avoid_: Fast voice path, generic model path

**Non-Coding Transport**:
A provider path that can converse but does not have local repo access in the active workdir.
_Avoid_: Coding agent, supported onboarding path

**Internal Baseline**:
A non-public comparison path kept only to measure latency or interaction tradeoffs against a real coding agent path.
_Avoid_: Supported provider, onboarding option

**Public Scorecard**:
A benchmark report or support matrix that makes product-facing claims about RepoLine.
_Avoid_: Internal comparison sheet, all-provider matrix

**Validated Support**:
A public support claim backed by recent checked-in evidence and an explicit tested date.
_Avoid_: Implemented in code, theoretically supported

**Stale Support**:
A public support state for a coding agent path that remains an intended compatibility target but lacks recent checked-in validation evidence.
_Avoid_: Recommended, currently validated

**Hard Cutover**:
An immediate product-surface change with no transitional public wording, mixed support matrix, or shared scorecard during the migration.
_Avoid_: Soft migration, temporary mixed mode

**Deleted Transport**:
A provider path removed from both the public product surface and the codebase because it violates the repo's product boundary.
_Avoid_: Internal baseline, hidden fallback

**Spoken Response Latency**:
The elapsed time from the finalized user transcript to the first spoken chunk the caller hears.
_Avoid_: First response

**Assistant Delta Latency**:
The elapsed time from the finalized user transcript to the first assistant text delta emitted by the provider.
_Avoid_: User-facing response time

**Agent-Owned First Response**:
The first useful spoken reply must come from the coding agent itself rather than from RepoLine as a separate fast-ack layer.
_Avoid_: Orchestrator-owned fast ack, bridge-owned first reply

**Planning-First Session**:
A RepoLine interaction mode where thoughtful coding or planning quality matters more than sub-second conversational responsiveness.
_Avoid_: Realtime assistant, interrupt-driven chat

**Acceptable First Reply Window**:
The response window RepoLine can tolerate before the first spoken chunk without it being considered a product failure for the current mode.
_Avoid_: Must feel instant

**Read-Only Planning Eval**:
An easier first evaluation slice centered on planning tasks such as repo summary, explanation, root-cause hypothesis, patch planning, and verification guidance, chosen for tractability rather than as a permanent product boundary.
_Avoid_: Permanent scope limit, mutation ban

**Evaluation Harness**:
The measurement and reporting system used both to understand how RepoLine behaves and to improve it over time.
_Avoid_: Public scorecard only, benchmark theater

**Diagnostic Turn Record**:
A richer per-turn evaluation artifact that can include timings, transcript, tool events, artifacts, and other debugging context beyond what belongs in a public scorecard.
_Avoid_: Public summary row, final published metric

**Normalized Turn Schema**:
A single canonical evaluation record shape that both public scorecards and deeper diagnostic tools read from.
_Avoid_: One-off report format, temporary adapter-specific schema

**Diagnostic-First Delivery**:
An implementation order where the harness must first work as an internal understanding tool before time is spent polishing a public scorecard.
_Avoid_: Scorecard-first rollout, benchmark theater

**Coding-Agent Comparison Harness**:
A controlled evaluation runner for comparing coding agents on timing behavior and prompt-shape effects in this repo.
_Avoid_: Telephony benchmark, voice quality harness

**Scenario Runner Primary**:
A harness design where scripted scenarios against coding agents are the main source of comparison data, and real call telemetry is secondary.
_Avoid_: Telemetry-first harness

**Prompt Variant**:
A named prompt or system-shaping strategy that is intentionally compared as part of the harness rather than treated as incidental setup.
_Avoid_: Hidden prompt tweak, ad hoc wording

**Latency Archetype**:
A class of task chosen for how it stresses timing behavior, such as trivial answer, repo lookup, planning question, or light investigation.
_Avoid_: Product feature checklist, arbitrary prompt list

**Fixed Prompt Set**:
A small stable set of prompts that is rerun over time so latency changes remain attributable.
_Avoid_: Fast-growing corpus, shifting benchmark target

**Harness Row Key**:
The canonical identity of one comparison row: provider path, model, prompt variant, latency archetype, prompt id, and session state.
_Avoid_: Provider-only row, ambiguous benchmark row

**Session State**:
Whether a turn is measured on a fresh session or a resumed warm session.
_Avoid_: Hidden benchmark condition, mixed average

**Breaking Schema Cutover**:
An immediate replacement of the old evaluation schema with the normalized one, with no backward-compatibility layer for legacy benchmark artifacts or reports.
_Avoid_: Compatibility shim, dual schema period

**End-to-End Voice Latency**:
Latency measured from the end of the user's speech/finalized transcript boundary to the first spoken chunk.
_Avoid_: Provider-only latency

**Provider Latency**:
Latency measured from when RepoLine starts the provider turn to provider milestones such as first assistant delta, first spoken chunk, and completion.
_Avoid_: Full voice path latency

**First Wait Signal**:
The earliest explicit indication that the system is working, including thinking sound, status, or spoken acknowledgment.
_Avoid_: Spoken response

**Unexplained Silence**:
The elapsed time before any explicit wait signal is given to the caller.
_Avoid_: Normal thinking time

**Bridge-Constant Latency**:
Latency that is mostly the same across providers because it is owned by RepoLine itself, such as transcript finalization and bridge-level wait cues.
_Avoid_: Provider comparison metric

**Provider-Dependent Latency**:
Latency that varies meaningfully by provider path, such as session startup, first assistant delta, first spoken chunk, and completion time.
_Avoid_: Fixed bridge overhead

## Relationships

- Every public **Onboarding Path** must be a **Coding Agent Path**
- A **Non-Coding Transport** may exist only as an **Internal Baseline**, not as a public **Onboarding Path**
- Every **Public Scorecard** must include only **Coding Agent Paths**
- Public support claims require **Validated Support**
- **Validated Support** expires after 90 days without refreshed checked-in evidence, after which the path becomes **Stale Support**
- A coding agent path may remain in the public matrix as **Stale Support** when it is still intended but not recently revalidated
- A **Hard Cutover** removes conflicting public claims immediately instead of carrying a transition period
- A **Deleted Transport** is removed from docs, support claims, benchmark plans, and code
- A **Deleted Transport** also disappears from checked-in current-tree artifacts; git history is the archive
- `Gemini CLI` remains a **Coding Agent Path**
- Internal benchmark/reporting schema should use **Spoken Response Latency** explicitly instead of an overloaded `first_response` field
- The first useful spoken reply is an **Agent-Owned First Response**
- RepoLine is currently a **Planning-First Session**
- The current **Acceptable First Reply Window** is about 10 seconds for thinking/planning turns
- The first shipped evaluation scope is a **Read-Only Planning Eval**
- The **Evaluation Harness** exists for understanding and improving the system, not only for publishing comparisons
- The **Evaluation Harness** should keep a **Diagnostic Turn Record** that is deeper than the public scorecard
- The **Evaluation Harness** should emit a **Normalized Turn Schema** as the canonical source for both public and diagnostic reporting
- The schema change is a **Breaking Schema Cutover**
- The same **Normalized Turn Schema** should carry both **End-to-End Voice Latency** and **Provider Latency**
- The current rollout is a **Diagnostic-First Delivery**
- The first harness is a **Coding-Agent Comparison Harness**
- The first harness design is **Scenario Runner Primary**
- **Prompt Variant** is a first-class comparison dimension in the harness
- The first task set should be organized by **Latency Archetype**
- Each latency archetype should start with a **Fixed Prompt Set**
- The canonical row identity is the **Harness Row Key**
- **Session State** is a first-class comparison dimension and must not be averaged away
- The public scorecard headline should use **End-to-End Voice Latency**
- **Provider Latency** belongs in diagnostic drilldowns, not as the primary public headline
- The harness should track **First Wait Signal**, **Spoken Response Latency**, and **Unexplained Silence** separately
- **First Wait Signal** is mainly useful for UX diagnostics, not provider comparison, because it is largely **Bridge-Constant Latency**
- Provider scorecards should focus on **Provider-Dependent Latency**
- The early harness priority is timing understanding and prompt engineering, not rich answer-quality grading
- **Assistant Delta Latency** is diagnostic telemetry that may explain **Spoken Response Latency**

## Example dialogue

> **Dev:** "Gemini API is fast, so should we recommend it as an onboarding path?"
> **Domain expert:** "No. If it cannot inspect the repo through the local coding runtime, it is not a **Coding Agent Path** and does not belong in the public support matrix."

## Flagged ambiguities

- "first response" was being used to mean both **Spoken Response Latency** and **Assistant Delta Latency** — resolved: use **Spoken Response Latency** as the user-facing latency metric and **Assistant Delta Latency** only for diagnostics.
- "supported provider" was being used to mean both public product path and internal experiment — resolved: only **Coding Agent Paths** belong in public onboarding and support claims.
- "keep it in the repo" was being used to mean both public support and internal comparison — resolved: a **Non-Coding Transport** may remain only as an **Internal Baseline**.
- "benchmark matrix" was being used to mean both product-facing proof and internal experimentation — resolved: a **Public Scorecard** includes only **Coding Agent Paths**.
- "migration" was being used to mean both staged cleanup and immediate boundary enforcement — resolved: this change is a **Hard Cutover**.
- "Gemini API" was being treated as a possible internal exception — resolved: in this repo it is a **Deleted Transport**, not an **Internal Baseline**.
- "Gemini" was being used to mean both the CLI coding path and the non-coding API transport — resolved: `Gemini CLI` stays, `Gemini API` is a **Deleted Transport**.
- "first_response" was being used as an internal fallback field name — resolved: rename the schema now so **Spoken Response Latency** is explicit in code and reports.
- "supported" was being used to mean both code presence and real product readiness — resolved: public support requires **Validated Support** with checked-in evidence and a tested date.
- "supported but not revalidated" was being described informally — resolved: keep those paths in the matrix as **Stale Support**. `Claude Code` currently falls into that bucket.
- "delete it" was ambiguous between stopping new references and removing existing artifacts — resolved: a **Deleted Transport** is removed from the current tree entirely, with git history serving as the archive.
- "recently validated" was undefined — resolved: **Validated Support** has a 90-day freshness window.
- "fast acknowledgment" was ambiguous about who owns it — resolved: the first reply should be an **Agent-Owned First Response**, not a RepoLine-generated fast ack.
- "latency priority" was shifting between instant reply and thoughtful planning — resolved: RepoLine is currently a **Planning-First Session**, and the **Acceptable First Reply Window** is roughly 10 seconds for those turns.
- "first eval scope" was ambiguous between planning work and code edits — resolved: the initial slice is a **Read-Only Planning Eval** because it is easier, not because mutation is out of scope forever.
- "eval harness" was being treated as just a public benchmark — resolved: the **Evaluation Harness** is also an internal understanding and improvement tool.
- "eval artifact" was being treated as one thing — resolved: keep a simple public scorecard plus a richer **Diagnostic Turn Record** for investigation and improvement.
- "harness output" could have split into quick patches and multiple shapes — resolved: use one **Normalized Turn Schema** for both public and diagnostic consumers.
- "schema migration" could have kept the old latency fields alive — resolved: do a **Breaking Schema Cutover** with no backward-compat layer.
- "two clocks" sounded like two separate systems — resolved: keep one harness and one schema, but record both **End-to-End Voice Latency** and **Provider Latency**.
- "which clock is public" was unclear — resolved: the public headline uses **End-to-End Voice Latency**, while **Provider Latency** is for drilldown and diagnosis.
- "public scorecard" was starting to drive early design — resolved: this is a **Diagnostic-First Delivery**, so the first requirement is an actually useful harness, not a polished public artifact.
- "first harness" was drifting toward phone telemetry and voice quality — resolved: the first cut is a **Coding-Agent Comparison Harness** with **Scenario Runner Primary**.
- "prompt engineering" could have remained outside the harness design — resolved: **Prompt Variant** is a first-class comparison dimension.
- "task set" could have drifted into a vague feature grab-bag — resolved: organize the first harness by **Latency Archetype**.
- "prompt coverage" could have expanded too early — resolved: begin with a **Fixed Prompt Set** so changes stay attributable.
- "benchmark row" could have collapsed too much context — resolved: each row is identified by the **Harness Row Key**.
- "warm versus fresh" could have been folded into one number — resolved: **Session State** is a first-class dimension in the **Harness Row Key**.
- "waiting" was being treated as one metric — resolved: distinguish **First Wait Signal**, **Spoken Response Latency**, and **Unexplained Silence**.
- "first wait signal" was drifting into the provider harness — resolved: it is mostly **Bridge-Constant Latency** and should not drive provider comparisons.
