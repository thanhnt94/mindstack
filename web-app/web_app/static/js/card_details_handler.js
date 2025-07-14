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
    const summaryTextElement = dynamicCardDetails ? dynamicCardDetails.querySelector('.summary-text') : null;
    const progressBarContainer = document.getElementById('dynamic-island-progress-bar');
    const progressFill = document.getElementById('progressFill'); // Thanh fill của progress bar
    const progressText = document.getElementById('progressText'); // Văn bản trên progress bar

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại
    if (!dynamicCardDetails || !mainFlashcard || !flashcardHeader || !jsDataElement ||
        !dynamicIslandContent || !summaryTextElement || !progressBarContainer ||
        !progressFill || !progressText) {
        console.warn("Thiếu các phần tử HTML cần thiết cho Dynamic Island. Script sẽ không chạy.");
        return;
    }

    // Lấy dữ liệu từ data attributes
    const currentMode = jsDataElement.dataset.currentMode;
    const progressLastReviewed = jsDataElement.dataset.progressLastReviewed; 
    const isNewCard = (progressLastReviewed === '' || progressLastReviewed === 'None'); // Xác định thẻ mới

    // Dữ liệu cho tiến độ bộ thẻ
    const setTotalCards = parseInt(jsDataElement.dataset.setTotalCards || '0');
    const setLearnedCards = parseInt(jsDataElement.dataset.setLearnedCards || '0');
    const setMasteredCards = parseInt(jsDataElement.dataset.setMasteredCards || '0'); // Số thẻ nhớ sâu

    // Dữ liệu cho hiệu suất thẻ cá nhân
    const cardCorrectCount = parseInt(jsDataElement.dataset.cardCorrectCount || '0');
    const cardReviewCount = parseInt(jsDataElement.dataset.cardReviewCount || '0'); // Tổng số lần ôn tập thẻ này

    let animationIntervalId = null; // ID của setInterval để điều khiển vòng lặp animation
    
    // THAY ĐỔI: Tăng thời gian animation lên gấp 3 lần
    const ANIMATION_DURATION_MS = 1000; // Thời gian chạy animation bar (2 giây)
    const TEXT_FADE_DURATION_MS = 1000; // Thời gian mờ/hiện chữ (1 giây)
    const DISPLAY_DURATION_MS = 1000; // Thời gian hiển thị mỗi trạng thái (4 giây)

    /**
     * Mô tả: Tính toán tỷ lệ phần trăm và trả về màu sắc tương ứng.
     * Hàm này vẫn được giữ để tính toán percentage, nhưng colorClass trả về sẽ bị bỏ qua
     * khi chúng ta muốn màu cố định.
     * @param {number} correct - Số lần đúng.
     * @param {number} total - Tổng số lần.
     * @returns {object} {percentage: number, colorClass: string}
     */
    function calculatePerformance(correct, total) {
        if (total === 0) return { percentage: 0, colorClass: 'low-performance' }; 
        const percentage = (correct / total) * 100;
        let colorClass = '';
        if (percentage >= 80) {
            colorClass = 'high-performance'; 
        } else if (percentage >= 60) {
            colorClass = 'medium-performance'; 
        } else {
            colorClass = 'low-performance'; 
        }
        return { percentage: Math.round(percentage), colorClass: colorClass };
    }

    /**
     * Mô tả: Thực hiện hoạt ảnh thanh tiến trình và chuyển đổi văn bản.
     * @param {number} targetPercentage - Phần trăm cuối cùng của thanh bar.
     * @param {string} initialText - Văn bản ban đầu (ví dụ: "X/Y").
     * @param {string} finalPercentageText - Văn bản phần trăm cuối cùng (ví dụ: "Z%").
     * @param {string} colorClass - Lớp CSS cho màu sắc của thanh bar (được truyền cố định).
     * @returns {Promise<void>} Một Promise sẽ được giải quyết khi hoạt ảnh hoàn tất.
     */
    function animateProgressBar(targetPercentage, initialText, finalPercentageText, colorClass) {
        return new Promise(resolve => {
            // Đặt lại trạng thái ban đầu
            progressFill.style.width = '0%';
            progressFill.className = 'progress-fill'; // Xóa tất cả các lớp màu cũ
            progressFill.classList.add(colorClass); // Thêm lớp màu mới cố định
            progressText.innerHTML = initialText; // Sử dụng innerHTML để hiển thị icon
            progressText.style.opacity = '1';

            // Bắt đầu animation thanh bar
            requestAnimationFrame(() => {
                progressFill.style.transition = `width ${ANIMATION_DURATION_MS / 1000}s ease-out`;
                progressFill.style.width = `${targetPercentage}%`;
            });

            // Sau khi animation bar chạy được một nửa, bắt đầu mờ dần chữ ban đầu và hiện chữ phần trăm
            setTimeout(() => {
                progressText.style.transition = `opacity ${TEXT_FADE_DURATION_MS / 1000}s ease-in-out`;
                progressText.style.opacity = '0'; // Mờ dần chữ ban đầu

                setTimeout(() => {
                    progressText.innerHTML = finalPercentageText; // Sử dụng innerHTML để hiển thị icon
                    progressText.style.opacity = '1'; // Hiện chữ phần trăm
                    resolve(); // Giải quyết Promise sau khi chữ cuối cùng hiện ra
                }, TEXT_FADE_DURATION_MS); // Chờ cho chữ ban đầu mờ hết
            }, ANIMATION_DURATION_MS / 2); // Bắt đầu hiệu ứng chữ ở giữa animation bar
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
        if (animationIntervalId) {
            clearInterval(animationIntervalId);
        }

        let animationSequence = [];

        // THAY ĐỔI LOGIC CHUỖI ANIMATION DỰA TRÊN THẺ CŨ/MỚI
        if (!isNewCard) { // Thẻ cũ (đã ôn tập)
            // 1. Màu vàng: Số thẻ nhớ sâu / Số thẻ đã học
            const masteredLearnedPercentage = setLearnedCards > 0 ? (setMasteredCards / setLearnedCards) * 100 : 0;
            const masteredLearnedInitialText = `<i class="fas fa-brain"></i> Trí nhớ dài hạn: ${setMasteredCards} / ${setLearnedCards}`;
            const masteredLearnedFinalText = `<i class="fas fa-brain"></i> ${Math.round(masteredLearnedPercentage)}%`;
            animationSequence.push(async () => {
                await animateProgressBar(masteredLearnedPercentage, masteredLearnedInitialText, masteredLearnedFinalText, 'medium-performance'); // Luôn màu vàng
                await new Promise(resolve => setTimeout(resolve, DISPLAY_DURATION_MS));
            });

            // 2. Xanh lá cây: Số lần đáp đúng / Tổng số lần ôn tập (của thẻ này)
            const cardPerformance = calculatePerformance(cardCorrectCount, cardReviewCount); // Vẫn dùng để lấy percentage
            const cardInitialText = `<i class="fas fa-check-circle"></i> Số lần đáp đúng: ${cardCorrectCount} / ${cardReviewCount}`;
            const cardFinalText = `<i class="fas fa-check-circle"></i> ${cardPerformance.percentage}%`;
            animationSequence.push(async () => {
                await animateProgressBar(cardPerformance.percentage, cardInitialText, cardFinalText, 'high-performance'); // Luôn màu xanh lá
                await new Promise(resolve => setTimeout(resolve, DISPLAY_DURATION_MS));
            });

            // 3. Xanh nước biển: Số thẻ đã học / Tổng số thẻ (của bộ)
            const setProgressPercentage = setTotalCards > 0 ? (setLearnedCards / setTotalCards) * 100 : 0;
            const setInitialText = `<i class="fas fa-layer-group"></i> Tiến độ bộ: ${setLearnedCards} / ${setTotalCards}`;
            const setFinalText = `<i class="fas fa-layer-group"></i> ${Math.round(setProgressPercentage)}%`;
            animationSequence.push(async () => {
                await animateProgressBar(setProgressPercentage, setInitialText, setFinalText, 'set-progress-blue'); // Luôn màu xanh nước biển
                await new Promise(resolve => setTimeout(resolve, DISPLAY_DURATION_MS));
            });

        } else { // Thẻ học mới
            // 1. Xanh nước biển: Số thẻ đã học / Tổng số thẻ (của bộ)
            const setProgressPercentage = setTotalCards > 0 ? (setLearnedCards / setTotalCards) * 100 : 0;
            const setInitialText = `<i class="fas fa-layer-group"></i> Tiến độ bộ: ${setLearnedCards} / ${setTotalCards}`;
            const setFinalText = `<i class="fas fa-layer-group"></i> ${Math.round(setProgressPercentage)}%`;
            animationSequence.push(async () => {
                await animateProgressBar(setProgressPercentage, setInitialText, setFinalText, 'set-progress-blue'); // Luôn màu xanh nước biển
                await new Promise(resolve => setTimeout(resolve, DISPLAY_DURATION_MS));
            });

            // 2. Màu vàng: Số thẻ nhớ sâu / Số thẻ đã học
            const masteredLearnedPercentage = setLearnedCards > 0 ? (setMasteredCards / setLearnedCards) * 100 : 0;
            const masteredLearnedInitialText = `<i class="fas fa-brain"></i> Trí nhớ dài hạn: ${masteredLearnedCards} / ${setLearnedCards}`;
            const masteredLearnedFinalText = `<i class="fas fa-brain"></i> ${Math.round(masteredLearnedPercentage)}%`;
            animationSequence.push(async () => {
                await animateProgressBar(masteredLearnedPercentage, masteredLearnedInitialText, masteredLearnedFinalText, 'medium-performance'); // Luôn màu vàng
                await new Promise(resolve => setTimeout(resolve, DISPLAY_DURATION_MS));
            });
        }

        let currentAnimationIndex = 0;

        // Hàm để chạy chuỗi animation
        const runNextAnimation = async () => {
            if (animationSequence.length > 0) {
                await animationSequence[currentAnimationIndex]();
                currentAnimationIndex = (currentAnimationIndex + 1) % animationSequence.length;
            }
        };

        // Chạy animation đầu tiên ngay lập tức
        runNextAnimation();

        // Thiết lập interval để lặp lại chuỗi animation
        // Thời gian interval phải đủ để hoàn thành một chuỗi animation + thời gian hiển thị
        animationIntervalId = setInterval(runNextAnimation, ANIMATION_DURATION_MS + TEXT_FADE_DURATION_MS + DISPLAY_DURATION_MS);
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
            if (animationIntervalId) {
                clearInterval(animationIntervalId);
                animationIntervalId = null;
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
    if (currentMode !== 'autoplay_review') { // Giả định 'autoplay_review' là chế độ không cần dynamic island
        updateDynamicIslandContent();
    } else {
        // Nếu ở chế độ Autoplay, ẩn Dynamic Island
        dynamicCardDetails.style.display = 'none';
    }
});
