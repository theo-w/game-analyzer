/** Unified top navigation — primary items +「更多」dropdown */
(function (global) {
    var PRIMARY = [
        { id: "home", label: "首页", href: "/", icon: "🏠", home: true },
        { id: "platform", label: "舆情平台", href: "/game-public-opinion-ai-analysis", icon: "📡" },
        { id: "guide", label: "分析向导", href: "/guide", icon: "🧭" },
        { id: "dashboard", label: "数据看板", href: "/dashboard", icon: "📊" },
        { id: "compare", label: "竞品分析", href: "/games/compare", icon: "⚔️" },
        { id: "review", label: "复盘归档", href: "/games/review", icon: "📅" },
    ];

    var MORE = [
        { id: "work", label: "落地指导", href: "/work" },
        { id: "hotspot", label: "热点深析", href: "/hotspot" },
        { id: "pricing", label: "订阅套餐", href: "/pricing" },
    ];

    function esc(s) {
        var d = document.createElement("div");
        d.textContent = s || "";
        return d.innerHTML;
    }

    function detectActive(fallback) {
        var path = location.pathname.replace(/\/$/, "") || "/";
        if (path.indexOf("/game-public-opinion-ai-analysis") === 0
            || path.indexOf("/ai-game-opinion-monitoring-system") === 0
            || path.indexOf("/game-negative-public-opinion-monitoring") === 0
            || path.indexOf("/mobile-game-player-experience-analysis") === 0
            || path.indexOf("/game-hot-event-tracking") === 0
            || path.indexOf("/game-monetization-controversy-monitoring") === 0
            || path.indexOf("/cross-platform-game-opinion-aggregation") === 0) return "platform";
        if (path === "/" || path === "/welcome") return "home";
        if (path === "/dashboard") return "dashboard";
        if (path.indexOf("/guide") === 0) return "guide";
        if (path.indexOf("/games/compare") === 0) return "compare";
        if (path.indexOf("/games/review") === 0) return "review";
        if (path.indexOf("/work") === 0) return "work";
        if (path.indexOf("/games/library") === 0) return "library";
        if (path.indexOf("/comments") === 0) return "comments";
        if (path.indexOf("/hotspot") === 0) return "hotspot";
        if (path.indexOf("/metrics") === 0) return "metrics";
        if (path.indexOf("/import") === 0) return "import";
        if (path.indexOf("/team") === 0) return "team";
        if (path.indexOf("/pricing") === 0) return "pricing";
        return fallback || "";
    }

    function render(activeId) {
        var primaryHtml = PRIMARY.map(function (item) {
            var cls = "app-nav-item" + (item.id === activeId ? " active" : "");
            if (item.home) cls += " app-nav-home";
            return (
                '<a class="' +
                cls +
                '" href="' +
                esc(item.href) +
                '"><span class="app-nav-icon">' +
                item.icon +
                '</span><span class="app-nav-label">' +
                esc(item.label) +
                "</span></a>"
            );
        }).join("");

        var moreActive = MORE.some(function (m) {
            return m.id === activeId;
        });
        var moreItems = MORE.map(function (item) {
            if (item.divider) return '<div class="app-nav-divider"></div>';
            var cls = item.id === activeId ? ' class="active"' : "";
            return '<a href="' + esc(item.href) + '"' + cls + ">" + esc(item.label) + "</a>";
        }).join("");

        return (
            '<nav class="app-nav" role="navigation" aria-label="主导航">' +
            primaryHtml +
            '<div class="app-nav-more' +
            (moreActive ? " open" : "") +
            '">' +
            '<button type="button" class="app-nav-item' +
            (moreActive ? " active" : "") +
            '" id="app-nav-more-btn" aria-haspopup="true" aria-expanded="' +
            (moreActive ? "true" : "false") +
            '"><span class="app-nav-icon">⋯</span><span class="app-nav-label">更多</span></button>' +
            '<div class="app-nav-dropdown" id="app-nav-dropdown">' +
            moreItems +
            '</div></div><button type="button" class="app-nav-item app-nav-help" data-sitemap-open aria-label="帮助与指引" title="数据流与分析指引">' +
            '<span class="app-nav-icon">📖</span><span class="app-nav-label">指引</span></button></nav>'
        );
    }

    function bindDropdown(root) {
        var wrap = root.querySelector(".app-nav-more");
        var btn = root.querySelector("#app-nav-more-btn");
        var menu = root.querySelector("#app-nav-dropdown");
        if (!wrap || !btn || !menu) return;

        btn.addEventListener("click", function (e) {
            e.stopPropagation();
            var open = wrap.classList.toggle("open");
            btn.setAttribute("aria-expanded", open ? "true" : "false");
        });

        document.addEventListener("click", function () {
            wrap.classList.remove("open");
            btn.setAttribute("aria-expanded", "false");
        });

        menu.addEventListener("click", function (e) {
            e.stopPropagation();
        });
    }

    function mount(selector, opts) {
        opts = opts || {};
        var el = typeof selector === "string" ? document.querySelector(selector) : selector;
        if (!el) return;
        var active = opts.active || el.getAttribute("data-active") || detectActive();
        el.innerHTML = render(active);
        bindDropdown(el);
    }

    global.AppNav = { mount: mount, detectActive: detectActive, PRIMARY: PRIMARY, MORE: MORE };
})(typeof window !== "undefined" ? window : globalThis);
