/**
 * Mô tả: Xử lý logic cho modal gửi feedback.
 */
document.addEventListener('DOMContentLoaded', function() {
    const feedbackModal = document.getElementById('feedback-modal');
    if (!feedbackModal) return;

    const closeBtn = document.getElementById('feedback-modal-close-btn');
    const saveBtn = document.getElementById('save-feedback-btn');
    const textarea = document.getElementById('feedback-textarea');
    const statusEl = document.getElementById('feedback-save-status');
    
    let currentFlashcardId = null;
    let currentQuestionId = null;

    function openFeedbackModal() {
        textarea.value = '';
        statusEl.textContent = '';
        statusEl.style.opacity = 0;
        feedbackModal.style.display = 'flex';
        textarea.focus();
    }

    function closeFeedbackModal() {
        feedbackModal.style.display = 'none';
        currentFlashcardId = null;
        currentQuestionId = null;
    }

    async function sendFeedback() {
        const content = textarea.value.trim();
        if (!content) {
            alert('Vui lòng nhập nội dung feedback.');
            return;
        }

        statusEl.style.color = '#007bff';
        statusEl.textContent = 'Đang gửi...';
        statusEl.style.opacity = 1;
        saveBtn.disabled = true;

        const payload = {
            content: content,
            flashcard_id: currentFlashcardId,
            question_id: currentQuestionId
        };

        try {
            const response = await fetch('/api/feedback/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                statusEl.style.color = '#28a745';
                statusEl.textContent = 'Đã gửi thành công!';
                setTimeout(() => {
                    closeFeedbackModal();
                }, 1500);
            } else {
                throw new Error(result.message || 'Lỗi không xác định.');
            }

        } catch (error) {
            statusEl.style.color = '#dc3545';
            statusEl.textContent = `Lỗi: ${error.message}`;
            setTimeout(() => {
                statusEl.style.opacity = 0;
            }, 4000);
        } finally {
            saveBtn.disabled = false;
        }
    }

    // Gắn sự kiện cho tất cả các nút feedback
    document.querySelectorAll('.open-feedback-btn').forEach(button => {
        button.addEventListener('click', function() {
            currentFlashcardId = this.dataset.flashcardId || null;
            currentQuestionId = this.dataset.questionId || null;
            openFeedbackModal();
        });
    });

    if(closeBtn) closeBtn.addEventListener('click', closeFeedbackModal);
    if(saveBtn) saveBtn.addEventListener('click', sendFeedback);
    window.addEventListener('click', (event) => {
        if (event.target === feedbackModal) {
            closeFeedbackModal();
        }
    });
});
