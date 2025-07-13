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

    const hasImage = jsDataElement.dataset.hasImage === 'true';

    // Nếu không có ảnh, ẩn popup ngay lập tức và không cần chạy logic này
    if (!hasImage) {
        imagePopup.classList.add('hidden');
        return;
    }

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

    // BẮT ĐẦU THÊM MỚI: Logic hiển thị popup ảnh khi lật thẻ (mặt sau)
    // Kiểm tra xem đây có phải là mặt sau của thẻ và có ảnh hay không
    const isFront = jsDataElement.dataset.isFront === 'true';

    // Nếu là mặt sau và có ảnh, hiển thị popup ảnh
    if (!isFront && hasImage) {
        imagePopup.classList.remove('hidden');
        // Điều chỉnh font size ngay sau khi hiển thị ảnh để nội dung đẩy lên
        // Sử dụng setTimeout để đảm bảo DOM đã được render lại sau khi bỏ class 'hidden'
        setTimeout(function() {
            if (typeof adjustFontSize === 'function') {
                adjustFontSize();
            }
        }, 0); // Độ trễ 0ms để chạy ở cuối event loop
    } else {
        // Nếu là mặt trước hoặc không có ảnh, đảm bảo popup ẩn
        imagePopup.classList.add('hidden');
    }
    // KẾT THÚC THÊM MỚI
});

