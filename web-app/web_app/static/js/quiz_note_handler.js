// web_app/static/js/quiz_note_handler.js

/**
 * Mô tả: Xử lý logic cho chức năng ghi chú trên trang quiz, bao gồm mở/đóng modal và lưu ghi chú qua API.
 * Được điều chỉnh để hỗ trợ nhiều nút ghi chú trên cùng một trang.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Lấy các phần tử DOM cần thiết
    const noteModal = document.getElementById('quiz-note-modal');
    const closeNoteBtn = document.getElementById('quiz-note-modal-close-btn');
    const saveNoteBtn = document.getElementById('save-quiz-note-btn');
    const noteTextarea = document.getElementById('quiz-note-textarea');
    const noteSaveStatus = document.getElementById('quiz-note-save-status');

    // Biến để lưu trữ question_id của câu hỏi hiện tại đang được chỉnh sửa ghi chú
    let currentQuestionIdForNote = null;

    // Chỉ chạy script nếu các phần tử modal cần thiết tồn tại
    if (!noteModal || !closeNoteBtn || !saveNoteBtn) {
        console.warn("Thiếu các phần tử HTML cần thiết cho Quiz Note Modal. Script sẽ không chạy.");
        return;
    }

    // Lắng nghe sự kiện click trên TẤT CẢ các nút "Ghi chú"
    document.querySelectorAll('.open-quiz-note-btn').forEach(openNoteBtn => {
        openNoteBtn.addEventListener('click', function() {
            // Lấy question_id từ data attribute của nút được click
            currentQuestionIdForNote = this.dataset.questionId;
            openNoteModal();
        });
    });

    /**
     * Mô tả: Mở modal ghi chú và tải nội dung ghi chú hiện tại từ server cho câu hỏi đang chọn.
     */
    async function openNoteModal() {
        if (!currentQuestionIdForNote) {
            console.error("Không có Question ID để mở ghi chú.");
            return;
        }

        // Hiển thị trạng thái đang tải
        noteTextarea.value = "Đang tải ghi chú...";
        noteModal.style.display = 'flex';

        try {
            // Gọi API để lấy ghi chú cho currentQuestionIdForNote
            const response = await fetch(`/api/quiz_note/${currentQuestionIdForNote}`);
            if (!response.ok) {
                throw new Error('Không thể kết nối đến máy chủ.');
            }
            const data = await response.json();
            // Điền nội dung vào textarea
            noteTextarea.value = data.note || '';
        } catch (error) {
            console.error('Lỗi khi tải ghi chú:', error);
            noteTextarea.value = 'Không thể tải ghi chú. Vui lòng thử lại sau.';
        }
    }

    /**
     * Mô tả: Đóng modal ghi chú.
     */
    function closeNoteModal() {
        noteModal.style.display = 'none';
        currentQuestionIdForNote = null; // Reset ID khi đóng modal
    }

    /**
     * Mô tả: Lưu nội dung ghi chú hiện tại trong textarea vào database thông qua API.
     */
    async function saveNote() {
        if (!currentQuestionIdForNote) {
            console.error("Không có Question ID để lưu ghi chú.");
            return;
        }

        const noteContent = noteTextarea.value;
        noteSaveStatus.style.color = '#28a745'; // Reset màu về màu thành công
        noteSaveStatus.textContent = 'Đang lưu...';
        noteSaveStatus.style.opacity = 1;

        try {
            // Gọi API để lưu ghi chú cho currentQuestionIdForNote
            const response = await fetch(`/api/quiz_note/${currentQuestionIdForNote}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ note: noteContent }),
            });

            if (!response.ok) {
                throw new Error('Lỗi từ máy chủ khi lưu ghi chú.');
            }

            const result = await response.json();

            // Hiển thị thông báo thành công và làm mờ dần
            if (result.status === 'updated' || result.status === 'created') {
                noteSaveStatus.textContent = 'Đã lưu!';
                // Cập nhật trạng thái nút "Ghi chú" trên giao diện
                const clickedNoteBtn = document.querySelector(`.open-quiz-note-btn[data-question-id="${currentQuestionIdForNote}"]`);
                if (clickedNoteBtn) {
                    clickedNoteBtn.classList.add('has-note');
                }

                setTimeout(() => {
                    noteSaveStatus.style.opacity = 0;
                }, 2000); // Giữ thông báo trong 2 giây
            } else {
                 throw new Error(result.message || 'Lỗi không xác định.');
            }

        } catch (error) {
            console.error('Lỗi khi lưu ghi chú:', error);
            // Hiển thị thông báo lỗi
            noteSaveStatus.textContent = 'Lỗi!';
            noteSaveStatus.style.color = '#dc3545'; // Màu đỏ cho lỗi
            setTimeout(() => {
                noteSaveStatus.style.opacity = 0;
            }, 3000); // Giữ thông báo lỗi trong 3 giây
        }
    }

    // Gắn các sự kiện cho các nút trong modal
    closeNoteBtn.addEventListener('click', closeNoteModal);
    saveNoteBtn.addEventListener('click', saveNote);

    // Đóng modal khi người dùng nhấp vào vùng nền mờ bên ngoài
    window.addEventListener('click', function(event) {
        if (event.target === noteModal) {
            closeNoteModal();
        }
    });
});
