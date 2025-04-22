/**
 * Authentication Service for Discord Bot Dashboard
 * Handles user authentication, session management and API key handling
 */

class Auth {
    constructor() {
        this.authEndpoint = DashboardConfig.apiBaseUrl + '/auth';
        this.user = null;
        this.isAuthenticated = false;
        this.accessStatus = 'pending';
        this.authListeners = [];
    }

    /**
     * Initialize the authentication system
     * @returns {Promise<void>}
     */
    async initialize() {
        try {
            // Check if the user is already authenticated
            const userData = await this.fetchCurrentUser();
            this.isAuthenticated = userData.authenticated;
            this.user = userData.user;
            
            // Check access status if authenticated
            if (this.isAuthenticated) {
                const accessData = await this.checkAccessStatus();
                this.accessStatus = accessData.status;
                
                // If user is admin, grant access automatically
                if (accessData.is_admin) {
                    this.accessStatus = 'approved';
                }
            }
            
            // Update the UI based on auth state and access status
            this.updateUI();
            
            // Notify listeners of auth state
            this.notifyAuthStateChanged();
        } catch (error) {
            console.error('Failed to initialize authentication:', error);
            this.isAuthenticated = false;
            this.user = null;
        }
    }

    /**
     * Fetch the currently authenticated user
     * @returns {Promise<Object>} User data and authentication state
     */
    async fetchCurrentUser() {
        try {
            const response = await fetch(`${this.authEndpoint}/user`, {
                method: 'GET',
                credentials: 'include' // Include cookies for session
            });

            if (!response.ok) {
                return { authenticated: false, user: null };
            }

            return await response.json();
        } catch (error) {
            console.error('Error fetching current user:', error);
            return { authenticated: false, user: null };
        }
    }

    /**
     * Check the user's dashboard access status
     * @returns {Promise<Object>} Access status data
     */
    async checkAccessStatus() {
        try {
            const response = await fetch(`${this.authEndpoint}/access/status`, {
                method: 'GET',
                credentials: 'include'
            });
            
            if (!response.ok) {
                return { status: 'pending', is_admin: false };
            }
            
            return await response.json();
        } catch (error) {
            console.error('Error checking access status:', error);
            return { status: 'pending', is_admin: false };
        }
    }
    
    /**
     * Request dashboard access
     * @param {string} message Optional message for administrators
     * @returns {Promise<Object>} Request result
     */
    async requestAccess(message = '') {
        if (!this.isAuthenticated) {
            console.error('Cannot request access: Not authenticated');
            return { success: false, error: 'Not authenticated' };
        }
        
        try {
            const response = await fetch(`${this.authEndpoint}/access/request`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message }),
                credentials: 'include'
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                return { success: false, error: errorData.error || 'Failed to request access' };
            }
            
            const result = await response.json();
            this.accessStatus = 'requested';
            this.updateUI();
            return { success: true, ...result };
        } catch (error) {
            console.error('Error requesting access:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Fetch pending access requests (admin only)
     * @returns {Promise<Array>} List of pending requests
     */
    async getPendingAccessRequests() {
        if (!this.isAuthenticated || !this.user?.is_admin) {
            console.error('Cannot get access requests: Not admin');
            return [];
        }
        
        try {
            const response = await fetch(`${this.authEndpoint}/admin/access/requests`, {
                method: 'GET',
                credentials: 'include'
            });
            
            if (!response.ok) {
                console.error('Failed to get access requests:', response.status);
                return [];
            }
            
            const data = await response.json();
            return data.requests || [];
        } catch (error) {
            console.error('Error getting access requests:', error);
            return [];
        }
    }
    
    /**
     * Approve an access request (admin only)
     * @param {string} requestId Request ID to approve
     * @returns {Promise<boolean>} Success status
     */
    async approveAccessRequest(requestId) {
        if (!this.isAuthenticated || !this.user?.is_admin) {
            console.error('Cannot approve request: Not admin');
            return false;
        }
        
        try {
            const response = await fetch(`${this.authEndpoint}/admin/access/approve/${requestId}`, {
                method: 'POST',
                credentials: 'include'
            });
            
            if (!response.ok) {
                console.error('Failed to approve request:', response.status);
                return false;
            }
            
            return true;
        } catch (error) {
            console.error('Error approving request:', error);
            return false;
        }
    }
    
    /**
     * Deny an access request (admin only)
     * @param {string} requestId Request ID to deny
     * @returns {Promise<boolean>} Success status
     */
    async denyAccessRequest(requestId) {
        if (!this.isAuthenticated || !this.user?.is_admin) {
            console.error('Cannot deny request: Not admin');
            return false;
        }
        
        try {
            const response = await fetch(`${this.authEndpoint}/admin/access/deny/${requestId}`, {
                method: 'POST',
                credentials: 'include'
            });
            
            if (!response.ok) {
                console.error('Failed to deny request:', response.status);
                return false;
            }
            
            return true;
        } catch (error) {
            console.error('Error denying request:', error);
            return false;
        }
    }

    /**
     * Get the user's API key
     * @returns {String|null} API key if authenticated, null otherwise
     */
    getApiKey() {
        return this.isAuthenticated && this.user ? this.user.api_key : null;
    }

    /**
     * Generate a new API key for the authenticated user
     * @returns {Promise<string|null>} The new API key or null if failed
     */
    async regenerateApiKey() {
        if (!this.isAuthenticated) {
            console.error('Cannot regenerate API key: Not authenticated');
            return null;
        }

        try {
            const response = await fetch(`${this.authEndpoint}/user/api-key`, {
                method: 'PUT',
                credentials: 'include'
            });

            if (!response.ok) {
                console.error('Failed to regenerate API key:', response.status);
                return null;
            }

            const data = await response.json();
            if (data.success && data.api_key) {
                // Update the stored user object
                this.user.api_key = data.api_key;
                this.notifyAuthStateChanged();
                return data.api_key;
            }
            return null;
        } catch (error) {
            console.error('Error regenerating API key:', error);
            return null;
        }
    }

    /**
     * Login with Discord
     */
    login() {
        window.location.href = `${this.authEndpoint}/login`;
    }

    /**
     * Logout the current user
     */
    logout() {
        window.location.href = `${this.authEndpoint}/logout`;
    }

    /**
     * Add an auth state change listener
     * @param {Function} listener Callback function
     */
    addAuthStateListener(listener) {
        if (typeof listener === 'function' && !this.authListeners.includes(listener)) {
            this.authListeners.push(listener);
        }
    }

    /**
     * Remove an auth state change listener
     * @param {Function} listener Callback function to remove
     */
    removeAuthStateListener(listener) {
        const index = this.authListeners.indexOf(listener);
        if (index !== -1) {
            this.authListeners.splice(index, 1);
        }
    }

    /**
     * Notify listeners of auth state changes
     */
    notifyAuthStateChanged() {
        const authState = {
            isAuthenticated: this.isAuthenticated,
            user: this.user
        };

        this.authListeners.forEach(listener => {
            try {
                listener(authState);
            } catch (e) {
                console.error('Error in auth state listener:', e);
            }
        });
    }

    /**
     * Update UI based on authentication state
     */
    updateUI() {
        // Elements
        const loginPage = document.getElementById('login-page');
        const dashboardWrapper = document.getElementById('dashboard-wrapper');
        const pendingAccessPage = document.getElementById('pending-access-page');
        
        if (!this.isAuthenticated) {
            // User is not authenticated, show login page
            loginPage.style.display = 'flex';
            dashboardWrapper.style.display = 'none';
            if (pendingAccessPage) pendingAccessPage.style.display = 'none';
            return;
        }
        
        // User is authenticated, check access status
        if (this.accessStatus === 'approved' || this.user.is_admin) {
            // User has access, show dashboard
            loginPage.style.display = 'none';
            if (pendingAccessPage) pendingAccessPage.style.display = 'none';
            dashboardWrapper.style.display = 'flex';
            
            // Initialize the dashboard
            if (typeof initializeDashboard === 'function') {
                initializeDashboard();
            }
            
            // If user is admin, load pending access requests
            if (this.user.is_admin && typeof loadPendingAccessRequests === 'function') {
                loadPendingAccessRequests();
            }
        } else {
            // User does not have access, show pending page
            loginPage.style.display = 'none';
            dashboardWrapper.style.display = 'none';
            
            if (pendingAccessPage) {
                pendingAccessPage.style.display = 'flex';
                this.updatePendingAccessUI();
            } else {
                // Pending access page doesn't exist, create it
                this.createPendingAccessPage();
            }
        }
        
        // Update user profile in sidebar
        this.updateUserProfile();

        // Show/hide login/logout buttons
        this.updateAuthButtons();

        // Update settings page
        this.updateSettingsPage();
    }
    
    /**
     * Create the pending access page
     */
    createPendingAccessPage() {
        const pendingPage = document.createElement('div');
        pendingPage.id = 'pending-access-page';
        pendingPage.className = 'pending-access-container';
        pendingPage.style.display = 'flex';
        pendingPage.style.flexDirection = 'column';
        pendingPage.style.alignItems = 'center';
        pendingPage.style.justifyContent = 'center';
        pendingPage.style.height = '100vh';
        pendingPage.style.width = '100%';
        pendingPage.style.position = 'fixed';
        pendingPage.style.top = '0';
        pendingPage.style.left = '0';
        pendingPage.style.background = 'var(--background-color, #f8f9fa)';
        pendingPage.style.zIndex = '1000';
        
        // Create appropriate content based on status
        this.updatePendingAccessPageContent(pendingPage);
        
        // Add to the body
        document.body.appendChild(pendingPage);
    }
    
    /**
     * Update the pending access UI based on current status
     */
    updatePendingAccessUI() {
        const pendingPage = document.getElementById('pending-access-page');
        if (!pendingPage) return;
        
        this.updatePendingAccessPageContent(pendingPage);
    }
    
    /**
     * Update the content of the pending access page
     * @param {HTMLElement} container The container element
     */
    updatePendingAccessPageContent(container) {
        if (!container) return;
        
        // Get avatar URL
        const avatarUrl = this.user && this.user.avatar 
            ? `https://cdn.discordapp.com/avatars/${this.user.id}/${this.user.avatar}.png`
            : 'https://cdn.discordapp.com/embed/avatars/0.png';
        
        // Create content based on status
        let content = '';
        
        if (this.accessStatus === 'pending') {
            // User hasn't requested access yet
            content = `
                <div class="card" style="max-width: 500px; width: 90%;">
                    <div class="card-header text-center bg-primary text-white">
                        <h3>Dashboard Access Required</h3>
                    </div>
                    <div class="card-body text-center">
                        <img src="${avatarUrl}" alt="User Avatar" class="rounded-circle mb-3" style="width: 80px; height: 80px;">
                        <h4>Welcome, ${escapeHtml(this.user?.username || 'User')}</h4>
                        <p class="mb-4">You need to request access to use this dashboard.</p>
                        
                        <div class="mb-3">
                            <label for="access-request-message" class="form-label">Message (optional):</label>
                            <textarea class="form-control" id="access-request-message" rows="3" 
                                placeholder="Briefly explain why you need access to the dashboard..."></textarea>
                        </div>
                        
                        <button class="btn btn-primary btn-lg" id="request-access-btn">Request Access</button>
                    </div>
                </div>
            `;
        } else if (this.accessStatus === 'requested') {
            // User has requested access and is waiting
            content = `
                <div class="card" style="max-width: 500px; width: 90%;">
                    <div class="card-header text-center bg-warning text-dark">
                        <h3>Access Requested</h3>
                    </div>
                    <div class="card-body text-center">
                        <img src="${avatarUrl}" alt="User Avatar" class="rounded-circle mb-3" style="width: 80px; height: 80px;">
                        <h4>Thanks, ${escapeHtml(this.user?.username || 'User')}</h4>
                        <p>Your request for dashboard access has been submitted.</p>
                        <div class="alert alert-info">
                            <i class="fas fa-info-circle"></i> The administrator will review your request soon.
                            You'll receive a Discord notification when your request is approved or denied.
                        </div>
                        <button class="btn btn-outline-secondary mt-3" id="refresh-status-btn">Refresh Status</button>
                    </div>
                </div>
            `;
        } else if (this.accessStatus === 'denied') {
            // User's request was denied
            content = `
                <div class="card" style="max-width: 500px; width: 90%;">
                    <div class="card-header text-center bg-danger text-white">
                        <h3>Access Denied</h3>
                    </div>
                    <div class="card-body text-center">
                        <img src="${avatarUrl}" alt="User Avatar" class="rounded-circle mb-3" style="width: 80px; height: 80px;">
                        <h4>Sorry, ${escapeHtml(this.user?.username || 'User')}</h4>
                        <p>Your request for dashboard access has been denied.</p>
                        <div class="alert alert-secondary">
                            If you believe this is a mistake or want to appeal this decision,
                            please contact the administrator via Discord.
                        </div>
                        <button class="btn btn-outline-secondary mt-3" id="refresh-status-btn">Refresh Status</button>
                        <button class="btn btn-primary mt-3" id="request-access-again-btn">Request Again</button>
                    </div>
                </div>
            `;
        }
        
        // Update the container
        container.innerHTML = content;
        
        // Add event listeners
        this.setupPendingPageListeners();
    }
    
    /**
     * Set up event listeners for the pending access page
     */
    setupPendingPageListeners() {
        const requestBtn = document.getElementById('request-access-btn');
        const refreshBtn = document.getElementById('refresh-status-btn');
        const requestAgainBtn = document.getElementById('request-access-again-btn');
        
        // Request access button
        if (requestBtn) {
            requestBtn.addEventListener('click', async () => {
                const messageElem = document.getElementById('access-request-message');
                const message = messageElem ? messageElem.value : '';
                
                // Disable button and show loading
                requestBtn.disabled = true;
                requestBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Requesting...';
                
                // Send request
                const result = await this.requestAccess(message);
                
                if (result.success) {
                    // Update UI for requested state
                    this.accessStatus = 'requested';
                    this.updatePendingAccessUI();
                } else {
                    // Show error and re-enable button
                    alert(`Failed to request access: ${result.error}`);
                    requestBtn.disabled = false;
                    requestBtn.innerHTML = 'Request Access';
                }
            });
        }
        
        // Refresh status button
        if (refreshBtn) {
            refreshBtn.addEventListener('click', async () => {
                refreshBtn.disabled = true;
                refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Refreshing...';
                
                // Check status again
                const accessData = await this.checkAccessStatus();
                this.accessStatus = accessData.status;
                
                // Update UI
                this.updateUI();
            });
        }
        
        // Request again button
        if (requestAgainBtn) {
            requestAgainBtn.addEventListener('click', async () => {
                this.accessStatus = 'pending';
                this.updatePendingAccessUI();
            });
        }
    }

    /**
     * Update the user profile display in the sidebar
     */
    updateUserProfile() {
        const profileContainer = document.querySelector('.profile-container');
        if (!profileContainer) return;

        if (this.isAuthenticated && this.user) {
            // User is logged in, show their profile
            const avatarUrl = this.user.avatar 
                ? `https://cdn.discordapp.com/avatars/${this.user.id}/${this.user.avatar}.png` 
                : 'https://cdn.discordapp.com/embed/avatars/0.png';

            profileContainer.innerHTML = `
                <img src="${avatarUrl}" alt="User Avatar" class="user-avatar">
                <div class="user-info">
                    <h6 class="user-name">${escapeHtml(this.user.username)}</h6>
                    <small class="text-muted">${this.user.is_admin ? 'Administrator' : 'User'}</small>
                </div>
            `;
        } else {
            // User is not logged in, show login prompt
            profileContainer.innerHTML = `
                <div class="user-info">
                    <h6 class="user-name">Not logged in</h6>
                    <button class="btn btn-sm btn-primary" onclick="auth.login()">Login with Discord</button>
                </div>
            `;
        }
    }

    /**
     * Update authentication buttons in the sidebar
     */
    updateAuthButtons() {
        const loginBtn = document.getElementById('login-btn');
        const logoutBtn = document.getElementById('logout-btn');
        
        if (loginBtn) {
            loginBtn.style.display = this.isAuthenticated ? 'none' : 'block';
        }
        
        if (logoutBtn) {
            logoutBtn.style.display = this.isAuthenticated ? 'block' : 'none';
        }
    }

    /**
     * Update the settings page with user data
     */
    updateSettingsPage() {
        const apiKeyField = document.getElementById('api-key');
        const regenerateBtn = document.getElementById('regenerate-api-key');
        const userProfileSection = document.querySelector('.user-profile-section');
        
        if (!apiKeyField || !regenerateBtn || !userProfileSection) return;
        
        if (this.isAuthenticated && this.user) {
            // Update API key field
            apiKeyField.value = this.user.api_key;
            apiKeyField.readOnly = false;
            regenerateBtn.disabled = false;

            // Update user profile section
            const avatarUrl = this.user.avatar 
                ? `https://cdn.discordapp.com/avatars/${this.user.id}/${this.user.avatar}.png` 
                : 'https://cdn.discordapp.com/embed/avatars/0.png';

            userProfileSection.innerHTML = `
                <img src="${avatarUrl}" alt="User Avatar" class="settings-avatar">
                <div class="user-details">
                    <h4>${escapeHtml(this.user.username)}</h4>
                    <p>Discord ID: ${this.user.id}</p>
                    <p>${this.user.is_admin ? '<span class="badge bg-primary">Administrator</span>' : '<span class="badge bg-secondary">User</span>'}</p>
                </div>
            `;
        } else {
            // Clear API key field
            apiKeyField.value = '';
            apiKeyField.readOnly = true;
            regenerateBtn.disabled = true;

            // Update user profile section
            userProfileSection.innerHTML = `
                <div class="user-details">
                    <h4>Not logged in</h4>
                    <p>Please login with Discord to access your profile</p>
                    <button class="btn btn-primary" onclick="auth.login()">Login with Discord</button>
                </div>
            `;
        }
    }
}

// Create global auth instance
const auth = new Auth();

// Setup regenerate API key button
document.addEventListener('DOMContentLoaded', function() {
    const regenerateBtn = document.getElementById('regenerate-api-key');
    if (regenerateBtn) {
        regenerateBtn.addEventListener('click', async function() {
            if (!auth.isAuthenticated) {
                alert('Please login to regenerate your API key.');
                return;
            }

            if (confirm('Are you sure you want to regenerate your API key? This will invalidate your current key.')) {
                const newApiKey = await auth.regenerateApiKey();
                if (newApiKey) {
                    document.getElementById('api-key').value = newApiKey;
                    alert('API key regenerated successfully!');
                } else {
                    alert('Failed to regenerate API key.');
                }
            }
        });
    }

    // Initialize authentication system
    auth.initialize().then(() => {
        console.log('Authentication system initialized');
    });
});