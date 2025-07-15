/**
 * navbar_handler.js
 * Mô tả: Xử lý logic cho các menu dropdown trong thanh điều hướng.
 */
document.addEventListener('DOMContentLoaded', function() {

    // --- BẮT ĐẦU SỬA ĐỔI: Xóa logic cho dropdown chính (MindStack) trên mobile ---
    // Các phần tử và logic liên quan đến dropdown của MindStack không còn cần thiết
    // vì menu chính sẽ luôn hiển thị dưới dạng tab trên mobile.
    // const brandMenuTrigger = document.getElementById('brand-menu-trigger'); 
    // const mainNavWrapper = document.getElementById('main-nav-wrapper'); 
    // const mainChevron = document.querySelector('.nav-chevron-main'); 

    // if (brandMenuTrigger && mainNavWrapper) {
    //     brandMenuTrigger.addEventListener('click', function(event) {
    //         if (window.innerWidth <= 768) {
    //             event.preventDefault(); 
    //             if (userDropdownMenu && userDropdownMenu.classList.contains('open')) {
    //                 userDropdownMenu.classList.remove('open');
    //                 userMenuTrigger.querySelector('.fa-chevron-down').style.transform = 'rotate(0deg)';
    //             }
    //             const isOpen = mainNavWrapper.classList.toggle('open');
    //             brandMenuTrigger.classList.toggle('open', isOpen);
    //             if (mainChevron) {
    //                 mainChevron.style.transform = isOpen ? 'rotate(180deg)' : 'rotate(0deg)';
    //             }
    //         }
    //     });
    // }
    // --- KẾT THÚC SỬA ĐỔI ---

    // --- Logic cho menu người dùng (bên phải) ---
    const userMenuTrigger = document.getElementById('user-menu-trigger');
    const userDropdownMenu = document.getElementById('user-dropdown-menu');
    // THAY ĐỔI: Lấy chevron của user menu
    const userChevron = userMenuTrigger ? userMenuTrigger.querySelector('.user-chevron') : null;

    if (userMenuTrigger && userDropdownMenu) {
        userMenuTrigger.addEventListener('click', function(event) {
            event.stopPropagation();

            // BẮT ĐẦU SỬA ĐỔI: Xóa logic đóng dropdown chính vì nó không còn là dropdown
            // if (mainNavWrapper && mainNavWrapper.classList.contains('open')) {
            //     mainNavWrapper.classList.remove('open');
            //     brandMenuTrigger.classList.remove('open');
            //     if (mainChevron) {
            //         mainChevron.style.transform = 'rotate(0deg)';
            //     }
            // }
            // KẾT THÚC SỬA ĐỔI

            // Mở/đóng dropdown người dùng
            const isOpen = userDropdownMenu.classList.toggle('open');
            // THAY ĐỔI: Sử dụng userChevron
            if (userChevron) {
                userChevron.style.transform = isOpen ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });
    }

    // --- Logic chung: Đóng tất cả menu khi bấm ra ngoài ---
    window.addEventListener('click', function(event) {
        // BẮT ĐẦU SỬA ĐỔI: Xóa logic đóng dropdown chính vì nó không còn là dropdown
        // if (mainNavWrapper && mainNavWrapper.classList.contains('open') && !brandMenuTrigger.contains(event.target)) {
        //     mainNavWrapper.classList.remove('open');
        //     brandMenuTrigger.classList.remove('open');
        //     if (mainChevron) {
        //         mainChevron.style.transform = 'rotate(0deg)';
        //     }
        // }
        // KẾT THÚC SỬA ĐỔI

        // Đóng dropdown người dùng
        if (userDropdownMenu && userDropdownMenu.classList.contains('open') && !userMenuTrigger.contains(event.target)) {
            userDropdownMenu.classList.remove('open');
            // THAY ĐỔI: Sử dụng userChevron
            if (userChevron) {
                userChevron.style.transform = 'rotate(0deg)';
            }
        }
    });

    // Ngăn việc bấm vào bên trong dropdown làm đóng nó
    // BẮT ĐẦU SỬA ĐỔI: Xóa logic ngăn chặn cho mainNavWrapper
    // if (mainNavWrapper) {
    //     mainNavWrapper.addEventListener('click', function(event) {
    //         event.stopPropagation();
    //     });
    // }
    // KẾT THÚC SỬA ĐỔI
    if (userDropdownMenu) {
        userDropdownMenu.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    }
});
