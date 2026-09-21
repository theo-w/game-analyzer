/**
 * Mouse-friendly multi product picker (replaces native <select multiple>).
 */
(function (global) {
    "use strict";

    const DEFAULT_MOUNT = "product-picker";
    const HIDDEN_SELECT_ID = "product-select";

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s || "";
        return d.innerHTML;
    }

    function getMountId(mountId) {
        return mountId || DEFAULT_MOUNT;
    }

    function hiddenSelectIdForMount(mountId) {
        const root = document.getElementById(getMountId(mountId));
        return (root && root.dataset.pickerHiddenSelect) || HIDDEN_SELECT_ID;
    }

    function getHiddenSelect(mountId) {
        return document.getElementById(hiddenSelectIdForMount(mountId));
    }

    function readCheckedIds(mountId) {
        const root = document.getElementById(getMountId(mountId));
        if (!root) return [];
        return Array.from(root.querySelectorAll('input[type="checkbox"][data-product-id]:checked')).map(
            (el) => el.getAttribute("data-product-id") || ""
        );
    }

    function syncHiddenSelectFromCheckboxes(mountId) {
        const select = getHiddenSelect(mountId);
        const ids = new Set(readCheckedIds(mountId));
        if (!select) return ids;
        Array.from(select.options).forEach((opt) => {
            opt.selected = ids.has(opt.value);
        });
        return ids;
    }

    function syncAllMountsFromHiddenSelect(hiddenSelectId) {
        const selectId = hiddenSelectId || HIDDEN_SELECT_ID;
        const selected = new Set(
            Array.from(document.getElementById(selectId)?.selectedOptions || []).map((o) => o.value)
        );
        document.querySelectorAll("[data-product-picker-mount]").forEach((root) => {
            if ((root.dataset.pickerHiddenSelect || HIDDEN_SELECT_ID) !== selectId) return;
            root.querySelectorAll('input[type="checkbox"][data-product-id]').forEach((input) => {
                input.checked = selected.has(input.getAttribute("data-product-id") || "");
            });
        });
    }

    function render(mountId, products, options) {
        options = options || {};
        const root = document.getElementById(getMountId(mountId));
        const hiddenId = options.hiddenSelectId || HIDDEN_SELECT_ID;
        const select = document.getElementById(hiddenId);
        if (!root || !Array.isArray(products)) return;

        root.dataset.productPickerMount = "1";
        root.dataset.pickerHiddenSelect = hiddenId;

        const selectedIds =
            options.selectedIds instanceof Set
                ? options.selectedIds
                : new Set(options.selectedIds || []);
        const defaultCount = options.defaultCount ?? 2;
        const emptyHint = options.emptyHint || "暂无产品，请先在分析向导抓取数据";

        if (!select) return;

        if (!products.length) {
            select.innerHTML = '<option value="" disabled selected>暂无产品</option>';
            root.innerHTML = '<p class="product-picker-empty">' + esc(emptyHint) + "</p>";
            return;
        }

        let html = "";
        products.forEach((item, index) => {
            const id = String(item.id || "");
            let name = item.name || id;
            if (name.length > 32) name = name.slice(0, 30) + "…";
            if (item.platform) name += " · " + item.platform;
            if (item.user_added) name += " · 自定义";
            const checked = selectedIds.size
                ? selectedIds.has(id)
                : index < Math.min(defaultCount, products.length);
            html +=
                '<label class="product-picker-item">' +
                '<input type="checkbox" data-product-id="' +
                esc(id) +
                '"' +
                (checked ? " checked" : "") +
                ">" +
                '<span class="product-picker-name" title="' +
                esc(item.name || id) +
                '">' +
                esc(name) +
                "</span>" +
                (item.genre
                    ? '<span class="product-picker-genre">' + esc(item.genre) + "</span>"
                    : "") +
                "</label>";
        });
        root.innerHTML = html;

        const nextIds = products.map((item) => String(item.id || ""));
        const existingIds = Array.from(select.options).map((opt) => opt.value);
        const needsRebuild =
            existingIds.length !== nextIds.length ||
            nextIds.some((id, index) => existingIds[index] !== id);

        if (needsRebuild) {
            select.innerHTML = "";
            products.forEach((item, index) => {
                const id = String(item.id || "");
                let name = item.name || id;
                if (item.platform) name += " · " + item.platform;
                const opt = document.createElement("option");
                opt.value = id;
                opt.textContent = name;
                opt.selected = selectedIds.size
                    ? selectedIds.has(id)
                    : index < Math.min(defaultCount, products.length);
                select.appendChild(opt);
            });
        } else {
            Array.from(select.options).forEach((opt) => {
                opt.selected = selectedIds.size ? selectedIds.has(opt.value) : opt.selected;
            });
        }

        root.querySelectorAll('input[type="checkbox"][data-product-id]').forEach((input) => {
            input.addEventListener("change", () => {
                syncHiddenSelectFromCheckboxes(mountId);
                syncAllMountsFromHiddenSelect(hiddenId);
                if (typeof options.onChange === "function") options.onChange(readCheckedIds(mountId));
            });
        });

        syncHiddenSelectFromCheckboxes(mountId);
    }

    function getSelectedIds(mountId) {
        syncHiddenSelectFromCheckboxes(mountId);
        const ids = readCheckedIds(mountId);
        if (ids.length) return ids;
        const select = getHiddenSelect(mountId);
        if (!select) return [];
        return Array.from(select.selectedOptions).map((o) => o.value);
    }

    function restoreStoredSelection(mountId, ids) {
        if (!Array.isArray(ids) || !ids.length) return;
        const idSet = new Set(ids);
        const hiddenId = hiddenSelectIdForMount(mountId);
        const select = document.getElementById(hiddenId);
        if (select) {
            Array.from(select.options).forEach((opt) => {
                opt.selected = idSet.has(opt.value);
            });
        }
        syncAllMountsFromHiddenSelect(hiddenId);
    }

    global.ProductPicker = {
        HIDDEN_SELECT_ID,
        DEFAULT_MOUNT,
        render,
        getSelectedIds,
        readCheckedIds,
        syncHiddenSelectFromCheckboxes,
        syncAllMountsFromHiddenSelect,
        restoreStoredSelection,
    };
})(typeof window !== "undefined" ? window : globalThis);
