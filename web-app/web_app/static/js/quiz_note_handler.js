// web_app/static/js/quiz_note_handler.js

document.addEventListener('DOMContentLoaded', function() {
    const openNoteBtn = document.getElementById('open-quiz-note-btn');
    if (!openNoteBtn) return;

    const noteModal = document.getElementById('quiz-note-modal');
    const closeNoteBtn = document.getElementById('quiz-note-modal-close-btn');
    const saveNoteBtn = document.getElementById('save-quiz-note-btn');
    const noteTextarea = document.getElementById('quiz-note-textarea');
    const noteSaveStatus = document.getElementById('quiz-note-save-status');
    const quizForm = document.getElementById('quiz-form');
    const questionId = quizForm.dataset.questionId;

    async function openNoteModal() {
        noteTextarea.value = "Đang tải ghi chú...";
        noteModal.style.display = 'flex';

        try {
            const response = await fetch(`/api/quiz_note/${questionId}`);
            if (!response.ok) throw new Error('Lỗi server');
            const data = await response.json();
            noteTextarea.value = data.note || '';
        } catch (error) {
            console.error('Lỗi khi tải ghi chú:', error);
            noteTextarea.value = 'Không thể tải ghi chú.';
        }
    }

    function closeNoteModal() {
        noteModal.style.display = 'none';
    }

    async function saveNote() {
        noteSaveStatus.style.color = '#28a745';
        noteSaveStatus.textContent = 'Đang lưu...';
        noteSaveStatus.style.opacity = 1;

        try {
            const response = await fetch(`/api/quiz_note/${questionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: noteTextarea.value }),
            });
            if (!response.ok) throw new Error('Lỗi server');
            
            const result = await response.json();
            if (result.status === 'updated' || result.status === 'created') {
                noteSaveStatus.textContent = 'Đã lưu!';
                openNoteBtn.classList.add('has-note'); // Đánh dấu nút là đã có note
                setTimeout(() => { noteSaveStatus.style.opacity = 0; }, 2000);
            } else {
                throw new Error(result.message || 'Lỗi không xác định.');
            }
        } catch (error) {
            console.error('Lỗi khi lưu ghi chú:', error);
            noteSaveStatus.textContent = `Lỗi: ${error.message}`;
            noteSaveStatus.style.color = '#dc3545';
            setTimeout(() => { noteSaveStatus.style.opacity = 0; }, 4000);
        }
    }

    openNoteBtn.addEventListener('click', openNoteModal);
    closeNoteBtn.addEventListener('click', closeNoteModal);
    saveNoteBtn.addEventListener('click', saveNote);
    window.addEventListener('click', (event) => {
        if (event.target === noteModal) closeNoteModal();
    });
});
