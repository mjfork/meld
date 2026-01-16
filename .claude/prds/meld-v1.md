---
name: meld-v1
description: Multi-model planning convergence CLI that synthesizes plans from Claude, Gemini, and ChatGPT into a unified approach
status: backlog
created: 2026-01-16T00:52:34Z
---

# PRD: meld-v1

## Executive Summary

Meld is a command-line tool that converges planning across multiple frontier AI models. Given a task description, Meld generates an initial plan using Claude (the "Melder"), then solicits feedback from three AI "voices" (Claude CLI, Gemini CLI, ChatGPT CLI) in parallel. The Melder synthesizes all feedback, updates the plan, and iterates until convergence—when no substantive changes remain—or a maximum iteration count is reached.

The result is a battle-tested plan that incorporates diverse AI perspectives, reducing blind spots and improving plan quality through adversarial collaboration.

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
3. See three voices provide feedback simultaneously
4. Watch Melder incorporate feedback and iterate
5. Receive final converged plan as markdown

**Acceptance Criteria:**
- Total time under 10 minutes for typical features
- Plan includes architecture, steps, and considerations
- Divergent opinions from voices are reconciled, not ignored

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
- Final plan addresses concerns raised by all voices

### Story 3: Debugging a Planning Failure
**As a developer whose meld failed**, I want to understand what went wrong so that I can retry or adjust.

**Flow:**
1. Run meld, one voice times out
2. See clear indication in TUI which voice failed
3. Meld retries once, then continues without that voice
4. Final plan notes which voices contributed

**Acceptance Criteria:**
- Clear error indication in TUI
- Automatic retry before giving up on a voice
- Graceful degradation (2 voices still produces useful output)
- Final output indicates which voices participated

## Requirements

### Functional Requirements

#### FR1: Task Input
- Accept natural language task description as CLI argument
- Support multi-line input via stdin or file (`meld --file task.txt`)
- Validate input is non-empty and reasonable length

#### FR2: Initial Plan Generation (Melder)
- Use Claude CLI to generate structured initial plan
- Plan should include: overview, steps, considerations, risks
- Melder prompt should be optimized for actionable plans

#### FR3: Voice Feedback Collection
- Invoke three CLI tools in parallel: `claude`, `gemini`, `chatgpt`
- Each voice receives: original task + current plan
- Each voice provides: structured feedback (improvements, concerns, additions)
- Timeout per voice: 120 seconds (configurable)
- On timeout: retry once, then proceed without that voice

#### FR4: Feedback Synthesis (Melder)
- Melder receives all voice feedback
- Melder decides what to incorporate, what to reject, and why
- Melder produces updated plan
- Melder indicates if convergence reached (no substantive changes)

#### FR5: Iteration Loop
- Default: 5 rounds maximum
- Configurable via `--rounds N` flag
- Early termination on convergence
- Each round: collect feedback → synthesize → update plan

#### FR6: TUI Display
- Four-panel layout using Rich + Textual
- Top panel: Melder (full width)
- Bottom three panels: Claude voice, Gemini voice, ChatGPT voice (each 1/3 width)
- Real-time streaming output as each component runs
- Clear visual indication of current phase (planning, feedback, synthesis)
- Status indicators for each voice (running, complete, failed, retrying)

#### FR7: Output Generation
- Final plan output as markdown document
- Default: print to stdout
- Optional: write to file via `--output plan.md`
- Include metadata: voices that participated, rounds completed, convergence status

#### FR8: Configuration
- `--rounds N`: max iteration rounds (default: 5)
- `--output FILE`: write plan to file instead of stdout
- `--file FILE`: read task from file instead of argument
- `--quiet`: minimal output, no TUI (for scripting)
- `--verbose`: include raw voice outputs in final document

### Non-Functional Requirements

#### NFR1: Performance
- Initial plan generation: < 30 seconds
- Each feedback round: < 60 seconds (parallel voice calls)
- Total time for 5 rounds: < 5 minutes typical
- Timeout handling prevents infinite hangs

#### NFR2: Reliability
- Graceful handling of CLI failures (retry + continue)
- No data loss if process interrupted (partial results logged)
- Clear error messages for common failures (CLI not found, auth issues)

#### NFR3: Usability
- Zero configuration for users with pre-configured CLIs
- Intuitive TUI that doesn't require documentation to understand
- Helpful error messages that suggest fixes

#### NFR4: Maintainability
- Clean separation: orchestration, voice adapters, TUI, output formatting
- Easy to add new voices (new CLI tools)
- Prompt templates externalized for tuning

## Success Criteria

### Quantitative Metrics
- **Convergence rate:** >80% of tasks converge within 5 rounds
- **Voice success rate:** >95% of voice invocations complete without timeout
- **User task completion:** Users can run meld end-to-end in <10 minutes

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
- Users have `claude`, `gemini`, and `chatgpt` CLIs installed and configured
- CLIs are authenticated and ready to use (API keys configured)
- Users have sufficient API credits/quota for multiple model calls
- Network connectivity to all three AI providers

### Constraints
- **Python 3.10+** required (for modern async and type hints)
- **No API key management** - relies on pre-configured CLIs
- **Three specific voices** for v1 - no pluggable voice system yet
- **CLI-based only** - no web interface, no API server

### Technical Constraints
- Rich + Textual for TUI (Python ecosystem)
- Subprocess-based CLI invocation (not direct API calls)
- Local execution only (no cloud deployment for v1)

## Out of Scope (v1)

The following are explicitly **NOT** included in v1:

- **Custom voice configuration** - hardcoded to Claude, Gemini, ChatGPT
- **Direct API integration** - uses CLIs, not API libraries
- **Plan history/versioning** - each run is independent
- **Web interface** - CLI only
- **Plan templates** - freeform output only
- **Cost tracking** - no token counting or cost estimation
- **Offline mode** - requires network access
- **Plugin system** - no extensibility architecture
- **Plan execution** - outputs plan only, doesn't run it
- **Context/codebase awareness** - takes only the task prompt, no repo analysis

## Dependencies

### External Dependencies
- `claude` CLI - Anthropic's official Claude CLI tool
- `gemini` CLI - Google's official Gemini CLI tool
- `chatgpt` CLI - OpenAI's official ChatGPT CLI tool
- Python 3.10+
- Rich library (terminal formatting)
- Textual library (TUI framework)

### Development Dependencies
- pytest for testing
- black/ruff for formatting
- mypy for type checking

### No Internal Dependencies
This is a standalone tool with no dependencies on other internal systems.

## Technical Notes

### CLI Invocation Pattern
Each voice CLI will be invoked via subprocess with prompt piped to stdin:
```python
process = await asyncio.create_subprocess_exec(
    "claude", "--prompt", "-",
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE
)
stdout, stderr = await asyncio.wait_for(
    process.communicate(input=prompt.encode()),
    timeout=120
)
```

### TUI Layout (Textual)
```
┌─────────────────────────────────────────┐
│              MELDER (Claude)            │
│  [Status: Synthesizing round 2/5...]    │
│  Current plan: ...                      │
├─────────────┬─────────────┬─────────────┤
│   CLAUDE    │   GEMINI    │   CHATGPT   │
│   [Voice]   │   [Voice]   │   [Voice]   │
│             │             │             │
│  Feedback:  │  Feedback:  │  Feedback:  │
│  ...        │  ...        │  ...        │
└─────────────┴─────────────┴─────────────┘
```

### Convergence Detection
The Melder will be prompted to explicitly state whether convergence is reached:
- "CONVERGED: No substantive changes needed"
- "CONTINUING: Incorporated N changes, M open items remain"

This structured output enables reliable convergence detection.

## Open Questions

1. **Voice prompt tuning:** What prompt structure yields the most useful feedback?
2. **Convergence threshold:** Should "cosmetic only" changes count as convergence?
3. **Partial voice failure:** With only 2 voices, is the output still valuable enough?
4. **Long tasks:** How to handle tasks that need more context than fits in a prompt?

These will be resolved during prototyping.

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-16 | 0.1 | Initial PRD draft |
