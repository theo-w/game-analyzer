/** Dashboard data governance: de-emphasize mock KPIs. */
(function (global) {
    function apply(payload) {
        if (!payload) return;
        global.dataProvenance = payload;
        const source = payload.source || "";
        const isMock = source === "mock";
        const isReal =
            source === "imported" ||
            source === "mvp_steam" ||
            source === "mvp_multi" ||
            source === "taptap_public" ||
            source === "google_play_public" ||
            (source && source.startsWith("mvp_"));

        global.__gaSimulatedAnalytics = isMock || !!payload.collapse_demo_metrics;

        const kpiGrid = document.getElementById("kpi-grid");
        if (kpiGrid) {
            kpiGrid.classList.toggle("demo-metrics", isMock);
            kpiGrid.classList.toggle("steam-trust-kpi", isReal);
        }
    }

    global.DashboardGovernance = { apply };
})(typeof window !== "undefined" ? window : globalThis);
