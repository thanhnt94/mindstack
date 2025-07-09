// card_content_adjuster.js

/**
 * Mô tả: Điều chỉnh kích thước font của nội dung thẻ để vừa với khung.
 * Nếu nội dung tràn, giảm font size. Nếu không, tăng font size.
 * Hàm này được đưa ra ngoài để có thể gọi từ script khác.
 */
function adjustFontSize() {
    const flashcard = document.querySelector('.flashcard');
    const scrollableContent = document.querySelector('.scrollable-card-content');
    const cardText = document.querySelector('.card-text');

    if (!flashcard || !scrollableContent || !cardText) {
        // Không tìm thấy phần tử cần thiết, không làm gì cả.
        return;
    }

    // Reset style trước khi tính toán để có kết quả chính xác
    cardText.style.fontSize = '';
    flashcard.classList.remove('is-overflow', 'is-multi-line');

    const isContentOverflowing = () => scrollableContent.scrollHeight > scrollableContent.clientHeight;

    // Chỉ điều chỉnh font size cho mặt sau
    if (flashcard.classList.contains('is-back-side')) {
        let currentFontSize = parseFloat(window.getComputedStyle(cardText).fontSize);
        // THAY ĐỔI: Tăng cỡ chữ tối thiểu từ 16 lên 18
        const minFontSize = 18;
        const maxFontSize = 32; // Kích thước font tối đa

        // Vòng lặp để giảm font size nếu bị tràn
        while (isContentOverflowing() && currentFontSize > minFontSize) {
            currentFontSize -= 1;
            cardText.style.fontSize = `${currentFontSize}px`;
        }

        // Nếu sau khi giảm vẫn tràn, hoặc nội dung có nhiều dòng, căn lề trái
        if (isContentOverflowing() || cardText.innerText.includes('\n') || cardText.innerText.length > 50) {
             flashcard.classList.add('is-overflow'); // Dùng class này để căn trái
        }

    } else {
        // Đối với mặt trước, chỉ cần đảm bảo nó được căn giữa
        cardText.style.fontSize = '';
    }
}


document.addEventListener('DOMContentLoaded', function() {
    // Gọi hàm điều chỉnh lần đầu khi tải trang
    adjustFontSize();

    // Lắng nghe sự kiện thay đổi kích thước cửa sổ
    window.addEventListener('resize', adjustFontSize);

    // Lắng nghe sự kiện thay đổi nội dung thẻ
    const cardText = document.querySelector('.card-text');
    if (cardText) {
        const observer = new MutationObserver(adjustFontSize);
        observer.observe(cardText, { childList: true, subtree: true, characterData: true });
    }
});
