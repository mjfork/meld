---
name: meld-v1
description: Multi-model planning convergence CLI that synthesizes plans from multiple provider CLIs into a unified approach (defaults: Claude, Gemini, OpenAI)
status: backlog
created: 2026-01-16T00:52:34Z
updated: 2026-01-15T22:30:00Z
---

# PRD: meld-v1

## Executive Summary

Meld is a command-line tool that converges planning across multiple frontier AI models. Given a task description, Meld generates an initial plan using the "melder" (Claude), then solicits feedback from AI "advisors" (Claude CLI, Gemini CLI, OpenAI CLI) in parallel via a provider-adapter layer. The Melder synthesizes all feedback, updates the plan, and iterates until convergence — when no substantive changes remain — or a maximum iteration count is reached.

The result is a rigorously reviewed plan that incorporates diverse AI perspectives, reducing blind spots and improving plan quality through adversarial collaboration.

**Value Proposition:** Developers get better plans by leveraging the collective intelligence of multiple frontier models, each with different training data, reasoning styles, and blind spots.

## Problem Statement

### The Problem
When developers use AI to plan complex tasks, they're limited to a single model's perspective. Each AI model has:
- Different training data and knowledge cutoffs
- Unique reasoning patterns and biases
- Varying strengths (code architecture vs. edge cases vs. documentation)
- Blind spots the user may not recognize

Asking multiple models manually is tedious: copy-paste between interfaces, mentally track differences, manually synthesize feedback.

### Why Now
- Multiple high-quality frontier models now have official CLIs (Claude, Gemini, ChatGPT)
- Token costs have dropped, making multi-model workflows economically viable
- Developers increasingly use AI for planning, not just code generation
- No existing tool automates multi-model plan convergence

## User Stories

### Primary Persona: Developer Planning a Feature

**As a developer**, I want to get a plan reviewed by multiple AI models so that I catch issues before implementation.

**Acceptance Criteria:**
- I can run a single command with my task description
- I see real-time feedback from all three models in a TUI
- I get a final markdown plan that incorporates the best insights
- The process completes within 5-10 minutes for typical tasks

### Story 1: Quick Planning Session
**As a developer starting a new feature**, I want to quickly generate a solid implementation plan so that I don't waste time on a flawed approach.

**Flow:**
1. Run `meld "Add user authentication with OAuth2 support"`
2. Watch the TUI show Melder creating initial plan
3. See three advisors provide feedback simultaneously
4. Watch Melder incorporate feedback and iterate
5. Receive final converged plan as markdown

**Acceptance Criteria:**
- Total time under 10 minutes for typical features
- Plan includes architecture, steps, and considerations
- Divergent opinions from advisors are reconciled, not ignored

### Story 2: Complex System Design
**As a developer designing a distributed system**, I want thorough multi-perspective review so that I catch scalability and reliability issues early.

**Flow:**
1. Run `meld --rounds 7 "Design event-driven order processing system"`
2. Specify more rounds for deeper iteration
3. Review the extensive feedback cycles
4. Get a comprehensive plan addressing multiple concerns

**Acceptance Criteria:**
- Can configure iteration count via `--rounds` flag
- Complex tasks benefit from additional iterations
- Final plan addresses concerns raised by all advisors

### Story 3: Debugging a Planning Failure
**As a developer whose meld failed**, I want to understand what went wrong so that I can retry or adjust.

**Flow:**
1. Run meld, one advisor times out
2. See clear indication in TUI which advisor failed
3. Meld retries once, then continues without that advisor
4. Final plan notes which advisors contributed

**Acceptance Criteria:**
- Clear error indication in TUI
- Automatic retry before giving up on an advisor
- Graceful degradation (2 advisors still produces useful output)
- Final output indicates which advisors participated
- `meld doctor` provides actionable diagnostics for missing CLIs and auth failures

## Requirements

### Functional Requirements

#### FR1: Task Input
- Accept natural language task description as CLI argument
- Support multi-line input via stdin or file (`meld --file task.txt`)
- Optional: accept a PRD/requirements file for additional context (`meld --prd prd.md`)
- Validate input is non-empty and reasonable length

#### FR2: Initial Plan Generation (Melder)
- Use Claude CLI to generate structured initial plan
- Plan should include: overview, steps, considerations, risks
- Melder prompt should be optimized for actionable plans

#### FR3: Advisor Feedback Collection
- Invoke advisor CLIs in parallel via provider-adapter layer (default: `claude`, `gemini`, `openai`)
- Each advisor receives: original task + current plan (+ PRD context if provided)
- Each advisor provides: structured feedback (improvements, concerns, additions, rationale)
- Timeout per advisor: 600 seconds (configurable)
- Error handling must classify failures:
  - TIMEOUT: retry once
  - RATE_LIMIT / NETWORK: retry with exponential backoff (max 3 attempts)
  - AUTH_FAILED / CLI_NOT_FOUND / PARSE_ERROR: fail fast for that provider (no retry)
- After retries exhausted: continue with remaining advisors and record failures in output metadata

#### FR4: Feedback Synthesis (Melder)
- Melder receives all advisor feedback
- Melder decides what to incorporate, what to reject, and why
- Melder produces updated plan
- Melder indicates if convergence reached (no substantive changes)

#### FR5: Iteration Loop
- Default: 5 rounds maximum
- Configurable via `--rounds N` flag
- Early termination on convergence
- Each round: collect feedback → synthesize → update plan

#### FR6: TUI Display
- Four-panel layout using Textual (Rich-based rendering)
- Top panel: Melder (full width)
- Bottom three panels: Claude advisor, Gemini advisor, OpenAI advisor (each 1/3 width)
- Real-time streaming output as each component runs
- Clear visual indication of current phase (planning, feedback, synthesis)
- Status indicators for each advisor (running, complete, failed, retrying)
- Event-driven updates (TUI subscribes to orchestrator events)
- Throttled rendering to prevent flicker and excessive CPU usage
- Provide a compact "Plan Delta" indicator per round (summary of what changed)

#### FR7: Output Generation
- Final plan output as markdown document
- Default: print to stdout
- Optional: write to file via `--output plan.md`
- Optional: emit machine-readable JSON summary for CI/scripting (`--json-output result.json`)
- Include metadata: advisors that participated, rounds completed, convergence status

#### FR8: Configuration
- `--rounds N`: max iteration rounds (default: 5)
- `--output FILE`: write plan to file instead of stdout
- `--json-output FILE`: write machine-readable JSON summary
- `--file FILE`: read task from file instead of argument
- `--prd FILE`: include requirements context in prompts
- `--quiet`: minimal output, no TUI (for scripting)
- `--verbose`: include raw advisor outputs in final document
- `--run-dir DIR`: root directory for run artifacts (default: `.meld/runs/`)
- `--resume RUN_ID`: resume an interrupted run from the last checkpoint
- `--no-save`: do not write run artifacts to disk (disables resume)
- `--skip-preflight`: skip environment validation (advanced users / CI)

#### FR9: Session Persistence & Resume
- Create a run directory per invocation (default: `.meld/runs/<run_id>/`)
- Persist artifacts incrementally after each round:
  - Task input and PRD context (if provided)
  - Plan snapshots after each synthesis
  - Advisor feedback per round
  - Run summary with timing and status
- Support `--resume <run_id>` to continue from the last completed round after interruption
- On completion, write `final-plan.md` into the run directory (even if stdout is used)

#### FR10: Preflight & Diagnostics
- Before running (unless `--skip-preflight`), validate:
  - Required CLIs exist on PATH (for configured providers)
  - Authentication appears valid (provider-specific lightweight check)
  - Provider adapter can invoke the CLI in non-interactive mode
- Provide a `meld doctor` command that:
  - Runs all preflight checks
  - Prints suggested fixes for any failures
  - Lists detected provider CLIs with versions

### Non-Functional Requirements

#### NFR1: Reliability
- Graceful handling of CLI failures (classified retries + continue with remaining advisors)
- No data loss if process interrupted (crash-safe artifacts written each round; resumable run)
- Clear error messages for common failures (CLI not found, auth issues)
- Explicit error taxonomy with user-actionable messages (install/auth/fix flags)

#### NFR2: Usability
- Zero configuration for users with pre-configured CLIs
- Intuitive TUI that doesn't require documentation to understand
- Helpful error messages that suggest fixes

#### NFR3: Maintainability
- Clean separation: orchestration, provider adapters, TUI, output formatting
- Internal provider-adapter architecture isolates CLI quirks from core orchestration
- Easy to add new providers (new CLI tools)
- Prompt templates externalized for tuning
- Include mock provider implementations for deterministic CI testing

#### NFR4: Security & Privacy
- Default to provider read-only / sandbox modes where supported
- Persisted artifacts redact common secret patterns (API keys, tokens) by default
- Provide `--no-save` flag to disable writing artifacts for sensitive tasks
- Clearly document where run artifacts are stored (`.meld/runs/`) and recommend gitignoring

## Success Criteria

### Quantitative Metrics
- **Convergence rate:** >80% of tasks converge within 5 rounds
- **Voice success rate:** >95% of advisor invocations complete without timeout

### Qualitative Metrics
- Users report plans are "more thorough" than single-model plans
- Users discover issues they wouldn't have caught alone
- TUI is described as "intuitive" and "informative"

### Prototype Success Criteria
- Successfully orchestrates all three CLIs
- TUI displays real-time output from all four panels
- Completes 5-round iteration on sample task
- Produces coherent merged markdown plan

## Constraints & Assumptions

### Assumptions
- Users have at least one of `claude`, `gemini`, `openai` CLIs installed and configured
- CLIs are authenticated and ready to use (API keys configured)
- Users have sufficient API credits/quota for multiple model calls
- Network connectivity to AI providers
- For optimal multi-perspective feedback, all three CLIs should be available (graceful degradation with fewer)

### Constraints
- **Python 3.10+** required (for modern async and type hints)
- **No API key management** - relies on pre-configured CLIs
- **Ships with three built-in providers** (Claude, Gemini, OpenAI) by default; internal adapter architecture supports additional providers without changes to core orchestration. User-configurable advisor selection is v1.1.
- **CLI-based only** - no web interface, no API server

### Technical Constraints
- Rich + Textual for TUI (Python ecosystem)
- Subprocess-based CLI invocation (not direct API calls)
- Local execution only (no cloud deployment for v1)

## Out of Scope (v1)

The following are explicitly **NOT** included in v1:

- **Custom advisor configuration** - v1 ships with Claude, Gemini, OpenAI; user selection is v1.1
- **Direct API integration** - uses CLIs, not API libraries
- **Plan history/versioning** - each run is independent
- **Web interface** - CLI only
- **Plan templates** - freeform output only (but PRD/requirements context injection is supported via `--prd`)
- **Cost tracking** - no token counting or cost estimation
- **Offline mode** - requires network access
- **Plugin system** - no third-party extensibility architecture
- **Plan execution** - outputs plan only, doesn't run it
- **Automatic context/codebase awareness** - no automatic repo analysis (explicit `--prd` context is supported)

## Dependencies

### External Dependencies
- `claude` CLI - Anthropic's official Claude CLI tool
- `gemini` CLI - Google's official Gemini CLI tool
- `openai` CLI - OpenAI's official CLI tool (or `chatgpt` depending on available tooling)
- Python 3.10+
- Rich library (terminal formatting)
- Textual library (TUI framework)

### No Internal Dependencies
This is a standalone tool with no dependencies on other internal systems.

### TUI Layout (Textual)
```
┌─────────────────────────────────────────┐
│              MELDER (Claude)            │
│  [Status: Synthesizing round 2/5...]    │
│  Current plan: ...                      │
├─────────────┬─────────────┬─────────────┤
│   CLAUDE    │   GEMINI    │   OPENAI    │
│   [Voice]   │   [Voice]   │   [Voice]   │
│             │             │             │
│  Feedback:  │  Feedback:  │  Feedback:  │
│  ...        │  ...        │  ...        │
└─────────────┴─────────────┴─────────────┘
```

### Convergence Detection

Use a hybrid approach to reduce false convergence:

**Primary signal:** Melder must output a structured "Convergence Assessment" section with:
- STATUS: CONVERGED | CONTINUING
- CHANGES_MADE: integer (substantive changes this round)
- OPEN_ITEMS: integer (unresolved concerns / questions)

**Secondary validation:** Compute a normalized diff ratio between the previous plan and current plan.
- If OPEN_ITEMS > 0: never converge
- If STATUS=CONVERGED but diff ratio is large: treat as CONTINUING

**Oscillation guard:** If the plan cycles across recent rounds (e.g., A→B→A), stop early and output:
"NEEDS HUMAN DECISION" with the unresolved tradeoffs and the competing options.

This multi-signal approach prevents false positives from models overclaiming completion.

## Open Questions

1. **Advisor prompt tuning:** What prompt structure yields the most useful feedback?

These will be resolved during prototyping.

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-16 | 0.1 | Initial PRD draft |
| 2026-01-15 | 0.2 | Added FR9 (session persistence), FR10 (preflight/doctor), NFR4 (security); upgraded convergence detection to hybrid approach; added error taxonomy; added `--prd`, `--json-output`, `--resume` flags; internal provider-adapter architecture |
