// web_app/static/js/card_details_handler.js

/**
 * Mô tả: Xử lý logic cho "Dynamic Island" hiển thị chi tiết thẻ trên giao diện di động.
 * Bao gồm việc mở rộng và thu gọn thông tin khi người dùng nhấn vào,
 * và cập nhật nội dung/thanh tiến trình dựa trên chế độ học.
 * Đặc biệt, thêm hiệu ứng "đảo động" cho thanh bar khi thu gọn, bao gồm hoạt ảnh chạy và chuyển đổi nội dung.
 */
document.addEventListener('DOMContentLoaded', function() {
    const dynamicCardDetails = document.getElementById('dynamic-card-details'); // Đây là phần tử dynamic island
    const mainFlashcard = document.getElementById('main-flashcard'); // Lấy thẻ flashcard chính
    const flashcardHeader = document.querySelector('.flashcard-header'); // Lấy header của flashcard
    const jsDataElement = document.getElementById('jsData'); // Lấy phần tử chứa dữ liệu JS

    // Các phần tử con của Dynamic Island
    const dynamicIslandContent = dynamicCardDetails ? dynamicCardDetails.querySelector('.dynamic-island-content') : null;
    const progressBarContainer = document.getElementById('dynamic-island-progress-bar');
    const progressFill = document.getElementById('progressFill'); // Thanh fill của progress bar
    const progressText = document.getElementById('progressText'); // Văn bản trên progress bar

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại
    if (!dynamicCardDetails || !mainFlashcard || !flashcardHeader || !jsDataElement ||
        !dynamicIslandContent || !progressBarContainer ||
        !progressFill || !progressText) {
        console.warn("Thiếu các phần tử HTML cần thiết cho Dynamic Island. Script sẽ không chạy.");
        return;
    }

    // Lấy dữ liệu từ data attributes
    const currentMode = jsDataElement.dataset.currentMode;
    const progressLastReviewed = jsDataElement.dataset.progressLastReviewed; 
    const isNewCard = (progressLastReviewed === '' || progressLastReviewed === 'None'); // Xác định thẻ mới

    let animationTimeoutId = null; 
    
    // Các hằng số thời gian cho animation
    const ANIMATION_DURATION_MS = 1000; // Thời gian chạy animation bar (1 giây)
    const TEXT_FADE_DURATION_MS = 500; // Thời gian mờ/hiện chữ (0.5 giây)
    const PERCENTAGE_DELAY_MS = 2000; // Thời gian chờ trước khi hiển thị % (2 giây)
    const DISPLAY_DURATION_MS = 2000; // Thời gian hiển thị mỗi trạng thái sau khi animation hoàn tất (2 giây)

    // Ánh xạ lớp màu CSS sang giá trị hex để đặt border-color
    const colorClassToHex = {
        'reviewed-progress-color': '#FFB6C1', // Tím
        'high-performance': '#28a745',        // Xanh lá cây
        'medium-performance': '#ffc107',      // Vàng/Cam
        'set-progress-blue': '#3498db'        // Xanh nước biển
    };

    /**
     * Mô tả: Cập nhật trạng thái hiển thị của thanh tiến trình Dynamic Island.
     * @param {object} state - Đối tượng chứa trạng thái hiển thị:
     * - type: 'progress' hoặc 'text'
     * - percentage: (chỉ cho type='progress') Phần trăm để điền thanh bar.
     * - initialText: (chỉ cho type='progress') Văn bản ban đầu hiển thị trên thanh.
     * - percentageText: (chỉ cho type='progress') Văn bản hiển thị % trên thanh sau delay.
     * - text: (chỉ cho type='text') Văn bản hiển thị trên thanh.
     * - iconClass: Lớp icon Font Awesome.
     * - colorClass: (chỉ cho type='progress') Lớp màu cho thanh bar.
     * - specialClass: (tùy chọn) Lớp CSS đặc biệt để áp dụng cho progressBarContainer (ví dụ: animation border).
     * @returns {Promise<void>}
     */
    function displayDynamicIslandState(state) {
        return new Promise(resolve => {
            // Reset progressFill styles
            progressFill.style.transition = `none`; // Tắt transition để reset ngay lập tức
            progressFill.style.width = '0%';
            progressFill.className = 'progress-fill'; // Reset tất cả các lớp màu cũ

            // Xóa bất kỳ lớp đặc biệt nào trên progressBarContainer
            progressBarContainer.classList.remove('animated-border'); // Xóa lớp animation border cũ
            progressBarContainer.style.borderColor = 'transparent'; // Reset viền về trong suốt

            // Hiển thị văn bản ban đầu (hoặc văn bản tĩnh) ngay lập tức
            progressText.innerHTML = `<i class="${state.iconClass}"></i> ${state.initialText || state.text}`;
            progressText.style.transition = `none`; // Không có transition cho hiển thị ban đầu
            progressText.style.opacity = '1';

            if (state.type === 'progress') {
                progressFill.classList.add(state.colorClass);
                // Đặt màu viền trùng với màu bar
                if (colorClassToHex[state.colorClass]) {
                    progressBarContainer.style.borderColor = colorClassToHex[state.colorClass];
                }

                // Bắt đầu animation width
                requestAnimationFrame(() => {
                    progressFill.style.transition = `width ${ANIMATION_DURATION_MS / 1000}s ease-out`;
                    progressFill.style.width = `${state.percentage}%`;
                });

                // Sau PERCENTAGE_DELAY_MS, mờ dần văn bản ban đầu, sau đó thay đổi và hiện văn bản phần trăm
                setTimeout(() => {
                    progressText.style.transition = `opacity ${TEXT_FADE_DURATION_MS / 1000}s ease-in-out`;
                    progressText.style.opacity = '0'; // Mờ dần văn bản ban đầu

                    setTimeout(() => {
                        progressText.innerHTML = `<i class="${state.iconClass}"></i> ${state.percentageText}`; // Thay đổi văn bản thành chỉ %
                        progressText.style.opacity = '1'; // Hiện văn bản phần trăm
                        // SỬA LỖI: Resolve Promise sau khi văn bản phần trăm đã hiện ra hoàn toàn
                        // và sau khi animation bar đã chạy xong (đảm bảo hiển thị mượt mà)
                        setTimeout(resolve, TEXT_FADE_DURATION_MS); 
                    }, TEXT_FADE_DURATION_MS); // Chờ cho fade out hoàn tất trước khi thay đổi văn bản
                }, PERCENTAGE_DELAY_MS); // Chờ theo yêu cầu của người dùng (2 giây)
            } else { // type === 'text' (văn bản tĩnh như copyright)
                progressFill.style.width = '0%'; // Không có fill cho các trạng thái chỉ có văn bản

                // Áp dụng lớp đặc biệt nếu có (ví dụ: animated border cho copyright)
                if (state.specialClass) {
                    progressBarContainer.classList.add(state.specialClass);
                }
                
                // SỬA LỖI: Resolve Promise sau khi văn bản tĩnh đã hiện ra hoàn toàn
                setTimeout(resolve, TEXT_FADE_DURATION_MS); 
            }
        });
    }


    /**
     * Mô tả: Cập nhật nội dung và thanh tiến trình của dynamic island dựa trên chế độ học.
     * Thực hiện hiệu ứng "đảo động" giữa các thông tin.
     */
    async function updateDynamicIslandContent() {
        // Luôn hiển thị thanh tiến trình khi thu gọn
        progressBarContainer.style.display = 'flex';
        dynamicIslandContent.style.display = 'none'; // Đảm bảo nội dung đầy đủ ẩn

        // Dừng bất kỳ animation đang chạy nào
        if (animationTimeoutId) { 
            clearTimeout(animationTimeoutId); 
            animationTimeoutId = null;
        }

        let animationSequence = [];

        // Lấy dữ liệu mới nhất từ data attributes (đảm bảo cập nhật nếu có thay đổi)
        const setTotalCards = parseInt(jsDataElement.dataset.setTotalCards || '0');
        const setLearnedCards = parseInt(jsDataElement.dataset.setLearnedCards || '0');
        const setMasteredCards = parseInt(jsDataElement.dataset.setMasteredCards || '0');
        const setDueCards = parseInt(jsDataElement.dataset.setDueCards || '0'); // Lấy số thẻ cần ôn
        const cardCorrectCount = parseInt(jsDataElement.dataset.cardCorrectCount || '0');
        const cardReviewCount = parseInt(jsDataElement.dataset.cardReviewCount || '0');

        if (!isNewCard) { // Thẻ cũ (đã ôn tập)
            // 1. Đã ôn tập: (số thẻ đã học - số thẻ cần ôn tập)/ số thẻ đã học 
            const reviewedCardsNotDue = setLearnedCards - setDueCards;
            const reviewedProgressPercentage = setLearnedCards > 0 ? (reviewedCardsNotDue / setLearnedCards) * 100 : 0;
            animationSequence.push({
                type: 'progress',
                percentage: Math.round(reviewedProgressPercentage),
                initialText: `Đã ôn tập: ${reviewedCardsNotDue} / ${setLearnedCards}`,
                percentageText: `${Math.round(reviewedProgressPercentage)}%`, // Chỉ %
                iconClass: 'fas fa-history',
                colorClass: 'reviewed-progress-color' // Màu tím
            });

            // 2. Số lần đáp đúng (của thẻ này) - HIỂN THỊ PHẦN TRĂM
            const cardCorrectPercentage = cardReviewCount > 0 ? (cardCorrectCount / cardReviewCount) * 100 : 0;
            animationSequence.push({
                type: 'progress',
                percentage: Math.round(cardCorrectPercentage),
                initialText: `Đúng: ${cardCorrectCount} / ${cardReviewCount}`,
                percentageText: `${Math.round(cardCorrectPercentage)}%`, // Chỉ %
                iconClass: 'fas fa-check-circle',
                colorClass: 'high-performance' // Màu xanh lá cây
            });

            // 3. Bộ nhớ dài hạn: (số thẻ nhớ sâu / số thẻ đã học)
            const masteredPercentage = setLearnedCards > 0 ? (setMasteredCards / setLearnedCards) * 100 : 0;
            animationSequence.push({
                type: 'progress',
                percentage: Math.round(masteredPercentage),
                initialText: `Nhớ sâu: ${setMasteredCards} / ${setLearnedCards}`,
                percentageText: `${Math.round(masteredPercentage)}%`, // Chỉ %
                iconClass: 'fas fa-brain',
                colorClass: 'medium-performance' // Màu vàng/cam
            });

            // 4. Số thẻ đã học (của bộ)
            const learnedSetProgressPercentage = setTotalCards > 0 ? (setLearnedCards / setTotalCards) * 100 : 0;
            animationSequence.push({
                type: 'progress',
                percentage: Math.round(learnedSetProgressPercentage),
                initialText: `Đã học: ${setLearnedCards} / ${setTotalCards}`,
                percentageText: `${Math.round(learnedSetProgressPercentage)}%`, // Chỉ %
                iconClass: 'fas fa-graduation-cap',
                colorClass: 'set-progress-blue' // Màu xanh nước biển
            });

            // 5. Mind Stack by thanhnt94
            animationSequence.push({
                type: 'text',
                text: 'Mind Stack by thanhnt94',
                iconClass: 'fas fa-book',
                specialClass: 'animated-border' // Kích hoạt animation border
            });

        } else { // Thẻ mới lần đầu (chưa xuất hiện bao giờ)
            // 1. Số thẻ đã học (của bộ)
            const learnedSetProgressPercentage = setTotalCards > 0 ? (setLearnedCards / setTotalCards) * 100 : 0;
            animationSequence.push({
                type: 'progress',
                percentage: Math.round(learnedSetProgressPercentage),
                initialText: `Đã học: ${setLearnedCards} / ${setTotalCards}`,
                percentageText: `${Math.round(learnedSetProgressPercentage)}%`, // Chỉ %
                iconClass: 'fas fa-graduation-cap',
                colorClass: 'set-progress-blue' // Màu xanh nước biển
            });

            // 2. Bộ nhớ dài hạn: (số thẻ nhớ sâu / số thẻ đã học)
            const masteredPercentage = setLearnedCards > 0 ? (setMasteredCards / setLearnedCards) * 100 : 0;
            animationSequence.push({
                type: 'progress',
                percentage: Math.round(masteredPercentage),
                initialText: `Nhớ sâu: ${setMasteredCards} / ${setLearnedCards}`,
                percentageText: `${Math.round(masteredPercentage)}%`, // Chỉ %
                iconClass: 'fas fa-brain',
                colorClass: 'medium-performance' // Màu vàng/cam
            });

            // 3. Mind Stack by thanhnt94
            animationSequence.push({
                type: 'text',
                text: 'Mind Stack by thanhnt94',
                iconClass: 'fas fa-book',
                specialClass: 'animated-border' // Kích hoạt animation border
            });
        }

        let currentAnimationIndex = 0;

        // Hàm để chạy chuỗi animation
        const runNextAnimation = async () => {
            if (animationSequence.length === 0) {
                // Nếu không có trạng thái nào, dừng lại
                return;
            }

            const state = animationSequence[currentAnimationIndex];
            await displayDynamicIslandState(state);
            
            // Tính toán thời gian chờ cho trạng thái tiếp theo
            let delayForNextState;
            if (state.type === 'progress') {
                // Tổng thời gian một trạng thái progress hiển thị:
                // PERCENTAGE_DELAY_MS (văn bản ban đầu)
                // + TEXT_FADE_DURATION_MS (mờ đi)
                // + TEXT_FADE_DURATION_MS (hiện lên %)
                // + DISPLAY_DURATION_MS (thời gian giữ)
                delayForNextState = PERCENTAGE_DELAY_MS + (2 * TEXT_FADE_DURATION_MS) + DISPLAY_DURATION_MS;
            } else { // type === 'text'
                // Tổng thời gian một trạng thái text hiển thị:
                // TEXT_FADE_DURATION_MS (hiện lên)
                // + DISPLAY_DURATION_MS (thời gian giữ)
                delayForNextState = TEXT_FADE_DURATION_MS + DISPLAY_DURATION_MS;
            }

            currentAnimationIndex = (currentAnimationIndex + 1) % animationSequence.length;
            
            // Lên lịch cho lần chạy tiếp theo
            animationTimeoutId = setTimeout(runNextAnimation, delayForNextState);
        };

        // Gọi runNextAnimation lần đầu tiên ngay lập tức để khởi động chuỗi
        runNextAnimation();
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
            // Khi mở rộng: hiển thị nội dung đầy đủ, ẩn thanh bar và dừng animation
            dynamicIslandContent.style.display = 'flex'; 
            progressBarContainer.style.display = 'none'; 
            if (animationTimeoutId) { 
                clearTimeout(animationTimeoutId); 
                animationTimeoutId = null;
            }
        } else {
            // Khi thu gọn: ẩn nội dung đầy đủ, hiển thị thanh bar và khởi động lại animation
            dynamicIslandContent.style.display = 'none';
            progressBarContainer.style.display = 'flex';
            updateDynamicIslandContent(); // Khởi động lại animation khi thu gọn
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
    // Chỉ chạy khi không ở chế độ Autoplay
    if (currentMode !== 'autoplay_review') { 
        updateDynamicIslandContent();
    } else {
        // Nếu ở chế độ Autoplay, ẩn Dynamic Island
        dynamicCardDetails.style.display = 'none';
    }
});
