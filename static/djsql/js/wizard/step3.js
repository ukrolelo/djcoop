document.addEventListener('DOMContentLoaded', function() {
    // Get elements
    const form = document.getElementById('databaseSelectForm');
    const databaseSelect = document.getElementById('sourceDatabase');
    const sourceCommandTextarea = document.getElementById('sourceCommand');
    const targetCommandTextarea = document.getElementById('targetCommand');
    const transferCommandPre = document.getElementById('transferCommand');
    const sendSourceBtn = document.getElementById('sendSourceCommand');
    const sendTargetBtn = document.getElementById('sendTargetCommand');
    const transferBtn = document.getElementById('transferData');
    const sourceOutput = document.getElementById('sourceCommandOutput');
    const targetOutput = document.getElementById('targetCommandOutput');
    const transferOutput = document.getElementById('transferOutput');

    // Check if required elements exist
    if (!databaseSelect || !sourceCommandTextarea || !targetCommandTextarea || !transferCommandPre) {
        console.error('Required elements not found');
        return;
    }
    
    // Initially disable transfer and target buttons
    transferBtn.disabled = true;
    sendTargetBtn.disabled = true;

    // Generate SQL commands when database selection changes
    databaseSelect.addEventListener('change', async function() {
        const selectedDb = this.value;
        console.log('Database selection changed:', selectedDb);
        
        if (selectedDb) {
            try {
                // First, get binary log information
                const response = await fetch('/djsql/replication/setup/3/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    },
                    body: JSON.stringify({
                        action: 'get_master_status',
                        database: selectedDb
                    })
                });

                const data = await response.json();
                if (data.status === 'success') {
                    // Get server details from select element
                    const sourceHost = databaseSelect.dataset.sourceHost;
                    const sourcePort = databaseSelect.dataset.sourcePort;
                    const sourceUser = databaseSelect.dataset.sourceUser;
                    
                    // Get commands from backend to ensure correct commands and password
                    const commandsResponse = await fetch('/djsql/replication/setup/3/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                        },
                        body: JSON.stringify({
                            action: 'generate_commands',
                            database: selectedDb
                        })
                    });

                    const commandsData = await commandsResponse.json();
                    if (commandsData.status !== 'success') {
                        throw new Error(commandsData.message || 'Failed to generate commands');
                    }

                    // Debug log the response and set commands from backend
                    console.log('Response from generate_commands:', commandsData);
                    
                    // Set source and target commands from backend, converting to single line
                    sourceCommandTextarea.value = (commandsData.source_commands || '').replace(/\n/g, ' ').replace(/  +/g, ' ').trim();
                    targetCommandTextarea.value = (commandsData.target_commands || '').replace(/\n/g, ' ').replace(/  +/g, ' ').trim();
                    
                    // Enable both buttons since we have both command sets
                    sendSourceBtn.disabled = false;
                    sendTargetBtn.disabled = false;
                } else {
                    throw new Error(data.message || 'Failed to get master status');
                }
            } catch (error) {
                showError(error.message);
                sourceCommandTextarea.value = '';
                targetCommandTextarea.value = '';
            }
        } else {
            sourceCommandTextarea.value = '';
            targetCommandTextarea.value = '';
        }
    });

    // Handle source command button
    sendSourceBtn.addEventListener('click', async function() {
        const selectedDb = databaseSelect.value;
        const command = sourceCommandTextarea.value;

        if (!selectedDb || !command) {
            showError('Please select a database first');
            return;
        }

        await executeCommand(this, sourceOutput, 'source', selectedDb, command);
    });

    // Handle data transfer button
    transferBtn.addEventListener('click', async function() {
        const selectedDb = databaseSelect.value;
        if (!selectedDb) {
            showError('Please select a database first');
            return;
        }

        const btn = this;
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Transferring Data...';

        try {
            const response = await fetch('/djsql/replication/setup/3/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify({
                    action: 'transfer_data',
                    database: selectedDb
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                transferOutput.className = 'alert alert-success mt-3';
                transferOutput.innerHTML = `
                    <div class="d-flex align-items-center mb-2">
                        <i class="bi bi-check-circle-fill text-success me-2"></i>
                        <strong>Database Transfer Complete</strong>
                    </div>
                    <p class="mb-2">
                        The database has been successfully transferred from source to target server.
                        You can now proceed with configuring replication on the target server.
                    </p>
                    ${data.output ? `
                        <div class="mt-3 border-top pt-3">
                            <small class="text-muted d-block mb-1">Command Output:</small>
                            <pre class="mb-0 bg-light p-2 rounded" style="font-size: 0.875rem;">${data.output}</pre>
                        </div>
                    ` : ''}
                `;
                transferOutput.classList.remove('d-none');
                
                // Enable target execution button
                sendTargetBtn.disabled = false;
            } else {
                throw new Error(data.message || 'Failed to transfer database');
            }
        } catch (error) {
            transferOutput.className = 'alert alert-danger mt-3';
            transferOutput.innerHTML = `
                <i class="bi bi-exclamation-triangle me-2"></i>
                ${error.message}
            `;
            transferOutput.classList.remove('d-none');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    });

    // Handle target command button
    sendTargetBtn.addEventListener('click', async function() {
        const selectedDb = databaseSelect.value;
        const command = targetCommandTextarea.value;

        if (!selectedDb || !command) {
            showError('Please select a database first');
            return;
        }

        await executeSlaveCommands(this, targetOutput, selectedDb);
    });

    async function executeSlaveCommands(button, output, database) {
        const originalText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Executing...';

        try {
            const response = await fetch('/djsql/replication/setup/3/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify({
                    action: 'execute_slave_commands',
                    database: database
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                output.className = 'alert alert-success mt-3';
                output.innerHTML = 'Commands executed successfully.';
                output.classList.remove('d-none');
            } else {
                throw new Error(data.message || 'Failed to execute command');
            }
        } catch (error) {
            output.className = 'alert alert-danger mt-3';
            output.innerHTML = `
                <i class="bi bi-exclamation-triangle me-2"></i>
                ${error.message}
            `;
            output.classList.remove('d-none');
        } finally {
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }

    // Execute command helper function
    async function executeCommand(button, output, server, database, command) {
        const originalText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Executing...';

        try {
            const response = await fetch('/djsql/replication/setup/3/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify({
                    action: 'execute_command',
                    server: server,
                    database: database,
                    command: command
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                const commandOutputDiv = document.getElementById('command-output');
                commandOutputDiv.innerHTML = `<pre>${data.raw_output}</pre>`;
                output.className = 'alert alert-success mt-3';
                output.innerHTML = 'Commands executed successfully. See raw output below.';
                output.classList.remove('d-none');

                // If this was source command execution, enable transfer button
                if (server === 'source' && data.master_status) {
                    transferBtn.disabled = false;
                    sendTargetBtn.disabled = false;
                    
                    console.log('Master status received:', data.master_status);
                    
                    // No need to fetch commands again - we already have them
                    // Just ensure target commands are properly displayed
                    if (targetCommandTextarea.value) {
                        console.log('Target commands already loaded');
                    } else {
                        console.error('Target commands not loaded');
                        showError('Target commands not loaded - please refresh the page');
                    }
                    
                    // Get server details from select element
                    const sourceHost = databaseSelect.dataset.sourceHost || 'source_host';
                    const sourcePort = databaseSelect.dataset.sourcePort || '3306';
                    const sourceUser = databaseSelect.dataset.sourceUser || 'repl_user';
                    const targetHost = databaseSelect.dataset.targetHost || 'target_host';
                    const targetPort = databaseSelect.dataset.targetPort || '3306';
                    const targetUser = databaseSelect.dataset.targetUser || 'repl_user';
                    const selectedDb = databaseSelect.value;
                    
                    // Generate transfer command
                    const transferCmd = [
                        `# Step 1: Export from source server (${sourceHost}:${sourcePort})`,
                        `mysqldump -h ${sourceHost} \\`,
                        `          -P ${sourcePort} \\`,
                        `          -u ${sourceUser} \\`,
                        `          -p'<source_password>' \\`,
                        `          --single-transaction \\`,  // For consistent backup
                        `          --set-gtid-purged=OFF \\`, // Skip GTID info
                        `          --triggers \\`,           // Include triggers
                        `          --routines \\`,          // Include stored procedures/functions
                        `          --events \\`,            // Include events
                        `          ${selectedDb} \\`,
                        ``,
                        `  # Step 2: Import into target server (${targetHost}:${targetPort})`,
                        `  | mysql -h ${targetHost} \\`,
                        `          -P ${targetPort} \\`,
                        `          -u ${targetUser} \\`,
                        `          -p'<target_password>' \\`,
                        `          ${selectedDb}`,
                        ``,
                        `# Note: Replace <source_password> and <target_password> with actual passwords`,
                    ].join('\n');
                    
                    // Show the transfer section
                    const transferSection = document.querySelector('.data-transfer-section');
                    if (transferSection) {
                        transferSection.classList.remove('d-none');
                        transferSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                    transferCommandPre.textContent = transferCmd;
                    transferCommandPre.parentElement.classList.remove('d-none');
                }
            } else {
                throw new Error(data.message || 'Failed to execute command');
            }
        } catch (error) {
            output.className = 'alert alert-danger mt-3';
            output.innerHTML = `
                <i class="bi bi-exclamation-triangle me-2"></i>
                ${error.message}
            `;
            output.classList.remove('d-none');
        } finally {
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }

    // Handle form submission (Next button)
    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        const selectedDb = databaseSelect.value;
        if (!selectedDb) {
            showError('Please select a database first');
            return;
        }

        try {
            const response = await fetch('/djsql/replication/setup/3/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify({
                    action: 'save_selection',
                    database: selectedDb
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                window.location.href = '/djsql/replication/setup/4/';
            } else {
                throw new Error(data.message || 'Failed to save database selection');
            }
        } catch (error) {
            showError(error.message);
        }
    });

    function showError(message) {
        const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
        document.getElementById('errorMessage').textContent = message;
        errorModal.show();
    }
});
