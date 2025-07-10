// web_app/static/js/edit_handler.js

/**
 * Mô tả: Xử lý logic cho chức năng sửa flashcard, bao gồm mở/đóng modal,
 * lấy dữ liệu, lưu thay đổi qua API và cập nhật giao diện.
 */
document.addEventListener('DOMContentLoaded', function() {
    // Lấy các phần tử DOM và dữ liệu cần thiết
    const jsData = document.getElementById('jsData');
    const canEdit = jsData.dataset.canEdit === 'true';

    // Nếu người dùng không có quyền sửa, dừng script ngay lập tức
    if (!canEdit) {
        return;
    }

    const editModal = document.getElementById('edit-modal');
    const openEditBtn = document.getElementById('open-edit-btn');
    const closeEditBtn = document.getElementById('edit-modal-close-btn');
    const saveEditBtn = document.getElementById('save-edit-btn');
    const editSaveStatus = document.getElementById('edit-save-status');
    const flashcardId = jsData.dataset.flashcardId;

    // Các trường input trong modal
    const editFront = document.getElementById('edit-front');
    const editBack = document.getElementById('edit-back');
    const editFrontAudio = document.getElementById('edit-front-audio');
    const editBackAudio = document.getElementById('edit-back-audio');
    const editFrontImg = document.getElementById('edit-front-img');
    const editBackImg = document.getElementById('edit-back-img');

    // Phần tử hiển thị nội dung thẻ trên trang chính
    const mainCardText = document.querySelector('.flashcard-body .card-text');

    /**
     * Mô tả: Mở modal sửa thẻ và tải dữ liệu chi tiết của thẻ từ server.
     */
    async function openEditModal() {
        if (!editModal) return;

        // Hiển thị trạng thái đang tải
        editFront.value = "Đang tải...";
        editBack.value = "Đang tải...";
        // ... có thể thêm cho các trường khác
        editModal.style.display = 'flex';

        try {
            const response = await fetch(`/api/flashcard/details/${flashcardId}`);
            if (!response.ok) {
                throw new Error('Không thể lấy chi tiết thẻ từ máy chủ.');
            }
            const result = await response.json();

            if (result.status === 'success') {
                // Điền dữ liệu lấy được vào các ô input
                const cardData = result.data;
                editFront.value = cardData.front || '';
                editBack.value = cardData.back || '';
                editFrontAudio.value = cardData.front_audio_content || '';
                editBackAudio.value = cardData.back_audio_content || '';
                editFrontImg.value = cardData.front_img || '';
                editBackImg.value = cardData.back_img || '';
            } else {
                throw new Error(result.message || 'Lỗi không xác định từ server.');
            }
        } catch (error) {
            console.error('Lỗi khi tải chi tiết thẻ:', error);
            editFront.value = 'Không thể tải dữ liệu. Vui lòng thử lại.';
            editBack.value = '';
        }
    }

    /**
     * Mô tả: Đóng modal sửa thẻ.
     */
    function closeEditModal() {
        if (editModal) {
            editModal.style.display = 'none';
        }
    }

    /**
     * Mô tả: Thu thập dữ liệu từ form, gửi lên API để lưu và cập nhật giao diện.
     */
    async function saveCardChanges() {
        editSaveStatus.style.color = '#28a745'; // Màu thành công
        editSaveStatus.textContent = 'Đang lưu...';
        editSaveStatus.style.opacity = 1;

        // Thu thập dữ liệu từ các ô input
        const updatedData = {
            front: editFront.value,
            back: editBack.value,
            front_audio_content: editFrontAudio.value,
            back_audio_content: editBackAudio.value,
            front_img: editFrontImg.value,
            back_img: editBackImg.value
        };

        try {
            const response = await fetch(`/api/flashcard/edit/${flashcardId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(updatedData),
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                editSaveStatus.textContent = 'Đã lưu!';

                // Cập nhật nội dung thẻ trên trang chính một cách linh động
                const isFront = jsData.dataset.isFront === 'true';
                if (isFront) {
                    mainCardText.textContent = result.data.front;
                } else {
                    mainCardText.textContent = result.data.back;
                }
                
                // Cập nhật cả popup ảnh nếu có
                // (Phần này có thể được cải tiến thêm để ẩn/hiện popup nếu ảnh được thêm/xóa)

                setTimeout(() => {
                    editSaveStatus.style.opacity = 0;
                    closeEditModal();
                    // Cân nhắc tải lại trang để cập nhật audio và các thông tin khác
                    // window.location.reload(); 
                }, 1500); // Đợi 1.5 giây rồi đóng modal
            } else {
                throw new Error(result.message || 'Lỗi không xác định khi lưu.');
            }

        } catch (error) {
            console.error('Lỗi khi lưu thay đổi thẻ:', error);
            editSaveStatus.textContent = `Lỗi: ${error.message}`;
            editSaveStatus.style.color = '#dc3545'; // Màu đỏ cho lỗi
            setTimeout(() => {
                editSaveStatus.style.opacity = 0;
            }, 4000); // Giữ thông báo lỗi lâu hơn
        }
    }

    // Gắn các sự kiện
    if (openEditBtn) {
        openEditBtn.addEventListener('click', openEditModal);
    }
    if (closeEditBtn) {
        closeEditBtn.addEventListener('click', closeEditModal);
    }
    if (saveEditBtn) {
        saveEditBtn.addEventListener('click', saveCardChanges);
    }

    // Đóng modal khi nhấn ra ngoài
    window.addEventListener('click', function(event) {
        if (event.target === editModal) {
            closeEditModal();
        }
    });
});
