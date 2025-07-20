/**
 * settings.js
 * Mô tả: Xử lý logic cho trang cài đặt, bao gồm chuyển tab và xác thực form.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Xử lý chuyển tab
    const tabs = document.querySelectorAll('.tab-link');
    const contents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Xóa active class khỏi tất cả các tab và content
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            // Thêm active class vào tab và content được click
            tab.classList.add('active');
            const contentId = tab.dataset.tab;
            document.getElementById(contentId).classList.add('active');
        });
    });

    // Xử lý xác thực form mật khẩu
    const passwordForm = document.getElementById('password-form');
    if (passwordForm) {
        const newPassword = document.getElementById('new_password');
        const confirmPassword = document.getElementById('confirm_password');
        const errorMessage = document.getElementById('password-match-error');

        const validatePasswords = () => {
            if (newPassword.value !== confirmPassword.value) {
                errorMessage.style.display = 'block';
                confirmPassword.setCustomValidity("Mật khẩu không khớp.");
            } else {
                errorMessage.style.display = 'none';
                confirmPassword.setCustomValidity("");
            }
        };

        newPassword.addEventListener('change', validatePasswords);
        confirmPassword.addEventListener('keyup', validatePasswords);

        passwordForm.addEventListener('submit', (event) => {
            if (newPassword.value !== confirmPassword.value) {
                event.preventDefault(); // Ngăn form submit nếu mật khẩu không khớp
                alert('Mật khẩu mới và xác nhận không khớp. Vui lòng kiểm tra lại.');
            }
        });
    }
});
