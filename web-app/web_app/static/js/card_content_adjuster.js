// card_content_adjuster.js

document.addEventListener('DOMContentLoaded', function() {
    const flashcard = document.querySelector('.flashcard');
    const scrollableContent = document.querySelector('.scrollable-card-content');
    const cardText = document.querySelector('.card-text');

    if (!flashcard || !scrollableContent || !cardText) {
        console.warn("Thiếu các phần tử flashcard, scrollable-card-content hoặc card-text. Không thể điều chỉnh nội dung thẻ.");
        return;
    }

    /**
     * Mô tả: Kiểm tra xem nội dung thẻ có bị tràn hay không.
     * @returns {boolean} True nếu nội dung bị tràn, ngược lại là False.
     */
    function isContentOverflowing() {
        return scrollableContent.scrollHeight > scrollableContent.clientHeight;
    }

    /**
     * Mô tả: Điều chỉnh kích thước font của nội dung thẻ để vừa với khung.
     * Nếu nội dung tràn, giảm font size cho đến khi vừa hoặc đạt kích thước tối thiểu.
     * Nếu không tràn, tăng font size cho đến khi đạt kích thước tối đa hoặc vừa khung.
     */
    function adjustFontSize() {
        // Chỉ điều chỉnh font size cho mặt sau khi nó bị tràn
        if (flashcard.classList.contains('is-back-side')) {
            let currentFontSize = parseFloat(window.getComputedStyle(cardText).fontSize);
            const minFontSize = 16; // Kích thước font tối thiểu cho mặt sau
            const maxFontSize = 32; // Kích thước font tối đa cho mặt sau (nếu không tràn)

            // Kiểm tra tràn và điều chỉnh font size
            if (isContentOverflowing()) {
                // Nếu tràn, giảm font size
                while (isContentOverflowing() && currentFontSize > minFontSize) {
                    currentFontSize -= 1;
                    cardText.style.fontSize = `${currentFontSize}px`;
                }
                flashcard.classList.add('is-overflow'); // Thêm class để CSS căn chỉnh
                flashcard.classList.remove('is-multi-line'); // Đảm bảo không có class multi-line
            } else {
                // Nếu không tràn, kiểm tra xem có phải là nội dung nhiều dòng không
                // và điều chỉnh căn chỉnh
                if (cardText.innerText.includes('\n') || cardText.innerText.length > 50) { // Giả định nhiều dòng nếu có xuống dòng hoặc dài
                    flashcard.classList.add('is-multi-line'); // Thêm class để CSS căn chỉnh
                    flashcard.classList.remove('is-overflow'); // Đảm bảo không có class overflow
                } else {
                    flashcard.classList.remove('is-multi-line');
                    flashcard.classList.remove('is-overflow');
                }

                // Cố gắng tăng font size nếu có không gian và chưa đạt max
                while (!isContentOverflowing() && currentFontSize < maxFontSize) {
                    currentFontSize += 1;
                    cardText.style.fontSize = `${currentFontSize}px`;
                    if (isContentOverflowing()) { // Nếu vừa tăng mà bị tràn thì quay lại 1px
                        currentFontSize -= 1;
                        cardText.style.fontSize = `${currentFontSize}px`;
                        break;
                    }
                }
            }
        } else {
            // Đối với mặt trước, đặt font size cố định (hoặc theo quy tắc CSS)
            // và đảm bảo không có các class điều chỉnh tràn/multi-line
            cardText.style.fontSize = ''; // Reset về font size mặc định của CSS
            flashcard.classList.remove('is-overflow');
            flashcard.classList.remove('is-multi-line');
        }
    }

    // Gọi hàm điều chỉnh font size khi tải trang và khi cửa sổ thay đổi kích thước
    adjustFontSize();
    window.addEventListener('resize', adjustFontSize);

    // Sử dụng MutationObserver để phát hiện thay đổi nội dung của card-text
    // Điều này quan trọng khi nội dung thẻ thay đổi mà không tải lại trang (ví dụ: lật thẻ)
    const observer = new MutationObserver(adjustFontSize);
    observer.observe(cardText, { childList: true, subtree: true, characterData: true });
});
