# Meld v1 Bead Structure Review

## Executive Summary

After analyzing 50 beads created from the meld-v1 epic, I've identified several structural issues that should be addressed before implementation begins. This document outlines the problems and proposes specific fixes.

## Current State

- **Total beads:** 50
- **Structure:** 11 main tasks with subtasks
- **Dependency graph:** Generally correct at task level, but missing critical cross-cutting dependencies

## Critical Issues Found

### 1. E2E Tests Dependency Chain Incomplete

**Problem:** E2E tests (11.4) only depend on 11.3 (unit tests), but they actually need ALL system components to be built and working.

**Impact:** E2E tests would be blocked waiting for unit tests but could fail because core components aren't ready.

**Fix:** Add dependencies:
```
11.4 depends on:
  - 8.2 (signal handling - for graceful shutdown tests)
  - 9.3 (status indicators - for TUI state verification)
  - 10.2 (JSON output - for CI verification)
  - 6.5 (oscillation detection - for oscillation E2E test)
  - 2.7 (events.jsonl - for event verification tests)
```

### 2. Oscillation Detection Not Wired Into Main Loop

**Problem:** Oscillation detection (6.5) is implemented but the orchestrator (8.1) doesn't explicitly depend on it.

**Impact:** Main loop might be implemented without oscillation checks, requiring rework.

**Fix:** Add dependency:
```
8.1 (main convergence loop) depends on 6.5 (oscillation detection)
```

### 3. Event Logging Is A Leaf Node

**Problem:** Events.jsonl (2.7) is implemented but nothing uses it. The orchestrator, advisors, and melder should all emit events.

**Impact:** Events would be implemented but never integrated into the system.

**Fix:** Add dependencies (make 2.7 a prerequisite for components that emit events):
```
8.1 (orchestrator) depends on 2.7 (events.jsonl)
7.1 (parallel advisor invocation) depends on 2.7
6.2 (Melder class) depends on 2.7
```

### 4. Secret Redaction Not Prerequisite For Writing

**Problem:** Secret redaction (2.5) is a leaf node but should be applied by atomic file writing (2.2).

**Current:** 2.5 depends on 2.2
**Should be:** 2.2 implementation should INCLUDE secret redaction, or 2.5 should come before artifacts are written in a way that 2.2 uses it.

**Fix:** Merge 2.5 INTO 2.2's acceptance criteria, or make 2.5 depend on 2.1 and 2.2 depend on 2.5:
```
2.5 depends on 2.1 (session directory exists)
2.2 depends on 2.5 (redaction available for writing)
```

### 5. Plan Delta Needs Convergence Logic

**Problem:** Plan Delta indicator (9.4) depends only on TUI (9.1), but it needs convergence detection (6.3) to understand what changed between plans.

**Fix:** Add dependency:
```
9.4 depends on 6.3 (convergence detection provides diff_ratio)
```

### 6. Testing As Separate Phase (Design Issue)

**Problem:** All tests are in Task 11, running after implementation. This prevents TDD and means tests are an afterthought.

**Recommendation:** Keep current structure BUT ensure:
1. Each component's acceptance criteria explicitly lists required test scenarios
2. Unit test task (11.3) runs BEFORE E2E (already correct)
3. MockAdapter (11.2) depends specifically on 3.2 (ProviderAdapter base class)

### 7. Quiet Mode Bypass Logic

**Problem:** Quiet mode (10.3) needs to bypass TUI, so it must understand TUI exists.

**Current:** Depends on 10.1, 10.2
**Should also depend on:** 9 (TUI task) to ensure it can properly bypass

**Fix:** Add dependency:
```
10.3 depends on 9 (understands what TUI provides to bypass it)
```

### 8. Missing Final Integration Task

**Problem:** No explicit task to wire everything together before E2E tests.

**Recommendation:** The orchestrator (8.1) effectively serves this purpose, but we should add an acceptance criterion to 8.1:
- "Complete integration test: run full meld session with mocks"

## Acceptance Criteria Gaps

Several beads have good descriptions but weak acceptance criteria:

### 6.5 (Oscillation Detection)
Missing:
- [ ] OscillationDetector is imported and used by Orchestrator
- [ ] Orchestrator checks for oscillation BEFORE normal convergence

### 7.1 (Parallel Advisor Invocation)
Missing:
- [ ] AdvisorPool uses EventLogger to log advisor start/complete/error
- [ ] Timeout cancellation properly cleans up all running advisors

### 8.1 (Main Convergence Loop)
Missing:
- [ ] Uses oscillation detection
- [ ] Emits events via EventLogger
- [ ] Calls session.update_status() at each phase transition

### 9.2 (Streaming Content Display)
Missing:
- [ ] Throttling specifically tested (verify no faster than 30fps)
- [ ] Memory doesn't grow unbounded with long output

## Testing Coverage Analysis

The E2E test bead (11.4) has excellent acceptance criteria covering 12 scenarios:
1. Happy path
2. Partial advisor failure
3. All advisors fail
4. Max rounds reached
5. Resume from interrupt
6. Oscillation detection
7. Secret redaction
8. No-save mode
9. Quiet mode
10. Events.jsonl verification
11. Plan delta indicator
12. Signal handling

**These are comprehensive.** However, unit tests (11.3) are incomplete. The description is truncated.

### Recommended Unit Test Additions for 11.3:

```python
# test_secret_redaction.py - CRITICAL
class TestSecretRedaction:
    def test_openai_key_redacted(self): ...
    def test_anthropic_key_redacted(self): ...
    def test_aws_key_redacted(self): ...
    def test_github_token_redacted(self): ...
    def test_generic_patterns(self): ...
    def test_non_secret_preserved(self): ...

# test_event_logger.py
class TestEventLogger:
    def test_logs_to_file(self): ...
    def test_respects_no_save(self): ...
    def test_file_locking(self): ...
    def test_all_event_types(self): ...

# test_plan_delta.py
class TestPlanDelta:
    def test_section_count_change(self): ...
    def test_line_count_change(self): ...
    def test_key_change_extraction(self): ...
    def test_initial_plan_delta(self): ...
```

## Proposed Dependency Updates

Execute these bd commands to fix dependencies:

```bash
# Fix oscillation detection → orchestrator
bd dep add meld-eq0.8.1 meld-jjp

# Fix event logging integration
bd dep add meld-eq0.8.1 meld-a0o
bd dep add meld-eq0.7.1 meld-a0o
bd dep add meld-eq0.6.2 meld-a0o

# Fix secret redaction order
bd dep rm meld-eq0.2.5 meld-eq0.2.2  # Remove current
bd dep add meld-eq0.2.5 meld-eq0.2.1  # 2.5 depends on 2.1
bd dep add meld-eq0.2.2 meld-eq0.2.5  # 2.2 depends on 2.5

# Fix plan delta dependency on convergence
bd dep add meld-p7f meld-eq0.6.3

# Fix E2E test dependencies
bd dep add meld-eq0.11.4 meld-eq0.8.2
bd dep add meld-eq0.11.4 meld-eq0.9.3
bd dep add meld-eq0.11.4 meld-eq0.10.2
bd dep add meld-eq0.11.4 meld-jjp
bd dep add meld-eq0.11.4 meld-a0o

# Fix quiet mode TUI awareness
bd dep add meld-eq0.10.3 meld-eq0.9
```

## Performance Benchmarks Gap (11.5)

The performance benchmarks bead is solid but missing:
- Memory profiling benchmark
- Context size measurement (plans + feedback don't exceed limits)

Add to acceptance criteria:
- [ ] Memory usage stays under 500MB for typical session
- [ ] Context tracking shows total tokens per round

## Recommended Priority Adjustments

Current: All beads are priority 1.

Suggested:
- Keep foundation (Tasks 1-3) at P1
- Core logic (Tasks 4-8) at P1
- TUI (Task 9) could be P2 (--quiet mode works without TUI)
- Testing (Task 11) at P1 (critical for quality)
- Polish (Task 10) at P2

However, since this is a small project with one implementer, priority 1 for all is acceptable.

## Summary of Actions

1. **Add 11 missing dependencies** (see commands above)
2. **Update 11.3 acceptance criteria** with required unit tests
3. **Update 11.5 acceptance criteria** with memory benchmarks
4. **Update 8.1 acceptance criteria** to include oscillation and events
5. **Verify 2.2 includes redaction** (or fix dependency order)

Total estimated changes: ~15 bead updates

---

## Changes Applied (2026-01-16)

### Dependencies Added
All 11 proposed dependency changes have been applied:

1. ✅ `meld-eq0.8.1` now depends on `meld-jjp` (oscillation detection)
2. ✅ `meld-eq0.8.1` now depends on `meld-a0o` (event logging)
3. ✅ `meld-eq0.7.1` now depends on `meld-a0o` (event logging)
4. ✅ `meld-eq0.6.2` now depends on `meld-a0o` (event logging)
5. ✅ `meld-eq0.2.5` now depends on `meld-eq0.2.1` (redaction before writing)
6. ✅ `meld-eq0.2.2` now depends on `meld-eq0.2.5` (writing uses redaction)
7. ✅ `meld-p7f` now depends on `meld-eq0.6.3` (plan delta needs convergence)
8. ✅ `meld-eq0.11.4` now depends on `meld-eq0.8.2` (E2E needs signal handling)
9. ✅ `meld-eq0.11.4` now depends on `meld-eq0.9.3` (E2E needs status indicators)
10. ✅ `meld-eq0.11.4` now depends on `meld-eq0.10.2` (E2E needs JSON output)
11. ✅ `meld-eq0.11.4` now depends on `meld-jjp` (E2E needs oscillation)
12. ✅ `meld-eq0.11.4` now depends on `meld-a0o` (E2E needs events)
13. ✅ `meld-eq0.10.3` now depends on `meld-eq0.9` (quiet mode needs TUI awareness)

### Acceptance Criteria Updated
The following beads had their acceptance criteria enhanced:

1. ✅ **meld-eq0.8.1** (Main Convergence Loop)
   - Added oscillation detection requirement
   - Added EventLogger usage requirements
   - Added testing requirements

2. ✅ **meld-eq0.11.3** (Unit Tests)
   - Added comprehensive test requirements for all modules
   - Added secret redaction tests
   - Added event logger tests
   - Added oscillation detector tests
   - Added plan delta tests

3. ✅ **meld-eq0.11.5** (Performance Benchmarks)
   - Added memory usage benchmarks (<500MB peak)
   - Added memory leak detection
   - Added context size tracking

4. ✅ **meld-jjp** (Oscillation Detection)
   - Made orchestrator integration explicit
   - Added testing requirements

5. ✅ **meld-a0o** (Events.jsonl)
   - Made integration requirements explicit
   - Clarified which components must use EventLogger

6. ✅ **meld-eq0.7.1** (Parallel Advisor Invocation)
   - Added EventLogger usage requirements
   - Added timeout cancellation requirements

7. ✅ **meld-eq0.6.2** (Melder Class)
   - Added EventLogger usage requirements
   - Added extraction testing requirements

### Verification
- ✅ No dependency cycles detected
- ✅ E2E tests now have 7 dependencies (was 2)
- ✅ Main loop now has 5 dependencies (was 3)
- ✅ All acceptance criteria include testing requirements

### Final Bead Statistics
- **Total beads:** 50
- **Total dependencies:** ~113 edges (was ~102)
- **Maximum depth:** Unchanged
- **Cycles:** None
