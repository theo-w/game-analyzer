/** First-run onboarding wizard on dashboard. */
(function (global) {
    const STORAGE_KEY = "ga_onboarding_done_v1";

    function defaultSteps() {
        return [
            {
                title: "① 抓取真实竞品",
                body: "向导抓取后，评论与指标写入统一数据集（与看板共用，无需再导入）。",
                action: { label: "分析向导", href: "/guide" },
            },
            {
                title: "② 看板查看 KPI",
                body: "返回本页，选择产品与数据来源，点击「应用筛选」查看样本量、好评率与排行。",
                action: { label: "刷新筛选", href: "#" },
            },
            {
                title: "③ 报告与落地",
                body: "深度报告在向导；行动清单导出与复测在落地指导 / 复盘归档。",
                action: { label: "落地指导", href: "/work#actions" },
            },
        ];
    }

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s || "";
        return d.innerHTML;
    }

    function isDone() {
        try {
            return localStorage.getItem(STORAGE_KEY) === "1";
        } catch {
            return false;
        }
    }

    function markDone() {
        try {
            localStorage.setItem(STORAGE_KEY, "1");
        } catch (_) { /* ignore */ }
    }

    function render(containerId, steps) {
        const el = document.getElementById(containerId);
        if (!el || isDone()) return;
        const STEPS = steps || defaultSteps();

        el.innerHTML =
            '<div class="onboarding-wizard">' +
            '<div class="onboarding-head"><div><h3>🚀 操作路径 · 抓取数据自动进看板</h3>' +
            '<p style="font-size:0.8rem;color:#94a3b8;margin:6px 0 0;line-height:1.45;">真实竞品与看板<strong>不隔离</strong>：抓取 → 统一数据集 → 本页筛选展示。展开上方「数据流说明」查看详情。</p></div>' +
            '<button type="button" class="onboarding-dismiss" id="onboarding-dismiss">不再显示</button></div>' +
            '<div class="onboarding-steps">' +
            STEPS.map(
                (s) =>
                    '<div class="onboarding-step"><h4>' +
                    esc(s.title) +
                    "</h4><p>" +
                    esc(s.body) +
                    '</p><a class="onboarding-link" href="' +
                    esc(s.action.href) +
                    '">' +
                    esc(s.action.label) +
                    " →</a></div>"
            ).join("") +
            "</div></div>";

        document.getElementById("onboarding-dismiss").onclick = () => {
            markDone();
            el.innerHTML = "";
        };
        el.querySelectorAll('.onboarding-link[href="#"]').forEach((link) => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                if (typeof global.applyFilters === 'function') global.applyFilters();
            });
        });
    }

    async function maybeShowAfterLibraryCheck(containerId, token) {
        if (isDone() || !token) return;
        try {
            const fetchFn = typeof authFetch !== "undefined" ? authFetch : fetch;
            const [libRes, provRes] = await Promise.all([
                fetchFn("/api/games/library"),
                global.DataProvenance && global.DataProvenance.fetchProvenance
                    ? global.DataProvenance.fetchProvenance(token)
                    : Promise.resolve(null),
            ]);
            if (!libRes.ok) return;
            const data = await libRes.json();
            const prov = provRes && provRes.success !== false ? provRes : null;
            const needsCrawl =
                prov?.source === "empty" ||
                prov?.source === "mock" ||
                prov?.show_mock_warning;
            const liveCount = (data.games || []).filter((g) =>
                String(g.source || "").includes("mvp")
            ).length;
            if (liveCount >= 1 && !needsCrawl) {
                markDone();
                return;
            }
            const steps = defaultSteps();
            if (needsCrawl) {
                steps[0].body =
                    "当前暂无数据。请从 Steam / TapTap / Google Play 抓取评论，写入后与看板自动同步。";
                steps.push({
                    title: "④ 导入经营指标（可选）",
                    body: "DAU/收入等 Owner 数据可通过 CSV 导入，与抓取评论合并分析。",
                    action: { label: "去导入", href: "/import" },
                });
            }
            render(containerId, steps);
        } catch (_) {
            render(containerId);
        }
    }

    global.OnboardingWizard = {
        render,
        maybeShowAfterLibraryCheck,
        markDone,
    };
})(typeof window !== "undefined" ? window : globalThis);
