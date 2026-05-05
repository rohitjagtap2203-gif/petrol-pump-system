// Dashboard Charts - Production Ready (Phase 2 Complete)
// Petrol Pump Management System - Chart.js + AJAX

let dailyChartInstance = null;
let fuelPieChartInstance = null;
let monthlyChartInstance = null;

document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('.charts-container') || document.getElementById('dailyRevenueChart')) {
        fetchCharts();
        // Auto-refresh every 5 seconds
        setInterval(fetchCharts, 5000);
    }
});

async function fetchCharts() {
    const chartsContainer = document.querySelector('.charts-container, .charts-section');
    if (!chartsContainer) return;

    // Keep canvases; only show loading overlay in container.
    chartsContainer.innerHTML = '<div class="loading-charts"><i class="fas fa-spinner fa-spin"></i> Loading charts...</div>';

    try {
        const response = await fetch('/api/dashboard/charts');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        console.log(data); // required debugging log

        if (data.status === 'success') {
            chartsContainer.innerHTML = ''; // Clear loading

            // Re-render charts (simple + safe: destroy old instances if canvases still exist)
            destroyCharts();

            renderDailyRevenueChart(data.daily);
            renderFuelDistributionChart(data.fuel_pie);
            renderMonthlySalesChart(data.monthly);
            updateLowStockAlert(data.low_stock);
        } else {
            showChartError('Chart data unavailable', data.message);
        }
    } catch (error) {
        console.error('Charts fetch error:', error);
        showChartError('Failed to load charts', error.message || 'Unknown error');
    }
}

function destroyCharts() {
    try { dailyChartInstance?.destroy(); } catch (e) {}
    try { fuelPieChartInstance?.destroy(); } catch (e) {}
    try { monthlyChartInstance?.destroy(); } catch (e) {}
    dailyChartInstance = null;
    fuelPieChartInstance = null;
    monthlyChartInstance = null;
}

function showChartError(title, message) {
    const chartsContainer = document.querySelector('.charts-container, .charts-section');
    if (chartsContainer) {
        chartsContainer.innerHTML = `
            <div class="alert alert-error p-4 rounded-lg">
                <div class="flex items-center">
                    <i class="fas fa-chart-line text-2xl text-red-500 mr-3"></i>
                    <div>
                        <h3 class="font-bold text-lg">${title}</h3>
                        <p class="text-sm opacity-75">${message}</p>
                        <button onclick="fetchCharts()" class="mt-2 bg-blue-500 hover:bg-blue-600 text-white px-4 py-1 rounded text-sm">
                            🔄 Retry Charts
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}

function renderDailyRevenueChart(chartData) {
    const canvas = document.getElementById('dailyRevenueChart');
    const ctx = canvas?.getContext('2d');

    // Handle empty gracefully
    if (!ctx || !chartData.labels || chartData.labels.length === 0) {
        if (canvas) canvas.parentElement.innerHTML = '<div class="text-muted p-3">No data available</div>';
        return;
    }

    dailyChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: 'Daily Revenue (₹)',
                data: chartData.data,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#10b981',
                pointBorderColor: '#059669',
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { callback: value => '₹' + value.toLocaleString() }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: context => `₹${context.parsed.y.toLocaleString()}`
                    }
                }
            }
        }
    });
}

function renderFuelDistributionChart(chartData) {
    const canvas = document.getElementById('fuelPieChart');
    const ctx = canvas?.getContext('2d');

    // Handle empty gracefully
    if (!ctx || !chartData.labels || chartData.labels.length === 0) {
        if (canvas) canvas.parentElement.innerHTML = '<div class="text-muted p-3">No data available</div>';
        return;
    }

    const total = (chartData.data || []).reduce((a, b) => a + b, 0) || 0;

    fuelPieChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: chartData.labels,
            datasets: [{
                data: chartData.data,
                backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444'],
                borderWidth: 2,
                borderColor: '#1f2937'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { 
                    position: 'bottom',
                    labels: { padding: 20 }
                },
                tooltip: {
                    callbacks: {
                        label: context => {
                            const liters = context.parsed;
                            const pct = total > 0 ? Math.round((liters / total) * 100) : 0;
                            return `${context.label}: ${liters}L (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

function renderMonthlySalesChart(chartData) {
    const canvas = document.getElementById('monthlySalesChart');
    const ctx = canvas?.getContext('2d');

    // Handle empty gracefully
    if (!ctx || !chartData.labels || chartData.labels.length === 0) {
        if (canvas) canvas.parentElement.innerHTML = '<div class="text-muted p-3">No data available</div>';
        return;
    }

    monthlyChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: chartData.labels.map(m => m.slice(5)), // Show MM-YY
            datasets: [{
                label: 'Monthly Revenue (₹)',
                data: chartData.data,
                backgroundColor: 'rgba(255, 127, 0, 0.8)',
                borderColor: '#ff7f00',
                borderRadius: 8,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { callback: value => '₹' + value.toLocaleString() }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: context => `₹${context.parsed.y.toLocaleString()}`
                    }
                }
            }
        }
    });
}

function updateLowStockAlert(lowStock) {
    const alert = document.getElementById('lowStockAlert');
    const msg = document.getElementById('lowStockMsg');
    
    if (!alert || !msg) return;
    
    if (lowStock.length > 0) {
        msg.textContent = lowStock.map(item => 
            `<strong>${item.type}:</strong> ${item.stock.toFixed(1)}L`
        ).join(', ');
        alert.style.display = 'flex';
        alert.classList.add('alert-warning');
    } else {
        alert.style.display = 'none';
        alert.classList.remove('alert-warning');
    }
}

function showError(message) {
    const chartsSection = document.querySelector('.charts-section');
    if (chartsSection) {
        chartsSection.innerHTML = `
            <div class="alert alert-error">
                <i class="fas fa-exclamation-triangle"></i>
                ${message}
                <button onclick="fetchCharts()" class="btn btn-small">Retry</button>
            </div>
        `;
    }
}

