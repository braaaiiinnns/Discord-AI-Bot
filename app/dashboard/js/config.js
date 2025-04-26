/**
 * Dashboard Configuration
 */

const DashboardConfig = {
    // API Base URL - pointing to separate API server
    apiBaseUrl: 'http://127.0.0.1:5000/api',
    
    // Default time range in days
    defaultTimeRange: 30,
    
    // Default refresh interval in milliseconds
    refreshInterval: 5 * 60 * 1000, // 5 minutes (restored to original value)
    
    // Chart colors
    chartColors: [
        '#7289da', // Discord blue
        '#43b581', // Discord green
        '#f04747', // Discord red
        '#faa61a', // Discord yellow
        '#2e3136', // Discord dark
        '#99aab5', // Discord gray
        '#b9bbbe'  // Discord light gray
    ],
    
    // Chart options common to all charts
    chartOptions: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'bottom',
                labels: {
                    padding: 20,
                    boxWidth: 12
                }
            },
            tooltip: {
                backgroundColor: 'rgba(46, 49, 54, 0.9)',
                titleColor: '#ffffff',
                bodyColor: '#ffffff',
                padding: 15,
                cornerRadius: 4,
                boxPadding: 5
            }
        }
    },
    
    // Storage keys
    storage: {
        apiKey: 'discord_dashboard_api_key',
        darkMode: 'discord_dashboard_dark_mode',
        refreshInterval: 'discord_dashboard_refresh_interval'
    }
};