# LabUtopia Learn Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a long interactive static HTML tutorial that explains LabUtopia end to end for a Chinese-speaking reader with basic Isaac Sim, USD, and robot-learning background.

**Architecture:** Keep the first version as a single self-contained `learn/index.html`, with inline CSS and JavaScript so it has no build step. Add a small Python validator that checks required sections, source links, local code references, and interaction hooks.

**Tech Stack:** Static HTML, CSS, vanilla JavaScript, Python standard library validation, Playwright/browser visual audit.

---

### Task 1: Add Static Validation

**Files:**
- Create: `learn/validate.py`

- [x] **Step 1: Write the failing validator**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def main():
    require(INDEX.exists(), "learn/index.html must exist")
    html = INDEX.read_text(encoding="utf-8")
    for phrase in [
        "LabUtopia",
        "SimulationApp",
        "task.step",
        "controller.step",
        "DataCollector",
        "Diffusion Policy",
        "Action Chunking Transformer",
        "OpenUSD",
        "Hydra",
        "Bibliography",
    ]:
        require(phrase in html, f"missing required phrase: {phrase}")
    for hook in [
        "data-stepper",
        "data-config-tabs",
        "data-loop-demo",
        "data-boundary-switch",
        "data-dataset-visualizer",
        "data-glossary-search",
    ]:
        require(hook in html, f"missing interactive hook: {hook}")

if __name__ == "__main__":
    main()
```

- [x] **Step 2: Run validator to verify red**

Run: `python3 learn/validate.py`

Expected: fails with `learn/index.html must exist`.

### Task 2: Create The Tutorial

**Files:**
- Create: `learn/index.html`
- Create: `learn/README.md`

- [ ] **Step 1: Implement static HTML book**

Create the full tutorial with the approved sections, inline design system, interactive widgets, and bibliography.

- [ ] **Step 2: Run validator to verify green**

Run: `python3 learn/validate.py`

Expected: exit code 0.

### Task 3: Browser Review

**Files:**
- Modify if needed: `learn/index.html`

- [ ] **Step 1: Start local server**

Run from `learn/`: `python3 -m http.server 8099`

Expected: serves `http://127.0.0.1:8099/index.html`.

- [ ] **Step 2: Audit in browser**

Use desktop and mobile viewports. Check no broken image requests, no console errors that break controls, no horizontal overflow, and readable Chinese/English mixed text.

- [ ] **Step 3: Fix defects and re-run checks**

Run `python3 learn/validate.py` and `git diff --check`.
