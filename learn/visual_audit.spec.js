const { test, expect } = require("@playwright/test");

const base = process.env.LABUTOPIA_LEARN_BASE || "http://127.0.0.1:8099";
const outDir = process.env.LABUTOPIA_VISUAL_OUT || "/tmp/labutopia-visual";

const routes = [
  "/learn/index.html",
  "/learn/chapters/00-orientation/0-1-why-labutopia.html",
  "/learn/chapters/03-runtime/3-3-task-controller-boundary.html",
  "/learn/chapters/05-data-policy/5-3-act-action-chunking.html",
  "/learn/chapters/07-ebench-assets/7-1-reuse-answer.html",
  "/learn/chapters/07-ebench-assets/7-8-conversion-workflow.html",
  "/learn/chapters/appendix/a-4-references.html",
];

const viewports = [
  ["desktop", { width: 1440, height: 1100 }],
  ["tablet", { width: 900, height: 1100 }],
  ["mobile", { width: 390, height: 844 }],
];

function shotName(viewportName, route) {
  const slug = route
    .replace(/^\/learn\/?/, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "index";
  return `${outDir}/${viewportName}-${slug}.png`;
}

for (const [viewportName, viewport] of viewports) {
  test.describe(viewportName, () => {
    test.use({ viewport });

    for (const route of routes) {
      test(route, async ({ page }) => {
        const consoleErrors = [];
        const pageErrors = [];
        const failedRequests = [];

        page.on("console", (msg) => {
          if (msg.type() === "error") consoleErrors.push(msg.text());
        });
        page.on("pageerror", (err) => pageErrors.push(err.message));
        page.on("requestfailed", (req) => failedRequests.push(req.url()));

        const response = await page.goto(base + route, { waitUntil: "networkidle" });
        expect(response.status()).toBe(200);

        await page.evaluate(async () => {
          await new Promise((resolve) => {
            let y = 0;
            const step = () => {
              y += Math.max(240, window.innerHeight * 0.7);
              window.scrollTo(0, y);
              if (y < document.documentElement.scrollHeight) {
                setTimeout(step, 20);
              } else {
                window.scrollTo(0, 0);
                setTimeout(resolve, 40);
              }
            };
            step();
          });
        });

        const metrics = await page.evaluate(() => {
          const doc = document.documentElement;
          const brokenImages = [...document.images]
            .filter((img) => img.complete && img.naturalWidth === 0)
            .map((img) => img.currentSrc || img.src);
          const wideElements = [...document.querySelectorAll("body *")]
            .filter((el) => {
              const rect = el.getBoundingClientRect();
              return rect.width > window.innerWidth + 2 && getComputedStyle(el).position !== "fixed";
            })
            .slice(0, 8)
            .map((el) => ({
              tag: el.tagName,
              className: String(el.className || ""),
              width: el.getBoundingClientRect().width,
            }));

          return {
            horizontalOverflow: doc.scrollWidth > window.innerWidth + 2,
            scrollWidth: doc.scrollWidth,
            innerWidth: window.innerWidth,
            brokenImages,
            wideElements,
            widgets: document.querySelectorAll("[data-widget]").length,
            sidebarLinks: document.querySelectorAll("#sidebar a").length,
          };
        });

        await page.screenshot({ path: shotName(viewportName, route), fullPage: true });

        expect(metrics.horizontalOverflow, JSON.stringify(metrics, null, 2)).toBeFalsy();
        expect(metrics.brokenImages, JSON.stringify(metrics, null, 2)).toHaveLength(0);
        expect(consoleErrors, consoleErrors.join("\n")).toHaveLength(0);
        expect(pageErrors, pageErrors.join("\n")).toHaveLength(0);
        expect(failedRequests, failedRequests.join("\n")).toHaveLength(0);
      });
    }
  });
}
