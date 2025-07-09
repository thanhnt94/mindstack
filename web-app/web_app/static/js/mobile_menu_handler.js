// mobile_menu_handler.js

/**
 * Mô tả: Xử lý logic mở và đóng menu điều hướng bên trái (side navigation).
 */
document.addEventListener('DOMContentLoaded', function() {
    // Lấy các phần tử DOM cần thiết
    const menuToggleBtn = document.getElementById('menu-toggle-btn');
    const sideNav = document.getElementById('side-nav');
    const sideNavCloseBtn = document.getElementById('side-nav-close-btn');
    const overlay = document.getElementById('side-nav-overlay');

    // Kiểm tra xem tất cả các phần tử có tồn tại không
    if (menuToggleBtn && sideNav && sideNavCloseBtn && overlay) {

        // Hàm để mở menu
        function openMenu() {
            sideNav.classList.add('open');
            overlay.classList.add('open');
        }

        // Hàm để đóng menu
        function closeMenu() {
            sideNav.classList.remove('open');
            overlay.classList.remove('open');
        }

        // Gắn sự kiện click cho các phần tử
        menuToggleBtn.addEventListener('click', openMenu);
        sideNavCloseBtn.addEventListener('click', closeMenu);
        overlay.addEventListener('click', closeMenu);
    }
});
