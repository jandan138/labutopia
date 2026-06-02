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
