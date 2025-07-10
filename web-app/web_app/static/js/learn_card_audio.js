// learn_card_audio.js

document.addEventListener('DOMContentLoaded', function() {
    // --- Lấy các phần tử và dữ liệu cần thiết từ DOM ---
    const cardAudioPlayer = document.getElementById('cardAudioPlayer');
    const playAudioButton = document.getElementById('playAudioButton');
    const jsDataElement = document.getElementById('jsData');

    if (!cardAudioPlayer || !playAudioButton || !jsDataElement) {
        console.error("Thiếu các phần tử HTML cần thiết.");
        return;
    }

    // --- Trích xuất dữ liệu từ các thuộc tính data-* ---
    const audioUrl = jsDataElement.dataset.audioUrl;
    const isAutoplayMode = jsDataElement.dataset.isAutoplayMode === 'true';
    const userAudioSettings = JSON.parse(jsDataElement.dataset.userAudioSettings);
    const isFront = jsDataElement.dataset.isFront === 'true';
    const hasBackAudioContent = jsDataElement.dataset.hasBackAudioContent === 'true';

    /**
     * Mô tả: Hàm cốt lõi để phát audio.
     * Nó chỉ thực hiện một việc: gán src và play.
     */
    function playAudio() {
        if (audioUrl) {
            // SỬA LỖI: Reset trình phát trước khi gán nguồn mới
            // để tránh lỗi trạng thái "kẹt" trên một số trình duyệt.
            cardAudioPlayer.load(); 
            cardAudioPlayer.src = audioUrl;
            cardAudioPlayer.play().catch(error => {
                console.error("Lỗi khi phát audio:", error);
            });
        } else {
            console.log("Không có URL audio để phát.");
        }
    }

    // --- Gắn sự kiện cho nút bấm thủ công ---
    // Logic này đảm bảo nút bấm luôn hoạt động ở mọi chế độ.
    playAudioButton.addEventListener('click', playAudio);

    // ===================================================================
    // LOGIC RIÊNG BIỆT CHO CHẾ ĐỘ AUTOPLAY
    // ===================================================================
    if (isAutoplayMode) {
        const POST_AUDIO_DELAY_MS = 1500;
        const MASTER_TIMEOUT_MS = 10000;
        let actionTriggered = false;
        let masterTimeoutId = null;

        function performRedirect() {
            if (actionTriggered) return;
            actionTriggered = true;
            if (masterTimeoutId) clearTimeout(masterTimeoutId);

            const targetLink = isFront ? 
                document.querySelector('.flashcard-footer a.button') : 
                document.querySelector('.flashcard-footer a.button.primary');

            if (targetLink) {
                window.location.href = targetLink.href;
            }
        }

        function handleAudioEnd() {
            setTimeout(performRedirect, POST_AUDIO_DELAY_MS);
        }

        cardAudioPlayer.addEventListener('ended', handleAudioEnd);

        // Bắt đầu chu trình Autoplay
        setTimeout(() => {
            masterTimeoutId = setTimeout(performRedirect, MASTER_TIMEOUT_MS);
            
            if (audioUrl) {
                playAudio();
            } else {
                // Nếu không có audio, chuyển ngay
                handleAudioEnd();
            }
        }, 1000);
    } 
    // ===================================================================
    // LOGIC TỰ ĐỘNG PHÁT CHO CHẾ ĐỘ THƯỜNG
    // ===================================================================
    else {
        let shouldAutoplayOnLoad = false;
        if (isFront) {
            shouldAutoplayOnLoad = userAudioSettings.front_audio_enabled;
        } else {
            // Mặt sau chỉ tự phát khi có cài đặt và có cache
            shouldAutoplayOnLoad = userAudioSettings.back_audio_enabled && hasBackAudioContent;
        }

        if (shouldAutoplayOnLoad && audioUrl) {
            setTimeout(playAudio, 300);
        }
    }
});
