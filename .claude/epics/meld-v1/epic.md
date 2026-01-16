---
name: meld-v1
status: backlog
created: 2026-01-16T02:47:17Z
updated: 2026-01-16T04:22:00Z
progress: 0%
prd: .claude/prds/meld-v1.md
github: [Will be updated when synced to GitHub]
---

# Epic: meld-v1

## Overview

Meld is a Python CLI tool that orchestrates multi-model plan convergence. Given a task description, it uses Claude as the "Melder" to generate an initial plan, then collects parallel feedback from three AI advisors (Claude CLI, Gemini CLI, Codex CLI), synthesizes the feedback, and iterates until convergence or max rounds. The tool uses a Textual-based TUI to display real-time progress across all four panels.

**Key v1 design goals:**
- **Advisor adapter layer**: Encapsulate per-CLI quirks (flags, output parsing) so CLI drift doesn't break the core loop
- **Session persistence**: Crash-safe artifacts enable debugging, `--resume`, and meet PRD requirement "no data loss if interrupted"
- **Structured feedback**: Lightly structured advisor responses improve synthesis quality and convergence accuracy

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.10+ | Required for Textual/Rich; modern async support |
| TUI Framework | Textual | Purpose-built for terminal apps; handles layout, streaming, async natively |
| CLI Invocation | `asyncio.create_subprocess_exec` | Non-blocking parallel execution; stdout streaming |
| Process Management | Subprocess with timeout | CLIs are pre-authenticated; no API key handling needed |
| Output Format | Markdown + optional JSON | Markdown for humans, JSON for CI/scripting |
| Configuration | CLI flags only | No config files for v1; keeps it simple |
| Advisor Integration | Provider adapters | Encapsulates per-CLI flags/parsing; handles CLI drift; enables reliable preflight |
| Run Persistence | Session directory `.meld/runs/` | Crash-safe artifacts, debugging, enables `--resume` |
| Feedback Format | Lightly structured markdown | Preserves natural language while improving synthesis reliability |

## Technical Approach

### Core Components

1. **CLI Entry Point (`meld/cli.py`)**
   - Subcommands: `meld run` (default), `meld doctor`
   - Input modes: positional arg, `--file`, stdin (auto-detect when piped)
   - PRD input: `--prd <file>` (optional)
   - Run control: `--rounds`, `--timeout`, `--output`, `--quiet`, `--verbose`
   - Session: `--resume <run_id>`, `--run-dir`, `--json-output`
   - Preflight: `--skip-preflight`

2. **Preflight Validator (`meld/preflight.py`)**
   - Verify required CLIs exist (`which claude gemini codex`)
   - Test authentication with minimal API call
   - Report missing/broken components with install instructions
   - Powers both inline preflight and `meld doctor` subcommand

3. **Session Manager (`meld/session.py`)**
   - Creates unique run directory: `.meld/runs/<timestamp>-<id>/`
   - Writes artifacts incrementally after each round:
     - `task.md`, `prd.md` (if provided)
     - `plan.round<N>.md`, `advisor.<name>.round<N>.md`
     - `events.jsonl` (structured event log)
   - Supports `--resume <run_id>` to continue from last completed round

4. **Provider Adapters (`meld/providers/`)**
   - One adapter per provider: `claude.py`, `gemini.py`, `openai.py`
   - Encapsulates: command building, flags, environment normalization, output parsing
   - Consistent interface: `async run(prompt) -> AdvisorResult` + streamed events
   - Handles CLI quirks/drift without affecting core logic

5. **Orchestrator (`meld/orchestrator.py`)**
   - Main loop: plan → feedback → synthesize → check convergence
   - Manages iteration count and early termination
   - Coordinates between Melder, Advisors, and Session Manager
   - Writes checkpoints after each round

6. **Melder (`meld/melder.py`)**
   - Wraps Claude adapter for plan generation and synthesis
   - Two modes: initial plan generation, feedback synthesis
   - Streams output to TUI in real-time during generation
   - Outputs Decision Log (ACCEPTED/REJECTED/DEFERRED)
   - Detects convergence via structured JSON + diff validation

7. **Advisor Pool (`meld/advisors.py`)**
   - Parallel invocation via provider adapters
   - Timeout handling (configurable via `--timeout`, default 600s)
   - Streams output to TUI as it arrives
   - Graceful degradation (continues with 2 advisors if one fails)
   - Error categorization with smart retry logic

8. **TUI (`meld/tui.py`)**
   - Textual app with 4-panel layout
   - Top: Melder panel (full width) with real-time streaming
   - Bottom: Three advisor panels (1/3 width each)
   - Real-time streaming for all panels (Melder + advisors)
   - Status indicators with elapsed time per panel
   - Bottom status bar: session time, round number, activity indicator
   - Phase display (Planning → Feedback → Synthesis)

9. **Output Formatter (`meld/output.py`)**
   - Generates final markdown document with:
     - Final plan
     - Run report: round summaries, key deltas
     - Decision log (accepted/rejected/deferred suggestions)
     - Advisor participation + any failures
   - Optional `--json-output` for CI/scripting
   - Handles `--verbose` mode (includes raw advisor outputs)

10. **Signal Handler (`meld/signals.py`)**
    - Registers SIGINT/SIGTERM handlers for graceful shutdown
    - Maintains list of active subprocess PIDs
    - Graceful shutdown: signal processes, wait 5s, force kill if needed
    - Updates session status to `interrupted` before exit
    - Enables clean resume from last completed round

### Data Flow

```
Task Input (+ optional PRD) → Preflight checks → Create session
                                                      ↓
                                              Melder (initial plan)
                                                      ↓
                                              [Checkpoint: round 0]
                                                      ↓
                                               ┌──────┼──────┐
                                               ↓      ↓      ↓
                                            Claude  Gemini  Codex
                                            (parallel structured feedback)
                                               └──────┼──────┘
                                                      ↓
                                              Melder (synthesize + decision log)
                                                      ↓
                                              [Checkpoint: round N]
                                                      ↓
                                   OPEN_ITEMS > 0? → Yes → Continue
                                                      ↓ No
                                              Converged? → Yes → Output
                                                      ↓ No
                                              Max rounds? → Yes → Output
                                                      ↓ No
                                              Loop back to feedback
```

### Prompt Templates

Externalize prompts in `meld/prompts.py`:
- `MELDER_INITIAL_PLAN`: Generates structured plan from task
- `MELDER_SYNTHESIZE`: Incorporates feedback, detects convergence
- `ADVISOR_FEEDBACK`: Structured feedback request for each advisor

## Implementation Strategy

### Phase 1: Foundation
- Project scaffolding (pyproject.toml, directory structure)
- CLI with subcommands (`run`, `doctor`) and all input modes
- Session manager + artifact writing
- Provider adapter interface + Claude adapter
- Basic orchestrator loop (no TUI)

### Phase 2: Core Logic
- Gemini and OpenAI adapters
- Melder with Decision Log output
- Advisor pool with structured feedback parsing
- Convergence detection with OPEN_ITEMS check
- Error categorization and retry logic

### Phase 3: TUI
- Textual app with 4-panel layout
- Streaming output integration
- Status indicators (○/◐/●/✗/↻) and phase display
- Throttled updates to prevent flicker

### Phase 4: Polish
- Output formatter with run report + decision log
- JSON output for CI
- Resume from checkpoint
- Graceful degradation handling
- Quiet mode for scripting

## Task Breakdown Preview

- [ ] **Task 1: Project Setup** - Python project structure, CLI with subcommands, input modes (arg/file/stdin/--prd)
- [ ] **Task 2: Session Manager** - Run directory creation, artifact writing, checkpoint persistence, --resume support
- [ ] **Task 3: Provider Adapter Interface** - Base adapter class, async subprocess runner, streaming, timeout, error categorization
- [ ] **Task 4: Provider Adapters** - Claude, Gemini, OpenAI adapters with CLI-specific handling
- [ ] **Task 5: Preflight / Doctor** - CLI existence checks, auth validation, `meld doctor` subcommand
- [ ] **Task 6: Melder Implementation** - Plan generation, synthesis with Decision Log, convergence output
- [ ] **Task 7: Advisor Pool** - Parallel invocation, structured feedback parsing, graceful degradation
- [ ] **Task 8: Orchestrator** - Main loop, OPEN_ITEMS convergence check, checkpoint writes
- [ ] **Task 9: TUI Implementation** - Textual 4-panel layout, status indicators, throttled streaming
- [ ] **Task 10: Output Formatter** - Final markdown with run report, decision log, --json-output, --verbose

## Dependencies

### External (user must have installed)
- `claude` CLI - Anthropic's Claude Code CLI (authenticated)
- `gemini` CLI - Google's Gemini CLI (authenticated)
- `codex` CLI - OpenAI's Codex CLI (authenticated)
- Python 3.10+

### Python Packages
- `textual>=0.50.0` - TUI framework
- `rich>=13.0.0` - Terminal formatting (Textual dependency)

### No Internal Dependencies
Standalone tool with no internal system dependencies.

## Success Criteria (Technical)

| Criteria | Target |
|----------|--------|
| All CLIs invoked successfully | 100% when CLIs are available |
| Preflight detects missing/broken CLIs | Actionable error messages (no stack traces) |
| Parallel execution of advisors | <5s overhead vs sequential |
| TUI renders without flicker | Smooth streaming with throttled updates |
| Convergence detection accuracy | No false positives; OPEN_ITEMS > 0 always blocks |
| Graceful degradation | Works with 2/3 advisors |
| Session artifacts written | Crash recovery possible via --resume |
| Output is valid markdown | Renders correctly in any viewer |
| Run summary is inspectable | Round summaries + decision log included |
| CI-friendly output | JSON summary via --json-output |

## Estimated Effort

- **Total tasks:** 10
- **Complexity:** Medium-High - subprocess orchestration, TUI, persistence, adapters
- **Risk areas:**
  - CLI output format variations (mitigate with adapter layer)
  - Textual learning curve (mitigate with simple layout)
  - Session resume edge cases (mitigate with clear checkpointing)

## Deferred to v1.1

- Event-driven architecture (event bus for TUI/logging separation)
- Context size guardrails (--max-context-chars, PRD summarization)
- Semantic oscillation detection
- Advisor specialization hints (provider-specific focus areas via `--advisor-hints`)
- Cost tracking and token usage estimation

## CLI Invocation Specification

All advisors run in **read-only/plan mode** with **maximum reasoning** enabled.

### Claude CLI (Melder + Advisor)

```bash
claude -p "PROMPT" \
  --permission-mode plan \
  --model opus \
  --output-format text
```

| Flag | Purpose |
|------|---------|
| `-p "PROMPT"` | Non-interactive mode, returns text |
| `--permission-mode plan` | Read-only, proposes but doesn't execute changes |
| `--model opus` | Use Claude Opus (highest capability) |
| `--output-format text` | Plain text output for parsing |

### Gemini CLI (Advisor)

```bash
gemini -p "PROMPT" \
  -m gemini-2.5-pro \
  --sandbox
```

| Flag | Purpose |
|------|---------|
| `-p "PROMPT"` | Non-interactive mode |
| `-m gemini-2.5-pro` | Use Gemini 2.5 Pro (1M context, best reasoning) |
| `--sandbox` | Sandboxed execution, prevents file modifications |

**Note:** Gemini CLI's `thinkingBudget` parameter isn't yet exposed as a CLI flag (GitHub issue #6693). The model uses dynamic thinking by default. When the flag becomes available, add `--thinking-budget 32768` for maximum reasoning.

### Codex CLI (ChatGPT/OpenAI Advisor)

```bash
codex exec "PROMPT" \
  --sandbox read-only \
  --model gpt-5.2
```

| Flag | Purpose |
|------|---------|
| `exec "PROMPT"` | Non-interactive execution mode |
| `--sandbox read-only` | Prevents file modifications |
| `--model gpt-5` | Use GPT-5 (or gpt-5-codex for coding tasks) |

**Reasoning configuration:** Set `model_reasoning_effort = "xhigh"` in `~/.codex/config.toml` for maximum reasoning. This can't be passed as a CLI flag currently.

### Working Directory

All CLIs should be invoked from the **project root directory** that the user runs `meld` from:

```python
process = await asyncio.create_subprocess_exec(
    *cmd,
    cwd=os.getcwd(),  # User's current working directory
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE
)
```

## Convergence Detection

### Approach: Hybrid (Melder signal + diff validation)

**Primary signal:** Melder explicitly declares convergence status in structured output.

**Secondary signal:** Diff ratio validates Melder's claim.

### Melder Synthesis Prompt (end of response)

```markdown
After incorporating feedback, end your response with two sections:

## Decision Log

ACCEPTED:
- [Advisor] Brief description of incorporated feedback (1 line each)

REJECTED:
- [Advisor] Brief description — reason for rejection (1 line each)

DEFERRED / NEEDS HUMAN DECISION:
- Brief description + what input is needed (1 line each)

## Convergence Assessment

STATUS: [CONVERGED | CONTINUING]
CHANGES_MADE: [count of substantive changes incorporated]
OPEN_ITEMS: [count of unresolved concerns, including DEFERRED items]
RATIONALE: [one sentence explanation]

Then output a JSON block for machine parsing:

```json
{
  "status": "CONVERGED" | "CONTINUING",
  "changes_made": <number>,
  "open_items": <number>,
  "deferred_items": ["item1", "item2"],
  "rationale": "one sentence"
}
```

Choose CONVERGED only if:
- No substantive changes to plan structure or approach
- All advisor concerns addressed or reasonably dismissed
- DEFERRED list is empty (no items needing human decision)
- Plan is ready for implementation

Choose CONTINUING if:
- You made meaningful changes
- Unresolved concerns remain
- Any DEFERRED items exist
- Any uncertainty about the plan
```

### Decision Log Purpose

The Decision Log provides:
- **Transparency**: Users see WHY feedback was incorporated or rejected
- **Debugging**: When plans don't converge as expected, trace contested points
- **Convergence accuracy**: DEFERRED items block false convergence
- **Audit trail**: Important for trust in the tool's synthesis

### Detection Logic

```python
import re
import json
from difflib import SequenceMatcher

def parse_convergence_json(response: str) -> dict | None:
    """Extract JSON convergence block from Melder response."""
    match = re.search(r'```json\s*(\{[^`]+\})\s*```', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None

def detect_convergence(
    melder_response: str,
    prev_plan: str,
    curr_plan: str,
    round_num: int
) -> tuple[bool, str]:
    # Never converge on round 1
    if round_num == 1:
        return False, "First round - collecting initial feedback"

    # Parse structured JSON block (primary method)
    conv = parse_convergence_json(melder_response)
    if conv:
        open_items = conv.get("open_items", 0)
        melder_says_converged = conv.get("status") == "CONVERGED"
    else:
        # Fallback to regex parsing (legacy/malformed responses)
        status_match = re.search(r'STATUS:\s*(CONVERGED|CONTINUING)', melder_response)
        melder_says_converged = status_match and status_match.group(1) == "CONVERGED"
        open_items = _parse_int(melder_response, r'OPEN_ITEMS:\s*(\d+)')

    # OPEN_ITEMS > 0 means we can NEVER converge (regardless of other signals)
    if open_items is not None and open_items > 0:
        return False, f"Continuing: {open_items} open items remain"

    # Compute diff ratio
    diff_ratio = compute_diff_ratio(prev_plan, curr_plan)
    small_diff = diff_ratio < 0.05  # <5% changed

    # Decision matrix (only reached if OPEN_ITEMS == 0 or unknown)
    if melder_says_converged and small_diff:
        return True, "Converged: Melder confirmed, minimal changes, no open items"
    elif melder_says_converged and not small_diff:
        return False, "Continuing: Melder said converged but significant changes detected"
    elif not melder_says_converged and small_diff:
        return False, "Continuing: Melder indicates work remains"
    else:
        return False, "Continuing: substantive changes made"

def compute_diff_ratio(old: str, new: str) -> float:
    """0.0 = identical, 1.0 = completely different"""
    old_norm = ' '.join(old.split())
    new_norm = ' '.join(new.split())
    return 1.0 - SequenceMatcher(None, old_norm, new_norm).ratio()

def _parse_int(text: str, pattern: str) -> int | None:
    """Extract integer from text using regex pattern."""
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None
```

### Decision Matrix

| OPEN_ITEMS | Melder Says | Diff Size | Round | Action |
|------------|-------------|-----------|-------|--------|
| > 0 | any | any | any | **Never converge** |
| 0 | CONVERGED | <5% | 2+ | **Converge** |
| 0 | CONVERGED | >5% | any | Continue (Melder wrong) |
| 0 | CONTINUING | any | any | Continue (trust Melder) |
| unknown | any | any | any | Fall back to existing logic |
| any | any | any | 1 | Continue (never converge R1) |

### Edge Cases

1. **Malformed response:** Fall back to diff-only (converge if <2% changed)
2. **Oscillation:** Track last 3 plans; if cycling, produce stable plan with explicit "Needs Human Decision" section
3. **Max rounds:** Always terminate at max regardless of status

## Advisor Feedback Prompt

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Format | Lightly structured markdown | Preserves natural language while making synthesis reliable (PRD requirement) |
| Roles | Identical | Let model diversity produce different perspectives |
| Context | Task + PRD + plan | Full context without cross-advisor contamination |
| Tone | Balanced | Honest critique without being adversarial |

### Prompt Template

```
You are reviewing an implementation plan for a software task.

## Original Task

{task_description}

## Product Requirements

{prd_content}

## Current Plan (Round {round_num})

{current_plan}

---

Review this plan honestly. Your job is to help improve it.

Return feedback using the following headings (keep it concise):

## Summary (1-3 bullets)
- Your overall assessment

## Must-Fix Risks (0-5 bullets)
- [Severity: Low/Med/High] Issue description + suggested fix

## Improvements (0-10 bullets)
- Suggestions that would make the plan better

## Missing Requirements / Edge Cases (0-10 bullets)
- PRD requirements not addressed, or edge cases not considered

## Questions / Assumptions to Validate (0-10 bullets)
- Clarifications needed before implementation

If the plan is solid and you have no substantive feedback, say so
briefly under "Summary" and leave the other sections empty.
```

### Why Lightly Structured?

The PRD requires "structured feedback (improvements, concerns, additions, rationale)." Pure freeform doesn't meet this requirement.

Light structure:
- Gives Melder consistent anchors for comparison ("Must-Fix", "Missing", "Questions")
- Improves synthesis quality and reduces false convergence
- Still allows natural language within sections
- Doesn't force-fit every thought into rigid schemas

### Context Scope

Including the PRD ensures advisors can check plan against requirements.
Excluding previous feedback keeps perspectives independent (no groupthink).

## Preflight Validation

Before starting the meld process, validate the environment:

```python
import shutil
from pathlib import Path

async def run_preflight() -> list[str]:
    """Returns list of errors, empty if all checks pass."""
    errors = []

    # Check CLIs exist
    cli_install = {
        "claude": "npm install -g @anthropic-ai/claude-code",
        "gemini": "npm install -g @google/gemini-cli",
        "codex": "npm install -g @openai/codex",
    }

    for cli, install_cmd in cli_install.items():
        if not shutil.which(cli):
            errors.append(f"CLI not found: {cli}. Install with: {install_cmd}")

    return errors
```

### Preflight Error Messages

| Check | Error | Fix |
|-------|-------|-----|
| `claude` missing | `CLI not found: claude` | `npm install -g @anthropic-ai/claude-code` |
| `gemini` missing | `CLI not found: gemini` | `npm install -g @google/gemini-cli` |
| `codex` missing | `CLI not found: codex` | `npm install -g @openai/codex` |

## Error Handling

### Error Categories

| Category | Cause | Auto-Retry | User Action |
|----------|-------|------------|-------------|
| `CLI_NOT_FOUND` | CLI not installed | No | Install CLI (see Preflight) |
| `AUTH_FAILED` | Not authenticated | No | `{cli} auth login` |
| `TIMEOUT` | Response too slow | Once | `--timeout 900` or simplify task |
| `RATE_LIMITED` | API quota exceeded | Yes (exp. backoff) | Wait or check quota |
| `NETWORK_ERROR` | Connectivity issue | Yes (3x) | Check network |
| `PARSE_ERROR` | Unexpected CLI output | No | File bug with `--verbose` output |

### Retry Strategy

```python
from enum import Enum, auto

class AdvisorError(Enum):
    CLI_NOT_FOUND = auto()
    AUTH_FAILED = auto()
    TIMEOUT = auto()
    RATE_LIMITED = auto()
    NETWORK_ERROR = auto()
    PARSE_ERROR = auto()

RETRY_CONFIG = {
    AdvisorError.TIMEOUT: {"max_retries": 1, "backoff": None},
    AdvisorError.RATE_LIMITED: {"max_retries": 3, "backoff": "exponential"},  # 1s, 2s, 4s
    AdvisorError.NETWORK_ERROR: {"max_retries": 3, "backoff": "linear"},      # 1s, 1s, 1s
}
```

### Graceful Degradation

After exhausting retries for an advisor:
1. Log the failure with full context
2. Continue with remaining advisor(s)
3. Note in final output which advisors participated
4. If ALL advisors fail, output best plan so far with warning

## TUI Status Indicators

### Status States

| Status | Icon | Color | When |
|--------|------|-------|------|
| Waiting | `○` | dim | Advisor hasn't started yet |
| Running | `◐` | yellow | Currently executing |
| Streaming | `▌` | cyan | Actively receiving output |
| Complete | `●` | green | Finished successfully |
| Failed | `✗` | red | Error after retries exhausted |
| Retrying | `↻` | orange | Failed once, trying again |

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│                      MELDER (Claude)                        │
│  [Round 2/5] ▌ Synthesizing feedback...                     │
│                                                             │
│  The authentication flow should use OAuth2 with PKCE for    │
│  mobile clients. Based on advisor feedback, I'm updating    │
│  the token refresh strategy to use sliding expiration...▌   │
├───────────────────┬───────────────────┬─────────────────────┤
│      CLAUDE       │      GEMINI       │       CODEX         │
│    ● 45s          │   ↻ Retry 1/1     │   ◐ 2m 15s          │
│                   │                   │                     │
│  Feedback:        │  Timed out,       │  Feedback:          │
│  - The auth flow  │  retry 1/1...     │  ▌                  │
│    looks solid... │                   │                     │
└───────────────────┴───────────────────┴─────────────────────┘
                    [Session: 4m 32s | Round 2 | ◐ Active]
```

**Status bar elements:**
- Session elapsed time (total runtime)
- Current round number
- Overall activity indicator (spinning when any subprocess active)

### Phase Indicators

The Melder panel header shows current phase:
- `[Planning]` - Initial plan generation
- `[Feedback Round N/M]` - Collecting advisor feedback
- `[Synthesizing]` - Melder incorporating feedback
- `[Converged]` - Process complete

## CLI Flags Reference

### Subcommands

| Command | Description |
|---------|-------------|
| `meld run [TASK]` | Run a meld session (default if no subcommand) |
| `meld doctor` | Check CLI availability and authentication |

### Input Options

| Flag | Default | Description |
|------|---------|-------------|
| `TASK` | - | Task description (positional arg) |
| `--file FILE` | - | Read task from file |
| (stdin) | - | Read task from pipe (auto-detected) |
| `--prd FILE` | - | Load PRD file for context |

### Run Control

| Flag | Default | Description |
|------|---------|-------------|
| `--rounds N` | 5 | Maximum iteration rounds |
| `--timeout SECS` | 600 | Per-advisor timeout in seconds |

### Cancellation Behavior

Pressing Ctrl+C during a session:
1. Immediately signals all running advisor subprocesses to terminate
2. Waits up to 5 seconds for graceful shutdown
3. Force-kills any remaining processes
4. Saves current state to session directory with status `interrupted`
5. Displays: `Session interrupted. Resume with: meld --resume {run_id}`

The session can be resumed from the last completed round using `--resume`.

### Session Management

| Flag | Default | Description |
|------|---------|-------------|
| `--resume RUN_ID` | - | Resume interrupted session from last checkpoint |
| `--run-dir DIR` | `.meld/runs/` | Directory for session artifacts |

### Output Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output FILE` | stdout | Write final plan to file |
| `--json-output FILE` | - | Write machine-readable JSON summary (for CI) |
| `--quiet`, `-q` | false | No TUI; final plan to stdout; progress to stderr |
| `--verbose` | false | Include raw advisor outputs in final document |

### Quiet Mode Behavior

In quiet mode (`--quiet` or `-q`):
- No TUI is displayed
- Progress messages go to stderr: `Round 1/5... Round 2/5...`
- Final plan goes to stdout (unless `--output` specified)
- Exit codes:
  - `0`: Converged successfully
  - `1`: Max rounds reached without convergence
  - `2`: Preflight failed (missing CLIs)
  - `3`: All advisors failed
  - `4`: Melder failed
  - `5`: Interrupted by user (Ctrl+C)

**Example usage:**
```bash
# Pipe to file
meld -q "Build auth system" > plan.md

# Check convergence
meld -q "Build auth system" && echo "Converged!" || echo "Needs review"

# With progress visible
meld -q "Build auth system" 2>&1 | tee session.log
```

### Other

| Flag | Default | Description |
|------|---------|-------------|
| `--skip-preflight` | false | Skip CLI validation checks |

## Session Directory Structure

```
.meld/
  runs/
    2026-01-16T02-47-17Z-abc123/
      session.json          # Run metadata, status, config
      task.md               # Original task input
      prd.md                # PRD content (if provided)
      plan.round0.md        # Initial plan (before feedback)
      plan.round1.md        # Plan after round 1
      advisor.claude.round1.md
      advisor.gemini.round1.md
      advisor.codex.round1.md
      plan.round2.md
      advisor.claude.round2.md
      ...
      final-plan.md         # Final output (on completion)
      events.jsonl          # Structured event log
```

### session.json Schema

```json
{
  "id": "2026-01-16T02-47-17Z-abc123",
  "status": "in_progress | completed | failed | interrupted",
  "current_round": 2,
  "interrupted_at": "planning | feedback | synthesis",
  "max_rounds": 5,
  "started": "2026-01-16T02:47:17Z",
  "updated": "2026-01-16T02:52:00Z",
  "config": {
    "timeout": 600,
    "prd_file": "requirements.md"
  },
  "advisors": {
    "claude": "completed",
    "gemini": "failed",
    "codex": "completed"
  },
  "convergence": {
    "status": "continuing",
    "open_items": 2,
    "diff_ratio": 0.08
  }
}
```

**Note:** `interrupted_at` field is only present when `status` is `interrupted`, indicating which phase was in progress when the user pressed Ctrl+C.

## Open Items

None - ready for decomposition.

## Sources

- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-usage)
- [Gemini CLI GitHub](https://github.com/google-gemini/gemini-cli)
- [Gemini CLI Sandbox Docs](https://geminicli.com/docs/cli/sandbox/)
- [Codex CLI Reference](https://developers.openai.com/codex/cli/reference/)
- [Codex Config Reference](https://developers.openai.com/codex/config-reference/)
