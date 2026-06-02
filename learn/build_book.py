from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parent


SOURCES = [
    ("LabUtopia arXiv", "https://arxiv.org/abs/2505.22634"),
    ("LabUtopia NeurIPS 2025 abstract", "https://proceedings.neurips.cc/paper_files/paper/2025/hash/313d6659e6532e6ba192dfb910d4261e-Abstract-Datasets_and_Benchmarks_Track.html"),
    ("LabUtopia project page", "https://rui-li023.github.io/labutopia-site/"),
    ("LabUtopia Dataset", "https://huggingface.co/datasets/Ruinwalker/Labutopia-Dataset"),
    ("EBench repository", "https://github.com/InternRobotics/EBench"),
    ("EBench docs", "https://internrobotics.github.io/EBench-doc/"),
    ("EBench-Assets", "https://huggingface.co/datasets/InternRobotics/EBench-Assets"),
    ("EBench-Dataset", "https://huggingface.co/datasets/InternRobotics/EBench-Dataset"),
    ("GenManip arXiv", "https://arxiv.org/abs/2506.10966"),
    ("Isaac Sim docs", "https://docs.isaacsim.omniverse.nvidia.com/latest/index.html"),
    ("Isaac Sim 5.1 docs", "https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/download.html"),
    ("OpenUSD introduction", "https://openusd.org/release/intro.html"),
    ("LeRobot docs", "https://huggingface.co/docs/lerobot/main/en/index"),
    ("Hydra docs", "https://hydra.cc/docs/intro/"),
    ("Diffusion Policy", "https://arxiv.org/abs/2303.04137"),
    ("Action Chunking Transformer", "https://arxiv.org/abs/2304.13705"),
]


def sec(
    sid: str,
    title: str,
    slug: str,
    lede: str,
    angle: str,
    walk: str,
    use: str,
    notes: list[str],
    paths: list[str] | None = None,
    widget: str | None = None,
    code: tuple[str, str, str] | None = None,
    source_keys: list[str] | None = None,
) -> dict:
    return {
        "id": sid,
        "title": title,
        "slug": slug,
        "lede": lede,
        "angle": angle,
        "walk": walk,
        "use": use,
        "notes": notes,
        "paths": paths or [],
        "widget": widget,
        "code": code,
        "source_keys": source_keys or [],
    }


PARTS = [
    {
        "id": "00-orientation",
        "title": "Part 0 · 先把整座实验室看成一张图",
        "kicker": "从只会点 Isaac Sim 到能读懂项目",
        "sections": [
            sec(
                "0-1",
                "为什么 LabUtopia 不是一个普通仿真 demo",
                "why-labutopia",
                "如果你只把 LabUtopia 当成一批 USD 场景，就会错过它真正的结构：它同时是 scientific embodied agents 的仿真环境、任务层级和数据生成入口。",
                "这份教程把项目当成一本书来拆。第一层是 <span class=\"term\">Isaac Sim</span> 与 <span class=\"term\">OpenUSD</span> 的世界观；第二层是 LabUtopia 论文里的 <span class=\"term\">LabSim</span>、<span class=\"term\">LabScene</span>、<span class=\"term\">LabBench</span>；第三层才是代码里的 <span class=\"term\">BaseTask</span>、<span class=\"term\">BaseController</span>、policy workspace 和 assets。读者如果有一点 RL 与 USD 资产基础，最容易卡住的不是概念，而是这些层之间的映射。",
                "本地代码显示，项目入口不是某个孤立 task，而是 <span class=\"term\">main.py</span> 中的 loop：启动 <span class=\"term\">SimulationApp</span>，创建 <span class=\"term\">World</span>，把配置里的 <span class=\"term\">usd_path</span> reference 到 <span class=\"term\">/World</span>，再让 task 提供 state、controller 产生 action。也就是说，LabUtopia 的“实验室”不是静态模型，而是一套从 USD 场景到 robot policy 的闭环。",
                "读这本教程时，先不要急着训练 policy。你要先能回答三个问题：场景从哪里进来，state 如何被整理，action 由谁执行。能回答这三个问题，再去看 <span class=\"term\">Diffusion Policy</span> 或 <span class=\"term\">Action Chunking Transformer</span>，就不会把 learning algorithm 和 simulation plumbing 混在一起。",
                ["把 LabUtopia 看成 benchmark/runtime/data 三者叠在一起，而不是单一 repo。", "中文解释负责建直觉；English terms 保留论文和代码真实命名。", "本书所有章节都尽量把论文术语落到本地文件路径。"],
                ["README.md", "main.py", "tasks/base_task.py", "controllers/base_controller.py"],
                widget="runtime-loop",
                source_keys=["LabUtopia arXiv", "LabUtopia project page"],
            ),
            sec(
                "0-2",
                "读者画像：从 RL 和 USD 点选经验出发",
                "reader-map",
                "这本书假设你知道 reward、policy、trajectory 这些 RL 词，也知道 Isaac Sim 里可以点开 USD stage，但还没有把 benchmark、dataset、controller 串起来。",
                "RL 背景给你一个很有用的类比：每个 episode 都像一次 rollout，task 负责提供 observation 和 terminal condition，controller 或 learned policy 负责 action。区别是 LabUtopia 目前大量 collect mode 由 rule/controller 驱动，它更像 imitation learning pipeline 的数据工厂，而不是端到端 RL trainer。",
                "USD 点选经验也有用。你知道 prim path、material、camera、reference 的存在，就能理解为什么配置里大量出现 <span class=\"term\">/World/...</span>、<span class=\"term\">usd_path</span> 和 camera prim。LabUtopia 的难点在于这些路径不是装饰，它们直接影响 object lookup、success check、data collection 和可复用性。",
                "所以本教程会反复把同一件事讲三遍：先用直觉讲一遍，再用本地代码路径讲一遍，最后用“如果迁移到 EBench 会怎样”讲一遍。这样你不只是会运行命令，还能判断改动会撞到哪一层 contract。",
                ["如果看到 unfamiliar term，先看 Appendix glossary，再回到当前章节。", "如果看到文件路径，建议直接在 IDE 中打开；章节不是 API 文档，而是阅读路线。", "如果你只关心资产迁移，可以先读 Part 6 和 Part 7。"],
                ["config/*.yaml", "assets/chemistry_lab", "assets/robots", "policy/config"],
            ),
            sec(
                "0-3",
                "本书目录如何组织",
                "book-map",
                "目录不是简单罗列文件，而是按“论文概念 → 仿真栈 → runtime → task/controller → data/policy → assets → EBench 对比”的依赖顺序展开。",
                "前半部分解决“LabUtopia 是什么”。Part 1 从论文抽象层讲 <span class=\"term\">LabSim</span>、<span class=\"term\">LabScene</span>、<span class=\"term\">LabBench</span>；Part 2 把它放回 <span class=\"term\">Isaac Sim</span>、<span class=\"term\">OpenUSD</span>、<span class=\"term\">PhysX</span>、<span class=\"term\">RTX Renderer</span> 的工程语境；Part 3 则从 <span class=\"term\">main.py</span> 的 runtime loop 讲清实际运行。",
                "中间部分解决“数据和策略从哪里来”。Part 4 拆 task/controller 的层级；Part 5 讲 HDF5 episode、language instruction、ACT 与 Diffusion Policy；Part 6 单独讲 LabUtopia assets，因为资产在这个项目里既是视觉内容，也是 task semantic 的来源。",
                "Part 7 是专门回应资产迁移问题：<span class=\"term\">EBench assets</span> 与 <span class=\"term\">LabUtopia assets</span> 的区别、关系、能否直接复用到 EBench、需要哪些 conversion workflow 和 visual QA。结论会很明确：不能直接复用，not plug-and-play，但可以经过适配后作为 source assets 进入新的 EBench/GenManip 任务。",
                ["每个章节页都有左侧目录、右侧本页索引和前后章节导航。", "交互 widget 只服务理解，不把书变成玩具。", "Appendix 保存命令、来源和术语，方便复查。"],
                ["learn/content.js", "learn/assets/js/book.js", "learn/assets/js/widgets/book-widgets.js"],
            ),
            sec(
                "0-4",
                "资料口径：哪些是论文事实，哪些是本地事实",
                "evidence-rules",
                "项目理解最怕把论文愿景、本地 README、外部 benchmark 文档和代码事实混成一句话。本书会把来源口径拆开。",
                "LabUtopia 的公开资料来自 arXiv、NeurIPS 2025 abstract、project page、Hugging Face dataset 和本地 README。它们告诉我们 LabUtopia 面向 scientific embodied agents，强调 high-fidelity simulation、hierarchical benchmark、scientific laboratory tasks，并在本地 README 中给出 <span class=\"term\">Isaac Sim 5.1</span>、Python 3.11、Ubuntu 24.04 的环境要求。",
                "EBench 的公开资料来自 GitHub、EBench docs、Hugging Face <span class=\"term\">EBench-Assets</span> 与 <span class=\"term\">EBench-Dataset</span>，以及 <span class=\"term\">GenManip</span> 论文。它们告诉我们 EBench 是基于 <span class=\"term\">Isaac Sim 4.1</span> 与 GenManip server 的 indoor VLA manipulation benchmark，核心本体是 <span class=\"term\">lift2</span> dual-arm mobile base。",
                "本地代码事实优先用于解释 LabUtopia repo 现在怎么跑：例如 task/controller factory、HDF5 数据保存、RMPFlow controller、navigation barrier image。外部资料优先用于解释 benchmark relation，而不是替本地代码编不存在的接口。",
                ["遇到版本冲突时，按“本地 README/代码事实”和“外部 EBench 文档事实”分别陈述。", "资产复用结论必须同时检查 simulation version、embodiment、task/eval contract、dataset format。", "所有外部来源统一放在 Appendix 参考资料。"],
                ["README.md", "README_CN.md", "/cpfs/shared/simulation/zhuzihou/dev/EBench/README.md"],
                source_keys=["LabUtopia NeurIPS 2025 abstract", "EBench repository", "EBench docs"],
            ),
        ],
    },
    {
        "id": "01-paper-model",
        "title": "Part 1 · 从论文模型建立 LabUtopia 心智地图",
        "kicker": "LabSim, LabScene, LabBench",
        "sections": [
            sec(
                "1-1",
                "LabSim：不是渲染器，而是实验闭环",
                "labsim-loop",
                "LabSim 可以先粗略理解为“让实验室任务真正动起来的 simulation runtime”，它把场景、物体、机器人、传感器和 episode loop 放进同一个执行语境。",
                "在论文语言里，<span class=\"term\">LabSim</span> 承载 high-fidelity simulation；在本地代码里，它落到 <span class=\"term\">SimulationApp</span>、<span class=\"term\">World</span>、USD reference、camera sensor、task/controller loop。这种对应关系很重要，因为你在代码里找不到一个叫 LabSim 的大类，但能看到它被拆成多个模块。",
                "如果你从 Isaac Sim 点选经验出发，LabSim 的关键不是“能看见一个 lab”，而是“每一步都能取到 robot state、camera image、object pose，并把 action 写回 articulation controller”。这正是 <span class=\"term\">task.step()</span> 与 <span class=\"term\">controller.step()</span> 在 main loop 中交替出现的意义。",
                "理解 LabSim 后，你会知道为什么本书不断强调 runtime loop。assets 只有进入 loop，才从模型文件变成可采集数据、可评估 success、可训练 policy 的 embodied environment。",
                ["LabSim 是运行时概念，不一定有同名源码目录。", "它的边界跨过 scene loading、sensor acquisition、physics stepping、control execution。", "从 RL 看，它提供 rollout 发生的 environment。"],
                ["main.py", "utils/camera_utils.py", "utils/object_utils.py"],
                widget="runtime-loop",
                source_keys=["LabUtopia arXiv"],
            ),
            sec(
                "1-2",
                "LabScene：scientific laboratory 的空间语义",
                "labscene-semantics",
                "LabScene 不是“漂亮的实验室背景”，而是把化学实验任务需要的 workspace、器材、台面、门抽屉、加热设备、导航障碍放进可引用的 USD hierarchy。",
                "本地 assets 体现了这个定位：<span class=\"term\">assets/chemistry_lab/lab_001/lab_001.usd</span>、<span class=\"term\">lab_003.usd</span>、<span class=\"term\">hard_task/Scene1_hard.usd</span> 和 <span class=\"term\">navigation_lab/navigation_lab_01/lab.usd</span> 分别服务 table-top manipulation、press/heat/stir、long-horizon hard task 与 navigation/mobile manipulation。",
                "场景语义通过 prim path 进入配置。比如 task config 中的 <span class=\"term\">obj_paths</span>、<span class=\"term\">target_path</span>、camera prim 和 material path，都是 LabScene 的接口。你在 Isaac Sim 里点一个物体，只是看到了 prim；在 LabUtopia 中，这个 prim 还可能决定 success predicate、data record 的 object_name 和 controller 的目标点。",
                "这也解释了为什么资产迁移不能只复制 USD。只要目标平台依赖不同 prim naming、robot reachability、collision schema 或 task scoring，LabScene 的语义就需要重新绑定。",
                ["LabScene 的核心是 semantic scene，而不是纯 geometry。", "USD path 是任务配置和运行时之间的桥。", "资产迁移时 prim path 稳定性比贴图是否漂亮更关键。"],
                ["assets/chemistry_lab", "assets/navigation_lab", "config/level4_CleanBeaker.yaml"],
                widget="asset-map",
            ),
            sec(
                "1-3",
                "LabBench：层级任务为什么要分 level",
                "labbench-levels",
                "LabBench 的价值在于把科学实验能力拆成层级：atomic skill、combined skill、generalization、long horizon、mobility，不同 level 让 failure diagnosis 更具体。",
                "本地 config 目录把这种层级变成可运行入口。<span class=\"term\">level1_pick.yaml</span>、<span class=\"term\">level1_pour.yaml</span>、<span class=\"term\">level1_stir.yaml</span> 代表 atomic task；<span class=\"term\">level2_PourLiquid.yaml</span> 与 <span class=\"term\">level2_TransportBeaker.yaml</span> 开始组合技能；<span class=\"term\">level4_CleanBeaker.yaml</span>、<span class=\"term\">level4_OpenTransportPour.yaml</span> 则把任务拉成长序列；<span class=\"term\">level5_Navigation.yaml</span> 和 <span class=\"term\">level5_Mobile_manipulation.yaml</span> 引入移动底盘。",
                "从 RL 看，level 不是难度标签那么简单。它改变 horizon、state distribution、failure mode 和 demonstration 数据的覆盖需求。一个 policy 在 level1 pick 上成功，不代表它能在 level4 clean beaker 中忍受中间步骤的微小误差。",
                "因此后续讲 controller 时，我们会把 level 当作 task decomposition 的线索，而不是文件名前缀。",
                ["Level 越高，episode horizon 和 state distribution 越复杂。", "Generalization task 通常通过 object/material/background/instruction variation 制造分布外条件。", "Mobile level 改变 robot embodiment 和 action space。"],
                ["config/level1_pick.yaml", "config/level4_CleanBeaker.yaml", "config/level5_Navigation.yaml"],
                widget="task-levels",
                source_keys=["LabUtopia arXiv"],
            ),
            sec(
                "1-4",
                "科学实验任务和 household manipulation 的根本差异",
                "science-vs-household",
                "LabUtopia 和 EBench 都在 Isaac Sim 语境里，但一个强调 scientific laboratory，一个强调 indoor/mobile manipulation。这个差异会一路影响资产、任务、动作和评测。",
                "科学实验任务通常要求器材身份、液体容器、加热/搅拌/清洗等步骤有明确语义。household manipulation 更强调家庭空间、日常物体、双臂移动操作和 VLA 对语言指令的泛化。二者都可视作 embodied agents benchmark，但它们不是同一批 assets 换名字。",
                "在 LabUtopia 本地仓库里，你会看到 beaker、glass rod、press、heat、clean 等 controller/task 命名；在 EBench 资料里，你会看到 <span class=\"term\">long_horizon</span>、<span class=\"term\">simple_pnp</span>、<span class=\"term\">teleop_tasks</span>，以及 <span class=\"term\">lift2</span> 的双臂移动本体和 4 个相机视角。",
                "这个差异不是“谁更好”，而是 benchmark contract 不同。教程后面判断资产是否能复用时，会从 contract 出发，而不是从视觉相似度出发。",
                ["Scientific lab assets 更依赖器材语义和实验步骤。", "Household/mobile benchmark 更依赖本体、导航、双臂协作和标准评测接口。", "跨 benchmark 迁移时要先问 contract，而不是先问 mesh。"],
                ["controllers/*beaker*.py", "/cpfs/shared/simulation/zhuzihou/dev/EBench/README.md"],
                source_keys=["EBench repository", "EBench-Dataset"],
            ),
            sec(
                "1-5",
                "指标和成功条件：别把 reward 想得太早",
                "metrics-success",
                "有 RL 背景的读者容易立刻找 reward function，但 LabUtopia 里更直接的入口是 task success condition、episode completion 和 data collection outcome。",
                "在 collect mode 中，controller 根据 state 推动作，并在任务完成时把 success 传给 <span class=\"term\">task.on_task_complete(is_success)</span>。<span class=\"term\">BaseController</span> 维护 <span class=\"term\">success_count</span>、<span class=\"term\">_episode_num</span>、failure reason；<span class=\"term\">BaseTask</span> 维护 reset flag、frame limit、object/material index。这些变量更像 benchmark bookkeeping，而不是 policy gradient 的 reward stream。",
                "当你开始训练 <span class=\"term\">Diffusion Policy</span> 或 <span class=\"term\">Action Chunking Transformer</span>，数据集里保存的是 demonstration trajectory：image、agent_pose、actions、language_instruction 和 task_properties。训练目标主要是 imitation loss，而不是 Bellman backup。",
                "这不是说 reward 不重要，而是本项目当前最容易读懂的评测入口在 controller/task 的 success 逻辑。先把 success contract 看清，再谈学出来的 policy 为什么失败。",
                ["先看 success predicate，再看 training loss。", "Data collection 成功率是数据质量信号，不等价于 learned policy 的最终泛化。", "Long-horizon task 的 failure reason 比单一 success rate 更有诊断价值。"],
                ["controllers/base_controller.py", "tasks/base_task.py", "data_collectors/data_collector.py"],
            ),
        ],
    },
    {
        "id": "02-sim-usd",
        "title": "Part 2 · Isaac Sim 与 OpenUSD 基础",
        "kicker": "把点选经验变成工程理解",
        "sections": [
            sec(
                "2-1",
                "SimulationApp, World, Stage 三件事",
                "simulationapp-world-stage",
                "LabUtopia 的第一行关键代码不是 robot，也不是 task，而是 <span class=\"term\">SimulationApp</span>。它决定 Isaac Sim runtime 能否启动，后面的 World 与 Stage 都在它之后才有意义。",
                "<span class=\"term\">SimulationApp</span> 是应用级入口，负责加载 Omniverse/Isaac Sim 扩展、渲染和物理 runtime。<span class=\"term\">World</span> 是 Isaac Sim core API 里的 simulation wrapper，管理 physics step、reset、play/stop 状态。<span class=\"term\">Stage</span> 则是 OpenUSD 场景图，里面有 prim、reference、material、camera、robot articulation。",
                "本地 <span class=\"term\">main.py</span> 的顺序正好体现这个关系：先创建 SimulationApp，再 import Isaac Sim 相关模块，之后创建 World，获取 stage，然后用 <span class=\"term\">add_reference_to_stage</span> 把配置里的 USD 加到 <span class=\"term\">/World</span>。这也是很多 Isaac Sim 项目要求“先启动 SimulationApp 再 import omni”的原因。",
                "从 GAMES103 看，World.step 就像推进一次物理系统；从 USD 看，Stage 是状态的可编辑数据库；从 policy 看，二者共同产生下一步 observation。",
                ["SimulationApp 是应用 runtime。", "World 是 simulation stepping wrapper。", "Stage 是 USD scene graph。"],
                ["main.py"],
                code=("python", "main.py", "simulation_app = SimulationApp(simulation_config)\nworld = World(stage_units_in_meters=1.0, physics_prim_path=\"/physicsScene\", backend=\"numpy\")\nstage = omni.usd.get_context().get_stage()\nadd_reference_to_stage(usd_path=os.path.abspath(cfg.usd_path), prim_path=\"/World\")"),
                source_keys=["Isaac Sim docs", "OpenUSD introduction"],
            ),
            sec(
                "2-2",
                "OpenUSD：prim path 为什么像 API",
                "openusd-prim-path",
                "在 LabUtopia 里，USD 的 prim path 不只是 UI 中的树节点名字，它实际承担了对象寻址、camera 初始化、material binding 和 success check 的 API 角色。",
                "OpenUSD 的核心是 stage/layer/prim/composition。你可以把 stage 想成场景数据库，把 prim path 想成数据库 key。LabUtopia 的 task config 把 object path、target path、camera prim path 写进 YAML，运行时用 <span class=\"term\">stage.GetPrimAtPath</span> 查询它们是否存在，然后把位置、尺寸、语义或材质绑定到这些 prim 上。",
                "这解释了为什么同一个 mesh 换了路径，代码可能就坏。比如 <span class=\"term\">BaseTask.setup_cameras</span> 会先检查 camera prim 是否有效；<span class=\"term\">apply_material_to_object</span> 会用 target path 找 prim，再用 <span class=\"term\">UsdShade.MaterialBindingAPI</span> 绑定材质。路径错了，不是视觉小问题，而是 runtime contract 断了。",
                "资产迁移到 EBench 时也会遇到同样问题。EBench/GenManip 的 task config 和 scoring 期待另一套 scene semantics；LabUtopia 的 prim path 不能默认被对方理解。",
                ["Prim path 是 contract，不是标签。", "Reference 到 /World 后，路径会影响所有 lookup。", "迁移资产前先做 path inventory。"],
                ["tasks/base_task.py", "config/level1_pick.yaml", "assets/chemistry_lab/lab_001/lab_001.usd"],
                source_keys=["OpenUSD introduction"],
            ),
            sec(
                "2-3",
                "PhysX 与 articulation：动作怎么变成运动",
                "physx-articulation",
                "你在 policy 里看到的是 action array，但 Isaac Sim 里真正动起来的是 robot articulation、joint target、gripper command 和 physics step。",
                "LabUtopia 的 controller 输出 action 后，<span class=\"term\">main.py</span> 调用 <span class=\"term\">robot.get_articulation_controller().apply_action(action)</span>。这一步把高层 controller 的结果交给 Isaac Sim articulation controller，随后 World.step 推进物理和渲染。对于 Franka，项目还使用 <span class=\"term\">RMPFlowController</span> 和 trajectory controller 来生成更平滑的末端运动。",
                "从 GAMES103 看，articulation 是带约束的多刚体系统；从 RL 看，它是 action 被 environment 接收后的 dynamics。你不需要一开始就懂 PhysX SDK 的所有细节，但要知道：action 不是直接“瞬移物体”，而是作用在关节/末端控制接口上，经过物理和碰撞后才进入下一帧 state。",
                "这也是为什么资产 collision、scale、mass、joint limit 会影响 policy 数据质量。一个 USD 看起来正确，不代表 articulation 和 collision 都适合采集 demonstration。",
                ["Action array 必须匹配 robot articulation/control mode。", "Physics step 后 observation 才有意义。", "资产 QA 要检查 collision 和 articulation，不只看 render。"],
                ["controllers/robot_controllers/trajectory_controller.py", "robots/franka/rmpflow_controller.py", "main.py"],
                source_keys=["Isaac Sim docs"],
            ),
            sec(
                "2-4",
                "RTX Renderer 与 cameras：数据集里的 image 从哪里来",
                "rtx-cameras",
                "LabUtopia 的 image observation 来自 Isaac Sim camera sensor，而不是事后截图。camera 配置决定了训练数据的视角、分辨率、image type 和可见信息。",
                "<span class=\"term\">BaseTask.setup_cameras</span> 会按 YAML 中的 camera config 创建或绑定 camera prim，设置 resolution、focal_length、orientation 和 clipping range。随后 <span class=\"term\">process_camera_image</span> 根据 image_type 取 rgb、depth、pointcloud、segmentation 等数据，并拆成 record data 与 display data。",
                "这对 policy 很关键。ACT/Diffusion Policy 的 observation encoder 不是抽象地“看世界”，而是吃具体 camera tensor。换 camera resolution、视角、image type，都会改变 dataset shape_meta 和模型输入分布。对 EBench 来说，lift2 固定有 top/left/right/overlook 等视角；LabUtopia 本地 config 多数是 3 个 camera，二者不能直接混用。",
                "因此 debug policy 时，第一件事不是调 learning rate，而是确认 camera 数据是否稳定、无遮挡、尺寸和训练配置一致。",
                ["Camera config 是 dataset contract 的一部分。", "Display image 和 record image 在代码里分开处理。", "跨 benchmark 复用数据时，view naming 和 tensor shape 必须重建。"],
                ["tasks/base_task.py", "utils/camera_utils.py", "policy/config/task/dp.yaml"],
                source_keys=["Isaac Sim docs"],
            ),
            sec(
                "2-5",
                "版本现实：Isaac Sim 5.1 与 4.1 的差别要认真对待",
                "version-reality",
                "LabUtopia 本地 README 要求 <span class=\"term\">Isaac Sim 5.1</span>，而 EBench/GenManip 资料使用 <span class=\"term\">Isaac Sim 4.1</span>。资产复用时，这不是小版本洁癖。",
                "Isaac Sim 版本变化可能影响 extension 名称、USD schema、physics behavior、material rendering、sensor API、Python package layout 和依赖版本。LabUtopia 现在安装 <span class=\"term\">isaacsim[all,extscache]==5.1.0</span>；EBench 的 runtime 由 GenManip server 管理，文档口径是 Isaac Sim 4.1.0、CUDA 12.1、torch 2.4.0。",
                "这意味着直接把 LabUtopia USD 拿到 EBench server 中打开，可能遇到材料丢失、physics schema 不兼容、prim reference 断开、控制器找不到路径等问题。反过来，把 EBench assets 放进 LabUtopia 也需要适配 local task/controller contract。",
                "本书 Part 7 的复用结论会把版本差异放在第一层风险，而不是最后才提。",
                ["Version mismatch 是资产迁移风险。", "先在目标 Isaac Sim 版本中打开和检查 USD，再写 task。", "不要用本机能打开来证明 EBench server 能跑。"],
                ["README.md", "/cpfs/shared/simulation/zhuzihou/dev/EBench/learn/_AGENT_BRIEF.md"],
                widget="version-bridge",
                source_keys=["Isaac Sim docs", "EBench docs"],
            ),
        ],
    },
    {
        "id": "03-runtime",
        "title": "Part 3 · Runtime Architecture",
        "kicker": "从 main.py 读懂一次 episode",
        "sections": [
            sec(
                "3-1",
                "Hydra config 是整条链的入口",
                "hydra-config-entry",
                "LabUtopia 的 task 不是在命令行里硬编码出来的，而是由 Hydra config 决定 task_type、controller_type、usd_path、robot、camera 和 collect/infer mode。",
                "<span class=\"term\">main.py</span> 用 <span class=\"term\">hydra.initialize</span> 和 <span class=\"term\">hydra.compose</span> 读取 <span class=\"term\">--config-name</span>。这份 cfg 随后被保存到 run_dir，成为一次实验的 provenance。你在 config 里改 <span class=\"term\">usd_path</span>，就换场景；改 <span class=\"term\">robot.type</span>，就换 factory 创建的机器人；改 <span class=\"term\">mode</span>，BaseController 初始化 collect 或 infer 分支。",
                "从工程角度看，Hydra config 是 LabUtopia 的 experiment contract。它把 Python class 的组合关系外置，让同一套 runtime 可以运行不同 level task。读项目时不要从 controller 文件海洋开始，而要先看 config，找到它指定的 task/controller/asset。",
                "这也解释了为什么 assets chapter 会频繁引用 config：资产不是孤立目录，而是 cfg.usd_path 和 prim paths 引入 runtime。",
                ["先读 config，再读 factory，再读具体 task/controller。", "run_dir 中保存 config.yaml，方便复现实验。", "Hydra resolver 用于训练配置里的动态表达式。"],
                ["main.py", "config/level1_pick.yaml", "policy/config/train_diffusion_unet_image_workspace.yaml"],
                code=("bash", "Collect one task", "python main.py --config-name level1_pick\npython main.py --config-name level4_CleanBeaker --headless --no-video"),
                source_keys=["Hydra docs"],
            ),
            sec(
                "3-2",
                "Factory pattern：字符串如何变成 class",
                "factory-pattern",
                "配置里写的是 task_type 和 controller_type，但运行时需要具体 Python class。LabUtopia 用 factory 把这一步集中管理。",
                "<span class=\"term\">create_robot</span>、<span class=\"term\">create_task</span>、<span class=\"term\">create_controller</span> 分别根据 cfg 的字符串创建对象。这样做的好处是 main loop 不需要知道 pick、pour、navigation、cleanbeaker 的细节；缺点是新任务如果没有注册到 factory，会在运行时才暴露。",
                "从阅读路线看，factory 是你查找具体实现的索引。看到 <span class=\"term\">controller_type: \"pickpour\"</span>，就去 controller factory 找映射，再读 <span class=\"term\">controllers/pickpour_controller.py</span>。看到 <span class=\"term\">task_type: \"navigation\"</span>，就去 task factory 找到 <span class=\"term\">tasks/navigation_task.py</span>。",
                "这类模式在 benchmark 项目里很常见，因为任务数量多，但 runtime loop 应该稳定。你改 factory 就是在扩大支持的 task vocabulary。",
                ["Factory 让 main.py 不随 task 数量膨胀。", "新增 task 要同时补 config、task class、controller class、factory mapping。", "迁移到 EBench 时，GenManip 的 task registry 会成为对应位置。"],
                ["factories/task_factory.py", "factories/controller_factory.py", "factories/robot_factory.py"],
            ),
            sec(
                "3-3",
                "Task/Controller boundary：谁看世界，谁做动作",
                "task-controller-boundary",
                "LabUtopia 的 README 已经给出设计哲学：scene state 和 observation acquisition 由 tasks 处理，robot control 与 success condition checking 由 controllers 处理。",
                "<span class=\"term\">BaseTask</span> 负责 cameras、objects、materials、state dict。它知道如何从 stage 中读取 object position、size、camera frame，也知道什么时候需要 reset。<span class=\"term\">BaseController</span> 负责把 state 变成 action，管理 collect/infer mode、RMPFlow、DataCollector、episode count 和 failure reason。",
                "这个边界对初学者很有帮助。你看到一个 bug，如果是 camera image 为空、object path 找不到、material 没绑定，优先看 task；如果是 robot 不动、动作顺序错、success 统计异常，优先看 controller。不要一上来全局搜索。",
                "从 RL 看，task 更像 environment observation wrapper，controller 更像 expert policy 或 learned policy adapter。二者之间的接口就是 state dict。",
                ["Task owns sensing and scene bookkeeping。", "Controller owns action generation and episode policy。", "State dict 是二者之间的 contract。"],
                ["tasks/base_task.py", "controllers/base_controller.py"],
                widget="task-boundary",
            ),
            sec(
                "3-4",
                "一次 world.step 到底发生什么",
                "one-world-step",
                "main loop 的每一轮都先 <span class=\"term\">world.step(render=True)</span>，然后根据 world 状态、reset flag、task state 和 controller action 决定下一步。",
                "如果 world stopped，controller 需要 reset；如果 world playing，程序先检查 controller 或 task 是否需要 reset。reset 分支会释放 video writer、重置 controller、判断 episode 数是否达到 cfg.max_episodes、再重置 task。非 reset 分支才调用 <span class=\"term\">task.step()</span> 取 state。",
                "拿到 state 后，controller 返回 <span class=\"term\">action, done, is_success</span>。如果 action 存在，articulation controller 应用动作；如果 done，打印 failure reason 并调用 <span class=\"term\">task.on_task_complete(is_success)</span>。最后，若开启视频，程序把 camera_display 拼成一张 OpenCV 画面并写入 mp4。",
                "这条线解释了为什么一些 failure 看起来“延迟一帧”。物理、状态读取、动作应用、completion 标记不是同一瞬间发生，而是在 loop 的不同位置。",
                ["先 step physics/render，再处理 task/controller。", "reset branch 会跳过当前轮的 action。", "video 写入使用 display data，不一定等同训练记录。"],
                ["main.py"],
                widget="runtime-loop",
            ),
            sec(
                "3-5",
                "ObjectUtils 与 scene query",
                "object-utils",
                "LabUtopia 很多任务都需要知道物体中心、尺寸、位置和可见性，这些 scene query 被集中在 ObjectUtils 和 task helper 中。",
                "<span class=\"term\">ObjectUtils.get_instance(stage)</span> 在 main.py 中初始化，之后 task/controller 可以通过 singleton 访问 stage。<span class=\"term\">BaseTask.get_basic_state_info</span> 用它读取 object geometry center 和 object size；<span class=\"term\">randomize_object_position</span> 与 <span class=\"term\">place_objects_with_visibility_management</span> 用它移动对象并管理可见性。",
                "这种设计让 task 可以处理 object variation 和 material variation。比如 generalization task 可以在 episode 之间切换 object/material，使 policy 不只记住一个固定物体。",
                "注意 singleton 带来的隐含依赖：如果 stage 没初始化，或迁移到另一个 runtime，ObjectUtils 的调用就可能失效。资产复用时也要重新验证 object center 计算是否适用于新 mesh/collision。",
                ["Scene query 是 success check 和 data record 的基础。", "Object randomization 依赖 prim path 有效。", "Singleton 方便，但也让 runtime stage 成为隐式依赖。"],
                ["utils/object_utils.py", "tasks/base_task.py"],
            ),
            sec(
                "3-6",
                "Collect mode 与 infer mode",
                "collect-infer-mode",
                "同一个 controller base 同时支持 collect 和 infer，这让 LabUtopia 既能生成 demonstration，也能把训练好的 policy 放回 simulation 中测试。",
                "在 <span class=\"term\">collect</span> mode 下，BaseController 创建 <span class=\"term\">DataCollector</span>，controller 通常按规则或运动规划生成动作，并把 trajectory 写入 HDF5。 在 <span class=\"term\">infer</span> mode 下，BaseController 创建 <span class=\"term\">FrankaTrajectoryController</span> 和 <span class=\"term\">InferenceEngine</span>，由 local/remote/replay engine 提供动作。",
                "这条分支的意义是把“专家数据采集”和“模型部署评测”放在同一 runtime 中。它比单独写一个 offline trainer 更有价值，因为你可以回到相同 scene、camera 和 robot contract 下看 policy 是否真的能执行。",
                "从调试角度，mode 错了会导致完全不同的错误。collect mode 没有模型推理，infer mode 则需要 checkpoint、shape_meta、trajectory controller 与 inference engine 全部匹配。",
                ["collect 生成数据，infer 消耗模型。", "local/remote/replay 是 inference engine 的三种入口。", "同一 config 改 mode 不代表所有参数都自动适配。"],
                ["controllers/base_controller.py", "controllers/inference_engines", "policy/config"],
                widget="mode-switch",
            ),
        ],
    },
    {
        "id": "04-tasks",
        "title": "Part 4 · Tasks 与 Controllers",
        "kicker": "从 level1 到 level5",
        "sections": [
            sec(
                "4-1",
                "Level1 atomic skill：pick/place/pour/stir 的意义",
                "level1-atomic",
                "Level1 task 看似简单，却是理解所有高阶任务的基础。它们把一个动作技能拆到足够短，让你能定位 robot、object、camera、success condition 哪一层出错。",
                "本地 Level1 包含 pick、place、open/close door/drawer、pour、press、shake、stir 等配置。它们通常使用 Franka 和 chemistry lab 场景，episode horizon 较短，controller 逻辑也更直接。对初学者来说，先跑 <span class=\"term\">level1_pick</span> 比直接跑 long-horizon task 更适合建立 debug 感。",
                "从 data perspective 看，atomic skill demonstration 是组合任务的素材。即使未来用 VLA 或 Diffusion Policy，也要知道模型学到的动作 chunk 其实来自这些低层数据分布。",
                "如果你想验证环境，建议先从 Level1 开始：camera 是否有图、robot 是否能动、object path 是否正确、HDF5 是否写出。",
                ["Atomic task 是 debugging unit。", "短 horizon 降低 compounding error。", "它们为组合技能提供动作和视觉分布。"],
                ["config/level1_pick.yaml", "controllers/pick_controller.py", "tasks/pick_task.py"],
                widget="task-levels",
            ),
            sec(
                "4-2",
                "Level2 combined skill：组合不是简单相加",
                "level2-combined",
                "Level2 把多个 atomic skill 接起来，例如 pick 后 pour、place 后 press、transport beaker、openclose。组合的难点不只是多了步骤，而是中间状态成为下一步的初始条件。",
                "以 <span class=\"term\">level2_PourLiquid.yaml</span> 为例，task_type 是 pickpour，controller_type 可能是 pickpour 或 pour。controller 不再只追一个目标，而要管理阶段切换：靠近、抓取、移动、倾倒、退出。每个阶段的误差都会改变下一阶段的可达性。",
                "这就是 RL 中 compounding error 的直观版本。一个 atomic controller 在单步环境中成功，组合后可能因为对象位置轻微偏移而失败。对于 imitation learning，Level2 数据能让模型看到更多阶段转换，但也要求 action annotation 更稳定。",
                "读 Level2 时，重点看 controller 内部状态机，而不是只看 config 名字。",
                ["组合任务的关键是 phase transition。", "中间 object pose 是下一阶段的 condition。", "Controller state machine 是阅读重点。"],
                ["config/level2_PourLiquid.yaml", "controllers/pickpour_controller.py", "tasks/pickpour_task.py"],
            ),
            sec(
                "4-3",
                "Level3 generalization：object/material/instruction 的变化",
                "level3-generalization",
                "Level3 让任务不再只围绕一个固定对象或材质。它通过 object list、position range、material_paths、inference test material 等机制制造泛化压力。",
                "<span class=\"term\">BaseTask.setup_objects</span> 会收集 cfg.task.obj_paths，<span class=\"term\">update_object_and_material_indices</span> 在成功 episode 后轮换 object/material。<span class=\"term\">setup_materials</span> 还区分 collect/infer 和 is_test_material，让测试时可以使用不同 material set。",
                "这对 policy training 很关键。模型如果只在一个颜色/材质/背景下训练，视觉 encoder 很容易学到捷径；Level3 的意义是让 data distribution 更接近 benchmark 对泛化的要求。",
                "从 USD 资产角度，material path 和 object path 一样都是 contract。材质不兼容、绑定失败或 test_materials 缺失，都会让所谓 generalization 实验失真。",
                ["Generalization 不只是换 prompt。", "Material binding 使用 UsdShade，需要 target/material prim 都有效。", "Train/test material split 要在 config 中显式表达。"],
                ["tasks/base_task.py", "config/level3_pick.yaml", "config/level3_HeatLiquid.yaml"],
            ),
            sec(
                "4-4",
                "Level4 long horizon：CleanBeaker 作为案例",
                "level4-cleanbeaker",
                "Long-horizon task 最适合暴露 embodied agents 的真实短板：不是不会抓，而是步骤多、误差积累、状态切换和成功条件都更脆弱。",
                "<span class=\"term\">level4_CleanBeaker.yaml</span> 使用 <span class=\"term\">assets/chemistry_lab/hard_task/Scene1_hard.usd</span>，controller_type 是 cleanbeaker。它不是单一动作，而是科学实验语境中的连续过程：定位器材、拿取、移动、清洗或相关操作、判断完成。",
                "从 policy 角度，long horizon 会放大 covariate shift。ACT 的 action chunking 和 Diffusion Policy 的 receding horizon 都试图缓解这个问题，但前提是 demonstration 数据覆盖了合理的中间状态。",
                "读 CleanBeaker controller 时，不要只看最终 success。要记录每个 phase 的进入条件、目标 prim、末端位姿和 failure reason，这些才是训练失败后能解释现象的线索。",
                ["Long horizon 的主要风险是 phase drift。", "Hard task scene 与普通 lab scene 不同，asset path 也不同。", "失败诊断要按阶段记录。"],
                ["config/level4_CleanBeaker.yaml", "tasks/cleanbeaker_task.py", "controllers/cleanbeaker_controller.py"],
                source_keys=["Action Chunking Transformer", "Diffusion Policy"],
            ),
            sec(
                "4-5",
                "Level5 mobility：navigation 与 mobile manipulation",
                "level5-mobility",
                "Level5 引入移动底盘，LabUtopia 从 table-top manipulation 进入 navigation/mobile manipulation，robot type 也从 Franka 切到 ridgebase。",
                "<span class=\"term\">level5_Navigation.yaml</span> 使用 navigation lab USD，并通过 <span class=\"term\">assets/navigation/barrier/lab_1.png</span> 表示障碍地图。<span class=\"term\">NavigationTask</span> 与 <span class=\"term\">NavigationController</span> 使用 A* 相关工具和 ridgebase controller，让 base motion 成为任务的一部分。",
                "Mobile manipulation 的难点在于 action space 和 observation 都变了。Franka 桌面任务主要关注 arm/gripper；ridgebase_franka 还要处理 base pose、路径规划和移动过程中的 camera distribution。这个变化与 EBench 的 lift2 mobile base 有概念关系，但本体和接口不同。",
                "因此不要把 LabUtopia Level5 直接等同于 EBench mobile_manip。二者都是 mobile manipulation，但 embodiment、camera、server/eval contract 完全不同。",
                ["Mobility 改变 action space 和 state distribution。", "Barrier image 是 navigation 任务的资产之一。", "与 EBench lift2 有概念相似性，但不能直接互换。"],
                ["config/level5_Navigation.yaml", "tasks/navigation_task.py", "controllers/navigation_controller.py", "assets/navigation/barrier/lab_1.png"],
                widget="task-levels",
            ),
            sec(
                "4-6",
                "Atomic controllers 与高阶 controller 的关系",
                "atomic-to-composite",
                "controllers/atomic_actions 里有 move、pick、place、pour、press、shake、stir 等低层控制器，高阶 controller 往往把这些动作组合成任务阶段。",
                "这是一种 pragmatic 的 hierarchy。底层 atomic controller 负责一个短动作的几何与控制，高层 controller 负责阶段顺序、语言指令、success check 和数据写入。它不像 hierarchical RL 那样训练 option policy，但工程结构上有类似分层思想。",
                "对读代码很实用：如果 robot 在某个阶段动作异常，先确认高阶 controller 是否调用了正确 atomic action，再进入 atomic controller 看目标位姿、gripper 状态和阈值。这样比从 main loop 追到底更快。",
                "对资产迁移也重要。一个 beaker mesh 能不能进入新 benchmark，还取决于对应 atomic action 是否能抓、能倒、能放，collision 和 geometry center 是否支持这些动作。",
                ["Atomic action 是 controller 复用单元。", "高阶 controller 是任务状态机。", "资产可复用性要通过 atomic action 执行验证。"],
                ["controllers/atomic_actions", "controllers/pickpour_controller.py", "controllers/opentransportpour_controller.py"],
                widget="task-boundary",
            ),
        ],
    },
    {
        "id": "05-data-policy",
        "title": "Part 5 · Data 与 Policy",
        "kicker": "从 HDF5 episode 到 learned action",
        "sections": [
            sec(
                "5-1",
                "DataCollector：episode 如何写成 HDF5",
                "data-collector",
                "LabUtopia 的 demonstration 数据不是随手存几张图，而是按 episode 写入 HDF5，并在 meta/episode.jsonl 中记录任务文本和长度。",
                "<span class=\"term\">DataCollector</span> 初始化时根据 camera config 建立临时缓存；每个 step 缓存 camera image、joint angle 和 language instruction；episode 结束时用 ProcessPoolExecutor 异步写入 <span class=\"term\">episode_0000.h5</span>。HDF5 中包含 camera dataset、<span class=\"term\">agent_pose</span>、<span class=\"term\">actions</span>、<span class=\"term\">language_instruction</span> 和 <span class=\"term\">task_properties</span>。",
                "注意 actions 的构造：代码用 agent_pose[1:] 加 final_joint_positions 形成下一步动作标签。这是一种 imitation learning 常见对齐方式，表示在当前 observation 后应该到达的下一状态/关节目标。",
                "如果训练效果差，先检查数据文件：相机 dataset shape 是否一致，agent_pose/actions 长度是否匹配，language_instruction 是否写入，episode.jsonl 是否和 HDF5 文件对应。",
                ["HDF5 是 LabUtopia 本地数据格式核心。", "Camera dataset key 由 camera name 和 image_type 拼成。", "异步写入提升性能，但 close 时必须等待 future 完成。"],
                ["data_collectors/data_collector.py"],
                widget="dataset-flow",
            ),
            sec(
                "5-2",
                "Language instruction：文字不是装饰",
                "language-instruction",
                "对于 VLA 或 language-conditioned imitation learning，language_instruction 是 observation 的一部分，不只是日志里的一句话。",
                "<span class=\"term\">BaseController</span> 提供 language_instruction property，DataCollector 会把它写入 HDF5。训练时，具体 dataset class 再把 instruction 与 image/low_dim state 一起组织给 policy。对于只训练低层控制的任务，语言可能看似多余；但一旦做多任务或泛化，它就是区分任务意图的关键。",
                "从论文阅读习惯看，VLA 的 L 不只是 prompt。它影响模型如何在相同视觉状态下选择不同动作，例如拿 beaker、倒液体、打开抽屉可能共享相似视觉，但目标不同。",
                "调试语言条件时，别只看字符串是否存在，还要看多任务数据中 instruction 是否有足够多样性，是否和 task_properties、object_name 对齐。",
                ["Language instruction 是 policy input contract。", "多任务训练时，prompt ambiguity 会直接造成 action ambiguity。", "EBench-Dataset 的 meta/tasks.jsonl 也体现多 instruction paraphrase 的重要性。"],
                ["controllers/base_controller.py", "data_collectors/data_collector.py", "policy/dataset"],
                source_keys=["EBench-Dataset"],
            ),
            sec(
                "5-3",
                "ACT：Action Chunking Transformer 为什么适合长序列",
                "act-action-chunking",
                "Action Chunking Transformer 的核心直觉是：不要每一步都重新预测一个动作，而是一次预测未来一段 action chunk，减少 compounding error。",
                "在 imitation learning 中，单步 policy 很容易因为一点误差进入训练集中少见的状态；随后误差会继续放大。<span class=\"term\">Action Chunking Transformer</span> 通过预测 H 个未来动作，把有效决策次数变少，并让动作更平滑。LabUtopia 的 policy 目录中有 <span class=\"term\">act_image_policy</span> 和对应 training workspace。",
                "这和 LabUtopia long-horizon task 的关系很直接。CleanBeaker 这类任务不是每一步都需要全局重新规划；很多阶段需要连续稳定执行。action chunking 能让模型在短时间内保持一致意图，但也带来反应慢的问题，所以通常配合 receding horizon。",
                "读 ACT 配置时，关注 observation shape、action dim、chunk size、temporal aggregation/trajectory horizon，而不是只看 transformer 名字。",
                ["ACT 解决的是 sequential imitation 的 covariate shift。", "Action chunk 越长越平滑，但对突发状态反应越慢。", "长序列任务要平衡 horizon 与 replan frequency。"],
                ["policy/policy/act_image_policy.py", "policy/workspace/train_act_image_workspace.py", "policy/config/train_act_image_workspace.yaml"],
                widget="action-chunking",
                source_keys=["Action Chunking Transformer"],
            ),
            sec(
                "5-4",
                "Diffusion Policy：连续动作分布的另一种写法",
                "diffusion-policy",
                "Diffusion Policy 把 robot action 看成条件生成问题：给定 image/state/language observation，逐步从噪声中生成连续 action trajectory。",
                "LabUtopia 的 <span class=\"term\">train_diffusion_unet_image_workspace.yaml</span> 配置了 noise_scheduler、multi image observation encoder、conditional UNet 以及训练参数。它不是 value-based RL，没有 Q function 或 Bellman target；训练目标是让模型复现 demonstration action distribution。",
                "对于科学实验任务，动作往往存在多模态：同样拿一个 beaker，可以从略不同路径靠近，只要最终稳定抓取。简单 MSE 回归可能学到平均动作，而 diffusion/flow 类方法更适合表达分布。",
                "不过 Diffusion Policy 对数据质量很敏感。camera view 不稳定、actions 对齐错误、episode 中夹杂失败动作，都会被模型认真学进去。",
                ["Diffusion Policy 是 behavior cloning 的生成式策略。", "Noise scheduler 和 action horizon 是核心超参。", "数据清洁程度直接影响生成策略质量。"],
                ["policy/config/train_diffusion_unet_image_workspace.yaml", "policy/policy/diffusion_unet_image_policy.py", "policy/model/diffusion/conditional_unet1d.py"],
                widget="dataset-flow",
                source_keys=["Diffusion Policy"],
            ),
            sec(
                "5-5",
                "训练 workspace：Hydra 到 BaseWorkspace",
                "training-workspace",
                "训练入口 <span class=\"term\">train.py</span> 很短，但它背后依赖 Hydra 根据配置实例化 workspace，再由 workspace 组织 dataset、policy、optimizer、checkpoint 和 validation。",
                "<span class=\"term\">train.py</span> 读取 policy/config 下的 YAML，解析 <span class=\"term\">cfg._target_</span>，用 <span class=\"term\">hydra.utils.get_class</span> 找到 workspace class，并调用 <span class=\"term\">workspace.run()</span>。这让 ACT 和 Diffusion Policy 可以共享训练入口，但使用不同 workspace。",
                "对初学者来说，训练报错通常不是 train.py 本身，而是 cfg 中的 dataset_path、shape_meta、policy target、obs key 与真实 HDF5 数据不一致。先用小 batch 打印 dataset sample，比盲目调模型更有效。",
                "把训练和 simulation 分开理解也很重要：main.py 负责生成/运行 episode，train.py 负责离线训练。infer mode 才把训练好的模型带回 simulation。",
                ["train.py 是 dispatcher，不是训练算法主体。", "cfg._target_ 决定实际 workspace。", "Dataset path 和 shape_meta 是最常见错配点。"],
                ["train.py", "policy/workspace", "policy/config/task/dp.yaml", "policy/config/task/act.yaml"],
                code=("bash", "Training entry", "python train.py --config-name=train_diffusion_unet_image_workspace\npython train.py --config-name=train_act_image_workspace"),
                source_keys=["Hydra docs"],
            ),
        ],
    },
    {
        "id": "06-assets",
        "title": "Part 6 · LabUtopia Assets",
        "kicker": "USD, MDL, robots, navigation",
        "sections": [
            sec(
                "6-1",
                "资产树总览：471 个文件如何服务任务",
                "asset-tree",
                "LabUtopia 本地 assets 不是巨型外部数据包，而是一组随 repo 管理的 USD/MDL/texture/robot/navigation 资产，直接被 config 引用。",
                "本地统计显示 <span class=\"term\">assets</span> 目录约 471 个文件、0.34 GB，主要扩展名包括 <span class=\"term\">.mdl</span>、<span class=\"term\">.jpg</span>、<span class=\"term\">.png</span>、<span class=\"term\">.usd</span>、<span class=\"term\">.urdf</span>、<span class=\"term\">.yaml</span>。这说明 LabUtopia assets 的重点是 scene USD、materials/textures 和 robot descriptions，而不是像大型 benchmark asset hub 那样外置几 GB 数据。",
                "这些资产通过 config 的 usd_path 进入 runtime。绝大多数 manipulation task 使用 chemistry_lab 下的 lab_001 或 lab_003；Level4 使用 hard_task；Level5 使用 navigation_lab。机器人资产包含 Franka、ridgeback_franka 和 Fetch 相关文件。",
                "理解资产树后，读 config 就有画面感：看到 lab_003，你会想到 press/heat/stir 类任务；看到 navigation_lab，你会想到 ridgebase 和 barrier map。",
                ["资产目录小而直接，和本地 config 强绑定。", "MDL/JPG/PNG 表明材料系统在视觉真实性里占比很高。", "USD root 文件数量不多，但每个承载不同 task family。"],
                ["assets", "assets/properties.json", "config/*.yaml"],
                widget="asset-map",
            ),
            sec(
                "6-2",
                "Lab object assets：真实实验室物体对应哪些 USD",
                "asset-census",
                "这一页只回答一个更具体的问题：实验室里真实出现的物体，分别落在哪个 scene USD 和哪个 /World prim path 上。",
                "先把误区说清楚：LabUtopia 的烧杯、锥形瓶、玻璃棒、干燥箱、马弗炉这些实验室物体，大多数没有单独的 <span class=\"term\">beaker.usd</span> 或 <span class=\"term\">glass_rod.usd</span> 文件。它们通常是嵌在 scene entry USD 里的 prim。正确的对应关系不是“物体名 → 单独 USD 文件”，而是“物体名 → scene USD → <span class=\"term\">/World/...</span> prim path”。少数例外是 scene shell 通过 local SubUSD payload 进入场景，柜子通过外部 Omniverse payload 进入场景。",
                "核心 scene entry 有五个：<span class=\"term\">assets/chemistry_lab/lab_001/lab_001.usd</span> 包含通用桌面物体和可开门设备；<span class=\"term\">assets/chemistry_lab/lab_003/lab_003.usd</span> 包含 press/heat/stir/shake 相关物体；<span class=\"term\">assets/chemistry_lab/lab_003/clock.usd</span> 是 LiquidMixing 使用的 lab_003 变体；<span class=\"term\">assets/chemistry_lab/hard_task/Scene1_hard.usd</span> 包含 CleanBeaker 长任务物体；<span class=\"term\">assets/navigation_lab/navigation_lab_01/lab.usd</span> 包含移动任务场景和一个 beaker。",
                "读这张表时，先看 <span class=\"term\">scene USD</span>，再看 <span class=\"term\">prim path</span>，最后看是否有 <span class=\"term\">RigidBodyAPI</span>、<span class=\"term\">CollisionAPI</span> 或 <span class=\"term\">PhysicsArticulationRootAPI</span>。比如 <span class=\"term\">DryingBox_01</span> 和 <span class=\"term\">MuffleFurnace</span> 是真的 articulated device；<span class=\"term\">beaker2</span> 是可抓取 rigid object；<span class=\"term\">target_plat</span> 更像任务用的放置平台；<span class=\"term\">lab_015</span> 是实验室背景空间，不是手要操作的小物体。",
                ["真实物体多数是 scene USD 内的 prim，不是单独 USD 文件。", "最重要的定位格式是 scene USD + /World prim path。", "Articulated device 主要在 lab_001；press/heat/stir objects 主要在 lab_003。"],
                ["assets", "config/*.yaml", "robots/franka/franka.py", "robots/ridgebase_franka/ridgebase.py"],
                widget="lab-object-assets",
                code=("text", "How to read the table", "object asset = scene USD + prim path\nexample:\n  DryingBox_01\n  scene USD: assets/chemistry_lab/lab_001/lab_001.usd\n  prim path: /World/DryingBox_01\n  physics: PhysicsArticulationRootAPI + RevoluteJoint + button PrismaticJoint\n\nnot every visible object has its own .usd file"),
            ),
            sec(
                "6-3",
                "Chemistry lab scenes：lab_001, lab_003, hard_task",
                "chemistry-scenes",
                "chemistry_lab 是 LabUtopia 最核心的资产目录，它把实验台、器材、设备和任务对象组织成可被 task config 引用的 USD 场景。",
                "<span class=\"term\">lab_001/lab_001.usd</span> 常用于 pick/place/open/close/pour/transport 等桌面任务；<span class=\"term\">lab_003/lab_003.usd</span> 常用于 press、heat、shake、stir 等任务；<span class=\"term\">hard_task/Scene1_hard.usd</span> 用于 CleanBeaker 等 long-horizon hard task。<span class=\"term\">lab_003/clock.usd</span> 则出现在 LiquidMixing 相关配置中。",
                "这些 scene 不是互换背景。它们的 prim path、object placement、device geometry、camera 可见性都会影响 task/controller。一个 controller 依赖某个 beaker path 或 target pose，如果换到另一个 scene，可能需要重写路径和 success predicate。",
                "因此当你想“加一个新任务”时，先问：现有 scene 是否有合适 object 和 prim path？如果没有，是改 USD 还是新建 scene？这比先写 controller 更基础。",
                ["lab_001 偏通用桌面操作。", "lab_003 偏设备/press/heat/stir。", "hard_task 承载长序列实验任务。"],
                ["assets/chemistry_lab/lab_001/lab_001.usd", "assets/chemistry_lab/lab_003/lab_003.usd", "assets/chemistry_lab/hard_task/Scene1_hard.usd"],
                widget="asset-map",
            ),
            sec(
                "6-4",
                "Robots：Franka, ridgeback_franka, Fetch",
                "robots",
                "LabUtopia 当前任务主要围绕 Franka 和 ridgeback_franka，Fetch 资产也存在，但本地 config 的主线是 Franka 桌面操作与 ridgebase 移动任务。",
                "<span class=\"term\">assets/robots/Franka.usd</span> 与 SubUSDs/panda_* 构成 Franka 机械臂资产；<span class=\"term\">assets/robots/ridgeback_franka.usd</span> 与 schema/subUSD 负责移动底盘加机械臂；<span class=\"term\">assets/fetch</span> 包含 URDF、USD 和 fixed camera variants。",
                "Robot asset 不只是模型。它决定 joint naming、articulation root、gripper geometry、RMPFlow descriptor、action dimension 和 controller 能否工作。LabUtopia 的 BaseController 默认创建 FrankaRMPFlowController；Level5 则切换到 ridgebase controller。",
                "这也是和 EBench 最大差异之一：EBench 的本体是 <span class=\"term\">lift2</span> dual-arm + mobile base，观测和动作 contract 都围绕它设计。LabUtopia 的 robot assets 不能直接替换 EBench 本体。",
                ["Robot asset 决定 control contract。", "Franka 桌面任务和 ridgebase 移动任务要分开看。", "Fetch 资产存在，不等于所有 runtime 都已围绕 Fetch 配好。"],
                ["assets/robots/Franka.usd", "assets/robots/ridgeback_franka.usd", "assets/fetch/fetch.usd", "robots/franka", "robots/ridgebase_franka"],
                widget="asset-map",
            ),
            sec(
                "6-5",
                "Materials 与 MDL：视觉真实度背后的依赖",
                "materials-mdl",
                "LabUtopia assets 中 .mdl 文件数量很高，说明材料系统是 high-fidelity scene 的重要组成部分。材质迁移往往比 mesh 迁移更容易被低估。",
                "在 task 运行时，<span class=\"term\">BaseTask.apply_material_to_object</span> 用 <span class=\"term\">UsdShade.MaterialBindingAPI</span> 把 material prim 绑定到 target prim。Level3 generalization 会通过 material_paths 在 episode 间切换材料。视觉上，这改变颜色、反射、透明度；学习上，它改变 image distribution。",
                "MDL material 在不同 Isaac Sim/Omniverse 版本中的解析、依赖路径和渲染效果可能不同。把 LabUtopia asset 移到 EBench 的 Isaac Sim 4.1 环境时，材料是必须检查的迁移风险：能否加载、是否丢贴图、是否影响 RTX Renderer、是否需要转成更通用的 USD Preview Surface。",
                "所以资产 QA 不只截图，还要检查 material binding log、texture path 和不同光照下的可读性。",
                ["MDL 是 high-fidelity 的一部分，也是迁移风险。", "Material variation 是 generalization 实验的一部分。", "跨版本迁移可能需要 material conversion。"],
                ["assets/chemistry_lab", "tasks/base_task.py"],
                widget="asset-map",
            ),
            sec(
                "6-6",
                "Navigation assets：barrier map 与移动任务",
                "navigation-assets",
                "Level5 navigation 不只依赖 navigation_lab USD，还依赖 barrier image 和路径规划工具。这里的资产开始从纯 3D 场景扩展到 planning representation。",
                "<span class=\"term\">config/navigation/navigation_assets.yaml</span> 指向 <span class=\"term\">assets/navigation/barrier/lab_1.png</span>。Navigation task/controller 结合 A* 工具与 ridgebase controller，把机器人从一个位置移动到目标位置。barrier image 可以理解成给 planner 用的简化 occupancy 信息。",
                "这提醒我们，资产不一定都是 USD。对于 navigation，2D barrier map、起终点、base controller 参数同样是 benchmark asset 的一部分。如果只复制 USD 而忽略 barrier map，mobile task 可能根本无法规划。",
                "与 EBench 对比时，mobile manipulation 的场景资产、base motion schema、evaluation worker 和 dataset format 都要一起看，不能只比较是否有移动底盘。",
                ["Navigation asset 包括 USD 和 planning map。", "Barrier image 是 task contract 的一部分。", "Mobile task 的复用风险高于 table-top object asset。"],
                ["config/navigation/navigation_assets.yaml", "assets/navigation/barrier/lab_1.png", "tasks/navigation_task.py", "utils/a_star.py"],
                widget="asset-map",
            ),
        ],
    },
    {
        "id": "07-ebench-assets",
        "title": "Part 7 · LabUtopia Assets 与 EBench Assets 深度对比",
        "kicker": "区别、关系、能否复用",
        "sections": [
            sec(
                "7-1",
                "先给结论：不能直接复用，但可以迁移改造",
                "reuse-answer",
                "LabUtopia assets 不能直接复用到 EBench；更准确地说，它们 not plug-and-play，但可作为 source assets 经过 conversion workflow、task/eval contract 重建和 visual QA 后进入 EBench/GenManip 风格任务。",
                "直接复用失败的原因不是一个，而是一组 contract mismatch。LabUtopia 本地 assets 服务 Isaac Sim 5.1、Franka/ridgeback_franka、本地 Hydra config、BaseTask/BaseController、HDF5 数据格式；EBench assets 服务 Isaac Sim 4.1、GenManip server、lift2 dual-arm mobile base、gmp/EvalClient、LeRobot v2.1 dataset 和 EBench scoring。",
                "如果你的目标只是“把 LabUtopia 的某个 beaker 或 lab scene 在 EBench Isaac Sim server 里看见”，可行路径是资产迁移；如果目标是“成为 EBench benchmark 中可评测任务”，还要写 GenManip task definition、scoring predicate、language instruction、dataset/eval integration。",
                "因此本章的结论会分层：visual/static asset 可能复用；task concept 可以移植；robot/control/data/eval 不能直接复用。",
                ["直接复用答案：不能直接复用。", "可迁移对象：部分 USD mesh/material/scene concept。", "必须重建对象：embodiment、task/eval contract、dataset format、scoring。"],
                ["assets", "/cpfs/shared/simulation/zhuzihou/dev/EBench/README.md"],
                widget="reuse-matrix",
                source_keys=["EBench repository", "EBench-Assets", "EBench-Dataset"],
            ),
            sec(
                "7-2",
                "EBench assets 是什么：外部 Hugging Face 资产包",
                "what-are-ebench-assets",
                "EBench entry repo 本身并不把 benchmark assets 全部放在 Git 里；它把前门、baselines、scripts 留在 GitHub，把核心 assets 和 dataset 放到 Hugging Face。",
                "EBench README 与 docs 指向 <span class=\"term\">InternRobotics/EBench-Assets</span> 和 <span class=\"term\">InternRobotics/EBench-Dataset</span>。这说明 EBench assets 是 benchmark runtime 的外部依赖，而不是像 LabUtopia 本地 assets 那样随 repo 直接出现。EBench 的 server 端来自 <span class=\"term\">GenManip</span>，client 侧用 <span class=\"term\">genmanip-client</span> 和 <span class=\"term\">gmp</span> 命令提交/评测。",
                "资产内容服务的是 EBench 的 26 tasks、3 tracks/splits、本体 lift2 和 LeRobot 数据格式。它和 baselines 的 openpi/X-VLA/InternVLA-A1 通过统一 observation/action contract 对接。",
                "所以比较两边 assets 时，不能只比较文件扩展名。要比较“谁管理资产、谁加载资产、谁定义 task、谁记录数据、谁评分”。",
                ["EBench assets 外置在 Hugging Face。", "Entry repo 不是完整 runtime。", "Assets 与 GenManip server、gmp eval、LeRobot dataset 是一套系统。"],
                ["/cpfs/shared/simulation/zhuzihou/dev/EBench/README.md"],
                code=("bash", "EBench asset download", "huggingface-cli download InternRobotics/EBench-Assets --local-dir saved --repo-type dataset\nhuggingface-cli download InternRobotics/EBench-Dataset --local-dir saved/dataset --repo-type dataset"),
                source_keys=["EBench repository", "EBench-Assets", "EBench-Dataset"],
            ),
            sec(
                "7-3",
                "资产 taxonomy：LabUtopia 与 EBench 的侧重点",
                "asset-taxonomy",
                "LabUtopia assets 的 taxonomy 更像 scientific lab kit；EBench assets 的 taxonomy 更像 indoor mobile manipulation benchmark kit。",
                "LabUtopia 侧重点是 chemistry lab scenes、scientific objects、materials、Franka/ridgeback_franka robot assets、navigation barrier map。它的任务名字也围绕 pick/place/pour/stir/shake/heat/clean beaker/device operation。EBench 侧重点是 household/indoor manipulation tasks、lift2 dual-arm mobile base、4-camera observation、long_horizon/simple_pnp/teleop_tasks 数据子集和 GenManip task assets。",
                "关系上，二者都使用 Isaac Sim/OpenUSD 生态，都把 assets 放进 embodied benchmark，都服务 VLA/imitation learning。差异上，LabUtopia 更领域化、更科学实验；EBench 更标准化、更面向 VLA leaderboard 和 client-server eval。",
                "所以 LabUtopia 可以给 EBench 提供“新 scientific lab task family”的素材，但不是 EBench 原资产的 drop-in replacement。",
                ["共同点：Isaac Sim/OpenUSD、embodied tasks、language-conditioned manipulation。", "LabUtopia：scientific lab, Franka/ridgebase, in-repo assets。", "EBench：indoor VLA benchmark, lift2, external assets/dataset。"],
                ["assets/chemistry_lab", "assets/robots", "/cpfs/shared/simulation/zhuzihou/dev/EBench/learn/_AGENT_BRIEF.md"],
                widget="asset-map",
                source_keys=["LabUtopia arXiv", "EBench docs"],
            ),
            sec(
                "7-4",
                "Embodiment mismatch：Franka/ridgeback_franka 对 lift2",
                "embodiment-mismatch",
                "最硬的差异是 robot embodiment。LabUtopia 的主线是 Franka 与 ridgeback_franka；EBench 的评测 contract 是 lift2 dual-arm mobile base。",
                "Embodiment mismatch 不只是外观不同。它改变 joint count、gripper layout、base motion、camera placement、reachable workspace、action vector 和 success predicate。EBench docs 中 observation 包含 <span class=\"term\">state.joints</span>、<span class=\"term\">state.gripper</span>、<span class=\"term\">state.base</span>、<span class=\"term\">state.ee_pose</span> 与多视角 video；action 则包含双臂关节/夹爪和 <span class=\"term\">base_motion</span>。LabUtopia 的 Franka controller 和 RMPFlow contract 不等价。",
                "这意味着 LabUtopia robot assets 不能直接拿去跑 EBench baseline。更现实的方案是保留 EBench 的 lift2，把 LabUtopia 的 lab props/scene 作为新环境素材；或者在 GenManip 中新建一个支持 Franka/ridgeback_franka 的 benchmark family，但那已不是直接复用。",
                "对于资产迁移，先问 robot 是否保持 EBench lift2。如果保持，LabUtopia 的桌面高度、object scale、collision、reachability 都要为 lift2 重新验证。",
                ["embodiment mismatch 是直接复用的第一阻碍。", "Robot asset 影响 action/observation schema。", "建议先迁移 props/scene，而不是迁移 robot。"],
                ["assets/robots/Franka.usd", "assets/robots/ridgeback_franka.usd", "controllers/robot_controllers"],
                widget="reuse-matrix",
                source_keys=["EBench docs"],
            ),
            sec(
                "7-5",
                "Simulation version mismatch：Isaac Sim 5.1 对 4.1",
                "sim-version-mismatch",
                "LabUtopia README 明确 Isaac Sim 5.1；EBench/GenManip 文档口径是 Isaac Sim 4.1。资产能否打开、材料能否显示、physics 是否一致，都要在目标版本验证。",
                "USD 理论上用于跨工具交换，但真实工程里还有 Isaac Sim extension、MDL material、physics schema、RTX renderer、sensor API、Python binding 和 asset resolver 的版本差异。LabUtopia assets 中大量 MDL/JPG/PNG 与 USD reference，如果路径或 material implementation 在 4.1 中不兼容，就会出现可见但不正确的场景。",
                "所以 conversion workflow 的第一步不是写 task，而是在 Isaac Sim 4.1/GenManip 环境中加载 LabUtopia USD，记录 missing assets、material warnings、physics warnings、collision behavior 和 camera render。通过这个 gate 之后，再考虑 task binding。",
                "这也是 visual QA 必须反复迭代的原因：有些问题不会在静态文件检查中暴露，只会在真实渲染/物理 step 中出现。",
                ["Isaac Sim 版本差异会影响 USD/MDL/physics/sensor。", "先在目标 runtime 中打开资产，再改 benchmark。", "Visual QA 与 physics QA 都是迁移步骤。"],
                ["README.md", "assets/chemistry_lab"],
                widget="version-bridge",
                source_keys=["Isaac Sim docs", "EBench docs"],
            ),
            sec(
                "7-6",
                "Task/eval contract mismatch：BaseTask 不是 EvalClient",
                "task-eval-contract",
                "LabUtopia 的任务契约是 Hydra config + BaseTask + BaseController；EBench 的评测契约是 GenManip server + gmp submit/eval + EvalClient observation/action schema。",
                "LabUtopia 里 task.step 返回 state dict，controller.step 返回 action/done/is_success，main.py 直接 apply_action。EBench client 则通过 network/API 从 server reset/step，模型实现 <span class=\"term\">get_action(obs)</span> 或 action chunk 接口，并按 worker_id 返回 action dict。server 负责 Isaac Sim 和 scoring，client 只像黑盒一样交互。",
                "这意味着即使 LabUtopia USD 被加载到 EBench 中，原来的 BaseTask/BaseController 也不会自动工作。你需要把 scientific lab task 重新表达为 GenManip/EBench task：初始状态采样、instruction、success predicate、partial score、episode timeout、observation/action packing。",
                "如果不重建 task/eval contract，所谓复用只是“看见资产”，不是“进入 EBench benchmark”。",
                ["LabUtopia: local loop, direct controller。", "EBench: client-server, black-box eval。", "Task/eval contract 必须重写。"],
                ["main.py", "tasks/base_task.py", "controllers/base_controller.py"],
                widget="runtime-loop",
                source_keys=["EBench docs", "GenManip arXiv"],
            ),
            sec(
                "7-7",
                "Dataset format mismatch：HDF5 episode 对 LeRobot v2.1",
                "dataset-format-mismatch",
                "LabUtopia 的 DataCollector 写 HDF5 episode；EBench-Dataset 使用 LeRobot v2.1。数据不能直接互当训练集，除非做格式转换和语义对齐。",
                "LabUtopia HDF5 包含 camera datasets、agent_pose、actions、language_instruction、task_properties，并用 episode.jsonl 记录 episode metadata。EBench-Dataset 则围绕 LeRobot：低维信号、视频、metadata、tasks.jsonl、modality.json，以及 lift2 的 joints/gripper/base/ee_pose/action_delta 等字段。",
                "数据格式 mismatch 背后其实还是 embodiment mismatch。LabUtopia 的 action 可能是 Franka 关节目标；EBench action contract 是 lift2 双臂/底盘动作。即使把 HDF5 转成 Parquet/MP4，也不能自动变成 lift2 demonstration。",
                "可行路线是：用 LabUtopia assets 在 EBench/GenManip 中重新采集 lift2 数据；或只把 LabUtopia 数据用于预训练视觉/语言表征，低层动作部分不直接混合。",
                ["HDF5 到 LeRobot 是格式转换，不是语义转换。", "Action/state schema 必须和 robot embodiment 对齐。", "重新采集目标本体数据通常比硬转动作更可靠。"],
                ["data_collectors/data_collector.py", "policy/dataset"],
                widget="dataset-flow",
                source_keys=["LeRobot docs", "EBench-Dataset"],
            ),
            sec(
                "7-8",
                "Conversion workflow：从 LabUtopia USD 到 EBench task",
                "conversion-workflow",
                "如果真的要把 LabUtopia 的实验室资产带到 EBench，推荐按 workflow 做，而不是一次性复制目录后祈祷它能跑。",
                "第一步做 asset inventory：列出 root USD、subUSD、textures、MDL、prim path、scale、collision、articulation、semantic object list。第二步在 Isaac Sim 4.1/GenManip 环境打开，记录 missing reference、material warning、physics warning。第三步根据 EBench/lift2 workspace 检查可达性和 camera visibility。第四步把 scene/objects 包装成 EBench-Assets 风格目录和 metadata。",
                "第五步才是 task definition：写 instruction set、initial state sampler、goal predicate、partial scoring、timeout 和 worker reset。第六步生成或采集 LeRobot v2.1 数据，确保 observation/action schema 与 lift2 对齐。第七步做 visual QA、physics QA 和小规模 gmp eval。",
                "这套流程看似慢，但比把错误带到 leaderboard 上快。资产迁移的真正成本在 contract validation，不在复制文件。",
                ["Inventory → target runtime open → material/physics fix → task contract → dataset/eval → QA。", "每一步都要有可回滚记录。", "先做一个小 task pilot，不要一次迁移整座实验室。"],
                ["assets/chemistry_lab", "assets/robots", "config"],
                widget="reuse-matrix",
                code=("text", "Migration checklist", "1. Inventory USD/MDL/texture/prim paths\n2. Open in Isaac Sim 4.1 + GenManip runtime\n3. Fix references, materials, collision, scale\n4. Keep EBench lift2 or explicitly create new embodiment contract\n5. Write task/eval contract and scoring\n6. Generate LeRobot v2.1 data or eval-only episodes\n7. Run visual QA, physics QA, small gmp eval"),
                source_keys=["EBench-Assets", "GenManip arXiv"],
            ),
            sec(
                "7-9",
                "Visual QA：资产迁移必须反复看真实渲染",
                "visual-qa",
                "资产比较不能只在文本里完成。LabUtopia 与 EBench 的迁移必须反复做 visual QA，因为材料、尺度、碰撞和 camera 可见性都会在渲染中暴露。",
                "最低限度的 visual QA 包括：目标 Isaac Sim 版本中场景是否加载完整；MDL/texture 是否丢失；物体是否过大过小；robot reachability 是否合理；camera 是否遮挡目标；透明/反光材料是否可读；episode reset 后物体是否漂浮或穿模；mobile base 是否能通过 navigation path。",
                "对于网页教程本身，本书也使用 browser visual review：检查目录、章节布局、移动端、交互 widget、代码块、图片和内部链接。对资产迁移本身，真实 QA 还需要在 Isaac Sim/GenManip 中截图或录制 episode。",
                "如果未来你要真正迁移 LabUtopia assets 到 EBench，建议把每个迁移阶段都保存 before/after screenshot 和 short rollout video，避免“文件能打开”被误判为“任务能评测”。",
                ["Visual QA 不是美观审查，而是 contract 审查。", "至少覆盖 load、material、scale、camera、collision、reachability。", "网页 visual review 与 Isaac Sim render review 都要留证据。"],
                ["learn/assets/js/widgets/book-widgets.js", "assets/chemistry_lab"],
                widget="version-bridge",
            ),
        ],
    },
    {
        "id": "08-extension-debug",
        "title": "Part 8 · 扩展与 Debug",
        "kicker": "如何安全地改项目",
        "sections": [
            sec(
                "8-1",
                "新增一个 task 的最小路径",
                "new-task-path",
                "新增 task 不应该从复制整个 controller 开始，而应该从 contract 列表开始：config、asset、task class、controller class、factory、data shape、success condition。",
                "最小路径是：选或建 USD scene；写 config 指定 task_type/controller_type/usd_path/robot/cameras/task params；新增 task class 继承 BaseTask 并返回稳定 state；新增 controller 继承 BaseController 并把 state 变成 action/done/is_success；在 factory 注册；跑 collect mode 生成少量 episode；检查 HDF5；再考虑 training。",
                "如果 task 涉及新物体，要先在 Isaac Sim 中确认 prim path、collision、geometry center、grasp pose。如果涉及新 camera，要同步修改 policy shape_meta。不要等模型训练失败后才发现 camera key 不存在。",
                "这条路径看起来朴素，但能避免最常见的“能运行一次但无法收数据/无法训练/无法复现”。",
                ["新增 task 的单元是 contract，不是单个 Python 文件。", "先 collect 5 个 episode 检查数据，再扩大规模。", "所有路径都应能从 config 追到 stage prim。"],
                ["config", "tasks", "controllers", "factories"],
                widget="task-boundary",
            ),
            sec(
                "8-2",
                "新增资产前的 checklist",
                "asset-checklist",
                "新增 USD/MDL/texture 资产时，先做 checklist。否则后面 controller、dataset、policy 都会替资产问题背锅。",
                "检查项包括：USD 是否能在目标 Isaac Sim 版本打开；所有 reference/texture/MDL 是否可解析；scale 是否以米为单位合理；collision 是否存在且不穿模；articulation 是否有正确 joint；prim path 是否稳定；camera 是否能看到目标；material 是否在训练视角下可区分；object_utils 是否能读到 geometry center。",
                "如果资产用于 generalization，还要检查 material_paths、test_materials、position_range 是否覆盖真实变化，而不是只在一个固定位置渲染。对于 navigation，还要同步 barrier map 或 occupancy representation。",
                "把这份 checklist 当成资产 PR 的最低门槛，会比后期调 policy 省很多时间。",
                ["资产 QA 要覆盖 render、physics、semantics、data。", "Prim path 变更要同步 config/controller。", "移动任务还要检查 planning map。"],
                ["assets", "config/navigation/navigation_assets.yaml", "tasks/base_task.py"],
                widget="asset-map",
            ),
            sec(
                "8-3",
                "常见 failure mode：从症状定位层级",
                "failure-modes",
                "LabUtopia 的错误大多可以按层级定位：environment、asset、task、controller、data、policy。先定位层级，再谈修复。",
                "如果 Isaac Sim 启动失败，先看环境版本、extension、GPU 和 headless 设置。若 scene 加载但 object 找不到，看 USD reference 和 prim path。若 camera 没图，看 camera prim、resolution、image_type、clipping range。若 robot 不动，看 controller 是否输出 action、articulation controller 是否匹配。若 HDF5 异常，看 DataCollector 缓存和 close。若训练不收敛，看 dataset shape、action/state 对齐和失败 episode 是否混入。",
                "这种分层 debug 和 RL 实验很像：不要把所有 failure 都归因于 policy。很多时候 policy 只是忠实学习了有问题的数据，或被不稳定 scene distribution 推到了未覆盖状态。",
                "建议每次只改一个层级，并保存 run_dir/config.yaml 与少量 episode 作为证据。",
                ["先定位层级，再改代码。", "能 collect 成功不代表能 train 成功。", "能 train loss 下降不代表能 infer 成功。"],
                ["main.py", "tasks/base_task.py", "controllers/base_controller.py", "data_collectors/data_collector.py", "policy/dataset"],
            ),
            sec(
                "8-4",
                "从网页教程回到真实项目：推荐阅读顺序",
                "reading-order",
                "如果你要真正掌握项目，不要按文件树从上到下读。按一次 episode 的数据流读，效率更高。",
                "第一轮读 main.py，只追 cfg、world、stage、task、controller、state、action。第二轮读一个最简单 task，比如 level1_pick 的 config/task/controller。第三轮读 BaseTask/BaseController，理解共用机制。第四轮读 DataCollector，看数据如何落盘。第五轮读 policy/config/task 与 workspace，看数据如何进模型。第六轮才看 long-horizon 或 mobile task。",
                "读资产时，打开对应 config 中的 usd_path，再在 USD stage 里验证 prim path。读训练时，打开 dataset 文件并检查 key/shape，不要只读 YAML。",
                "这条顺序让你每次只理解一个 contract。等 contract 都清楚，再谈重构或迁移到 EBench。",
                ["按数据流读，不按目录树读。", "每个章节都可以对应一次 IDE 阅读。", "理解一个 level1 task 是理解全部任务的入口。"],
                ["main.py", "config/level1_pick.yaml", "tasks/pick_task.py", "controllers/pick_controller.py"],
                widget="runtime-loop",
            ),
            sec(
                "8-5",
                "Capstone：把一个小实验跑完整",
                "capstone",
                "最后，用一个小实验把整本书串起来：选择 level1_pick，确认 assets，collect 少量 episode，检查 HDF5，再用训练配置理解输入输出。",
                "建议流程：运行 <span class=\"term\">python main.py --config-name level1_pick --no-video</span> 采集少量数据；打开 run_dir/config.yaml 确认 cfg 被保存；检查 dataset/episode_0000.h5 中 camera、agent_pose、actions、language_instruction；打开 policy/config/task/dp.yaml 或 act.yaml 对齐 dataset_path；最后再读对应 workspace。",
                "如果你能解释每个文件从哪里来、为什么存在、下一步被谁读取，你就已经越过“只会点点点”的阶段。此时再看 LabUtopia 论文或 EBench 资产迁移，就有自己的判断力。",
                "这个 capstone 不要求你训练出强 policy，而是要求你能把 simulation、data、policy 三条线连起来。",
                ["目标不是刷结果，而是建立闭环理解。", "少量 episode 足够验证 contract。", "能解释数据流，比盲跑大规模训练更重要。"],
                ["main.py", "outputs/collect", "policy/config/task/dp.yaml"],
                code=("bash", "Small capstone", "python main.py --config-name level1_pick --no-video\npython train.py --config-name=train_diffusion_unet_image_workspace"),
            ),
        ],
    },
    {
        "id": "appendix",
        "title": "Appendix · 查阅资料",
        "kicker": "术语、命令、链接、文件地图",
        "sections": [
            sec(
                "A-1",
                "Glossary：中英文术语对照",
                "glossary",
                "本附录把书中反复出现的 English terms 放在一起，便于你读论文、代码和 docs 时保持同一套词表。",
                "<span class=\"term\">SimulationApp</span> 是 Isaac Sim 应用入口；<span class=\"term\">World</span> 是 simulation wrapper；<span class=\"term\">Stage</span> 是 OpenUSD scene graph；<span class=\"term\">prim path</span> 是 USD 对象路径；<span class=\"term\">articulation</span> 是机器人关节系统；<span class=\"term\">RMPFlow</span> 是 Franka 运动生成/控制工具；<span class=\"term\">BaseTask</span> 负责 state；<span class=\"term\">BaseController</span> 负责 action；<span class=\"term\">DataCollector</span> 写 episode；<span class=\"term\">LeRobot</span> 是 EBench-Dataset 使用的数据格式生态。",
                "LabUtopia 相关：<span class=\"term\">LabSim</span>、<span class=\"term\">LabScene</span>、<span class=\"term\">LabBench</span>。EBench 相关：<span class=\"term\">GenManip</span>、<span class=\"term\">gmp</span>、<span class=\"term\">EvalClient</span>、<span class=\"term\">lift2</span>、<span class=\"term\">EBench-Assets</span>、<span class=\"term\">EBench-Dataset</span>。",
                "Policy 相关：<span class=\"term\">Diffusion Policy</span>、<span class=\"term\">Action Chunking Transformer</span>、<span class=\"term\">action chunk</span>、<span class=\"term\">receding horizon</span>、<span class=\"term\">covariate shift</span>。",
                ["术语保留英文是为了和论文/代码一致。", "中文解释只负责建立直觉。", "遇到缩写先查本页，再回到章节。"],
                [],
                widget="glossary-search",
            ),
            sec(
                "A-2",
                "Commands：常用命令速查",
                "commands",
                "这里收集本书涉及的常用命令，方便你从阅读切到实践。",
                "LabUtopia collection 使用 <span class=\"term\">python main.py --config-name ...</span>；training 使用 <span class=\"term\">python train.py --config-name=...</span>；Isaac Sim 环境安装按 README 使用 <span class=\"term\">isaacsim[all,extscache]==5.1.0</span>。EBench assets/dataset 下载使用 huggingface-cli，评测使用 <span class=\"term\">gmp submit</span>、<span class=\"term\">gmp eval</span>、<span class=\"term\">gmp status</span>。",
                "命令不是孤立记忆。每条命令背后都有 contract：config-name 决定 task；dataset_path 决定训练数据；gmp eval 依赖 server、run_id、worker_ids、lift2 contract。",
                "执行前先确认当前工作目录、Python env、Isaac Sim version 和 GPU 是否满足要求。",
                ["命令要和配置一起读。", "跨项目命令不要混用。", "EBench 命令不能直接驱动 LabUtopia main.py。"],
                [],
                code=("bash", "Command sheet", "python main.py --config-name level1_pick\npython main.py --config-name level5_Navigation --headless --no-video\npython train.py --config-name=train_act_image_workspace\nhuggingface-cli download InternRobotics/EBench-Assets --local-dir saved --repo-type dataset\ngmp submit ebench/generalist/val_train --run_id my_run\ngmp eval -a r5a -g lift2 --worker_ids 0"),
            ),
            sec(
                "A-3",
                "Local file map：从概念到文件",
                "local-file-map",
                "这页把概念映射到本地文件，方便你回到 IDE 中查证。",
                "Runtime：<span class=\"term\">main.py</span>。Task base：<span class=\"term\">tasks/base_task.py</span>。Controller base：<span class=\"term\">controllers/base_controller.py</span>。Factory：<span class=\"term\">factories/*.py</span>。Data：<span class=\"term\">data_collectors/data_collector.py</span>。Policy training：<span class=\"term\">train.py</span>、<span class=\"term\">policy/workspace</span>、<span class=\"term\">policy/config</span>。",
                "Assets：<span class=\"term\">assets/chemistry_lab</span>、<span class=\"term\">assets/navigation_lab</span>、<span class=\"term\">assets/navigation/barrier/lab_1.png</span>、<span class=\"term\">assets/robots/Franka.usd</span>、<span class=\"term\">assets/robots/ridgeback_franka.usd</span>、<span class=\"term\">assets/fetch</span>。",
                "EBench reference：本地 EBench 的 learn 目录可作为交互教程结构参考；但 LabUtopia 的内容、资产关系和版本口径应以本 repo 与外部资料为准。",
                ["先从 main.py 出发。", "再按 config 找 task/controller。", "资产路径要和 config 一起看。"],
                ["main.py", "config", "tasks", "controllers", "assets", "policy"],
                widget="asset-map",
            ),
            sec(
                "A-4",
                "References：本书使用的公开资料",
                "references",
                "本书先收集公开资料，再结合本地代码和领域知识综合解释。下面是核心来源，便于你继续追原文。",
                "LabUtopia 来源包括 arXiv 论文、NeurIPS 2025 abstract、project page、Hugging Face dataset 和本地 README。EBench 来源包括 GitHub repo、EBench docs、Hugging Face EBench-Assets、EBench-Dataset 和 GenManip arXiv。底层技术来源包括 Isaac Sim docs、OpenUSD introduction、LeRobot docs、Hydra docs、Diffusion Policy 和 Action Chunking Transformer papers。",
                "阅读参考资料时要注意口径：论文常描述 benchmark design 和愿景，README 给安装与当前代码入口，docs 给运行契约，代码给真正的现状。本书的结论尤其是资产复用结论，基于这些来源的交叉核对。",
                "如果未来这些项目更新，建议重新检查 Isaac Sim 版本、dataset 格式、asset hosting 和 eval contract。",
                ["所有来源链接也出现在 index 的 source panel。", "资产复用结论依赖当前公开资料和本地代码。", "版本更新后要重新评估。"],
                [],
                source_keys=[name for name, _ in SOURCES],
            ),
        ],
    },
]


def source_url(name: str) -> str:
    return dict(SOURCES)[name]


def slug_section(part_id: str, section: dict) -> str:
    numeric = section["id"].lower().replace(".", "-")
    return f"chapters/{part_id}/{numeric}-{section['slug']}.html"


def metadata() -> dict:
    parts = []
    for part in PARTS:
        sections = []
        for section in part["sections"]:
            sections.append(
                {
                    "id": section["id"],
                    "title": section["title"],
                    "file": slug_section(part["id"], section),
                    "summary": strip_tags(section["lede"]),
                }
            )
        parts.append({"id": part["id"], "title": part["title"], "kicker": part["kicker"], "sections": sections})
    return {
        "title": "LabUtopia Interactive Book",
        "subtitle": "从 Isaac Sim + USD 基础到 LabUtopia 架构、数据、资产与 EBench 复用判断",
        "updated": "2026-06-02",
        "parts": parts,
        "sources": [{"name": name, "url": url} for name, url in SOURCES],
    }


def strip_tags(text: str) -> str:
    return re_sub(r"<[^>]+>", "", text)


def re_sub(pattern: str, repl: str, text: str) -> str:
    import re

    return re.sub(pattern, repl, text)


def css() -> str:
    return dedent(
        """
        :root {
          color-scheme: light;
          --bg: #f6f7f9;
          --paper: #ffffff;
          --paper-2: #f1f5f3;
          --ink: #182126;
          --muted: #5c6870;
          --line: #d8dedc;
          --accent: #0f766e;
          --accent-2: #b45309;
          --accent-3: #9f1239;
          --soft: #e6f2ef;
          --warn: #fff4d6;
          --code: #102027;
          --code-ink: #d9f0ea;
          --shadow: 0 16px 40px rgba(24, 33, 38, 0.10);
          --radius: 8px;
        }
        [data-theme="dark"] {
          color-scheme: dark;
          --bg: #11171a;
          --paper: #182126;
          --paper-2: #202b30;
          --ink: #edf5f2;
          --muted: #a9b8b4;
          --line: #334348;
          --accent: #5eead4;
          --accent-2: #f59e0b;
          --accent-3: #fb7185;
          --soft: #153633;
          --warn: #3d3218;
          --code: #071113;
          --code-ink: #d9f0ea;
          --shadow: 0 16px 40px rgba(0, 0, 0, 0.28);
        }
        * { box-sizing: border-box; }
        html { scroll-behavior: smooth; }
        body {
          margin: 0;
          background: var(--bg);
          color: var(--ink);
          font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif;
          line-height: 1.7;
          letter-spacing: 0;
          overflow-x: hidden;
        }
        a { color: var(--accent); text-decoration-thickness: 0.08em; text-underline-offset: 0.18em; }
        button, input { font: inherit; }
        .topbar {
          position: sticky;
          top: 0;
          z-index: 20;
          min-height: 58px;
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 18px;
          border-bottom: 1px solid var(--line);
          background: color-mix(in srgb, var(--paper) 88%, transparent);
          backdrop-filter: blur(12px);
        }
        .brand {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          min-width: 0;
          color: var(--ink);
          text-decoration: none;
          font-weight: 800;
        }
        .brand-mark {
          width: 28px;
          height: 28px;
          display: inline-grid;
          place-items: center;
          border-radius: 7px;
          background: linear-gradient(135deg, var(--accent), var(--accent-2));
          color: #fff;
          font-size: 13px;
        }
        .brand span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .top-actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }
        .icon-btn, .text-btn, .cp {
          border: 1px solid var(--line);
          background: var(--paper);
          color: var(--ink);
          border-radius: 7px;
          min-height: 36px;
          padding: 7px 10px;
          cursor: pointer;
        }
        .icon-btn { width: 38px; padding: 0; display: inline-grid; place-items: center; }
        .text-btn:hover, .icon-btn:hover, .cp:hover { border-color: var(--accent); color: var(--accent); }
        .progress {
          position: fixed;
          top: 0;
          left: 0;
          height: 3px;
          width: 0;
          z-index: 50;
          background: linear-gradient(90deg, var(--accent), var(--accent-2), var(--accent-3));
        }
        .book {
          display: grid;
          grid-template-columns: 292px minmax(0, 1fr) 230px;
          gap: 0;
          max-width: 1540px;
          margin: 0 auto;
        }
        .sidebar, .rail {
          position: sticky;
          top: 59px;
          height: calc(100vh - 59px);
          overflow: auto;
          padding: 22px 18px;
        }
        .sidebar { border-right: 1px solid var(--line); }
        .rail { border-left: 1px solid var(--line); }
        .content {
          min-width: 0;
          padding: 34px min(5vw, 58px) 72px;
          background: var(--paper);
        }
        .cover {
          max-width: 1180px;
          margin: 0 auto;
          padding: 34px min(5vw, 48px) 72px;
        }
        .hero {
          display: grid;
          min-height: 520px;
          align-items: end;
          padding: 42px;
          border-radius: 8px;
          overflow: hidden;
          background:
            linear-gradient(180deg, rgba(6, 19, 22, 0.18), rgba(6, 19, 22, 0.80)),
            url("../../../images/teaser.png") center / cover no-repeat;
          color: #fff;
          box-shadow: var(--shadow);
        }
        .cover .hero { background-image: linear-gradient(180deg, rgba(6, 19, 22, 0.12), rgba(6, 19, 22, 0.82)), url("../../../images/teaser.png"); }
        .hero h1 { max-width: 880px; margin: 0; font-size: clamp(34px, 6vw, 76px); line-height: 1.04; letter-spacing: 0; }
        .hero p { max-width: 740px; margin: 18px 0 0; color: rgba(255,255,255,0.88); font-size: 18px; }
        .hero-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 26px; }
        .hero-actions a { color: #fff; border: 1px solid rgba(255,255,255,0.55); padding: 10px 14px; border-radius: 7px; text-decoration: none; }
        .eyebrow { color: var(--accent-2); font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; font-size: 12px; }
        h1, h2, h3 { line-height: 1.2; letter-spacing: 0; }
        h1, h2, h3, .lede, .plain-card, .lab, .widget, .matrix-cell, .level-card, .term { overflow-wrap: anywhere; }
        h1 { margin: 8px 0 18px; font-size: clamp(32px, 4vw, 56px); }
        h2 { margin: 36px 0 12px; font-size: 25px; }
        h3 { margin: 24px 0 8px; font-size: 19px; }
        .lede {
          font-size: 20px;
          color: var(--muted);
          margin: 0 0 26px;
          max-width: 860px;
        }
        .prose { max-width: 900px; margin: 0 auto; }
        .prose p { margin: 0 0 16px; }
        .term {
          color: var(--accent);
          font-weight: 800;
        }
        .term-i {
          color: var(--accent-2);
          font-style: italic;
          font-weight: 700;
        }
        .callout, .bridge {
          margin: 22px 0;
          padding: 16px 18px;
          border: 1px solid var(--line);
          border-left: 4px solid var(--accent);
          border-radius: 8px;
          background: var(--paper-2);
        }
        .callout.warn { border-left-color: var(--accent-2); background: var(--warn); }
        .callout.note { border-left-color: var(--accent-3); }
        .plain-card {
          margin: 18px 0;
          padding: 16px 18px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: color-mix(in srgb, var(--soft) 68%, var(--paper));
        }
        .plain-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
          margin: 22px 0 28px;
        }
        .plain-grid .plain-card { margin: 0; }
        .plain-card h2,
        .plain-card h3 {
          margin: 0 0 8px;
          font-size: 17px;
        }
        .plain-card p { margin: 0; color: var(--ink); }
        .plain-card ul { margin: 6px 0 0; padding-left: 18px; }
        .plain-card li { margin: 4px 0; }
        .c-h { font-weight: 850; margin-bottom: 8px; }
        .tag {
          display: inline-block;
          margin-right: 8px;
          padding: 2px 7px;
          border: 1px solid var(--line);
          border-radius: 999px;
          color: var(--accent);
          font-size: 12px;
        }
        .note-list { margin: 0; padding-left: 20px; }
        .note-list li { margin: 7px 0; }
        .path-grid, .source-grid, .cover-toc {
          display: grid;
          gap: 12px;
        }
        .path-grid { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin: 18px 0; }
        .path {
          padding: 12px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--paper-2);
          overflow-wrap: anywhere;
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 13px;
        }
        .code {
          margin: 22px 0;
          overflow: hidden;
          border-radius: 8px;
          background: var(--code);
          color: var(--code-ink);
          border: 1px solid color-mix(in srgb, var(--line) 30%, transparent);
        }
        .code-h {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          padding: 8px 10px;
          border-bottom: 1px solid rgba(255,255,255,0.12);
          color: #afc9c2;
        }
        .fn { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; overflow-wrap: anywhere; }
        .cp { color: var(--code-ink); background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.20); min-height: 30px; }
        pre { margin: 0; padding: 16px; overflow: auto; }
        code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; display: block; overflow-x: auto; }
        th, td { border: 1px solid var(--line); padding: 10px; text-align: left; vertical-align: top; }
        th { background: var(--paper-2); }
        .table-scroll { overflow-x: auto; margin: 18px 0; }
        .table-scroll table { min-width: 640px; margin: 0; display: table; }
        .part-title {
          margin: 20px 0 8px;
          font-size: 12px;
          color: var(--muted);
          text-transform: uppercase;
          font-weight: 850;
        }
        .nav-list { list-style: none; padding: 0; margin: 0; }
        .nav-list a {
          display: block;
          padding: 7px 8px;
          border-radius: 7px;
          color: var(--muted);
          text-decoration: none;
          font-size: 14px;
          line-height: 1.35;
        }
        .nav-list a:hover, .nav-list a.active { background: var(--soft); color: var(--ink); }
        .rail h2 { font-size: 12px; color: var(--muted); text-transform: uppercase; margin: 0 0 10px; }
        .rail a { display: block; color: var(--muted); text-decoration: none; font-size: 13px; padding: 5px 0; }
        .rail a:hover { color: var(--accent); }
        .pager {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 14px;
          max-width: 900px;
          margin: 42px auto 0;
        }
        .pager a {
          padding: 14px;
          border: 1px solid var(--line);
          border-radius: 8px;
          color: var(--ink);
          text-decoration: none;
          background: var(--paper-2);
        }
        .pager .next { text-align: right; }
        .cover-toc {
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          margin-top: 28px;
        }
        .toc-card, .source-card {
          padding: 18px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--paper);
          box-shadow: 0 8px 20px rgba(24, 33, 38, 0.04);
        }
        .toc-card h2 { margin: 0 0 6px; font-size: 18px; }
        .toc-card ol { margin: 10px 0 0; padding-left: 20px; }
        .toc-card li { margin: 6px 0; }
        .source-grid { grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); margin-top: 18px; }
        .source-card { font-size: 14px; overflow-wrap: anywhere; }
        .lab {
          margin: 26px 0;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--paper);
          box-shadow: var(--shadow);
          overflow: hidden;
        }
        .lab-h {
          display: flex;
          gap: 10px;
          align-items: center;
          padding: 12px 14px;
          border-bottom: 1px solid var(--line);
          background: var(--paper-2);
        }
        .lab-tag {
          border: 1px solid var(--line);
          color: var(--accent);
          border-radius: 999px;
          padding: 2px 8px;
          font-size: 12px;
          font-weight: 800;
          white-space: nowrap;
          overflow-wrap: normal;
        }
        .lab-t { font-weight: 850; }
        .lab-body { padding: 16px; }
        .lab-cap { padding: 0 16px 16px; color: var(--muted); font-size: 14px; }
        .widget-help, .widget-feedback {
          padding: 12px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--paper-2);
          margin: 0 0 12px;
        }
        .widget-help strong, .widget-feedback strong { color: var(--accent); }
        .widget-feedback { border-left: 4px solid var(--accent-2); }
        .seg { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
        .seg button, .widget button {
          border: 1px solid var(--line);
          border-radius: 7px;
          background: var(--paper);
          color: var(--ink);
          min-height: 34px;
          padding: 6px 10px;
          cursor: pointer;
        }
        .seg button.active, .widget button.active { border-color: var(--accent); background: var(--soft); color: var(--accent); }
        input[type="range"] { max-width: 100%; }
        .flow-track {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 10px;
          align-items: stretch;
        }
        .flow-node, .matrix-cell, .level-card {
          padding: 12px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--paper-2);
          min-height: 72px;
        }
        .flow-node.active { outline: 2px solid var(--accent); background: var(--soft); }
        .matrix { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
        .meter { height: 10px; border-radius: 999px; background: var(--line); overflow: hidden; margin-top: 8px; }
        .meter span { display: block; height: 100%; width: var(--w, 50%); background: linear-gradient(90deg, var(--accent), var(--accent-2)); }
        .search-overlay {
          position: fixed;
          inset: 0;
          z-index: 80;
          display: none;
          background: rgba(0,0,0,0.34);
          padding: 70px min(4vw, 40px);
        }
        .search-overlay.open { display: block; }
        .search-box {
          max-width: 760px;
          margin: 0 auto;
          background: var(--paper);
          border-radius: 8px;
          border: 1px solid var(--line);
          box-shadow: var(--shadow);
          overflow: hidden;
        }
        .search-box input {
          width: 100%;
          border: 0;
          border-bottom: 1px solid var(--line);
          padding: 16px;
          background: var(--paper);
          color: var(--ink);
        }
        .search-results { max-height: 60vh; overflow: auto; padding: 10px; }
        .search-results a { display: block; padding: 10px; border-radius: 7px; color: var(--ink); text-decoration: none; }
        .search-results a:hover { background: var(--soft); }
        @media (max-width: 1120px) {
          .book { grid-template-columns: 252px minmax(0, 1fr); }
          .rail { display: none; }
          .plain-grid { grid-template-columns: 1fr; }
          .flow-track { grid-template-columns: 1fr; }
        }
        @media (max-width: 820px) {
          .topbar { padding: 8px 10px; }
          .book { display: block; }
          .sidebar { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); max-height: 46vh; }
          .content, .cover { padding: 24px 16px 56px; }
          .hero { min-height: 430px; padding: 24px; }
          .pager { grid-template-columns: 1fr; }
          .pager .next { text-align: left; }
          .plain-grid { grid-template-columns: 1fr; }
          .brand span:last-child { max-width: 160px; }
        }
        """
    ).strip() + "\n"


def book_js() -> str:
    return dedent(
        """
        (() => {
          const book = window.LABUTOPIA_BOOK;
          if (!book) return;

          const root = document.body.dataset.root || "./";
          const current = document.body.dataset.section || "";
          const flat = book.parts.flatMap(part => part.sections.map(section => ({...section, part})));

          const linkFor = section => root + section.file;
          const byId = id => flat.find(s => s.id === id);

          function renderSidebar() {
            const sidebar = document.getElementById("sidebar");
            if (!sidebar) return;
            const home = `<a class="brand side-brand" href="${root}index.html"><span class="brand-mark">LU</span><span>LabUtopia Book</span></a>`;
            const html = book.parts.map(part => {
              const items = part.sections.map(section => {
                const active = section.id === current ? "active" : "";
                return `<li><a class="${active}" href="${linkFor(section)}">${section.id} · ${section.title}</a></li>`;
              }).join("");
              return `<div class="part-title">${part.title}</div><ul class="nav-list">${items}</ul>`;
            }).join("");
            sidebar.innerHTML = home + html;
          }

          function renderPager() {
            const pager = document.getElementById("pager");
            if (!pager || !current) return;
            const idx = flat.findIndex(s => s.id === current);
            const prev = idx > 0 ? flat[idx - 1] : null;
            const next = idx >= 0 && idx < flat.length - 1 ? flat[idx + 1] : null;
            pager.innerHTML = `${prev ? `<a href="${linkFor(prev)}"><span>上一节</span><br><strong>${prev.id} · ${prev.title}</strong></a>` : "<span></span>"}${next ? `<a class="next" href="${linkFor(next)}"><span>下一节</span><br><strong>${next.id} · ${next.title}</strong></a>` : "<span></span>"}`;
          }

          function renderRail() {
            const rail = document.getElementById("rail");
            if (!rail) return;
            const heads = [...document.querySelectorAll("main h2[id], main h3[id]")];
            if (!heads.length) {
              rail.innerHTML = "";
              return;
            }
            rail.innerHTML = `<h2>On this page</h2>${heads.map(h => `<a href="#${h.id}">${h.textContent}</a>`).join("")}`;
          }

          function setupSearch() {
            const overlay = document.getElementById("book-search");
            const input = document.getElementById("book-search-input");
            const results = document.getElementById("book-search-results");
            const openers = document.querySelectorAll("[data-search-open]");
            const closers = document.querySelectorAll("[data-search-close]");
            if (!overlay || !input || !results) return;
            const render = () => {
              const q = input.value.trim().toLowerCase();
              const hits = q ? flat.filter(s => `${s.id} ${s.title} ${s.summary} ${s.part.title}`.toLowerCase().includes(q)) : flat.slice(0, 12);
              results.innerHTML = hits.map(s => `<a href="${linkFor(s)}"><strong>${s.id} · ${s.title}</strong><br><span>${s.summary}</span></a>`).join("");
            };
            openers.forEach(btn => btn.addEventListener("click", () => {
              overlay.classList.add("open");
              input.focus();
              render();
            }));
            closers.forEach(btn => btn.addEventListener("click", () => overlay.classList.remove("open")));
            overlay.addEventListener("click", event => {
              if (event.target === overlay) overlay.classList.remove("open");
            });
            input.addEventListener("input", render);
            document.addEventListener("keydown", event => {
              if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                overlay.classList.add("open");
                input.focus();
                render();
              }
              if (event.key === "Escape") overlay.classList.remove("open");
            });
          }

          function setupTheme() {
            const btn = document.querySelector("[data-theme-toggle]");
            const stored = localStorage.getItem("labutopia-theme");
            if (stored) document.documentElement.dataset.theme = stored;
            if (!btn) return;
            btn.addEventListener("click", () => {
              const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
              document.documentElement.dataset.theme = next;
              localStorage.setItem("labutopia-theme", next);
            });
          }

          function setupProgress() {
            const bar = document.getElementById("progress");
            if (!bar) return;
            const update = () => {
              const total = document.documentElement.scrollHeight - window.innerHeight;
              const pct = total > 0 ? (window.scrollY / total) * 100 : 0;
              bar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
            };
            update();
            document.addEventListener("scroll", update, {passive: true});
          }

          function setupCopy() {
            document.querySelectorAll(".cp").forEach(btn => {
              btn.addEventListener("click", async () => {
                const code = btn.closest(".code")?.querySelector("code")?.innerText || "";
                await navigator.clipboard.writeText(code);
                const old = btn.textContent;
                btn.textContent = "已复制";
                setTimeout(() => btn.textContent = old, 900);
              });
            });
          }

          renderSidebar();
          renderPager();
          renderRail();
          setupSearch();
          setupTheme();
          setupProgress();
          setupCopy();
          if (window.LUWidgets) window.LUWidgets.mountAll();
        })();
        """
    ).strip() + "\n"


def widgets_js() -> str:
    return dedent(
        """
        (() => {
          const W = {};
          const esc = value => String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
          const help = text => `<div class="widget-help"><strong>怎么用：</strong>${text}</div>`;
          const feedback = text => `<div class="widget-feedback" aria-live="polite"><strong>现在你看到的是：</strong><span>${text}</span></div>`;

          W["runtime-loop"] = el => {
            const steps = [
              ["Hydra cfg", "像实验单：写清楚今天做哪个任务、用哪个场景、哪个机器人、哪些相机。"],
              ["Stage reference", "像把实验室搬到舞台上：USD 被挂到 /World，后面所有路径都从这里找。"],
              ["task.step", "像观察员：读取 camera、object、robot state，整理成 controller 能看的 state dict。"],
              ["controller.step", "像操作员：根据 state 决定下一步动作，同时判断 episode 是否结束。"],
              ["apply_action", "像把手伸出去：动作写入 articulation controller，下一帧物理才会真正变化。"]
            ];
            let i = 0;
            const render = () => {
              el.innerHTML = `<div class="widget">${help("按“下一步”顺着一次 episode 走，重点看每一步把什么交给下一步。")}${feedback(`${steps[i][0]}：${steps[i][1]}`)}<div class="flow-track">${steps.map((s, idx) => `<div class="flow-node ${idx === i ? "active" : ""}"><strong>${idx + 1}. ${esc(s[0])}</strong><br><span>${esc(s[1])}</span></div>`).join("")}</div><div class="seg"><button data-widget-action="prev">上一帧</button><button data-widget-action="next" class="active">下一帧</button></div></div>`;
              el.querySelector('[data-widget-action="prev"]').onclick = () => { i = (i + steps.length - 1) % steps.length; render(); };
              el.querySelector('[data-widget-action="next"]').onclick = () => { i = (i + 1) % steps.length; render(); };
            };
            render();
          };

          W["task-levels"] = el => {
            const levels = {
              Level1: ["先练一个动作", "pick/place/pour/stir/open/close。适合确认相机、机器人、物体路径是否能工作。"],
              Level2: ["把动作串起来", "例如先拿再倒。中间状态会影响下一步，失败常出现在阶段切换。"],
              Level3: ["换物体和材质", "让模型不要只记住一个瓶子、一种颜色、一个位置。"],
              Level4: ["做完整长实验", "CleanBeaker 这类任务会放大小误差，适合看 long-horizon 能力。"],
              Level5: ["机器人开始移动", "ridgebase/navigation 引入 base pose 和路径规划，已经不是单纯桌面机械臂。"]
            };
            const keys = Object.keys(levels);
            let active = keys[0];
            const render = () => {
              const item = levels[active];
              el.innerHTML = `<div class="widget">${help("点不同 level，看难度到底增加在哪里；不要只把 level 当编号。")}${feedback(`${active}：${item[0]}。${item[1]}`)}<div class="seg">${keys.map(k => `<button data-widget-action="level" class="${k === active ? "active" : ""}" data-k="${k}">${k}</button>`).join("")}</div><div class="level-card"><h3>${active} · ${item[0]}</h3><p>${item[1]}</p></div></div>`;
              el.querySelectorAll("[data-widget-action]").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
            };
            render();
          };

          W["task-boundary"] = el => {
            const cases = {
              camera: ["看 BaseTask", "图像为空、相机视角不对、segmentation 不出现，先查 camera config 和 BaseTask.setup_cameras。"],
              robot: ["看 BaseController", "机器人不动、夹爪不闭合、动作顺序怪，先查 controller.step 和 apply_action。"],
              data: ["看 DataCollector", "能动但没数据、HDF5 为空、episode 长度不对，先查 collect mode 和 DataCollector。"]
            };
            let active = "camera";
            const render = () => {
              el.innerHTML = `<div class="widget">${help("选择一个故障症状，控件会告诉你先看 Task、Controller 还是 Data。")}${feedback(`${cases[active][0]}：${cases[active][1]}`)}<div class="seg">${Object.keys(cases).map(k => `<button data-widget-action="case" class="${k === active ? "active" : ""}" data-k="${k}">${k}</button>`).join("")}</div><div class="matrix"><div class="matrix-cell"><strong>BaseTask</strong><p>负责看世界：camera、object、material、state。</p></div><div class="matrix-cell"><strong>State dict</strong><p>Task 交给 Controller 的“观察报告”。</p></div><div class="matrix-cell"><strong>BaseController</strong><p>负责做动作：control、success、collect/infer。</p></div></div></div>`;
              el.querySelectorAll("[data-widget-action]").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
            };
            render();
          };

          W["asset-map"] = el => {
            const data = {
              chemistry_lab: ["实验室房间和器材", "lab_001、lab_003、hard_task 决定桌面、设备、器材位置和 prim path。"],
              robots: ["谁来动手", "Franka、ridgeback_franka、Fetch 决定 action space、关节、夹爪和可达范围。"],
              materials: ["东西看起来像什么", "MDL/JPG/PNG 改变颜色、反光、透明度，也影响视觉模型是否学偏。"],
              navigation: ["移动时怎么避障", "navigation_lab 加 barrier map，给 Level5 的 base planner 提供简化地图。"]
            };
            const keys = Object.keys(data);
            let active = keys[0];
            const render = () => {
              const item = data[active];
              el.innerHTML = `<div class="widget">${help("点一个资产类别，看它在任务里到底影响什么。")}${feedback(`${item[0]}：${item[1]}`)}<div class="seg">${keys.map(k => `<button data-widget-action="asset" class="${k === active ? "active" : ""}" data-k="${k}">${k}</button>`).join("")}</div><div class="level-card"><strong>${active} · ${item[0]}</strong><p>${item[1]}</p></div></div>`;
              el.querySelectorAll("[data-widget-action]").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
            };
            render();
          };

          W["lab-object-assets"] = el => {
            const rows = [
              ["container", "烧杯 / beaker", "lab_001.usd: /World/beaker1, /World/beaker2, /World/beaker3; lab_003.usd/clock.usd: /World/target_beaker, /World/beaker_1..5, /World/beaker_03..05; Scene1_hard.usd: /World/target_beaker, /World/beaker_1..4, /World/beaker_hard_1, /World/beaker_hard_2; navigation lab: /World/beaker", "RigidBodyAPI + CollisionAPI on most movable beakers", "pick/place/pour/stir/shake/clean/mobile manipulation"],
              ["container", "锥形瓶 / conical bottle", "lab_001.usd: /World/conical_bottle01..04; lab_003.usd/clock.usd: /World/conical_bottle01..04; Scene1_hard.usd: /World/conical_bottle01..04", "RigidBodyAPI + CollisionAPI", "pick/pour/LiquidMixing 相关任务和 distractor objects"],
              ["container", "量筒 / graduated cylinder", "lab_001.usd: /World/graduated_cylinder_03", "RigidBodyAPI + CollisionAPI", "level3_PourLiquid 使用"],
              ["tool", "玻璃棒 / glass rod", "lab_003.usd: /World/glass_rod, /World/glass_rod/Cylinder; Scene1_hard.usd: /World/glass_rod; OpenTransportPour 使用 /World/glass_rod/mesh", "CollisionAPI; pick controller 对 glass_rod 有专门 grasp path", "stir、StirGlassrod、OpenTransportPour"],
              ["tool", "试管架 / test tube rack", "lab_003.usd: /World/test_tube_rack; Scene1_hard.usd: /World/test_tube_rack", "CollisionAPI; mostly support/static object", "stir reset 会摆放 rack；OpenTransportPour 配置引用"],
              ["device", "干燥箱 / DryingBox", "lab_001.usd: /World/DryingBox_01, /World/DryingBox_02, /World/DryingBox_03, /World/DryingBox_04", "PhysicsArticulationRootAPI; door RevoluteJoint; DryingBox_01/04 also button PrismaticJoint", "open/close door、DeviceOperation；DryingBox_04 当前主要是可用但少被 config 引用"],
              ["device", "马弗炉 / MuffleFurnace", "lab_001.usd: /World/MuffleFurnace", "PhysicsArticulationRootAPI; door RevoluteJoint; handle fixed to door; no thermal simulation", "level3_open、OpenTransportPour 的 open-door stage"],
              ["device", "加热装置 / heat_device", "lab_003.usd and clock.usd: /World/heat_device, /World/heat_device/button, /World/heat_device/heat_device/heat_device/plat", "Rigid/Collision on button/device parts; no articulated joint found", "HeatLiquid、LiquidMixing 的 place-and-press target"],
              ["button", "按钮组 / target and distractor buttons", "lab_003.usd and Scene1_hard.usd: /World/target_button, /World/target_button/button, /World/distractor_button_1, /World/distractor_button_2", "RigidBodyAPI + CollisionAPI; not USD articulated joints", "level1_press、level3_press、CleanBeaker scene objects"],
              ["device", "仪器架/实验仪器 / instrument", "lab_003.usd and Scene1_hard.usd: /World/instrument", "Visual/static support object; no rigid body in scanned top prim", "press scene 中作为按钮装置/实验设备背景"],
              ["furniture", "柜子/抽屉 / Cabinet", "lab_001.usd: /World/Cabinet_01, /World/Cabinet_02 plus drawer_handle_top", "External Omniverse payload: Sektion_Cabinet; local scan warns payload URL may not load offline", "open drawer / close drawer configs"],
              ["furniture", "实验台和桌面 / table", "lab_001.usd: /World/table; lab_003.usd/clock.usd: /World/table; Scene1_hard.usd: /World/table_hard", "Static support surfaces with CollisionAPI on relevant table/surface prims", "object placement, material variation, CleanBeaker surfaces"],
              ["furniture", "放置平台 / target platform", "lab_001.usd: /World/target_plat, /World/target_plat2; lab_003.usd: /World/target_plat; Scene1_hard.usd: /World/target_plat, /World/target_plat_1, /World/target_plat_2, /World/plat", "Support/target geometry; often static collision", "place/transport/clean success predicates"],
              ["scene", "实验室空间 / lab shell", "lab_003.usd and Scene1_hard.usd: /World/lab_015 payload -> ./SubUSDs/lab_015.usd; navigation lab: /World/lab_001 payload -> ./lab_001/lab_001.usd", "Large static lab room/furniture shell; no task-level manipulation", "background, walls, benches, navigation scene context"],
            ];
            const filters = [
              ["all", "全部"],
              ["container", "容器"],
              ["device", "设备"],
              ["tool", "工具"],
              ["button", "按钮"],
              ["furniture", "家具/平台"],
              ["scene", "场景壳"],
            ];
            const labels = Object.fromEntries(filters);
            let active = "all";
            const render = () => {
              const shown = active === "all" ? rows : rows.filter(r => r[0] === active);
              const message = `${labels[active]}：${shown.length} 类真实实验室物体。表里的路径都是 scene USD 内的 prim path。`;
              el.innerHTML = `<div class="widget">${help("按真实物体类别过滤；这里列的是 object -> scene USD -> prim path，不是文件扩展名统计。")}${feedback(message)}<div class="seg">${filters.map(([k, label]) => `<button data-widget-action="lab-object-assets" class="${k === active ? "active" : ""}" data-k="${k}">${label}</button>`).join("")}</div><div class="table-scroll"><table><thead><tr><th>类别</th><th>真实物体</th><th>USD / prim path</th><th>物理状态</th><th>任务用途</th></tr></thead><tbody>${shown.map(r => `<tr><td>${esc(labels[r[0]])}</td><td><strong>${esc(r[1])}</strong></td><td>${esc(r[2])}</td><td>${esc(r[3])}</td><td>${esc(r[4])}</td></tr>`).join("")}</tbody></table></div></div>`;
              el.querySelectorAll("[data-widget-action]").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
            };
            render();
          };

          W["dataset-flow"] = el => {
            const steps = [
              ["cache", "每步先攒 image、joint、language，不急着写文件。"],
              ["HDF5", "episode 结束后写 camera dataset、agent_pose、actions。"],
              ["dataset", "训练代码按 shape_meta 取 key，key 错就喂不进模型。"],
              ["workspace", "workspace 负责 policy、optimizer、checkpoint。"],
              ["infer", "模型动作回到 simulation，才知道学到的东西能不能执行。"]
            ];
            let active = 0;
            const render = () => {
              el.innerHTML = `<div class="widget">${help("按顺序点数据流，理解“仿真里动一下”怎样变成“模型能训练的一条样本”。")}${feedback(`${steps[active][0]}：${steps[active][1]}`)}<div class="seg">${steps.map((s, idx) => `<button data-widget-action="data-step" class="${idx === active ? "active" : ""}" data-i="${idx}">${idx + 1}</button>`).join("")}</div><div class="flow-track">${steps.map((s, idx) => `<div class="flow-node ${idx === active ? "active" : ""}"><strong>${s[0]}</strong><br>${s[1]}</div>`).join("")}</div></div>`;
              el.querySelectorAll("[data-widget-action]").forEach(btn => btn.onclick = () => { active = Number(btn.dataset.i); render(); });
            };
            render();
          };

          W["action-chunking"] = el => {
            let h = 16;
            const render = () => {
              const judgment = h < 14 ? "反应快，但每隔很短时间就要重新决定，误差更容易滚雪球。" : h > 34 ? "动作很连贯，但如果中途物体位置变了，它会慢半拍才改。" : "比较折中：既减少频繁重推，也保留一定反应速度。";
              el.innerHTML = `<div class="widget">${help("拖动 horizon，感受 action chunk 越长/越短带来的取舍。")}${feedback(`H=${h}：${judgment}`)}<label>chunk horizon: <strong>${h}</strong></label><input data-widget-action="horizon" type="range" min="4" max="50" value="${h}" step="2"><div class="matrix"><div class="matrix-cell"><strong>长 chunk</strong><p>更平滑，replan 少，但突发变化反应慢。</p></div><div class="matrix-cell"><strong>短 chunk</strong><p>反应快，但 compounding error 和网络调用更频繁。</p></div></div></div>`;
              el.querySelector("[data-widget-action]").oninput = event => { h = Number(event.target.value); render(); };
            };
            render();
          };

          W["mode-switch"] = el => {
            const modes = {
              collect: ["采集示范", "controller 自己做动作，DataCollector 把过程写成 HDF5。你要检查数据是否干净。"],
              infer: ["测试模型", "inference_engine 读模型输出动作。你要检查 checkpoint、shape_meta 和动作维度。"]
            };
            let active = "collect";
            const render = () => {
              const item = modes[active];
              el.innerHTML = `<div class="widget">${help("切换 collect/infer，看同一个 runtime 在“录老师示范”和“让学生考试”之间怎么变。")}${feedback(`${item[0]}：${item[1]}`)}<div class="seg">${Object.keys(modes).map(k => `<button data-widget-action="mode" class="${k === active ? "active" : ""}" data-k="${k}">${k}</button>`).join("")}</div><div class="level-card"><strong>${item[0]}</strong><p>${item[1]}</p></div></div>`;
              el.querySelectorAll("[data-widget-action]").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
            };
            render();
          };

          W["reuse-matrix"] = el => {
            const rows = [
              ["USD mesh/props", "可能", "需要路径、材质、scale、collision QA", "asset"],
              ["Lab scene concept", "可以移植", "需要重新写 GenManip task/scoring", "task"],
              ["Franka robot", "不直接", "EBench contract 是 lift2", "robot"],
              ["HDF5 dataset", "不直接", "EBench-Dataset 是 LeRobot v2.1 + lift2 schema", "data"],
              ["BaseTask/BaseController", "不直接", "EBench 是 client-server EvalClient", "code"]
            ];
            let active = "all";
            const render = () => {
              const shown = active === "all" ? rows : rows.filter(r => r[3] === active);
              const message = active === "all" ? "总览：只有静态视觉资产比较可能迁移，其余都要重建 contract。" : `${shown[0][0]}：${shown[0][1]}，原因是 ${shown[0][2]}。`;
              el.innerHTML = `<div class="widget">${help("点类别过滤矩阵。目标是判断“能不能直接复用”，不是只看文件能不能复制。")}${feedback(message)}<div class="seg">${["all","asset","task","robot","data","code"].map(k => `<button data-widget-action="reuse" class="${k === active ? "active" : ""}" data-k="${k}">${k}</button>`).join("")}</div><div class="table-scroll"><table><thead><tr><th>对象</th><th>复用判断</th><th>原因</th></tr></thead><tbody>${shown.map(r => `<tr><td>${r[0]}</td><td><strong>${r[1]}</strong></td><td>${r[2]}</td></tr>`).join("")}</tbody></table></div></div>`;
              el.querySelectorAll("[data-widget-action]").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
            };
            render();
          };

          W["version-bridge"] = el => {
            const data = [
              ["labutopia", "Isaac Sim 5.1", "LabUtopia README/runtime：本地安装与资产创建口径。"],
              ["ebench", "Isaac Sim 4.1", "EBench/GenManip runtime：目标 server 需要重新打开与验证。"],
              ["bridge", "Bridge", "迁移时先做 material/physics/sensor/path QA，再写 task。"]
            ];
            let active = "bridge";
            const render = () => {
              const item = data.find(d => d[0] === active);
              el.innerHTML = `<div class="widget">${help("切换版本视角，看为什么“本机能打开”不等于“EBench server 能评测”。")}${feedback(`${item[1]}：${item[2]}`)}<div class="seg">${data.map(d => `<button data-widget-action="version" class="${d[0] === active ? "active" : ""}" data-k="${d[0]}">${d[1]}</button>`).join("")}</div><div class="matrix">${data.map(d => `<div class="matrix-cell"><strong>${d[1]}</strong><p>${d[2]}</p></div>`).join("")}</div></div>`;
              el.querySelectorAll("[data-widget-action]").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
            };
            render();
          };

          W["glossary-search"] = el => {
            const terms = [
              ["SimulationApp", "Isaac Sim 的应用开关；没启动它，后面的 World/Stage 都没法正常用。"],
              ["World", "仿真每一步的管理器，负责 step、reset、play/stop。"],
              ["Stage", "USD 场景图；你在 Isaac Sim 里看到的所有 prim 都在这里。"],
              ["BaseTask", "观察员：负责相机、物体、材质、state。"],
              ["BaseController", "操作员：负责动作、成功判断、collect/infer。"],
              ["DataCollector", "记录员：把每个 episode 写成 HDF5。"],
              ["GenManip", "EBench server 背后的 Isaac Sim manipulation runtime。"],
              ["lift2", "EBench 使用的双臂移动本体。"],
              ["LeRobot", "EBench-Dataset 使用的数据格式生态。"]
            ];
            el.innerHTML = `<div class="widget">${help("输入术语，下面会显示一句人话解释。")}${feedback("先搜一个你卡住的词，例如 Stage 或 BaseTask。")}<input data-widget-action="glossary" aria-label="Glossary filter" placeholder="输入 term 过滤..." style="width:100%;padding:10px;border:1px solid var(--line);border-radius:7px;background:var(--paper);color:var(--ink)"><div class="matrix" style="margin-top:12px"></div></div>`;
            const input = el.querySelector("input");
            const box = el.querySelector(".matrix");
            const render = () => {
              const q = input.value.toLowerCase();
              const hits = terms.filter(t => `${t[0]} ${t[1]}`.toLowerCase().includes(q));
              box.innerHTML = hits.map(t => `<div class="matrix-cell"><strong>${t[0]}</strong><p>${t[1]}</p></div>`).join("");
              el.querySelector(".widget-feedback span").textContent = hits.length ? `找到 ${hits.length} 个解释；先读中文解释，再回到正文看英文术语。` : "没有匹配，换一个更短的关键词。";
            };
            input.oninput = render;
            render();
          };

          window.LUWidgets = {
            mountAll() {
              document.querySelectorAll("[data-widget]").forEach(el => {
                const name = el.dataset.widget;
                if (W[name]) W[name](el);
              });
            }
          };
        })();
        """
    ).strip() + "\n"


def shell(data_root: str, section_id: str | None, title: str, main_html: str, is_cover: bool = False) -> str:
    body_attrs = f'data-root="{data_root}"'
    if section_id:
        body_attrs += f' data-section="{section_id}"'
    layout = main_html if is_cover else f"""
    <div class="book">
      <nav class="sidebar" id="sidebar" aria-label="Book navigation"></nav>
      <main class="content">{main_html}</main>
      <aside class="rail" id="rail" aria-label="On this page"></aside>
    </div>
    """
    return dedent(
        f"""
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>{html.escape(title)} · LabUtopia Interactive Book</title>
          <link rel="stylesheet" href="{data_root}assets/css/book.css">
        </head>
        <body {body_attrs}>
          <div class="progress" id="progress"></div>
          <header class="topbar">
            <a class="brand" href="{data_root}index.html"><span class="brand-mark">LU</span><span>LabUtopia Interactive Book</span></a>
            <div class="top-actions">
              <button class="text-btn" data-search-open title="Search">Search</button>
              <button class="icon-btn" data-theme-toggle title="Theme">◐</button>
            </div>
          </header>
          {layout}
          <div class="search-overlay" id="book-search" role="dialog" aria-label="Book search">
            <div class="search-box">
              <input id="book-search-input" placeholder="搜索章节、术语或路径，例如 BaseTask / EBench-Assets / Isaac Sim">
              <div class="search-results" id="book-search-results"></div>
              <div style="padding:10px;border-top:1px solid var(--line);text-align:right"><button class="text-btn" data-search-close>关闭</button></div>
            </div>
          </div>
          <script src="{data_root}content.js"></script>
          <script src="{data_root}assets/js/widgets/book-widgets.js"></script>
          <script src="{data_root}assets/js/book.js"></script>
        </body>
        </html>
        """
    ).strip() + "\n"


def code_block(code: tuple[str, str, str] | None) -> str:
    if not code:
        return ""
    lang, name, body = code
    return f"""
    <div class="code" data-lang="{html.escape(lang)}"><div class="code-h"><span class="fn">{html.escape(name)}</span><button class="cp">复制</button></div><pre><code>{html.escape(body)}</code></pre></div>
    """


def sources_block(names: list[str]) -> str:
    if not names:
        return ""
    links = []
    for name in names:
        links.append(f'<a href="{html.escape(source_url(name))}" target="_blank" rel="noreferrer">{html.escape(name)}</a>')
    return f'<div class="callout note"><div class="c-h">Source trail</div><p>{" · ".join(links)}</p></div>'


def plain_language_blocks(part: dict, section: dict) -> str:
    title = html.escape(section["title"])
    clean_lede = html.escape(strip_tags(section["lede"]))
    first_path = html.escape(section["paths"][0]) if section["paths"] else "本节提到的配置、代码或资产路径"
    part_id = part["id"]
    analogies = {
        "00-orientation": "把它想成先画地图：你不是马上拧螺丝，而是先知道门、桌子、机器人、数据出口分别在哪里。",
        "01-paper-model": "把它想成给实验室贴标签：同一间房既可以从论文看，也可以从代码看，标签帮你不迷路。",
        "02-sim-usd": "把它想成一场舞台剧：Stage 是舞台，World 是每一拍的节奏，SimulationApp 是剧场电源。",
        "03-runtime": "把它想成一次做实验的流水线：先拿实验单，再摆场景，再观察，再动作，再记录结果。",
        "04-tasks": "把它想成学做实验动作：先练拿起、放下、倾倒，再把它们串成完整实验。",
        "05-data-policy": "把它想成给学生录示范视频：数据越清楚，后面训练出来的 policy 越不容易学偏。",
        "06-assets": "把它想成实验室仓库：不是所有瓶子都一样，位置、材质、碰撞和名字都会影响能不能用。",
        "07-ebench-assets": "把它想成搬家：东西可以搬，但门锁、插座、电压和房间布局不同，不能原封不动就开工。",
        "08-extension-debug": "把它想成修机器：先听声音判断是哪一层坏了，再拆对应零件。",
        "appendix": "把它想成书后索引：读正文卡住时回来查，不需要一次背完。",
    }
    analogy = analogies.get(part_id, "把它想成把复杂项目拆成小盒子：先看盒子之间怎么接，再看每个盒子内部。")
    return f"""
      <div class="plain-grid">
        <section class="plain-card">
          <h2 id="plain">先讲人话</h2>
          <p>{clean_lede} 换成更直白的话：这一节是在告诉你“遇到 {title} 时，应该先看哪一层，不要一上来被术语吓住”。</p>
        </section>
        <section class="plain-card">
          <h2 id="analogy">你可以这样想</h2>
          <p>{analogy}</p>
        </section>
        <section class="plain-card">
          <h2 id="checkpoint">读完你应该能回答</h2>
          <ul>
            <li>这节和一次 episode、一个 asset 或一条数据有什么关系？</li>
            <li>如果要在项目里找证据，第一眼应该打开 <span class="term">{first_path}</span>。</li>
            <li>如果这里出错，后面的 task、controller、dataset 或 EBench 复用会受什么影响？</li>
          </ul>
        </section>
      </div>
    """


def section_page(part: dict, section: dict) -> str:
    paths = ""
    if section["paths"]:
        paths = '<div class="path-grid">' + "".join(f'<div class="path">{html.escape(p)}</div>' for p in section["paths"]) + "</div>"
    widget = ""
    if section["widget"]:
        widget = f"""
        <div class="lab">
          <div class="lab-h"><span class="lab-tag">interactive</span><span class="lab-t">{html.escape(section["title"])}</span></div>
          <div class="lab-body" data-widget="{html.escape(section["widget"])}"></div>
          <div class="lab-cap">拖动、切换或逐步播放，把本节概念映射到项目结构。</div>
        </div>
        """
    notes = "".join(f"<li>{note}</li>" for note in section["notes"])
    main = f"""
    <article class="prose">
      <div class="eyebrow">{html.escape(part["title"])} · {html.escape(section["id"])}</div>
      <h1>{html.escape(section["title"])}</h1>
      <p class="lede">{section["lede"]}</p>
      {plain_language_blocks(part, section)}
      <h2 id="why">为什么它在本项目里重要</h2>
      <p>{section["angle"]}</p>
      <div class="bridge rl"><div class="c-h"><span class="tag">从 RL 看</span> 把概念落到 trajectory</div><p>这里的关键不是把术语背下来，而是看它怎样改变 episode、observation、action、success 和 dataset distribution。</p></div>
      <h2 id="where">从代码和资产落地</h2>
      <p>{section["walk"]}</p>
      {paths}
      {code_block(section["code"])}
      {widget}
      <h2 id="practice">读论文和跑实验时怎么用</h2>
      <p>{section["use"]}</p>
      <div class="callout warn"><div class="c-h">本节要记住</div><ul class="note-list">{notes}</ul></div>
      {sources_block(section["source_keys"])}
      <div id="pager" class="pager"></div>
    </article>
    """
    return shell("../../", section["id"], section["title"], main)


def index_page(meta: dict) -> str:
    toc = []
    for part in meta["parts"]:
        items = "".join(f'<li><a href="{html.escape(s["file"])}">{html.escape(s["id"])} · {html.escape(s["title"])}</a></li>' for s in part["sections"])
        toc.append(f'<section class="toc-card"><h2>{html.escape(part["title"])}</h2><p>{html.escape(part["kicker"])}</p><ol>{items}</ol></section>')
    source_cards = "".join(f'<div class="source-card"><strong>{html.escape(s["name"])}</strong><br><a href="{html.escape(s["url"])}">{html.escape(s["url"])}</a></div>' for s in meta["sources"])
    main = f"""
    <main class="cover">
      <section class="hero">
        <div>
          <div class="eyebrow">LabUtopia · Isaac Sim · OpenUSD · VLA</div>
          <h1>LabUtopia Interactive Book</h1>
          <p>一本面向已有一点强化学习、Isaac Sim 和 USD 资产基础读者的长教程。中文用于解释性叙述，English terms 保留架构术语、命令名、性能指标和论文概念。</p>
          <div class="hero-actions">
            <a href="{html.escape(meta["parts"][0]["sections"][0]["file"])}">开始阅读</a>
            <a href="{html.escape(meta["parts"][7]["sections"][0]["file"])}">直接看 EBench 资产对比</a>
          </div>
        </div>
      </section>
      <section>
        <h2 id="toc">目录</h2>
        <div class="cover-toc">
          {"".join(toc)}
        </div>
      </section>
      <section>
        <h2 id="sources">资料来源</h2>
        <p>本书先收集 whitepaper/paper、Isaac Sim/OpenUSD docs、EBench docs、Hugging Face dataset pages 与本地代码，再整合为教程。下面链接也会在相关章节中出现。</p>
        <div class="source-grid">{source_cards}</div>
      </section>
    </main>
    """
    return shell("./", None, "Home", main, is_cover=True)


def readme() -> str:
    meta = metadata()
    count = sum(len(p["sections"]) for p in meta["parts"])
    return dedent(
        f"""
        # LabUtopia Interactive Book

        这是一份多章节 HTML 教程，面向已经有一点 RL、Isaac Sim 和 USD 资产基础的读者，目标是把 LabUtopia 项目从论文概念、runtime、task/controller、data/policy、assets 到 EBench 资产复用判断讲清楚。

        - 章节数：{count}
        - 入口：`learn/index.html`
        - 目录源：`learn/content.js`
        - 样式：`learn/assets/css/book.css`
        - 导航与搜索：`learn/assets/js/book.js`
        - 交互控件：`learn/assets/js/widgets/book-widgets.js`
        - 校验：`python3 learn/validate.py`
        - 视觉审查：先启动 `python3 -m http.server 8099 --bind 127.0.0.1`，临时安装 `npm install --no-save @playwright/test` 后运行 `npx playwright test learn/visual_audit.spec.js --reporter=line`

        内容组织参考了 `/cpfs/shared/simulation/zhuzihou/dev/EBench/learn` 的 book scaffold，但章节事实和写作结构重新围绕 LabUtopia、本地代码和外部资料整理。
        """
    ).strip() + "\n"


def design_doc() -> str:
    return dedent(
        """
        # LabUtopia Learn Design

        目标：把 `learn/` 从单页说明改成多章节互动书，既能解释 LabUtopia 项目，也能系统比较 LabUtopia assets 与 EBench assets。

        结构：
        - `content.js` 是目录单一来源。
        - 每个章节是完整 HTML，可直接由 GitHub Pages 服务。
        - `book.js` 负责 sidebar、search、theme、progress、pager 和右侧目录。
        - `book-widgets.js` 提供 runtime loop、task levels、asset map、dataset flow、reuse matrix、version bridge 等交互控件。
        - `validate.py` 检查章节数量、关键事实、来源链接、资产对比章节和 widget 覆盖。

        写作口径：
        - 中文解释，English terms 保留。
        - 公开资料与本地代码事实分开陈述。
        - 资产复用结论：LabUtopia assets 不能直接复用到 EBench；可经过 conversion workflow、task/eval contract 重建和 visual QA 迁移。
        """
    ).strip() + "\n"


def write_book() -> None:
    meta = metadata()

    for path in [ROOT / "chapters", ROOT / "assets"]:
        if path.exists():
            shutil.rmtree(path)

    (ROOT / "assets/css").mkdir(parents=True, exist_ok=True)
    (ROOT / "assets/js/widgets").mkdir(parents=True, exist_ok=True)
    (ROOT / "chapters").mkdir(parents=True, exist_ok=True)

    (ROOT / ".nojekyll").write_text("", encoding="utf-8")
    (ROOT / "content.js").write_text("window.LABUTOPIA_BOOK = " + json.dumps(meta, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
    (ROOT / "index.html").write_text(index_page(meta), encoding="utf-8")
    (ROOT / "assets/css/book.css").write_text(css(), encoding="utf-8")
    (ROOT / "assets/js/book.js").write_text(book_js(), encoding="utf-8")
    (ROOT / "assets/js/widgets/book-widgets.js").write_text(widgets_js(), encoding="utf-8")
    (ROOT / "README.md").write_text(readme(), encoding="utf-8")
    (ROOT / "DESIGN.md").write_text(design_doc(), encoding="utf-8")

    for part in PARTS:
        part_dir = ROOT / "chapters" / part["id"]
        part_dir.mkdir(parents=True, exist_ok=True)
        for section in part["sections"]:
            (ROOT / slug_section(part["id"], section)).write_text(section_page(part, section), encoding="utf-8")


if __name__ == "__main__":
    write_book()
