/**
 * 真实竞品抓取数据 ↔ 运营看板 — 统一说明（各页复用同一份文案）
 */
(function (global) {
    const STORAGE_KEY = "ga_data_flow_collapsed";

    const COPY = {
        title: "真实竞品数据如何进入看板",
        summary:
            "抓取与看板共用同一份数据集，不是两套系统。在分析向导完成抓取后，看板会自动读到评论与样本指标。",
        steps: [
            {
                num: "①",
                title: "抓取真实竞品",
                body: "在分析向导选择 Steam / TapTap / Google Play，输入游戏名、AppID 或包名，执行抓取。",
                links: [{ label: "分析向导", href: "/guide" }],
            },
            {
                num: "②",
                title: "写入统一数据集",
                body: "评论、样本好评率等指标写入 data/mvp/users/{用户名}/steam_dataset.json。向导与看板读取该登录用户目录下的数据。",
                links: [],
            },
            {
                num: "③",
                title: "看板自动同步",
                body: "运营看板通过 /api/metrics 读取上述数据集，无需单独导入或手动同步。",
                links: [{ label: "运营看板", href: "/dashboard" }],
            },
            {
                num: "④",
                title: "筛选并查看",
                body: "返回看板后点击「应用筛选」，按产品、数据来源、时间周期查看 KPI、平台排行与预警。",
                links: [],
            },
        ],
        optional:
            "可选：通过「导入指标」上传 CSV（DAU、收入、下载/注册/留存等 Owner 数据），会与抓取评论合并分析；导入数据优先级更高。",
        pages: [
            { name: "分析向导", role: "抓取 + 深度报告（口碑主题、行动建议）" },
            { name: "运营看板", role: "筛选 + KPI 汇总 + 平台排行 + 预警" },
            { name: "竞品工作台", role: "横向对比、玩法拆解（读取同一数据集）" },
        ],
    };

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s || "";
        return d.innerHTML;
    }

    function isCollapsed(key) {
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY);
            const map = raw ? JSON.parse(raw) : {};
            if (!(key in map) && key === "dfg_dashboard") return true;
            return !!map[key];
        } catch {
            return key === "dfg_dashboard";
        }
    }

    function setCollapsed(key, val) {
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY);
            const map = raw ? JSON.parse(raw) : {};
            map[key] = val;
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(map));
        } catch (_) { /* ignore */ }
    }

    function renderStepsHtml(highlight) {
        return (
            '<ol class="dfg-steps">' +
            COPY.steps
                .map((s) => {
                    const isHi = highlight && s.num === highlight;
                    const links =
                        s.links && s.links.length
                            ? '<span class="dfg-links">' +
                              s.links
                                  .map(
                                      (l) =>
                                          '<a href="' +
                                          esc(l.href) +
                                          '">' +
                                          esc(l.label) +
                                          "</a>"
                                  )
                                  .join(" · ") +
                              "</span>"
                            : "";
                    return (
                        '<li class="dfg-step' +
                        (isHi ? " dfg-step-active" : "") +
                        '"><span class="dfg-num">' +
                        esc(s.num) +
                        "</span><div><strong>" +
                        esc(s.title) +
                        "</strong><p>" +
                        esc(s.body) +
                        "</p>" +
                        links +
                        "</div></li>"
                    );
                })
                .join("") +
            "</ol>"
        );
    }

    function renderPagesTable() {
        return (
            '<table class="dfg-table"><thead><tr><th>页面</th><th>作用（数据同源）</th></tr></thead><tbody>' +
            COPY.pages
                .map(
                    (p) =>
                        "<tr><td>" +
                        esc(p.name) +
                        "</td><td>" +
                        esc(p.role) +
                        "</td></tr>"
                )
                .join("") +
            "</tbody></table>"
        );
    }

    /**
     * @param {string} containerId
     * @param {{ variant?: 'dashboard'|'wizard', theme?: 'light'|'dark', highlight?: string, showTable?: boolean }} opts
     */
    function render(containerId, opts) {
        const el = document.getElementById(containerId);
        if (!el) return;
        opts = opts || {};
        const variant = opts.variant || "dashboard";
        const theme = opts.theme || (variant === "dashboard" ? "light" : "dark");
        const key = "dfg_" + variant;
        const collapsed = isCollapsed(key);
        const highlight =
            opts.highlight || (variant === "wizard" ? "①" : null);

        const variantNote =
            variant === "wizard"
                ? "你正在第 ① 步：完成抓取后，打开看板并点击「应用筛选」即可看到同款竞品数据。"
                : "若刚完成抓取，请点「应用筛选」刷新；顶部横幅会显示当前数据来源。";

        el.innerHTML =
            '<section class="dfg-panel dfg-theme-' +
            theme +
            '" data-variant="' +
            esc(variant) +
            '">' +
            '<div class="dfg-header">' +
            "<div><h3 class=\"dfg-title\">📡 " +
            esc(COPY.title) +
            "</h3>" +
            '<p class="dfg-summary">' +
            esc(COPY.summary) +
            "</p>" +
            '<p class="dfg-variant-note">' +
            esc(variantNote) +
            "</p></div>" +
            '<button type="button" class="dfg-toggle" id="dfg-toggle-' +
            variant +
            '">' +
            (collapsed ? "展开说明" : "收起") +
            "</button></div>" +
            '<div class="dfg-body" id="dfg-body-' +
            variant +
            '" style="' +
            (collapsed ? "display:none" : "") +
            '">' +
            renderStepsHtml(highlight) +
            (opts.showTable !== false ? renderPagesTable() : "") +
            '<p class="dfg-optional">💡 ' +
            esc(COPY.optional) +
            ' <a href="/trust">数据说明</a></p>' +
            "</div></section>";

        document.getElementById("dfg-toggle-" + variant)?.addEventListener("click", () => {
            const body = document.getElementById("dfg-body-" + variant);
            const btn = document.getElementById("dfg-toggle-" + variant);
            const next = body.style.display !== "none";
            body.style.display = next ? "none" : "";
            btn.textContent = next ? "展开说明" : "收起";
            setCollapsed(key, next);
        });
    }

    global.DataFlowGuide = {
        COPY,
        render,
    };
})(typeof window !== "undefined" ? window : globalThis);
