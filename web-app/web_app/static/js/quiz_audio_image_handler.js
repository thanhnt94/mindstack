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
    // Lấy trực tiếp giá trị của question_audio_file từ data attribute
    const questionAudioFile = quizJsDataElement.dataset.questionAudioFile;

    /**
     * Mô tả: Hàm phát audio của câu hỏi.
     */
    function playQuizAudio() {
        let audioSrc = '';

        // BẮT ĐẦU THAY ĐỔI: Logic xác định nguồn audio
        if (questionAudioFile) {
            // Nếu questionAudioFile là một URL đầy đủ, sử dụng nó trực tiếp
            if (questionAudioFile.startsWith('http://') || questionAudioFile.startsWith('https://')) {
                audioSrc = questionAudioFile;
                console.log("Sử dụng URL audio trực tiếp:", audioSrc);
            } else {
                // Nếu không phải URL đầy đủ, giả định là đường dẫn cục bộ
                // và gọi API endpoint để phục vụ file
                audioSrc = `/api/quiz_audio/${questionId}`;
                console.log("Sử dụng API để phục vụ audio cục bộ:", audioSrc);
            }
        } else {
            console.log("Không có URL audio cho câu hỏi quiz này.");
            return; // Không có audio để phát
        }
        // KẾT THÚC THAY ĐỔI

        if (audioSrc) {
            quizAudioPlayer.load(); // Reset trình phát
            quizAudioPlayer.src = audioSrc;
            quizAudioPlayer.play().catch(error => {
                console.error("Lỗi khi phát audio quiz:", error);
                // Có thể thêm thông báo cho người dùng tại đây
            });
        }
    }

    // Gắn sự kiện click cho nút phát audio
    playQuizAudioButton.addEventListener('click', playQuizAudio);

    // Tự động phát audio khi trang tải nếu có audio
    // (Có thể thêm cài đặt người dùng để bật/tắt tự động phát sau này)
    if (questionAudioFile) { // Chỉ tự động phát nếu có file audio được chỉ định
        // Một độ trễ nhỏ để đảm bảo trình duyệt đã sẵn sàng
        setTimeout(playQuizAudio, 500); 
    }
});

