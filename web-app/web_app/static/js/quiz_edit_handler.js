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

    // BẮT ĐẦU THÊM MỚI: Lấy các phần tử và dữ liệu liên quan đến đoạn văn
    const quizJsDataElement = document.getElementById('quizJsData');
    const isPassageMainQuestion = quizJsDataElement.dataset.isPassageMainQuestion === 'true';
    const passageGroupId = quizJsDataElement.dataset.passageGroupId;

    const editPassageContent = document.getElementById('edit-passage-content');
    const passageEditInfo = document.getElementById('passage-edit-info');
    // KẾT THÚC THÊM MỚI

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
        // BẮT ĐẦU THÊM MỚI: Thêm trường passage_content vào fields
        passage_content: editPassageContent
        // KẾT THÚC THÊM MỚI
    };

    /**
     * Mô tả: Mở modal chỉnh sửa câu hỏi và tải dữ liệu chi tiết.
     */
    async function openEditModal() {
        // Đặt trạng thái tải cho tất cả các trường
        Object.values(fields).forEach(field => {
            if (field.tagName === 'TEXTAREA' || field.tagName === 'INPUT' || field.tagName === 'SELECT') {
                field.value = 'Đang tải...';
            }
        });
        editModal.style.display = 'flex';

        try {
            // Gọi API để lấy chi tiết câu hỏi (bao gồm cả các trường đoạn văn)
            const response = await fetch(`/api/quiz_question/details/${questionId}`);
            if (!response.ok) throw new Error('Lỗi server');
            const result = await response.json();

            if (result.status === 'success') {
                const data = result.data;
                for (const key in fields) {
                    // Đảm bảo gán giá trị chỉ khi key tồn tại trong data
                    if (data.hasOwnProperty(key)) {
                        fields[key].value = data[key] || '';
                    }
                }

                // BẮT ĐẦU THÊM MỚI: Logic hiển thị/vô hiệu hóa trường đoạn văn
                if (data.passage_group_id) { // Nếu câu hỏi thuộc một nhóm đoạn văn
                    if (data.is_passage_main_question) {
                        editPassageContent.disabled = false; // Cho phép chỉnh sửa
                        passageEditInfo.style.display = 'none'; // Ẩn thông báo
                    } else {
                        editPassageContent.disabled = true; // Vô hiệu hóa chỉnh sửa
                        passageEditInfo.style.display = 'block'; // Hiển thị thông báo
                        // Nếu là câu hỏi con, passage_content của nó sẽ rỗng.
                        // Nội dung đoạn văn đã được hiển thị ở phần chính của trang bởi Jinja.
                        // Ở đây ta chỉ hiển thị nội dung của chính câu hỏi này (nếu có)
                        // hoặc để trống nếu nó là câu hỏi con không chứa đoạn văn.
                        editPassageContent.value = data.passage_content || '';
                    }
                } else { // Câu hỏi độc lập, không có đoạn văn
                    editPassageContent.disabled = false; // Có thể nhập đoạn văn mới nếu muốn biến nó thành câu hỏi chính
                    editPassageContent.value = ''; // Đảm bảo trống
                    passageEditInfo.style.display = 'none';
                }
                // KẾT THÚC THÊM MỚI

            } else {
                throw new Error(result.message);
            }
        } catch (error) {
            console.error('Lỗi khi tải chi tiết câu hỏi:', error);
            fields.question.value = 'Không thể tải dữ liệu. Vui lòng thử lại.';
            // BẮT ĐẦU THÊM MỚI: Vô hiệu hóa trường đoạn văn nếu tải lỗi
            if (editPassageContent) editPassageContent.disabled = true;
            if (passageEditInfo) passageEditInfo.style.display = 'block';
            if (passageEditInfo) passageEditInfo.textContent = 'Không thể tải đoạn văn.';
            // KẾT THÚC THÊM MỚI
        }
    }

    /**
     * Mô tả: Đóng modal chỉnh sửa câu hỏi.
     */
    function closeEditModal() {
        editModal.style.display = 'none';
    }

    /**
     * Mô tả: Lưu các thay đổi của câu hỏi thông qua API.
     */
    async function saveChanges() {
        editSaveStatus.style.color = '#28a745';
        editSaveStatus.textContent = 'Đang lưu...';
        editSaveStatus.style.opacity = 1;

        const updatedData = {};
        for (const key in fields) {
            // BẮT ĐẦU THÊM MỚI: Chỉ gửi passage_content nếu nó có thể chỉnh sửa
            if (key === 'passage_content' && editPassageContent.disabled) {
                continue; // Bỏ qua nếu trường bị vô hiệu hóa
            }
            // KẾT THÚC THÊM MỚI
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
