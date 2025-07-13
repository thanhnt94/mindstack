// web_app/static/js/quiz_audio_image_handler.js

/**
 * Mô tả: Xử lý logic phát audio cho câu hỏi trắc nghiệm.
 */
document.addEventListener('DOMContentLoaded', function() {
    const quizAudioPlayer = document.getElementById('quizAudioPlayer');
    const quizJsDataElement = document.getElementById('quizJsData');

    // Lấy các phần tử điều khiển tùy chỉnh
    const customControlsContainer = document.querySelector('.quiz-audio-controls-custom');
    const playPauseBtn = document.getElementById('playPauseBtn');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    // BẮT ĐẦU THÊM MỚI: Thêm lại tham chiếu đến durationTimeSpan
    const durationTimeSpan = document.getElementById('durationTime');
    // KẾT THÚC THÊM MỚI

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại
    if (!quizAudioPlayer || !quizJsDataElement) {
        console.error("Thiếu các phần tử HTML cơ bản (quizAudioPlayer hoặc quizJsDataElement).");
        return;
    }

    const questionId = quizJsDataElement.dataset.questionId;
    const questionAudioFile = quizJsDataElement.dataset.questionAudioFile;

    // Chỉ xử lý customControlsContainer nếu có questionAudioFile
    if (questionAudioFile) {
        if (customControlsContainer) customControlsContainer.style.display = 'flex';
        
        let audioSrc = '';
        if (questionAudioFile.startsWith('http://') || questionAudioFile.startsWith('https://')) {
            audioSrc = questionAudioFile;
        } else {
            audioSrc = `/api/quiz_audio/${questionId}`;
        }
        quizAudioPlayer.src = audioSrc; // Đặt nguồn âm thanh
        quizAudioPlayer.load(); // Tải âm thanh
        
    } else {
        if (customControlsContainer) customControlsContainer.style.display = 'none';
        return; // Không có audio thì không cần thiết lập các listener
    }

    // Logic điều khiển tùy chỉnh
    if (playPauseBtn) {
        playPauseBtn.addEventListener('click', () => {
            if (quizAudioPlayer.paused) {
                quizAudioPlayer.play().catch(error => {
                    console.error("Lỗi khi phát audio thủ công:", error);
                });
            } else {
                quizAudioPlayer.pause();
            }
        });
    }

    quizAudioPlayer.addEventListener('play', () => {
        if (playPauseBtn) playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
    });

    quizAudioPlayer.addEventListener('pause', () => {
        if (playPauseBtn) playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
    });

    quizAudioPlayer.addEventListener('ended', () => {
        if (playPauseBtn) playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
        if (progressFill) progressFill.style.width = '0%'; // Reset thanh tiến trình
        // BẮT ĐẦU SỬA ĐỔI: Loại bỏ reset thời gian hiện tại (vì không hiển thị)
        // if (currentTimeSpan) currentTimeSpan.textContent = '0:00';
        // KẾT THÚC SỬA ĐỔI
    });

    quizAudioPlayer.addEventListener('timeupdate', () => {
        if (progressFill) {
            const progress = (quizAudioPlayer.currentTime / quizAudioPlayer.duration) * 100;
            progressFill.style.width = `${progress}%`;
        }
        // BẮT ĐẦU SỬA ĐỔI: Loại bỏ cập nhật thời gian hiện tại (vì không hiển thị)
        // if (currentTimeSpan) currentTimeSpan.textContent = formatTime(quizAudioPlayer.currentTime);
        // KẾT THÚC SỬA ĐỔI
    });

    quizAudioPlayer.addEventListener('loadedmetadata', () => {
        // BẮT ĐẦU THÊM MỚI: Cập nhật tổng thời gian
        if (durationTimeSpan) durationTimeSpan.textContent = formatTime(quizAudioPlayer.duration);
        // KẾT THÚC THÊM MỚI
        // BẮT ĐẦU SỬA ĐỔI: Loại bỏ cập nhật slider volume (vì không hiển thị)
        // if (volumeSlider) volumeSlider.value = quizAudioPlayer.volume;
        // KẾT THÚC SỬA ĐỔI
    });

    if (progressBar) {
        progressBar.addEventListener('click', (e) => {
            const clickX = e.offsetX;
            const width = progressBar.offsetWidth;
            const duration = quizAudioPlayer.duration;
            quizAudioPlayer.currentTime = (clickX / width) * duration;
        });
    }

    // BẮT ĐẦU SỬA ĐỔI: Loại bỏ logic điều khiển âm lượng và thời gian hiện tại
    // if (volumeBtn) { ... }
    // if (volumeSlider) { ... }
    // KẾT THÚC SỬA ĐỔI

    // Hàm định dạng thời gian (ví dụ: 0:00) - Giữ lại hàm vì vẫn dùng cho tổng thời gian
    function formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.floor(seconds % 60);
        return `${minutes}:${remainingSeconds < 10 ? '0' : ''}${remainingSeconds}`;
    }
});
