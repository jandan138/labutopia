from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content.js"
INDEX = ROOT / "index.html"
CHAPTERS = ROOT / "chapters"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def section_files(content_js: str) -> list[str]:
    matches = re.findall(r'"file"\s*:\s*"([^"]+)"|file:\s*"([^"]+)"', content_js)
    return [left or right for left, right in matches]


def main() -> None:
    index_html = read(INDEX)
    content_js = read(CONTENT)

    require("window.LABUTOPIA_BOOK" in content_js, "content.js must define window.LABUTOPIA_BOOK")
    require("book-search" in index_html, "index must include book search UI")
    require("cover-toc" in index_html, "index must include a table of contents")
    require(".book" in read(ROOT / "assets/css/book.css"), "book.css must style the book shell")
    require("LABUTOPIA_BOOK" in read(ROOT / "assets/js/book.js"), "book.js must load book metadata")

    files = section_files(content_js)
    require(len(files) >= 40, f"expected at least 40 section files, found {len(files)}")
    require(len(files) == len(set(files)), "section files must be unique")

    for file_name in files:
        path = ROOT / file_name
        html = read(path)
        require('data-section="' in html, f"{file_name} missing data-section")
        require('<p class="lede">' in html, f"{file_name} missing lede paragraph")
        require("<h2 id=" in html, f"{file_name} missing h2 anchors")
        require('class="plain-card"' in html, f"{file_name} missing plain-language card")
        require("先讲人话" in html, f"{file_name} missing plain-language explanation")
        require("你可以这样想" in html, f"{file_name} missing analogy explanation")
        require("读完你应该能回答" in html, f"{file_name} missing reader checkpoint")
        require("TODO" not in html and "TBD" not in html, f"{file_name} contains placeholders")

    all_html = "\n".join(read(ROOT / file_name) for file_name in files) + "\n" + index_html
    required_terms = [
        "SimulationApp",
        "World",
        "Hydra",
        "OpenUSD",
        "PhysX",
        "RTX Renderer",
        "BaseTask",
        "BaseController",
        "DataCollector",
        "Diffusion Policy",
        "Action Chunking Transformer",
        "Franka",
        "ridgeback_franka",
        "EBench-Assets",
        "EBench-Dataset",
        "GenManip",
        "LeRobot",
        "lift2",
        "Isaac Sim 4.1",
        "Isaac Sim 5.1",
        "不能直接复用",
        "not plug-and-play",
    ]
    for term in required_terms:
        require(term in all_html, f"missing required term: {term}")

    required_widgets = [
        'data-widget="runtime-loop"',
        'data-widget="task-levels"',
        'data-widget="asset-map"',
        'data-widget="dataset-flow"',
        'data-widget="reuse-matrix"',
        'data-widget="version-bridge"',
    ]
    for widget in required_widgets:
        require(widget in all_html, f"missing widget: {widget}")

    widgets_js = read(ROOT / "assets/js/widgets/book-widgets.js")
    require("widget-help" in widgets_js, "widgets must render help text that explains why the control exists")
    require("widget-feedback" in widgets_js, "widgets must render feedback that changes when the reader interacts")
    require("data-widget-action" in widgets_js, "interactive widget controls must expose data-widget-action markers")

    required_sources = [
        "https://arxiv.org/abs/2505.22634",
        "https://proceedings.neurips.cc/paper_files/paper/2025/hash/313d6659e6532e6ba192dfb910d4261e-Abstract-Datasets_and_Benchmarks_Track.html",
        "https://rui-li023.github.io/labutopia-site/",
        "https://huggingface.co/datasets/Ruinwalker/Labutopia-Dataset",
        "https://github.com/InternRobotics/EBench",
        "https://internrobotics.github.io/EBench-doc/",
        "https://huggingface.co/datasets/InternRobotics/EBench-Assets",
        "https://huggingface.co/datasets/InternRobotics/EBench-Dataset",
        "https://arxiv.org/abs/2506.10966",
        "https://docs.isaacsim.omniverse.nvidia.com/latest/index.html",
        "https://openusd.org/release/intro.html",
        "https://huggingface.co/docs/lerobot/main/en/index",
        "https://hydra.cc/docs/intro/",
    ]
    for link in required_sources:
        require(link in all_html, f"missing source link: {link}")

    comparison_files = [f for f in files if "/07-ebench-assets/" in f]
    require(len(comparison_files) >= 8, "asset comparison chapter must have at least 8 sections")
    comparison_html = "\n".join(read(ROOT / file_name) for file_name in comparison_files)
    comparison_lower = comparison_html.lower()
    comparison_terms = [
        "LabUtopia assets",
        "EBench assets",
        "USD",
        "MDL",
        "task/eval contract",
        "embodiment mismatch",
        "dataset format mismatch",
        "conversion workflow",
        "visual QA",
    ]
    for term in comparison_terms:
        require(term.lower() in comparison_lower, f"asset comparison chapter missing: {term}")

    generated_files = list(CHAPTERS.glob("**/*.html"))
    require(len(generated_files) == len(files), "chapter directory contains unexpected or missing html files")


if __name__ == "__main__":
    main()
