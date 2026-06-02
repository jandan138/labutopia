# LabUtopia Interactive Learn Guide Design

## Goal

Create a long, approachable Chinese HTML tutorial that helps a reader with basic Isaac Sim, USD asset, and reinforcement-learning exposure build a full mental model of the LabUtopia repository.

## Audience

The reader can operate Isaac Sim through GUI basics, has seen USD assets, and has introductory reinforcement-learning vocabulary. The tutorial should therefore explain implementation flow slowly, while preserving English terminology such as `SimulationApp`, `World`, `Stage`, `task`, `controller`, `policy`, `Diffusion Policy`, `ACT`, `HDF5`, `Hydra`, and `success rate`.

## Format

Use a single static page at `learn/index.html`. A single page is preferable for this first version because the user asked for something like a book, and a single page keeps the narrative path intact. The page will include a sticky table of contents, progress bar, interactive diagrams, collapsible code explanations, and a bibliography.

## Content Structure

The page will cover:

1. What LabUtopia is, and why it should not be confused with a standard Gym-style RL environment.
2. The paper-level model: `LabSim`, `LabScene`, and `LabBench`.
3. The local repository map: `main.py`, `config/`, `tasks/`, `controllers/`, `factories/`, `data_collectors/`, `policy/`, and `assets/`.
4. The Isaac Sim runtime model: `SimulationApp`, `World`, `Stage`, USD references, physics, and cameras.
5. The episode loop: `world.step()`, `task.step()`, `controller.step()`, `apply_action()`, reset, and video saving.
6. The boundary between `task` and `controller`.
7. Data collection into `HDF5` and `episode.jsonl`.
8. Training with `ACT` and `Diffusion Policy`.
9. Inference through `local`, `remote`, and `replay` engines.
10. The five benchmark levels and three case studies: `level1_pick`, `Level4_CleanBeaker`, and `level5_Navigation`.
11. A practical extension/debugging guide.
12. A bibliography linking paper, docs, and primary sources.

## Interactive Elements

The page will include:

- A pipeline stepper for `main.py`.
- A tabbed config explorer for `level1_pick`, `level4_CleanBeaker`, and `level5_Navigation`.
- An animated episode loop diagram.
- A `task` vs `controller` boundary switcher.
- A dataset shape visualizer for camera/state/action records.
- A benchmark level ladder.
- A glossary filter.

## Source Base

The tutorial integrates local repository inspection with external sources:

- LabUtopia arXiv and OpenReview pages.
- LabUtopia project page and Hugging Face dataset page.
- NVIDIA Isaac Sim 5.1 documentation for sensors, `SimulationApp`, stage utilities, and core API.
- OpenUSD documentation for `Stage`, `Prim`, `Layer`, and composition.
- NVIDIA Isaac Lab documentation to distinguish Isaac Lab-style RL from this repository.
- Diffusion Policy and ACT papers.
- LeRobot and Hydra documentation.

## File Scope

Create:

- `learn/index.html`: tutorial, styling, and JavaScript in one static file.
- `learn/README.md`: opening instructions.
- `learn/validate.py`: static regression checks for required content.

Create process records:

- `docs/superpowers/specs/2026-06-02-labutopia-learn-guide-design.md`
- `docs/superpowers/plans/2026-06-02-labutopia-learn-guide.md`

## Verification

Run:

- `python3 learn/validate.py`
- `python3 -m http.server 8099` from `learn/`
- Browser audit across desktop and mobile viewports.
- `git diff --check`
