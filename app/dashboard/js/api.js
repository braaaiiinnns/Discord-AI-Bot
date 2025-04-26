/**
 * API Service for Discord Bot Dashboard
 * Handles all API requests with authentication
 */

class Api {
    constructor() {
        this.baseUrl = DashboardConfig.apiBaseUrl;
        this.apiKey = null;
        this.requestQueue = [];
        this.isAuthReady = false;
        this.authRetryCount = 0;
        this.maxAuthRetries = 3;
        
        // Set up auth state listener to refresh auth status when it changes
        if (typeof auth !== 'undefined') {
            auth.addAuthStateListener(this.handleAuthStateChange.bind(this));
        }
        
        // Load saved API key from local storage as fallback
        const savedApiKey = localStorage.getItem(DashboardConfig.storage.apiKey);
        if (savedApiKey) {
            this.apiKey = savedApiKey;
            console.debug('API: Loaded API key from local storage for fallback');
            // Mark auth as ready if we have a saved API key
            this.setAuthReady();
        }
        
        // Set up event listener for visibility changes (tab focus/blur)
        if (typeof document !== 'undefined') {
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden && auth && auth.isAuthenticated) {
                    console.debug('Page became visible, refreshing authentication state');
                    auth.checkAccessStatus().then(() => {
                        this.setAuthReady();
                    });
                }
            });
        }
    }
    
    /**
     * Handle authentication state changes
     */
    handleAuthStateChange(authState) {
        if (authState.isAuthenticated && authState.user && authState.user.api_key) {
            console.debug('API: Auth state changed, user is authenticated with API key');
            this.setAuthReady();
        } else if (!authState.isAuthenticated) {
            console.debug('API: Auth state changed, user is not authenticated');
            this.isAuthReady = false;
        }
    }

    /**
     * Set the API key for authentication
     * @param {string} apiKey 
     */
    setApiKey(apiKey) {
        if (apiKey) {
            this.apiKey = apiKey;
            // Save to localStorage as fallback
            localStorage.setItem(DashboardConfig.storage.apiKey, apiKey);
            // Mark auth as ready since we have a valid API key
            this.setAuthReady();
        }
    }

    /**
     * Mark auth as ready and process any queued requests
     */
    setAuthReady() {
        this.isAuthReady = true;
        console.debug(`API: Auth is ready, processing ${this.requestQueue.length} queued requests`);
        this.processQueue();
    }

    /**
     * Process the queued requests once auth is ready
     */
    processQueue() {
        if (this.requestQueue.length > 0) {
            console.debug(`Processing ${this.requestQueue.length} queued API requests`);
            
            // Process each queued request
            this.requestQueue.forEach(item => {
                clearTimeout(item.timeoutId); // Clear the timeout
                this.executeRequest(item.endpoint, item.options)
                    .then(response => {
                        item.resolve(response);
                        item.subscribers.forEach(sub => sub.resolve(response));
                    })
                    .catch(error => {
                        item.reject(error);
                        item.subscribers.forEach(sub => sub.reject(error));
                    });
            });
            
            // Clear the queue
            this.requestQueue = [];
        }
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
            if (auth.user.api_key) {
                headers['Authorization'] = `Bearer ${auth.user.api_key}`;
                console.debug('Using user API key for authentication');
            } else {
                console.debug('User is authenticated but has no API key');
            }
        }
        // Fallback to locally stored API key if no user is authenticated
        else if (this.apiKey) {
            headers['Authorization'] = `Bearer ${this.apiKey}`;
            console.debug('Using locally stored API key for authentication');
        } else {
            console.debug('No API key available for authentication');
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
        // First, ensure we always have the latest API key from localStorage as a fallback
        if (!this.apiKey) {
            const savedApiKey = localStorage.getItem(DashboardConfig.storage.apiKey);
            if (savedApiKey) {
                console.debug('API: Loading API key from localStorage before request');
                this.apiKey = savedApiKey;
                this.isAuthReady = true;
            }
        }
        
        // Create a unique key for this request
        const requestKey = `${endpoint}-${JSON.stringify(options)}`;
        
        // Check if we're already waiting for this exact request
        if (this.requestQueue.some(item => item.key === requestKey)) {
            console.debug(`API: Identical request to ${endpoint} already queued, sharing promise`);
            // Find the existing request and return its promise
            const existingRequest = this.requestQueue.find(item => item.key === requestKey);
            return new Promise((resolve, reject) => {
                existingRequest.subscribers.push({ resolve, reject });
            });
        }
        
        if (!this.isAuthReady) {
            console.debug(`API: Auth not ready, queuing request to ${endpoint}`);
            return new Promise((resolve, reject) => {
                // Add request to queue with a timeout
                const timeoutId = setTimeout(() => {
                    // Find and remove this specific request
                    const index = this.requestQueue.findIndex(item => item.key === requestKey);
                    if (index !== -1) {
                        const item = this.requestQueue[index];
                        this.requestQueue.splice(index, 1);
                        
                        // Reject all subscribers
                        item.subscribers.forEach(sub => {
                            sub.reject(new Error("Request timed out waiting for authentication"));
                        });
                    }
                }, 10000); // 10 second timeout
                
                this.requestQueue.push({
                    endpoint,
                    options,
                    resolve,
                    reject,
                    key: requestKey,
                    timeoutId,
                    subscribers: [] // Other promises sharing this request
                });
            });
        }

        return this.executeRequest(endpoint, options);
    }

    /**
     * Execute the API request
     * @param {string} endpoint - API endpoint
     * @param {Object} options - Fetch options
     * @returns {Promise<Object>} Response data
     */
    async executeRequest(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        
        // CRITICAL FIX: Ensure API key is available before every request
        this._ensureApiKey();
        
        const headers = this.getHeaders();
        const fetchOptions = {
            ...options,
            headers: {
                ...headers,
                ...(options.headers || {})
            },
            credentials: 'include'  // Include cookies for session authentication
        };
        
        // Add debug logging for authentication headers
        const hasApiKey = headers['Authorization'] && headers['Authorization'].startsWith('Bearer ');
        console.debug(`API Request to ${endpoint}: Auth ${hasApiKey ? 'present' : 'missing'}`);

        try {
            const response = await fetch(url, fetchOptions);
            
            if (response.status === 401) {
                // Authentication error - try to recover
                console.warn(`Authentication failed for ${endpoint}, attempting to recover...`);
                
                // Increment retry counter
                this.authRetryCount++;
                
                if (this.authRetryCount <= this.maxAuthRetries) {
                    console.debug(`Auth retry attempt ${this.authRetryCount}/${this.maxAuthRetries}`);
                    
                    // Try to refresh auth if we have access to auth object
                    if (auth && typeof auth.fetchApiKey === 'function') {
                        try {
                            console.debug('Attempting to refresh API key...');
                            const keyData = await auth.fetchApiKey();
                            
                            if (keyData && keyData.api_key) {
                                console.debug('Successfully refreshed API key');
                                // Update the stored user object
                                if (auth.user) {
                                    auth.user.api_key = keyData.api_key;
                                    this.isAuthReady = true;
                                    
                                    // Save to localStorage as fallback
                                    localStorage.setItem(DashboardConfig.storage.apiKey, keyData.api_key);
                                    
                                    // Try the request again with the new API key
                                    console.debug('Retrying request with refreshed API key');
                                    return this.executeRequest(endpoint, options);
                                }
                            }
                        } catch (refreshError) {
                            console.error('Failed to refresh API key:', refreshError);
                        }
                    }
                } else {
                    // Reset retry counter after max retries
                    this.authRetryCount = 0;
                    console.error(`Maximum authentication retry attempts (${this.maxAuthRetries}) reached`);
                }
                
                // If we get here, authentication recovery failed
                if (!auth || !auth.isAuthenticated) {
                    console.warn('Authentication required. Consider logging in again.');
                }
                throw new Error('Authentication required');
            }
            
            // Reset retry counter on successful requests
            this.authRetryCount = 0;
            
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
     * Ensure the API key is set before making any request
     * This is called before any API request to guarantee authentication
     * @private
     */
    _ensureApiKey() {
        // Always check localStorage first for the most recent API key
        const savedApiKey = localStorage.getItem(DashboardConfig.storage.apiKey);
        
        // Only update if we have a saved key and our current one is missing or different
        if (savedApiKey && (!this.apiKey || this.apiKey !== savedApiKey)) {
            console.debug('API: Retrieving API key from localStorage before request');
            this.apiKey = savedApiKey;
            this.isAuthReady = true;
        }
        
        // Check auth user as fallback
        if ((!this.apiKey || this.apiKey === "undefined" || this.apiKey === "null") && 
            auth && auth.isAuthenticated && auth.user && auth.user.api_key) {
            console.debug('API: Using authenticated user API key');
            this.apiKey = auth.user.api_key;
            // Save to localStorage for future use
            localStorage.setItem(DashboardConfig.storage.apiKey, this.apiKey);
            this.isAuthReady = true;
        }
        
        return this.apiKey && this.apiKey !== "undefined" && this.apiKey !== "null";
    }

    /**
     * Health check endpoint
     * @returns {Promise<Object>} Health status
     */
    async healthCheck() {
        // Use the correct path for the health endpoint
        // The baseUrl already includes '/api' so we should access '/api/health'
        // Since the baseUrl already has '/api', we need to use '/health'
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