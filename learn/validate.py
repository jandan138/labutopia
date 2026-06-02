from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    require(INDEX.exists(), "learn/index.html must exist")
    html = INDEX.read_text(encoding="utf-8")

    required_phrases = [
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
        "中文解释",
        "English terms",
        "level1_pick",
        "Level4_CleanBeaker",
        "level5_Navigation",
    ]
    for phrase in required_phrases:
        require(phrase in html, f"missing required phrase: {phrase}")

    interactive_hooks = [
        "data-stepper",
        "data-config-tabs",
        "data-loop-demo",
        "data-boundary-switch",
        "data-dataset-visualizer",
        "data-glossary-search",
    ]
    for hook in interactive_hooks:
        require(hook in html, f"missing interactive hook: {hook}")

    source_links = [
        "https://arxiv.org/abs/2505.22634",
        "https://openreview.net/forum?id=AIOq1vWSgK",
        "https://rui-li023.github.io/labutopia-site/",
        "https://docs.isaacsim.omniverse.nvidia.com/5.1.0/",
        "https://openusd.org/docs/index.html",
        "https://arxiv.org/abs/2303.04137",
        "https://arxiv.org/abs/2304.13705",
        "https://hydra.cc/docs/",
    ]
    for link in source_links:
        require(link in html, f"missing source link: {link}")

    local_refs = [
        "main.py",
        "tasks/base_task.py",
        "controllers/base_controller.py",
        "data_collectors/data_collector.py",
        "policy/config/train_diffusion_unet_image_workspace.yaml",
    ]
    for ref in local_refs:
        require(ref in html, f"missing local code reference: {ref}")

    require("TODO" not in html, "tutorial should not contain TODO placeholders")
    require("TBD" not in html, "tutorial should not contain TBD placeholders")


if __name__ == "__main__":
    main()
