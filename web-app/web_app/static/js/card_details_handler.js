// web_app/static/js/card_details_handler.js

/**
 * Mô tả: Xử lý logic cho "Dynamic Island" hiển thị chi tiết thẻ trên giao diện di động.
 * Bao gồm việc mở rộng và thu gọn thông tin khi người dùng nhấn vào,
 * và cập nhật nội dung/thanh tiến trình dựa trên chế độ học.
 */
document.addEventListener('DOMContentLoaded', function() {
    const dynamicCardDetails = document.getElementById('dynamic-card-details'); // Đây là phần tử dynamic island
    const mainFlashcard = document.getElementById('main-flashcard'); // Lấy thẻ flashcard chính
    const flashcardHeader = document.querySelector('.flashcard-header'); // Lấy header của flashcard
    const jsDataElement = document.getElementById('jsData'); // Lấy phần tử chứa dữ liệu JS

    // Các phần tử con của Dynamic Island
    const dynamicIslandContent = dynamicCardDetails ? dynamicCardDetails.querySelector('.dynamic-island-content') : null;
    const summaryTextElement = dynamicCardDetails ? dynamicCardDetails.querySelector('.summary-text') : null;
    const progressBarContainer = document.getElementById('dynamic-island-progress-bar');
    const progressBarFill = progressBarContainer ? progressBarContainer.querySelector('.progress-fill') : null;
    const progressBarText = progressBarContainer ? progressBarContainer.querySelector('.progress-text') : null;

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại
    if (dynamicCardDetails && mainFlashcard && flashcardHeader && jsDataElement &&
        dynamicIslandContent && summaryTextElement && progressBarContainer &&
        progressBarFill && progressBarText) {

        // Lấy dữ liệu từ data attributes
        const currentMode = jsDataElement.dataset.currentMode;
        const correctStreak = parseInt(jsDataElement.dataset.progressCorrectStreak || '0');
        const correctCount = parseInt(jsDataElement.dataset.progressCorrectCount || '0');
        const incorrectCount = parseInt(jsDataElement.dataset.progressIncorrectCount || '0');
        const reviewCount = parseInt(jsDataElement.dataset.progressReviewCount || '0');
        const setTotalCards = parseInt(jsDataElement.dataset.setTotalCards || '0');
        const setLearnedCards = parseInt(jsDataElement.dataset.setLearnedCards || '0');
        const setMasteredCards = parseInt(jsDataElement.dataset.setMasteredCards || '0');
        const setDueCards = parseInt(jsDataElement.dataset.setDueCards || '0'); // Số thẻ cần ôn
        // THAY ĐỔI: Lấy last_reviewed để xác định thẻ mới
        const progressLastReviewed = jsDataElement.dataset.progressLastReviewed; 

        /**
         * Mô tả: Cập nhật nội dung và thanh tiến trình của dynamic island dựa trên chế độ học.
         */
        function updateDynamicIslandContent() {
            let summaryHtml = '';
            let progressPercentage = 0;
            let progressTextContent = '';
            
            // BẮT ĐẦU THAY ĐỔI: Logic xác định thẻ mới dựa trên progressLastReviewed
            // Thẻ được coi là mới nếu last_reviewed của nó là rỗng hoặc 'None'
            const isNewCard = (progressLastReviewed === '' || progressLastReviewed === 'None');

            // Ẩn cả hai phần tử trước khi quyết định hiển thị cái nào
            dynamicIslandContent.style.display = 'none';
            progressBarContainer.style.display = 'none';

            if (isNewCard) {
                // Đây là thẻ mới: hiển thị tiến độ học mới (màu xanh lá)
                summaryHtml = `<span class="summary-value">${setLearnedCards}</span> / <span class="summary-value">${setTotalCards}</span>`;
                progressPercentage = setTotalCards > 0 ? (setLearnedCards / setTotalCards) * 100 : 0;
                progressTextContent = `${setLearnedCards} / ${setTotalCards}`; 

                // Hiển thị thanh tiến trình
                progressBarContainer.style.display = 'flex';
                progressBarFill.style.width = `${progressPercentage}%`;
                progressBarFill.classList.remove('review-mode-color'); // Đảm bảo màu xanh lá
                progressBarText.textContent = progressTextContent;

            } else {
                // Đây là thẻ đã học (đang trong chế độ ôn tập): hiển thị tiến độ ôn tập (màu vàng cam)
                summaryHtml = `
                    <span class="summary-value correct-streak">${correctStreak}</span>
                    <span class="summary-separator">/</span>
                    <span class="summary-value correct-count">${correctCount}</span>
                    <span class="summary-separator">/</span>
                    <span class="summary-value incorrect-count">${incorrectCount}</span>
                    <span class="summary-separator">/</span>
                    <span class="summary-value review-count">${reviewCount}</span>
                `;
                // Tính toán phần trăm "số từ đã nhớ sâu / tổng số từ đã học"
                // Số thẻ đã nhớ sâu = setLearnedCards - setDueCards (trong số các thẻ đã học)
                progressPercentage = setLearnedCards > 0 ? ((setLearnedCards - setDueCards) / setLearnedCards) * 100 : 0;
                progressTextContent = `${setLearnedCards - setDueCards} / ${setLearnedCards}`; // Số thẻ đã nhớ sâu / Tổng số thẻ đã học

                // Hiển thị thanh tiến trình
                progressBarContainer.style.display = 'flex';
                progressBarFill.style.width = `${progressPercentage}%`;
                progressBarFill.classList.add('review-mode-color'); // Đảm bảo màu vàng cam
                progressBarText.textContent = progressTextContent;
            }

            // Cập nhật nội dung tóm tắt
            summaryTextElement.innerHTML = summaryHtml;
        }

        /**
         * Mô tả: Mở/Đóng dynamic island.
         * @param {Event} event Đối tượng sự kiện click.
         */
        function toggleDetails(event) {
            // Ngăn chặn sự kiện click lan ra các phần tử bên dưới khi dynamic island được nhấp
            event.stopPropagation();

            // Toggle lớp 'expanded' để mở/đóng phần chi tiết
            dynamicCardDetails.classList.toggle('expanded');

            // Điều chỉnh hiển thị của summary và progress bar khi mở rộng/thu gọn
            if (dynamicCardDetails.classList.contains('expanded')) {
                dynamicIslandContent.style.display = 'flex'; // Luôn hiển thị nội dung khi mở rộng
                progressBarContainer.style.display = 'none'; // Ẩn thanh tiến trình khi mở rộng
            } else {
                // Khi thu gọn, gọi lại hàm để quyết định hiển thị gì dựa trên chế độ
                updateDynamicIslandContent();
            }
        }

        // Gắn sự kiện click cho dynamic island
        dynamicCardDetails.addEventListener('click', toggleDetails);

        /**
         * Mô tả: Đóng dynamic island khi click ra ngoài (ngoại trừ các nút header).
         * @param {Event} event Đối tượng sự kiện click.
         */
        window.addEventListener('click', function(event) {
            const headerLeft = flashcardHeader.querySelector('.header-left');
            const headerRight = flashcardHeader.querySelector('.header-right');

            // Kiểm tra nếu dynamic island đang mở và click không phải vào dynamic island
            // và click không phải vào các nút header
            if (dynamicCardDetails.classList.contains('expanded') && 
                !dynamicCardDetails.contains(event.target) &&
                !headerLeft.contains(event.target) && 
                !headerRight.contains(event.target)
            ) {
                // Đóng dynamic island
                dynamicCardDetails.classList.remove('expanded');
                // Gọi lại hàm để cập nhật nội dung sau khi đóng
                updateDynamicIslandContent();
            }
        });

        // Gọi hàm cập nhật lần đầu khi tải trang để thiết lập trạng thái ban đầu
        updateDynamicIslandContent();
    }
});
