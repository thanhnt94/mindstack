// image_popup_handler.js

/**
 * Mô tả: File này xử lý logic đóng/mở popup hình ảnh trên giao diện học thẻ mobile.
 * Đồng thời điều chỉnh kích thước nội dung thẻ để phù hợp.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Tìm kiếm các phần tử trong DOM
    const imagePopup = document.getElementById('image-popup');
    const closeButton = document.getElementById('close-image-popup-btn');
    const jsDataElement = document.getElementById('jsData'); // Lấy jsData để kiểm tra có ảnh hay không

    // Chỉ thực hiện nếu popup và nút đóng tồn tại trên trang VÀ có ảnh
    if (!imagePopup || !closeButton || !jsDataElement) {
        return;
    }

    // Lấy trạng thái mặt thẻ hiện tại và kiểm tra xem có ảnh để hiển thị không
    const isFront = jsDataElement.dataset.isFront === 'true';
    // THAY ĐỔI: Lấy hasImage dựa trên mặt hiện tại của thẻ
    const hasImage = isFront ? jsDataElement.dataset.hasFrontImage === 'true' : jsDataElement.dataset.hasBackImage === 'true';

    /**
     * Mô tả: Hàm để đóng popup hình ảnh.
     */
    function closeImagePopup() {
        // Thêm class 'hidden' để ẩn popup
        imagePopup.classList.add('hidden');

        // Gọi lại hàm adjustFontSize() sau khi popup đã ẩn.
        // Thêm một khoảng trễ nhỏ để đợi hiệu ứng CSS hoàn tất.
        setTimeout(function() {
            if (typeof adjustFontSize === 'function') {
                adjustFontSize(); // Điều chỉnh lại font size của card text
            }
        }, 300); // 300ms, khớp với thời gian transition trong CSS
    }

    // Gắn sự kiện 'click' cho nút đóng
    closeButton.addEventListener('click', closeImagePopup);

    // LOGIC HIỂN THỊ POPUP ẢNH KHI TẢI TRANG HOẶC LẬT THẺ
    // Nếu có ảnh cho mặt hiện tại, hiển thị popup ảnh
    if (hasImage) {
        imagePopup.classList.remove('hidden');
        // Điều chỉnh font size ngay sau khi hiển thị ảnh để nội dung đẩy lên
        // Sử dụng setTimeout để đảm bảo DOM đã được render lại sau khi bỏ class 'hidden'
        setTimeout(function() {
            if (typeof adjustFontSize === 'function') {
                adjustFontSize();
            }
        }, 0); // Độ trễ 0ms để chạy ở cuối event loop
    } else {
        // Nếu không có ảnh cho mặt hiện tại, đảm bảo popup ẩn
        imagePopup.classList.add('hidden');
    }
});
