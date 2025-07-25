// web_app/static/js/edit_handler.js

/**
 * Mô tả: Xử lý logic cho chức năng sửa flashcard, bao gồm mở/đóng modal,
 * lấy dữ liệu, lưu thay đổi và tái tạo audio qua API.
 * Đã được cập nhật để hỗ trợ nhiều nút sửa trên cùng một trang.
 */
document.addEventListener('DOMContentLoaded', function() {
    const editModal = document.getElementById('edit-modal');
    // Bỏ qua việc kiểm tra jsData và canEdit vì trang feedback có thể không có
    // const jsData = document.getElementById('jsData');
    // const canEdit = jsData && jsData.dataset.canEdit === 'true';
    // if (!canEdit) {
    //     return;
    // }

    // Chỉ chạy nếu có modal trên trang
    if (!editModal) {
        return;
    }

    const closeEditBtn = document.getElementById('edit-modal-close-btn');
    const saveEditBtn = document.getElementById('save-edit-btn');
    const editSaveStatus = document.getElementById('edit-save-status');
    
    // Biến để lưu ID của thẻ đang được sửa
    let currentFlashcardId = null;

    const editFront = document.getElementById('edit-front');
    const editBack = document.getElementById('edit-back');
    const editFrontAudio = document.getElementById('edit-front-audio');
    const editBackAudio = document.getElementById('edit-back-audio');
    const editFrontImg = document.getElementById('edit-front-img');
    const editBackImg = document.getElementById('edit-back-img');

    // Tìm thẻ main-card-text nếu có (trên trang học)
    const mainCardText = document.querySelector('.flashcard-body .card-text');

    /**
     * Mô tả: Mở modal và tải dữ liệu cho thẻ được chọn.
     */
    async function openEditModal() {
        if (!editModal || !currentFlashcardId) return;

        editFront.value = "Đang tải...";
        editBack.value = "Đang tải...";
        editModal.style.display = 'flex';

        try {
            const response = await fetch(`/api/flashcard/details/${currentFlashcardId}`);
            if (!response.ok) {
                throw new Error('Không thể lấy chi tiết thẻ từ máy chủ.');
            }
            const result = await response.json();

            if (result.status === 'success') {
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
     * Mô tả: Đóng modal sửa lỗi.
     */
    function closeEditModal() {
        if (editModal) {
            editModal.style.display = 'none';
            currentFlashcardId = null; // Reset ID
        }
    }

    /**
     * Mô tả: Lưu các thay đổi vào DB.
     */
    async function saveCardChanges() {
        if (!currentFlashcardId) return;

        editSaveStatus.style.color = '#28a745';
        editSaveStatus.textContent = 'Đang lưu...';
        editSaveStatus.style.opacity = 1;

        const updatedData = {
            front: editFront.value,
            back: editBack.value,
            front_audio_content: editFrontAudio.value,
            back_audio_content: editBackAudio.value,
            front_img: editFrontImg.value,
            back_img: editBackImg.value
        };

        try {
            const response = await fetch(`/api/flashcard/edit/${currentFlashcardId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updatedData),
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                editSaveStatus.textContent = 'Đã lưu!';
                
                // Nếu đang ở trang học, cập nhật nội dung thẻ ngay lập tức
                if (mainCardText && document.getElementById('jsData')) {
                    const isFront = document.getElementById('jsData').dataset.isFront === 'true';
                    mainCardText.textContent = isFront ? result.data.front : result.data.back;
                }
                
                setTimeout(() => {
                    editSaveStatus.style.opacity = 0;
                    closeEditModal();
                    // Nếu không ở trang học (ví dụ: trang feedback), tải lại trang để thấy thay đổi
                    if (!mainCardText) {
                        window.location.reload();
                    }
                }, 1500);
            } else {
                throw new Error(result.message || 'Lỗi không xác định khi lưu.');
            }
        } catch (error) {
            console.error('Lỗi khi lưu thay đổi thẻ:', error);
            editSaveStatus.textContent = `Lỗi: ${error.message}`;
            editSaveStatus.style.color = '#dc3545';
            setTimeout(() => {
                editSaveStatus.style.opacity = 0;
            }, 4000);
        }
    }

    /**
     * Mô tả: Tái tạo audio cho một mặt của thẻ.
     */
    async function regenerateAudio(side, button) {
        if (!currentFlashcardId) return;
        const originalIcon = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        button.disabled = true;

        editSaveStatus.style.color = '#007bff';
        editSaveStatus.textContent = `Đang tái tạo audio mặt ${side}...`;
        editSaveStatus.style.opacity = 1;

        try {
            const response = await fetch(`/api/flashcard/regenerate_audio/${currentFlashcardId}/${side}`, {
                method: 'POST',
            });
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                editSaveStatus.style.color = '#28a745';
                editSaveStatus.textContent = 'Tái tạo thành công!';
            } else {
                throw new Error(result.message || 'Lỗi không xác định.');
            }
        } catch (error) {
            console.error(`Lỗi khi tái tạo audio mặt ${side}:`, error);
            editSaveStatus.textContent = `Lỗi: ${error.message}`;
            editSaveStatus.style.color = '#dc3545';
        } finally {
            button.innerHTML = originalIcon;
            button.disabled = false;
            setTimeout(() => {
                editSaveStatus.style.opacity = 0;
            }, 3000);
        }
    }

    // Gắn sự kiện cho tất cả các nút có class '.open-edit-btn'
    document.querySelectorAll('.open-edit-btn').forEach(button => {
        button.addEventListener('click', function() {
            currentFlashcardId = this.dataset.flashcardId;
            openEditModal();
        });
    });

    // Gắn sự kiện cho các nút trong modal
    if (closeEditBtn) closeEditBtn.addEventListener('click', closeEditModal);
    if (saveEditBtn) saveEditBtn.addEventListener('click', saveCardChanges);
    
    document.querySelectorAll('.regenerate-audio-btn').forEach(button => {
        button.addEventListener('click', function() {
            const side = this.dataset.side;
            regenerateAudio(side, this);
        });
    });

    // Đóng modal khi click ra ngoài
    window.addEventListener('click', function(event) {
        if (event.target === editModal) {
            closeEditModal();
        }
    });
});
