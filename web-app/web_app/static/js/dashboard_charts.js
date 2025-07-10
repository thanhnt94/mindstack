// web_app/static/js/dashboard_charts.js

document.addEventListener('DOMContentLoaded', function () {
    const dataScriptElement = document.getElementById('dashboard-data');
    if (!dataScriptElement) {
        console.error('Không tìm thấy dữ liệu dashboard.');
        return;
    }

    const dashboardData = JSON.parse(dataScriptElement.textContent);

    // --- BẮT ĐẦU SỬA: Cập nhật biểu đồ để hiển thị 2 đường ---
    const activityCtx = document.getElementById('activityChart');
    if (activityCtx) {
        new Chart(activityCtx, {
            type: 'line',
            data: {
                labels: dashboardData.activity_chart_data.labels,
                datasets: [
                    {
                        label: 'Số thẻ đã ôn tập',
                        data: dashboardData.activity_chart_data.datasets[0].data,
                        borderColor: 'rgba(52, 152, 219, 1)',
                        backgroundColor: 'rgba(52, 152, 219, 0.2)',
                        fill: true,
                        tension: 0.3,
                        borderWidth: 2
                    },
                    {
                        label: 'Số thẻ học mới',
                        data: dashboardData.activity_chart_data.datasets[1].data,
                        borderColor: 'rgba(46, 204, 113, 1)',
                        backgroundColor: 'rgba(46, 204, 113, 0.2)',
                        fill: true,
                        tension: 0.3,
                        borderWidth: 2
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            // Đảm bảo trục Y luôn là số nguyên
                            callback: function(value) {if (value % 1 === 0) {return value;}}
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true, // Hiển thị chú giải cho 2 đường
                        position: 'top'
                    }
                }
            }
        });
    }
    // --- KẾT THÚC SỬA ---

    // --- 2. Xử lý Thống kê chi tiết theo bộ ---
    const setSelector = document.getElementById('setSelector');
    const setDetailsContainer = document.getElementById('set-details-container');
    const pieChartCtx = document.getElementById('setPieChart');
    const setDetailsText = document.getElementById('set-details-text');
    let pieChartInstance = null;

    if (setSelector && setDetailsContainer && pieChartCtx) {
        setSelector.addEventListener('change', function () {
            const selectedSetId = this.value;

            if (selectedSetId) {
                const setData = dashboardData.sets_stats[selectedSetId];
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
                                backgroundColor: [
                                    'rgba(46, 204, 113, 0.8)',
                                    'rgba(241, 196, 15, 0.8)',
                                    'rgba(231, 233, 235, 0.8)'
                                ],
                                borderColor: '#fff',
                                borderWidth: 2
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    position: 'top',
                                }
                            }
                        }
                    });

                    setDetailsText.innerHTML = `
                        <p><strong>Tổng số thẻ:</strong> ${setData.total_cards}</p>
                        <p><strong>Số thẻ đã học:</strong> ${setData.learned_cards}</p>
                    `;
                }
            } else {
                setDetailsContainer.style.display = 'none';
            }
        });
    }
});
