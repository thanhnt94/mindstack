// web_app/static/js/quiz_handler.js

document.addEventListener('DOMContentLoaded', function() {
    const quizForm = document.getElementById('quiz-form');
    if (!quizForm) {
        console.log("quiz_handler.js: Quiz form not found, exiting.");
        return; // Thoát nếu không phải trang làm quiz
    }

    const submitAllAnswersBtn = document.getElementById('submit-all-answers-btn');
    const nextQuestionBtn = document.getElementById('next-question-btn');
    const quizJsDataElement = document.getElementById('quizJsData');

    // Lấy dữ liệu về tất cả các câu hỏi từ data attribute
    // questionsData là một chuỗi JSON, cần parse về object
    const allQuestionsData = JSON.parse(quizJsDataElement.dataset.questionsData || '[]');
    console.log("quiz_handler.js: Loaded allQuestionsData:", allQuestionsData);

    // BẮT ĐẦU THÊM MỚI: Áp dụng chiều rộng cho thanh tiến trình desktop
    const progressBarFillDesktop = document.querySelector('.quiz-header-bar .progress-bar-fill');
    if (progressBarFillDesktop) {
        const percentage = progressBarFillDesktop.dataset.percentage;
        if (percentage !== undefined) {
            progressBarFillDesktop.style.width = `${percentage}%`;
            console.log(`quiz_handler.js: Desktop progress bar set to ${percentage}%`);
        }
    }
    // KẾT THÚC THÊM MỚI

    // Lắng nghe sự kiện thay đổi lựa chọn cho mỗi nhóm câu hỏi
    document.querySelectorAll('.options-grid').forEach(optionsGrid => {
        optionsGrid.addEventListener('change', function(event) {
            if (event.target.type === 'radio') {
                console.log("quiz_handler.js: Radio button changed. Target:", event.target);
                // Lấy tên của nhóm radio button (ví dụ: 'option-123')
                const radioGroupName = event.target.name;
                // Xóa class 'selected' khỏi tất cả các card trong nhóm này
                optionsGrid.querySelectorAll(`input[name="${radioGroupName}"]`).forEach(radio => {
                    const parentCard = radio.closest('.option-card');
                    if (parentCard) {
                        parentCard.classList.remove('selected');
                    }
                });
                // Thêm class 'selected' vào card được chọn
                const selectedCard = event.target.closest('.option-card');
                if (selectedCard) {
                    selectedCard.classList.add('selected');
                    console.log("quiz_handler.js: Added 'selected' class to:", selectedCard);
                }
            }
        });
    });

    /**
     * Mô tả: Xử lý sự kiện khi người dùng nộp tất cả các câu trả lời trong form.
     * Thu thập các câu trả lời, gửi đến API và hiển thị kết quả cho từng câu hỏi.
     * @param {Event} event - Đối tượng sự kiện.
     */
    quizForm.addEventListener('submit', async function(event) {
        event.preventDefault(); 
        console.log("quiz_handler.js: Form submitted.");

        const answersToSend = [];
        let allRequiredAnswered = true;

        // Lặp qua từng khối câu hỏi để thu thập câu trả lời
        document.querySelectorAll('.question-block').forEach(questionBlock => {
            const questionId = questionBlock.dataset.questionId;
            const selectedRadio = questionBlock.querySelector(`input[name="option-${questionId}"]:checked`);
            
            // Kiểm tra nếu câu hỏi là bắt buộc (có attribute 'required' trên radio)
            const isRequired = questionBlock.querySelector(`input[name="option-${questionId}"][required]`);

            if (isRequired && !selectedRadio) {
                allRequiredAnswered = false;
                // Thêm hiệu ứng highlight câu hỏi chưa trả lời
                questionBlock.style.border = '2px solid red'; // Ví dụ: highlight viền đỏ
                console.log(`quiz_handler.js: Question ${questionId} is required but not answered.`);
            } else {
                questionBlock.style.border = ''; // Xóa viền đỏ nếu đã trả lời
            }

            if (selectedRadio) {
                answersToSend.push({
                    question_id: parseInt(questionId),
                    selected_option: selectedRadio.value
                });
                console.log(`quiz_handler.js: Collected answer for Q${questionId}: ${selectedRadio.value}`);
            }
        });

        if (!allRequiredAnswered) {
            // Cuộn đến câu hỏi đầu tiên chưa được trả lời
            const firstUnansweredQuestion = document.querySelector('.question-block[style*="border: 2px solid red"]');
            if (firstUnansweredQuestion) {
                firstUnansweredQuestion.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            alert('Vui lòng trả lời tất cả các câu hỏi bắt buộc.');
            console.log("quiz_handler.js: Not all required questions answered.");
            return;
        }

        if (answersToSend.length === 0) {
            alert('Vui lòng chọn ít nhất một đáp án trước khi nộp bài.');
            console.log("quiz_handler.js: No answers selected.");
            return;
        }

        const submitUrl = quizForm.dataset.submitUrl;
        console.log("quiz_handler.js: Submitting answers to:", submitUrl, "Data:", answersToSend);
        
        // Vô hiệu hóa nút nộp bài để tránh gửi nhiều lần
        submitAllAnswersBtn.disabled = true;
        submitAllAnswersBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang nộp...';

        try {
            const response = await fetch(submitUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(answersToSend),
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error("quiz_handler.js: Server error response:", response.status, errorText);
                throw new Error(`Lỗi từ server khi kiểm tra đáp án: ${response.status} - ${errorText}`);
            }

            const result = await response.json();
            console.log("quiz_handler.js: API response received:", result);

            if (result.status === 'success') {
                // Hiển thị kết quả cho từng câu hỏi
                result.results.forEach(qResult => {
                    const questionBlock = document.querySelector(`.question-block[data-question-id="${qResult.question_id}"]`);
                    if (questionBlock) {
                        showResultForQuestion(questionBlock, qResult.is_correct, qResult.correct_answer, answersToSend.find(a => a.question_id === qResult.question_id)?.selected_option, qResult.guidance);
                        console.log(`quiz_handler.js: Displayed result for Q${qResult.question_id}`);
                    }
                });

                // Cập nhật thanh trạng thái tổng thể
                // Gửi sự kiện tùy chỉnh để cập nhật thanh trạng thái
                const quizSetId = quizJsDataElement.dataset.quizSetId; 
                
                // Lấy thống kê bộ đề và thống kê câu hỏi hiện tại
                const statsResponse = await fetch(`/api/quiz_set_stats/${quizSetId}`);
                if (statsResponse.ok) {
                    const statsResult = await statsResponse.json();
                    if (statsResult.status === 'success') {
                        const quizAnsweredEvent = new CustomEvent('quizAnswered', {
                            detail: {
                                quizSetStats: statsResult.data, // Dữ liệu thống kê bộ đề
                                // questionProgress sẽ không còn cần ở đây vì nó là của từng câu hỏi
                            }
                        });
                        window.dispatchEvent(quizAnsweredEvent);
                        console.log("quiz_handler.js: Dispatched 'quizAnswered' event.");
                    }
                } else {
                    console.error("quiz_handler.js: Lỗi khi tải thống kê bộ đề.");
                }

                // Ẩn nút "Nộp bài" và hiện nút "Tiếp theo"
                submitAllAnswersBtn.style.display = 'none';
                nextQuestionBtn.style.display = 'inline-flex';
                nextQuestionBtn.focus(); // Tự động focus vào nút tiếp theo
                console.log("quiz_handler.js: Submit button hidden, Next button shown.");
            } else {
                alert(result.message || 'Có lỗi xảy ra.');
                submitAllAnswersBtn.disabled = false;
                submitAllAnswersBtn.innerHTML = 'Nộp bài';
                console.error("quiz_handler.js: API returned error status:", result.message);
            }

        } catch (error) {
            console.error('quiz_handler.js: Lỗi khi gửi câu trả lời:', error);
            alert('Không thể kết nối đến máy chủ. Vui lòng thử lại.');
            submitAllAnswersBtn.disabled = false;
            submitAllAnswersBtn.innerHTML = 'Nộp bài';
        }
    });

    /**
     * Mô tả: Hiển thị kết quả cho một câu hỏi cụ thể sau khi kiểm tra.
     * @param {HTMLElement} questionBlock - Phần tử DOM của khối câu hỏi.
     * @param {boolean} isCorrect - Câu trả lời có đúng không.
     * @param {string} correctAnswer - Đáp án đúng ('A', 'B', 'C', 'D').
     * @param {string} selectedOption - Đáp án người dùng đã chọn.
     * @param {string} guidance - Nội dung giải thích.
     */
    function showResultForQuestion(questionBlock, isCorrect, correctAnswer, selectedOption, guidance) {
        const optionsGrid = questionBlock.querySelector('.options-grid');
        const resultSection = questionBlock.querySelector('.result-section');
        const guidancePanel = questionBlock.querySelector('.guidance-panel');
        const guidanceText = questionBlock.querySelector('.guidance-text'); // Sử dụng class

        console.log(`quiz_handler.js: Showing result for Q${questionBlock.dataset.questionId}. Correct: ${isCorrect}, Selected: ${selectedOption}, Correct Answer: ${correctAnswer}`);

        // Vô hiệu hóa tất cả các lựa chọn
        optionsGrid.querySelectorAll('input[type="radio"]').forEach(radio => {
            radio.disabled = true;
            radio.closest('.option-card').classList.remove('selected'); // Bỏ hiệu ứng selected
        });

        // Tìm và tô màu các lựa chọn
        optionsGrid.querySelectorAll('.option-card').forEach(card => {
            const optionValue = card.dataset.option;
            const optionContent = card.querySelector('.option-content p'); // Lấy phần tử chứa nội dung đáp án

            // Xóa bất kỳ biểu tượng kết quả cũ nào
            const existingIcon = card.querySelector('.result-icon');
            if (existingIcon) {
                existingIcon.remove();
            }

            if (optionValue === correctAnswer) {
                card.classList.add('correct');
                // Thêm biểu tượng đúng vào đáp án đúng
                const icon = document.createElement('i');
                icon.classList.add('fas', 'fa-check-circle', 'result-icon');
                icon.style.color = '#28a745'; // Màu xanh lá
                card.querySelector('.option-content').prepend(icon); // Thêm vào đầu nội dung
                console.log(`quiz_handler.js: Q${questionBlock.dataset.questionId} - Option ${optionValue} is correct.`);
            } 
            
            if (optionValue === selectedOption) {
                if (!isCorrect) { // Nếu lựa chọn của người dùng sai
                    card.classList.add('incorrect');
                    // Thêm biểu tượng sai vào lựa chọn của người dùng
                    const icon = document.createElement('i');
                    icon.classList.add('fas', 'fa-times-circle', 'result-icon');
                    icon.style.color = '#dc3545'; // Màu đỏ
                    card.querySelector('.option-content').prepend(icon); // Thêm vào đầu nội dung
                    console.log(`quiz_handler.js: Q${questionBlock.dataset.questionId} - Option ${optionValue} is incorrect (selected).`);
                }
                // Nếu lựa chọn của người dùng đúng, nó đã được xử lý ở khối 'correct'
            }
        });

        // Hiển thị khu vực kết quả
        resultSection.style.display = 'block';
        if (guidance) {
            guidanceText.innerText = guidance;
            guidancePanel.style.display = 'block';
            console.log(`quiz_handler.js: Q${questionBlock.dataset.questionId} - Guidance shown.`);
        } else {
            guidancePanel.style.display = 'none';
            console.log(`quiz_handler.js: Q${questionBlock.dataset.questionId} - No guidance.`);
        }
    }
});
