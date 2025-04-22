/**
 * Main Dashboard Application Logic
 */

document.addEventListener('DOMContentLoaded', function() {
    // Authentication is now handled by auth.js
    // When auth.js loads, it will call initAuth() which will:
    // 1. Check if the user is authenticated
    // 2. Show login page or dashboard based on authentication status
    
    // Set up event listeners
    setupEventListeners();
    
    // Load settings from local storage
    loadSettings();
});

/**
 * Initialize the dashboard
 */
function initializeDashboard() {
    // Check API connectivity
    checkApiConnection()
        .then(connected => {
            if (!connected) {
                showApiErrorMessage();
                return;
            }
            
            // Load initial data
            loadDashboardData();
            
            // Load guilds (servers) for the selector
            loadGuilds();
            
            // Load bot status
            loadBotStatus();
            
            // Set up automatic refresh
            setupRefreshTimer();
        });
}

/**
 * Check API connection
 */
async function checkApiConnection() {
    try {
        await api.healthCheck();
        return true;
    } catch (error) {
        console.error('API connection failed:', error);
        return false;
    }
}

/**
 * Show API error message
 */
function showApiErrorMessage() {
    // Create error message element
    const errorMsg = document.createElement('div');
    errorMsg.className = 'alert alert-danger';
    errorMsg.innerHTML = `
        <strong>API Connection Error</strong><br>
        Could not connect to the API. Please check:
        <ul>
            <li>The server is running</li>
            <li>You are logged in properly</li>
            <li>Your browser allows cross-origin requests</li>
        </ul>
        <button class="btn btn-sm btn-outline-danger mt-2" onclick="retryConnection()">Retry Connection</button>
    `;
    
    // Insert at the top of the content area
    const contentArea = document.getElementById('content');
    contentArea.insertBefore(errorMsg, contentArea.firstChild);
    
    // Navigate to settings page
    navigateToPage('settings');
}

/**
 * Retry API connection
 */
function retryConnection() {
    // Remove error message
    const errorMsg = document.querySelector('.alert.alert-danger');
    if (errorMsg) {
        errorMsg.remove();
    }
    
    // Try to initialize again
    initializeDashboard();
}

/**
 * Set up event listeners
 */
function setupEventListeners() {
    // Sidebar toggle
    document.getElementById('sidebarCollapse').addEventListener('click', function() {
        document.getElementById('sidebar').classList.toggle('active');
        document.getElementById('content').classList.toggle('active');
    });
    
    // Navigation links
    document.querySelectorAll('#sidebar a[data-page]').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const page = this.getAttribute('data-page');
            navigateToPage(page);
        });
    });
    
    // Guild selector
    document.getElementById('guild-selector').addEventListener('change', function() {
        const guildId = this.value;
        loadDashboardData(guildId);
    });
    
    // Time range selector
    document.querySelectorAll('.time-range').forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const days = parseInt(this.getAttribute('data-days'));
            const guildId = document.getElementById('guild-selector').value;
            loadDashboardData(guildId, days);
        });
    });
    
    // Settings form
    document.getElementById('settings-form').addEventListener('submit', function(e) {
        e.preventDefault();
        saveSettings();
    });
}

/**
 * Navigate to a page
 */
function navigateToPage(page) {
    // Update active state in sidebar
    document.querySelectorAll('#sidebar li').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`#sidebar a[data-page="${page}"]`).parentElement.classList.add('active');
    
    // Hide all pages and show the selected one
    document.querySelectorAll('.dashboard-page').forEach(item => {
        item.style.display = 'none';
    });
    document.getElementById(`${page}-page`).style.display = 'block';
    
    // Load page-specific data if needed
    loadPageData(page);
}

/**
 * Load page-specific data
 */
function loadPageData(page) {
    const guildId = document.getElementById('guild-selector').value;
    const days = DashboardConfig.defaultTimeRange;
    
    switch (page) {
        case 'overview':
            // Dashboard summary already loaded
            break;
        case 'messages':
            loadMessageStats(guildId, days);
            break;
        case 'users':
            loadUserStats(guildId);
            break;
        case 'ai':
            loadAIStats(guildId, days);
            break;
        case 'settings':
            // Update settings with user data if authenticated
            if (auth && auth.user) {
                updateSettingsPage();
            }
            break;
    }
}

/**
 * Load dashboard data
 */
async function loadDashboardData(guildId = '', days = DashboardConfig.defaultTimeRange) {
    try {
        // Get dashboard summary
        const summaryData = await api.getDashboardSummary(guildId);
        updateDashboardSummary(summaryData);
        
        // Get message stats for overview charts
        const messageData = await api.getMessageStats(guildId, days);
        updateOverviewCharts(messageData);
    } catch (error) {
        console.error('Failed to load dashboard data:', error);
    }
}

/**
 * Load guilds for the selector
 */
async function loadGuilds() {
    try {
        const guilds = await api.getGuilds();
        const selector = document.getElementById('guild-selector');
        
        // Keep the "All Servers" option
        selector.innerHTML = '<option value="">All Servers</option>';
        
        // Add guilds
        guilds.forEach(guild => {
            const option = document.createElement('option');
            option.value = guild.id;
            option.textContent = guild.name;
            selector.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load guilds:', error);
    }
}

/**
 * Load bot status
 */
async function loadBotStatus() {
    try {
        const status = await api.getBotStatus();
        const botStatus = document.getElementById('bot-status');
        
        botStatus.innerHTML = `
            <p class="bot-name">${status.logged_in_as || 'Discord Bot'}</p>
            <span class="status-dot ${status.is_ready ? 'online' : 'idle'}"></span>
            <span class="status-text">${status.is_ready ? 'Online' : 'Connecting...'}</span>
        `;
    } catch (error) {
        console.error('Failed to load bot status:', error);
        document.getElementById('bot-status').innerHTML = `
            <p class="bot-name">Discord Bot</p>
            <span class="status-dot offline"></span>
            <span class="status-text">Status Unknown</span>
        `;
    }
}

/**
 * Load message statistics
 */
async function loadMessageStats(guildId, days) {
    try {
        const data = await api.getMessageStats(guildId, days);
        
        // Update message page charts
        chartManager.updateMessageTrendsChart(data);
        chartManager.updateMessageLengthChart(data);
        chartManager.updateWeekdayChart(data);
        chartManager.updateHourDistributionChart(data);
    } catch (error) {
        console.error('Failed to load message statistics:', error);
    }
}

/**
 * Load user statistics
 */
async function loadUserStats(guildId) {
    try {
        const data = await api.getUserStats(guildId);
        
        // Update user page charts
        chartManager.updateUserTrendsChart(data);
        chartManager.updateUserActivityChart(data);
        
        // Update users table
        updateUsersTable(data);
    } catch (error) {
        console.error('Failed to load user statistics:', error);
    }
}

/**
 * Load AI statistics
 */
async function loadAIStats(guildId, days) {
    try {
        const data = await api.getAIStats(guildId, days);
        
        // Update AI page charts
        chartManager.updateAIDailyChart(data);
        chartManager.updateAIModelsChart(data);
        chartManager.updateAIUsersChart(data);
        
        // Update recent AI interactions
        updateRecentAIInteractions(data);
    } catch (error) {
        console.error('Failed to load AI statistics:', error);
    }
}

/**
 * Update dashboard summary
 */
function updateDashboardSummary(data) {
    // Update stat cards
    document.getElementById('total-messages').textContent = formatNumber(data.message_count || 0);
    document.getElementById('total-users').textContent = formatNumber(data.user_count || 0);
    document.getElementById('ai-interactions').textContent = formatNumber(data.ai_interaction_count || 0);
    document.getElementById('channel-count').textContent = formatNumber(data.channel_count || 0);
}

/**
 * Update overview page charts
 */
function updateOverviewCharts(data) {
    chartManager.updateMessageActivityChart(data);
    chartManager.updateChannelChart(data);
    chartManager.updateUserChart(data);
    chartManager.updateHourlyChart(data);
}

/**
 * Update the users table
 */
function updateUsersTable(data) {
    const tableBody = document.querySelector('#users-table tbody');
    tableBody.innerHTML = '';
    
    if (data && data.top_users) {
        data.top_users.forEach(user => {
            const row = document.createElement('tr');
            
            row.innerHTML = `
                <td>${escapeHtml(user.username || 'Unknown')}</td>
                <td>${formatNumber(user.message_count || 0)}</td>
                <td>${formatNumber(user.active_days || 0)}</td>
                <td>${user.avg_length ? user.avg_length.toFixed(1) : '0'}</td>
                <td>${formatDate(user.last_active || null)}</td>
            `;
            
            tableBody.appendChild(row);
        });
    }
}

/**
 * Update recent AI interactions
 */
function updateRecentAIInteractions(data) {
    const container = document.querySelector('.ai-interactions-list');
    container.innerHTML = '';
    
    // Check for mock data which might not have this property
    if (!data || !data.recent_interactions) {
        container.innerHTML = '<div class="p-3 text-center">No recent AI interactions to display</div>';
        return;
    }
    
    data.recent_interactions.slice(0, 5).forEach(interaction => {
        const item = document.createElement('div');
        item.className = 'ai-interaction-item';
        
        item.innerHTML = `
            <div class="ai-interaction-header">
                <span class="ai-interaction-model">${escapeHtml(interaction.model || 'Unknown Model')}</span>
                <span class="ai-interaction-time">${formatDate(interaction.timestamp || null)}</span>
            </div>
            <div class="ai-interaction-content">${escapeHtml(truncateText(interaction.response || 'No response', 150))}</div>
        `;
        
        container.appendChild(item);
    });
}

/**
 * Setup refresh timer
 */
function setupRefreshTimer() {
    const interval = parseInt(localStorage.getItem(DashboardConfig.storage.refreshInterval)) || DashboardConfig.refreshInterval;
    
    // Clear existing timer if any
    if (window.dashboardRefreshTimer) {
        clearInterval(window.dashboardRefreshTimer);
    }
    
    // Set up new timer
    window.dashboardRefreshTimer = setInterval(() => {
        const guildId = document.getElementById('guild-selector').value;
        loadDashboardData(guildId);
        loadBotStatus();
    }, interval);
}

/**
 * Load settings from local storage
 */
function loadSettings() {
    // API Key
    const apiKey = localStorage.getItem(DashboardConfig.storage.apiKey) || '';
    document.getElementById('api-key').value = apiKey;
    api.setApiKey(apiKey);
    
    // Refresh interval
    const refreshInterval = localStorage.getItem(DashboardConfig.storage.refreshInterval);
    if (refreshInterval) {
        document.getElementById('refresh-interval').value = parseInt(refreshInterval) / (60 * 1000);
    }
    
    // Dark mode
    const darkMode = localStorage.getItem(DashboardConfig.storage.darkMode) === 'true';
    document.getElementById('dark-mode').checked = darkMode;
    if (darkMode) {
        document.body.classList.add('dark-mode');
    }
}

/**
 * Save settings to local storage
 */
function saveSettings() {
    // Refresh interval (convert minutes to milliseconds)
    const refreshInterval = parseInt(document.getElementById('refresh-interval').value) * 60 * 1000;
    localStorage.setItem(DashboardConfig.storage.refreshInterval, refreshInterval);
    
    // Dark mode
    const darkMode = document.getElementById('dark-mode').checked;
    localStorage.setItem(DashboardConfig.storage.darkMode, darkMode);
    
    if (darkMode) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
    
    // Update refresh timer
    setupRefreshTimer();
    
    // Refresh data with new settings
    loadDashboardData();
    
    // Show success alert
    alert('Settings saved successfully!');
}

/**
 * Helper function to format numbers
 */
function formatNumber(num) {
    if (num === undefined || num === null) return '0';
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * Helper function to format dates
 */
function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    return moment(dateStr).format('MMM D, YYYY h:mm A');
}

/**
 * Helper function to truncate text
 */
function truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

/**
 * Helper function to escape HTML
 */
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

/**
 * Update settings page with user data
 */
function updateSettingsPage() {
    updateUserProfile();
}