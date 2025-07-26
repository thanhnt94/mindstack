/**
 * web_app/static/js/ai_handler.js
 * Xử lý logic cho tính năng giải thích bằng AI thông qua modal.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Lấy các phần tử DOM cần thiết
    const openAiModalBtn = document.getElementById('open-ai-modal-btn');
    const aiModal = document.getElementById('ai-explanation-modal');
    const closeAiModalBtn = document.getElementById('ai-modal-close-btn');
    const closeFooterBtn = document.getElementById('ai-modal-close-footer-btn');
    const aiModalBody = document.getElementById('ai-modal-body');
    const jsData = document.getElementById('jsData');

    // Nếu không tìm thấy các phần tử cơ bản, dừng lại.
    if (!openAiModalBtn || !aiModal || !jsData) {
        return;
    }

    // --- BẮT ĐẦU SỬA LỖI: Luôn ẩn modal khi trang tải ---
    // Đảm bảo modal được ẩn ngay từ đầu để tránh lỗi CSS
    aiModal.style.display = 'none';
    // --- KẾT THÚC SỬA LỖI ---


    // --- BẮT ĐẦU SỬA LỖI: Logic ẩn/hiện nút bấm AI ---
    /**
     * Kiểm tra trạng thái của thẻ (mặt trước/sau) và quyết định có hiển thị nút AI hay không.
     */
    function toggleAiButtonVisibility() {
        const isFront = jsData.dataset.isFront === 'true';
        if (isFront) {
            // Nếu là mặt trước, ẩn nút đi
            openAiModalBtn.style.display = 'none';
        } else {
            // Nếu là mặt sau, hiển thị nút
            openAiModalBtn.style.display = 'flex';
        }
    }

    // Chạy hàm kiểm tra ngay khi trang được tải
    toggleAiButtonVisibility();
    // --- KẾT THÚC SỬA LỖI ---


    /**
     * Mở modal và bắt đầu quá trình lấy dữ liệu.
     */
    function openModal() {
        aiModal.style.display = 'flex'; // Sử dụng flex để căn giữa
        fetchAndDisplayExplanation();
    }

    /**
     * Đóng modal và reset nội dung.
     */
    function closeModal() {
        aiModal.style.display = 'none';
        aiModalBody.innerHTML = ''; // Xóa nội dung cũ khi đóng
    }

    /**
     * Gọi API để lấy giải thích và hiển thị vào modal.
     */
    function fetchAndDisplayExplanation() {
        const itemId = jsData.dataset.flashcardId;
        const itemType = 'flashcard'; // Luôn là flashcard ở trang này

        if (!itemId) {
            console.error('Không tìm thấy flashcard ID.');
            aiModalBody.innerHTML = '<p class="error-message">Lỗi: Không thể xác định thẻ hiện tại.</p>';
            return;
        }

        // Hiển thị trạng thái đang tải
        aiModalBody.innerHTML = '<div class="loader"></div><p style="text-align: center;"><em>Đang kết nối với trợ lý AI...</em></p>';

        // Gọi API
        fetch(`/api/get_explanation?type=${itemType}&id=${itemId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Lỗi mạng hoặc server: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                    aiModalBody.innerHTML = `<p class="error-message">Lỗi: ${data.error}</p>`;
                } else {
                    if (typeof showdown === 'undefined') {
                        console.error('Thư viện Showdown.js chưa được tải.');
                        aiModalBody.innerText = data.explanation; // Hiển thị text thô
                        return;
                    }
                    // Chuyển đổi Markdown sang HTML và hiển thị
                    const converter = new showdown.Converter({
                        tables: true,
                        strikethrough: true,
                        tasklists: true
                    });
                    const htmlContent = converter.makeHtml(data.explanation);
                    aiModalBody.innerHTML = htmlContent;
                }
            })
            .catch(error => {
                console.error('Lỗi khi lấy giải thích từ AI:', error);
                aiModalBody.innerHTML = '<p class="error-message" style="text-align: center;">Không thể tải giải thích. Vui lòng thử lại sau.</p>';
            });
    }

    // Gán sự kiện cho các nút
    openAiModalBtn.addEventListener('click', openModal);
    closeAiModalBtn.addEventListener('click', closeModal);
    closeFooterBtn.addEventListener('click', closeModal);

    // Đóng modal khi click ra ngoài vùng nội dung
    window.addEventListener('click', function(event) {
        if (event.target === aiModal) {
            closeModal();
        }
    });
});
