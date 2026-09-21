/** Data provenance badges for dashboard and compare views. */
(function (global) {
    const TRUST_STYLES = {
        high: { bg: 'rgba(34,197,94,0.15)', border: '#22c55e', color: '#86efac' },
        medium: { bg: 'rgba(234,179,8,0.12)', border: '#eab308', color: '#fde047' },
        low: { bg: 'rgba(239,68,68,0.12)', border: '#ef4444', color: '#fca5a5' },
    };

    function renderBadge(trust, source) {
        const level = (trust && trust.level) || 'medium';
        const style = TRUST_STYLES[level] || TRUST_STYLES.medium;
        const label = (trust && trust.label) || source || '未知来源';
        const hint = (trust && trust.hint) || '';
        return (
            '<span class="data-trust-badge" data-level="' + level + '" title="' +
            escapeAttr(hint) +
            '" style="background:' +
            style.bg +
            ';border:1px solid ' +
            style.border +
            ';color:' +
            style.color +
            '">' +
            escapeHtml(label) +
            '</span>'
        );
    }

    function escapeHtml(s) {
        return String(s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function escapeAttr(s) {
        return escapeHtml(s).replace(/"/g, '&quot;');
    }

    function importCtaHtml() {
        return (
            '<a href="/import" class="data-trust-import-cta" ' +
            'style="margin-left:auto;font-size:0.8rem;color:#67e8f9;text-decoration:none;' +
            'padding:4px 10px;border-radius:8px;border:1px solid rgba(103,232,249,0.35);">' +
            '📥 导入真实数据</a>'
        );
    }

    function renderBanner(containerId, payload) {
        const el = document.getElementById(containerId);
        if (!el || !payload) return;
        const trust = payload.trust || {};
        const level = trust.level || 'medium';
        const badge = renderBadge(trust, payload.source);
        let extra = '';
        if (payload.source === 'empty' || payload.needs_crawl) {
            extra =
                '<span style="font-size:0.8rem;color:#fca5a5;">看板暂无数据，请先完成抓取后再查看指标</span>';
        } else if (payload.show_mock_warning) {
            extra =
                '<span style="font-size:0.8rem;color:#fca5a5;">演示 KPI 已弱化显示，请优先参考 Steam 口碑指标</span>';
        } else if (level === 'low') {
            extra =
                '<span style="font-size:0.8rem;color:#fde047;">可信度较低，结论仅供流程演示</span>';
        }
        let cta = '';
        if (payload.source === 'empty' || payload.needs_crawl) {
            cta =
                '<a href="/guide" style="margin-left:auto;font-size:0.8rem;color:#67e8f9;text-decoration:none;' +
                'padding:4px 10px;border-radius:8px;border:1px solid rgba(103,232,249,0.35);">🚀 先抓取</a>';
        } else if (payload.show_mock_warning || level === 'low' || payload.source === 'mock') {
            cta = importCtaHtml();
        }
        el.innerHTML =
            '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:10px 14px;border-radius:10px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);">' +
            '<span style="font-size:0.8rem;color:#94a3b8;">当前数据：</span>' +
            badge +
            extra +
            cta +
            '</div>';
        el.style.display = 'block';
        global.dataProvenance = payload;
    }

    async function fetchProvenance(token) {
        const t = token || (global.getAuthToken && global.getAuthToken()) || localStorage.getItem('access_token');
        if (!t) return null;
        const fetchFn = (typeof authFetch !== 'undefined' ? authFetch : fetch);
        const res = await fetchFn('/api/data/provenance');
        if (!res.ok) return null;
        return res.json();
    }

    const SOURCE_LABELS = {
        imported: { label: 'Owner 导入数据', level: 'high' },
        mvp_steam: { label: 'Steam 真数据', level: 'high' },
        mvp_multi: { label: '多平台真数据', level: 'high' },
        taptap_public: { label: 'TapTap 真数据', level: 'high' },
        google_play_public: { label: 'Google Play 真数据', level: 'high' },
        cached: { label: '缓存数据', level: 'medium' },
        mock: { label: '演示 Mock', level: 'low' },
        empty: { label: '暂无数据', level: 'low' },
    };

    function renderDataSourceBadge(source) {
        const meta = SOURCE_LABELS[source] || { label: source || '未知', level: 'medium' };
        return renderBadge({ level: meta.level, label: meta.label, hint: '数据来源：' + meta.label }, source);
    }

    global.DataProvenance = {
        renderBadge,
        renderBanner,
        renderDataSourceBadge,
        fetchProvenance,
        SOURCE_LABELS,
    };
})(typeof window !== 'undefined' ? window : globalThis);
