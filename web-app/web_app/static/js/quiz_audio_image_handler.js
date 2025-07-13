// web_app/static/js/quiz_audio_image_handler.js

/**
 * Mô tả: Xử lý logic phát audio cho câu hỏi trắc nghiệm.
 */
document.addEventListener('DOMContentLoaded', function() {
    const quizAudioPlayer = document.getElementById('quizAudioPlayer');
    const quizJsDataElement = document.getElementById('quizJsData');

    // BẮT ĐẦU THÊM MỚI: Lấy các phần tử điều khiển tùy chỉnh
    const customControlsContainer = document.querySelector('.quiz-audio-controls-custom');
    const playPauseBtn = document.getElementById('playPauseBtn');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    const currentTimeSpan = document.getElementById('currentTime');
    const durationTimeSpan = document.getElementById('durationTime');
    const volumeBtn = document.getElementById('volumeBtn');
    const volumeSlider = document.getElementById('volumeSlider');
    const noAudioMessage = document.querySelector('.no-audio-message');
    // KẾT THÚC THÊM MỚI

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại
    if (!quizAudioPlayer || !quizJsDataElement) {
        // Nếu không có player hoặc jsData, có thể không có audio, hoặc lỗi HTML
        // Console log để debug, nhưng không dừng script hoàn toàn nếu chỉ thiếu customControlsContainer
        console.error("Thiếu các phần tử HTML cơ bản (quizAudioPlayer hoặc quizJsDataElement).");
        return;
    }

    const questionId = quizJsDataElement.dataset.questionId;
    const questionAudioFile = quizJsDataElement.dataset.questionAudioFile;

    // BẮT ĐẦU THÊM MỚI: Ẩn/hiện custom controls dựa vào questionAudioFile
    if (questionAudioFile) {
        if (customControlsContainer) customControlsContainer.style.display = 'flex';
        if (noAudioMessage) noAudioMessage.style.display = 'none';
        
        let audioSrc = '';
        if (questionAudioFile.startsWith('http://') || questionAudioFile.startsWith('https://')) {
            audioSrc = questionAudioFile;
        } else {
            audioSrc = `/api/quiz_audio/${questionId}`;
        }
        quizAudioPlayer.src = audioSrc; // Đặt nguồn âm thanh
        quizAudioPlayer.load(); // Tải âm thanh
        
        // Tự động phát khi trang tải (với độ trễ nhỏ để trình duyệt sẵn sàng)
        // Cần xử lý Promise để bắt lỗi chặn autoplay của trình duyệt
        setTimeout(() => {
            quizAudioPlayer.play().then(() => {
                console.log("Audio tự động phát thành công.");
            }).catch(error => {
                console.warn("Tự động phát audio bị chặn hoặc lỗi:", error);
                // Cập nhật icon play nếu không tự động phát được
                if (playPauseBtn) playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
            });
        }, 500);

    } else {
        if (customControlsContainer) customControlsContainer.style.display = 'none';
        if (noAudioMessage) noAudioMessage.style.display = 'block';
        return; // Không có audio thì không cần thiết lập các listener
    }
    // KẾT THÚC THÊM MỚI

    // BẮT ĐẦU THÊM MỚI: Logic điều khiển tùy chỉnh
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
        progressFill.style.width = '0%'; // Reset thanh tiến trình
        currentTimeSpan.textContent = '0:00'; // Reset thời gian hiện tại
    });

    quizAudioPlayer.addEventListener('timeupdate', () => {
        const progress = (quizAudioPlayer.currentTime / quizAudioPlayer.duration) * 100;
        progressFill.style.width = `${progress}%`;
        currentTimeSpan.textContent = formatTime(quizAudioPlayer.currentTime);
    });

    quizAudioPlayer.addEventListener('loadedmetadata', () => {
        durationTimeSpan.textContent = formatTime(quizAudioPlayer.duration);
        volumeSlider.value = quizAudioPlayer.volume; // Cập nhật slider volume ban đầu
    });

    if (progressBar) {
        progressBar.addEventListener('click', (e) => {
            const clickX = e.offsetX;
            const width = progressBar.offsetWidth;
            const duration = quizAudioPlayer.duration;
            quizAudioPlayer.currentTime = (clickX / width) * duration;
        });
    }

    if (volumeBtn) {
        volumeBtn.addEventListener('click', () => {
            if (quizAudioPlayer.muted) {
                quizAudioPlayer.muted = false;
                volumeBtn.innerHTML = '<i class="fas fa-volume-up"></i>';
                volumeSlider.value = quizAudioPlayer.volume; // Khôi phục slider về volume trước khi mute
            } else {
                quizAudioPlayer.muted = true;
                volumeBtn.innerHTML = '<i class="fas fa-volume-mute"></i>';
                volumeSlider.value = 0; // Đặt slider về 0 khi mute
            }
        });
    }

    if (volumeSlider) {
        volumeSlider.addEventListener('input', () => {
            quizAudioPlayer.volume = volumeSlider.value;
            if (volumeSlider.value == 0) {
                quizAudioPlayer.muted = true;
                volumeBtn.innerHTML = '<i class="fas fa-volume-mute"></i>';
            } else {
                quizAudioPlayer.muted = false;
                volumeBtn.innerHTML = '<i class="fas fa-volume-up"></i>';
            }
        });
    }

    // Hàm định dạng thời gian (ví dụ: 0:00)
    function formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.floor(seconds % 60);
        return `${minutes}:${remainingSeconds < 10 ? '0' : ''}${remainingSeconds}`;
    }
    // KẾT THÚC THÊM MỚI
});

