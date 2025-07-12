// web_app/static/js/card_details_handler.js

/**
 * Mô tả: Xử lý logic cho "Dynamic Island" hiển thị chi tiết thẻ trên giao diện di động.
 * Bao gồm việc mở rộng và thu gọn thông tin khi người dùng nhấn vào.
 */
document.addEventListener('DOMContentLoaded', function() {
    const dynamicCardDetails = document.getElementById('dynamic-card-details');
    const cardSideText = document.getElementById('card-side-text'); // Lấy tham chiếu đến chữ "Mặt trước/Mặt sau"

    // Chỉ chạy script nếu phần tử dynamic island tồn tại
    if (dynamicCardDetails) {
        /**
         * Mô tả: Chuyển đổi trạng thái mở rộng/thu gọn của dynamic island.
         */
        function toggleDetails() {
            dynamicCardDetails.classList.toggle('expanded');

            // BẮT ĐẦU THÊM MỚI: Ẩn/hiện chữ "Mặt trước/Mặt sau"
            if (cardSideText) {
                if (dynamicCardDetails.classList.contains('expanded')) {
                    cardSideText.classList.add('hidden'); // Ẩn chữ
                } else {
                    cardSideText.classList.remove('hidden'); // Hiện chữ
                }
            }
            // KẾT THÚC THÊM MỚI
        }

        // Gắn sự kiện click vào toàn bộ khu vực dynamic island
        dynamicCardDetails.addEventListener('click', toggleDetails);
    }
});
