document.addEventListener('DOMContentLoaded', function() {
    const selections = {
        source: null,
        target: null
    };

    // Server card selection
    const serverCards = document.querySelectorAll('.server-card');
    serverCards.forEach(card => {
        card.addEventListener('click', handleCardClick);
    });

    // Form submission
    const form = document.getElementById('serverSelectForm');
    if (form) {
        form.addEventListener('submit', handleFormSubmit);
    }

    function handleCardClick(e) {
        const card = e.currentTarget;
        const serverId = card.dataset.serverId;
        const serverType = card.dataset.serverType;

        // If card is disabled, don't allow selection
        if (card.classList.contains('disabled')) {
            return;
        }

        // Handle source selection
        if (serverType === 'source') {
            // If already selected, deselect it
            if (serverId === selections.source) {
                selections.source = null;
                card.style.backgroundColor = 'white';
                card.style.borderColor = '#e9ecef';
                card.classList.remove('selected');
            } else {
                // Deselect previous source if exists
                if (selections.source) {
                    const prevCard = document.querySelector(`.server-card[data-server-type="source"][data-server-id="${selections.source}"]`);
                    if (prevCard) {
                        prevCard.style.backgroundColor = 'white';
                        prevCard.style.borderColor = '#e9ecef';
                        prevCard.classList.remove('selected');
                    }
                }
                // Select new source
                selections.source = serverId;
                card.style.backgroundColor = '#eef1ff';
                card.style.borderColor = '#4154f1';
                card.classList.add('selected');
            }
            updateTargetAvailability();
        }
        // Handle target selection
        else if (serverType === 'target') {
            // If already selected, deselect it
            if (serverId === selections.target) {
                selections.target = null;
                card.style.backgroundColor = 'white';
                card.style.borderColor = '#e9ecef';
                card.classList.remove('selected');
            } else {
                // Deselect previous target if exists
                if (selections.target) {
                    const prevCard = document.querySelector(`.server-card[data-server-type="target"][data-server-id="${selections.target}"]`);
                    if (prevCard) {
                        prevCard.style.backgroundColor = 'white';
                        prevCard.style.borderColor = '#e9ecef';
                        prevCard.classList.remove('selected');
                    }
                }
                // Select new target
                selections.target = serverId;
                card.style.backgroundColor = '#eef1ff';
                card.style.borderColor = '#4154f1';
                card.classList.add('selected');
            }
        }

        // Update hidden inputs
        document.getElementById('sourceServer').value = selections.source || '';
        document.getElementById('targetServer').value = selections.target || '';
    }

    function updateTargetAvailability() {
        const targetCards = document.querySelectorAll('.server-card[data-server-type="target"]');
        targetCards.forEach(card => {
            if (selections.source === card.dataset.serverId) {
                // Disable and gray out the card if it's the selected source
                card.classList.add('disabled');
                card.style.opacity = '0.5';
                card.style.cursor = 'not-allowed';
                // If this was selected as target, unselect it
                if (selections.target === card.dataset.serverId) {
                    selections.target = null;
                    card.style.backgroundColor = 'white';
                    card.style.borderColor = '#e9ecef';
                    card.classList.remove('selected');
                    document.getElementById('targetServer').value = '';
                }
            } else {
                // Enable the card
                card.classList.remove('disabled');
                card.style.opacity = '1';
                card.style.cursor = 'pointer';
            }
        });
    }

    async function handleFormSubmit(e) {
        e.preventDefault();
        
        if (!selections.source || !selections.target) {
            showError('Please select both source and target servers.');
            return;
        }
        
        if (selections.source === selections.target) {
            showError('Source and target servers must be different.');
            return;
        }

        // Store selections in session
        try {
            const response = await fetch('/djsql/replication/setup/1/', {  // Updated URL
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify({
                    step: 1,
                    source: selections.source,
                    target: selections.target
                })
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                // Redirect to step 2
                window.location.href = '/djsql/replication/setup/2/';
            } else {
                throw new Error(data.message || 'Failed to process server selection');
            }
        } catch (error) {
            showError(error.message);
        }
    }

    function showError(message) {
        const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
        document.getElementById('errorMessage').textContent = message;
        errorModal.show();
    }
});
