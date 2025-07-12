// web_app/static/js/dashboard_charts.js

document.addEventListener('DOMContentLoaded', function () {
    const dataScriptElement = document.getElementById('dashboard-data');
    if (!dataScriptElement) return;

    const dashboardData = JSON.parse(dataScriptElement.textContent);
    let activityChartInstance = null;

    // --- Logic biểu đồ hoạt động (Line Chart) ---
    const activityCtx = document.getElementById('activityChart');
    if (activityCtx) {
        // ... (Giữ nguyên phần code vẽ biểu đồ đường)
        const datasets = [
            { label: 'Số lần ôn tập', data: dashboardData.activity_chart_data.datasets[0].data, borderColor: 'rgba(52, 152, 219, 1)', backgroundColor: 'rgba(52, 152, 219, 0.2)', yAxisID: 'y', tension: 0.3, fill: true },
            { label: 'Số thẻ ôn tập', data: dashboardData.activity_chart_data.datasets[1].data, borderColor: 'rgba(155, 89, 182, 1)', backgroundColor: 'rgba(155, 89, 182, 0.2)', yAxisID: 'y', tension: 0.3, fill: true },
            { label: 'Số thẻ học mới', data: dashboardData.activity_chart_data.datasets[2].data, borderColor: 'rgba(46, 204, 113, 1)', backgroundColor: 'rgba(46, 204, 113, 0.2)', yAxisID: 'y', tension: 0.3, fill: true },
            { label: 'Điểm đạt được', data: dashboardData.activity_chart_data.datasets[3].data, borderColor: 'rgba(241, 196, 15, 1)', backgroundColor: 'rgba(241, 196, 15, 0.2)', yAxisID: 'y1', tension: 0.3, fill: true }
        ];
        activityChartInstance = new Chart(activityCtx, {
            type: 'line',
            data: { labels: dashboardData.activity_chart_data.labels, datasets: datasets },
            options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, scales: { y: { type: 'linear', display: true, position: 'left', beginAtZero: true, ticks: { callback: function(value) { if (value % 1 === 0) { return value; } } } }, y1: { type: 'linear', display: true, position: 'right', beginAtZero: true, grid: { drawOnChartArea: false } } }, plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } } }
        });
        document.querySelectorAll('.chart-toggle-checkbox').forEach(toggle => {
            toggle.addEventListener('change', function() {
                if (activityChartInstance) {
                    activityChartInstance.setDatasetVisibility(this.dataset.datasetIndex, !this.checked);
                    activityChartInstance.update();
                }
            });
        });
    }

    // --- Logic vẽ Lịch Nhiệt Hoạt Động ---
    function renderHeatmap() {
        const heatmapContainer = document.getElementById('heatmap-container');
        if (!heatmapContainer) return;
        heatmapContainer.innerHTML = '';
        const activityData = dashboardData.heatmap_data || {};
        const today = new Date();
        const oneYearAgo = new Date(today);
        oneYearAgo.setFullYear(today.getFullYear() - 1);
        const dateMap = new Map(Object.entries(activityData));
        const maxValue = Math.max(...dateMap.values(), 1);
        let currentDay = new Date(oneYearAgo);
        const dayOfWeek = currentDay.getDay();
        if (dayOfWeek !== 0) {
            for (let i = 0; i < dayOfWeek; i++) {
                heatmapContainer.innerHTML += `<div class="heatmap-day" style="background-color: transparent;"></div>`;
            }
        }
        while (currentDay <= today) {
            const dateString = currentDay.toISOString().slice(0, 10);
            const count = dateMap.get(dateString) || 0;
            let level = 0;
            if (count > 0) {
                const p = count / maxValue;
                if (p > 0.75) level = 4; else if (p > 0.5) level = 3; else if (p > 0.25) level = 2; else level = 1;
            }
            heatmapContainer.innerHTML += `<div class="heatmap-day" data-level="${level}" title="${count} lần ôn tập vào ${currentDay.toLocaleDateString('vi-VN')}"></div>`;
            currentDay.setDate(currentDay.getDate() + 1);
        }
    }
    renderHeatmap();

    // --- Logic hiển thị chi tiết bộ thẻ (ĐÃ CẬP NHẬT) ---
    const setSelector = document.getElementById('setSelector');
    const setDetailsContainer = document.getElementById('set-details-container');
    const setSelectorContainer = document.querySelector('.set-selector-container');

    function displaySetDetails(setId) {
        if (!setId) {
            setDetailsContainer.style.display = 'none';
            return;
        }

        const setData = dashboardData.sets_stats[setId];
        if (setData) {
            setDetailsContainer.style.display = 'block';
            const stats = setData.stat_values;
            const percentage = setData.total_cards > 0 ? (setData.learned_cards * 100 / setData.total_cards).toFixed(0) : 0;

            // Tạo HTML cho giao diện mới
            setDetailsContainer.innerHTML = `
                <div class="progress-bar-new">
                    <div class="progress-bar-fill-new" style="width: ${percentage}%;"></div>
                    <span class="progress-bar-text-new">${percentage}% (${setData.learned_cards}/${setData.total_cards})</span>
                </div>

                <div class="key-stats-grid-2x3">
                    <div class="key-stat-card learning clickable-stat-card" data-category="learning">
                        <span class="key-stat-value">${stats.learning}</span>
                        <span class="key-stat-label">Đang học</span>
                    </div>
                    <div class="key-stat-card mastered clickable-stat-card" data-category="mastered">
                        <span class="key-stat-value">${stats.mastered}</span>
                        <span class="key-stat-label">Nhớ sâu</span>
                    </div>
                    <div class="key-stat-card unseen clickable-stat-card" data-category="unseen">
                        <span class="key-stat-value">${stats.unseen}</span>
                        <span class="key-stat-label">Chưa học</span>
                    </div>
                    <div class="key-stat-card due clickable-stat-card" data-category="due">
                        <span class="key-stat-value">${stats.due}</span>
                        <span class="key-stat-label">Cần ôn</span>
                    </div>
                    <div class="key-stat-card due-soon clickable-stat-card" data-category="due_soon">
                        <span class="key-stat-value">${stats.due_soon}</span>
                        <span class="key-stat-label">Sắp đến hạn</span>
                    </div>
                    <div class="key-stat-card lapsed clickable-stat-card" data-category="lapsed">
                        <span class="key-stat-value">${stats.lapsed}</span>
                        <span class="key-stat-label">Hay sai</span>
                    </div>
                </div>
            `;
            
            addEventListenersToStatCards();
        }
    }

    if (setSelector && setDetailsContainer && setSelectorContainer) {
        setSelector.addEventListener('change', function () {
            displaySetDetails(this.value);
        });
        const currentSetId = setSelectorContainer.dataset.currentSetId;
        if (currentSetId && dashboardData.sets_stats[currentSetId]) {
            setSelector.value = currentSetId;
            setSelector.dispatchEvent(new Event('change'));
        }
    }

    // --- Logic cho Modal danh sách thẻ (CẬP NHẬT TIÊU ĐỀ) ---
    const modal = document.getElementById('card-list-modal');
    const modalCloseBtn = document.getElementById('card-list-modal-close-btn');
    const modalTitle = document.getElementById('card-list-modal-title');
    const cardListContainer = document.getElementById('card-list-container');
    const paginationContainer = document.getElementById('card-list-pagination');

    const categoryTitles = {
        due: 'Các thẻ cần ôn',
        mastered: 'Các thẻ đã nhớ sâu',
        lapsed: 'Các thẻ hay sai',
        learning: 'Các thẻ đang học',
        unseen: 'Các thẻ chưa học',
        due_soon: 'Các thẻ sắp đến hạn'
    };

    async function fetchAndShowCards(setId, category, page = 1) {
        // ... (Giữ nguyên phần code fetch và render modal)
        modal.style.display = 'flex';
        modalTitle.textContent = categoryTitles[category] || 'Danh sách thẻ';
        cardListContainer.innerHTML = '<div class="loader-container"><div class="loader"></div></div>';
        paginationContainer.innerHTML = '';
        try {
            const response = await fetch(`/api/cards_by_category/${setId}/${category}?page=${page}`);
            if (!response.ok) throw new Error('Lỗi mạng hoặc server.');
            const data = await response.json();
            if (data.status === 'success') {
                renderCards(data.cards);
                renderPagination(data.pagination, setId, category);
            } else {
                throw new Error(data.message || 'Lỗi không xác định.');
            }
        } catch (error) {
            cardListContainer.innerHTML = `<p style="color: red; text-align: center;">Không thể tải danh sách thẻ: ${error.message}</p>`;
        }
    }

    function renderCards(cards) {
        // ... (Giữ nguyên phần code render bảng thẻ)
        if (!cards || cards.length === 0) {
            cardListContainer.innerHTML = '<p style="text-align: center;">Không có thẻ nào trong danh mục này.</p>';
            return;
        }
        let tableHTML = '<table class="card-list-table"><thead><tr><th>Mặt trước</th><th>Mặt sau</th></tr></thead><tbody>';
        cards.forEach(card => { tableHTML += `<tr><td>${card.front}</td><td>${card.back}</td></tr>`; });
        tableHTML += '</tbody></table>';
        cardListContainer.innerHTML = tableHTML;
    }

    function renderPagination(pagination, setId, category) {
        // ... (Giữ nguyên phần code render phân trang)
        paginationContainer.innerHTML = '';
        if (pagination.pages <= 1) return;
        const prevButton = document.createElement('button');
        prevButton.innerHTML = '&laquo;';
        prevButton.disabled = !pagination.has_prev;
        prevButton.addEventListener('click', () => fetchAndShowCards(setId, category, pagination.page - 1));
        paginationContainer.appendChild(prevButton);
        const pageInfo = document.createElement('span');
        pageInfo.textContent = `Trang ${pagination.page} / ${pagination.pages}`;
        paginationContainer.appendChild(pageInfo);
        const nextButton = document.createElement('button');
        nextButton.innerHTML = '&raquo;';
        nextButton.disabled = !pagination.has_next;
        nextButton.addEventListener('click', () => fetchAndShowCards(setId, category, pagination.page + 1));
        paginationContainer.appendChild(nextButton);
    }

    function addEventListenersToStatCards() {
        document.querySelectorAll('.clickable-stat-card').forEach(card => {
            card.addEventListener('click', function() {
                const category = this.dataset.category;
                const selectedSetId = setSelector.value;
                if (!selectedSetId) {
                    alert('Vui lòng chọn một bộ thẻ trước.');
                    return;
                }
                fetchAndShowCards(selectedSetId, category);
            });
        });
    }

    if (modalCloseBtn) modalCloseBtn.addEventListener('click', () => { modal.style.display = 'none'; });
    if (modal) modal.addEventListener('click', function(event) { if (event.target === modal) { modal.style.display = 'none'; } });
});