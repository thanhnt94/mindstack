// web_app/static/js/edit_handler.js

/**
 * Mô tả: Xử lý logic cho chức năng sửa flashcard, bao gồm mở/đóng modal,
 * lấy dữ liệu, lưu thay đổi và tái tạo audio qua API.
 */
document.addEventListener('DOMContentLoaded', function() {
    const jsData = document.getElementById('jsData');
    const canEdit = jsData.dataset.canEdit === 'true';

    if (!canEdit) {
        return;
    }

    const editModal = document.getElementById('edit-modal');
    const openEditBtn = document.getElementById('open-edit-btn');
    const closeEditBtn = document.getElementById('edit-modal-close-btn');
    const saveEditBtn = document.getElementById('save-edit-btn');
    const editSaveStatus = document.getElementById('edit-save-status');
    const flashcardId = jsData.dataset.flashcardId;

    const editFront = document.getElementById('edit-front');
    const editBack = document.getElementById('edit-back');
    const editFrontAudio = document.getElementById('edit-front-audio');
    const editBackAudio = document.getElementById('edit-back-audio');
    const editFrontImg = document.getElementById('edit-front-img');
    const editBackImg = document.getElementById('edit-back-img');

    const mainCardText = document.querySelector('.flashcard-body .card-text');

    async function openEditModal() {
        if (!editModal) return;

        editFront.value = "Đang tải...";
        editBack.value = "Đang tải...";
        editModal.style.display = 'flex';

        try {
            const response = await fetch(`/api/flashcard/details/${flashcardId}`);
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

    function closeEditModal() {
        if (editModal) {
            editModal.style.display = 'none';
        }
    }

    async function saveCardChanges() {
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
            const response = await fetch(`/api/flashcard/edit/${flashcardId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updatedData),
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                editSaveStatus.textContent = 'Đã lưu!';
                const isFront = jsData.dataset.isFront === 'true';
                if (isFront) {
                    mainCardText.textContent = result.data.front;
                } else {
                    mainCardText.textContent = result.data.back;
                }
                
                setTimeout(() => {
                    editSaveStatus.style.opacity = 0;
                    closeEditModal();
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

    // --- BẮT ĐẦU THÊM MỚI: Logic tái tạo audio ---
    async function regenerateAudio(side, button) {
        const originalIcon = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        button.disabled = true;

        editSaveStatus.style.color = '#007bff';
        editSaveStatus.textContent = `Đang tái tạo audio mặt ${side}...`;
        editSaveStatus.style.opacity = 1;

        try {
            const response = await fetch(`/api/flashcard/regenerate_audio/${flashcardId}/${side}`, {
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

    document.querySelectorAll('.regenerate-audio-btn').forEach(button => {
        button.addEventListener('click', function() {
            const side = this.dataset.side;
            regenerateAudio(side, this);
        });
    });
    // --- KẾT THÚC THÊM MỚI ---

    if (openEditBtn) {
        openEditBtn.addEventListener('click', openEditModal);
    }
    if (closeEditBtn) {
        closeEditBtn.addEventListener('click', closeEditModal);
    }
    if (saveEditBtn) {
        saveEditBtn.addEventListener('click', saveCardChanges);
    }

    window.addEventListener('click', function(event) {
        if (event.target === editModal) {
            closeEditModal();
        }
    });
});
