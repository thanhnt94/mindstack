// web_app/static/js/dashboard_charts.js

document.addEventListener('DOMContentLoaded', function () {
    const dataScriptElement = document.getElementById('dashboard-data');
    if (!dataScriptElement) {
        console.error('Không tìm thấy dữ liệu dashboard.');
        return;
    }

    const dashboardData = JSON.parse(dataScriptElement.textContent);
    let activityChartInstance = null;

    // --- Logic biểu đồ hoạt động (Line Chart) ---
    const activityCtx = document.getElementById('activityChart');
    if (activityCtx) {
        const datasets = [
            {
                label: 'Số lần ôn tập',
                data: dashboardData.activity_chart_data.datasets[0].data,
                borderColor: 'rgba(52, 152, 219, 1)',
                backgroundColor: 'rgba(52, 152, 219, 0.2)',
                yAxisID: 'y',
                tension: 0.3,
                fill: true
            },
            {
                label: 'Số thẻ ôn tập',
                data: dashboardData.activity_chart_data.datasets[1].data,
                borderColor: 'rgba(155, 89, 182, 1)',
                backgroundColor: 'rgba(155, 89, 182, 0.2)',
                yAxisID: 'y',
                tension: 0.3,
                fill: true
            },
            {
                label: 'Số thẻ học mới',
                data: dashboardData.activity_chart_data.datasets[2].data,
                borderColor: 'rgba(46, 204, 113, 1)',
                backgroundColor: 'rgba(46, 204, 113, 0.2)',
                yAxisID: 'y',
                tension: 0.3,
                fill: true
            },
            {
                label: 'Điểm đạt được',
                data: dashboardData.activity_chart_data.datasets[3].data,
                borderColor: 'rgba(241, 196, 15, 1)',
                backgroundColor: 'rgba(241, 196, 15, 0.2)',
                yAxisID: 'y1', // Trục Y phụ
                tension: 0.3,
                fill: true
            }
        ];

        activityChartInstance = new Chart(activityCtx, {
            type: 'line',
            data: {
                labels: dashboardData.activity_chart_data.labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {if (value % 1 === 0) {return value;}}
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        beginAtZero: true,
                        grid: {
                            drawOnChartArea: false,
                        },
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    }
                }
            }
        });

        const chartToggles = document.querySelectorAll('.chart-toggle-checkbox');
        chartToggles.forEach(toggle => {
            toggle.addEventListener('change', function() {
                const datasetIndex = this.dataset.datasetIndex;
                if (activityChartInstance) {
                    const isVisible = activityChartInstance.isDatasetVisible(datasetIndex);
                    activityChartInstance.setDatasetVisibility(datasetIndex, !isVisible);
                    activityChartInstance.update();
                }
            });
        });
    }

    // --- Logic vẽ Lịch Nhiệt Hoạt Động ---
    function renderHeatmap() {
        const heatmapContainer = document.getElementById('heatmap-container');
        if (!heatmapContainer) return;

        const activityData = dashboardData.heatmap_data || {};
        const today = new Date();
        const oneYearAgo = new Date();
        oneYearAgo.setFullYear(today.getFullYear() - 1);

        const dataMap = new Map(Object.entries(activityData));
        const maxValue = Math.max(...dataMap.values(), 1); 
        
        let currentDay = oneYearAgo;
        let html = '';

        while (currentDay <= today) {
            const dateString = currentDay.toISOString().slice(0, 10);
            const count = dataMap.get(dateString) || 0;
            
            let level = 0;
            if (count > 0) {
                level = Math.ceil((count / maxValue) * 4);
                level = Math.max(1, Math.min(4, level));
            }
            
            const tooltip = `${count} lần ôn tập vào ${currentDay.toLocaleDateString('vi-VN')}`;
            html += `<div class="heatmap-day" data-level="${level}" title="${tooltip}"></div>`;
            
            currentDay.setDate(currentDay.getDate() + 1);
        }
        heatmapContainer.innerHTML = html;
    }
    renderHeatmap();

    // --- Logic biểu đồ tròn (Pie Chart) ---
    const setSelector = document.getElementById('setSelector');
    const setDetailsContainer = document.getElementById('set-details-container');
    const pieChartCtx = document.getElementById('setPieChart');
    const setDetailsText = document.getElementById('set-details-text');
    const setSelectorContainer = document.querySelector('.set-selector-container');
    let pieChartInstance = null;

    // --- BẮT ĐẦU SỬA: Cập nhật hàm hiển thị chi tiết ---
    function displaySetDetails(setId) {
        if (!setId) {
            setDetailsContainer.style.display = 'none';
            return;
        }

        const setData = dashboardData.sets_stats[setId];
        if (setData) {
            setDetailsContainer.style.display = 'flex';

            if (pieChartInstance) {
                pieChartInstance.destroy();
            }
            pieChartInstance = new Chart(pieChartCtx, {
                type: 'pie',
                data: {
                    labels: setData.pie_chart_data.labels,
                    datasets: [{
                        data: setData.pie_chart_data.data,
                        backgroundColor: ['#2ecc71', '#f1c40f', '#ecf0f1'],
                        borderColor: '#fff',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'top' } }
                }
            });

            // Cập nhật nội dung chi tiết với giao diện biểu đồ hóa mới
            const percentage = setData.total_cards > 0 ? (setData.learned_cards * 100 / setData.total_cards).toFixed(0) : 0;
            setDetailsText.innerHTML = `
                <div class="set-details-info">
                    <div class="main-progress-bar-container">
                        <div class="main-progress-bar-label">
                            <span>Tiến độ chung</span>
                            <strong>${setData.learned_cards} / ${setData.total_cards}</strong>
                        </div>
                        <div class="main-progress-bar">
                            <div class="main-progress-fill" style="width: ${percentage}%;"></div>
                        </div>
                    </div>
                    <div class="key-stats-grid">
                        <div class="key-stat-card due">
                            <span class="key-stat-value">${setData.due_cards}</span>
                            <span class="key-stat-label">Cần ôn</span>
                        </div>
                        <div class="key-stat-card mastered">
                            <span class="key-stat-value">${setData.mastered_cards}</span>
                            <span class="key-stat-label">Nhớ sâu</span>
                        </div>
                        <div class="key-stat-card lapsed">
                            <span class="key-stat-value">${setData.lapsed_cards}</span>
                            <span class="key-stat-label">Hay sai</span>
                        </div>
                    </div>
                </div>
            `;
        }
    }
    // --- KẾT THÚC SỬA ---

    if (setSelector && setDetailsContainer && pieChartCtx && setSelectorContainer) {
        setSelector.addEventListener('change', function () {
            displaySetDetails(this.value);
        });

        const currentSetId = setSelectorContainer.dataset.currentSetId;
        if (currentSetId && dashboardData.sets_stats[currentSetId]) {
            setSelector.value = currentSetId;
            setSelector.dispatchEvent(new Event('change'));
        }
    }
});
