document.addEventListener('DOMContentLoaded', function() {
    // Initialize wizardHandlers globally
    window.wizardHandlers = window.wizardHandlers || {};

    // Handle form submission
    const form = document.getElementById('prerequisitesForm');
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            // Get selected users
            const sourceUser = document.querySelector('input[name="source_user"]:checked');
            const targetUser = document.querySelector('input[name="target_user"]:checked');
            
            // Check if users are selected
            if (!sourceUser) {
                const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
                document.getElementById('errorMessage').textContent = 'Please select the source user before proceeding.';
                errorModal.show();
                return;
            }

            try {
                // Create form data
                const formData = new FormData();
                formData.append('action', 'validate_prerequisites');
                formData.append('source_user', sourceUser.value);
                if (targetUser) {
                    formData.append('target_user', targetUser.value);
                }
                formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

                const response = await fetch(form.action, {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    // Use the next_step URL from the response if provided
                    const nextStepUrl = data.next_step || '/djsql/replication/setup/3/';
                    window.location.href = nextStepUrl;
                } else {
                    throw new Error(data.message || 'Failed to validate prerequisites');
                }
            } catch (error) {
                const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
                document.getElementById('errorMessage').textContent = error.message;
                errorModal.show();
            }
        });
    }

    // Handle back button
    const backBtn = document.getElementById('backBtn');
    if (backBtn) {
        backBtn.addEventListener('click', function() {
            window.location.href = '/djsql/replication/setup/1/';
        });
    }

    // Define the openCreateSqlUserModal function
    wizardHandlers.openCreateSqlUserModal = async function(serverId, serverType) {
        // Get the modal element
        const modalEl = document.getElementById('createSqlUserModal');
        const modal = new bootstrap.Modal(modalEl);
        
        // Clear previous values
        modalEl.querySelector('#newSqlUsername').value = '';
        modalEl.querySelector('#newSqlPassword').value = '';
        modalEl.querySelector('#newSqlHost').value = '%';  // default host can be '%'
        modalEl.querySelector('#createUserAlert').classList.add('d-none');  // hide any previous alerts
        
        modal.show();

        // Setup the submit handler
        const submitBtn = modalEl.querySelector('#submitNewSqlUser');
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Create User';

        submitBtn.onclick = async () => {
            const username = modalEl.querySelector('#newSqlUsername').value.trim();
            const password = modalEl.querySelector('#newSqlPassword').value.trim();
            const host = modalEl.querySelector('#newSqlHost').value.trim();
            
            if (!username || !password || !host) {
                alert("Please provide all required fields (username, password, host).");
                return;
            }

            // Set privileges based on server type
            const privileges = serverType === 'source' 
                ? 'REPLICATION SLAVE, REPLICATION CLIENT'  // for source/master
                : 'REPLICATION CLIENT';  // for target/slave
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Creating...';
            
            try {
                // Log password length before sending
                console.log('Password length before sending:', password.length);
                
                const formData = new FormData();
                formData.append('action', 'create_sql_user');
                formData.append('server_id', serverId);
                formData.append('username', username);
                formData.append('password', password);
                formData.append('host', host);
                formData.append('privileges', privileges);
                formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

                // Log form data before sending
                console.log('Form data entries:', Array.from(formData.entries()));
                
                const response = await fetch('/djsql/replication/setup/2/', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    // Hide modal immediately and refresh the page content after a short delay
                    modal.hide();
                    setTimeout(() => {
                        // Fetch updated data
                        window.location.reload();
                    }, 1000);
                } else {
                    const alertEl = modalEl.querySelector('#createUserAlert');
                    alertEl.className = 'alert alert-danger';
                    alertEl.innerHTML = `
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        Error: ${data.message}
                    `;
                    alertEl.classList.remove('d-none');
                }
            } catch (error) {
                const alertEl = modalEl.querySelector('#createUserAlert');
                alertEl.className = 'alert alert-danger';
                alertEl.innerHTML = `
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Error: ${error.message}
                `;
                alertEl.classList.remove('d-none');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = 'Create User';
            }
        };
    };

    // Handle Check Privileges button clicks
    document.querySelectorAll('.check-privileges-btn').forEach(button => {
        button.addEventListener('click', async function() {
            const serverId = this.dataset.serverId;
            const username = this.dataset.user;
            const host = this.dataset.host;
            
            // Show check privileges modal
            const modal = new bootstrap.Modal(document.getElementById('checkPrivilegesModal'));
            document.getElementById('grantsOutput').textContent = 'Loading...';
            modal.show();
            
            try {
                const formData = new FormData();
                formData.append('action', 'check_grants');
                formData.append('server_id', serverId);
                formData.append('username', username);
                formData.append('host', host);
                formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

                const response = await fetch('/djsql/replication/setup/2/', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    document.getElementById('grantsOutput').textContent = data.grants.join('\n');
                } else {
                    throw new Error(data.message || 'Failed to check privileges');
                }
            } catch (error) {
                document.getElementById('grantsOutput').textContent = `Error: ${error.message}`;
            }
        });
    });

    // Handle Grant Privileges button clicks
    document.querySelectorAll('.grant-privileges-btn').forEach(button => {
        button.addEventListener('click', async function() {
            const serverId = this.dataset.serverId;
            const username = this.dataset.user;
            const host = this.dataset.host;
            const missingPrivs = this.dataset.missingPrivs.split(',');
            
            // Show grant privileges modal
            const modal = new bootstrap.Modal(document.getElementById('grantPrivilegesModal'));
            const sqlCommand = `GRANT ${missingPrivs.join(', ')} ON *.* TO '${username}'@'${host}';`;
            document.getElementById('sqlCommand').value = sqlCommand;
            document.getElementById('grantCommandOutput').classList.add('d-none');
            modal.show();
            
            // Handle Execute Command button click
            document.getElementById('executeGrantBtn').onclick = async () => {
                const commandOutput = document.getElementById('commandOutput');
                const executeBtn = document.getElementById('executeGrantBtn');
                const modifiedSql = document.getElementById('sqlCommand').value;
                
                executeBtn.disabled = true;
                executeBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Executing...';
                
                try {
                    const formData = new FormData();
                    formData.append('action', 'execute_sql');
                    formData.append('server_id', serverId);
                    formData.append('sql_command', modifiedSql);
                    formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

                    const response = await fetch('/djsql/replication/setup/2/', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    document.getElementById('grantCommandOutput').classList.remove('d-none');
                    
                    if (data.status === 'success') {
                        commandOutput.textContent = data.output || 'Command executed successfully';
                        // Hide modal after a short delay and refresh the page
                        setTimeout(() => {
                            bootstrap.Modal.getInstance(document.getElementById('grantPrivilegesModal')).hide();
                            // Fetch updated data
                            window.location.reload();
                        }, 1000);
                    } else {
                        commandOutput.textContent = `Error: ${data.message}\n${data.output || ''}`;
                    }
                } catch (error) {
                    commandOutput.textContent = `Error: ${error.message}`;
                } finally {
                    executeBtn.disabled = false;
                    executeBtn.innerHTML = '<i class="bi bi-play-fill me-1"></i>Execute Command';
                }
            };
        });
    });

    // Handle Delete User button clicks
    document.querySelectorAll('.delete-user-btn').forEach(button => {
        button.addEventListener('click', function() {
            const serverId = this.dataset.serverId;
            const username = this.dataset.user;
            const host = this.dataset.host;
            
            // Show delete confirmation modal
            const modalEl = document.getElementById('deleteUserModal');
            if (!modalEl) {
                console.error('Delete modal element not found');
                return;
            }
            
            // Get existing modal instance or create new one
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            
            // Set the username in the confirmation message
            const userNameEl = modalEl.querySelector('#deleteUserName');
            if (userNameEl) {
                userNameEl.textContent = `'${username}'@'${host}'`;
            }
            
            // Setup the confirm button handler
            const confirmBtn = modalEl.querySelector('#confirmDeleteUser');
            if (confirmBtn) {
                confirmBtn.onclick = async () => {
                    confirmBtn.disabled = true;
                    confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Deleting...';
                    
                    try {
                        const formData = new FormData();
                        formData.append('action', 'delete_sql_user');
                        formData.append('server_id', serverId);
                        formData.append('username', username);
                        formData.append('host', host);
                        formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

                        const response = await fetch('/djsql/replication/setup/2/', {
                            method: 'POST',
                            body: formData
                        });
                        
                        const data = await response.json();
                        
                        if (data.status === 'success') {
                            // Hide modal and refresh page
                            modal.hide();
                            window.location.reload();
                        } else {
                            throw new Error(data.message || 'Failed to delete user');
                        }
                    } catch (error) {
                        alert(`Error deleting user: ${error.message}`);
                    } finally {
                        confirmBtn.disabled = false;
                        confirmBtn.innerHTML = 'Delete User';
                    }
                };
            }
            
            modal.show();
        });
    });
});
