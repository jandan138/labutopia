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
