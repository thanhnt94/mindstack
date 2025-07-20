// web_app/static/js/quiz_audio_image_handler.js

/**
 * Mô tả: Xử lý logic phát audio cho câu hỏi trắc nghiệm.
 * Được điều chỉnh để hỗ trợ nhiều trình phát audio trên cùng một trang,
 * bao gồm cả audio chung cho một nhóm câu hỏi.
 */
document.addEventListener('DOMContentLoaded', function() {
    const quizJsDataElement = document.getElementById('quizJsData');
    if (!quizJsDataElement) {
        console.warn("quiz_audio_image_handler.js: Thiếu phần tử HTML quizJsData. Script sẽ không chạy.");
        return;
    }

    // Lấy tất cả dữ liệu câu hỏi được truyền từ backend
    const allQuestionsData = JSON.parse(quizJsDataElement.dataset.questionsData || '[]');
    console.log("quiz_audio_image_handler.js: Loaded allQuestionsData for audio/image handler:", allQuestionsData);

    // BẮT ĐẦU THÊM MỚI: Xử lý trình phát audio chung (nếu có)
    const commonAudioControlContainer = document.querySelector('.question-audio-controls.common-audio-controls .quiz-audio-controls-custom');
    if (commonAudioControlContainer) {
        const commonAudioFile = commonAudioControlContainer.dataset.audioFile; // Giờ đây là đường dẫn đầy đủ
        const commonAudioPlayer = document.getElementById('quizAudioPlayer-common');
        if (commonAudioPlayer && commonAudioFile && commonAudioFile.trim() !== '') {
            initializeAudioPlayer(commonAudioPlayer, commonAudioControlContainer, commonAudioFile, 'common');
        } else {
            commonAudioControlContainer.style.display = 'none'; // Ẩn nếu không có file
            console.log("quiz_audio_image_handler.js: Common audio controls hidden due to no file.");
        }
    }
    // KẾT THÚC THÊM MỚI

    // Xử lý các trình phát audio riêng lẻ cho từng câu hỏi
    document.querySelectorAll('.quiz-audio-controls-custom:not([data-question-id="common"])').forEach(controlContainer => {
        const questionId = parseInt(controlContainer.dataset.questionId);
        const quizAudioPlayer = document.getElementById(`quizAudioPlayer-${questionId}`);
        
        const currentQuestionData = allQuestionsData.find(q_data => q_data.obj.question_id === questionId);
        
        // Kiểm tra cờ display_audio_controls từ backend
        if (!currentQuestionData || !currentQuestionData.display_audio_controls || 
            !currentQuestionData.obj.question_audio_file || currentQuestionData.obj.question_audio_file.trim() === '') {
            controlContainer.style.display = 'none'; // Ẩn nếu không nên hiển thị hoặc không có file
            console.log(`quiz_audio_image_handler.js: Q${questionId} - Individual audio controls hidden.`);
            return;
        }

        const questionAudioFile = currentQuestionData.obj.question_audio_file; // Giờ đây là đường dẫn đầy đủ
        initializeAudioPlayer(quizAudioPlayer, controlContainer, questionAudioFile, questionId);
    });

    /**
     * Mô tả: Khởi tạo và gắn sự kiện cho một trình phát audio cụ thể.
     * @param {HTMLAudioElement} audioPlayer - Đối tượng audio HTML.
     * @param {HTMLElement} controlContainer - Phần tử chứa các điều khiển tùy chỉnh.
     * @param {string} audioFile - Đường dẫn đầy đủ của file audio (ví dụ: "study4_toeic/hash.mp3") hoặc URL.
     * @param {string|number} idForLog - ID để log (questionId hoặc 'common').
     */
    function initializeAudioPlayer(audioPlayer, controlContainer, audioFile, idForLog) {
        const playPauseBtn = controlContainer.querySelector('.play-pause-btn');
        const progressBar = controlContainer.querySelector('.progress-bar');
        const progressFill = controlContainer.querySelector('.progress-fill');
        const durationTimeSpan = controlContainer.querySelector('.time-display');

        if (!audioPlayer || !playPauseBtn || !progressBar || !progressFill || !durationTimeSpan) {
            console.warn(`quiz_audio_image_handler.js: Missing elements for audio player ${idForLog}.`);
            controlContainer.style.display = 'none';
            return;
        }

        let audioSrc = '';
        if (audioFile.startsWith('http://') || audioFile.startsWith('https://')) {
            audioSrc = audioFile;
            console.log(`quiz_audio_image_handler.js: ${idForLog} - Audio source is external URL: ${audioSrc}`);
        } else {
            // BẮT ĐẦU THAY ĐỔI: Gửi đường dẫn đầy đủ đến API
            audioSrc = `/api/quiz_audio/${audioFile}`; 
            console.log(`quiz_audio_image_handler.js: ${idForLog} - Audio source is local API: ${audioSrc}`);
        }
        audioPlayer.src = audioSrc;
        audioPlayer.load();
        
        controlContainer.style.display = 'flex'; // Đảm bảo hiển thị control

        playPauseBtn.addEventListener('click', () => {
            console.log(`quiz_audio_image_handler.js: ${idForLog} - Play/Pause button clicked. Current state: paused=${audioPlayer.paused}`);
            if (audioPlayer.paused) {
                document.querySelectorAll('audio').forEach(otherPlayer => {
                    if (otherPlayer !== audioPlayer && !otherPlayer.paused) {
                        otherPlayer.pause();
                        const otherPlayPauseBtn = otherPlayer.closest('.question-audio-controls').querySelector('.play-pause-btn');
                        if (otherPlayPauseBtn) {
                            otherPlayPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
                        }
                        console.log(`quiz_audio_image_handler.js: Paused other player.`);
                    }
                });
                audioPlayer.play().catch(error => {
                    console.error(`quiz_audio_image_handler.js: ${idForLog} - Lỗi khi phát audio thủ công:`, error);
                });
            } else {
                audioPlayer.pause();
            }
        });

        audioPlayer.addEventListener('play', () => {
            playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
            console.log(`quiz_audio_image_handler.js: ${idForLog} - Audio playing.`);
        });

        audioPlayer.addEventListener('pause', () => {
            playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
            console.log(`quiz_audio_image_handler.js: ${idForLog} - Audio paused.`);
        });

        audioPlayer.addEventListener('ended', () => {
            playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
            progressFill.style.width = '0%';
            console.log(`quiz_audio_image_handler.js: ${idForLog} - Audio ended.`);
        });

        audioPlayer.addEventListener('timeupdate', () => {
            if (audioPlayer.duration && !isNaN(audioPlayer.duration)) {
                const progress = (audioPlayer.currentTime / audioPlayer.duration) * 100;
                progressFill.style.width = `${progress}%`;
            }
        });

        audioPlayer.addEventListener('loadedmetadata', () => {
            if (audioPlayer.duration && !isNaN(audioPlayer.duration)) {
                durationTimeSpan.textContent = formatTime(audioPlayer.duration);
                console.log(`quiz_audio_image_handler.js: ${idForLog} - Audio metadata loaded. Duration: ${formatTime(audioPlayer.duration)}`);
            } else {
                durationTimeSpan.textContent = '0:00';
                console.warn(`quiz_audio_image_handler.js: ${idForLog} - Audio duration not valid.`);
            }
        });

        progressBar.addEventListener('click', (e) => {
            console.log(`quiz_audio_image_handler.js: ${idForLog} - Progress bar clicked.`);
            const clickX = e.offsetX;
            const width = progressBar.offsetWidth;
            const duration = audioPlayer.duration;
            if (duration && !isNaN(duration)) {
                audioPlayer.currentTime = (clickX / width) * duration;
                console.log(`quiz_audio_image_handler.js: ${idForLog} - Set current time to: ${audioPlayer.currentTime}`);
            }
        });
    }

    function formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.floor(seconds % 60);
        return `${minutes}:${remainingSeconds < 10 ? '0' : ''}${remainingSeconds}`;
    }
});
