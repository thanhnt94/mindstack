// learn_card_audio.js

document.addEventListener('DOMContentLoaded', function() {
    // Lấy các phần tử DOM cần thiết
    const playAudioButton = document.getElementById('playAudioButton');
    const cardAudioPlayer = document.getElementById('cardAudioPlayer');
    const jsDataElement = document.getElementById('jsData');

    // Lấy dữ liệu từ các thuộc tính data của div jsData
    const flashcardData = JSON.parse(jsDataElement.dataset.flashcard);
    const isFront = jsDataElement.dataset.isFront === 'true';
    const userAudioSettings = JSON.parse(jsDataElement.dataset.userAudioSettings);

    /**
     * Mô tả: Phát âm thanh cho thẻ dựa trên mặt hiện tại và cài đặt của người dùng.
     * Kiểm tra xem có nội dung audio và cài đặt cho phép phát hay không.
     * @param {boolean} forcePlay - Nếu là true, sẽ cố gắng phát audio bất kể cài đặt người dùng (chỉ cho mặt hiện tại).
     */
    function playCardAudio(forcePlay = false) { // Thêm tham số forcePlay với giá trị mặc định là false
        if (!flashcardData) {
            console.warn("Không có dữ liệu flashcard để phát audio.");
            return;
        }

        let audioContent = null;
        let audioEnabled = false;

        if (isFront) {
            audioContent = flashcardData.front_audio_content;
            // Kích hoạt phát nếu forcePlay là true HOẶC cài đặt của người dùng cho phép
            audioEnabled = forcePlay || userAudioSettings.front_audio_enabled;
        } else { // isBackSide
            audioContent = flashcardData.back_audio_content;
            // Kích hoạt phát nếu forcePlay là true HOẶC cài đặt của người dùng cho phép
            audioEnabled = forcePlay || userAudioSettings.back_audio_enabled;
        }

        if (audioContent && audioEnabled) {
            // Gọi API để lấy file audio
            const audioUrl = `/api/card_audio/${flashcardData.flashcard_id}/${isFront ? 'front' : 'back'}`;
            cardAudioPlayer.src = audioUrl;
            cardAudioPlayer.play().catch(error => {
                console.error("Lỗi khi cố gắng phát audio:", error);
                // Hiển thị thông báo lỗi thân thiện với người dùng nếu cần
            });
        } else {
            console.log("Audio không được bật hoặc không có nội dung audio cho mặt này.");
        }
    }

    // Gắn sự kiện click cho nút play audio
    if (playAudioButton) {
        // Khi click nút, không forcePlay, để nó tôn trọng cài đặt người dùng
        playAudioButton.addEventListener('click', () => playCardAudio(false));
    }

    // Tự động phát audio khi thẻ được tải (nếu có)
    if (flashcardData) {
        // Tự động phát audio ở mặt trước khi tải trang (forcePlay = true để bỏ qua cài đặt người dùng cho lần đầu)
        if (isFront) {
            playCardAudio(true); // Force play for the front side on load
        }
        // Đối với mặt sau, không tự động phát khi tải trang, chỉ khi người dùng click nút
        // (logic này đã được xử lý bởi isFront check ở trên và button click listener)
    }
});
