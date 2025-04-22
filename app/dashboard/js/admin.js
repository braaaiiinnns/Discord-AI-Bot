/**
 * Admin functionality for Discord Bot Dashboard
 * Handles user management and access request approval
 */

// Load pending access requests when the admin page is shown
function loadPendingAccessRequests() {
    if (!auth || !auth.isAuthenticated || !auth.user?.is_admin) {
        console.warn('Cannot load access requests: Not admin');
        return;
    }
    
    const container = document.getElementById('pending-requests-container');
    const noRequestsMessage = document.getElementById('no-pending-requests');
    
    if (!container || !noRequestsMessage) return;
    
    // Show loading state
    container.innerHTML = `
        <div class="text-center p-3">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2">Loading pending requests...</p>
        </div>
    `;
    
    // Fetch pending requests
    auth.getPendingAccessRequests().then(requests => {
        if (!requests || requests.length === 0) {
            container.innerHTML = '';
            noRequestsMessage.style.display = 'block';
            return;
        }
        
        // Hide no requests message
        noRequestsMessage.style.display = 'none';
        
        // Create request cards
        const requestsHtml = requests.map(request => {
            const avatarUrl = request.avatar 
                ? `https://cdn.discordapp.com/avatars/${request.user_id}/${request.avatar}.png` 
                : 'https://cdn.discordapp.com/embed/avatars/0.png';
            
            const requestTime = moment(request.created_at * 1000).format('MMM D, YYYY h:mm A');
            
            return `
                <div class="card mb-3 request-card" data-request-id="${request.id}">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${escapeHtml(request.username)}</strong>
                            <span class="text-muted">#${request.discriminator || '0000'}</span>
                        </div>
                        <span class="badge bg-warning">Pending</span>
                    </div>
                    <div class="card-body">
                        <div class="d-flex mb-3">
                            <img src="${avatarUrl}" alt="User Avatar" 
                                class="rounded-circle me-3" style="width: 50px; height: 50px;">
                            <div>
                                <p><strong>User ID:</strong> ${request.user_id}</p>
                                <p><strong>Requested:</strong> ${requestTime}</p>
                                ${request.email ? `<p><strong>Email:</strong> ${escapeHtml(request.email)}</p>` : ''}
                            </div>
                        </div>
                        
                        ${request.message ? `
                            <div class="alert alert-secondary">
                                <strong>Message:</strong><br>
                                ${escapeHtml(request.message)}
                            </div>
                        ` : ''}
                        
                        <div class="d-flex justify-content-end gap-2 mt-3">
                            <button class="btn btn-danger btn-sm deny-request-btn">
                                <i class="fas fa-times"></i> Deny
                            </button>
                            <button class="btn btn-success btn-sm approve-request-btn">
                                <i class="fas fa-check"></i> Approve
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = requestsHtml;
        
        // Add event listeners to buttons
        setupRequestButtonListeners();
    }).catch(error => {
        console.error('Error loading access requests:', error);
        container.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-circle"></i> Failed to load access requests.
                <button class="btn btn-outline-danger btn-sm ms-2" onclick="loadPendingAccessRequests()">
                    Retry
                </button>
            </div>
        `;
    });
}

// Set up event listeners for approve/deny buttons
function setupRequestButtonListeners() {
    // Approve buttons
    document.querySelectorAll('.approve-request-btn').forEach(btn => {
        btn.addEventListener('click', async function() {
            const card = this.closest('.request-card');
            const requestId = card.getAttribute('data-request-id');
            
            if (!requestId) return;
            
            // Disable buttons and show loading
            const buttons = card.querySelectorAll('button');
            buttons.forEach(b => b.disabled = true);
            
            this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Approving...';
            
            try {
                // Approve the request
                const success = await auth.approveAccessRequest(requestId);
                
                if (success) {
                    // Show success message
                    card.classList.add('border-success');
                    card.querySelector('.card-body').innerHTML = `
                        <div class="alert alert-success">
                            <i class="fas fa-check-circle"></i> Access request approved successfully!
                        </div>
                    `;
                    
                    // Update badge
                    card.querySelector('.badge').classList.remove('bg-warning');
                    card.querySelector('.badge').classList.add('bg-success');
                    card.querySelector('.badge').textContent = 'Approved';
                    
                    // Remove after a delay
                    setTimeout(() => {
                        card.style.opacity = '0';
                        setTimeout(() => {
                            card.remove();
                            
                            // Check if there are no more requests
                            if (document.querySelectorAll('.request-card').length === 0) {
                                document.getElementById('no-pending-requests').style.display = 'block';
                            }
                        }, 500);
                    }, 2000);
                } else {
                    // Show error message
                    this.innerHTML = '<i class="fas fa-check"></i> Approve';
                    buttons.forEach(b => b.disabled = false);
                    
                    alert('Failed to approve the access request. Please try again.');
                }
            } catch (error) {
                console.error('Error approving request:', error);
                this.innerHTML = '<i class="fas fa-check"></i> Approve';
                buttons.forEach(b => b.disabled = false);
                
                alert('An error occurred while approving the request. Please try again.');
            }
        });
    });
    
    // Deny buttons
    document.querySelectorAll('.deny-request-btn').forEach(btn => {
        btn.addEventListener('click', async function() {
            const card = this.closest('.request-card');
            const requestId = card.getAttribute('data-request-id');
            
            if (!requestId) return;
            
            if (!confirm('Are you sure you want to deny this access request?')) {
                return;
            }
            
            // Disable buttons and show loading
            const buttons = card.querySelectorAll('button');
            buttons.forEach(b => b.disabled = true);
            
            this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Denying...';
            
            try {
                // Deny the request
                const success = await auth.denyAccessRequest(requestId);
                
                if (success) {
                    // Show success message
                    card.classList.add('border-danger');
                    card.querySelector('.card-body').innerHTML = `
                        <div class="alert alert-danger">
                            <i class="fas fa-times-circle"></i> Access request denied.
                        </div>
                    `;
                    
                    // Update badge
                    card.querySelector('.badge').classList.remove('bg-warning');
                    card.querySelector('.badge').classList.add('bg-danger');
                    card.querySelector('.badge').textContent = 'Denied';
                    
                    // Remove after a delay
                    setTimeout(() => {
                        card.style.opacity = '0';
                        setTimeout(() => {
                            card.remove();
                            
                            // Check if there are no more requests
                            if (document.querySelectorAll('.request-card').length === 0) {
                                document.getElementById('no-pending-requests').style.display = 'block';
                            }
                        }, 500);
                    }, 2000);
                } else {
                    // Show error message
                    this.innerHTML = '<i class="fas fa-times"></i> Deny';
                    buttons.forEach(b => b.disabled = false);
                    
                    alert('Failed to deny the access request. Please try again.');
                }
            } catch (error) {
                console.error('Error denying request:', error);
                this.innerHTML = '<i class="fas fa-times"></i> Deny';
                buttons.forEach(b => b.disabled = false);
                
                alert('An error occurred while denying the request. Please try again.');
            }
        });
    });
}

// Load all users for the admin page
function loadAllUsers() {
    if (!auth || !auth.isAuthenticated || !auth.user?.is_admin) {
        console.warn('Cannot load users: Not admin');
        return;
    }
    
    const tableBody = document.getElementById('users-table-body');
    
    if (!tableBody) return;
    
    // Show loading state
    tableBody.innerHTML = `
        <tr>
            <td colspan="5" class="text-center">
                <div class="spinner-border spinner-border-sm text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                Loading users...
            </td>
        </tr>
    `;
    
    // Fetch all users
    fetch(`${DashboardConfig.apiBaseUrl}/auth/admin/users`, {
        method: 'GET',
        credentials: 'include'
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Failed to fetch users: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (!data.users || data.users.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center">No users found.</td>
                </tr>
            `;
            return;
        }
        
        // Create user rows
        const usersHtml = data.users.map(user => {
            const avatarUrl = user.avatar 
                ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png`
                : 'https://cdn.discordapp.com/embed/avatars/0.png';
            
            return `
                <tr data-user-id="${user.id}">
                    <td>
                        <div class="d-flex align-items-center">
                            <img src="${avatarUrl}" alt="User Avatar" 
                                class="rounded-circle me-2" style="width: 32px; height: 32px;">
                            <div>
                                <strong>${escapeHtml(user.username)}</strong>
                                ${user.discriminator ? `<span class="text-muted">#${user.discriminator}</span>` : ''}
                            </div>
                        </div>
                    </td>
                    <td>${user.id}</td>
                    <td>
                        <span class="badge ${getBadgeClass(user.access_status || 'pending')}">
                            ${user.access_status || 'Pending'}
                        </span>
                    </td>
                    <td>
                        <div class="form-check form-switch">
                            <input class="form-check-input admin-toggle" type="checkbox" 
                                ${user.is_admin ? 'checked' : ''}
                                ${user.id === auth.user.id ? 'disabled' : ''}>
                        </div>
                    </td>
                    <td>
                        <div class="btn-group">
                            <button class="btn btn-sm btn-outline-primary dropdown-toggle" type="button" 
                                data-bs-toggle="dropdown" aria-expanded="false">
                                Actions
                            </button>
                            <ul class="dropdown-menu">
                                <li><a class="dropdown-item set-access-status" data-status="approved" href="#">
                                    <i class="fas fa-check text-success"></i> Approve Access
                                </a></li>
                                <li><a class="dropdown-item set-access-status" data-status="denied" href="#">
                                    <i class="fas fa-times text-danger"></i> Deny Access
                                </a></li>
                                <li><a class="dropdown-item set-access-status" data-status="pending" href="#">
                                    <i class="fas fa-clock text-warning"></i> Reset to Pending
                                </a></li>
                                <li><hr class="dropdown-divider"></li>
                                <li><a class="dropdown-item text-danger reset-api-key" href="#">
                                    <i class="fas fa-key"></i> Reset API Key
                                </a></li>
                            </ul>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
        
        tableBody.innerHTML = usersHtml;
        
        // Add event listeners
        setupUserTableListeners();
    })
    .catch(error => {
        console.error('Error loading users:', error);
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-danger">
                    <i class="fas fa-exclamation-circle"></i> Failed to load users.
                    <button class="btn btn-outline-danger btn-sm ms-2" onclick="loadAllUsers()">
                        Retry
                    </button>
                </td>
            </tr>
        `;
    });
}

// Set up event listeners for user table actions
function setupUserTableListeners() {
    // Admin toggle switches
    document.querySelectorAll('.admin-toggle').forEach(toggle => {
        toggle.addEventListener('change', function() {
            const userId = this.closest('tr').getAttribute('data-user-id');
            if (!userId) return;
            
            if (userId === auth.user.id) {
                // Don't allow changing own admin status
                this.checked = true;
                return;
            }
            
            const isAdmin = this.checked;
            
            // Disable toggle temporarily
            this.disabled = true;
            
            // Update admin status
            fetch(`${DashboardConfig.apiBaseUrl}/auth/admin/users/${userId}/admin`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ is_admin: isAdmin }),
                credentials: 'include'
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Failed to update admin status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Success - leave toggle in new state
                } else {
                    // Revert toggle
                    this.checked = !isAdmin;
                }
            })
            .catch(error => {
                console.error('Error updating admin status:', error);
                // Revert toggle
                this.checked = !isAdmin;
                alert('Failed to update admin status. Please try again.');
            })
            .finally(() => {
                // Re-enable toggle
                this.disabled = false;
            });
        });
    });
    
    // Access status dropdown items
    document.querySelectorAll('.set-access-status').forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            
            const userId = this.closest('tr').getAttribute('data-user-id');
            if (!userId) return;
            
            const status = this.getAttribute('data-status');
            if (!status) return;
            
            // Update the user's access status
            fetch(`${DashboardConfig.apiBaseUrl}/auth/admin/users/${userId}/access-status`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ status }),
                credentials: 'include'
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Failed to update access status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Update the badge in the table
                    const badgeCell = this.closest('tr').querySelector('td:nth-child(3)');
                    if (badgeCell) {
                        badgeCell.innerHTML = `
                            <span class="badge ${getBadgeClass(status)}">
                                ${status}
                            </span>
                        `;
                    }
                }
            })
            .catch(error => {
                console.error('Error updating access status:', error);
                alert('Failed to update access status. Please try again.');
            });
        });
    });
    
    // Reset API key buttons
    document.querySelectorAll('.reset-api-key').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            
            const userId = this.closest('tr').getAttribute('data-user-id');
            if (!userId) return;
            
            if (!confirm('Are you sure you want to reset this user\'s API key? This action cannot be undone.')) {
                return;
            }
            
            // Reset the user's API key
            fetch(`${DashboardConfig.apiBaseUrl}/auth/admin/users/${userId}/api-key/reset`, {
                method: 'POST',
                credentials: 'include'
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Failed to reset API key: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    alert('API key has been reset successfully.');
                }
            })
            .catch(error => {
                console.error('Error resetting API key:', error);
                alert('Failed to reset API key. Please try again.');
            });
        });
    });
}

// Helper function to get the appropriate badge class for an access status
function getBadgeClass(status) {
    switch (status) {
        case 'approved':
            return 'bg-success';
        case 'denied':
            return 'bg-danger';
        case 'requested':
            return 'bg-warning text-dark';
        case 'pending':
        default:
            return 'bg-secondary';
    }
}

// Set up refresh button
document.addEventListener('DOMContentLoaded', function() {
    const refreshUsersBtn = document.getElementById('refresh-users-btn');
    if (refreshUsersBtn) {
        refreshUsersBtn.addEventListener('click', loadAllUsers);
    }
    
    // Add navigation hook
    if (typeof addPageNavigationHook === 'function') {
        addPageNavigationHook('admin', () => {
            loadPendingAccessRequests();
            loadAllUsers();
        });
    }
});