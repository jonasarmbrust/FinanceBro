/**
 * FinanceBro i18n — Bilingual Translation System (DE + EN)
 * Usage: t('key') returns the string for the current language
 * Language is stored in localStorage and defaults to browser language
 */

let currentLang = localStorage.getItem('financebro-lang') ||
    (navigator.language.startsWith('de') ? 'de' : 'en');

const i18n = {
    de: {
        // Header
        portfolioValue: 'Portfoliowert',
        today: 'Heute:',
        toggleTheme: 'Farbschema wechseln',
        toggleCurrency: 'Währung wechseln',
        actions: 'Aktionen',
        updateParqet: 'Update Parqet',
        telegramReport: 'Telegram Report',
        fullAnalysis: 'Komplette Analyse',
        demoMode: 'Demo-Modus',
        demoBanner: '🎭 Demo-Modus — Fiktive Daten zu Präsentationszwecken',
        uploadCsv: 'CSV Import',

        // Navigation
        overview: 'Übersicht',
        analysis: 'Analyse',
        history: 'Historie',
        rebalancing: 'Rebalancing',
        techPicks: 'Tech Picks',
        aiAdvisor: 'AI Advisor',

        // Stats
        positions: 'Positionen',

        // Movers
        dailyWinners: '🟢 Tagesgewinner',
        dailyLosers: '🔴 Tagesverlierer',

        // Heatmap
        portfolioHeatmap: '🗺️ Portfolio-Heatmap',

        // Table
        portfolioPositions: 'Portfolio-Positionen',
        sortBy: 'Sortieren:',
        name: 'Name',
        price: 'Kurs',
        costBasis: 'Einstand',
        todayShort: 'Heute',
        shares: 'Stk.',
        value: 'Wert',
        score: 'Score',
        rating: 'Rating',
        details: 'Details',
        all: 'Alle',

        // Analysis Tab
        sectorAllocation: '🏗️ Sektor-Allokation',
        riskProfile: '🛡️ Risiko-Profil',
        performanceBenchmark: '📈 Performance vs. Benchmark',
        dividends: '💰 Dividenden',
        correlationMatrix: '🔗 Korrelationsmatrix',
        earningsCalendar: '📅 Earnings-Kalender',
        months3: '3 Monate',
        months6: '6 Monate',
        year1: '1 Jahr',

        // History Tab
        totalValue: '📊 Gesamtwert',
        unrealized: '📈 Unrealisiert',
        realized: '💰 Realisiert',
        dividendsKpi: '🪙 Dividenden',
        taxes: '🏛️ Steuern',
        fees: '💳 Gebühren',
        allPositions: '📋 Alle Positionen',
        active: 'Aktiv',
        sold: 'Verkauft',

        // Rebalancing Tab
        rebalancingRecommendations: '⚖️ Rebalancing-Empfehlungen',
        calculating: 'Wird berechnet...',

        // Tech Picks Tab
        dailyTechPicks: '🚀 Tägliche Tech-Empfehlungen',
        techPicksSubtitle: 'Aktien aus dem Technologie-Sektor mit hohem Potenzial',

        // AI Advisor Tab
        tradeAnalysis: 'Trade-Analyse',
        chat: 'Chat',
        aiTradeAdvisor: '🧠 AI Trade Advisor',
        advisorSubtitle: 'Evaluiere Kauf- und Verkaufsentscheidungen mit KI-gestützter Portfolio-Analyse',
        ticker: 'Ticker',
        tickerPlaceholder: 'z.B. NVDA',
        action: 'Aktion',
        buy: 'Kauf',
        increase: 'Aufstocken',
        sell: 'Verkauf',
        amountEur: 'Betrag (EUR)',
        amountPlaceholder: 'z.B. 2000',
        externalSources: '📎 Externe Quellen',
        optional: '(optional)',
        contextPlaceholder: 'Analystenkommentare, Artikel-Auszüge oder eigene Notizen hier einfügen...',
        startAnalysis: 'Analyse starten',
        aiAnalyzing: '⏳ AI analysiert...',

        // Chat
        portfolioChat: '💬 Portfolio-Chat',
        newChat: '🗑️ Neu',
        chatSubtitle: 'Stelle Fragen, diskutiere Hypothesen, analysiere Szenarien — mit vollem Portfolio-Kontext',
        chatWelcome1: '👋 Hallo! Ich bin dein Portfolio-Berater.',
        chatWelcome2: 'Du kannst mich alles zu deinem Portfolio fragen. Beispiele:',
        chatSuggestion1: 'Wie diversifiziert ist mein Portfolio?',
        chatSuggestion2: 'Was passiert wenn der USD 10% fällt?',
        chatSuggestion3: 'Welche Aktie hat das beste Chance/Risiko-Verhältnis?',
        chatSuggestion4: 'Wie hoch ist mein Klumpenrisiko im Tech-Sektor?',
        chatInputPlaceholder: 'Deine Frage...',
        send: 'Senden',

        // Stock Panel
        stockOverview: 'Übersicht',
        fundamentals: 'Fundamentals',
        technical: 'Technisch',
        news: 'News',

        // Mobile Nav
        rebalance: 'Rebalance',
        picks: 'Picks',
        ai: 'AI',

        // Dynamic content (app.js)
        priority: 'Priorität',
        quality: 'Qualität',
        scoreBreakdown: 'Score-Aufschlüsselung',
        insiderBuys: 'Insider Käufe',
        insiderSells: 'Insider Verkäufe',
        insiderBuysPct: 'Käufe',
        annualPerShare: 'Jährlich/Aktie',
        overbought: '⚠️ Überkauft',
        oversold: '⚠️ Überverkauft',
        normal: '✅ Normal',
        noTechData: 'Keine technischen Daten verfügbar',
        noFundData: 'Keine Fundamentaldaten verfügbar',
        switchToReal: 'Zurück zu echten Portfolio-Daten',
        fullAnalysisRunning: '🔬 Komplette Analyse läuft...',
        volatilityPa: 'Volatilität (p.a.)',
        varDaily: 'VaR 95% (täglich)',
        annualIncome: 'Jährliche Einnahmen',
        calcRunning: 'Berechnung läuft... (benötigt Preisdaten)',
        newsUnavailable: 'News nicht verfügbar',
        noHistoryData: 'Keine historischen Daten verfügbar. Bitte zuerst ein Parqet-Update durchführen.',
        sellRatingHint: 'mit Sell-Rating – Rebalancing prüfen?',
        position: 'Position',
        positionPlural: 'Positionen',

        // CSV Upload
        csvUploadTitle: 'CSV Portfolio Import',
        csvUploadDesc: 'Importiere dein Portfolio aus einer CSV-Datei',
        csvSelectFile: 'Datei auswählen',
        csvImporting: 'Importiere...',
        csvSuccess: 'Portfolio erfolgreich importiert!',
        csvError: 'Fehler beim CSV-Import',
        csvFormatHint: 'Format: ticker, shares, buy_price, buy_date, currency (optional)',

        // Shadow Portfolio Agent
        shadowAgent: 'Shadow Agent',
        shadowTitle: '🤖 Shadow Portfolio Agent',
        shadowSubtitle: 'Autonomer AI-Agent der selbstständig ein fiktives Portfolio verwaltet',
        shadowStartAgent: 'Agent starten',
        shadowRunning: '⏳ Läuft...',
        shadowResetTitle: 'Portfolio zurücksetzen',
        shadowKpiTotal: 'Gesamtwert',
        shadowKpiPnl: 'P&L gesamt',
        shadowKpiCash: 'Cash',
        shadowKpiPositions: 'Positionen',
        shadowChartTitle: '📈 Shadow vs. Echtes Portfolio',
        shadowTableTitle: '📋 Shadow-Positionen',
        shadowTableHeaderStock: 'Aktie',
        shadowTableHeaderShares: 'Stk.',
        shadowTableHeaderPrice: 'Kurs (EUR)',
        shadowTableHeaderValue: 'Wert',
        shadowTableHeaderWeight: 'Gewicht',
        shadowTableHeaderPnl: 'P&L',
        shadowTableHeaderSector: 'Sektor',
        shadowEmptyPositions: 'Noch keine Positionen — Agent starten um zu initialisieren.',
        shadowLastDecision: 'Letzter AI-Entscheid',
        shadowTransactions: '🔄 Transaktionshistorie',
        shadowLoading: 'Wird geladen...',
        shadowConfigTitle: '⚙️ Agenten-Konfiguration',
        shadowConfigBadge: 'Standard',
        shadowConfigDesc: 'Konfiguration bleibt nach Reset erhalten',
        shadowStrategyMode: '🎯 Strategie-Modus',
        shadowStratConsLabel: 'Konservativ',
        shadowStratConsDesc: 'Viel Cash, nur Score >70, stabile Sektoren',
        shadowStratBalLabel: 'Ausgewogen',
        shadowStratBalDesc: 'Wachstum + Sicherheit, Regeln strikt',
        shadowStratAggLabel: 'Aggressiv',
        shadowStratAggDesc: 'Risikofreudig, weniger Cash, hohe Gewichtungen',
        shadowRulesTitle: '📏 Portfolio-Regeln',
        shadowRuleMaxPos: 'Max. Positionen',
        shadowRuleMaxPosDesc: 'Wie viele Aktien darf das Portfolio maximal halten',
        shadowRuleMaxWeight: 'Max. Gewichtung / Position',
        shadowRuleMaxWeightDesc: 'Maximaler Anteil einer einzelnen Position am Gesamtportfolio',
        shadowRuleMinCash: 'Mind. Cash-Reserve',
        shadowRuleMinCashDesc: 'Dieser Cash-Anteil bleibt immer unberührt (Sicherheitspuffer)',
        shadowRuleMinTrade: 'Min. Trade-Volumen',
        shadowRuleMinTradeDesc: 'Kleinere Trades werden ignoriert (Transaktionskosten-Simulation)',
        shadowRuleMaxTrades: 'Max. Trades pro Zyklus',
        shadowRuleMaxTradesDesc: 'Begrenzt wie viele Trades der Agent pro Tag ausführen darf',
        shadowRuleMaxSector: 'Max. Sektor-Konzentration',
        shadowRuleMaxSectorDesc: 'Verhindert Klumpenrisiken in einem einzelnen Sektor',
        shadowRuleMinScore: 'Mindest-Score für Kauf',
        shadowRuleMinScoreDesc: 'Aktiengüte-Schwellenwert für Neukäufe',
        shadowRestoreDefaults: 'Standard wiederherstellen',
        shadowSaveConfig: 'Konfiguration speichern',

        // Shadow Agent JS Strings
        shadowAgentRunningToast: '🤖 Shadow Agent läuft... (30-90 Sekunden)',
        shadowAgentErrorToast: '❌ Agent-Fehler: ',
        shadowAgentSuccessToast: '✅ Shadow Agent:', // {0} Trades ausgeführt appended dynamically
        shadowAgentFailToast: '❌ Agent-Aufruf fehlgeschlagen',
        shadowResetConfirm: 'Shadow-Portfolio wirklich zurücksetzen? Alle Positionen und Transaktionen werden gelöscht.\n\n💡 Die Konfiguration (Agenten-Regeln) bleibt erhalten.',
        shadowResetSuccess: '🗑️ Shadow-Portfolio zurückgesetzt',
        shadowResetFail: '❌ Reset fehlgeschlagen',
        shadowEmptyTransactions: 'Noch keine Transaktionen.',
        shadowModeCons: 'Konservativ',
        shadowModeBal: 'Ausgewogen',
        shadowModeAgg: 'Aggressiv',
        shadowModeDefault: 'Standard',
        shadowSaveSaving: 'Speichert...',
        shadowSaveSuccess: '✅ Konfiguration gespeichert — gilt ab dem nächsten Zyklus',
        shadowSaveFail: '❌ Speichern fehlgeschlagen',
        shadowSaveNetFail: '❌ Netzwerkfehler beim Speichern',
        shadowResetConfigConfirm: 'Konfiguration auf Standardwerte zurücksetzen?',
        shadowResetConfigSuccess: '🔄 Konfiguration zurückgesetzt',
        shadowResetConfigFail: '❌ Fehler beim Zurücksetzen',
        shadowEmptyChart: 'Noch keine Performance-Daten — Agent starten um zu beginnen.',
    },
    en: {
        // Header
        portfolioValue: 'Portfolio Value',
        today: 'Today:',
        toggleTheme: 'Toggle theme',
        toggleCurrency: 'Toggle currency',
        actions: 'Actions',
        updateParqet: 'Update Parqet',
        telegramReport: 'Telegram Report',
        fullAnalysis: 'Full Analysis',
        demoMode: 'Demo Mode',
        demoBanner: '🎭 Demo Mode — Fictitious data for demonstration purposes',
        uploadCsv: 'CSV Import',

        // Navigation
        overview: 'Overview',
        analysis: 'Analysis',
        history: 'History',
        rebalancing: 'Rebalancing',
        techPicks: 'Tech Picks',
        aiAdvisor: 'AI Advisor',

        // Stats
        positions: 'Positions',

        // Movers
        dailyWinners: '🟢 Top Gainers',
        dailyLosers: '🔴 Top Losers',

        // Heatmap
        portfolioHeatmap: '🗺️ Portfolio Heatmap',

        // Table
        portfolioPositions: 'Portfolio Positions',
        sortBy: 'Sort:',
        name: 'Name',
        price: 'Price',
        costBasis: 'Cost',
        todayShort: 'Today',
        shares: 'Shares',
        value: 'Value',
        score: 'Score',
        rating: 'Rating',
        details: 'Details',
        all: 'All',

        // Analysis Tab
        sectorAllocation: '🏗️ Sector Allocation',
        riskProfile: '🛡️ Risk Profile',
        performanceBenchmark: '📈 Performance vs. Benchmark',
        dividends: '💰 Dividends',
        correlationMatrix: '🔗 Correlation Matrix',
        earningsCalendar: '📅 Earnings Calendar',
        months3: '3 Months',
        months6: '6 Months',
        year1: '1 Year',

        // History Tab
        totalValue: '📊 Total Value',
        unrealized: '📈 Unrealized',
        realized: '💰 Realized',
        dividendsKpi: '🪙 Dividends',
        taxes: '🏛️ Taxes',
        fees: '💳 Fees',
        allPositions: '📋 All Positions',
        active: 'Active',
        sold: 'Sold',

        // Rebalancing Tab
        rebalancingRecommendations: '⚖️ Rebalancing Recommendations',
        calculating: 'Calculating...',

        // Tech Picks Tab
        dailyTechPicks: '🚀 Daily Tech Picks',
        techPicksSubtitle: 'High-potential stocks from the technology sector',

        // AI Advisor Tab
        tradeAnalysis: 'Trade Analysis',
        chat: 'Chat',
        aiTradeAdvisor: '🧠 AI Trade Advisor',
        advisorSubtitle: 'Evaluate buy and sell decisions with AI-powered portfolio analysis',
        ticker: 'Ticker',
        tickerPlaceholder: 'e.g. NVDA',
        action: 'Action',
        buy: 'Buy',
        increase: 'Add to Position',
        sell: 'Sell',
        amountEur: 'Amount (EUR)',
        amountPlaceholder: 'e.g. 2000',
        externalSources: '📎 External Sources',
        optional: '(optional)',
        contextPlaceholder: 'Paste analyst comments, article excerpts, or your own notes here...',
        startAnalysis: 'Start Analysis',
        aiAnalyzing: '⏳ AI analyzing...',

        // Chat
        portfolioChat: '💬 Portfolio Chat',
        newChat: '🗑️ New',
        chatSubtitle: 'Ask questions, discuss hypotheses, analyze scenarios — with full portfolio context',
        chatWelcome1: '👋 Hi! I\'m your portfolio advisor.',
        chatWelcome2: 'Ask me anything about your portfolio. Examples:',
        chatSuggestion1: 'How diversified is my portfolio?',
        chatSuggestion2: 'What happens if the USD drops 10%?',
        chatSuggestion3: 'Which stock has the best risk/reward ratio?',
        chatSuggestion4: 'How concentrated is my tech sector exposure?',
        chatInputPlaceholder: 'Your question...',
        send: 'Send',

        // Stock Panel
        stockOverview: 'Overview',
        fundamentals: 'Fundamentals',
        technical: 'Technical',
        news: 'News',

        // Mobile Nav
        rebalance: 'Rebalance',
        picks: 'Picks',
        ai: 'AI',

        // Dynamic content (app.js)
        priority: 'Priority',
        quality: 'Quality',
        scoreBreakdown: 'Score Breakdown',
        insiderBuys: 'Insider Buys',
        insiderSells: 'Insider Sales',
        insiderBuysPct: 'Buys',
        annualPerShare: 'Annual/Share',
        overbought: '⚠️ Overbought',
        oversold: '⚠️ Oversold',
        normal: '✅ Normal',
        noTechData: 'No technical data available',
        noFundData: 'No fundamental data available',
        switchToReal: 'Switch to real portfolio data',
        fullAnalysisRunning: '🔬 Full analysis running...',
        volatilityPa: 'Volatility (p.a.)',
        varDaily: 'VaR 95% (daily)',
        annualIncome: 'Annual Income',
        calcRunning: 'Calculating... (requires price data)',
        newsUnavailable: 'News unavailable',
        noHistoryData: 'No historical data available. Please run a data update first.',
        sellRatingHint: 'with Sell rating — check rebalancing?',
        position: 'position',
        positionPlural: 'positions',

        // CSV Upload
        csvUploadTitle: 'CSV Portfolio Import',
        csvUploadDesc: 'Import your portfolio from a CSV file',
        csvSelectFile: 'Select File',
        csvImporting: 'Importing...',
        csvSuccess: 'Portfolio imported successfully!',
        csvError: 'CSV import error',
        csvFormatHint: 'Format: ticker, shares, buy_price, buy_date, currency (optional)',

        // Shadow Portfolio Agent
        shadowAgent: 'Shadow Agent',
        shadowTitle: '🤖 Shadow Portfolio Agent',
        shadowSubtitle: 'Autonomous AI agent independently managing a fictitious portfolio',
        shadowStartAgent: 'Start Agent',
        shadowRunning: '⏳ Running...',
        shadowResetTitle: 'Reset portfolio',
        shadowKpiTotal: 'Total Value',
        shadowKpiPnl: 'Total P&L',
        shadowKpiCash: 'Cash',
        shadowKpiPositions: 'Positions',
        shadowChartTitle: '📈 Shadow vs. Real Portfolio',
        shadowTableTitle: '📋 Shadow Positions',
        shadowTableHeaderStock: 'Stock',
        shadowTableHeaderShares: 'Shares',
        shadowTableHeaderPrice: 'Price (EUR)',
        shadowTableHeaderValue: 'Value',
        shadowTableHeaderWeight: 'Weight',
        shadowTableHeaderPnl: 'P&L',
        shadowTableHeaderSector: 'Sector',
        shadowEmptyPositions: 'No positions yet — Start the agent to initialize.',
        shadowLastDecision: 'Last AI Decision',
        shadowTransactions: '🔄 Transaction History',
        shadowLoading: 'Loading...',
        shadowConfigTitle: '⚙️ Agent Configuration',
        shadowConfigBadge: 'Default',
        shadowConfigDesc: 'Configuration is preserved after reset',
        shadowStrategyMode: '🎯 Strategy Mode',
        shadowStratConsLabel: 'Conservative',
        shadowStratConsDesc: 'High cash, only score >70, stable sectors',
        shadowStratBalLabel: 'Balanced',
        shadowStratBalDesc: 'Growth & Security, strict rules',
        shadowStratAggLabel: 'Aggressive',
        shadowStratAggDesc: 'Risk-seeking, less cash, high weights',
        shadowRulesTitle: '📏 Portfolio Rules',
        shadowRuleMaxPos: 'Max Positions',
        shadowRuleMaxPosDesc: 'Maximum number of stocks the portfolio may hold',
        shadowRuleMaxWeight: 'Max Weight / Position',
        shadowRuleMaxWeightDesc: 'Maximum percentage a single position can represent',
        shadowRuleMinCash: 'Min Cash Reserve',
        shadowRuleMinCashDesc: 'This cash ratio remains untouched (safety buffer)',
        shadowRuleMinTrade: 'Min Trade Volume',
        shadowRuleMinTradeDesc: 'Smaller trades are ignored (Transaction cost simulation)',
        shadowRuleMaxTrades: 'Max Trades per Cycle',
        shadowRuleMaxTradesDesc: 'Limits how many trades the agent can execute per day',
        shadowRuleMaxSector: 'Max Sector Concentration',
        shadowRuleMaxSectorDesc: 'Prevents cluster risks in a single sector',
        shadowRuleMinScore: 'Minimum Buy Score',
        shadowRuleMinScoreDesc: 'Stock quality threshold for new purchases',
        shadowRestoreDefaults: 'Restore defaults',
        shadowSaveConfig: 'Save configuration',

        // Shadow Agent JS Strings
        shadowAgentRunningToast: '🤖 Shadow Agent running... (30-90 seconds)',
        shadowAgentErrorToast: '❌ Agent Error: ',
        shadowAgentSuccessToast: '✅ Shadow Agent:', // {0} Trades executed appended dynamically
        shadowAgentFailToast: '❌ Agent execution failed',
        shadowResetConfirm: 'Really reset Shadow Portfolio? All positions and transactions will be deleted.\n\n💡 The configuration (Agent Rules) will be preserved.',
        shadowResetSuccess: '🗑️ Shadow Portfolio reset successfully',
        shadowResetFail: '❌ Reset failed',
        shadowEmptyTransactions: 'No transactions yet.',
        shadowModeCons: 'Conservative',
        shadowModeBal: 'Balanced',
        shadowModeAgg: 'Aggressive',
        shadowModeDefault: 'Default',
        shadowSaveSaving: 'Saving...',
        shadowSaveSuccess: '✅ Configuration saved — effective next cycle',
        shadowSaveFail: '❌ Save failed',
        shadowSaveNetFail: '❌ Network error while saving',
        shadowResetConfigConfirm: 'Reset configuration to default values?',
        shadowResetConfigSuccess: '🔄 Configuration reset',
        shadowResetConfigFail: '❌ Reset failed',
        shadowEmptyChart: 'No performance data yet — start the agent to begin.',
    }
};

/**
 * Get translation for a key
 * @param {string} key - Translation key
 * @returns {string} Translated string
 */
function t(key) {
    return (i18n[currentLang] && i18n[currentLang][key]) || (i18n.en && i18n.en[key]) || key;
}

/**
 * Switch language and re-render UI
 * @param {string} lang - 'de' or 'en'
 */
function switchLanguage(lang) {
    currentLang = lang;
    localStorage.setItem('financebro-lang', lang);
    applyTranslations();
    // Re-render dynamic content
    if (typeof renderDashboard === 'function') {
        renderDashboard();
    }
}

/**
 * Apply translations to all elements with data-i18n attribute
 */
function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const translated = t(key);
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
            el.placeholder = translated;
        } else {
            // Preserve child elements (icons etc.)
            const icon = el.querySelector('[data-lucide]');
            if (icon) {
                el.innerHTML = '';
                el.appendChild(icon);
                el.appendChild(document.createTextNode(' ' + translated));
            } else {
                el.textContent = translated;
            }
        }
    });
    // Update title attribute translations
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        el.title = t(el.getAttribute('data-i18n-title'));
    });
    // Update html lang
    document.documentElement.lang = currentLang;
    // Update language toggle button
    const langBtn = document.getElementById('langToggle');
    if (langBtn) langBtn.textContent = currentLang.toUpperCase();
}
