window.LABUTOPIA_BOOK = {
  "title": "LabUtopia Interactive Book",
  "subtitle": "从 Isaac Sim + USD 基础到 LabUtopia 架构、数据、资产与 EBench 复用判断",
  "updated": "2026-06-02",
  "parts": [
    {
      "id": "00-orientation",
      "title": "Part 0 · 先把整座实验室看成一张图",
      "kicker": "从只会点 Isaac Sim 到能读懂项目",
      "sections": [
        {
          "id": "0-1",
          "title": "为什么 LabUtopia 不是一个普通仿真 demo",
          "file": "chapters/00-orientation/0-1-why-labutopia.html",
          "summary": "如果你只把 LabUtopia 当成一批 USD 场景，就会错过它真正的结构：它同时是 scientific embodied agents 的仿真环境、任务层级和数据生成入口。"
        },
        {
          "id": "0-2",
          "title": "读者画像：从 RL 和 USD 点选经验出发",
          "file": "chapters/00-orientation/0-2-reader-map.html",
          "summary": "这本书假设你知道 reward、policy、trajectory 这些 RL 词，也知道 Isaac Sim 里可以点开 USD stage，但还没有把 benchmark、dataset、controller 串起来。"
        },
        {
          "id": "0-3",
          "title": "本书目录如何组织",
          "file": "chapters/00-orientation/0-3-book-map.html",
          "summary": "目录不是简单罗列文件，而是按“论文概念 → 仿真栈 → runtime → task/controller → data/policy → assets → EBench 对比”的依赖顺序展开。"
        },
        {
          "id": "0-4",
          "title": "资料口径：哪些是论文事实，哪些是本地事实",
          "file": "chapters/00-orientation/0-4-evidence-rules.html",
          "summary": "项目理解最怕把论文愿景、本地 README、外部 benchmark 文档和代码事实混成一句话。本书会把来源口径拆开。"
        }
      ]
    },
    {
      "id": "01-paper-model",
      "title": "Part 1 · 从论文模型建立 LabUtopia 心智地图",
      "kicker": "LabSim, LabScene, LabBench",
      "sections": [
        {
          "id": "1-1",
          "title": "LabSim：不是渲染器，而是实验闭环",
          "file": "chapters/01-paper-model/1-1-labsim-loop.html",
          "summary": "LabSim 可以先粗略理解为“让实验室任务真正动起来的 simulation runtime”，它把场景、物体、机器人、传感器和 episode loop 放进同一个执行语境。"
        },
        {
          "id": "1-2",
          "title": "LabScene：scientific laboratory 的空间语义",
          "file": "chapters/01-paper-model/1-2-labscene-semantics.html",
          "summary": "LabScene 不是“漂亮的实验室背景”，而是把化学实验任务需要的 workspace、器材、台面、门抽屉、加热设备、导航障碍放进可引用的 USD hierarchy。"
        },
        {
          "id": "1-3",
          "title": "LabBench：层级任务为什么要分 level",
          "file": "chapters/01-paper-model/1-3-labbench-levels.html",
          "summary": "LabBench 的价值在于把科学实验能力拆成层级：atomic skill、combined skill、generalization、long horizon、mobility，不同 level 让 failure diagnosis 更具体。"
        },
        {
          "id": "1-4",
          "title": "科学实验任务和 household manipulation 的根本差异",
          "file": "chapters/01-paper-model/1-4-science-vs-household.html",
          "summary": "LabUtopia 和 EBench 都在 Isaac Sim 语境里，但一个强调 scientific laboratory，一个强调 indoor/mobile manipulation。这个差异会一路影响资产、任务、动作和评测。"
        },
        {
          "id": "1-5",
          "title": "指标和成功条件：别把 reward 想得太早",
          "file": "chapters/01-paper-model/1-5-metrics-success.html",
          "summary": "有 RL 背景的读者容易立刻找 reward function，但 LabUtopia 里更直接的入口是 task success condition、episode completion 和 data collection outcome。"
        }
      ]
    },
    {
      "id": "02-sim-usd",
      "title": "Part 2 · Isaac Sim 与 OpenUSD 基础",
      "kicker": "把点选经验变成工程理解",
      "sections": [
        {
          "id": "2-1",
          "title": "SimulationApp, World, Stage 三件事",
          "file": "chapters/02-sim-usd/2-1-simulationapp-world-stage.html",
          "summary": "LabUtopia 的第一行关键代码不是 robot，也不是 task，而是 SimulationApp。它决定 Isaac Sim runtime 能否启动，后面的 World 与 Stage 都在它之后才有意义。"
        },
        {
          "id": "2-2",
          "title": "OpenUSD：prim path 为什么像 API",
          "file": "chapters/02-sim-usd/2-2-openusd-prim-path.html",
          "summary": "在 LabUtopia 里，USD 的 prim path 不只是 UI 中的树节点名字，它实际承担了对象寻址、camera 初始化、material binding 和 success check 的 API 角色。"
        },
        {
          "id": "2-3",
          "title": "PhysX 与 articulation：动作怎么变成运动",
          "file": "chapters/02-sim-usd/2-3-physx-articulation.html",
          "summary": "你在 policy 里看到的是 action array，但 Isaac Sim 里真正动起来的是 robot articulation、joint target、gripper command 和 physics step。"
        },
        {
          "id": "2-4",
          "title": "RTX Renderer 与 cameras：数据集里的 image 从哪里来",
          "file": "chapters/02-sim-usd/2-4-rtx-cameras.html",
          "summary": "LabUtopia 的 image observation 来自 Isaac Sim camera sensor，而不是事后截图。camera 配置决定了训练数据的视角、分辨率、image type 和可见信息。"
        },
        {
          "id": "2-5",
          "title": "版本现实：Isaac Sim 5.1 与 4.1 的差别要认真对待",
          "file": "chapters/02-sim-usd/2-5-version-reality.html",
          "summary": "LabUtopia 本地 README 要求 Isaac Sim 5.1，而 EBench/GenManip 资料使用 Isaac Sim 4.1。资产复用时，这不是小版本洁癖。"
        }
      ]
    },
    {
      "id": "03-runtime",
      "title": "Part 3 · Runtime Architecture",
      "kicker": "从 main.py 读懂一次 episode",
      "sections": [
        {
          "id": "3-1",
          "title": "Hydra config 是整条链的入口",
          "file": "chapters/03-runtime/3-1-hydra-config-entry.html",
          "summary": "LabUtopia 的 task 不是在命令行里硬编码出来的，而是由 Hydra config 决定 task_type、controller_type、usd_path、robot、camera 和 collect/infer mode。"
        },
        {
          "id": "3-2",
          "title": "Factory pattern：字符串如何变成 class",
          "file": "chapters/03-runtime/3-2-factory-pattern.html",
          "summary": "配置里写的是 task_type 和 controller_type，但运行时需要具体 Python class。LabUtopia 用 factory 把这一步集中管理。"
        },
        {
          "id": "3-3",
          "title": "Task/Controller boundary：谁看世界，谁做动作",
          "file": "chapters/03-runtime/3-3-task-controller-boundary.html",
          "summary": "LabUtopia 的 README 已经给出设计哲学：scene state 和 observation acquisition 由 tasks 处理，robot control 与 success condition checking 由 controllers 处理。"
        },
        {
          "id": "3-4",
          "title": "一次 world.step 到底发生什么",
          "file": "chapters/03-runtime/3-4-one-world-step.html",
          "summary": "main loop 的每一轮都先 world.step(render=True)，然后根据 world 状态、reset flag、task state 和 controller action 决定下一步。"
        },
        {
          "id": "3-5",
          "title": "ObjectUtils 与 scene query",
          "file": "chapters/03-runtime/3-5-object-utils.html",
          "summary": "LabUtopia 很多任务都需要知道物体中心、尺寸、位置和可见性，这些 scene query 被集中在 ObjectUtils 和 task helper 中。"
        },
        {
          "id": "3-6",
          "title": "Collect mode 与 infer mode",
          "file": "chapters/03-runtime/3-6-collect-infer-mode.html",
          "summary": "同一个 controller base 同时支持 collect 和 infer，这让 LabUtopia 既能生成 demonstration，也能把训练好的 policy 放回 simulation 中测试。"
        }
      ]
    },
    {
      "id": "04-tasks",
      "title": "Part 4 · Tasks 与 Controllers",
      "kicker": "从 level1 到 level5",
      "sections": [
        {
          "id": "4-1",
          "title": "Level1 atomic skill：pick/place/pour/stir 的意义",
          "file": "chapters/04-tasks/4-1-level1-atomic.html",
          "summary": "Level1 task 看似简单，却是理解所有高阶任务的基础。它们把一个动作技能拆到足够短，让你能定位 robot、object、camera、success condition 哪一层出错。"
        },
        {
          "id": "4-2",
          "title": "Level2 combined skill：组合不是简单相加",
          "file": "chapters/04-tasks/4-2-level2-combined.html",
          "summary": "Level2 把多个 atomic skill 接起来，例如 pick 后 pour、place 后 press、transport beaker、openclose。组合的难点不只是多了步骤，而是中间状态成为下一步的初始条件。"
        },
        {
          "id": "4-3",
          "title": "Level3 generalization：object/material/instruction 的变化",
          "file": "chapters/04-tasks/4-3-level3-generalization.html",
          "summary": "Level3 让任务不再只围绕一个固定对象或材质。它通过 object list、position range、material_paths、inference test material 等机制制造泛化压力。"
        },
        {
          "id": "4-4",
          "title": "Level4 long horizon：CleanBeaker 作为案例",
          "file": "chapters/04-tasks/4-4-level4-cleanbeaker.html",
          "summary": "Long-horizon task 最适合暴露 embodied agents 的真实短板：不是不会抓，而是步骤多、误差积累、状态切换和成功条件都更脆弱。"
        },
        {
          "id": "4-5",
          "title": "Level5 mobility：navigation 与 mobile manipulation",
          "file": "chapters/04-tasks/4-5-level5-mobility.html",
          "summary": "Level5 引入移动底盘，LabUtopia 从 table-top manipulation 进入 navigation/mobile manipulation，robot type 也从 Franka 切到 ridgebase。"
        },
        {
          "id": "4-6",
          "title": "Atomic controllers 与高阶 controller 的关系",
          "file": "chapters/04-tasks/4-6-atomic-to-composite.html",
          "summary": "controllers/atomic_actions 里有 move、pick、place、pour、press、shake、stir 等低层控制器，高阶 controller 往往把这些动作组合成任务阶段。"
        }
      ]
    },
    {
      "id": "05-data-policy",
      "title": "Part 5 · Data 与 Policy",
      "kicker": "从 HDF5 episode 到 learned action",
      "sections": [
        {
          "id": "5-1",
          "title": "DataCollector：episode 如何写成 HDF5",
          "file": "chapters/05-data-policy/5-1-data-collector.html",
          "summary": "LabUtopia 的 demonstration 数据不是随手存几张图，而是按 episode 写入 HDF5，并在 meta/episode.jsonl 中记录任务文本和长度。"
        },
        {
          "id": "5-2",
          "title": "Language instruction：文字不是装饰",
          "file": "chapters/05-data-policy/5-2-language-instruction.html",
          "summary": "对于 VLA 或 language-conditioned imitation learning，language_instruction 是 observation 的一部分，不只是日志里的一句话。"
        },
        {
          "id": "5-3",
          "title": "ACT：Action Chunking Transformer 为什么适合长序列",
          "file": "chapters/05-data-policy/5-3-act-action-chunking.html",
          "summary": "Action Chunking Transformer 的核心直觉是：不要每一步都重新预测一个动作，而是一次预测未来一段 action chunk，减少 compounding error。"
        },
        {
          "id": "5-4",
          "title": "Diffusion Policy：连续动作分布的另一种写法",
          "file": "chapters/05-data-policy/5-4-diffusion-policy.html",
          "summary": "Diffusion Policy 把 robot action 看成条件生成问题：给定 image/state/language observation，逐步从噪声中生成连续 action trajectory。"
        },
        {
          "id": "5-5",
          "title": "训练 workspace：Hydra 到 BaseWorkspace",
          "file": "chapters/05-data-policy/5-5-training-workspace.html",
          "summary": "训练入口 train.py 很短，但它背后依赖 Hydra 根据配置实例化 workspace，再由 workspace 组织 dataset、policy、optimizer、checkpoint 和 validation。"
        }
      ]
    },
    {
      "id": "06-assets",
      "title": "Part 6 · LabUtopia Assets",
      "kicker": "USD, MDL, robots, navigation",
      "sections": [
        {
          "id": "6-1",
          "title": "资产树总览：471 个文件如何服务任务",
          "file": "chapters/06-assets/6-1-asset-tree.html",
          "summary": "LabUtopia 本地 assets 不是巨型外部数据包，而是一组随 repo 管理的 USD/MDL/texture/robot/navigation 资产，直接被 config 引用。"
        },
        {
          "id": "6-2",
          "title": "Lab object assets：真实实验室物体对应哪些 USD",
          "file": "chapters/06-assets/6-2-asset-census.html",
          "summary": "这一页只回答一个更具体的问题：实验室里真实出现的物体，分别落在哪个 scene USD 和哪个 /World prim path 上。"
        },
        {
          "id": "6-3",
          "title": "Chemistry lab scenes：lab_001, lab_003, hard_task",
          "file": "chapters/06-assets/6-3-chemistry-scenes.html",
          "summary": "chemistry_lab 是 LabUtopia 最核心的资产目录，它把实验台、器材、设备和任务对象组织成可被 task config 引用的 USD 场景。"
        },
        {
          "id": "6-4",
          "title": "Robots：Franka, ridgeback_franka, Fetch",
          "file": "chapters/06-assets/6-4-robots.html",
          "summary": "LabUtopia 当前任务主要围绕 Franka 和 ridgeback_franka，Fetch 资产也存在，但本地 config 的主线是 Franka 桌面操作与 ridgebase 移动任务。"
        },
        {
          "id": "6-5",
          "title": "Materials 与 MDL：视觉真实度背后的依赖",
          "file": "chapters/06-assets/6-5-materials-mdl.html",
          "summary": "LabUtopia assets 中 .mdl 文件数量很高，说明材料系统是 high-fidelity scene 的重要组成部分。材质迁移往往比 mesh 迁移更容易被低估。"
        },
        {
          "id": "6-6",
          "title": "Navigation assets：barrier map 与移动任务",
          "file": "chapters/06-assets/6-6-navigation-assets.html",
          "summary": "Level5 navigation 不只依赖 navigation_lab USD，还依赖 barrier image 和路径规划工具。这里的资产开始从纯 3D 场景扩展到 planning representation。"
        }
      ]
    },
    {
      "id": "07-ebench-assets",
      "title": "Part 7 · LabUtopia Assets 与 EBench Assets 深度对比",
      "kicker": "区别、关系、能否复用",
      "sections": [
        {
          "id": "7-1",
          "title": "先给结论：不能直接复用，但可以迁移改造",
          "file": "chapters/07-ebench-assets/7-1-reuse-answer.html",
          "summary": "LabUtopia assets 不能直接复用到 EBench；更准确地说，它们 not plug-and-play，但可作为 source assets 经过 conversion workflow、task/eval contract 重建和 visual QA 后进入 EBench/GenManip 风格任务。"
        },
        {
          "id": "7-2",
          "title": "EBench assets 是什么：外部 Hugging Face 资产包",
          "file": "chapters/07-ebench-assets/7-2-what-are-ebench-assets.html",
          "summary": "EBench entry repo 本身并不把 benchmark assets 全部放在 Git 里；它把前门、baselines、scripts 留在 GitHub，把核心 assets 和 dataset 放到 Hugging Face。"
        },
        {
          "id": "7-3",
          "title": "资产 taxonomy：LabUtopia 与 EBench 的侧重点",
          "file": "chapters/07-ebench-assets/7-3-asset-taxonomy.html",
          "summary": "LabUtopia assets 的 taxonomy 更像 scientific lab kit；EBench assets 的 taxonomy 更像 indoor mobile manipulation benchmark kit。"
        },
        {
          "id": "7-4",
          "title": "Embodiment mismatch：Franka/ridgeback_franka 对 lift2",
          "file": "chapters/07-ebench-assets/7-4-embodiment-mismatch.html",
          "summary": "最硬的差异是 robot embodiment。LabUtopia 的主线是 Franka 与 ridgeback_franka；EBench 的评测 contract 是 lift2 dual-arm mobile base。"
        },
        {
          "id": "7-5",
          "title": "Simulation version mismatch：Isaac Sim 5.1 对 4.1",
          "file": "chapters/07-ebench-assets/7-5-sim-version-mismatch.html",
          "summary": "LabUtopia README 明确 Isaac Sim 5.1；EBench/GenManip 文档口径是 Isaac Sim 4.1。资产能否打开、材料能否显示、physics 是否一致，都要在目标版本验证。"
        },
        {
          "id": "7-6",
          "title": "Task/eval contract mismatch：BaseTask 不是 EvalClient",
          "file": "chapters/07-ebench-assets/7-6-task-eval-contract.html",
          "summary": "LabUtopia 的任务契约是 Hydra config + BaseTask + BaseController；EBench 的评测契约是 GenManip server + gmp submit/eval + EvalClient observation/action schema。"
        },
        {
          "id": "7-7",
          "title": "Dataset format mismatch：HDF5 episode 对 LeRobot v2.1",
          "file": "chapters/07-ebench-assets/7-7-dataset-format-mismatch.html",
          "summary": "LabUtopia 的 DataCollector 写 HDF5 episode；EBench-Dataset 使用 LeRobot v2.1。数据不能直接互当训练集，除非做格式转换和语义对齐。"
        },
        {
          "id": "7-8",
          "title": "Conversion workflow：从 LabUtopia USD 到 EBench task",
          "file": "chapters/07-ebench-assets/7-8-conversion-workflow.html",
          "summary": "如果真的要把 LabUtopia 的实验室资产带到 EBench，推荐按 workflow 做，而不是一次性复制目录后祈祷它能跑。"
        },
        {
          "id": "7-9",
          "title": "Visual QA：资产迁移必须反复看真实渲染",
          "file": "chapters/07-ebench-assets/7-9-visual-qa.html",
          "summary": "资产比较不能只在文本里完成。LabUtopia 与 EBench 的迁移必须反复做 visual QA，因为材料、尺度、碰撞和 camera 可见性都会在渲染中暴露。"
        }
      ]
    },
    {
      "id": "08-extension-debug",
      "title": "Part 8 · 扩展与 Debug",
      "kicker": "如何安全地改项目",
      "sections": [
        {
          "id": "8-1",
          "title": "新增一个 task 的最小路径",
          "file": "chapters/08-extension-debug/8-1-new-task-path.html",
          "summary": "新增 task 不应该从复制整个 controller 开始，而应该从 contract 列表开始：config、asset、task class、controller class、factory、data shape、success condition。"
        },
        {
          "id": "8-2",
          "title": "新增资产前的 checklist",
          "file": "chapters/08-extension-debug/8-2-asset-checklist.html",
          "summary": "新增 USD/MDL/texture 资产时，先做 checklist。否则后面 controller、dataset、policy 都会替资产问题背锅。"
        },
        {
          "id": "8-3",
          "title": "常见 failure mode：从症状定位层级",
          "file": "chapters/08-extension-debug/8-3-failure-modes.html",
          "summary": "LabUtopia 的错误大多可以按层级定位：environment、asset、task、controller、data、policy。先定位层级，再谈修复。"
        },
        {
          "id": "8-4",
          "title": "从网页教程回到真实项目：推荐阅读顺序",
          "file": "chapters/08-extension-debug/8-4-reading-order.html",
          "summary": "如果你要真正掌握项目，不要按文件树从上到下读。按一次 episode 的数据流读，效率更高。"
        },
        {
          "id": "8-5",
          "title": "Capstone：把一个小实验跑完整",
          "file": "chapters/08-extension-debug/8-5-capstone.html",
          "summary": "最后，用一个小实验把整本书串起来：选择 level1_pick，确认 assets，collect 少量 episode，检查 HDF5，再用训练配置理解输入输出。"
        },
        {
          "id": "8-6",
          "title": "新手跑起来：环境、踩坑和 expert 视频",
          "file": "chapters/08-extension-debug/8-6-run-locally.html",
          "summary": "面向第一次接手项目的人，用通俗步骤解释当前可用环境、Isaac Sim 启动前检查、smoke run、expert 视频录制、常见坑和 29 个视频批跑的正确口径。"
        }
      ]
    },
    {
      "id": "appendix",
      "title": "Appendix · 查阅资料",
      "kicker": "术语、命令、链接、文件地图",
      "sections": [
        {
          "id": "A-1",
          "title": "Glossary：中英文术语对照",
          "file": "chapters/appendix/a-1-glossary.html",
          "summary": "本附录把书中反复出现的 English terms 放在一起，便于你读论文、代码和 docs 时保持同一套词表。"
        },
        {
          "id": "A-2",
          "title": "Commands：常用命令速查",
          "file": "chapters/appendix/a-2-commands.html",
          "summary": "这里收集本书涉及的常用命令，方便你从阅读切到实践。"
        },
        {
          "id": "A-3",
          "title": "Local file map：从概念到文件",
          "file": "chapters/appendix/a-3-local-file-map.html",
          "summary": "这页把概念映射到本地文件，方便你回到 IDE 中查证。"
        },
        {
          "id": "A-4",
          "title": "References：本书使用的公开资料",
          "file": "chapters/appendix/a-4-references.html",
          "summary": "本书先收集公开资料，再结合本地代码和领域知识综合解释。下面是核心来源，便于你继续追原文。"
        }
      ]
    }
  ],
  "sources": [
    {
      "name": "LabUtopia arXiv",
      "url": "https://arxiv.org/abs/2505.22634"
    },
    {
      "name": "LabUtopia NeurIPS 2025 abstract",
      "url": "https://proceedings.neurips.cc/paper_files/paper/2025/hash/313d6659e6532e6ba192dfb910d4261e-Abstract-Datasets_and_Benchmarks_Track.html"
    },
    {
      "name": "LabUtopia project page",
      "url": "https://rui-li023.github.io/labutopia-site/"
    },
    {
      "name": "LabUtopia Dataset",
      "url": "https://huggingface.co/datasets/Ruinwalker/Labutopia-Dataset"
    },
    {
      "name": "EBench repository",
      "url": "https://github.com/InternRobotics/EBench"
    },
    {
      "name": "EBench docs",
      "url": "https://internrobotics.github.io/EBench-doc/"
    },
    {
      "name": "EBench-Assets",
      "url": "https://huggingface.co/datasets/InternRobotics/EBench-Assets"
    },
    {
      "name": "EBench-Dataset",
      "url": "https://huggingface.co/datasets/InternRobotics/EBench-Dataset"
    },
    {
      "name": "GenManip arXiv",
      "url": "https://arxiv.org/abs/2506.10966"
    },
    {
      "name": "Isaac Sim docs",
      "url": "https://docs.isaacsim.omniverse.nvidia.com/latest/index.html"
    },
    {
      "name": "Isaac Sim 5.1 docs",
      "url": "https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/download.html"
    },
    {
      "name": "OpenUSD introduction",
      "url": "https://openusd.org/release/intro.html"
    },
    {
      "name": "LeRobot docs",
      "url": "https://huggingface.co/docs/lerobot/main/en/index"
    },
    {
      "name": "Hydra docs",
      "url": "https://hydra.cc/docs/intro/"
    },
    {
      "name": "Diffusion Policy",
      "url": "https://arxiv.org/abs/2303.04137"
    },
    {
      "name": "Action Chunking Transformer",
      "url": "https://arxiv.org/abs/2304.13705"
    }
  ]
};
