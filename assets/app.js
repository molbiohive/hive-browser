const API_URL = 'http://localhost:8000/api';

function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    event.target.classList.add('active');
    document.getElementById(`${tab}-tab`).classList.add('active');

    if (tab === 'scan') getStats();
}

async function search() {
    const query = document.getElementById('search-input').value;
    const dataType = document.getElementById('data-type').value;
    const fromField = document.getElementById('from-field').value;
    const toField = document.getElementById('to-field').value;

    const response = await fetch(`${API_URL}/search`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            query: query,
            data_type: dataType,
            from_field: fromField,
            to_field: toField
        })
    });

    const data = await response.json();
    displayResults(data.results);
}

function displayResults(results) {
    const html = results.map(r => `
        <div class="result-card">
            <div class="result-header">
                <strong>${r.file_path || r.data?.file_path || 'Result'}</strong>
                <span class="result-badge">${r.data_type || r.data?.data_type || 'unknown'}</span>
            </div>
            ${r.sequences ? `<div>Sequences: ${r.sequences.length}</div>` : ''}
            ${r.features ? `<div>Features: ${r.features.join(', ')}</div>` : ''}
            ${r.from ? `<div>${r.from} → ${r.to}</div>` : ''}
        </div>
    `).join('');

    document.getElementById('results').innerHTML = html || '<p>No results found</p>';
}

async function scan() {
    const path = document.getElementById('path-input').value;
    const recursive = document.getElementById('recursive').checked;
    const status = document.getElementById('scan-status');

    const response = await fetch(`${API_URL}/scan`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            directory_path: path,
            recursive: recursive
        })
    });

    const data = await response.json();

    if (data.error) {
        status.className = 'error';
        status.textContent = data.error;
    } else {
        status.className = 'success';
        status.textContent = `Imported ${data.imported} of ${data.total} files`;
        getStats();
    }
}

async function importSample() {
    const response = await fetch(`${API_URL}/import-sample`, {method: 'POST'});
    const data = await response.json();

    const status = document.getElementById('scan-status');
    status.className = 'success';
    status.textContent = `Imported ${data.imported} sample files`;
    getStats();
}

async function clearDB() {
    if (!confirm('Clear all data?')) return;

    await fetch(`${API_URL}/clear`, {method: 'DELETE'});

    const status = document.getElementById('scan-status');
    status.className = 'success';
    status.textContent = 'Database cleared';
    getStats();
}

async function getStats() {
    const response = await fetch(`${API_URL}/stats`);
    const data = await response.json();

    document.getElementById('stats').innerHTML = `
        <div class="stat-card">
            <div class="stat-value">${data.total}</div>
            <div class="stat-label">Total</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${data.dna}</div>
            <div class="stat-label">DNA</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${data.rna}</div>
            <div class="stat-label">RNA</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${data.protein}</div>
            <div class="stat-label">Protein</div>
        </div>
    `;
}

