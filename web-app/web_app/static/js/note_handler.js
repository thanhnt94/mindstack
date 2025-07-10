// web_app/static/js/note_handler.js

/**
 * Mô tả: Xử lý logic cho chức năng ghi chú, bao gồm mở/đóng modal và lưu ghi chú qua API.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Lấy các phần tử DOM cần thiết
    const noteModal = document.getElementById('note-modal');
    const openNoteBtn = document.getElementById('open-note-btn');
    const closeNoteBtn = document.getElementById('note-modal-close-btn');
    const saveNoteBtn = document.getElementById('save-note-btn');
    const noteTextarea = document.getElementById('note-textarea');
    const noteSaveStatus = document.getElementById('note-save-status');
    const jsDataElement = document.getElementById('jsData');

    // --- BẮT ĐẦU SỬA LỖI: Kiểm tra chế độ Autoplay ---
    // Lấy thông tin về chế độ autoplay từ data attribute
    const isAutoplayMode = jsDataElement.dataset.isAutoplayMode === 'true';

    // Nếu đang ở chế độ Autoplay, ẩn nút ghi chú và dừng script này lại ngay lập tức
    if (isAutoplayMode) {
        if (openNoteBtn) {
            openNoteBtn.style.display = 'none'; // Ẩn nút ghi chú
        }
        return; // Không chạy bất kỳ mã nào khác của chức năng ghi chú
    }
    // --- KẾT THÚC SỬA LỖI ---

    // Chỉ chạy script nếu các phần tử cần thiết tồn tại trên trang
    if (!noteModal || !openNoteBtn || !closeNoteBtn || !saveNoteBtn || !jsDataElement) {
        return;
    }

    // Lấy flashcard_id từ thuộc tính data-*
    const flashcardId = jsDataElement.dataset.flashcardId;

    /**
     * Mô tả: Mở modal ghi chú và tải nội dung ghi chú hiện tại từ server.
     */
    async function openNoteModal() {
        // Hiển thị trạng thái đang tải
        noteTextarea.value = "Đang tải ghi chú...";
        noteModal.style.display = 'flex';

        try {
            // Gọi API để lấy ghi chú
            const response = await fetch(`/api/note/${flashcardId}`);
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
    }

    /**
     * Mô tả: Lưu nội dung ghi chú hiện tại trong textarea vào database thông qua API.
     */
    async function saveNote() {
        const noteContent = noteTextarea.value;
        noteSaveStatus.style.color = '#28a745'; // Reset màu về màu thành công
        noteSaveStatus.textContent = 'Đang lưu...';
        noteSaveStatus.style.opacity = 1;

        try {
            // Gọi API để lưu ghi chú
            const response = await fetch(`/api/note/${flashcardId}`, {
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

    // Gắn các sự kiện cho các nút
    openNoteBtn.addEventListener('click', openNoteModal);
    closeNoteBtn.addEventListener('click', closeNoteModal);
    saveNoteBtn.addEventListener('click', saveNote);

    // Đóng modal khi người dùng nhấp vào vùng nền mờ bên ngoài
    window.addEventListener('click', function(event) {
        if (event.target === noteModal) {
            closeNoteModal();
        }
    });
});
