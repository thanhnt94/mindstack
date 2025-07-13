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

    // BẮT ĐẦU THAY ĐỔI: Lấy các phần tử liên quan đến đoạn văn và thứ tự
    const quizJsDataElement = document.getElementById('quizJsData');
    const currentPassageId = quizJsDataElement.dataset.passageId; // Lấy passage_id hiện tại
    
    const editPassageContent = document.getElementById('edit-passage-content');
    const editPassageOrder = document.getElementById('edit-passage-order');
    const passageEditInfo = document.getElementById('passage-edit-info');
    // KẾT THÚC THAY ĐỔI

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
        // BẮT ĐẦU THAY ĐỔI: Thêm trường passage_order vào fields
        passage_order: editPassageOrder
        // KẾT THÚC THAY ĐỔI
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
        // BẮT ĐẦU THAY ĐỔI: Đặt trạng thái tải cho passage_content
        if (editPassageContent) editPassageContent.value = 'Đang tải...';
        // KẾT THÚC THAY ĐỔI
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
                        // BẮT ĐẦU SỬA: Gán giá trị rỗng nếu là null để input hiển thị trống
                        fields[key].value = data[key] === null ? '' : data[key];
                        // KẾT THÚC SỬA
                    }
                }

                // BẮT ĐẦU THAY ĐỔI: Xử lý hiển thị và chỉnh sửa passage_content
                if (data.passage_id) { // Nếu câu hỏi thuộc một đoạn văn
                    // Lấy nội dung đoạn văn từ API riêng
                    const passageResponse = await fetch(`/api/quiz_passage/${data.passage_id}`);
                    if (passageResponse.ok) {
                        const passageData = await passageResponse.json();
                        editPassageContent.value = passageData.passage_content || '';
                    } else {
                        editPassageContent.value = 'Không thể tải đoạn văn.';
                    }
                    editPassageContent.disabled = false; // Cho phép chỉnh sửa đoạn văn
                    passageEditInfo.style.display = 'block'; // Hiển thị thông báo
                } else { // Câu hỏi độc lập, không có đoạn văn
                    editPassageContent.value = ''; // Đảm bảo trống
                    editPassageContent.disabled = false; // Có thể nhập đoạn văn mới nếu muốn biến nó thành câu hỏi chính
                    passageEditInfo.style.display = 'none';
                }
                // KẾT THÚC THAY ĐỔI

            } else {
                throw new Error(result.message);
            }
        } catch (error) {
            console.error('Lỗi khi tải chi tiết câu hỏi:', error);
            fields.question.value = 'Không thể tải dữ liệu. Vui lòng thử lại.';
            // BẮT ĐẦU THAY ĐỔI: Vô hiệu hóa trường đoạn văn nếu tải lỗi
            if (editPassageContent) {
                editPassageContent.value = 'Lỗi tải dữ liệu.';
                editPassageContent.disabled = true;
            }
            if (passageEditInfo) passageEditInfo.style.display = 'block';
            if (passageEditInfo) passageEditInfo.textContent = 'Không thể tải đoạn văn.';
            // KẾT THÚC THAY ĐỔI
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
            // BẮT ĐẦU SỬA: Gửi chuỗi rỗng nếu giá trị là rỗng, để backend có thể chuyển thành None
            updatedData[key] = fields[key].value.trim();
            // KẾT THÚC SỬA
        }

        // BẮT ĐẦU THAY ĐỔI: Thêm passage_content vào dữ liệu gửi đi nếu nó được phép chỉnh sửa
        if (editPassageContent && !editPassageContent.disabled) {
            updatedData['passage_content'] = editPassageContent.value.trim(); // SỬA: trim()
        } else {
            // Nếu không được chỉnh sửa hoặc không có đoạn văn, đảm bảo không gửi passage_content
            delete updatedData['passage_content'];
        }
        // KẾT THÚC THAY ĐỔI

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

