/**
 * FinanzBro i18n — Bilingual Translation System (DE + EN)
 * Usage: t('key') returns the string for the current language
 * Language is stored in localStorage and defaults to browser language
 */

let currentLang = localStorage.getItem('finanzbro-lang') ||
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
    localStorage.setItem('finanzbro-lang', lang);
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
