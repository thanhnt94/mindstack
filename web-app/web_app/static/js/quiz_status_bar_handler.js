// web_app/static/js/quiz_status_bar_handler.js

/**
 * Mô tả: Xử lý logic cho thanh trạng thái Quiz cố định trên giao diện di động.
 * Bao gồm việc mở rộng/thu gọn thông tin chi tiết và cập nhật các số liệu thống kê.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Lấy các phần tử DOM cần thiết
    const quizStatusBar = document.getElementById('quiz-status-bar');
    const toggleButton = document.getElementById('quiz-status-toggle-btn');
    const quizJsDataElement = document.getElementById('quizJsData');
    const quizTakePanel = document.querySelector('.quiz-take-panel'); // Lấy panel chứa nội dung quiz chính

    // Các phần tử hiển thị số liệu tóm tắt
    const correctCountSpan = document.getElementById('quiz-correct-count');
    const incorrectCountSpan = document.getElementById('quiz-incorrect-count');

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại
    if (!quizStatusBar || !toggleButton || !quizJsDataElement || !quizTakePanel) {
        console.warn("Thiếu các phần tử HTML cần thiết cho Quiz Status Bar hoặc Quiz Take Panel. Script sẽ không chạy.");
        return;
    }

    // Lấy dữ liệu thống kê từ data attributes
    // Các biến này được khai báo lại để đảm bảo chúng có phạm vi cục bộ trong hàm này
    let quizTotalQuestions = parseInt(quizJsDataElement.dataset.quizTotalQuestions || '0');
    let quizAnsweredQuestions = parseInt(quizJsDataElement.dataset.quizAnsweredQuestions || '0');
    let quizCorrectAnswers = parseInt(quizJsDataElement.dataset.quizCorrectAnswers || '0');
    let quizIncorrectAnswers = parseInt(quizJsDataElement.dataset.quizIncorrectAnswers || '0');
    let quizMasteredQuestions = parseInt(quizJsDataElement.dataset.quizMasteredQuestions || '0');
    let quizUnansweredQuestions = parseInt(quizJsDataElement.dataset.quizUnansweredQuestions || '0');


    /**
     * Mô tả: Cập nhật các số liệu thống kê trên thanh trạng thái.
     * Hàm này có thể được gọi lại nếu số liệu thay đổi (ví dụ: sau khi trả lời câu hỏi).
     */
    function updateStatsDisplay() {
        // Cập nhật phần tóm tắt
        if (correctCountSpan) {
            correctCountSpan.textContent = quizCorrectAnswers;
        }
        if (incorrectCountSpan) {
            incorrectCountSpan.textContent = quizIncorrectAnswers;
        }

        // Cập nhật các giá trị trong phần chi tiết
        // Lấy lại các phần tử chi tiết nếu chúng ta muốn cập nhật động sau mỗi câu trả lời
        const detailItems = quizStatusBar.querySelectorAll('.status-details .detail-item');
        if (detailItems.length > 0) {
            detailItems[0].querySelector('.detail-value').textContent = quizTotalQuestions;
            detailItems[1].querySelector('.detail-value').textContent = quizAnsweredQuestions;
            detailItems[2].querySelector('.detail-value').textContent = quizMasteredQuestions;
            detailItems[3].querySelector('.detail-value').textContent = quizUnansweredQuestions;
        }
    }

    /**
     * Mô tả: Điều chỉnh margin-top của quiz-take-panel để đẩy nội dung xuống.
     */
    function adjustContentMargin() {
        // Lấy chiều cao thực tế của thanh trạng thái
        const statusBarHeight = quizStatusBar.offsetHeight;
        // Chiều cao của navbar cố định (đã được định nghĩa trong CSS)
        const navbarHeight = 50; 
        // Khoảng cách ban đầu của quiz-take-panel (đã được định nghĩa trong CSS)
        const initialPanelMarginTop = 20; 

        // Tính toán margin-top mới cho quiz-take-panel
        // Nó sẽ bằng chiều cao của status bar trừ đi chiều cao mặc định của nó khi thu gọn
        // và cộng thêm khoảng trống ban đầu
        const newMarginTop = statusBarHeight - (quizStatusBar.classList.contains('expanded') ? 0 : 50) + initialPanelMarginTop; /* 50px là chiều cao thu gọn */
        
        // Áp dụng margin-top mới cho quiz-take-panel
        quizTakePanel.style.marginTop = `${newMarginTop}px`;
    }

    /**
     * Mô tả: Mở/Đóng thanh trạng thái Quiz.
     */
    function toggleStatusBar() {
        quizStatusBar.classList.toggle('expanded');
        // Chờ một chút để CSS transition hoàn tất trước khi điều chỉnh margin
        setTimeout(adjustContentMargin, 300); // 300ms là thời gian transition trong CSS
    }

    // Gắn sự kiện click cho nút mở rộng/thu gọn
    toggleButton.addEventListener('click', toggleStatusBar);

    // Gọi hàm cập nhật và điều chỉnh margin lần đầu khi tải trang
    updateStatsDisplay();
    adjustContentMargin();

    // Lắng nghe sự kiện resize để điều chỉnh lại margin khi xoay màn hình hoặc thay đổi kích thước
    window.addEventListener('resize', adjustContentMargin);

    // BẮT ĐẦU THÊM MỚI: Thêm hàm cập nhật thống kê sau khi trả lời câu hỏi
    // Cần một cách để quiz_handler thông báo cho quiz_status_bar_handler khi có câu trả lời mới
    // Một cách là sử dụng CustomEvent
    window.addEventListener('quizAnswered', function(event) {
        // Cập nhật các biến thống kê cục bộ từ dữ liệu mới nhất
        const newStats = event.detail.quizSetStats;
        quizTotalQuestions = newStats.total_questions;
        quizAnsweredQuestions = newStats.answered_questions;
        quizCorrectAnswers = newStats.correct_answers;
        quizIncorrectAnswers = newStats.incorrect_answers;
        quizMasteredQuestions = newStats.mastered_questions;
        quizUnansweredQuestions = newStats.unanswered_questions;
        updateStatsDisplay(); // Cập nhật hiển thị
        adjustContentMargin(); // Điều chỉnh lại margin nếu cần (mặc dù thường không thay đổi chiều cao)
    });
    // KẾT THÚC THÊM MỚI
});
