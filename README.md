# Meld

Multi-model planning convergence CLI that synthesizes plans from multiple AI providers.

## Overview

Meld orchestrates multiple AI advisors (Claude, Gemini, OpenAI) to collaboratively develop implementation plans. Through iterative refinement, the advisors converge on a unified approach that incorporates diverse perspectives.

## Installation

```bash
pip install meld
```

Or install from source:

```bash
git clone https://github.com/meld-project/meld.git
cd meld
pip install -e .
```

## Usage

### Basic Usage

```bash
# Run with a task description
meld "Build an authentication system with OAuth2 support"

# Read task from file
meld --file task.txt

# Pipe task from stdin
echo "Design a REST API for user management" | meld
```

### With PRD Context

```bash
meld "Implement user authentication" --prd requirements.md
```

### Options

```bash
meld "Task description" \
  --rounds 5              # Max iteration rounds (default: 5)
  --timeout 600           # Timeout per advisor in seconds (default: 600)
  --output plan.md        # Write final plan to file
  --json-output summary.json  # Write JSON summary
  --quiet                 # Minimal output, no TUI
  --verbose               # Include raw advisor outputs
  --skip-preflight        # Skip environment checks
```

### Session Management

```bash
# Resume an interrupted run
meld --resume 2026-01-16T02-47-17Z-abc123

# Custom run directory
meld "Task" --run-dir ./custom-runs/
```

### Environment Check

```bash
# Check if all required CLIs are available
meld doctor
```

## How It Works

1. **Preflight**: Verifies required CLI tools (claude, gemini, openai) are available
2. **Initial Planning**: Each advisor independently generates an implementation plan
3. **Critique Rounds**: Advisors review and critique each other's plans
4. **Synthesis**: A "melder" synthesizes critiques into a unified plan
5. **Convergence**: Process repeats until advisors reach consensus or max rounds

## Requirements

- Python 3.10+
- At least one AI CLI tool:
  - `claude` (Anthropic Claude)
  - `gemini` (Google Gemini)
  - `openai` (OpenAI)

## License

MIT
