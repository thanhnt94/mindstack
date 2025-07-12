// web_app/static/js/dashboard_charts.js

document.addEventListener('DOMContentLoaded', function () {
    const dataScriptElement = document.getElementById('dashboard-data');
    if (!dataScriptElement) {
        console.error('Không tìm thấy dữ liệu dashboard.');
        return;
    }

    const dashboardData = JSON.parse(dataScriptElement.textContent);
    let activityChartInstance = null;

    // --- BẮT ĐẦU SỬA: Logic biểu đồ hoạt động với 3 chỉ số ---
    const activityCtx = document.getElementById('activityChart');
    if (activityCtx) {
        const datasets = [
            {
                label: 'Số lần ôn tập',
                data: dashboardData.activity_chart_data.datasets[0].data,
                borderColor: 'rgba(52, 152, 219, 1)',
                backgroundColor: 'rgba(52, 152, 219, 0.2)',
                tension: 0.3,
                fill: true
            },
            {
                label: 'Số thẻ ôn tập',
                data: dashboardData.activity_chart_data.datasets[1].data,
                borderColor: 'rgba(155, 89, 182, 1)',
                backgroundColor: 'rgba(155, 89, 182, 0.2)',
                tension: 0.3,
                fill: true
            },
            {
                label: 'Số thẻ học mới',
                data: dashboardData.activity_chart_data.datasets[2].data,
                borderColor: 'rgba(46, 204, 113, 1)',
                backgroundColor: 'rgba(46, 204, 113, 0.2)',
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
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {if (value % 1 === 0) {return value;}}
                        }
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
    // --- KẾT THÚC SỬA ---

    // --- Xử lý Thống kê chi tiết theo bộ ---
    const setSelector = document.getElementById('setSelector');
    const setDetailsContainer = document.getElementById('set-details-container');
    const pieChartCtx = document.getElementById('setPieChart');
    const setDetailsText = document.getElementById('set-details-text');
    const setSelectorContainer = document.querySelector('.set-selector-container');
    let pieChartInstance = null;

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
                        backgroundColor: ['rgba(46, 204, 113, 0.8)', 'rgba(241, 196, 15, 0.8)', 'rgba(231, 233, 235, 0.8)'],
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

            setDetailsText.innerHTML = `
                <p><strong>Tổng số thẻ:</strong> ${setData.total_cards}</p>
                <p><strong>Số thẻ đã học:</strong> ${setData.learned_cards}</p>
            `;
        }
    }

    if (setSelector && setDetailsContainer && pieChartCtx && setSelectorContainer) {
        // Gắn sự kiện change cho dropdown
        setSelector.addEventListener('change', function () {
            displaySetDetails(this.value);
        });

        // --- BẮT ĐẦU SỬA: Tự động hiển thị chi tiết cho bộ thẻ active ---
        const currentSetId = setSelectorContainer.dataset.currentSetId;
        if (currentSetId && dashboardData.sets_stats[currentSetId]) {
            setSelector.value = currentSetId;
            // Kích hoạt sự kiện change để vẽ biểu đồ
            setSelector.dispatchEvent(new Event('change'));
        }
        // --- KẾT THÚC SỬA ---
    }
});
