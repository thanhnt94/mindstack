// web_app/static/js/edit_handler.js

document.addEventListener('DOMContentLoaded', function() {
    const editModal = document.getElementById('edit-modal');
    if (!editModal) return;
    const closeEditBtn = document.getElementById('edit-modal-close-btn');
    const saveEditBtn = document.getElementById('save-edit-btn');
    const editSaveStatus = document.getElementById('edit-save-status');
    const editFront = document.getElementById('edit-front');
    const editBack = document.getElementById('edit-back');
    const editFrontAudio = document.getElementById('edit-front-audio');
    const editBackAudio = document.getElementById('edit-back-audio');
    const editFrontImg = document.getElementById('edit-front-img');
    const editBackImg = document.getElementById('edit-back-img');
    const editAiPrompt = document.getElementById('edit-ai-prompt');

    const confirmDeleteModal = document.getElementById('confirm-delete-modal');
    const confirmDeleteBtn = document.getElementById('confirm-delete-btn');
    const cancelDeleteBtn = document.getElementById('cancel-delete-btn');

    let cardIdToProcess = null;

    async function openEditModal() {
        if (!cardIdToProcess) return;
        editFront.value = "Đang tải...";
        editBack.value = "Đang tải...";
        editFrontAudio.value = "";
        editBackAudio.value = "";
        editFrontImg.value = "";
        editBackImg.value = "";
        editAiPrompt.value = "";
        editModal.style.display = 'flex';

        try {
            const response = await fetch(`/api/flashcard/details/${cardIdToProcess}`);
            const result = await response.json();
            if (!response.ok || result.status !== 'success') throw new Error(result.message || 'Lỗi server');
            
            const cardData = result.data;
            editFront.value = cardData.front || '';
            editBack.value = cardData.back || '';
            editFrontAudio.value = cardData.front_audio_content || '';
            editBackAudio.value = cardData.back_audio_content || '';
            editFrontImg.value = cardData.front_img || '';
            editBackImg.value = cardData.back_img || '';
            editAiPrompt.value = cardData.ai_prompt || '';
        } catch (error) {
            console.error('Lỗi khi tải chi tiết thẻ:', error);
            editFront.value = 'Không thể tải dữ liệu.';
        }
    }

    function closeEditModal() {
        editModal.style.display = 'none';
    }

    async function saveCardChanges() {
        if (!cardIdToProcess) return;
        editSaveStatus.textContent = 'Đang lưu...';
        editSaveStatus.style.opacity = 1;

        const updatedData = {
            front: editFront.value, back: editBack.value,
            front_audio_content: editFrontAudio.value, back_audio_content: editBackAudio.value,
            front_img: editFrontImg.value, back_img: editBackImg.value,
            ai_prompt: editAiPrompt.value 
        };

        try {
            const response = await fetch(`/api/flashcard/edit/${cardIdToProcess}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updatedData),
            });
            const result = await response.json();
            if (!response.ok || result.status !== 'success') throw new Error(result.message || 'Lỗi khi lưu');
            
            editSaveStatus.textContent = 'Đã lưu!';
            setTimeout(() => window.location.reload(), 1000);
        } catch (error) {
            console.error('Lỗi khi lưu thay đổi thẻ:', error);
            editSaveStatus.textContent = `Lỗi: ${error.message}`;
        }
    }

    function openDeleteModal() {
        if (!cardIdToProcess || !confirmDeleteModal) return;
        confirmDeleteModal.style.display = 'flex';
    }

    function closeDeleteModal() {
        if (!confirmDeleteModal) return;
        confirmDeleteModal.style.display = 'none';
    }

    async function deleteCard() {
        if (!cardIdToProcess) return;
        confirmDeleteBtn.textContent = 'Đang xóa...';
        confirmDeleteBtn.disabled = true;

        try {
            const response = await fetch(`/api/flashcard/delete/${cardIdToProcess}`, { method: 'DELETE' });
            const result = await response.json();
            if (!response.ok || result.status !== 'success') throw new Error(result.message || 'Lỗi server');
            
            window.location.reload();
        } catch (error) {
            console.error('Lỗi khi xóa thẻ:', error);
            alert(`Không thể xóa thẻ: ${error.message}`);
            confirmDeleteBtn.textContent = 'Xác nhận Xóa';
            confirmDeleteBtn.disabled = false;
            closeDeleteModal();
        }
    }

    document.addEventListener('click', function(event) {
        const target = event.target;

        const editButton = target.closest('.open-edit-btn');
        if (editButton) {
            event.preventDefault();
            cardIdToProcess = editButton.dataset.flashcardId;
            openEditModal();
            return;
        }

        const deleteButton = target.closest('.delete-card-btn');
        if (deleteButton) {
            event.preventDefault();
            cardIdToProcess = deleteButton.dataset.flashcardId;
            openDeleteModal();
            return;
        }
    });

    if (closeEditBtn) closeEditBtn.addEventListener('click', closeEditModal);
    if (saveEditBtn) saveEditBtn.addEventListener('click', saveCardChanges);
    if (cancelDeleteBtn) cancelDeleteBtn.addEventListener('click', closeDeleteModal);
    if (confirmDeleteBtn) confirmDeleteBtn.addEventListener('click', deleteCard);

    window.addEventListener('click', function(event) {
        if (event.target === editModal) closeEditModal();
        if (event.target === confirmDeleteModal) closeDeleteModal();
    });
});
