// web_app/static/js/quiz_status_bar_handler.js

/**
 * Mô tả: Xử lý logic cho thanh trạng thái Quiz cố định trên giao diện di động.
 * Bao gồm việc cập nhật các số liệu thống kê.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Lấy các phần tử DOM cần thiết
    const quizStatusBar = document.getElementById('quiz-status-bar');
    const quizJsDataElement = document.getElementById('quizJsData');
    const mainContainer = document.querySelector('.main-container'); // Lấy main-container

    // Các phần tử hiển thị số liệu thống kê câu hỏi hiện tại
    const correctCountSpan = document.getElementById('quiz-correct-count');
    const incorrectCountSpan = document.getElementById('quiz-incorrect-count');
    
    // Các phần tử của thanh tiến trình bộ đề
    const progressBarFillQuiz = quizStatusBar.querySelector('.progress-bar-fill-quiz');
    const progressBarTextQuiz = quizStatusBar.querySelector('.progress-bar-text-quiz');
    
    // Phần tử hiển thị tên chế độ
    const quizModeDisplaySpan = document.getElementById('quiz-mode-display');

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại
    if (!quizStatusBar || !quizJsDataElement || !mainContainer) {
        console.warn("Thiếu các phần tử HTML cần thiết cho Quiz Status Bar hoặc Main Container. Script sẽ không chạy.");
        return;
    }

    // Chiều cao của navbar cố định (đã được định nghĩa trong CSS)
    const navbarHeight = 15; 

    /**
     * Mô tả: Cập nhật các số liệu thống kê trên thanh trạng thái.
     * Hàm này có thể được gọi lại nếu số liệu thay đổi (ví dụ: sau khi trả lời câu hỏi).
     */
    function updateStatsDisplay() {
        // Lấy dữ liệu thống kê bộ đề từ data attributes
        let quizTotalQuestions = parseInt(quizJsDataElement.dataset.quizTotalQuestions || '0');
        let quizAnsweredQuestions = parseInt(quizJsDataElement.dataset.quizAnsweredQuestions || '0');
        let currentQuizModeDisplay = quizJsDataElement.dataset.currentQuizModeDisplay || 'Chế độ';

        // Lấy dữ liệu thống kê CÂU HỎI HIỆN TẠI từ data attributes
        let questionTimesCorrect = parseInt(quizJsDataElement.dataset.questionTimesCorrect || '0');
        let questionTimesIncorrect = parseInt(quizJsDataElement.dataset.questionTimesIncorrect || '0');

        // Cập nhật số lần đúng/sai CỦA CÂU HỎI HIỆN TẠI
        if (correctCountSpan) {
            correctCountSpan.textContent = questionTimesCorrect;
        }
        if (incorrectCountSpan) {
            incorrectCountSpan.textContent = questionTimesIncorrect;
        }

        // Cập nhật thanh tiến trình bộ đề
        if (progressBarFillQuiz && progressBarTextQuiz) {
            const answeredPercentage = quizTotalQuestions > 0 ? (quizAnsweredQuestions / quizTotalQuestions) * 100 : 0;
            progressBarFillQuiz.style.width = `${answeredPercentage}%`;
            progressBarTextQuiz.textContent = `${quizAnsweredQuestions} / ${quizTotalQuestions}`;
        }

        // Cập nhật tên chế độ
        if (quizModeDisplaySpan) {
            quizModeDisplaySpan.textContent = currentQuizModeDisplay;
        }
    }

    /**
     * Mô tả: Điều chỉnh padding-top của body để đẩy nội dung xuống.
     * Sử dụng requestAnimationFrame để đảm bảo tính toán chính xác sau khi render.
     */
    function adjustBodyPadding() {
        requestAnimationFrame(() => {
            const quizStatusBarHeight = quizStatusBar.offsetHeight;
            const totalFixedHeaderHeight = navbarHeight + quizStatusBarHeight;
            document.body.style.paddingTop = `${totalFixedHeaderHeight}px`;
        });
    }

    // Gọi hàm cập nhật và điều chỉnh padding lần đầu khi tải trang
    updateStatsDisplay();
    adjustBodyPadding(); // Gọi lần đầu để thiết lập padding chính xác

    // Lắng nghe sự kiện resize để điều chỉnh lại padding khi xoay màn hình hoặc thay đổi kích thước
    window.addEventListener('resize', adjustBodyPadding);

    // Thêm MutationObserver để theo dõi thay đổi chiều cao của quizStatusBar
    const observer = new MutationObserver(adjustBodyPadding);
    observer.observe(quizStatusBar, { attributes: true, childList: true, subtree: true });


    // BẮT ĐẦU THÊM MỚI: Thêm hàm cập nhật thống kê sau khi trả lời câu hỏi
    window.addEventListener('quizAnswered', function(event) {
        // Cập nhật các biến thống kê bộ đề từ dữ liệu mới nhất
        quizJsDataElement.dataset.quizTotalQuestions = event.detail.quizSetStats.total_questions;
        quizJsDataElement.dataset.quizAnsweredQuestions = event.detail.quizSetStats.answered_questions;
        
        // Cập nhật thống kê CÂU HỎI HIỆN TẠI
        quizJsDataElement.dataset.questionTimesCorrect = event.detail.questionProgress.times_correct;
        quizJsDataElement.dataset.questionTimesIncorrect = event.detail.questionProgress.times_incorrect;

        updateStatsDisplay(); // Cập nhật hiển thị
        adjustBodyPadding(); 
    });
    // KẾT THÚC THÊM MỚI
});
