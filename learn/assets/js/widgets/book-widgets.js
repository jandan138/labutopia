(() => {
  const W = {};

  W["runtime-loop"] = el => {
    const steps = [
      ["Hydra cfg", "config-name 决定 task/controller/usd/robot/cameras"],
      ["Stage reference", "add_reference_to_stage 把 USD 放进 /World"],
      ["task.step", "读取 camera/object/robot state"],
      ["controller.step", "输出 action, done, is_success"],
      ["apply_action", "articulation controller 写入动作并进入下一帧"]
    ];
    let i = 0;
    const render = () => {
      el.innerHTML = `<div class="widget"><div class="flow-track">${steps.map((s, idx) => `<div class="flow-node ${idx === i ? "active" : ""}"><strong>${idx + 1}. ${s[0]}</strong><br><span>${s[1]}</span></div>`).join("")}</div><div class="seg"><button data-prev>上一帧</button><button data-next class="active">下一帧</button></div></div>`;
      el.querySelector("[data-prev]").onclick = () => { i = (i + steps.length - 1) % steps.length; render(); };
      el.querySelector("[data-next]").onclick = () => { i = (i + 1) % steps.length; render(); };
    };
    render();
  };

  W["task-levels"] = el => {
    const levels = {
      Level1: "atomic skill: pick/place/pour/stir/open/close，用来定位最小 failure mode。",
      Level2: "combined skill: 多个 atomic action 串联，中间状态成为下一阶段条件。",
      Level3: "generalization: object/material/instruction/background variation。",
      Level4: "long horizon: CleanBeaker 等任务暴露 phase drift 和 compounding error。",
      Level5: "mobility: ridgebase/navigation/mobile manipulation 改变 action space。"
    };
    const keys = Object.keys(levels);
    let active = keys[0];
    const render = () => {
      el.innerHTML = `<div class="widget"><div class="seg">${keys.map(k => `<button class="${k === active ? "active" : ""}" data-k="${k}">${k}</button>`).join("")}</div><div class="level-card"><h3>${active}</h3><p>${levels[active]}</p></div></div>`;
      el.querySelectorAll("button").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
    };
    render();
  };

  W["task-boundary"] = el => {
    el.innerHTML = `<div class="matrix"><div class="matrix-cell"><strong>BaseTask</strong><p>camera, object, material, state, reset flag</p><div class="meter"><span style="--w: 78%"></span></div></div><div class="matrix-cell"><strong>State dict</strong><p>joint_positions, camera_data, gripper_position, object/target info</p><div class="meter"><span style="--w: 56%"></span></div></div><div class="matrix-cell"><strong>BaseController</strong><p>action generation, collect/infer, RMPFlow, success, DataCollector</p><div class="meter"><span style="--w: 82%"></span></div></div></div>`;
  };

  W["asset-map"] = el => {
    const data = {
      chemistry_lab: "lab_001, lab_003, hard_task/Scene1_hard: table-top 与 long-horizon scientific lab scene。",
      robots: "Franka.usd, ridgeback_franka.usd, Fetch: robot embodiment 与 control contract。",
      materials: "MDL/JPG/PNG: material binding 与 visual generalization。",
      navigation: "navigation_lab + barrier/lab_1.png: mobile task 的 planning representation。"
    };
    const keys = Object.keys(data);
    let active = keys[0];
    const render = () => {
      el.innerHTML = `<div class="widget"><div class="seg">${keys.map(k => `<button class="${k === active ? "active" : ""}" data-k="${k}">${k}</button>`).join("")}</div><div class="level-card"><strong>${active}</strong><p>${data[active]}</p></div></div>`;
      el.querySelectorAll("button").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
    };
    render();
  };

  W["dataset-flow"] = el => {
    el.innerHTML = `<div class="flow-track"><div class="flow-node active"><strong>camera/state cache</strong><br>每步缓存 image 与 joint</div><div class="flow-node"><strong>episode HDF5</strong><br>agent_pose/actions/language</div><div class="flow-node"><strong>dataset class</strong><br>读取 shape_meta 与 obs key</div><div class="flow-node"><strong>workspace</strong><br>policy/optimizer/checkpoint</div><div class="flow-node"><strong>infer mode</strong><br>模型动作回到 simulation</div></div>`;
  };

  W["action-chunking"] = el => {
    let h = 16;
    const render = () => {
      el.innerHTML = `<div class="widget"><label>chunk horizon: <strong>${h}</strong></label><input type="range" min="4" max="50" value="${h}" step="2"><div class="matrix"><div class="matrix-cell"><strong>长 chunk</strong><p>更平滑，replan 少，但突发变化反应慢。</p></div><div class="matrix-cell"><strong>短 chunk</strong><p>反应快，但 compounding error 和网络调用更频繁。</p></div></div></div>`;
      el.querySelector("input").oninput = event => { h = event.target.value; render(); };
    };
    render();
  };

  W["mode-switch"] = el => {
    const modes = {
      collect: "create_collector → controller 规则/规划动作 → HDF5 episode",
      infer: "trajectory_controller + inference_engine → local/remote/replay model action"
    };
    let active = "collect";
    const render = () => {
      el.innerHTML = `<div class="seg">${Object.keys(modes).map(k => `<button class="${k === active ? "active" : ""}" data-k="${k}">${k}</button>`).join("")}</div><div class="level-card">${modes[active]}</div>`;
      el.querySelectorAll("button").forEach(btn => btn.onclick = () => { active = btn.dataset.k; render(); });
    };
    render();
  };

  W["reuse-matrix"] = el => {
    const rows = [
      ["USD mesh/props", "可能", "需要路径、材质、scale、collision QA"],
      ["Lab scene concept", "可以移植", "需要重新写 GenManip task/scoring"],
      ["Franka robot", "不直接", "EBench contract 是 lift2"],
      ["HDF5 dataset", "不直接", "EBench-Dataset 是 LeRobot v2.1 + lift2 schema"],
      ["BaseTask/BaseController", "不直接", "EBench 是 client-server EvalClient"]
    ];
    el.innerHTML = `<div class="table-scroll"><table><thead><tr><th>对象</th><th>复用判断</th><th>原因</th></tr></thead><tbody>${rows.map(r => `<tr><td>${r[0]}</td><td><strong>${r[1]}</strong></td><td>${r[2]}</td></tr>`).join("")}</tbody></table></div>`;
  };

  W["version-bridge"] = el => {
    const data = [
      ["Isaac Sim 5.1", "LabUtopia README/runtime", "本地安装与资产创建口径"],
      ["Isaac Sim 4.1", "EBench/GenManip runtime", "目标 server 需要重新打开与验证"],
      ["Bridge", "conversion workflow", "material/physics/sensor/path QA 后再写 task"]
    ];
    el.innerHTML = `<div class="matrix">${data.map(d => `<div class="matrix-cell"><strong>${d[0]}</strong><p>${d[1]}</p><span>${d[2]}</span></div>`).join("")}</div>`;
  };

  W["glossary-search"] = el => {
    const terms = ["SimulationApp", "World", "Stage", "OpenUSD", "PhysX", "RTX Renderer", "BaseTask", "BaseController", "DataCollector", "Diffusion Policy", "Action Chunking Transformer", "GenManip", "EvalClient", "lift2", "LeRobot"];
    el.innerHTML = `<input aria-label="Glossary filter" placeholder="输入 term 过滤..." style="width:100%;padding:10px;border:1px solid var(--line);border-radius:7px;background:var(--paper);color:var(--ink)"><div class="matrix" style="margin-top:12px"></div>`;
    const input = el.querySelector("input");
    const box = el.querySelector(".matrix");
    const render = () => {
      const q = input.value.toLowerCase();
      box.innerHTML = terms.filter(t => t.toLowerCase().includes(q)).map(t => `<div class="matrix-cell"><strong>${t}</strong></div>`).join("");
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
