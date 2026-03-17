/**
 * FinanzBro – Dashboard Frontend Logic
 * Fetches data from FastAPI backend and renders the dashboard.
 */

// ==================== State ====================
let portfolioData = null;
let sectorChart = null;
let scoreChart = null;
let currentFilter = 'all';
let currentSort = 'score-desc';
let displayCurrency = 'EUR'; // EUR or USD
let priceEventSource = null;
let wsConnected = false;

function getRate() {
    return portfolioData?.eur_usd_rate || 1.08;
}

function toDisplay(eurValue) {
    if (eurValue == null) return null;
    // Backend liefert alle Werte bereits in EUR
    if (displayCurrency === 'USD') return eurValue * getRate();
    return eurValue;  // EUR → passthrough
}

// ==================== Init ====================
document.addEventListener('DOMContentLoaded', () => {
    loadPortfolio();
    startPriceStream();
});

async function loadPortfolio() {
    showLoading(true);
    try {
        const res = await fetch('/api/portfolio');
        if (res.status === 503) {
            // Data still loading, retry after delay
            setTimeout(loadPortfolio, 2000);
            return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        portfolioData = await res.json();
        renderDashboard();
    } catch (err) {
        console.error('Portfolio laden fehlgeschlagen:', err);
        setTimeout(loadPortfolio, 3000); // Retry
        showLoading(false);
    }
}

// ==================== Render ====================
function renderDashboard() {
    if (!portfolioData) return;

    renderHeader();
    renderStats();
    renderMarketIndices();
    renderMovers();
    renderHeatmap();
    renderTable();
    renderRebalancing();
    renderTechPicks();

    // Lazy-load Analyse tab data if visible
    const analyseTab = document.getElementById('tab-analyse');
    if (analyseTab && analyseTab.classList.contains('active')) {
        renderAnalyseTab();
    }

    showLoading(false);
}

function renderHeader() {
    const d = portfolioData;

    // Demo badge
    const badge = document.getElementById('demoBadge');
    badge.style.display = d.is_demo ? 'inline-block' : 'none';

    // Portfolio value (converted)
    document.getElementById('totalValue').textContent = formatCurrency(toDisplay(d.total_value));

    // Cash info
    const cashStock = (d.stocks || []).find(s => s.position.ticker === 'CASH');
    const cashEl = document.getElementById('cashInfo');
    if (cashStock && cashEl) {
        const cashValue = toDisplay(cashStock.position.current_price);
        cashEl.textContent = `💵 Cash: ${formatCurrency(cashValue)}`;
    } else if (cashEl) {
        cashEl.textContent = '';
    }

    // P&L (Gesamt)
    const pnlEl = document.getElementById('portfolioPnl');
    const pnlConverted = toDisplay(d.total_pnl);
    const sign = pnlConverted >= 0 ? '+' : '';
    document.getElementById('totalPnl').textContent = `${sign}${formatCurrency(pnlConverted)}`;
    document.getElementById('totalPnlPct').textContent = `(${sign}${d.total_pnl_percent.toFixed(1)}%)`;
    pnlEl.className = `portfolio-pnl ${d.total_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`;

    // Daily change (Heute)
    const dailyEl = document.getElementById('dailyChange');
    const dailyEur = d.daily_total_change || 0;
    const dailyPct = d.daily_total_change_pct || 0;
    const dSign = dailyEur >= 0 ? '+' : '';
    document.getElementById('dailyPnl').textContent = `${dSign}${formatCurrency(dailyEur)}`;
    document.getElementById('dailyPnlPct').textContent = `(${dSign}${dailyPct.toFixed(2)}%)`;
    dailyEl.className = `portfolio-pnl daily-change ${dailyEur >= 0 ? 'pnl-positive' : 'pnl-negative'}`;

    // Currency toggle
    const toggleEl = document.getElementById('currencyToggle');
    if (toggleEl) {
        toggleEl.textContent = displayCurrency;
        toggleEl.title = `Wechselkurs: 1 EUR = ${getRate().toFixed(4)} USD`;
    }

    // Last update
    if (d.last_updated) {
        const dt = new Date(d.last_updated);
        document.getElementById('lastUpdate').textContent =
            `Letztes Update: ${dt.toLocaleString('de-DE')}`;
    }

    // Fear & Greed in header (if available)
    if (d.fear_greed && d.fear_greed.value !== 50) {
        const fg = d.fear_greed;
        const fgColor = fg.value <= 25 ? '#ef4444' : fg.value <= 45 ? '#f97316' : fg.value <= 55 ? '#eab308' : fg.value <= 75 ? '#22c55e' : '#3b82f6';
        document.getElementById('lastUpdate').innerHTML =
            `<span style="color:${fgColor};font-weight:700;">F&G: ${fg.value}</span> (${fg.label}) · ` +
            document.getElementById('lastUpdate').textContent;
    }
}

function renderStats() {
    const scores = portfolioData.scores || [];
    const buyCount = scores.filter(s => s.rating === 'buy').length;
    const holdCount = scores.filter(s => s.rating === 'hold').length;
    const sellCount = scores.filter(s => s.rating === 'sell').length;

    document.getElementById('statPositions').textContent = portfolioData.num_positions;
    document.getElementById('statBuy').textContent = buyCount;
    document.getElementById('statHold').textContent = holdCount;
    document.getElementById('statSell').textContent = sellCount;
}

function renderSectorChart(sectors) {
    const ctx = document.getElementById('sectorChart');
    if (!ctx) return;
    if (sectorChart) sectorChart.destroy();

    const colors = [
        '#3b82f6', '#8b5cf6', '#06b6d4', '#22c55e', '#eab308',
        '#ef4444', '#f97316', '#ec4899', '#14b8a6', '#6366f1'
    ];

    sectorChart = new Chart(ctx.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: sectors.map(s => s.sector),
            datasets: [{
                data: sectors.map(s => s.weight),
                backgroundColor: colors.slice(0, sectors.length),
                borderColor: '#1a2035',
                borderWidth: 2,
                hoverBorderWidth: 0,
                hoverOffset: 8,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#94a3b8',
                        font: { family: 'Inter', size: 11 },
                        padding: 12,
                        usePointStyle: true,
                        pointStyleWidth: 8,
                    }
                },
                tooltip: {
                    backgroundColor: '#1a2035',
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    cornerRadius: 8,
                    padding: 10,
                    callbacks: {
                        label: ctx => `${ctx.label}: ${ctx.raw.toFixed(1)}%`
                    }
                }
            }
        }
    });
}

let stockPriceChartInstance = null;

async function loadStockChart(ticker, period, btn) {
    // Update period buttons
    if (btn) {
        const parent = btn.parentElement;
        parent.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }

    try {
        const res = await fetch(`/api/stock/${ticker}/history?period=${period}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data || data.length < 2) return;

        const ctx = document.getElementById('stockPriceChart');
        if (!ctx) return;
        if (stockPriceChartInstance) stockPriceChartInstance.destroy();

        const first = data[0].close;
        const last = data[data.length - 1].close;
        const isUp = last >= first;
        const color = isUp ? '#22c55e' : '#ef4444';

        stockPriceChartInstance = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: data.map(d => d.date),
                datasets: [{
                    label: ticker,
                    data: data.map(d => d.close),
                    borderColor: color,
                    backgroundColor: (isUp ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)'),
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    pointHoverRadius: 3,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#64748b', font: { family: 'Inter', size: 10 }, maxTicksLimit: 6 }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { color: '#64748b', font: { family: 'Inter', size: 10 } }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1a2035',
                        titleColor: '#f1f5f9',
                        bodyColor: '#94a3b8',
                        callbacks: { label: ctx => `${formatCurrency(toDisplay(ctx.raw))}` }
                    }
                },
                interaction: { intersect: false, mode: 'index' }
            }
        });
    } catch (e) {
        console.log(`Kursverlauf für ${ticker} nicht verfügbar`);
    }
}

function renderTable() {
    const tbody = document.getElementById('portfolioTableBody');
    let stocks = getFilteredSorted();

    tbody.innerHTML = stocks.map(s => {
        const pos = s.position;
        const score = s.score;
        const rawValue = pos.shares * pos.current_price;
        const rawPnl = rawValue - pos.shares * pos.avg_cost;
        const pnlPct = pos.avg_cost > 0 ? ((pos.current_price - pos.avg_cost) / pos.avg_cost * 100) : 0;
        const value = toDisplay(rawValue);
        const pnl = toDisplay(rawPnl);

        // Tagesänderung in EUR berechnen
        const dailyPct = pos.daily_change_pct;
        const dailyEur = (dailyPct != null && pos.ticker !== 'CASH')
            ? toDisplay(rawValue * dailyPct / (100 + dailyPct))
            : null;
        const dailyClass = dailyPct > 0 ? 'positive' : dailyPct < 0 ? 'negative' : '';
        const dailySign = dailyPct != null && dailyPct >= 0 ? '+' : '';

        const scoreVal = score?.total_score || 0;
        const rating = score?.rating || 'hold';
        const scoreColor = rating === 'buy' ? '#22c55e' : rating === 'sell' ? '#ef4444' : '#eab308';
        const pnlClass = pnl >= 0 ? 'positive' : 'negative';
        const pnlSign = pnl >= 0 ? '+' : '';

        const ds = s.data_sources || {};
        const srcDots = ['fmp', 'technical', 'yfinance', 'alphavantage'].map(k => {
            const ok = ds[k];
            return `<span class="src-dot ${ok ? 'src-ok' : 'src-miss'}" title="${k}: ${ok ? '✓' : '✗'}"></span>`;
        }).join('');

        return `
            <tr data-ticker="${pos.ticker}" data-rating="${rating}">
                <td>
                    <div class="stock-info">
                        <div>
                            <div class="stock-name">${pos.name || pos.ticker}</div>
                            <div class="stock-ticker">${pos.ticker} <span class="src-dots">${srcDots}</span></div>
                        </div>
                    </div>
                </td>
                <td class="price-cell">${formatCurrency(toDisplay(pos.current_price))}</td>
                <td class="price-cell cost-cell">${pos.ticker !== 'CASH' ? formatCurrency(toDisplay(pos.avg_cost)) : '–'}</td>
                <td class="pnl-cell ${dailyClass}">
                    ${dailyPct != null ? `${dailySign}${formatCurrency(dailyEur)}<br><small>${dailySign}${dailyPct.toFixed(2)}%</small>` : '–'}
                </td>
                <td>${pos.shares.toFixed(2)}</td>
                <td class="price-cell">${formatCurrency(value)}</td>
                <td class="pnl-cell ${pnlClass}">
                    ${pnlSign}${formatCurrency(pnl)}<br>
                    <small>${pnlSign}${pnlPct.toFixed(1)}%</small>
                </td>
                <td>
                    <div class="score-bar">
                        <div class="score-bar-track">
                            <div class="score-bar-fill" style="width:${scoreVal}%;background:${scoreColor}"></div>
                        </div>
                        <span class="score-bar-value" style="color:${scoreColor}">${scoreVal.toFixed(0)}</span>
                    </div>
                </td>
                <td><span class="rating-badge rating-${rating}">${rating.toUpperCase()}</span></td>
                <td><button class="btn-detail" onclick="openStockDetail('${pos.ticker}')">Details</button></td>
            </tr>
        `;
    }).join('');

    // Cash row: separated at bottom
    const cashStock = (portfolioData.stocks || []).find(s => s.position.ticker === 'CASH');
    if (cashStock) {
        const cashPos = cashStock.position;
        const cashValue = toDisplay(cashPos.current_price);
        tbody.innerHTML += `
            <tr class="cash-separator"><td colspan="10"><hr></td></tr>
            <tr class="cash-row">
                <td>
                    <div class="stock-info">
                        <div>
                            <div class="stock-name">💵 Cash</div>
                            <div class="stock-ticker">Barbestand</div>
                        </div>
                    </div>
                </td>
                <td class="price-cell">–</td>
                <td class="price-cell cost-cell">–</td>
                <td class="pnl-cell">–</td>
                <td>–</td>
                <td class="price-cell">${formatCurrency(cashValue)}</td>
                <td class="pnl-cell">–</td>
                <td>–</td>
                <td>–</td>
                <td></td>
            </tr>
        `;
    }
}

function renderRebalancing() {
    const rb = portfolioData.rebalancing;
    if (!rb) return;

    document.getElementById('rebalancingSummary').textContent = rb.summary;

    const container = document.getElementById('rebalancingCards');
    const actions = rb.actions || [];

    // Sector warnings banner
    let warningsHTML = '';
    if (rb.sector_warnings && rb.sector_warnings.length > 0) {
        warningsHTML = `
            <div class="rebal-sector-warnings">
                ${rb.sector_warnings.map(w => `<div class="rebal-warning">${w}</div>`).join('')}
            </div>
        `;
    }

    // Summary totals
    let totalsHTML = '';
    if (rb.total_buy_amount > 0 || rb.total_sell_amount > 0) {
        totalsHTML = `
            <div class="rebal-totals">
                ${rb.total_sell_amount > 0 ? `<span class="rebal-total-sell">Verkaufen: ${formatCurrency(rb.total_sell_amount)}</span>` : ''}
                ${rb.total_buy_amount > 0 ? `<span class="rebal-total-buy">Kaufen: ${formatCurrency(rb.total_buy_amount)}</span>` : ''}
                <span class="rebal-total-net">Netto: ${formatCurrency(rb.net_rebalance)}</span>
            </div>
        `;
    }

    // Filter out "Halten" with very small amounts
    const relevantActions = actions.filter(a => a.action !== 'Halten' || a.amount_eur > 50);

    const cardsHTML = relevantActions.map(a => {
        const actionClass = a.action === 'Kaufen' ? 'buy' : a.action === 'Verkaufen' ? 'sell' : 'hold';
        const prioClass = a.priority >= 7 ? 'prio-high' : a.priority >= 4 ? 'prio-mid' : 'prio-low';

        // Score badge
        const scoreColor = a.rating === 'buy' ? '#22c55e' : a.rating === 'sell' ? '#ef4444' : '#eab308';
        const scoreChangeStr = a.score_change != null && Math.abs(a.score_change) >= 3
            ? ` <span style="font-size:0.7rem;color:${a.score_change > 0 ? '#22c55e' : '#ef4444'}">${a.score_change > 0 ? '↑' : '↓'}${Math.abs(a.score_change).toFixed(0)}</span>`
            : '';

        // Detailed reasons (use reasons array if available, fallback to reason string)
        const reasonsList = a.reasons && a.reasons.length > 0
            ? a.reasons.map(r => `<div class="rebal-reason-item">${r}</div>`).join('')
            : `<div class="rebal-reason-item">${a.reason}</div>`;

        return `
            <div class="rebal-card action-${actionClass}">
                <div class="rebal-card-header">
                    <div>
                        <div class="rebal-ticker">
                            ${a.ticker}
                            ${a.priority >= 4 ? `<span class="rebal-prio ${prioClass}" title="Priorität ${a.priority}/10">P${a.priority}</span>` : ''}
                        </div>
                        <div class="rebal-name">${a.name}${a.sector ? ` · ${a.sector}` : ''}</div>
                    </div>
                    <div class="rebal-header-right">
                        ${a.score > 0 ? `<span class="rebal-score" style="color:${scoreColor}">${a.score.toFixed(0)}${scoreChangeStr}</span>` : ''}
                        <span class="rebal-action ${a.action.toLowerCase()}">${a.action}</span>
                    </div>
                </div>
                <div class="rebal-weights">
                    <span class="rebal-weight current">${a.current_weight.toFixed(1)}%</span>
                    <span class="rebal-arrow">→</span>
                    <span class="rebal-weight target">${a.target_weight.toFixed(1)}%</span>
                </div>
                <div class="rebal-amount">
                    ${a.action !== 'Halten' ? `${formatCurrency(a.amount_eur)} (${a.shares_delta > 0 ? '+' : ''}${a.shares_delta.toFixed(1)} Stk.)` : ''}
                </div>
                <div class="rebal-reasons">${reasonsList}</div>
            </div>
        `;
    }).join('');

    container.innerHTML = warningsHTML + totalsHTML + cardsHTML;
}

function renderTechPicks() {
    const picks = portfolioData.tech_picks || [];
    const container = document.getElementById('techPicksGrid');

    container.innerHTML = picks.map(p => {
        const scoreClass = p.score >= 70 ? 'high' : p.score >= 40 ? 'medium' : 'low';
        const upsideStr = p.upside_percent != null
            ? `<span style="color:${p.upside_percent >= 0 ? '#22c55e' : '#ef4444'}">
                ${p.upside_percent >= 0 ? '+' : ''}${p.upside_percent.toFixed(1)}%
               </span>`
            : '–';

        // AI Summary Section
        const aiSummaryHTML = p.ai_summary
            ? `<div class="tech-ai-summary">🤖 ${p.ai_summary}</div>`
            : '';

        // Source badge
        const sourceHTML = p.source
            ? `<div class="tech-source">${p.source}</div>`
            : '';

        return `
            <div class="tech-card">
                <div class="tech-card-header">
                    <div>
                        <div class="tech-ticker">${p.ticker}</div>
                        <div class="tech-name">${p.name}</div>
                    </div>
                    <div class="tech-score-circle ${scoreClass}">${p.score.toFixed(0)}</div>
                </div>
                <div class="tech-stats">
                    <div>
                        <div class="tech-stat-label">Kurs</div>
                        <div class="tech-stat-value">${formatCurrency(p.current_price)}</div>
                    </div>
                    <div>
                        <div class="tech-stat-label">Upside</div>
                        <div class="tech-stat-value">${upsideStr}</div>
                    </div>
                    <div>
                        <div class="tech-stat-label">Revenue</div>
                        <div class="tech-stat-value">${p.revenue_growth != null ? (p.revenue_growth > 0 ? '+' : '') + p.revenue_growth.toFixed(0) + '%' : '–'}</div>
                    </div>
                    <div>
                        <div class="tech-stat-label">ROE</div>
                        <div class="tech-stat-value">${p.roe != null ? p.roe.toFixed(0) + '%' : '–'}</div>
                    </div>
                    <div>
                        <div class="tech-stat-label">PE Ratio</div>
                        <div class="tech-stat-value">${p.pe_ratio != null ? p.pe_ratio.toFixed(1) : '–'}</div>
                    </div>
                    <div>
                        <div class="tech-stat-label">Analyst</div>
                        <div class="tech-stat-value">${p.analyst_rating || '–'}</div>
                    </div>
                </div>
                ${aiSummaryHTML}
                <div class="tech-reason">${p.reason}</div>
                <div class="tech-tags">
                    ${(p.tags || []).map(t => `<span class="tech-tag">${t}</span>`).join('')}
                    ${sourceHTML}
                </div>
            </div>
        `;
    }).join('');
}

// ==================== Modal ====================
async function openStockDetail(ticker) {
    const modal = document.getElementById('stockModal');
    const stock = portfolioData.stocks.find(s => s.position.ticker === ticker);
    if (!stock) return;

    const pos = stock.position;
    const score = stock.score;
    const fd = stock.fundamentals;
    const analyst = stock.analyst;

    // Header
    document.getElementById('modalTitle').innerHTML = `
        <span style="color:var(--accent-blue)">${pos.ticker}</span> ${pos.name}
        <div class="modal-subtitle">${pos.sector} | ${pos.currency}</div>
    `;

    const ratingClass = score?.rating || 'hold';
    document.getElementById('modalRating').innerHTML = `
        <span class="rating-badge rating-${ratingClass}" style="font-size:0.85rem;padding:0.4rem 1rem;">
            ${(score?.rating || 'HOLD').toUpperCase()} – Score: ${(score?.total_score || 0).toFixed(1)}/100
        </span>
    `;

    // Body
    let bodyHTML = '';

    // Data Source Status
    const ds = stock.data_sources || {};
    const srcItems = [
        { key: 'parqet', label: 'Parqet' },
        { key: 'fmp', label: 'FMP' },
        { key: 'technical', label: 'Technical' },
        { key: 'yfinance', label: 'Yahoo' },
        { key: 'fear_greed', label: 'Fear&Greed' },
    ];
    bodyHTML += `
        <div class="modal-section">
            <div class="modal-section-title">Datenquellen</div>
            <div class="source-status-row">
                ${srcItems.map(s => `
                    <span class="source-badge ${ds[s.key] ? 'source-ok' : 'source-miss'}">
                        ${ds[s.key] ? '✓' : '✗'} ${s.label}
                    </span>
                `).join('')}
            </div>
        </div>
    `;

    // Score Breakdown
    if (score?.breakdown) {
        const bd = score.breakdown;
        const items = [
            { label: 'Qualit\u00e4t', value: bd.quality_score || bd.fundamental_score || 0, weight: '20%' },
            { label: 'Bewertung', value: bd.valuation_score || 0, weight: '15%' },
            { label: 'Analysten', value: bd.analyst_score || 0, weight: '15%' },
            { label: 'Technisch', value: bd.technical_score || 0, weight: '15%' },
            { label: 'Wachstum', value: bd.growth_score || 0, weight: '12%' },
            { label: 'Quantitativ', value: bd.quantitative_score || 0, weight: '10%' },
            { label: 'Sentiment', value: bd.sentiment_score || 0, weight: '8%' },
            { label: 'Insider', value: bd.insider_score || 0, weight: '3%' },
            { label: 'ESG', value: bd.esg_score || 0, weight: '2%' },
        ];

        bodyHTML += `
            <div class="modal-section">
                <div class="modal-section-title">Score-Aufschlüsselung</div>
                <div class="modal-breakdown">
                    ${items.map(it => {
            const color = it.value >= 70 ? '#22c55e' : it.value >= 40 ? '#eab308' : '#ef4444';
            return `
                            <div class="breakdown-item">
                                <span class="breakdown-label">${it.label} (${it.weight})</span>
                                <div class="breakdown-bar-track">
                                    <div class="breakdown-bar-fill" style="width:${it.value}%;background:${color}"></div>
                                </div>
                                <span class="breakdown-value" style="color:${color}">${it.value.toFixed(0)}</span>
                            </div>
                        `;
        }).join('')}
                </div>
            </div>
        `;
    }

    // Fundamentals
    if (fd) {
        const fmtPct = (v) => {
            if (v == null) return null;
            const pct = Math.abs(v) < 5 ? v * 100 : v;
            return pct.toFixed(1) + '%';
        };
        bodyHTML += `
            <div class="modal-section">
                <div class="modal-section-title">Fundamentaldaten</div>
                <div class="modal-metrics">
                    ${metricItem('PE Ratio', fd.pe_ratio?.toFixed(1))}
                    ${metricItem('PB Ratio', fd.pb_ratio?.toFixed(1))}
                    ${metricItem('ROE', fmtPct(fd.roe))}
                    ${metricItem('ROIC', fmtPct(fd.roic))}
                    ${metricItem('Debt/Equity', fd.debt_to_equity?.toFixed(2))}
                    ${metricItem('Gross Margin', fmtPct(fd.gross_margin))}
                    ${metricItem('Op. Margin', fmtPct(fd.operating_margin))}
                    ${metricItem('Net Margin', fmtPct(fd.net_margin))}
                    ${metricItem('EV/EBITDA', fd.ev_to_ebitda?.toFixed(1))}
                    ${metricItem('FCF Yield', fmtPct(fd.free_cashflow_yield))}
                    ${metricItem('PEG Ratio', fd.peg_ratio?.toFixed(2))}
                    ${metricItem('Mkt Cap', fd.market_cap ? formatLargeNumber(fd.market_cap) : null)}
                    ${metricItem('Altman Z', fd.altman_z_score?.toFixed(1))}
                    ${metricItem('Piotroski', fd.piotroski_score != null ? fd.piotroski_score + '/9' : null)}
                </div>
            </div>
        `;
    }

    // Analyst Data
    if (analyst && analyst.num_analysts > 0) {
        bodyHTML += `
            <div class="modal-section">
                <div class="modal-section-title">Analysten (${analyst.num_analysts})</div>
                <div class="modal-metrics">
                    ${metricItem('Konsens', analyst.consensus)}
                    ${metricItem('Preisziel', analyst.target_price ? formatCurrency(analyst.target_price) : null)}
                    ${metricItem('Strong Buy', analyst.strong_buy_count)}
                    ${metricItem('Buy', analyst.buy_count)}
                    ${metricItem('Hold', analyst.hold_count)}
                    ${metricItem('Sell', analyst.sell_count)}
                    ${metricItem('Strong Sell', analyst.strong_sell_count)}
                    ${metricItem('Upside', analyst.target_price && pos.current_price > 0
            ? ((analyst.target_price - pos.current_price) / pos.current_price * 100).toFixed(1) + '%'
            : null)}
                </div>
            </div>
        `;
    }

    // Technical Indicators
    const tech = stock.technical;
    if (tech && (tech.rsi_14 != null || tech.sma_cross || tech.momentum_30d != null)) {
        const signalEmoji = tech.signal === 'Bullish' ? '📈' : tech.signal === 'Bearish' ? '📉' : '➡️';
        const rsiLabel = tech.rsi_14 != null ?
            (tech.rsi_14 > 70 ? '⚠️ Überkauft' : tech.rsi_14 < 30 ? '⚠️ Überverkauft' : '✅ Normal') : null;
        const crossLabel = tech.sma_cross === 'golden' ? '🟢 Golden Cross' : tech.sma_cross === 'death' ? '🔴 Death Cross' : '➡️ Neutral';
        bodyHTML += `
            <div class="modal-section">
                <div class="modal-section-title">Technische Indikatoren</div>
                <div class="modal-metrics">
                    ${metricItem('Signal', signalEmoji + ' ' + tech.signal)}
                    ${metricItem('RSI(14)', tech.rsi_14 != null ? tech.rsi_14.toFixed(1) + ' (' + rsiLabel + ')' : null)}
                    ${metricItem('SMA Cross', crossLabel)}
                    ${metricItem('Momentum 30T', tech.momentum_30d != null ? (tech.momentum_30d > 0 ? '+' : '') + tech.momentum_30d.toFixed(1) + '%' : null)}
                    ${metricItem('SMA 50', tech.sma_50 != null ? tech.sma_50.toFixed(2) : null)}
                    ${metricItem('SMA 200', tech.sma_200 != null ? tech.sma_200.toFixed(2) : null)}
                    ${metricItem('Preis vs SMA50', tech.price_vs_sma50 != null ? (tech.price_vs_sma50 > 0 ? '+' : '') + tech.price_vs_sma50.toFixed(1) + '%' : null)}
                </div>
            </div>
        `;
    }

    // FMP Rating
    const fmpRating = stock.fmp_rating;
    if (fmpRating && fmpRating.rating) {
        bodyHTML += `
            <div class="modal-section">
                <div class="modal-section-title">FMP Rating</div>
                <div class="modal-metrics">
                    ${metricItem('Rating', fmpRating.rating)}
                    ${metricItem('Score', fmpRating.rating_score + '/5')}
                    ${metricItem('DCF', fmpRating.dcf_score + '/5')}
                    ${metricItem('ROE', fmpRating.roe_score + '/5')}
                    ${metricItem('ROA', fmpRating.roa_score + '/5')}
                    ${metricItem('D/E', fmpRating.de_score + '/5')}
                    ${metricItem('PE', fmpRating.pe_score + '/5')}
                    ${metricItem('PB', fmpRating.pb_score + '/5')}
                </div>
            </div>
        `;
    }

    // yFinance Data
    const yf = stock.yfinance;
    if (yf && (yf.recommendation_trend || yf.esg_risk_score != null || yf.insider_buy_count > 0 || yf.insider_sell_count > 0)) {
        const insiderTotal = (yf.insider_buy_count || 0) + (yf.insider_sell_count || 0);
        const insiderRatio = insiderTotal > 0 ? ((yf.insider_buy_count / insiderTotal) * 100).toFixed(0) + '% Käufe' : null;
        const esgLabel = yf.esg_risk_score != null ?
            (yf.esg_risk_score <= 10 ? '🟢 Niedrig' : yf.esg_risk_score <= 20 ? '🟢 Gering' :
                yf.esg_risk_score <= 30 ? '🟡 Mittel' : yf.esg_risk_score <= 40 ? '🟠 Hoch' : '🔴 Sehr hoch') : null;
        bodyHTML += `
            <div class="modal-section">
                <div class="modal-section-title">Yahoo Finance</div>
                <div class="modal-metrics">
                    ${metricItem('Empfehlung', yf.recommendation_trend)}
                    ${metricItem('ESG Risiko', yf.esg_risk_score != null ? yf.esg_risk_score.toFixed(1) + ' (' + esgLabel + ')' : null)}
                    ${metricItem('Insider Käufe', yf.insider_buy_count || 0)}
                    ${metricItem('Insider Verkäufe', yf.insider_sell_count || 0)}
                    ${metricItem('Insider Ratio', insiderRatio)}
                    ${metricItem('Earnings YoY', yf.earnings_growth_yoy != null ? (yf.earnings_growth_yoy > 0 ? '+' : '') + yf.earnings_growth_yoy.toFixed(1) + '%' : null)}
                </div>
            </div>
        `;
    }

    // AlphaVantage Data
    const av = stock.alphavantage;
    if (av && (av.news_sentiment != null || av.rsi_14 != null || av.macd_signal)) {
        const sentimentLabel = av.news_sentiment != null ?
            (av.news_sentiment > 0.15 ? '📈 Positiv' : av.news_sentiment < -0.15 ? '📉 Negativ' : '➡️ Neutral') : null;
        const rsiLabel = av.rsi_14 != null ?
            (av.rsi_14 > 70 ? '⚠️ Überkauft' : av.rsi_14 < 30 ? '⚠️ Überverkauft' : '✅ Normal') : null;
        bodyHTML += `
            <div class="modal-section">
                <div class="modal-section-title">Alpha Vantage</div>
                <div class="modal-metrics">
                    ${metricItem('News Sentiment', av.news_sentiment != null ? av.news_sentiment.toFixed(3) + ' (' + sentimentLabel + ')' : null)}
                    ${metricItem('RSI (14)', av.rsi_14 != null ? av.rsi_14.toFixed(1) + ' (' + rsiLabel + ')' : null)}
                    ${metricItem('MACD Signal', av.macd_signal)}
                </div>
            </div>
        `;
    }

    // Dividend Info
    const div = stock.dividend;
    if (div && (div.yield_percent || div.annual_dividend)) {
        bodyHTML += `
            <div class="modal-section">
                <div class="modal-section-title">💰 Dividende</div>
                <div class="modal-metrics">
                    ${metricItem('Rendite', div.yield_percent != null ? div.yield_percent.toFixed(2) + '%' : null)}
                    ${metricItem('Jährlich/Aktie', div.annual_dividend != null ? formatCurrency(toDisplay(div.annual_dividend)) : null)}
                    ${metricItem('Ex-Datum', div.ex_date)}
                    ${metricItem('Frequenz', div.frequency)}
                </div>
            </div>
        `;
    }

    // Stock Price Chart placeholder
    bodyHTML += `
        <div class="modal-section">
            <div class="modal-section-title">📊 Kursverlauf</div>
            <div class="modal-chart-controls">
                <button class="filter-btn active" onclick="loadStockChart('${pos.ticker}', '1month', this)">1M</button>
                <button class="filter-btn" onclick="loadStockChart('${pos.ticker}', '3month', this)">3M</button>
                <button class="filter-btn" onclick="loadStockChart('${pos.ticker}', '6month', this)">6M</button>
                <button class="filter-btn" onclick="loadStockChart('${pos.ticker}', '1year', this)">1Y</button>
            </div>
            <div style="height:200px;position:relative;">
                <canvas id="stockPriceChart"></canvas>
            </div>
        </div>
    `;

    // Score-History Chart (#9)
    bodyHTML += `
        <div class="modal-section">
            <div class="modal-section-title">📈 Score-Verlauf</div>
            <div style="height:160px;position:relative;">
                <canvas id="scoreHistoryChart"></canvas>
            </div>
        </div>
    `;

    // News section (#7)
    bodyHTML += `
        <div class="modal-section">
            <div class="modal-section-title">📰 Aktuelle News</div>
            <div id="stockNewsContainer"><div class="loading-text">News werden geladen...</div></div>
        </div>
    `;

    // Summary
    if (score?.summary) {
        bodyHTML += `
            <div class="modal-section">
                <div class="modal-summary">${score.summary}</div>
            </div>
        `;
    }

    document.getElementById('modalBody').innerHTML = bodyHTML;
    modal.classList.add('active');
    // Auto-load stock chart
    loadStockChart(pos.ticker, '3month');
    // Load score history
    loadScoreHistory(pos.ticker);
    // Load news
    loadStockNews(pos.ticker);
}

function metricItem(label, value) {
    return `
        <div class="metric-item">
            <div class="metric-label">${label}</div>
            <div class="metric-value">${value != null ? value : '–'}</div>
        </div>
    `;
}

function closeModal(event) {
    if (event && event.target !== document.getElementById('stockModal')) return;
    document.getElementById('stockModal').classList.remove('active');
}

// Close on click outside or argument-less call
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        document.getElementById('stockModal').classList.remove('active');
    }
});

// ==================== Tabs ====================
function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
    document.getElementById(`tab-${tab}`).classList.add('active');

    // Load analyse tab data on first view
    if (tab === 'analyse') {
        renderAnalyseTab();
    }
    // Load historie tab data on first view
    if (tab === 'historie') {
        loadPerformanceKPIs();
    }
}

// ==================== Filter & Sort ====================
function filterTable(filter, btn) {
    currentFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    renderTable();
}

function sortTable(field) {
    const [curField, curDir] = currentSort.split('-');
    // Toggle direction if same field, otherwise default to desc (except name → asc)
    if (curField === field) {
        currentSort = field + '-' + (curDir === 'desc' ? 'asc' : 'desc');
    } else {
        currentSort = field + '-' + (field === 'name' ? 'asc' : 'desc');
    }
    const [newField, newDir] = currentSort.split('-');
    const arrow = newDir === 'desc' ? ' ▼' : ' ▲';

    // Update column header arrows
    document.querySelectorAll('.sort-arrow').forEach(el => el.textContent = '');
    const arrowEl = document.getElementById('sort-' + newField);
    if (arrowEl) arrowEl.textContent = arrow;

    // Update sort buttons
    document.querySelectorAll('.sort-btn').forEach(btn => {
        btn.classList.remove('active');
        // Remove old arrows from button text
        btn.textContent = btn.textContent.replace(/ [▲▼]$/, '');
    });
    const activeBtn = document.getElementById('sortBtn-' + newField);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.textContent = activeBtn.textContent + arrow;
    }
    renderTable();
}

function getFilteredSorted() {
    let stocks = (portfolioData.stocks || []).filter(s => s.position.ticker !== 'CASH');

    // Filter
    if (currentFilter !== 'all') {
        stocks = stocks.filter(s => s.score?.rating === currentFilter);
    }

    // Sort
    const [field, dir] = currentSort.split('-');
    const mult = dir === 'desc' ? -1 : 1;

    stocks.sort((a, b) => {
        switch (field) {
            case 'score':
                return mult * ((a.score?.total_score || 0) - (b.score?.total_score || 0));
            case 'value':
                return mult * ((a.position.shares * a.position.current_price) -
                    (b.position.shares * b.position.current_price));
            case 'pnl': {
                const pnlA = (a.position.current_price - a.position.avg_cost) / Math.max(a.position.avg_cost, 0.01);
                const pnlB = (b.position.current_price - b.position.avg_cost) / Math.max(b.position.avg_cost, 0.01);
                return mult * (pnlA - pnlB);
            }
            case 'name':
                return mult * (a.position.name || a.position.ticker).localeCompare(b.position.name || b.position.ticker);
            case 'price':
                return mult * (a.position.current_price - b.position.current_price);
            case 'cost':
                return mult * (a.position.avg_cost - b.position.avg_cost);
            case 'daily':
                return mult * ((a.position.daily_change_pct || 0) - (b.position.daily_change_pct || 0));
            case 'shares':
                return mult * (a.position.shares - b.position.shares);
            default:
                return 0;
        }
    });

    return stocks;
}

// ==================== Refresh ====================
async function updateParqet() {
    const btn = document.getElementById('btnUpdateParqet');
    const btnFull = document.getElementById('btnRefresh');
    const lastUpdate = document.getElementById('lastUpdate');

    btn.classList.add('refreshing');
    btn.disabled = true;
    btnFull.disabled = true;
    lastUpdate.textContent = '🔄 Parqet wird aktualisiert...';

    try {
        const res = await fetch('/api/refresh/parqet', { method: 'POST' });
        const result = await res.json();

        if (result.status === 'done') {
            lastUpdate.textContent = `✅ ${result.positions} Positionen, ${result.total_eur?.toLocaleString('de-DE', { minimumFractionDigits: 2 })} EUR (Cash: ${result.cash_eur?.toLocaleString('de-DE', { minimumFractionDigits: 2 })} EUR)`;
            // Reload portfolio data
            await loadPortfolio();
        } else {
            lastUpdate.textContent = `⚠️ ${result.message || 'Fehler'}`;
        }
    } catch (err) {
        console.error('Update Parqet fehlgeschlagen:', err);
        lastUpdate.textContent = '❌ Update fehlgeschlagen';
    } finally {
        btn.classList.remove('refreshing');
        btn.disabled = false;
        btnFull.disabled = false;
    }
}

async function triggerReport() {
    const btn = document.getElementById('btnTelegramReport');
    const lastUpdate = document.getElementById('lastUpdate');

    btn.classList.add('refreshing');
    btn.disabled = true;

    try {
        const res = await fetch('/api/trigger-report', { method: 'POST' });
        const result = await res.json();

        if (result.status === 'started') {
            lastUpdate.textContent = `📨 ${result.message}`;
        } else {
            lastUpdate.textContent = `⚠️ ${result.message}`;
        }
    } catch (err) {
        console.error('Telegram Report fehlgeschlagen:', err);
        lastUpdate.textContent = '❌ Report fehlgeschlagen';
    } finally {
        // Button nach 3s wieder freigeben (Report läuft im Background)
        setTimeout(() => {
            btn.classList.remove('refreshing');
            btn.disabled = false;
        }, 3000);
    }
}

async function refreshData() {
    await _doRefresh('btnRefresh', '/api/refresh');
}

async function refreshPortfolio() {
    await _doRefresh('btnRefreshPortfolio', '/api/refresh/portfolio');
}

async function refreshScores() {
    await _doRefresh('btnRefreshScores', '/api/refresh/scores');
}

async function _doRefresh(btnId, endpoint) {
    const btn = document.getElementById(btnId);
    const btnParqet = document.getElementById('btnUpdateParqet');
    const btnTelegram = document.getElementById('btnTelegramReport');
    if (btn) btn.classList.add('refreshing');
    if (btn) btn.disabled = true;
    if (btnParqet) btnParqet.disabled = true;
    if (btnTelegram) btnTelegram.disabled = true;

    try {
        const res = await fetch(endpoint, { method: 'POST' });
        const result = await res.json();

        // Show status message
        const lastUpdate = document.getElementById('lastUpdate');
        lastUpdate.textContent = result.message || '🔬 Komplette Analyse läuft...';

        // Poll for completion
        let attempts = 0;
        const poll = setInterval(async () => {
            attempts++;
            try {
                const statusRes = await fetch('/api/status');
                const status = await statusRes.json();
                if (!status.refreshing || attempts > 120) {
                    clearInterval(poll);
                    await loadPortfolio();
                    if (btn) { btn.classList.remove('refreshing'); btn.disabled = false; }
                    if (btnParqet) btnParqet.disabled = false;
                    if (btnTelegram) btnTelegram.disabled = false;
                }
            } catch (e) {
                clearInterval(poll);
                if (btn) { btn.classList.remove('refreshing'); btn.disabled = false; }
                if (btnParqet) btnParqet.disabled = false;
                if (btnTelegram) btnTelegram.disabled = false;
            }
        }, 2000);
    } catch (err) {
        console.error('Analyse fehlgeschlagen:', err);
        if (btn) { btn.classList.remove('refreshing'); btn.disabled = false; }
        if (btnParqet) btnParqet.disabled = false;
        if (btnTelegram) btnTelegram.disabled = false;
    }
}

// ==================== Helpers ====================
function formatCurrency(val) {
    if (val == null) return '–';
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: displayCurrency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(val);
}

function toggleCurrency() {
    displayCurrency = displayCurrency === 'EUR' ? 'USD' : 'EUR';
    renderDashboard();
}

function formatLargeNumber(val) {
    const sym = displayCurrency === 'EUR' ? '€' : '$';
    const displayVal = toDisplay(val);
    if (displayVal >= 1e12) return `${sym}${(displayVal / 1e12).toFixed(1)}T`;
    if (displayVal >= 1e9) return `${sym}${(displayVal / 1e9).toFixed(1)}B`;
    if (displayVal >= 1e6) return `${sym}${(displayVal / 1e6).toFixed(1)}M`;
    return formatCurrency(displayVal);
}

function showLoading(show) {
    const overlay = document.getElementById('loadingOverlay');
    if (show) overlay.classList.add('active');
    else overlay.classList.remove('active');
}

// ==================== Live Price Stream (SSE) ====================
function startPriceStream() {
    if (priceEventSource) {
        priceEventSource.close();
        priceEventSource = null;
    }

    try {
        priceEventSource = new EventSource('/api/prices/stream');

        priceEventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                // Timeout event – reconnect
                if (data.type === 'timeout') {
                    priceEventSource.close();
                    setTimeout(startPriceStream, 1000);
                    return;
                }

                // Update WebSocket connection status
                if (data.ws_connected !== undefined) {
                    wsConnected = data.ws_connected;
                    updateLiveIndicator();
                }

                // Apply price updates
                if (data.prices && portfolioData) {
                    applyPriceUpdates(data.prices);
                }
            } catch (e) {
                // Ignore parse errors (keepalive comments etc.)
            }
        };

        priceEventSource.onerror = () => {
            wsConnected = false;
            updateLiveIndicator();
            priceEventSource.close();
            // Reconnect after 5 seconds
            setTimeout(startPriceStream, 5000);
        };
    } catch (e) {
        console.log('SSE nicht verfügbar:', e);
    }
}

function applyPriceUpdates(prices) {
    if (!portfolioData || !portfolioData.stocks) return;

    let totalValue = 0;
    let totalCost = 0;
    let updated = false;

    for (const stock of portfolioData.stocks) {
        const ticker = stock.position.ticker;
        if (prices[ticker] !== undefined && prices[ticker] > 0) {
            stock.position.current_price = prices[ticker];
            updated = true;
        }
        totalValue += stock.position.shares * stock.position.current_price;
        totalCost += stock.position.shares * stock.position.avg_cost;
    }

    if (!updated) return;

    // Update portfolio totals
    portfolioData.total_value = totalValue;
    portfolioData.total_cost = totalCost;
    portfolioData.total_pnl = totalValue - totalCost;
    portfolioData.total_pnl_percent = totalCost > 0
        ? ((totalValue - totalCost) / totalCost * 100) : 0;

    // Update DOM directly (no full re-render for performance)
    updateHeaderValues();
    updateTablePrices(prices);
}

function updateHeaderValues() {
    const d = portfolioData;
    const totalEl = document.getElementById('totalValue');
    const pnlEl = document.getElementById('portfolioPnl');

    if (totalEl) {
        totalEl.textContent = formatCurrency(toDisplay(d.total_value));
        // Brief flash animation
        totalEl.classList.add('price-flash');
        setTimeout(() => totalEl.classList.remove('price-flash'), 600);
    }

    if (pnlEl) {
        const pnlConverted = toDisplay(d.total_pnl);
        const sign = pnlConverted >= 0 ? '+' : '';
        document.getElementById('totalPnl').textContent = `${sign}${formatCurrency(pnlConverted)}`;
        document.getElementById('totalPnlPct').textContent = `(${sign}${d.total_pnl_percent.toFixed(1)}%)`;
        pnlEl.className = `portfolio-pnl ${d.total_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`;
    }
}

function updateTablePrices(prices) {
    const tbody = document.getElementById('portfolioTableBody');
    if (!tbody) return;

    for (const [ticker, price] of Object.entries(prices)) {
        const row = tbody.querySelector(`tr[data-ticker="${ticker}"]`);
        if (!row) continue;

        const stock = portfolioData.stocks.find(s => s.position.ticker === ticker);
        if (!stock) continue;

        const pos = stock.position;
        const rawValue = pos.shares * pos.current_price;
        const rawPnl = rawValue - pos.shares * pos.avg_cost;
        const pnlPct = pos.avg_cost > 0 ? ((pos.current_price - pos.avg_cost) / pos.avg_cost * 100) : 0;
        const value = toDisplay(rawValue);
        const pnl = toDisplay(rawPnl);
        const pnlSign = pnl >= 0 ? '+' : '';

        // Update price cell
        const priceCell = row.querySelector('.price-cell');
        if (priceCell) {
            priceCell.textContent = formatCurrency(toDisplay(pos.current_price));
            priceCell.classList.add('price-flash');
            setTimeout(() => priceCell.classList.remove('price-flash'), 600);
        }

        // Update PnL cell
        const pnlCell = row.querySelector('.pnl-cell');
        if (pnlCell) {
            const pnlClass = pnl >= 0 ? 'positive' : 'negative';
            pnlCell.className = `pnl-cell ${pnlClass}`;
            pnlCell.innerHTML = `${pnlSign}${formatCurrency(pnl)}<br><small>${pnlSign}${pnlPct.toFixed(1)}%</small>`;
        }
    }
}

function updateLiveIndicator() {
    let indicator = document.getElementById('liveIndicator');
    if (!indicator) {
        // Create indicator next to lastUpdate
        const lastUpdate = document.getElementById('lastUpdate');
        if (!lastUpdate) return;
        indicator = document.createElement('span');
        indicator.id = 'liveIndicator';
        indicator.style.cssText = 'margin-left:8px;font-size:0.75rem;';
        lastUpdate.parentElement.insertBefore(indicator, lastUpdate.nextSibling);
    }
    if (wsConnected) {
        indicator.innerHTML = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite;margin-right:4px;vertical-align:middle;"></span><span style="color:#22c55e;font-weight:600;">LIVE</span>';
    } else {
        indicator.innerHTML = '';
    }
}

// ==================== Analyse Tab ====================
let analyseLoaded = false;
let benchmarkChartInstance = null;

async function renderAnalyseTab() {
    if (analyseLoaded) return;
    analyseLoaded = true;

    // Sector chart in Analyse tab laden
    try {
        const sectorRes = await fetch('/api/sectors');
        if (sectorRes.ok) {
            const sectors = await sectorRes.json();
            renderSectorChart(sectors);
        }
    } catch (e) { console.log('Sektor-Daten nicht verfügbar'); }

    // Parallel laden
    renderRisk();
    loadBenchmark();
    renderDividends();
    renderCorrelation();
    renderEarnings();
}

async function renderMarketIndices() {
    try {
        const res = await fetch('/api/market-indices');
        if (!res.ok) return;
        const data = await res.json();

        const container = document.getElementById('headerIndices');
        if (!container) return;

        container.innerHTML = data.map(idx => {
            const sign = idx.change_pct >= 0 ? '+' : '';
            const color = idx.change_pct >= 0 ? 'var(--green)' : 'var(--red)';
            return `<span class="header-index"><span class="header-index-name">${idx.name}</span> <span style="color:${color};font-weight:700">${sign}${idx.change_pct.toFixed(2)}%</span></span>`;
        }).join('');
    } catch (e) { console.log('Market-Indices nicht verfügbar'); }
}

async function renderMovers() {
    try {
        const res = await fetch('/api/movers');
        if (!res.ok) return;
        const data = await res.json();

        const winnersEl = document.getElementById('winnersContainer');
        const losersEl = document.getElementById('losersContainer');

        winnersEl.innerHTML = (data.winners || []).map(m => `
            <div class="mover-item mover-up">
                <div class="mover-info">
                    <span class="mover-ticker">${m.ticker}</span>
                    <span class="mover-name">${m.name}</span>
                </div>
                <div class="mover-values">
                    <span class="mover-pct">+${m.daily_pct.toFixed(2)}%</span>
                    <span class="mover-eur">+${formatCurrency(m.daily_eur)}</span>
                </div>
            </div>
        `).join('') || '<div class="empty-state">Keine Gewinner heute</div>';

        losersEl.innerHTML = (data.losers || []).map(m => `
            <div class="mover-item mover-down">
                <div class="mover-info">
                    <span class="mover-ticker">${m.ticker}</span>
                    <span class="mover-name">${m.name}</span>
                </div>
                <div class="mover-values">
                    <span class="mover-pct">${m.daily_pct.toFixed(2)}%</span>
                    <span class="mover-eur">${formatCurrency(m.daily_eur)}</span>
                </div>
            </div>
        `).join('') || '<div class="empty-state">Keine Verlierer heute</div>';
    } catch (e) { console.log('Movers nicht verfügbar'); }
}

async function renderHeatmap() {
    try {
        const res = await fetch('/api/heatmap');
        if (!res.ok) return;
        const data = await res.json();
        const container = document.getElementById('heatmapContainer');
        if (!data.length) { container.innerHTML = '<div class="empty-state">Keine Daten</div>'; return; }

        // Sort: biggest winners first, biggest losers last
        data.sort((a, b) => b.daily_pct - a.daily_pct);

        // Equal distribution across 2 rows
        const cols = Math.ceil(data.length / 2);
        container.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;

        container.innerHTML = data.map(d => {
            const pct = d.daily_pct;
            const bg = pct > 2 ? '#166534' : pct > 0.5 ? '#15803d' : pct > 0 ? '#22c55e40'
                : pct > -0.5 ? '#ef444440' : pct > -2 ? '#dc2626' : '#991b1b';
            const textColor = Math.abs(pct) > 0.5 ? '#fff' : '#94a3b8';
            return `
                <div class="heatmap-cell" style="background:${bg};" 
                     title="${d.name}\n${d.sector}\nGewicht: ${d.weight.toFixed(1)}%\nHeute: ${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%\nScore: ${d.score}/100">
                    <span class="heatmap-ticker" style="color:${textColor}">${d.ticker}</span>
                    <span class="heatmap-pct" style="color:${textColor}">${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%</span>
                </div>
            `;
        }).join('');
    } catch (e) { console.log('Heatmap nicht verfügbar'); }
}

async function renderRisk() {
    try {
        const res = await fetch('/api/risk');
        if (!res.ok) return;
        const data = await res.json();
        const container = document.getElementById('riskContainer');

        const riskColor = data.risk_score <= 3 ? '#22c55e' : data.risk_score <= 6 ? '#eab308' : '#ef4444';
        const gaugeWidth = data.risk_score * 10;

        container.innerHTML = `
            <div class="risk-gauge">
                <div class="risk-gauge-label">Risk Score</div>
                <div class="risk-gauge-bar">
                    <div class="risk-gauge-fill" style="width:${gaugeWidth}%;background:${riskColor}"></div>
                </div>
                <div class="risk-gauge-value" style="color:${riskColor}">${data.risk_score}/10 — ${data.risk_level}</div>
            </div>
            <div class="risk-metrics">
                <div class="risk-metric">
                    <span class="risk-metric-label">Portfolio Beta</span>
                    <span class="risk-metric-value">${data.portfolio_beta}</span>
                </div>
                <div class="risk-metric">
                    <span class="risk-metric-label">Volatilität (p.a.)</span>
                    <span class="risk-metric-value">${data.volatility_annual}%</span>
                </div>
                <div class="risk-metric">
                    <span class="risk-metric-label">VaR 95% (täglich)</span>
                    <span class="risk-metric-value" style="color:#ef4444">-${data.var_95_daily}%</span>
                </div>
                <div class="risk-metric">
                    <span class="risk-metric-label">VaR 95% (monatlich)</span>
                    <span class="risk-metric-value" style="color:#ef4444">-${data.var_95_monthly}%</span>
                </div>
                <div class="risk-metric">
                    <span class="risk-metric-label">Max Drawdown</span>
                    <span class="risk-metric-value" style="color:#ef4444">-${data.max_drawdown}%</span>
                </div>
            </div>
        `;
    } catch (e) { console.log('Risiko nicht verfügbar'); }
}

async function loadBenchmark() {
    try {
        const symbol = document.getElementById('benchmarkSymbol')?.value || 'SPY';
        const period = document.getElementById('benchmarkPeriod')?.value || '6month';
        const res = await fetch(`/api/benchmark?symbol=${symbol}&period=${period}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.error || !data.benchmark?.length) return;

        const ctx = document.getElementById('benchmarkChart')?.getContext('2d');
        if (!ctx) return;
        if (benchmarkChartInstance) benchmarkChartInstance.destroy();

        const datasets = [{
            label: data.benchmark_name,
            data: data.benchmark.map(d => d.return_pct),
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,0.08)',
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
        }];

        let labels = data.benchmark.map(d => d.date);
        if (data.portfolio?.length > 1) {
            datasets.push({
                label: 'Mein Portfolio',
                data: data.portfolio.map(d => d.return_pct),
                borderColor: '#22c55e',
                backgroundColor: 'rgba(34,197,94,0.08)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
            });
            // Use longer label set
            if (data.portfolio.length > labels.length) {
                labels = data.portfolio.map(d => d.date);
            }
        }

        benchmarkChartInstance = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#64748b', font: { family: 'Inter', size: 10 }, maxTicksLimit: 6 } },
                    y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b', font: { family: 'Inter', size: 10 }, callback: v => v.toFixed(1) + '%' } }
                },
                plugins: {
                    legend: { labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } } },
                    tooltip: { backgroundColor: '#1a2035', titleColor: '#f1f5f9', bodyColor: '#94a3b8', callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)}%` } }
                },
                interaction: { intersect: false, mode: 'index' }
            }
        });
    } catch (e) { console.log('Benchmark nicht verfügbar:', e); }
}

async function renderDividends() {
    try {
        const res = await fetch('/api/dividends');
        if (!res.ok) return;
        const data = await res.json();
        const container = document.getElementById('dividendContainer');

        if (!data.positions?.length) {
            container.innerHTML = '<div class="empty-state">Keine Dividenden-Daten</div>';
            return;
        }

        container.innerHTML = `
            <div class="dividend-summary">
                <div class="dividend-stat">
                    <span class="dividend-stat-label">Jährliche Einnahmen</span>
                    <span class="dividend-stat-value">${formatCurrency(data.total_annual_income)}</span>
                </div>
                <div class="dividend-stat">
                    <span class="dividend-stat-label">Portfolio-Rendite</span>
                    <span class="dividend-stat-value">${data.portfolio_yield}%</span>
                </div>
                <div class="dividend-stat">
                    <span class="dividend-stat-label">Yield on Cost</span>
                    <span class="dividend-stat-value">${data.portfolio_yield_on_cost}%</span>
                </div>
                <div class="dividend-stat">
                    <span class="dividend-stat-label">Zahler</span>
                    <span class="dividend-stat-value">${data.num_dividend_payers}</span>
                </div>
            </div>
            <div class="dividend-list">
                ${data.positions.slice(0, 8).map(p => `
                    <div class="dividend-item">
                        <span class="dividend-ticker">${p.ticker}</span>
                        <span class="dividend-yield">${p.yield_pct}%</span>
                        <span class="dividend-income">${formatCurrency(p.annual_income)}/J</span>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (e) { console.log('Dividenden nicht verfügbar'); }
}

async function renderCorrelation() {
    try {
        const res = await fetch('/api/correlation');
        if (!res.ok) return;
        const data = await res.json();
        const container = document.getElementById('correlationContainer');

        if (!data.matrix?.length || !data.tickers?.length) {
            container.innerHTML = '<div class="empty-state">Berechnung läuft... (benötigt Preisdaten)</div>';
            return;
        }

        const divColor = data.diversification_score >= 70 ? '#22c55e' : data.diversification_score >= 40 ? '#eab308' : '#ef4444';

        let html = `
            <div class="corr-score" style="color:${divColor}">
                Diversifikation: ${data.diversification_score}/100
                <span style="font-size:0.75rem;color:#64748b">(Ø Korrelation: ${data.avg_correlation})</span>
            </div>
            <div class="corr-table-wrapper">
            <table class="corr-table">
                <thead><tr><th></th>${data.tickers.map(t => `<th>${t}</th>`).join('')}</tr></thead>
                <tbody>
        `;

        for (let i = 0; i < data.tickers.length; i++) {
            html += `<tr><td class="corr-row-label">${data.tickers[i]}</td>`;
            for (let j = 0; j < data.tickers.length; j++) {
                const val = data.matrix[i][j];
                const bg = i === j ? 'transparent' : corrColor(val);
                html += `<td style="background:${bg}" title="${data.tickers[i]} / ${data.tickers[j]}: ${val.toFixed(2)}">${i === j ? '—' : val.toFixed(2)}</td>`;
            }
            html += '</tr>';
        }
        html += '</tbody></table></div>';
        container.innerHTML = html;
    } catch (e) { console.log('Korrelation nicht verfügbar'); }
}

function corrColor(val) {
    if (val > 0.7) return 'rgba(239,68,68,0.4)';
    if (val > 0.4) return 'rgba(239,68,68,0.2)';
    if (val > 0.1) return 'rgba(234,179,8,0.15)';
    if (val > -0.1) return 'rgba(255,255,255,0.03)';
    if (val > -0.4) return 'rgba(34,197,94,0.15)';
    return 'rgba(34,197,94,0.3)';
}

async function renderEarnings() {
    try {
        const res = await fetch('/api/earnings-calendar');
        if (!res.ok) return;
        const data = await res.json();
        const container = document.getElementById('earningsContainer');

        if (!data.length) {
            container.innerHTML = '<div class="empty-state">Keine Earnings-Termine</div>';
            return;
        }

        container.innerHTML = data.slice(0, 10).map(e => {
            const dateObj = new Date(e.date);
            const dateStr = dateObj.toLocaleDateString('de-DE', { day: '2-digit', month: 'short' });
            const isUpcoming = dateObj >= new Date();
            return `
                <div class="earnings-item ${isUpcoming ? 'upcoming' : 'past'}">
                    <span class="earnings-date">${dateStr}</span>
                    <span class="earnings-ticker">${e.ticker}</span>
                    ${e.eps_estimated != null ? `<span class="earnings-eps">EPS est: $${e.eps_estimated.toFixed(2)}</span>` : ''}
                </div>
            `;
        }).join('');
    } catch (e) { console.log('Earnings nicht verfügbar'); }
}

// ==================== Score History (#9) ====================
let scoreHistoryChartInstance = null;

async function loadScoreHistory(ticker) {
    try {
        const res = await fetch(`/api/stock/${ticker}/score-history?days=30`);
        if (!res.ok) return;
        const data = await res.json();

        const ctx = document.getElementById('scoreHistoryChart');
        if (!ctx) return;
        if (scoreHistoryChartInstance) scoreHistoryChartInstance.destroy();

        if (!data.length) {
            ctx.parentElement.innerHTML = '<div class="empty-state">Noch keine Score-Historie</div>';
            return;
        }

        const labels = data.map(d => {
            const dt = new Date(d.timestamp);
            return dt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
        });
        const scores = data.map(d => d.score);
        const colors = data.map(d => d.rating === 'buy' ? '#22c55e' : d.rating === 'sell' ? '#ef4444' : '#eab308');

        scoreHistoryChartInstance = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Score',
                    data: scores,
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139,92,246,0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                    pointBackgroundColor: colors,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#64748b', font: { family: 'Inter', size: 10 } } },
                    y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b', font: { family: 'Inter', size: 10 } } }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: { backgroundColor: '#1a2035', titleColor: '#f1f5f9', bodyColor: '#94a3b8', callbacks: { label: ctx => `Score: ${ctx.raw.toFixed(1)}` } }
                }
            }
        });
    } catch (e) { console.log('Score-History nicht verfügbar'); }
}

// ==================== Stock News (#7) ====================
async function loadStockNews(ticker) {
    try {
        const container = document.getElementById('stockNewsContainer');
        if (!container) return;

        const res = await fetch(`/api/stock/${ticker}/news?limit=5`);
        if (!res.ok) { container.innerHTML = '<div class="empty-state">News nicht verfügbar</div>'; return; }
        const data = await res.json();

        if (!data.length) {
            container.innerHTML = '<div class="empty-state">Keine aktuellen News</div>';
            return;
        }

        container.innerHTML = data.map(n => `
            <a href="${n.url}" target="_blank" rel="noopener" class="news-item">
                <div class="news-title">${n.title}</div>
                <div class="news-meta">
                    <span class="news-site">${n.site}</span>
                    <span class="news-date">${new Date(n.published_date).toLocaleDateString('de-DE')}</span>
                </div>
            </a>
        `).join('');
    } catch (e) {
        const container = document.getElementById('stockNewsContainer');
        if (container) container.innerHTML = '<div class="empty-state">News nicht verfügbar</div>';
    }
}

// ==================== D5: Portfolio Performance Chart ====================
let perfChartInstance = null;

async function loadPerformanceChart(days = 30, btn = null) {
    if (btn) {
        const parent = btn.parentElement;
        parent.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }

    try {
        const res = await fetch(`/api/portfolio/history?days=${days}`);
        if (!res.ok) return;
        const data = await res.json();

        if (!data || data.length < 2) {
            const card = document.getElementById('performanceChartCard');
            if (card) card.style.display = 'none';
            return;
        }

        const card = document.getElementById('performanceChartCard');
        if (card) card.style.display = '';

        const ctx = document.getElementById('performanceChart');
        if (!ctx) return;
        if (perfChartInstance) perfChartInstance.destroy();

        const labels = data.map(d => {
            const dt = new Date(d.date);
            return dt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
        });
        const values = data.map(d => d.total_value);

        const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 200);
        const isPositive = values[values.length - 1] >= values[0];
        if (isPositive) {
            gradient.addColorStop(0, 'rgba(34, 197, 94, 0.25)');
            gradient.addColorStop(1, 'rgba(34, 197, 94, 0)');
        } else {
            gradient.addColorStop(0, 'rgba(239, 68, 68, 0.25)');
            gradient.addColorStop(1, 'rgba(239, 68, 68, 0)');
        }

        perfChartInstance = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    data: values,
                    borderColor: isPositive ? '#22c55e' : '#ef4444',
                    borderWidth: 2,
                    fill: true,
                    backgroundColor: gradient,
                    tension: 0.3,
                    pointRadius: data.length > 30 ? 0 : 3,
                    pointHoverRadius: 5,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1a2035',
                        titleColor: '#f1f5f9',
                        bodyColor: '#94a3b8',
                        callbacks: { label: ctx => `${formatCurrency(ctx.raw)}` }
                    }
                },
                scales: {
                    x: { display: true, grid: { display: false }, ticks: { color: '#64748b', maxTicksLimit: 8, font: { size: 10 } } },
                    y: { display: true, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b', callback: v => formatCurrency(v), font: { size: 10 } } }
                },
                interaction: { intersect: false, mode: 'index' }
            }
        });
    } catch (e) {
        console.log('Performance-Chart nicht verfügbar:', e);
    }
}


// ==================== D4: Theme Toggle ====================
function toggleTheme() {
    const body = document.body;
    const isLight = body.classList.toggle('light-mode');
    localStorage.setItem('finanzbroTheme', isLight ? 'light' : 'dark');
    const btn = document.getElementById('themeToggle');
    if (btn) btn.textContent = isLight ? '☀️' : '🌙';
}

// Initialize theme from localStorage
(function initTheme() {
    const saved = localStorage.getItem('finanzbroTheme');
    if (saved === 'light') {
        document.body.classList.add('light-mode');
        const btn = document.getElementById('themeToggle');
        if (btn) btn.textContent = '☀️';
    }
})();

// ==================== DA4: FMP Usage Display ====================
let fmpUsageInterval = null;

async function pollFmpUsage() {
    try {
        const res = await fetch('/api/status');
        if (!res.ok) return;
        const data = await res.json();
        const usage = data.fmp_usage;
        if (!usage) return;

        const pct = Math.min(100, (usage.requests_today / usage.daily_limit) * 100);
        const color = pct > 80 ? '#ef4444' : pct > 50 ? '#eab308' : '#22c55e';

        // Update or create FMP usage indicator
        let el = document.getElementById('fmpUsage');
        if (!el) {
            el = document.createElement('div');
            el.id = 'fmpUsage';
            el.className = 'fmp-usage';
            const lastUpdate = document.getElementById('lastUpdate');
            if (lastUpdate && lastUpdate.parentNode) {
                lastUpdate.parentNode.insertBefore(el, lastUpdate.nextSibling);
            }
        }
        el.innerHTML = `📡 FMP: ${usage.requests_today}/${usage.daily_limit} `
            + `<span class="fmp-usage-bar"><span class="fmp-usage-fill" style="width:${pct}%;background:${color}"></span></span>`
            + (usage.rate_limited ? ' ⚠️' : '');
    } catch (e) {
        // Silently ignore
    }
}

// Poll FMP usage every 60 seconds
if (!fmpUsageInterval) {
    fmpUsageInterval = setInterval(pollFmpUsage, 60000);
    // Initial poll after 3 seconds (let app load first)
    setTimeout(pollFmpUsage, 3000);
}

// ==================== D3: Score Sparklines ====================
// Store score history in localStorage for sparkline rendering
function saveScoreHistory() {
    if (!portfolioData || !portfolioData.scores) return;
    const today = new Date().toISOString().split('T')[0];
    const historyKey = 'finanzbroScoreHistory';
    let history = {};
    try {
        history = JSON.parse(localStorage.getItem(historyKey) || '{}');
    } catch(e) { history = {}; }

    for (const score of portfolioData.scores) {
        if (!history[score.ticker]) history[score.ticker] = [];
        const entries = history[score.ticker];
        // Update today's entry or add new
        const existing = entries.findIndex(e => e.d === today);
        if (existing >= 0) {
            entries[existing].s = Math.round(score.total_score);
        } else {
            entries.push({ d: today, s: Math.round(score.total_score) });
        }
        // Keep max 30 days
        if (entries.length > 30) history[score.ticker] = entries.slice(-30);
    }
    localStorage.setItem(historyKey, JSON.stringify(history));
}

function getScoreHistory(ticker) {
    try {
        const history = JSON.parse(localStorage.getItem('finanzbroScoreHistory') || '{}');
        return history[ticker] || [];
    } catch(e) { return []; }
}

function generateSparklineSVG(dataPoints, width = 50, height = 16) {
    if (!dataPoints || dataPoints.length < 2) return '';
    const values = dataPoints.map(p => p.s);
    const min = Math.min(...values) - 5;
    const max = Math.max(...values) + 5;
    const range = max - min || 1;

    const points = values.map((v, i) => {
        const x = (i / (values.length - 1)) * width;
        const y = height - ((v - min) / range) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    const last = values[values.length - 1];
    const first = values[0];
    const color = last > first + 2 ? '#22c55e' : last < first - 2 ? '#ef4444' : '#94a3b8';

    return `<svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
        <polyline fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" points="${points}"/>
    </svg>`;
}

function renderSparklineForTicker(ticker) {
    const history = getScoreHistory(ticker);
    if (history.length < 2) return '';
    const svg = generateSparklineSVG(history);
    const change = history[history.length - 1].s - history[0].s;
    const cls = change > 2 ? 'sparkline-up' : change < -2 ? 'sparkline-down' : 'sparkline-flat';
    const sign = change >= 0 ? '+' : '';
    return `<div class="sparkline-cell">${svg}<span class="sparkline-change ${cls}">${sign}${change}</span></div>`;
}

// Save score history on each data load
const _origRenderDashboard = renderDashboard;
renderDashboard = function() {
    _origRenderDashboard();
    saveScoreHistory();
};


// ==================== AI Trade Advisor ====================
let _advisorAction = 'buy';

function setAdvisorAction(action, btn) {
    _advisorAction = action;
    document.querySelectorAll('.advisor-action-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
}

async function submitAdvisorQuery() {
    const ticker = document.getElementById('advisorTicker')?.value?.trim().toUpperCase();
    if (!ticker) {
        alert('Bitte gib einen Ticker ein (z.B. NVDA, AAPL)');
        return;
    }

    const amount = document.getElementById('advisorAmount')?.value || null;
    const context = document.getElementById('advisorContext')?.value || null;

    // Loading state
    const btn = document.getElementById('advisorSubmitBtn');
    const btnText = btn.querySelector('.advisor-btn-text');
    const btnLoad = btn.querySelector('.advisor-btn-loading');
    btn.disabled = true;
    btnText.style.display = 'none';
    btnLoad.style.display = 'inline';

    const resultDiv = document.getElementById('advisorResult');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = `
        <div class="advisor-loading">
            <div class="advisor-loading-spinner"></div>
            <p>🧠 AI analysiert <strong>${ticker}</strong>...</p>
            <p class="advisor-loading-sub">Portfolio-Kontext, Score-Berechnung, Google Search Research</p>
        </div>
    `;

    try {
        const resp = await fetch('/api/advisor/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker,
                action: _advisorAction,
                amount_eur: amount ? parseFloat(amount) : null,
                extra_context: context || null,
            }),
        });
        const data = await resp.json();
        renderAdvisorResult(data);
    } catch (e) {
        resultDiv.innerHTML = `<div class="advisor-error">❌ Fehler: ${e.message}</div>`;
    } finally {
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnLoad.style.display = 'none';
    }
}

function renderAdvisorResult(data) {
    const resultDiv = document.getElementById('advisorResult');
    if (data.error) {
        resultDiv.innerHTML = `<div class="advisor-error">⚠️ ${data.error}</div>`;
        return;
    }

    const rec = data.recommendation || 'hold';
    const recMap = {
        buy: { label: 'KAUFEN', cls: 'rec-buy', icon: '🟢' },
        hold: { label: 'HALTEN', cls: 'rec-hold', icon: '🟡' },
        reduce: { label: 'REDUZIEREN', cls: 'rec-reduce', icon: '🟠' },
        avoid: { label: 'VERMEIDEN', cls: 'rec-avoid', icon: '🔴' },
    };
    const r = recMap[rec] || recMap.hold;
    const conf = data.confidence || 0;

    const actionDE = { buy: 'Kauf', sell: 'Verkauf', increase: 'Aufstocken' };
    const scoreInfo = data.score || {};
    const ticker = data.ticker || '';

    let scoreHtml = '';
    if (scoreInfo.total_score != null) {
        const sRating = (scoreInfo.rating || 'hold').toUpperCase();
        const sColor = sRating === 'BUY' ? 'var(--green)' : sRating === 'SELL' ? 'var(--red)' : 'var(--yellow)';
        scoreHtml = `
            <div class="advisor-score-card">
                <div class="advisor-score-value" style="color:${sColor}">${scoreInfo.total_score.toFixed(0)}<span>/100</span></div>
                <div class="advisor-score-rating" style="color:${sColor}">${sRating}</div>
                <div class="advisor-score-conf">Confidence: ${(scoreInfo.confidence * 100).toFixed(0)}%</div>
                ${scoreInfo.in_portfolio ? `<div class="advisor-score-meta">Im Portfolio: ${scoreInfo.current_weight}% | P&L: ${scoreInfo.current_pnl_pct > 0 ? '+' : ''}${scoreInfo.current_pnl_pct?.toFixed(1)}%</div>` : '<div class="advisor-score-meta">Nicht im Portfolio</div>'}
            </div>
        `;
    }

    let risksHtml = '';
    if (data.risks && data.risks.length > 0) {
        risksHtml = `<div class="advisor-section">
            <h4>⚠️ Risiken</h4>
            <ul class="advisor-risks">${data.risks.map(r => `<li>${r}</li>`).join('')}</ul>
        </div>`;
    }

    let externalHtml = '';
    if (data.external_analysis) {
        externalHtml = `<div class="advisor-section">
            <h4>📎 Externe Quellen</h4>
            <p>${data.external_analysis}</p>
        </div>`;
    }

    resultDiv.innerHTML = `
        <div class="advisor-result-header">
            <div>
                <h3>${ticker} — ${actionDE[data.action] || data.action}</h3>
                ${data.amount_eur ? `<span class="advisor-amount">${data.amount_eur.toLocaleString('de-DE')} EUR</span>` : ''}
            </div>
            <div class="advisor-rec-badge ${r.cls}">
                <span class="advisor-rec-icon">${r.icon}</span>
                <span class="advisor-rec-label">${r.label}</span>
                <span class="advisor-rec-conf">${conf}%</span>
            </div>
        </div>

        <div class="advisor-summary">${data.summary || ''}</div>

        <div class="advisor-grid">
            ${scoreHtml}

            <div class="advisor-section advisor-bull">
                <h4>🐂 Bull Case</h4>
                <p>${data.bull_case || '–'}</p>
            </div>

            <div class="advisor-section advisor-bear">
                <h4>🐻 Bear Case</h4>
                <p>${data.bear_case || '–'}</p>
            </div>
        </div>

        <div class="advisor-detail-grid">
            <div class="advisor-section">
                <h4>📊 Portfolio-Fit</h4>
                <p>${data.portfolio_fit || '–'}</p>
            </div>

            <div class="advisor-section">
                <h4>📐 Sizing</h4>
                <p>${data.sizing_advice || '–'}</p>
            </div>

            <div class="advisor-section">
                <h4>⏱️ Timing</h4>
                <p>${data.timing || '–'}</p>
            </div>

            ${risksHtml}
            ${externalHtml}
        </div>
    `;
}

// Ticker Autocomplete
(function() {
    const input = document.getElementById('advisorTicker');
    const dropdown = document.getElementById('advisorAutocomplete');
    if (!input || !dropdown) return;

    input.addEventListener('input', () => {
        const val = input.value.trim().toUpperCase();
        dropdown.innerHTML = '';
        if (!val || !portfolioData?.stocks) { dropdown.style.display = 'none'; return; }

        const matches = portfolioData.stocks
            .filter(s => s.position.ticker !== 'CASH')
            .filter(s => s.position.ticker.includes(val) || (s.position.name || '').toUpperCase().includes(val))
            .slice(0, 6);

        if (matches.length === 0) { dropdown.style.display = 'none'; return; }

        matches.forEach(s => {
            const div = document.createElement('div');
            div.className = 'advisor-ac-item';
            div.textContent = `${s.position.ticker} — ${s.position.name || ''}`;
            div.onclick = () => { input.value = s.position.ticker; dropdown.style.display = 'none'; };
            dropdown.appendChild(div);
        });
        dropdown.style.display = 'block';
    });

    input.addEventListener('blur', () => setTimeout(() => dropdown.style.display = 'none', 200));
})();


// ==================== AI Advisor Chat ====================
let _chatHistory = [];

function switchAdvisorMode(mode) {
    document.querySelectorAll('.advisor-mode-btn').forEach(b => b.classList.remove('active'));
    const analyseDiv = document.getElementById('advisorAnalyseMode');
    const chatDiv = document.getElementById('advisorChatMode');
    if (mode === 'chat') {
        document.getElementById('advisorModeChat').classList.add('active');
        analyseDiv.style.display = 'none';
        chatDiv.style.display = 'block';
        setTimeout(() => document.getElementById('advisorChatInput')?.focus(), 100);
    } else {
        document.getElementById('advisorModeAnalyse').classList.add('active');
        analyseDiv.style.display = 'block';
        chatDiv.style.display = 'none';
    }
}

function sendChatSuggestion(btn) {
    const text = btn.textContent.trim();
    document.getElementById('advisorChatInput').value = text;
    sendAdvisorChat();
}

function handleChatKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendAdvisorChat();
    }
}

function clearAdvisorChat() {
    _chatHistory = [];
    const messagesDiv = document.getElementById('advisorChatMessages');
    messagesDiv.innerHTML = `
        <div class="advisor-chat-welcome">
            <p>👋 Hallo! Ich bin dein Portfolio-Berater.</p>
            <p>Du kannst mich alles zu deinem Portfolio fragen. Beispiele:</p>
            <div class="advisor-chat-suggestions">
                <button class="advisor-chat-suggestion" onclick="sendChatSuggestion(this)">Wie diversifiziert ist mein Portfolio?</button>
                <button class="advisor-chat-suggestion" onclick="sendChatSuggestion(this)">Was passiert wenn der USD 10% fällt?</button>
                <button class="advisor-chat-suggestion" onclick="sendChatSuggestion(this)">Welche Aktie hat das beste Chance/Risiko-Verhältnis?</button>
                <button class="advisor-chat-suggestion" onclick="sendChatSuggestion(this)">Wie hoch ist mein Klumpenrisiko im Tech-Sektor?</button>
            </div>
        </div>`;
}

async function sendAdvisorChat() {
    const input = document.getElementById('advisorChatInput');
    const message = input.value.trim();
    if (!message) return;

    const btn = document.getElementById('advisorChatSendBtn');
    const btnText = btn.querySelector('.chat-send-text');
    const btnLoad = btn.querySelector('.chat-send-loading');
    const messagesDiv = document.getElementById('advisorChatMessages');

    // Welcome entfernen beim ersten Senden
    const welcome = messagesDiv.querySelector('.advisor-chat-welcome');
    if (welcome) welcome.remove();

    // User-Nachricht anzeigen
    messagesDiv.innerHTML += `
        <div class="chat-msg chat-msg-user">
            <div class="chat-msg-content">${_escapeHtml(message)}</div>
        </div>`;

    input.value = '';
    input.disabled = true;
    btn.disabled = true;
    btnText.style.display = 'none';
    btnLoad.style.display = 'inline';

    // Typing-Indikator
    messagesDiv.innerHTML += `
        <div class="chat-msg chat-msg-ai chat-msg-typing" id="chatTyping">
            <div class="chat-msg-content">
                <div class="chat-typing-dots"><span></span><span></span><span></span></div>
            </div>
        </div>`;
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    try {
        const resp = await fetch('/api/advisor/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ message, history: _chatHistory }),
        });
        const data = await resp.json();

        // Typing-Indikator entfernen
        document.getElementById('chatTyping')?.remove();

        if (data.error) {
            messagesDiv.innerHTML += `
                <div class="chat-msg chat-msg-ai">
                    <div class="chat-msg-content chat-msg-error">⚠️ ${data.error}</div>
                </div>`;
        } else {
            _chatHistory = data.history || [];
            const rendered = _renderMarkdown(data.response || '');
            messagesDiv.innerHTML += `
                <div class="chat-msg chat-msg-ai">
                    <div class="chat-msg-content">${rendered}</div>
                </div>`;
        }
    } catch (e) {
        document.getElementById('chatTyping')?.remove();
        messagesDiv.innerHTML += `
            <div class="chat-msg chat-msg-ai">
                <div class="chat-msg-content chat-msg-error">❌ ${e.message}</div>
            </div>`;
    }

    input.disabled = false;
    btn.disabled = false;
    btnText.style.display = 'inline';
    btnLoad.style.display = 'none';
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    input.focus();
}

function _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function _renderMarkdown(text) {
    // Einfaches Markdown-Rendering
    let html = _escapeHtml(text);
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Headers
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');
    // Unordered lists
    html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    // Line breaks
    html = html.replace(/\n/g, '<br>');
    // Clean up duplicate <ul> tags
    html = html.replace(/<\/ul><br><ul>/g, '');
    return html;
}

// ==================== Portfolio Historie (Stacked Area Chart) ====================
let historieChartInstance = null;
let historieCurrentPeriod = '6month';

const HISTORIE_COLORS = [
    '#3b82f6', '#8b5cf6', '#06b6d4', '#22c55e', '#eab308',
    '#ef4444', '#f97316', '#ec4899', '#14b8a6', '#6366f1',
    '#a855f7', '#0ea5e9', '#84cc16', '#f59e0b', '#e11d48',
    '#10b981', '#7c3aed', '#0891b2', '#65a30d', '#dc2626',
];

// ==================== Performance KPIs ====================
let _performanceData = null;

function formatEur(val) {
    if (val === null || val === undefined) return '—';
    return val.toLocaleString('de-DE', { style: 'currency', currency: 'EUR', minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

async function loadPerformanceKPIs() {
    if (_performanceData) {
        renderPerformanceKPIs(_performanceData);
        return;
    }
    try {
        const res = await fetch('/api/performance');
        if (!res.ok) return;
        _performanceData = await res.json();
        if (_performanceData.error) { _performanceData = null; return; }
        renderPerformanceKPIs(_performanceData);
    } catch (e) {
        console.error('Performance KPIs laden fehlgeschlagen:', e);
    }
}

function renderPerformanceKPIs(data) {
    const { kpis, holdingsActive, holdingsSold, activeHoldings, soldHoldings } = data;
    const container = document.getElementById('performanceKpis');
    if (!container) return;

    // KPI Values
    document.getElementById('kpiValuation').textContent = formatEur(kpis.valuation);

    const unrealGain = kpis.unrealizedGains?.gainGross || 0;
    const unrealPct = kpis.unrealizedGains?.returnGross || 0;
    const unrealEl = document.getElementById('kpiUnrealized');
    unrealEl.textContent = (unrealGain >= 0 ? '+' : '') + formatEur(unrealGain);
    unrealEl.style.color = unrealGain >= 0 ? '#22c55e' : '#ef4444';
    document.getElementById('kpiUnrealizedPct').textContent = `(${unrealPct >= 0 ? '+' : ''}${unrealPct.toFixed(1)}%)`;

    const realGain = kpis.realizedGains?.gainGross || 0;
    const realEl = document.getElementById('kpiRealized');
    realEl.textContent = (realGain >= 0 ? '+' : '') + formatEur(realGain);
    realEl.style.color = realGain >= 0 ? '#22c55e' : '#ef4444';

    document.getElementById('kpiDividends').textContent = formatEur(kpis.dividends?.gainGross || 0);
    document.getElementById('kpiTaxes').textContent = formatEur(kpis.taxes);
    document.getElementById('kpiFees').textContent = formatEur(kpis.fees);

    // Interval
    const intervalEl = document.getElementById('kpiInterval');
    if (kpis.interval) {
        intervalEl.textContent = `Zeitraum: ${kpis.interval.start} → ${kpis.interval.end} | ${activeHoldings} aktiv, ${soldHoldings} verkauft`;
    }

    container.style.display = 'block';

    // Holdings table
    renderHoldingsTable(holdingsActive);
    document.getElementById('holdingsSection').style.display = 'block';
}

let _currentHoldingsSort = { column: 'currentValue', dir: 'desc' };
let _currentHoldingsFilter = 'active';

function filterHoldings(filter, btn) {
    if (!_performanceData) return;
    _currentHoldingsFilter = filter;
    if (btn) {
        btn.parentElement.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }
    const holdings = filter === 'active' ? _performanceData.holdingsActive
        : filter === 'sold' ? _performanceData.holdingsSold
        : _performanceData.holdings;
    renderHoldingsTable(holdings);
}

function sortHoldings(column) {
    if (_currentHoldingsSort.column === column) {
        _currentHoldingsSort.dir = _currentHoldingsSort.dir === 'asc' ? 'desc' : 'asc';
    } else {
        _currentHoldingsSort = { column, dir: 'desc' };
    }
    filterHoldings(_currentHoldingsFilter);
}

function renderHoldingsTable(holdings) {
    const wrap = document.getElementById('holdingsTableWrap');
    if (!wrap || !holdings) return;

    if (holdings.length === 0) {
        wrap.innerHTML = '<p style="color:#94a3b8;text-align:center;padding:1rem;">Keine Positionen gefunden</p>';
        return;
    }

    // Sort holdings
    const { column, dir } = _currentHoldingsSort;
    const mult = dir === 'asc' ? 1 : -1;
    const sorted = [...holdings].filter(h => h.type !== 'cash').sort((a, b) => {
        switch (column) {
            case 'name': return mult * (a.name || '').localeCompare(b.name || '');
            case 'shares': return mult * ((a.shares || 0) - (b.shares || 0));
            case 'purchaseValue': return mult * ((a.purchaseValue || 0) - (b.purchaseValue || 0));
            case 'currentValue': return mult * ((a.currentValue || 0) - (b.currentValue || 0));
            case 'gain': {
                const gA = a.isSold ? (a.realizedGainGross || 0) : (a.unrealizedGainGross || 0);
                const gB = b.isSold ? (b.realizedGainGross || 0) : (b.unrealizedGainGross || 0);
                return mult * (gA - gB);
            }
            case 'gainPct': {
                const pA = a.isSold ? (a.purchaseValue > 0 ? (a.realizedGainGross || 0) / a.purchaseValue * 100 : 0) : (a.unrealizedReturnGross || 0);
                const pB = b.isSold ? (b.purchaseValue > 0 ? (b.realizedGainGross || 0) / b.purchaseValue * 100 : 0) : (b.unrealizedReturnGross || 0);
                return mult * (pA - pB);
            }
            case 'dividends': return mult * ((a.dividendsGross || 0) - (b.dividendsGross || 0));
            case 'taxes': return mult * ((a.taxes || 0) - (b.taxes || 0));
            default: return 0;
        }
    });

    const arrow = (col) => {
        if (_currentHoldingsSort.column !== col) return '';
        return _currentHoldingsSort.dir === 'asc' ? ' ▲' : ' ▼';
    };
    const thClass = (col) => _currentHoldingsSort.column === col ? 'sortable sorted' : 'sortable';

    let html = `<table class="holdings-table">
        <thead><tr>
            <th></th>
            <th class="${thClass('name')}" onclick="sortHoldings('name')">Position${arrow('name')}</th>
            <th class="${thClass('shares')}" onclick="sortHoldings('shares')" style="text-align:right">Stk.${arrow('shares')}</th>
            <th class="${thClass('purchaseValue')}" onclick="sortHoldings('purchaseValue')" style="text-align:right">Kaufwert${arrow('purchaseValue')}</th>
            <th class="${thClass('currentValue')}" onclick="sortHoldings('currentValue')" style="text-align:right">Aktuell${arrow('currentValue')}</th>
            <th class="${thClass('gain')}" onclick="sortHoldings('gain')" style="text-align:right">Gewinn${arrow('gain')}</th>
            <th class="${thClass('dividends')}" onclick="sortHoldings('dividends')" style="text-align:right">Div.${arrow('dividends')}</th>
            <th class="${thClass('taxes')}" onclick="sortHoldings('taxes')" style="text-align:right">Steuern${arrow('taxes')}</th>
        </tr></thead><tbody>`;

    for (const h of sorted) {
        const gain = h.isSold ? h.realizedGainGross : h.unrealizedGainGross;
        const gainPct = h.isSold ? (h.purchaseValue > 0 ? (gain / h.purchaseValue * 100) : 0) : h.unrealizedReturnGross;
        const gainColor = gain >= 0 ? '#22c55e' : '#ef4444';
        const gainSign = gain >= 0 ? '+' : '';
        const soldBadge = h.isSold ? '<span style="color:#94a3b8;font-size:0.7rem;margin-left:4px">✗</span>' : '';

        html += `<tr${h.isSold ? ' style="opacity:0.6"' : ''}>
            <td><img src="${h.logo}" alt="" style="width:24px;height:24px;border-radius:4px;" onerror="this.style.display='none'"></td>
            <td><strong>${h.name || h.ticker}</strong>${soldBadge}<br><span style="color:#94a3b8;font-size:0.75rem">${h.ticker}</span></td>
            <td style="text-align:right">${h.shares > 0 ? h.shares.toFixed(h.shares < 10 ? 2 : 0) : '—'}</td>
            <td style="text-align:right">${formatEur(h.purchaseValue)}</td>
            <td style="text-align:right">${h.currentValue > 0 ? formatEur(h.currentValue) : '—'}</td>
            <td style="text-align:right;color:${gainColor}">${gainSign}${formatEur(gain)}<br><span style="font-size:0.75rem">${gainSign}${gainPct.toFixed(1)}%</span></td>
            <td style="text-align:right">${h.dividendsGross > 0 ? formatEur(h.dividendsGross) : '—'}</td>
            <td style="text-align:right">${h.taxes > 0 ? formatEur(h.taxes) : '—'}</td>
        </tr>`;
    }

    html += '</tbody></table>';
    wrap.innerHTML = html;
}

async function loadHistorie(period, btn) {
    historieCurrentPeriod = period;

    // Update period buttons
    if (btn) {
        const parent = btn.parentElement;
        parent.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }

    // Show loading
    const loadingEl = document.getElementById('historieLoading');
    const canvasEl = document.getElementById('historieChart');
    if (loadingEl) loadingEl.style.display = 'flex';
    if (canvasEl) canvasEl.style.opacity = '0.3';

    try {
        const res = await fetch(`/api/portfolio/history-detail?period=${period}`);
        if (!res.ok) {
            console.error('Historie laden fehlgeschlagen:', res.status);
            if (loadingEl) loadingEl.style.display = 'none';
            if (canvasEl) canvasEl.style.opacity = '1';
            return;
        }
        const data = await res.json();
        if (data.error || !data.dates || data.dates.length === 0) {
            if (loadingEl) loadingEl.style.display = 'none';
            if (canvasEl) canvasEl.style.opacity = '1';
            const summaryEl = document.getElementById('historieSummary');
            if (summaryEl) summaryEl.innerHTML = '<p style="color:#94a3b8;text-align:center;padding:2rem;">Keine historischen Daten verfügbar. Bitte zuerst ein Parqet-Update durchführen.</p>';
            return;
        }
        renderHistorieChart(data);
    } catch (e) {
        console.error('Historie laden fehlgeschlagen:', e);
    } finally {
        if (loadingEl) loadingEl.style.display = 'none';
        if (canvasEl) canvasEl.style.opacity = '1';
    }
}

// Ticker filter state
let _historieFilteredTickers = new Set(); // empty = show all
let _lastHistorieData = null;

function renderHistorieChart(data) {
    const ctx = document.getElementById('historieChart');
    if (!ctx) return;
    if (historieChartInstance) historieChartInstance.destroy();
    _lastHistorieData = data;

    const { dates, stocks, total, total_cost, pnl } = data;
    const tickers = Object.keys(stocks);

    // Build datasets: one stacked area per stock (filtered)
    const datasets = [];
    const showAll = _historieFilteredTickers.size === 0;
    tickers.forEach((ticker, i) => {
        const color = HISTORIE_COLORS[i % HISTORIE_COLORS.length];
        const stockData = stocks[ticker];
        const hidden = !showAll && !_historieFilteredTickers.has(ticker);
        datasets.push({
            label: `${ticker} (${stockData.name})`,
            data: stockData.values,
            backgroundColor: color + '40',
            borderColor: color,
            borderWidth: 1,
            fill: true,
            stack: 'portfolio',
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 3,
            order: tickers.length - i,
            hidden: hidden,
        });
    });

    // Total line (not stacked, on top)
    datasets.push({
        label: 'Gesamtwert',
        data: total,
        borderColor: '#f1f5f9',
        borderWidth: 2.5,
        fill: false,
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 4,
        order: 0,
        borderDash: [],
    });

    // Cost basis line (dashed)
    if (total_cost && total_cost.some(v => v > 0)) {
        datasets.push({
            label: 'Einstandskosten',
            data: total_cost,
            borderColor: '#94a3b8',
            borderWidth: 1.5,
            borderDash: [6, 4],
            fill: false,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 3,
            order: -1,
        });
    }

    // P&L area (green when profit, red when loss)
    if (pnl && pnl.length > 0) {
        datasets.push({
            label: 'Gewinn',
            data: pnl.map(v => v >= 0 ? v : null),
            backgroundColor: 'rgba(34, 197, 94, 0.18)',
            borderColor: 'rgba(34, 197, 94, 0.7)',
            borderWidth: 1.5,
            fill: 'origin',
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 0,
            order: -2,
            yAxisID: 'pnl',
            spanGaps: true,
        });

        datasets.push({
            label: 'Verlust',
            data: pnl.map(v => v < 0 ? v : null),
            backgroundColor: 'rgba(239, 68, 68, 0.18)',
            borderColor: 'rgba(239, 68, 68, 0.7)',
            borderWidth: 1.5,
            fill: 'origin',
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 0,
            order: -3,
            yAxisID: 'pnl',
            spanGaps: true,
        });
    }

    // Sparse labels (show ~12 dates on x-axis)
    const labelInterval = Math.max(1, Math.floor(dates.length / 12));

    historieChartInstance = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: { labels: dates, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        color: '#64748b',
                        font: { family: 'Inter', size: 10 },
                        maxTicksLimit: 12,
                        callback: function(value, index) {
                            if (index % labelInterval === 0) {
                                const d = dates[index];
                                if (!d) return '';
                                const parts = d.split('-');
                                return `${parts[2]}.${parts[1]}`;
                            }
                            return '';
                        }
                    }
                },
                y: {
                    stacked: true,
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: {
                        color: '#64748b',
                        font: { family: 'Inter', size: 10 },
                        callback: v => formatCurrency(v),
                    }
                },
                pnl: {
                    display: true,
                    position: 'right',
                    beginAtZero: true,
                    grid: { display: false },
                    ticks: {
                        color: '#64748b',
                        font: { family: 'Inter', size: 10 },
                        callback: v => {
                            if (v === 0) return '0';
                            return (v >= 0 ? '+' : '') + formatCurrency(v);
                        },
                        maxTicksLimit: 6,
                    },
                    title: {
                        display: true,
                        text: 'P&L',
                        color: '#94a3b8',
                        font: { size: 10 },
                    },
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1a2035',
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    cornerRadius: 8,
                    padding: 12,
                    callbacks: {
                        title: (items) => {
                            if (!items.length) return '';
                            const d = items[0].label;
                            const parts = d.split('-');
                            return `${parts[2]}.${parts[1]}.${parts[0]}`;
                        },
                        label: (ctx) => {
                            const val = ctx.raw;
                            if (val == null || val === 0) return null;
                            return `${ctx.dataset.label}: ${formatCurrency(val)}`;
                        },
                        afterBody: (items) => {
                            if (!items.length) return '';
                            const idx = items[0].dataIndex;
                            const totalVal = total[idx] || 0;
                            const costVal = total_cost ? (total_cost[idx] || 0) : 0;
                            const pnl = totalVal - costVal;
                            const pnlPct = costVal > 0 ? (pnl / costVal * 100) : 0;
                            const sign = pnl >= 0 ? '+' : '';
                            return `\n━━━━━━━━━━━━━━━━\nGesamt: ${formatCurrency(totalVal)}\nEinstand: ${formatCurrency(costVal)}\nP&L: ${sign}${formatCurrency(pnl)} (${sign}${pnlPct.toFixed(1)}%)`;
                        }
                    }
                }
            }
        }
    });

    // Render legend
    _renderHistorieLegend(tickers, stocks, total);

    // Render summary (use Performance API data if available)
    _renderHistorieSummary(dates, total, total_cost);

    // Render ticker filter
    _renderTickerFilter(tickers, stocks);
}

function _renderHistorieLegend(tickers, stocks, total) {
    const container = document.getElementById('historieLegend');
    if (!container) return;

    const lastTotal = total[total.length - 1] || 1;

    container.innerHTML = tickers.map((ticker, i) => {
        const color = HISTORIE_COLORS[i % HISTORIE_COLORS.length];
        const stockData = stocks[ticker];
        const lastVal = stockData.values[stockData.values.length - 1] || 0;
        const pct = lastTotal > 0 ? (lastVal / lastTotal * 100) : 0;
        return `
            <div class="historie-legend-item">
                <span class="historie-legend-dot" style="background:${color}"></span>
                <span class="historie-legend-ticker">${ticker}</span>
                <span class="historie-legend-value">${formatCurrency(lastVal)} (${pct.toFixed(1)}%)</span>
            </div>
        `;
    }).join('');
}

function _renderHistorieSummary(dates, total, totalCost) {
    const container = document.getElementById('historieSummary');
    if (!container || !dates.length) return;

    const firstVal = total[0] || 0;
    const lastVal = total[total.length - 1] || 0;
    const change = lastVal - firstVal;
    const changePct = firstVal > 0 ? (change / firstVal * 100) : 0;
    const sign = change >= 0 ? '+' : '';
    const changeClass = change >= 0 ? 'positive' : 'negative';

    // Use Performance API for accurate P&L (if available)
    let totalPnl, totalPnlPct;
    if (_performanceData && _performanceData.kpis) {
        const kpis = _performanceData.kpis;
        const unrealized = kpis.unrealizedGains?.gainGross || 0;
        const realized = kpis.realizedGains?.gainGross || 0;
        totalPnl = unrealized + realized;
        // Invested = valuation - unrealized gains
        const invested = (kpis.valuation || lastVal) - unrealized;
        totalPnlPct = invested > 0 ? (totalPnl / invested * 100) : 0;
    } else {
        const costLast = totalCost ? (totalCost[totalCost.length - 1] || 0) : 0;
        totalPnl = lastVal - costLast;
        totalPnlPct = costLast > 0 ? (totalPnl / costLast * 100) : 0;
    }

    const pnlSign = totalPnl >= 0 ? '+' : '';
    const pnlClass = totalPnl >= 0 ? 'positive' : 'negative';

    const startDate = dates[0].split('-');
    const endDate = dates[dates.length - 1].split('-');

    container.innerHTML = `
        <div class="historie-summary-row">
            <div class="historie-summary-item">
                <span class="historie-summary-label">Zeitraum</span>
                <span class="historie-summary-value">${startDate[2]}.${startDate[1]}.${startDate[0]} — ${endDate[2]}.${endDate[1]}.${endDate[0]}</span>
            </div>
            <div class="historie-summary-item">
                <span class="historie-summary-label">Wertentwicklung (Zeitraum)</span>
                <span class="historie-summary-value ${changeClass}">${sign}${formatCurrency(change)} (${sign}${changePct.toFixed(1)}%)</span>
            </div>
            <div class="historie-summary-item">
                <span class="historie-summary-label">Aktueller Wert</span>
                <span class="historie-summary-value">${formatCurrency(lastVal)}</span>
            </div>
            <div class="historie-summary-item">
                <span class="historie-summary-label">Gesamt P&L${_performanceData ? ' (Parqet)' : ''}</span>
                <span class="historie-summary-value ${pnlClass}">${pnlSign}${formatCurrency(totalPnl)} (${pnlSign}${totalPnlPct.toFixed(1)}%)</span>
            </div>
        </div>
    `;
}

function _renderTickerFilter(tickers, stocks) {
    // Insert filter into historie-controls if not already there
    let filterWrap = document.getElementById('historieTickerFilter');
    if (!filterWrap) {
        const controls = document.querySelector('.historie-controls');
        if (!controls) return;
        filterWrap = document.createElement('div');
        filterWrap.id = 'historieTickerFilter';
        filterWrap.className = 'ticker-filter';
        controls.parentElement.appendChild(filterWrap);
    }

    const showAll = _historieFilteredTickers.size === 0;
    let html = `<button class="ticker-chip ${showAll ? 'active' : ''}" onclick="toggleTickerFilter('__ALL__', this)">Alle</button>`;
    tickers.forEach((ticker, i) => {
        const color = HISTORIE_COLORS[i % HISTORIE_COLORS.length];
        const active = showAll || _historieFilteredTickers.has(ticker);
        html += `<button class="ticker-chip ${active ? 'active' : ''}" style="--chip-color:${color}" onclick="toggleTickerFilter('${ticker}', this)">${ticker}</button>`;
    });
    filterWrap.innerHTML = html;
}

function toggleTickerFilter(ticker, btn) {
    if (ticker === '__ALL__') {
        _historieFilteredTickers.clear();
    } else {
        if (_historieFilteredTickers.has(ticker)) {
            _historieFilteredTickers.delete(ticker);
            // If none selected, revert to show all
            if (_historieFilteredTickers.size === 0) {
                // already empty = show all
            }
        } else {
            _historieFilteredTickers.add(ticker);
        }
    }
    // Re-render chart with current data
    if (_lastHistorieData) {
        renderHistorieChart(_lastHistorieData);
    }
}
