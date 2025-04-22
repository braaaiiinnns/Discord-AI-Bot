/**
 * API Service for Discord Bot Dashboard
 * Handles all API requests with authentication
 */

class Api {
    constructor() {
        this.baseUrl = DashboardConfig.apiBaseUrl;
        this.apiKey = null;
    }

    /**
     * Set the API key for authentication
     * @param {string} apiKey 
     */
    setApiKey(apiKey) {
        this.apiKey = apiKey;
    }

    /**
     * Get appropriate headers for API requests
     * @returns {Object} Headers object
     */
    getHeaders() {
        const headers = {
            'Content-Type': 'application/json',
        };

        // Use authenticated user's API key if available
        if (auth && auth.isAuthenticated && auth.user) {
            headers['Authorization'] = `Bearer ${auth.user.api_key}`;
        }
        // Fallback to locally stored API key if no user is authenticated
        else if (this.apiKey) {
            headers['Authorization'] = `Bearer ${this.apiKey}`;
        }

        return headers;
    }

    /**
     * Make an API request
     * @param {string} endpoint - API endpoint
     * @param {Object} options - Fetch options
     * @returns {Promise<Object>} Response data
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        
        const fetchOptions = {
            ...options,
            headers: {
                ...this.getHeaders(),
                ...(options.headers || {})
            },
            credentials: 'include'  // Include cookies for session authentication
        };

        try {
            const response = await fetch(url, fetchOptions);
            
            if (response.status === 401) {
                // Authentication error - if using stored API key, might need to login
                if (!auth || !auth.isAuthenticated) {
                    console.warn('Authentication required. Redirecting to login...');
                    // Optional: Redirect to login
                    // window.location.href = '/login';
                }
                throw new Error('Authentication required');
            }
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`API Error ${response.status}: ${errorText}`);
            }
            
            // Check if response is JSON
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            
            return await response.text();
        } catch (error) {
            console.error('API Request Error:', error);
            throw error;
        }
    }

    /**
     * Health check endpoint
     * @returns {Promise<Object>} Health status
     */
    async healthCheck() {
        return this.request('/health');
    }

    /**
     * Get bot status
     * @returns {Promise<Object>} Bot status data
     */
    async getBotStatus() {
        return this.request('/bot/status');
    }

    /**
     * Get dashboard summary data
     * @param {string} guildId - Optional guild ID to filter by
     * @returns {Promise<Object>} Dashboard data
     */
    async getDashboardSummary(guildId = '') {
        const endpoint = guildId ? `/dashboard/summary?guild_id=${guildId}` : '/dashboard/summary';
        return this.request(endpoint);
    }

    /**
     * Get message statistics
     * @param {string} guildId - Optional guild ID to filter by
     * @param {number} days - Number of days to include
     * @returns {Promise<Object>} Message statistics
     */
    async getMessageStats(guildId = '', days = 7) {
        const endpoint = `/stats/messages?days=${days}${guildId ? `&guild_id=${guildId}` : ''}`;
        return this.request(endpoint);
    }

    /**
     * Get user statistics
     * @param {string} guildId - Optional guild ID to filter by
     * @returns {Promise<Object>} User statistics
     */
    async getUserStats(guildId = '') {
        const endpoint = guildId ? `/stats/users?guild_id=${guildId}` : '/stats/users';
        return this.request(endpoint);
    }

    /**
     * Get AI interaction statistics
     * @param {string} guildId - Optional guild ID to filter by
     * @param {number} days - Number of days to include
     * @returns {Promise<Object>} AI statistics
     */
    async getAIStats(guildId = '', days = 7) {
        const endpoint = `/stats/ai?days=${days}${guildId ? `&guild_id=${guildId}` : ''}`;
        return this.request(endpoint);
    }

    /**
     * Get list of guilds (servers)
     * @returns {Promise<Array>} Guild list
     */
    async getGuilds() {
        return this.request('/bot/guilds');
    }

    /**
     * Get detailed guild information
     * @param {string} guildId - Guild ID
     * @returns {Promise<Object>} Guild details
     */
    async getGuildDetails(guildId) {
        return this.request(`/bot/guilds/${guildId}`);
    }

    /**
     * Update bot configuration
     * @param {Object} config - Configuration object
     * @returns {Promise<Object>} Updated configuration
     */
    async updateConfig(config) {
        return this.request('/config', {
            method: 'PUT',
            body: JSON.stringify(config)
        });
    }

    /**
     * Get bot configuration
     * @returns {Promise<Object>} Bot configuration
     */
    async getConfig() {
        return this.request('/config');
    }

    /**
     * Send a test message to a channel
     * @param {string} channelId - Channel ID
     * @param {string} message - Message to send
     * @returns {Promise<Object>} Response from Discord
     */
    async sendTestMessage(channelId, message) {
        return this.request('/bot/send-message', {
            method: 'POST',
            body: JSON.stringify({
                channel_id: channelId,
                message: message
            })
        });
    }
}

// Create global API instance
const api = new Api();