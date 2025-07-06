// card_content_adjuster.js

document.addEventListener('DOMContentLoaded', function() {
    // Lấy các phần tử DOM cần thiết
    const flashcardElement = document.querySelector('.flashcard');
    const scrollableContent = document.querySelector('.scrollable-card-content');
    const cardText = document.querySelector('.card-text');

    /**
     * Mô tả: Kiểm tra và áp dụng class CSS phù hợp cho mặt sau thẻ
     * dựa trên số lượng dòng và trạng thái tràn (overflow) của nội dung.
     *
     * - Nếu mặt sau chỉ có 1 dòng: Thêm class 'is-single-line' (để CSS căn giữa hoàn toàn).
     * - Nếu mặt sau có nhiều dòng nhưng không tràn: Thêm class 'is-multi-line' (để CSS căn giữa dọc, căn trái ngang).
     * - Nếu mặt sau có nhiều dòng và bị tràn (có scroll): Thêm class 'is-overflow' (để CSS căn trên dọc, căn trái ngang).
     */
    function adjustBackSideContentLayout() {
        if (!flashcardElement || !scrollableContent || !cardText) {
            console.warn("Không tìm thấy các phần tử cần thiết để điều chỉnh layout nội dung thẻ.");
            return;
        }

        // Chỉ áp dụng logic này cho mặt sau thẻ
        if (flashcardElement.classList.contains('is-back-side')) {
            // Xóa tất cả các class liên quan đến layout mặt sau trước khi áp dụng cái mới
            flashcardElement.classList.remove('is-single-line', 'is-multi-line', 'is-overflow');

            // Tính toán chiều cao của một dòng văn bản (ước lượng)
            // Có thể lấy line-height hoặc ước lượng từ font-size
            const lineHeight = parseFloat(getComputedStyle(cardText).lineHeight) || parseFloat(getComputedStyle(cardText).fontSize) * 1.2;
            
            // Lấy chiều cao hiển thị của container và chiều cao đầy đủ của nội dung
            const contentDisplayHeight = scrollableContent.clientHeight;
            const contentFullHeight = cardText.scrollHeight;

            // Ước tính số dòng
            const estimatedLines = contentFullHeight / lineHeight;

            if (contentFullHeight <= contentDisplayHeight) {
                // Nội dung không bị tràn (không có scrollbar)
                if (estimatedLines <= 1.5) { // Dùng 1.5 để linh hoạt hơn cho 1 dòng
                    // Nội dung chỉ có 1 dòng (hoặc rất ít)
                    flashcardElement.classList.add('is-single-line');
                } else {
                    // Nội dung có nhiều dòng nhưng không tràn
                    flashcardElement.classList.add('is-multi-line');
                }
            } else {
                // Nội dung bị tràn (có scrollbar)
                flashcardElement.classList.add('is-overflow');
            }
        }
    }

    // Chạy điều chỉnh khi tải trang
    adjustBackSideContentLayout();

    // Thêm lắng nghe sự kiện resize để điều chỉnh lại khi kích thước cửa sổ thay đổi
    // Điều này quan trọng vì layout có thể thay đổi và gây ra/mất overflow hoặc thay đổi số dòng
    window.addEventListener('resize', adjustBackSideContentLayout);

    // Thêm lắng nghe sự kiện khi hình ảnh hoặc nội dung động tải xong (nếu có)
    // (ví dụ: nếu flashcard.back có chứa hình ảnh hoặc được render động)
    // Đây là một ví dụ, có thể cần tinh chỉnh tùy thuộc vào cách nội dung được tải
    const images = flashcardElement.querySelectorAll('img');
    images.forEach(img => {
        if (!img.complete) {
            img.addEventListener('load', adjustBackSideContentLayout);
            img.addEventListener('error', adjustBackSideContentLayout); // Xử lý lỗi tải ảnh
        }
    });
});
