const API_URL = 'http://localhost:8000/api';

let searchTimeout;

// Tab switching
function switchTab(tab) {
    document.querySelectorAll('.pill-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));

    event.target.classList.add('active');
    document.getElementById(`${tab}-page`).classList.add('active');
}

// Debounced auto-search to prevent duplicate queries
function search() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(performSearch, 300);
}

async function performSearch() {
    const query = document.getElementById('search-input').value;
    const dataType = document.getElementById('sequence-type-select').value;
    const fromField = document.getElementById('from-select').value;
    const toField = document.getElementById('to-select').value;
    const limit = document.getElementById('results-limit').value;

    // Don't search if query is empty
    if (!query.trim()) {
        document.getElementById('results').innerHTML = '';
        return;
    }

    try {
        // Only pass query, data_type, and from_field to database
        const response = await fetch(`${API_URL}/search`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                query: query,
                data_type: dataType,
                from_field: fromField
            })
        });

        const data = await response.json();
        displayResults(data.results || [], toField, limit);
    } catch (error) {
        console.error('Search error:', error);
        document.getElementById('results').innerHTML = '';
    }
}

// Display results with filename as rightmost column in each row
function displayResults(results, toField, limit) {
    if (!results.length) {
        document.getElementById('results').innerHTML = '';
        return;
    }

    // Apply limit
    let limitedResults = results;
    if (limit !== 'all') {
        limitedResults = results.slice(0, parseInt(limit));
    }

    const html = limitedResults.map(result => {
        // Collect columns based on toField filter
        const columns = [];

        if (toField === 'any') {
            // Show all available columns
            if (result.sequences && result.sequences.length) {
                columns.push({label: 'Sequences', value: result.sequences.join(', ')});
            }
            if (result.features && result.features.length) {
                columns.push({label: 'Features', value: result.features.join(', ')});
            }
            if (result.primers && result.primers.length) {
                columns.push({label: 'Primers', value: result.primers.join(', ')});
            }
            if (result.data_type) {
                columns.push({label: 'Type', value: result.data_type});
            }
        } else if (toField === 'sequences' && result.sequences && result.sequences.length) {
            columns.push({label: 'Sequences', value: result.sequences.join(', ')});
        } else if (toField === 'features' && result.features && result.features.length) {
            columns.push({label: 'Features', value: result.features.join(', ')});
        } else if (toField === 'primers' && result.primers && result.primers.length) {
            columns.push({label: 'Primers', value: result.primers.join(', ')});
        }

        // ALWAYS append filename as the rightmost column
        const filename = result.file_path || result.data?.file_path || 'Unknown';
        columns.push({label: 'File', value: filename});

        // Generate columns HTML
        const columnsHTML = columns.map(col => `
            <div class="result-column">
                <div class="result-column-label">${col.label}</div>
                <div class="result-column-value">${col.value}</div>
            </div>
        `).join('');

        return `
            <div class="result-box">
                <div class="result-content">
                    ${columnsHTML}
                </div>
            </div>
        `;
    }).join('');

    document.getElementById('results').innerHTML = html;
}

// Scan directory with feed logging
let feedLines = [];
const MAX_FEED_LINES = 100;

async function scan() {
    const path = document.getElementById('path-input').value;
    const feedElement = document.getElementById('feed');

    // Clear feed
    feedLines = [];
    feedElement.innerHTML = '';

    addToFeed('Starting scan...');
    addToFeed(`Directory: ${path}`);

    try {
        const response = await fetch(`${API_URL}/scan`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                directory_path: path,
                recursive: true
            })
        });

        const data = await response.json();

        if (data.error) {
            addToFeed(`ERROR: ${data.error}`, 'error');
        } else {
            addToFeed(`Scanned ${data.total} files`, 'success');
            addToFeed(`Imported ${data.imported} files`, 'success');
            updateImportCount(data.imported);

            // Add file details if available
            if (data.files) {
                data.files.forEach(file => {
                    addToFeed(`  ✓ ${file}`);
                });
            }
        }
    } catch (error) {
        addToFeed(`ERROR: ${error.message}`, 'error');
    }

    addToFeed('Scan complete');
}

// Add line to feed log
function addToFeed(message, type = '') {
    feedLines.push({message, type});

    // Keep only last MAX_FEED_LINES
    if (feedLines.length > MAX_FEED_LINES) {
        feedLines = feedLines.slice(-MAX_FEED_LINES);
    }

    const feedElement = document.getElementById('feed');
    feedElement.innerHTML = feedLines.map(line =>
        `<div class="feed-line ${line.type}">${line.message}</div>`
    ).join('');

    // Auto-scroll to bottom
    feedElement.scrollTop = feedElement.scrollHeight;
}

// Update import counter
function updateImportCount(count) {
    document.getElementById('import-count').textContent = count;
}

// Initialize event listeners on load
window.addEventListener('load', () => {
    updateImportCount(0);

    // Add event listeners for search
    document.getElementById('search-input').addEventListener('input', search);
    document.getElementById('type-select').addEventListener('change', search);
    document.getElementById('from-select').addEventListener('change', search);
    document.getElementById('to-select').addEventListener('change', search);
    document.getElementById('results-limit').addEventListener('change', search);
});
