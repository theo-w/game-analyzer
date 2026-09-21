/**
 * 三类分析场景指引 — 首页总览 + 各模块页内嵌说明
 */
(function (global) {
    const STORAGE_KEY = "analysis_guide_collapsed";

    const GUIDES = {
        competitor: {
            icon: "⚔️",
            title: "竞品分析",
            subtitle: "界定竞品圈 → 横向对比 → 输出机会与建议",
            href: "/games/compare",
            homeLabel: "去竞品工作台",
            steps: [
                "界定竞品圈：同品类、同平台、相近商业模式",
                "建立产品档案：品类、核心循环、付费模型",
                "查看市场表现：规模、排名、增长（有数据时）",
                "分析用户口碑：评分、评论主题、正负向证据",
                "横向对比：KPI + 功能矩阵并排查看",
                "识别机会与威胁：预警、样本好评率排序",
                "形成可执行建议：版本 / 运营方向，并设定复测指标",
            ],
            tips: "在本页完成全部操作：选游戏 → 横向对比 → 玩法拆解 → 复盘归档 →「AI 总结」生成报告并归档。",
        },
        breakdown: {
            icon: "📚",
            title: "玩法拆解",
            subtitle: "按 7 段标准结构沉淀每款产品的核心设计",
            href: "/games/library",
            homeLabel: "去资料库",
            steps: [
                "核心循环：目标 → 操作 → 反馈 → 奖励的最小闭环",
                "成长路径：等级、装备、段位、收集等中长期追求",
                "商业化设计：付费点、Battle Pass、皮肤、抽卡等",
                "社交与竞技：组队、公会、排位、观战、UGC",
                "单局 / Session：时长、节奏、失败惩罚、回流钩子",
                "差异化卖点：相对同品类的核心差异",
                "可借鉴点：值得参考的机制或运营手法",
            ],
            tips: "在本页：编辑玩法拆解 →「对标竞品」页内对比 →「AI 总结」生成玩法报告并归档。",
        },
        review: {
            icon: "📅",
            title: "数据复盘",
            subtitle: "对比时间窗口内的指标与口碑变化，沉淀案例",
            href: "/games/review",
            homeLabel: "去复盘与归档",
            steps: [
                "选定时间窗口与产品范围（看板筛选 / 报告产品）",
                "对比核心 KPI 与口碑指标（快照 A vs B）",
                "归因：版本更新、活动、舆情事件",
                "输出复盘结论与下一轮实验假设，归档报告",
            ],
            tips: "在本页：快照 A/B 对比 →「AI 复盘报告」生成总结 → 归档到案例库，无需跳转看板。",
        },
        wizard: {
            icon: "🧭",
            title: "分析向导",
            subtitle: "抓取真实竞品 → 自动同步看板 → 生成报告与归档",
            href: "/guide",
            homeLabel: "开始分析",
            steps: [
                "选择平台：Steam / TapTap / Google Play",
                "输入游戏名、AppID 或包名（最多 5 款）",
                "执行抓取：评论与样本指标写入统一数据集（与看板共用）",
                "返回运营看板：点击「应用筛选」查看 KPI 与平台排行",
                "本向导额外产出：深度报告、行动清单、归档",
                "导出行动清单到 CSV / 飞书 / Jira",
            ],
            tips: "抓取 ≠ 看板隔离：数据自动进入 /dashboard。可选 CSV 导入经营指标与评论合并分析。",
        },
        dashboard: {
            icon: "📊",
            title: "运营看板",
            subtitle: "读取抓取/导入后的统一数据集，筛选查看 KPI 与预警",
            href: "/dashboard",
            homeLabel: "去看板",
            steps: [
                "数据来源：优先用户导入 CSV，其次 MVP 抓取数据集（steam_dataset.json）",
                "若看板为空：先去 /guide 完成抓取，再回本页点「应用筛选」",
                "产品 / 来源 / 周期筛选：作用于同一份已写入的评论与指标",
                "KPI 展示：抓取数据为「评论样本量 / 样本好评率」；导入后可显示 DAU/收入等",
                "竞品工作台、复盘页读取同一数据集，分工不同而非数据隔离",
            ],
            tips: "顶部「数据流说明」可展开查看抓取 ↔ 看板四步关系。",
        },
        workflow: {
            icon: "📋",
            title: "落地指导",
            subtitle: "分析 → 导出 → 分享 → 复测验证闭环",
            href: "/work",
            homeLabel: "去落地指导",
            steps: [
                "完成竞品分析并自动归档",
                "导出 P0/P1 行动清单到协作工具",
                "生成分享链接，团队在协作页查看",
                "2 周后复测，系统自动对比口碑并更新验证状态",
            ],
            tips: "制作人 / 策划 / 运营的一站式落地页：进度追踪、逾期提醒、一键复测。",
        },
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
            if (!(key in map) && key === "home") return true;
            return !!map[key];
        } catch {
            return key === "home";
        }
    }

    function setCollapsed(key, collapsed) {
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY);
            const map = raw ? JSON.parse(raw) : {};
            map[key] = collapsed;
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(map));
        } catch (_) { /* ignore */ }
    }

    function renderStepsList(steps) {
        return (
            "<ol class=\"ag-steps\">" +
            steps.map((s) => "<li>" + esc(s) + "</li>").join("") +
            "</ol>"
        );
    }

    /** 首页：三块指引卡片 */
    function renderHomeGuide(containerId) {
        const el = document.getElementById(containerId);
        if (!el) return;

        const collapsed = isCollapsed("home");
        const cards = Object.keys(GUIDES)
            .map((key) => {
                const g = GUIDES[key];
                return (
                    '<a class="ag-home-card" href="' +
                    esc(g.href) +
                    '">' +
                    '<div class="ag-home-card-icon">' +
                    g.icon +
                    "</div>" +
                    '<div class="ag-home-card-body">' +
                    "<h3>" +
                    esc(g.title) +
                    "</h3>" +
                    "<p>" +
                    esc(g.subtitle) +
                    "</p>" +
                    '<span class="ag-home-card-link">' +
                    esc(g.homeLabel) +
                    " →</span>" +
                    "</div></a>"
                );
            })
            .join("");

        el.innerHTML =
            '<section class="ag-panel ag-theme-light" id="analysis-guide">' +
            '<div class="ag-header">' +
            "<div>" +
            "<h2 class=\"ag-title\">📐 分析指引</h2>" +
            "<p class=\"ag-subtitle\">核心场景：分析向导 · 运营看板 · 落地指导 · 竞品分析 · 玩法拆解 · 数据复盘。真实竞品抓取后自动同步看板。</p>" +
            "</div>" +
            '<button type="button" class="ag-toggle" id="ag-home-toggle" aria-expanded="' +
            (!collapsed) +
            '">' +
            (collapsed ? "展开" : "收起") +
            "</button></div>" +
            '<div class="ag-home-body" id="ag-home-body" style="' +
            (collapsed ? "display:none" : "") +
            '">' +
            '<div class="ag-home-grid">' +
            cards +
            "</div>" +
            '<details class="ag-details">' +
            "<summary>查看完整检查清单（原「分析框架」）</summary>" +
            '<div class="ag-full-grid">' +
            Object.keys(GUIDES)
                .map((key) => {
                    const g = GUIDES[key];
                    return (
                        "<div class=\"ag-full-block\"><h4>" +
                        g.icon +
                        " " +
                        esc(g.title) +
                        "</h4>" +
                        renderStepsList(g.steps) +
                        "</div>"
                    );
                })
                .join("") +
            "</div></details></div></section>";

        document.getElementById("ag-home-toggle")?.addEventListener("click", () => {
            const body = document.getElementById("ag-home-body");
            const btn = document.getElementById("ag-home-toggle");
            const next = body.style.display !== "none";
            body.style.display = next ? "none" : "";
            btn.textContent = next ? "展开" : "收起";
            btn.setAttribute("aria-expanded", String(!next));
            setCollapsed("home", next);
        });
    }

    /** 模块页：当前场景的分步指引（可折叠） */
    function renderModuleGuide(containerId, moduleKey) {
        const el = document.getElementById(containerId);
        const g = GUIDES[moduleKey];
        if (!el || !g) return;

        const collapsed = isCollapsed("module_" + moduleKey);
        el.innerHTML =
            '<aside class="ag-panel ag-module-guide" data-module="' +
            esc(moduleKey) +
            '">' +
            '<div class="ag-header">' +
            "<div>" +
            "<h2 class=\"ag-title\">" +
            g.icon +
            " " +
            esc(g.title) +
            " · 操作指引</h2>" +
            "<p class=\"ag-subtitle\">" +
            esc(g.subtitle) +
            "</p>" +
            "</div>" +
            '<button type="button" class="ag-toggle" id="ag-mod-toggle-' +
            moduleKey +
            '">' +
            (collapsed ? "展开指引" : "收起") +
            "</button></div>" +
            '<div class="ag-module-body" id="ag-mod-body-' +
            moduleKey +
            '" style="' +
            (collapsed ? "display:none" : "") +
            '">' +
            renderStepsList(g.steps) +
            '<p class="ag-tip">💡 ' +
            esc(g.tips) +
            "</p>" +
            '<p class="ag-back"><a href="#" data-sitemap-open>← 打开帮助与指引</a></p>' +
            "</div></aside>";

        document.getElementById("ag-mod-toggle-" + moduleKey)?.addEventListener("click", () => {
            const body = document.getElementById("ag-mod-body-" + moduleKey);
            const btn = document.getElementById("ag-mod-toggle-" + moduleKey);
            const next = body.style.display !== "none";
            body.style.display = next ? "none" : "";
            btn.textContent = next ? "展开指引" : "收起";
            setCollapsed("module_" + moduleKey, next);
        });
    }

    global.AnalysisGuide = {
        GUIDES,
        renderHomeGuide,
        renderModuleGuide,
    };
})(typeof window !== "undefined" ? window : globalThis);
