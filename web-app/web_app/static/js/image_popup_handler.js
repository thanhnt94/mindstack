// image_popup_handler.js

/**
 * Mô tả: File này xử lý logic đóng popup hình ảnh trên giao diện học thẻ mobile.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Tìm kiếm các phần tử trong DOM
    const imagePopup = document.getElementById('image-popup');
    const closeButton = document.getElementById('close-image-popup-btn');

    // Chỉ thực hiện nếu popup và nút đóng tồn tại trên trang
    if (imagePopup && closeButton) {
        /**
         * Mô tả: Hàm để đóng popup hình ảnh.
         */
        function closeImagePopup() {
            // Thêm class 'hidden' để ẩn popup
            imagePopup.classList.add('hidden');

            // THAY ĐỔI QUAN TRỌNG: Gọi lại hàm adjustFontSize() sau khi popup đã ẩn.
            // Thêm một khoảng trễ nhỏ để đợi hiệu ứng CSS hoàn tất.
            setTimeout(function() {
                if (typeof adjustFontSize === 'function') {
                    adjustFontSize();
                }
            }, 300); // 300ms, khớp với thời gian transition trong CSS
        }

        // Gắn sự kiện 'click' cho nút đóng
        closeButton.addEventListener('click', closeImagePopup);
    }
});
