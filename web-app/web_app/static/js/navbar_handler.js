/**
 * navbar_handler.js
 * Mô tả: Xử lý logic cho menu người dùng trong thanh điều hướng.
 */
document.addEventListener('DOMContentLoaded', function() {
    const userMenuTrigger = document.getElementById('user-menu-trigger');
    const userDropdownMenu = document.getElementById('user-dropdown-menu');

    // Chỉ chạy script nếu các phần tử tồn tại
    if (userMenuTrigger && userDropdownMenu) {
        
        // Bấm vào nút trigger để hiện/ẩn dropdown
        userMenuTrigger.addEventListener('click', function(event) {
            // Ngăn sự kiện click lan ra ngoài (tới window)
            event.stopPropagation();
            
            // Chuyển đổi trạng thái hiển thị của dropdown
            userDropdownMenu.classList.toggle('open');
            
            // Xoay icon mũi tên
            const icon = userMenuTrigger.querySelector('.fa-chevron-down');
            if (icon) {
                icon.style.transform = userDropdownMenu.classList.contains('open') ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });

        // Bấm ra ngoài để đóng dropdown
        window.addEventListener('click', function(event) {
            if (userDropdownMenu.classList.contains('open')) {
                userDropdownMenu.classList.remove('open');
                
                // Reset icon mũi tên
                const icon = userMenuTrigger.querySelector('.fa-chevron-down');
                if (icon) {
                    icon.style.transform = 'rotate(0deg)';
                }
            }
        });

        // Ngăn việc bấm vào bên trong dropdown làm đóng nó
        userDropdownMenu.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    }
});
