// web_app/static/js/quiz_edit_handler.js

document.addEventListener('DOMContentLoaded', function() {
    const openEditBtn = document.getElementById('open-quiz-edit-btn');
    if (!openEditBtn) return;

    const editModal = document.getElementById('quiz-edit-modal');
    const closeEditBtn = document.getElementById('quiz-edit-modal-close-btn');
    const saveEditBtn = document.getElementById('save-quiz-edit-btn');
    const editSaveStatus = document.getElementById('quiz-edit-save-status');
    const quizForm = document.getElementById('quiz-form');
    const questionId = quizForm.dataset.questionId;

    // Các trường input trong modal
    const fields = {
        pre_question_text: document.getElementById('edit-pre-question-text'),
        question: document.getElementById('edit-question'),
        option_a: document.getElementById('edit-option-a'),
        option_b: document.getElementById('edit-option-b'),
        option_c: document.getElementById('edit-option-c'),
        option_d: document.getElementById('edit-option-d'),
        correct_answer: document.getElementById('edit-correct-answer'),
        guidance: document.getElementById('edit-guidance'),
    };

    async function openEditModal() {
        Object.values(fields).forEach(field => {
            if (field.tagName === 'TEXTAREA' || field.tagName === 'INPUT') field.value = 'Đang tải...';
        });
        editModal.style.display = 'flex';

        try {
            const response = await fetch(`/api/quiz_question/details/${questionId}`);
            if (!response.ok) throw new Error('Lỗi server');
            const result = await response.json();

            if (result.status === 'success') {
                const data = result.data;
                for (const key in fields) {
                    fields[key].value = data[key] || '';
                }
            } else {
                throw new Error(result.message);
            }
        } catch (error) {
            console.error('Lỗi khi tải chi tiết câu hỏi:', error);
            fields.question.value = 'Không thể tải dữ liệu. Vui lòng thử lại.';
        }
    }

    function closeEditModal() {
        editModal.style.display = 'none';
    }

    async function saveChanges() {
        editSaveStatus.style.color = '#28a745';
        editSaveStatus.textContent = 'Đang lưu...';
        editSaveStatus.style.opacity = 1;

        const updatedData = {};
        for (const key in fields) {
            updatedData[key] = fields[key].value;
        }

        try {
            const response = await fetch(`/api/quiz_question/edit/${questionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updatedData),
            });
            if (!response.ok) throw new Error('Lỗi server');
            
            const result = await response.json();
            if (result.status === 'success') {
                editSaveStatus.textContent = 'Đã lưu!';
                setTimeout(() => {
                    editSaveStatus.style.opacity = 0;
                    closeEditModal();
                    window.location.reload(); // Tải lại trang để thấy thay đổi
                }, 1500);
            } else {
                throw new Error(result.message);
            }
        } catch (error) {
            console.error('Lỗi khi lưu thay đổi:', error);
            editSaveStatus.textContent = `Lỗi: ${error.message}`;
            editSaveStatus.style.color = '#dc3545';
            setTimeout(() => { editSaveStatus.style.opacity = 0; }, 4000);
        }
    }

    openEditBtn.addEventListener('click', openEditModal);
    closeEditBtn.addEventListener('click', closeEditModal);
    saveEditBtn.addEventListener('click', saveChanges);
    window.addEventListener('click', (event) => {
        if (event.target === editModal) closeEditModal();
    });
});
