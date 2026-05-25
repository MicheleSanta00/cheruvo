export const translations = {
  it: {
    // Auth
    auth: {
      login: 'Accedi',
      register: 'Registrati',
      email: 'Email',
      password: 'Password',
      welcome: 'Bentornato su FinSentinel',
      noAccount: 'Non hai un account?',
      hasAccount: 'Hai già un account?',
      noCard: 'Inizia gratis, nessuna carta richiesta',
      loading: 'Caricamento...',
      confirmEmail: 'Controlla la tua email per confermare la registrazione!',
    },
    // Header
    header: {
      home: '← Home',
      csv: '↓ CSV',
      csvLocked: '🔒 CSV',
      pro: '✓ Pro',
      upgradePro: '⚡ Pro',
      loading: 'Caricamento...',
      updating: 'Aggiornando news...',
      enterTicker: 'Inserisci un ticker per iniziare',
    },
    // Sidebar
    sidebar: {
      ticker: 'Ticker',
      watchlist: 'Watchlist',
      daysLabel: (d) => `Ultimi ${d} giorni`,
      daysMin: '7g',
      daysMax: (m) => `${m}g`,
      daysProHint: '(Pro: 90g)',
      priceRange: 'Periodo prezzi',
      addWatchlist: '+ Aggiungi alla watchlist',
      saving: 'Salvando...',
      proWatchlist: '⚡ Pro per watchlist illimitata',
      refreshNews: '↻  Aggiorna news',
      updating: 'Aggiornamento...',
      locked: 'Disponibile con Pro',
      upgradeBanner: {
        title: '⚡ Passa a Pro',
        desc: 'Watchlist illimitata · 90 giorni\nAlert email · Export CSV',
        price: '€9/mese →',
      },
      maxDays: 'max 30g',
    },
    // Main content
    main: {
      noNews: 'Nessuna news nel database',
      noNewsHint: 'Clicca',
      noNewsHint2: 'nella sidebar per caricare i dati.',
      refreshNews: 'Aggiorna news',
      chartTitle: (t) => `${t} — Prezzo & Sentiment`,
      chartSub: 'Candlestick OHLCV + Sentiment giornaliero FinBERT',
      price: 'Prezzo',
      positive: 'Positivo',
      negative: 'Negativo',
      advancedTitle: '🔒 Analytics avanzate',
      advancedDesc: 'Distribuzione per fonte, istogramma sentiment e analisi dettagliata disponibili con Pro.',
      upgradeBtn: '⚡ Passa a Pro — €9/mese',
    },
    // Empty state
    empty: {
      title: 'Benvenuto in FinSentinel',
      desc: 'Cerca un ticker nella sidebar oppure selezionane uno dalla watchlist per visualizzare sentiment, prezzi e notizie in tempo reale.',
    },
    // Profile
    profile: {
      title: 'Il tuo profilo',
      subtitle: 'Gestisci il tuo account FinSentinel',
      email: 'Email',
      joinedAt: 'Iscritto il',
      plan: 'Piano',
      planFree: 'Free',
      planPro: '✓ Pro',
      upgradePro: '⚡ Passa a Pro — €9/mese',
      logout: 'Esci dall\'account',
      homepage: '← Homepage',
    },
    // KPI
    kpi: {
      total: 'News totali',
      avg: 'Sentiment medio',
      max: 'Picco positivo',
      min: 'Picco negativo',
      sources: 'Fonti attive',
    },
    // TopNews
    topNews: {
      title: 'Top News',
      lockedTitle: '🔒 Altre news',
      lockedDesc: 'Con Pro visualizzi tutte le news senza limite.',
      upgradeBtn: '⚡ Sblocca con Pro',
      readMore: 'Leggi →',
    },
    // Stats
    stats: {
      title: 'Analisi dettagliata',
      bySource: 'Per fonte',
      distribution: 'Distribuzione sentiment',
    },
  },

  en: {
    // Auth
    auth: {
      login: 'Sign in',
      register: 'Sign up',
      email: 'Email',
      password: 'Password',
      welcome: 'Welcome back to FinSentinel',
      noAccount: "Don't have an account?",
      hasAccount: 'Already have an account?',
      noCard: 'Start free, no card required',
      loading: 'Loading...',
      confirmEmail: 'Check your email to confirm your registration!',
    },
    // Header
    header: {
      home: '← Home',
      csv: '↓ CSV',
      csvLocked: '🔒 CSV',
      pro: '✓ Pro',
      upgradePro: '⚡ Pro',
      loading: 'Loading...',
      updating: 'Updating news...',
      enterTicker: 'Enter a ticker to start',
    },
    // Sidebar
    sidebar: {
      ticker: 'Ticker',
      watchlist: 'Watchlist',
      daysLabel: (d) => `Last ${d} days`,
      daysMin: '7d',
      daysMax: (m) => `${m}d`,
      daysProHint: '(Pro: 90d)',
      priceRange: 'Price range',
      addWatchlist: '+ Add to watchlist',
      saving: 'Saving...',
      proWatchlist: '⚡ Pro for unlimited watchlist',
      refreshNews: '↻  Refresh news',
      updating: 'Updating...',
      locked: 'Available with Pro',
      upgradeBanner: {
        title: '⚡ Upgrade to Pro',
        desc: 'Unlimited watchlist · 90 days\nEmail alerts · CSV export',
        price: '€9/month →',
      },
      maxDays: 'max 30d',
    },
    // Main content
    main: {
      noNews: 'No news in the database',
      noNewsHint: 'Click',
      noNewsHint2: 'in the sidebar to load data.',
      refreshNews: 'Refresh news',
      chartTitle: (t) => `${t} — Price & Sentiment`,
      chartSub: 'Candlestick OHLCV + FinBERT Daily Sentiment',
      price: 'Price',
      positive: 'Positive',
      negative: 'Negative',
      advancedTitle: '🔒 Advanced analytics',
      advancedDesc: 'Source breakdown, sentiment histogram and detailed analysis available with Pro.',
      upgradeBtn: '⚡ Upgrade to Pro — €9/month',
    },
    // Empty state
    empty: {
      title: 'Welcome to FinSentinel',
      desc: 'Search for a ticker in the sidebar or pick one from your watchlist to view sentiment, prices and real-time news.',
    },
    // Profile
    profile: {
      title: 'Your profile',
      subtitle: 'Manage your FinSentinel account',
      email: 'Email',
      joinedAt: 'Joined on',
      plan: 'Plan',
      planFree: 'Free',
      planPro: '✓ Pro',
      upgradePro: '⚡ Upgrade to Pro — €9/month',
      logout: 'Sign out',
      homepage: '← Homepage',
    },
    // KPI
    kpi: {
      total: 'Total news',
      avg: 'Avg sentiment',
      max: 'Peak positive',
      min: 'Peak negative',
      sources: 'Active sources',
    },
    // TopNews
    topNews: {
      title: 'Top News',
      lockedTitle: '🔒 More news',
      lockedDesc: 'With Pro you can view all news without limits.',
      upgradeBtn: '⚡ Unlock with Pro',
      readMore: 'Read →',
    },
    // Stats
    stats: {
      title: 'Detailed analysis',
      bySource: 'By source',
      distribution: 'Sentiment distribution',
    },
  },
}