/**
 * navbar_handler.js
 * Mô tả: Xử lý logic cho các menu dropdown trong thanh điều hướng.
 */
document.addEventListener('DOMContentLoaded', function() {
    
    // --- BẮT ĐẦU THÊM MỚI: Logic cho dropdown chính (MindStack) trên mobile ---
    const brandMenuTrigger = document.getElementById('brand-menu-trigger');
    const mainNavWrapper = document.getElementById('main-nav-wrapper');
    const mainChevron = document.querySelector('.nav-chevron-main');

    if (brandMenuTrigger && mainNavWrapper) {
        brandMenuTrigger.addEventListener('click', function(event) {
            // Chỉ kích hoạt dropdown trên màn hình mobile
            if (window.innerWidth <= 768) {
                event.preventDefault(); // Ngăn không cho chuyển về trang chủ
                
                // Đóng menu người dùng nếu nó đang mở
                if (userDropdownMenu && userDropdownMenu.classList.contains('open')) {
                    userDropdownMenu.classList.remove('open');
                    userMenuTrigger.querySelector('.fa-chevron-down').style.transform = 'rotate(0deg)';
                }

                // Mở/đóng dropdown chính
                const isOpen = mainNavWrapper.classList.toggle('open');
                brandMenuTrigger.classList.toggle('open', isOpen);
                if (mainChevron) {
                    mainChevron.style.transform = isOpen ? 'rotate(180deg)' : 'rotate(0deg)';
                }
            }
        });
    }
    // --- KẾT THÚC THÊM MỚI ---

    // --- Logic cho menu người dùng (bên phải) ---
    const userMenuTrigger = document.getElementById('user-menu-trigger');
    const userDropdownMenu = document.getElementById('user-dropdown-menu');

    if (userMenuTrigger && userDropdownMenu) {
        userMenuTrigger.addEventListener('click', function(event) {
            event.stopPropagation();

            // Đóng dropdown chính nếu nó đang mở
            if (mainNavWrapper && mainNavWrapper.classList.contains('open')) {
                mainNavWrapper.classList.remove('open');
                brandMenuTrigger.classList.remove('open');
                if (mainChevron) {
                    mainChevron.style.transform = 'rotate(0deg)';
                }
            }
            
            // Mở/đóng dropdown người dùng
            const isOpen = userDropdownMenu.classList.toggle('open');
            const icon = userMenuTrigger.querySelector('.fa-chevron-down');
            if (icon) {
                icon.style.transform = isOpen ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });
    }

    // --- Logic chung: Đóng tất cả menu khi bấm ra ngoài ---
    window.addEventListener('click', function(event) {
        // Đóng dropdown chính
        if (mainNavWrapper && mainNavWrapper.classList.contains('open') && !brandMenuTrigger.contains(event.target)) {
            mainNavWrapper.classList.remove('open');
            brandMenuTrigger.classList.remove('open');
            if (mainChevron) {
                mainChevron.style.transform = 'rotate(0deg)';
            }
        }

        // Đóng dropdown người dùng
        if (userDropdownMenu && userDropdownMenu.classList.contains('open') && !userMenuTrigger.contains(event.target)) {
            userDropdownMenu.classList.remove('open');
            const icon = userMenuTrigger.querySelector('.fa-chevron-down');
            if (icon) {
                icon.style.transform = 'rotate(0deg)';
            }
        }
    });

    // Ngăn việc bấm vào bên trong dropdown làm đóng nó
    if (mainNavWrapper) {
        mainNavWrapper.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    }
    if (userDropdownMenu) {
        userDropdownMenu.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    }
});
