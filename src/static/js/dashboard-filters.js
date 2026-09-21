/**
 * Dashboard filter catalog, metrics fetch, and view pipeline.
 * Loaded before the main dashboard script in index.html.
 */
(function (global) {
    "use strict";

    global.selectedProducts = global.selectedProducts || [];
    global.currentMetricsData = global.currentMetricsData || [];
    global.allMetricsData = global.allMetricsData ?? null;
    global.metricsLoadPromise = global.metricsLoadPromise ?? null;
    global.currentTimePeriod = global.currentTimePeriod || "week_22";
    global.currentDataSource = global.currentDataSource || "all";
    global.currentGenre = global.currentGenre || "all";
    global.productGenreMap = global.productGenreMap || {};
    global.allProductsCatalog = global.allProductsCatalog || [];
    global.productNamesMap = global.productNamesMap || {};
    global.timePeriodLabels = global.timePeriodLabels || {
        week_20: "第20周",
        week_21: "第21周",
        week_22: "第22周",
        quarter_2: "Q2季度",
    };

    function debounce(func, wait) {
        let timeout;
        return function debounced(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    function normalizeCatalogProductId(value) {
        const pid = String(value || "").trim();
        if (pid.startsWith("steam_") && /^\d+$/.test(pid.slice(6))) {
            return pid.slice(6);
        }
        return pid;
    }

    function metricMatchesPeriod(metric, period) {
        if (!period || period === "all") return true;
        const cycleRaw = String(metric.cycle || metric.周期 || "").trim();
        if (!cycleRaw) return true;
        if (cycleRaw === period || cycleRaw.toLowerCase() === String(period).toLowerCase()) {
            return true;
        }
        const normalizeKey = (text) =>
            String(text || "")
                .toLowerCase()
                .replace(/_/g, " ")
                .replace(/-/g, " ")
                .trim();
        const aliases = {
            "week 20": "week_20",
            week20: "week_20",
            "week 21": "week_21",
            week21: "week_21",
            "week 22": "week_22",
            week22: "week_22",
            q2: "q2",
            "quarter 2": "q2",
            quarter2: "q2",
        };
        const normalized = aliases[normalizeKey(period)] || String(period).toLowerCase();
        const cycleKey = normalizeKey(cycleRaw);
        const cycleCompact = cycleKey.replace(/\s+/g, "");
        const candidates = new Set([normalized, String(period).toLowerCase()]);
        if (normalized === "week_20") {
            candidates.add("week 20");
            candidates.add("week20");
        } else if (normalized === "week_21") {
            candidates.add("week 21");
            candidates.add("week21");
        } else if (normalized === "week_22") {
            candidates.add("week 22");
            candidates.add("week22");
        } else if (normalized === "q2") {
            candidates.add("q2");
            candidates.add("quarter 2");
            candidates.add("quarter_2");
        } else if (normalized.startsWith("month_")) {
            candidates.add(normalized.replace("_", " "));
        }
        for (const candidate of candidates) {
            if (!candidate) continue;
            const cand = normalizeKey(candidate);
            const candCompact = cand.replace(/\s+/g, "");
            if (cycleKey === cand || cycleCompact === candCompact) return true;
            if (cycleKey.includes(cand) || cycleCompact.includes(candCompact)) return true;
        }
        const dateValue = String(metric.date || metric.日期 || "");
        return dateValue.startsWith(String(period).slice(0, 4));
    }

    function productRecordMatches(metric, productId) {
        const pid = normalizeCatalogProductId(productId);
        const displayName = global.productNamesMap[productId] || global.productNamesMap[pid] || pid;
        return (
            normalizeCatalogProductId(metric.product || metric.产品 || metric.app_id || "") === pid ||
            metric.product === displayName ||
            String(metric.product_name || "") === displayName
        );
    }

    function persistProductSelection() {
        const productSelect = document.getElementById("product-select");
        if (global.CatalogFilters && productSelect) {
            global.CatalogFilters.writeStoredProduct(productSelect);
        }
    }

    function restoreStoredProductSelection(catalogIds) {
        if (readProductIdsFromUrl().length) return null;
        if (!global.CatalogFilters) return null;
        try {
            const raw = sessionStorage.getItem(global.CatalogFilters.STORAGE_PRODUCTS_MULTI);
            if (!raw) return null;
            const ids = JSON.parse(raw);
            if (!Array.isArray(ids) || !ids.length) return null;
            if (Array.isArray(catalogIds) && catalogIds.length) {
                const allowed = new Set(catalogIds);
                const matched = ids.filter((id) => allowed.has(id));
                return matched.length ? matched : null;
            }
            return ids;
        } catch (_e) {
            return null;
        }
    }

    function formatDashboardProductSelection() {
        const ids = getSelectedProductIds();
        if (!ids.length) return "全部产品";
        return ids
            .map((id) => global.productNamesMap[id] || global.productNamesMap[normalizeCatalogProductId(id)] || id)
            .join("、");
    }

    function updateLinkedProductSummaries() {
        const ids = getSelectedProductIds();
        const text = formatDashboardProductSelection();
        const hint =
            '<span class="dashboard-product-summary-hint">如需更改，请关闭本窗口并在看板筛选区调整，各报告/分析将自动同步。</span>';
        const emptyHint =
            '<span class="dashboard-product-summary-hint">请在看板顶部筛选区勾选产品。</span>';
        document.querySelectorAll("[data-dashboard-product-summary]").forEach((el) => {
            if (ids.length) {
                el.innerHTML = text + (el.id === "report-product-summary" ? hint : "");
            } else {
                el.innerHTML = "全部产品（请在看板顶部筛选区勾选）" + emptyHint;
            }
        });
        const reportEl = document.getElementById("report-product-summary");
        if (reportEl && !reportEl.dataset.dashboardProductSummary) {
            reportEl.innerHTML = ids.length
                ? text + hint
                : "沿用看板顶部筛选" + emptyHint;
        }
    }

    function syncFiltersFromDom() {
        const productSelect = document.getElementById("product-select");
        const periodSelect = document.getElementById("time-period-select");
        const sourceSelect = document.getElementById("data-source-select");
        const genreSelect = document.getElementById("genre-select");
        if (global.ProductPicker && document.getElementById("product-picker")) {
            global.selectedProducts = global.ProductPicker.getSelectedIds("product-picker");
        } else if (productSelect) {
            global.selectedProducts = Array.from(productSelect.selectedOptions).map((o) => o.value);
            if (global.selectedProducts.length === 0) {
                global.selectedProducts = Array.from(productSelect.options).map((o) => o.value);
            }
        }
        if (periodSelect) global.currentTimePeriod = periodSelect.value;
        if (sourceSelect) global.currentDataSource = sourceSelect.value;
        if (genreSelect) global.currentGenre = genreSelect.value;
        persistProductSelection();
    }

    function productsMatchingGenre(products, genre) {
        if (!Array.isArray(products)) return [];
        if (!genre || genre === "all") return products;
        return products.filter((p) => {
            const g = p.genre || global.productGenreMap[p.id] || "PC Game";
            return g === genre;
        });
    }

    function normalizeProductPlatform(platform) {
        return String(platform || "")
            .trim()
            .toLowerCase()
            .replace(/_/g, " ");
    }

    function dataSourcePlatformToken(dataSource) {
        const map = {
            steam: "steam",
            google_play: "google play",
            taptap: "taptap",
            app_store: "app store",
        };
        return map[String(dataSource || "").trim().toLowerCase()] || "";
    }

    function productsMatchingDataSource(products, dataSource) {
        if (!Array.isArray(products)) return [];
        if (!dataSource || dataSource === "all") return products;
        const target = dataSourcePlatformToken(dataSource);
        if (!target) return products;
        return products.filter((p) => {
            const plat = normalizeProductPlatform(p.platform);
            if (plat) {
                return plat === target;
            }
            // Numeric Steam app ids without an explicit platform tag
            return dataSource === "steam" && /^\d+$/.test(String(p.id || ""));
        });
    }

    const DEMO_DEFAULT_PRODUCT_IDS = ["730", "570"];

    function readProductIdsFromUrl() {
        try {
            const params = new URLSearchParams(window.location.search);
            const raw = params.get("product_ids") || params.get("products") || "";
            return raw
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean);
        } catch (_e) {
            return [];
        }
    }

    function readDataSourceFromUrl() {
        try {
            return new URLSearchParams(window.location.search).get("data_source") || "";
        } catch (_e) {
            return "";
        }
    }

    function defaultProductIdsForList(list) {
        const fromUrl = readProductIdsFromUrl();
        if (fromUrl.length) {
            const matched = fromUrl.filter((id) => list.some((p) => p.id === id));
            if (matched.length) return matched;
        }
        if (Array.isArray(global.dashboardDatasetProductIds) && global.dashboardDatasetProductIds.length) {
            const matched = global.dashboardDatasetProductIds.filter((id) =>
                list.some((p) => p.id === id)
            );
            if (matched.length) return matched;
        }
        // Crawl/import catalogs are small — select every product that has data.
        if (list.length <= 12) return list.map((p) => p.id);
        const demo = DEMO_DEFAULT_PRODUCT_IDS.filter((id) => list.some((p) => p.id === id));
        const extras = list.filter((p) => !DEMO_DEFAULT_PRODUCT_IDS.includes(p.id)).map((p) => p.id);
        if (demo.length) return [...demo, ...extras];
        return list.slice(0, Math.min(3, list.length)).map((p) => p.id);
    }

    function resolveDataSourceForDataset(result, prevSource) {
        const urlSource = readDataSourceFromUrl();
        if (urlSource) return urlSource;
        const hasCrawl = Number(result.metrics_total || 0) > 0;
        if (!hasCrawl) return prevSource || "all";
        const suggested = result.suggested_data_source || "all";
        if (!prevSource || prevSource === "all") return suggested;
        return prevSource;
    }

    function resolveTimePeriodForDataset(periods, prevPeriod) {
        const list = Array.isArray(periods) ? periods : [];
        if (!list.length) return "all";
        const ids = list.map((p) => p.id);
        const crawlSnapshot =
            list.length === 1 && list[0].id === "all" ||
            list.some((p) => /^\d{4}-\d{2}-\d{2}$/.test(String(p.id || "")));
        if (crawlSnapshot) {
            if (prevPeriod && ids.includes(prevPeriod) && !String(prevPeriod).startsWith("week_")) {
                return prevPeriod;
            }
            return ids.includes("all") ? "all" : list[0].id;
        }
        if (prevPeriod && ids.includes(prevPeriod)) return prevPeriod;
        return list[list.length - 1]?.id || "all";
    }

    function renderEmptyProductSelect(selectEl) {
        if (!selectEl) return;
        selectEl.innerHTML =
            '<option value="" disabled selected>暂无产品 — 请先抓取竞品数据</option>';
        global.selectedProducts = [];
        if (global.ProductPicker) {
            const root = document.getElementById("product-picker");
            if (root) {
                root.innerHTML =
                    '<p class="product-picker-empty">暂无产品 — 请先到 /guide 抓取竞品数据</p>';
            }
        }
    }

    function pickerOnChange() {
        syncFiltersFromDom();
        if (typeof global.debouncedApplyFilters === "function") {
            global.debouncedApplyFilters();
        }
    }

    function renderProductPickers(products, options) {
        options = options || {};
        const selectEl = document.getElementById("product-select");
        if (!selectEl) return;
        if (!Array.isArray(products) || !products.length) {
            renderEmptyProductSelect(selectEl);
            return;
        }
        products.forEach((item) => {
            global.productNamesMap[item.id] = item.name || item.id;
        });
        const pickerOptions = {
            selectedIds: options.selectedIds,
            defaultCount: options.defaultCount ?? 2,
            emptyHint: options.emptyHint || "暂无产品 — 请先到 /guide 抓取竞品数据",
            hiddenSelectId: "product-select",
            onChange: pickerOnChange,
        };
        if (global.ProductPicker && document.getElementById("product-picker")) {
            global.ProductPicker.render("product-picker", products, pickerOptions);
            global.selectedProducts = global.ProductPicker.getSelectedIds("product-picker");
            return;
        }
        fillProductSelect(selectEl, products, options);
    }

    function fillProductSelect(selectEl, products, options) {
        options = options || {};
        if (!selectEl) return;
        if (!Array.isArray(products) || !products.length) {
            renderEmptyProductSelect(selectEl);
            return;
        }
        if (global.ProductPicker && document.getElementById("product-picker")) {
            renderProductPickers(products, options);
            return;
        }
        const selectedIds =
            options.selectedIds instanceof Set ? options.selectedIds : new Set(options.selectedIds || []);
        const defaultCount = options.defaultCount ?? 2;
        selectEl.innerHTML = "";
        products.forEach((item, index) => {
            global.productNamesMap[item.id] = item.name || item.id;
            const option = document.createElement("option");
            option.value = item.id;
            let label = item.name || item.id;
            if (label.length > 32) label = label.slice(0, 30) + "…";
            if (item.platform) label += " · " + item.platform;
            option.textContent = label;
            option.title = (item.name || item.id) + (item.platform ? " · " + item.platform : "");
            option.selected = selectedIds.size
                ? selectedIds.has(item.id)
                : index < Math.min(defaultCount, products.length);
            selectEl.appendChild(option);
        });
    }

    function applyFiltersToProductSelect() {
        const productSelect = document.getElementById("product-select");
        if (!productSelect || !global.allProductsCatalog.length) return;

        const genre = document.getElementById("genre-select")?.value || global.currentGenre || "all";
        const dataSource =
            document.getElementById("data-source-select")?.value || global.currentDataSource || "all";
        global.currentGenre = genre;
        global.currentDataSource = dataSource;

        let list = productsMatchingGenre(global.allProductsCatalog, genre);
        if (genre !== "all" && !list.length) {
            productSelect.innerHTML = '<option disabled selected>该品类暂无产品数据</option>';
            global.selectedProducts = [];
            if (global.ProductPicker) {
                const root = document.getElementById("product-picker");
                if (root) {
                    root.innerHTML = '<p class="product-picker-empty">该品类暂无产品数据</p>';
                }
            }
            if (typeof global.renderProductList === "function") global.renderProductList();
            updateLinkedProductSummaries();
            return;
        }

        list = productsMatchingDataSource(list, dataSource);
        if (dataSource !== "all" && !list.length) {
            const sourceLabel =
                dataSourcePlatformToken(dataSource) === "google play"
                    ? "Google Play"
                    : dataSourcePlatformToken(dataSource) === "app store"
                      ? "App Store"
                      : dataSource.charAt(0).toUpperCase() + dataSource.slice(1).replace(/_/g, " ");
            productSelect.innerHTML = `<option disabled selected>该来源暂无产品 — 请先在向导抓取 ${sourceLabel} 数据</option>`;
            global.selectedProducts = [];
            if (global.ProductPicker) {
                const hint = `当前来源（${sourceLabel}）暂无产品，请切换来源或先到 /guide 抓取`;
                const root = document.getElementById("product-picker");
                if (root) root.innerHTML = `<p class="product-picker-empty">${hint}</p>`;
            }
            if (typeof global.renderProductList === "function") global.renderProductList();
            updateLinkedProductSummaries();
            return;
        }

        const selectAllInScope = genre !== "all" || dataSource !== "all";
        const catalogIds = list.map((p) => p.id);
        const storedIds = restoreStoredProductSelection(catalogIds);
        let preferredIds =
            global.selectedProducts.length
                ? global.selectedProducts.filter((id) => catalogIds.includes(id))
                : storedIds && storedIds.length
                  ? storedIds.filter((id) => catalogIds.includes(id))
                  : defaultProductIdsForList(list);
        if (!preferredIds.length) preferredIds = defaultProductIdsForList(list);
        if (selectAllInScope && preferredIds.length < list.length) {
            preferredIds = list.map((p) => p.id);
        }
        const sourceHint =
            dataSource !== "all"
                ? `当前来源：${dataSourcePlatformToken(dataSource) || dataSource}（${list.length} 款）`
                : "";
        renderProductPickers(list, {
            selectedIds: selectAllInScope ? new Set(list.map((p) => p.id)) : new Set(preferredIds),
            defaultCount: selectAllInScope ? list.length : 2,
            emptyHint: sourceHint || "暂无产品 — 请先到 /guide 抓取竞品数据",
        });
        global.selectedProducts = Array.from(productSelect.selectedOptions).map((o) => o.value);
        if (typeof global.syncReportProductOptions === "function") {
            global.syncReportProductOptions(list);
        }
        if (typeof global.renderProductList === "function") global.renderProductList();
        updateLinkedProductSummaries();
    }

    function applyGenreToProductSelect() {
        applyFiltersToProductSelect();
    }

    function getSelectedProductIds() {
        if (global.ProductPicker && document.getElementById("product-picker")) {
            const picked = global.ProductPicker.getSelectedIds("product-picker");
            if (picked.length) return picked;
        }
        const productSelect = document.getElementById("product-select");
        if (!productSelect) return global.selectedProducts.slice();
        const picked = Array.from(productSelect.selectedOptions).map((o) => o.value);
        return picked.length ? picked : Array.from(productSelect.options).map((o) => o.value);
    }

    function setDashboardLoading(loading) {
        const el = document.getElementById("dashboard-loading");
        const btn = document.getElementById("apply-filters-btn");
        if (el) el.style.display = loading ? "inline" : "none";
        if (btn) btn.disabled = !!loading;
    }

    async function fetchMetricsWithFilters() {
        const checkAuth = global.checkAuth || (() => !!global.getToken?.());
        if (!checkAuth()) return null;
        syncFiltersFromDom();
        const params = new URLSearchParams();
        const productIds = getSelectedProductIds();
        if (productIds.length) params.set("product_ids", productIds.join(","));
        if (global.currentTimePeriod && global.currentTimePeriod !== "all") {
            params.set("time_period", global.currentTimePeriod);
        }
        if (global.currentDataSource && global.currentDataSource !== "all") {
            params.set("data_source", global.currentDataSource);
        }
        const fetchFn = global.authFetch || fetch;
        const response = await fetchFn(`/api/metrics?${params.toString()}`);
        if (response.status === 401) {
            if (typeof global.redirectToLogin === "function") {
                global.redirectToLogin("/dashboard");
            } else {
                if (typeof global.clearAuthToken === "function") global.clearAuthToken();
                window.location.href = "/login?redirect=%2Fdashboard&reason=expired";
            }
            return null;
        }
        const result = await response.json();
        if (!result.success) {
            throw new Error(result.message || result.detail || "指标加载失败");
        }
        global.allMetricsData = result.data || [];
        global.currentMetricsData = global.allMetricsData;
        global.dashboardMetricsTotal = Number(result.total ?? global.dashboardMetricsTotal ?? 0);
        global.dashboardMetricsFiltered = Number(result.filtered_count ?? global.currentMetricsData.length);
        if (typeof global.showDashboardFilterHint === "function") {
            if (global.dashboardMetricsTotal > 0 && global.dashboardMetricsFiltered === 0) {
                global.showDashboardFilterHint(
                    "当前筛选条件下没有数据。请尝试：数据来源选「全部来源」、时间周期选「全部（抓取快照）」、并勾选已抓取的产品。"
                );
            } else if (global.dashboardMetricsFiltered > 0) {
                global.showDashboardFilterHint("");
            }
        }
        return global.currentMetricsData;
    }

    async function ensureMetricsLoaded(forceRefresh) {
        const checkAuth = global.checkAuth || (() => !!global.getToken?.());
        if (!checkAuth()) return null;
        const hasCachedRows = Array.isArray(global.allMetricsData) && global.allMetricsData.length > 0;
        const datasetReady = Number(global.dashboardMetricsTotal || 0) > 0;
        if (!forceRefresh && hasCachedRows) return global.allMetricsData;
        if (!forceRefresh && !hasCachedRows && !datasetReady && global.allMetricsData !== null) {
            return global.allMetricsData;
        }
        if (!forceRefresh && global.metricsLoadPromise) return global.metricsLoadPromise;

        setDashboardLoading(true);
        global.metricsLoadPromise = (async () => {
            try {
                return await fetchMetricsWithFilters();
            } catch (e) {
                console.error("指标加载失败", e);
                return global.allMetricsData;
            } finally {
                setDashboardLoading(false);
                global.metricsLoadPromise = null;
            }
        })();
        return global.metricsLoadPromise;
    }

    function getViewMetrics() {
        syncFiltersFromDom();
        let rows = Array.isArray(global.currentMetricsData) ? global.currentMetricsData.slice() : [];
        if (global.currentGenre && global.currentGenre !== "all") {
            rows = rows.filter((m) => {
                const pid = normalizeCatalogProductId(m.product || m.产品);
                return global.productGenreMap[pid] === global.currentGenre;
            });
        }
        return rows;
    }

    function renderDashboard() {
        const viewMetrics = getViewMetrics();
        if (typeof global.updateKPICards === "function") global.updateKPICards(viewMetrics);
        if (typeof global.updateProductCompare === "function") global.updateProductCompare(viewMetrics);
        if (typeof global.updateAlerts === "function") global.updateAlerts(viewMetrics);
        if (typeof global.updatePlatformRankings === "function") global.updatePlatformRankings(viewMetrics);
        if (typeof global.initChart === "function") global.initChart(viewMetrics);
    }

    async function loadFilterOptions() {
        const token = global.getToken?.();
        if (!token) return false;
        try {
            const fetchFn = global.authFetch || fetch;
            const response = await fetchFn(`/api/options`);
            if (response.status === 401) {
                if (typeof global.redirectToLogin === "function") {
                    global.redirectToLogin("/dashboard");
                } else {
                    if (typeof global.clearAuthToken === "function") global.clearAuthToken();
                    window.location.href = "/login?redirect=%2Fdashboard&reason=expired";
                }
                return false;
            }
            if (!response.ok) {
                console.error("加载筛选选项失败", response.status, await response.text());
                return false;
            }
            const result = await response.json();
            if (!result.success) return false;

            const productSelect = document.getElementById("product-select");
            const periodSelect = document.getElementById("time-period-select");

            global.dashboardMetricsTotal = Number(result.metrics_total || 0);
            global.dashboardDatasetProductIds = Array.isArray(result.dataset_product_ids)
                ? result.dataset_product_ids
                : [];

            if (productSelect) {
                global.allProductsCatalog = Array.isArray(result.products) ? result.products : [];
                global.productGenreMap = {};
                global.allProductsCatalog.forEach((p) => {
                    if (p.genre) global.productGenreMap[p.id] = p.genre;
                });
            }

            const sourceSelect = document.getElementById("data-source-select");
            if (sourceSelect && Array.isArray(result.data_sources) && result.data_sources.length) {
                const prevSource = sourceSelect.value || global.currentDataSource || "all";
                sourceSelect.innerHTML = "";
                result.data_sources.forEach((item) => {
                    const opt = document.createElement("option");
                    opt.value = item.id || item.name;
                    opt.textContent = item.name || item.id;
                    sourceSelect.appendChild(opt);
                });
                const nextSource = resolveDataSourceForDataset(result, prevSource);
                sourceSelect.value = [...sourceSelect.options].some((o) => o.value === nextSource)
                    ? nextSource
                    : "all";
                global.currentDataSource = sourceSelect.value;
            }

            const genreSelect = document.getElementById("genre-select");
            if (genreSelect && Array.isArray(result.genres) && result.genres.length) {
                const prev = genreSelect.value || "all";
                genreSelect.innerHTML = '<option value="all">全部品类</option>';
                result.genres.forEach((g) => {
                    const opt = document.createElement("option");
                    opt.value = g.id || g.name;
                    opt.textContent = g.name || g.id;
                    genreSelect.appendChild(opt);
                });
                genreSelect.value = [...genreSelect.options].some((o) => o.value === prev) ? prev : "all";
                global.currentGenre = genreSelect.value;
            }

            applyGenreToProductSelect();

            if (global.DataProvenance && result.data_trust) {
                const prov = {
                    source: result.data_source,
                    trust: result.data_trust,
                    show_mock_warning: result.data_source === "mock" || result.data_source === "empty",
                    collapse_demo_metrics: result.data_source === "mvp_steam" || result.data_source === "imported",
                    needs_crawl: result.data_source === "empty",
                };
                global.DataProvenance.renderBanner("data-provenance-banner", prov);
                if (global.DashboardGovernance) global.DashboardGovernance.apply(prov);
            }

            if (periodSelect && Array.isArray(result.time_periods) && result.time_periods.length) {
                const prevPeriod = periodSelect.value || global.currentTimePeriod || "all";
                periodSelect.innerHTML = "";
                const nextPeriod = resolveTimePeriodForDataset(result.time_periods, prevPeriod);
                result.time_periods.forEach((item) => {
                    global.timePeriodLabels[item.id] = item.name || item.id;
                    const option = document.createElement("option");
                    option.value = item.id;
                    option.textContent = item.name || item.id;
                    option.selected = item.id === nextPeriod;
                    periodSelect.appendChild(option);
                });
                global.currentTimePeriod = periodSelect.value || nextPeriod;
                const crawlSnapshot =
                    result.time_periods.length === 1 && result.time_periods[0].id === "all" ||
                    result.time_periods.some((p) => /^\d{4}-\d{2}-\d{2}$/.test(String(p.id || "")));
                if (crawlSnapshot) {
                    periodSelect.closest(".filter-group")?.classList.add("filter-group-dim");
                } else {
                    periodSelect.closest(".filter-group")?.classList.remove("filter-group-dim");
                }
            }

            if (typeof global.syncReportProductOptions === "function") {
                global.syncReportProductOptions(result.products);
            }
            syncFiltersFromDom();
            if (typeof global.renderProductList === "function") global.renderProductList();
            updateLinkedProductSummaries();
            return true;
        } catch (e) {
            console.error("加载筛选选项失败", e);
            return false;
        }
    }

    async function loadData(forceRefresh) {
        const checkAuth = global.checkAuth || (() => !!global.getToken?.());
        if (!checkAuth()) return;
        try {
            const shouldForce =
                !!forceRefresh ||
                (Number(global.dashboardMetricsTotal || 0) > 0 &&
                    (!Array.isArray(global.allMetricsData) || global.allMetricsData.length === 0));
            await ensureMetricsLoaded(shouldForce);
            renderDashboard();
            updateLinkedProductSummaries();
        } catch (e) {
            console.error("加载失败", e);
        }
    }

    function onFilterChange() {
        if (global.allProductsCatalog.length) {
            applyFiltersToProductSelect();
        }
        global.debouncedApplyFilters();
    }

    function applyFilters() {
        syncFiltersFromDom();
        updateLinkedProductSummaries();
        loadData(true);
    }

    function resetFilters() {
        if (typeof global.showDashboardFilterHint === "function") {
            global.showDashboardFilterHint("");
        }
        const productSelect = document.getElementById("product-select");
        if (productSelect) {
            Array.from(productSelect.options).forEach((o) => {
                o.selected = true;
            });
            if (global.ProductPicker) {
                global.ProductPicker.syncAllMountsFromHiddenSelect("product-select");
            }
        }
        const periodSelect = document.getElementById("time-period-select");
        if (periodSelect && periodSelect.options.length) {
            const allOpt = [...periodSelect.options].find((o) => o.value === "all");
            periodSelect.value = allOpt ? "all" : periodSelect.options[0].value;
        }
        const sourceSelect = document.getElementById("data-source-select");
        if (sourceSelect) sourceSelect.value = "all";
        const genreSelect = document.getElementById("genre-select");
        if (genreSelect) {
            genreSelect.value = "all";
            global.currentGenre = "all";
        }
        if (global.allProductsCatalog.length) {
            applyGenreToProductSelect();
        }
        syncFiltersFromDom();
        loadData(true);
    }

    function filterMetricsForView(metrics) {
        if (!Array.isArray(metrics)) return [];
        let rows = metrics.slice();
        if (global.selectedProducts && global.selectedProducts.length) {
            rows = rows.filter((m) => global.selectedProducts.some((pid) => productRecordMatches(m, pid)));
        }
        if (global.currentGenre && global.currentGenre !== "all") {
            rows = rows.filter((m) => {
                const pid = m.product || m.产品;
                return global.productGenreMap[pid] === global.currentGenre;
            });
        }
        if (global.currentTimePeriod && global.currentTimePeriod !== "all") {
            rows = rows.filter((m) => metricMatchesPeriod(m, global.currentTimePeriod));
        }
        if (global.currentDataSource && global.currentDataSource !== "all") {
            const src = global.currentDataSource.replace(/_/g, " ").toLowerCase();
            rows = rows.filter((m) => {
                const ch = String(m.channel || m.platform || m.平台 || "").toLowerCase();
                return ch === src || ch.replace(/\s+/g, " ") === src;
            });
        }
        return rows;
    }

    function filterMetricsByPeriodAndSource(metrics) {
        if (!Array.isArray(metrics)) return [];
        let rows = metrics.slice();
        if (global.currentTimePeriod && global.currentTimePeriod !== "all") {
            rows = rows.filter((m) => metricMatchesPeriod(m, global.currentTimePeriod));
        }
        if (global.currentDataSource && global.currentDataSource !== "all") {
            const src = global.currentDataSource.replace(/_/g, " ").toLowerCase();
            rows = rows.filter((m) => {
                const ch = String(m.channel || m.platform || m.平台 || "").toLowerCase();
                return ch === src || ch.replace(/\s+/g, " ") === src;
            });
        }
        return rows;
    }

    function filterMetricsByGenre(metrics) {
        if (!Array.isArray(metrics)) return [];
        if (!global.currentGenre || global.currentGenre === "all") return metrics;
        return metrics.filter((m) => global.productGenreMap[m.product] === global.currentGenre);
    }

    global.filterMetricsByPeriodAndSource = filterMetricsByPeriodAndSource;
    global.filterMetricsByGenre = filterMetricsByGenre;

    global.debouncedApplyFilters = debounce(() => loadData(false), 250);

    global.normalizeCatalogProductId = normalizeCatalogProductId;
    global.metricMatchesPeriod = metricMatchesPeriod;
    global.productRecordMatches = productRecordMatches;
    global.syncFiltersFromDom = syncFiltersFromDom;
    global.getDashboardProductIds = getSelectedProductIds;
    global.formatDashboardProductSelection = formatDashboardProductSelection;
    global.updateLinkedProductSummaries = updateLinkedProductSummaries;
    global.applyGenreToProductSelect = applyGenreToProductSelect;
    global.applyFiltersToProductSelect = applyFiltersToProductSelect;
    global.productsMatchingDataSource = productsMatchingDataSource;
    global.getSelectedProductIds = getSelectedProductIds;
    global.fillProductSelect = fillProductSelect;
    global.renderProductPickers = renderProductPickers;
    global.loadFilterOptions = loadFilterOptions;
    global.fetchMetricsWithFilters = fetchMetricsWithFilters;
    global.ensureMetricsLoaded = ensureMetricsLoaded;
    global.getViewMetrics = getViewMetrics;
    global.renderDashboard = renderDashboard;
    global.onFilterChange = onFilterChange;
    global.applyFilters = applyFilters;
    global.resetFilters = resetFilters;
    global.loadData = loadData;
    global.filterMetricsForView = filterMetricsForView;
    global.setDashboardLoading = setDashboardLoading;

    global.DashboardFilters = {
        loadFilterOptions,
        applyFilters,
        loadData,
        getViewMetrics,
        renderDashboard,
        metricMatchesPeriod,
        productRecordMatches,
    };
})(typeof window !== "undefined" ? window : globalThis);
