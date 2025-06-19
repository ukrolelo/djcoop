const wizardHandlers = {
    init: function() {
        console.log('Initializing replication wizard...');
        // Initialize wizard functionality
        this.setupEventListeners();
        this.updateNavigation();
    },
    
    setupEventListeners: function() {
        // Setup event listeners for wizard navigation
        document.querySelectorAll('.wizard-next-btn').forEach(btn => {
            btn.addEventListener('click', () => this.nextStep());
        });
        
        document.querySelectorAll('.wizard-prev-btn').forEach(btn => {
            btn.addEventListener('click', () => this.prevStep());
        });
        
        // Add other event listeners as needed
    },
    
    nextStep: function() {
        if (this.selections.currentStep < 4) {
            this.selections.currentStep++;
            this.updateNavigation();
        }
    },
    
    prevStep: function() {
        if (this.selections.currentStep > 1) {
            this.selections.currentStep--;
            this.updateNavigation();
        }
    },
    
    updateNavigation: function() {
        // Update UI to show current step
        document.querySelectorAll('.wizard-step').forEach((step, index) => {
            step.classList.toggle('active', index + 1 === this.selections.currentStep);
            step.classList.toggle('d-none', index + 1 !== this.selections.currentStep);
        });
        
        // Update progress indicators
        document.querySelectorAll('.progress-step').forEach((step, index) => {
            step.classList.toggle('active', index + 1 <= this.selections.currentStep);
        });
    },
    
    selections: {
        source: null,
        target: null,
        currentStep: 1
    },

    // ... [keep all existing methods unchanged until loadReplicationDetails]

    loadReplicationDetails: async function(linkId) {
        const spinner = document.getElementById('replicationDetailsSpinner');
        const modal = document.getElementById('replicationDetailsModal');
        const errorDiv = document.getElementById('replicationError');
        const detailsDiv = document.getElementById('replicationDetails');
        
        console.log('[DEBUG] Starting loadReplicationDetails for linkId:', linkId);
        
        // Reset states
        errorDiv.classList.add('d-none');
        detailsDiv.classList.add('d-none');
        spinner.classList.remove('d-none');
        modal.querySelector('.modal-body').classList.remove('d-none');
        
        console.log('[DEBUG] Spinner shown, details hidden');
        
        // Add event listener for refresh button
        const refreshBtn = document.getElementById('refreshDetailsBtn');
        if (refreshBtn) {
            refreshBtn.onclick = () => this.loadReplicationDetails(linkId);
        }
        
        try {
            const response = await fetch(`/dashboard/api/replication/${linkId}/status/`);
            const data = await response.json();
            console.log('Raw API response data:', data);
            
            if (data.status === 'success') {
                // Update status information
                console.log('Replication status:', data.replication.status);
                document.getElementById('replStatus').textContent = data.replication.status;
                console.log('Replication lag (seconds):', data.replication.lag_seconds);
                document.getElementById('replLag').textContent = `${data.replication.lag_seconds}s`;
                document.getElementById('replDatabases').textContent = (data.replication.databases || []).join(', ');
                document.getElementById('replUser').textContent = data.replication.user;
                document.getElementById('replError').textContent = data.replication.last_error || 'None';
                
                // Add source and target server information with robust fallbacks
                const sourceHost = document.getElementById('sourceHost');
                const sourcePort = document.getElementById('sourcePort');
                const sourceUser = document.getElementById('sourceUser');
                const sourceBinlog = document.getElementById('sourceBinlog');
                const targetHost = document.getElementById('targetHost');
                const targetPort = document.getElementById('targetPort');
                
                // Source server info
                if (data.replication.source) {
                    sourceHost.textContent = data.replication.source.host || 'N/A';
                    sourcePort.textContent = data.replication.source.port || 'N/A';
                } else {
                    sourceHost.textContent = 'N/A';
                    sourcePort.textContent = 'N/A';
                }
                
                // Use replication user if server user is unavailable
                sourceUser.textContent = data.replication.user || 
                                        (data.replication.source?.username || 'N/A');
                
                // Handle binlog info
                if (data.replication.binlog_info?.file) {
                    sourceBinlog.textContent = data.replication.binlog_info.file;
                } else {
                    sourceBinlog.textContent = 'N/A';
                }
                
                // Target server info
                if (data.replication.target) {
                    targetHost.textContent = data.replication.target.host || 'N/A';
                    targetPort.textContent = data.replication.target.port || 'N/A';
                } else {
                    targetHost.textContent = 'N/A';
                    targetPort.textContent = 'N/A';
                }
                console.log('Replication setup step:', data.replication.setup_step);

                // Update slave status table
                const slaveStatusTableBody = document.getElementById('slaveStatusTable').querySelector('tbody');
                slaveStatusTableBody.innerHTML = '';
                
                console.log('Slave status:', data.replication.slave_status);
                if (data.replication.slave_status) {
                    // Ensure we have the slave status element
                    const slaveStatusElement = document.getElementById('slaveStatus');
                    if (slaveStatusElement) {
                        slaveStatusElement.textContent = JSON.stringify(data.replication.slave_status, null, 2);
                    }

                    // Update table with slave status details
                    for (const [key, value] of Object.entries(data.replication.slave_status)) {
                        const row = slaveStatusTableBody.insertRow();
                        row.insertCell(0).textContent = key;
                        const valueCell = row.insertCell(1);

                        let displayValue = value;
                        if (value === 'Yes') {
                            displayValue = '<span class="badge bg-success">Yes</span>';
                        } else if (value === 'No' || (key.includes('Error') && value)) {
                            displayValue = `<span class="badge bg-danger">${value || 'Error'}</span>`;
                        } else if (value === null || value === '') {
                            displayValue = '<span class="text-muted">N/A</span>';
                        }
                        
                        valueCell.innerHTML = displayValue;
                    }
                } else {
                    const row = slaveStatusTableBody.insertRow();
                    const cell = row.insertCell(0);
                    cell.colSpan = 2;
                    cell.textContent = 'No replication data available.';
                    cell.classList.add('text-center', 'text-muted');
                }

                console.log('Replication logs:', data.logs);
                // Update logs
                const logsHtml = data.logs.map(log => `
                    <tr class="${log.is_error ? 'table-danger' : ''}">
                        <td>${new Date(log.timestamp).toLocaleString()}</td>
                        <td>${log.step}</td>
                        <td>${log.status}</td>
                        <td>
                            ${log.message}
                            ${log.command_to_run ? `<pre class="mt-1 mb-0 small">${log.command_to_run}</pre>` : ''}
                        </td>
                    </tr>
                `).join('');
                
                document.getElementById('replLogs').innerHTML = logsHtml;
                
                console.log('Before hiding spinner and showing details');
                spinner.classList.add('d-none');
                document.getElementById('replicationDetails').classList.remove('d-none');
                modal.querySelector('.modal-body').classList.remove('d-none');
                console.log('[DEBUG] After hiding spinner and showing details');
                // Show the modal using Bootstrap's modal API
                const bsModal = new bootstrap.Modal(modal);
                bsModal.show();
                console.log('[DEBUG] Modal shown');
                
                // Force a reflow to ensure styles are applied
                modal.offsetHeight;
            } else {
                throw new Error(data.message);
            }
        } catch (e) {
            console.error('[ERROR] in loadReplicationDetails:', e);
            spinner.classList.add('d-none');
            errorDiv.textContent = `Error: ${e.message}`;
            errorDiv.classList.remove('d-none');
            detailsDiv.classList.add('d-none');
            modal.querySelector('.modal-body').classList.remove('d-none');
        }
    },

    // ... [keep all remaining methods unchanged]
};

// Initialize the wizard when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing wizard...');
    wizardHandlers.init();
});
