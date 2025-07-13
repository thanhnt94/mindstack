// web_app/static/js/quiz_audio_image_handler.js

/**
 * Mô tả: Xử lý logic phát audio cho câu hỏi trắc nghiệm.
 */
document.addEventListener('DOMContentLoaded', function() {
    const quizAudioPlayer = document.getElementById('quizAudioPlayer');
    const playQuizAudioButton = document.getElementById('playQuizAudioButton');
    const quizJsDataElement = document.getElementById('quizJsData');

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại
    if (!quizAudioPlayer || !playQuizAudioButton || !quizJsDataElement) {
        return;
    }

    const questionId = quizJsDataElement.dataset.questionId;
    const questionAudioFile = quizJsDataElement.dataset.questionAudioFile;

    // Xây dựng URL audio
    let audioUrl = '';
    if (questionAudioFile) {
        // Kiểm tra nếu là URL đầy đủ (http/https)
        if (questionAudioFile.startsWith('http://') || questionAudioFile.startsWith('https://')) {
            audioUrl = questionAudioFile;
        } else {
            // Nếu là tên file cục bộ, sử dụng API endpoint
            // url_for('api.get_quiz_audio', question_id=question.question_id)
            // Vì đây là JS tĩnh, chúng ta không thể dùng url_for trực tiếp.
            // Cần xây dựng thủ công hoặc truyền từ Jinja.
            // Hiện tại, chúng ta sẽ xây dựng thủ công dựa trên cấu trúc đã biết.
            audioUrl = `/api/quiz_audio/${questionId}`;
        }
    }

    /**
     * Mô tả: Hàm phát audio của câu hỏi.
     */
    function playQuizAudio() {
        if (audioUrl) {
            quizAudioPlayer.load(); // Reset trình phát
            quizAudioPlayer.src = audioUrl;
            quizAudioPlayer.play().catch(error => {
                console.error("Lỗi khi phát audio quiz:", error);
                // Có thể thêm thông báo cho người dùng tại đây
            });
        } else {
            console.log("Không có URL audio cho câu hỏi quiz này.");
        }
    }

    // Gắn sự kiện click cho nút phát audio
    playQuizAudioButton.addEventListener('click', playQuizAudio);

    // Tự động phát audio khi trang tải nếu có audio
    // (Có thể thêm cài đặt người dùng để bật/tắt tự động phát sau này)
    if (audioUrl) {
        // Một độ trễ nhỏ để đảm bảo trình duyệt đã sẵn sàng
        setTimeout(playQuizAudio, 500); 
    }
});
