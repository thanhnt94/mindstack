// web_app/static/js/dashboard_charts.js

document.addEventListener('DOMContentLoaded', function () {
    const dataScriptElement = document.getElementById('dashboard-data');
    if (!dataScriptElement) return;

    const dashboardData = JSON.parse(dataScriptElement.textContent);
    
    let flashcardActivityChartInstance = null;
    let quizActivityChartInstance = null;

    // --- Logic biểu đồ hoạt động Flashcard (Line Chart) ---
    const flashcardActivityCtx = document.getElementById('flashcardActivityChart');
    if (flashcardActivityCtx) {
        const datasets = [
            { label: 'Số lần ôn tập', data: dashboardData.activity_chart_data.datasets[0].data, borderColor: 'rgba(52, 152, 219, 1)', backgroundColor: 'rgba(52, 152, 219, 0.2)', yAxisID: 'y', tension: 0.3, fill: true },
            { label: 'Số thẻ ôn tập', data: dashboardData.activity_chart_data.datasets[1].data, borderColor: 'rgba(155, 89, 182, 1)', backgroundColor: 'rgba(155, 89, 182, 0.2)', yAxisID: 'y', tension: 0.3, fill: true },
            { label: 'Số thẻ học mới', data: dashboardData.activity_chart_data.datasets[2].data, borderColor: 'rgba(46, 204, 113, 1)', backgroundColor: 'rgba(46, 204, 113, 0.2)', yAxisID: 'y', tension: 0.3, fill: true },
            { label: 'Điểm đạt được (Flashcard)', data: dashboardData.activity_chart_data.datasets[3].data, borderColor: 'rgba(241, 196, 15, 1)', backgroundColor: 'rgba(241, 196, 15, 0.2)', yAxisID: 'y1', tension: 0.3, fill: true }
        ];
        flashcardActivityChartInstance = new Chart(flashcardActivityCtx, {
            type: 'line',
            data: { labels: dashboardData.activity_chart_data.labels, datasets: datasets },
            options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, scales: { y: { type: 'linear', display: true, position: 'left', beginAtZero: true, ticks: { callback: function(value) { if (value % 1 === 0) { return value; } } } }, y1: { type: 'linear', display: true, position: 'right', beginAtZero: true, grid: { drawOnChartArea: false } } }, plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } } }
        });
    }

    // --- Logic biểu đồ hoạt động Quiz (Line Chart) ---
    const quizActivityCtx = document.getElementById('quizActivityChart');
    if (quizActivityCtx) {
        const datasets = [
            { label: 'Số lần trả lời (Quiz)', data: dashboardData.quiz_activity_chart_data.datasets[0].data, borderColor: 'rgba(155, 89, 182, 1)', backgroundColor: 'rgba(155, 89, 182, 0.2)', yAxisID: 'y', tension: 0.3, fill: true },
            { label: 'Số câu hỏi khác nhau (Quiz)', data: dashboardData.quiz_activity_chart_data.datasets[1].data, borderColor: 'rgba(230, 126, 34, 1)', backgroundColor: 'rgba(230, 126, 34, 0.2)', yAxisID: 'y', tension: 0.3, fill: true },
            { label: 'Điểm đạt được (Quiz)', data: dashboardData.quiz_activity_chart_data.datasets[2].data, borderColor: 'rgba(231, 76, 60, 1)', backgroundColor: 'rgba(231, 76, 60, 0.2)', yAxisID: 'y1', tension: 0.3, fill: true }
        ];
        quizActivityChartInstance = new Chart(quizActivityCtx, {
            type: 'line',
            data: { labels: dashboardData.quiz_activity_chart_data.labels, datasets: datasets },
            options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, scales: { y: { type: 'linear', display: true, position: 'left', beginAtZero: true, ticks: { callback: function(value) { if (value % 1 === 0) { return value; } } } }, y1: { type: 'linear', display: true, position: 'right', beginAtZero: true, grid: { drawOnChartArea: false } } }, plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } } }
        });
    }

    // --- Logic cho các checkbox điều khiển biểu đồ ---
    document.querySelectorAll('.chart-toggle-checkbox').forEach(toggle => {
        toggle.addEventListener('change', function() {
            const chartType = this.dataset.chartType; // 'flashcard' hoặc 'quiz'
            const datasetIndex = parseInt(this.dataset.datasetIndex);
            let chartInstance;

            if (chartType === 'flashcard' && flashcardActivityChartInstance) {
                chartInstance = flashcardActivityChartInstance;
            } else if (chartType === 'quiz' && quizActivityChartInstance) {
                chartInstance = quizActivityChartInstance;
            }

            if (chartInstance) {
                chartInstance.setDatasetVisibility(datasetIndex, !this.checked);
                chartInstance.update();
            }
        });
    });

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

    // --- Logic hiển thị chi tiết bộ (Flashcard & Quiz) ---
    const flashcardSetSelector = document.getElementById('flashcardSetSelector');
    const flashcardSetDetailsContainer = document.getElementById('flashcard-set-details-container');
    
    const quizSetSelector = document.getElementById('quizSetSelector');
    const quizSetDetailsContainer = document.getElementById('quiz-set-details-container');

    /**
     * Mô tả: Hiển thị chi tiết bộ thẻ/câu hỏi dựa trên loại và ID.
     * @param {string} type - Loại bộ ('flashcard' hoặc 'quiz').
     * @param {string} setId - ID của bộ.
     */
    function displaySetDetails(type, setId) {
        let detailsContainer;
        let setData;

        if (type === 'flashcard') {
            detailsContainer = flashcardSetDetailsContainer;
            setData = dashboardData.sets_stats[setId];
        } else if (type === 'quiz') {
            detailsContainer = quizSetDetailsContainer;
            setData = dashboardData.quiz_sets_stats[setId];
        }

        if (!setId || !setData) {
            if (detailsContainer) {
                detailsContainer.style.display = 'none';
            }
            return;
        }

        if (detailsContainer) {
            detailsContainer.style.display = 'block';
            const stats = setData.stat_values;
            let percentage = 0;
            let totalItems = 0;
            let learnedItems = 0;

            if (type === 'flashcard') {
                totalItems = setData.total_cards;
                learnedItems = setData.learned_cards;
                percentage = totalItems > 0 ? (learnedItems * 100 / totalItems).toFixed(0) : 0;
            } else if (type === 'quiz') {
                totalItems = setData.total_questions;
                learnedItems = setData.answered_questions;
                percentage = totalItems > 0 ? (learnedItems * 100 / totalItems).toFixed(0) : 0;
            }

            let statsHtml = '';
            if (type === 'flashcard') {
                statsHtml = `
                    <div class="key-stats-grid-2x3">
                        <div class="key-stat-card learning clickable-stat-card" data-category="learning" data-type="flashcard">
                            <span class="key-stat-value">${stats.learning}</span>
                            <span class="key-stat-label">Đang học</span>
                        </div>
                        <div class="key-stat-card mastered clickable-stat-card" data-category="mastered" data-type="flashcard">
                            <span class="key-stat-value">${stats.mastered}</span>
                            <span class="key-stat-label">Nhớ sâu</span>
                        </div>
                        <div class="key-stat-card unseen clickable-stat-card" data-category="unseen" data-type="flashcard">
                            <span class="key-stat-value">${stats.unseen}</span>
                            <span class="key-stat-label">Chưa học</span>
                        </div>
                        <div class="key-stat-card due clickable-stat-card" data-category="due" data-type="flashcard">
                            <span class="key-stat-value">${stats.due}</span>
                            <span class="key-stat-label">Cần ôn</span>
                        </div>
                        <div class="key-stat-card due-soon clickable-stat-card" data-category="due_soon" data-type="flashcard">
                            <span class="key-stat-value">${stats.due_soon}</span>
                            <span class="key-stat-label">Sắp đến hạn</span>
                        </div>
                        <div class="key-stat-card lapsed clickable-stat-card" data-category="lapsed" data-type="flashcard">
                            <span class="key-stat-value">${stats.lapsed}</span>
                            <span class="key-stat-label">Hay sai</span>
                        </div>
                    </div>
                `;
            } else if (type === 'quiz') {
                statsHtml = `
                    <div class="key-stats-grid-2x3">
                        <div class="key-stat-card correct clickable-stat-card" data-category="correct" data-type="quiz">
                            <span class="key-stat-value">${stats.correct}</span>
                            <span class="key-stat-label">Đúng</span>
                        </div>
                        <div class="key-stat-card incorrect clickable-stat-card" data-category="incorrect" data-type="quiz">
                            <span class="key-stat-value">${stats.incorrect}</span>
                            <span class="key-stat-label">Sai</span>
                        </div>
                        <div class="key-stat-card unanswered clickable-stat-card" data-category="unanswered" data-type="quiz">
                            <span class="key-stat-value">${stats.unanswered}</span>
                            <span class="key-stat-label">Chưa trả lời</span>
                        </div>
                        <div class="key-stat-card mastered clickable-stat-card" data-category="mastered" data-type="quiz">
                            <span class="key-stat-value">${stats.mastered}</span>
                            <span class="key-stat-label">Đã thành thạo</span>
                        </div>
                    </div>
                `;
            }

            detailsContainer.innerHTML = `
                <div class="progress-bar-new">
                    <div class="progress-bar-fill-new" style="width: ${percentage}%;"></div>
                    <span class="progress-bar-text-new">${percentage}% (${learnedItems}/${totalItems})</span>
                </div>
                ${statsHtml}
            `;
            
            addEventListenersToStatCards(); // Gọi lại để gắn sự kiện cho các thẻ mới
        }
    }

    // Gắn sự kiện cho selector Flashcard
    if (flashcardSetSelector && flashcardSetDetailsContainer) {
        flashcardSetSelector.addEventListener('change', function () {
            displaySetDetails('flashcard', this.value);
        });
        const currentSetId = document.querySelector('.set-selector-container[data-type="flashcard"]').dataset.currentSetId;
        if (currentSetId && dashboardData.sets_stats[currentSetId]) {
            flashcardSetSelector.value = currentSetId;
            flashcardSetSelector.dispatchEvent(new Event('change'));
        }
    }

    // Gắn sự kiện cho selector Quiz
    if (quizSetSelector && quizSetDetailsContainer) {
        quizSetSelector.addEventListener('change', function () {
            displaySetDetails('quiz', this.value);
        });
        // Không có current_set_id cho Quiz, nên không cần dispatch Event khi tải trang
    }


    // --- Logic cho Modal danh sách thẻ/câu hỏi ---
    const modal = document.getElementById('card-list-modal');
    const modalCloseBtn = document.getElementById('card-list-modal-close-btn');
    const modalTitle = document.getElementById('card-list-modal-title');
    const cardListContainer = document.getElementById('card-list-container');
    const paginationContainer = document.getElementById('card-list-pagination');

    const categoryTitles = {
        // Flashcard categories
        flashcard: {
            due: 'Các thẻ cần ôn',
            mastered: 'Các thẻ đã nhớ sâu',
            lapsed: 'Các thẻ hay sai',
            learning: 'Các thẻ đang học',
            unseen: 'Các thẻ chưa học',
            due_soon: 'Các thẻ sắp đến hạn'
        },
        // Quiz categories (simplified for now, API needs to support these)
        quiz: {
            correct: 'Các câu hỏi đã trả lời đúng',
            incorrect: 'Các câu hỏi đã trả lời sai',
            unanswered: 'Các câu hỏi chưa trả lời',
            mastered: 'Các câu hỏi đã thành thạo'
        }
    };

    /**
     * Mô tả: Tải và hiển thị danh sách thẻ hoặc câu hỏi trong modal.
     * @param {string} type - Loại ('flashcard' hoặc 'quiz').
     * @param {string} setId - ID của bộ.
     * @param {string} category - Danh mục (ví dụ: 'due', 'correct').
     * @param {number} page - Số trang.
     */
    async function fetchAndShowItems(type, setId, category, page = 1) {
        modal.style.display = 'flex';
        modalTitle.textContent = categoryTitles[type][category] || 'Danh sách';
        cardListContainer.innerHTML = '<div class="loader-container"><div class="loader"></div></div>';
        paginationContainer.innerHTML = '';
        
        let apiUrl = '';
        if (type === 'flashcard') {
            apiUrl = `/api/cards_by_category/${setId}/${category}?page=${page}`;
        } else if (type === 'quiz') {
            // LƯU Ý: Endpoint API này cần được tạo trong web_app/routes/api.py
            // Hiện tại, nó sẽ không hoạt động nếu chưa có API tương ứng.
            // Ví dụ: /api/quiz_questions_by_category/<set_id>/<category>?page=<page>
            apiUrl = `/api/quiz_questions_by_category/${setId}/${category}?page=${page}`;
            // Để tránh lỗi 404 khi API chưa có, có thể tạm thời bỏ qua hoặc hiển thị thông báo.
            cardListContainer.innerHTML = `<p style="text-align: center;">Chức năng này đang được phát triển cho Quiz.</p>`;
            paginationContainer.innerHTML = '';
            return; 
        }

        try {
            const response = await fetch(apiUrl);
            if (!response.ok) throw new Error('Lỗi mạng hoặc server.');
            const data = await response.json();
            if (data.status === 'success') {
                renderItems(type, data.cards || data.questions); // API có thể trả về 'cards' hoặc 'questions'
                renderPagination(type, data.pagination, setId, category);
            } else {
                throw new Error(data.message || 'Lỗi không xác định.');
            }
        } catch (error) {
            cardListContainer.innerHTML = `<p style="color: red; text-align: center;">Không thể tải danh sách: ${error.message}</p>`;
        }
    }

    /**
     * Mô tả: Render danh sách thẻ hoặc câu hỏi vào bảng trong modal.
     * @param {string} type - Loại ('flashcard' hoặc 'quiz').
     * @param {Array} items - Mảng các đối tượng thẻ/câu hỏi.
     */
    function renderItems(type, items) {
        if (!items || items.length === 0) {
            cardListContainer.innerHTML = '<p style="text-align: center;">Không có mục nào trong danh mục này.</p>';
            return;
        }

        let tableHTML = '';
        if (type === 'flashcard') {
            tableHTML = '<table class="card-list-table"><thead><tr><th>Mặt trước</th><th>Mặt sau</th></tr></thead><tbody>';
            items.forEach(item => { tableHTML += `<tr><td>${item.front}</td><td>${item.back}</td></tr>`; });
            tableHTML += '</tbody></table>';
        } else if (type === 'quiz') {
            tableHTML = '<table class="card-list-table"><thead><tr><th>Câu hỏi</th><th>Đáp án A</th><th>Đáp án B</th><th>Đáp án C</th><th>Đáp án D</th><th>Đáp án đúng</th></tr></thead><tbody>';
            items.forEach(item => { 
                tableHTML += `<tr>
                    <td>${item.question}</td>
                    <td>${item.option_a}</td>
                    <td>${item.option_b}</td>
                    <td>${item.option_c}</td>
                    <td>${item.option_d}</td>
                    <td>${item.correct_answer}</td>
                </tr>`; 
            });
            tableHTML += '</tbody></table>';
        }
        cardListContainer.innerHTML = tableHTML;
    }

    /**
     * Mô tả: Render phân trang cho modal.
     * @param {string} type - Loại ('flashcard' hoặc 'quiz').
     * @param {object} pagination - Đối tượng phân trang.
     * @param {string} setId - ID của bộ.
     * @param {string} category - Danh mục.
     */
    function renderPagination(type, pagination, setId, category) {
        paginationContainer.innerHTML = '';
        if (pagination.pages <= 1) return;
        const prevButton = document.createElement('button');
        prevButton.innerHTML = '&laquo;';
        prevButton.disabled = !pagination.has_prev;
        prevButton.addEventListener('click', () => fetchAndShowItems(type, setId, category, pagination.page - 1));
        paginationContainer.appendChild(prevButton);
        const pageInfo = document.createElement('span');
        pageInfo.textContent = `Trang ${pagination.page} / ${pagination.pages}`;
        paginationContainer.appendChild(pageInfo);
        const nextButton = document.createElement('button');
        nextButton.innerHTML = '&raquo;';
        nextButton.disabled = !pagination.has_next;
        nextButton.addEventListener('click', () => fetchAndShowItems(type, setId, category, pagination.page + 1));
        paginationContainer.appendChild(nextButton);
    }

    /**
     * Mô tả: Gắn sự kiện click cho các thẻ thống kê nhỏ trong phần chi tiết bộ.
     */
    function addEventListenersToStatCards() {
        document.querySelectorAll('.clickable-stat-card').forEach(card => {
            card.removeEventListener('click', handleStatCardClick); // Xóa listener cũ để tránh trùng lặp
            card.addEventListener('click', handleStatCardClick); // Gắn listener mới
        });
    }

    /**
     * Mô tả: Hàm xử lý sự kiện click cho các thẻ thống kê nhỏ.
     * @param {Event} event - Đối tượng sự kiện.
     */
    function handleStatCardClick(event) {
        const card = event.currentTarget; // Sử dụng currentTarget để đảm bảo lấy đúng phần tử có listener
        const category = card.dataset.category;
        const type = card.dataset.type; // 'flashcard' hoặc 'quiz'
        
        let selectedSetId;
        if (type === 'flashcard') {
            selectedSetId = flashcardSetSelector.value;
        } else if (type === 'quiz') {
            selectedSetId = quizSetSelector.value;
        }

        if (!selectedSetId) {
            alert(`Vui lòng chọn một bộ ${type === 'flashcard' ? 'thẻ' : 'câu hỏi'} trước.`);
            return;
        }
        fetchAndShowItems(type, selectedSetId, category);
    }

    // Gắn sự kiện ban đầu cho các thẻ thống kê (nếu có)
    addEventListenersToStatCards();

    // Sự kiện đóng modal
    if (modalCloseBtn) modalCloseBtn.addEventListener('click', () => { modal.style.display = 'none'; });
    if (modal) modal.addEventListener('click', function(event) { if (event.target === modal) { modal.style.display = 'none'; } });
});
