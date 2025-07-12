// web_app/static/js/card_details_handler.js

/**
 * Mô tả: Xử lý logic cho "Dynamic Island" hiển thị chi tiết thẻ trên giao diện di động.
 * Bao gồm việc mở rộng và thu gọn thông tin khi người dùng nhấn vào.
 */
document.addEventListener('DOMContentLoaded', function() {
    const dynamicCardDetails = document.getElementById('dynamic-card-details'); // Đây là phần tử dynamic island
    const mainFlashcard = document.getElementById('main-flashcard'); // Lấy thẻ flashcard chính
    const cardSideText = document.getElementById('card-side-text'); // Lấy tham chiếu đến chữ "Mặt trước/Mặt sau"
    const flashcardHeader = document.querySelector('.flashcard-header'); // Lấy header của flashcard

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại
    if (dynamicCardDetails && mainFlashcard && flashcardHeader) {
        /**
         * Mô tả: Mở/Đóng dynamic island.
         * @param {Event} event Đối tượng sự kiện click.
         */
        function toggleDetails(event) {
            // Ngăn chặn sự kiện click lan ra các phần tử bên dưới khi dynamic island được nhấp
            event.stopPropagation();

            dynamicCardDetails.classList.toggle('expanded');
            
            // Loại bỏ hoàn toàn logic ẩn/hiện cardSideText vì bạn muốn nó luôn hiển thị
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
            }
        });
    }
});