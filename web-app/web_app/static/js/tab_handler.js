// web_app/static/js/tab_handler.js

/**
 * Mô tả: Xử lý logic chuyển đổi tab cho các trang có giao diện tab.
 * Tìm tất cả các container tab trên trang và gắn sự kiện cho chúng.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Tìm tất cả các container có class 'tab-container'
    const tabContainers = document.querySelectorAll('.tab-container');

    // Lặp qua từng container để thiết lập logic riêng cho mỗi cái
    tabContainers.forEach(container => {
        const tabButtons = container.querySelectorAll('.tab-button');
        const tabContents = container.querySelectorAll('.tab-content');

        // Gắn sự kiện click cho mỗi nút tab trong container hiện tại
        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const targetTabId = button.dataset.tab;

                // Xóa lớp 'active' khỏi tất cả các nút tab và nội dung tab
                // trong phạm vi container hiện tại
                tabButtons.forEach(btn => btn.classList.remove('active'));
                tabContents.forEach(content => content.classList.remove('active'));

                // Thêm lớp 'active' vào nút được click và nội dung tương ứng
                button.classList.add('active');
                container.querySelector(`#${targetTabId}`).classList.add('active');
            });
        });
    });
});
