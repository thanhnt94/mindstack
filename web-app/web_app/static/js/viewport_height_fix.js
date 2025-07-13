// web_app/static/js/viewport_height_fix.js

/**
 * Mô tả: Khắc phục vấn đề đơn vị vh (viewport height) không chính xác trên trình duyệt di động.
 * Hàm này tính toán chiều cao thực tế của viewport và lưu vào biến CSS tùy chỉnh --vh.
 * Điều này giúp các phần tử sử dụng 100vh luôn khớp với không gian hiển thị thực tế,
 * ngăn chặn tình trạng nội dung bị cắt hoặc tạo cuộn ngoài ý muốn.
 */
function setVh() {
  let vh = window.innerHeight * 0.01;
  document.documentElement.style.setProperty('--vh', `${vh}px`);
}

// Chạy lần đầu khi DOM đã tải
document.addEventListener('DOMContentLoaded', setVh);

// Chạy lại mỗi khi thay đổi kích thước cửa sổ (ví dụ: xoay màn hình)
window.addEventListener('resize', setVh);