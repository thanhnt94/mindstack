// web_app/static/js/quiz_handler.js

document.addEventListener('DOMContentLoaded', function() {
    const quizForm = document.getElementById('quiz-form');
    if (!quizForm) {
        return; // Thoát nếu không phải trang làm quiz
    }

    const checkAnswerBtn = document.getElementById('check-answer-btn');
    const nextQuestionBtn = document.getElementById('next-question-btn');
    const optionsGrid = document.getElementById('options-grid');
    const resultSection = document.getElementById('result-section');
    const guidancePanel = document.getElementById('guidance-panel');
    const guidanceText = document.getElementById('guidance-text');
    const progressBarFill = document.querySelector('.progress-bar-fill'); // Lấy thanh tiến trình

    // BẮT ĐẦU THÊM MỚI: Áp dụng chiều rộng cho thanh tiến trình từ data attribute
    if (progressBarFill) {
        const percentage = progressBarFill.dataset.percentage;
        if (percentage !== undefined) {
            progressBarFill.style.width = `${percentage}%`;
        }
    }
    // KẾT THÚC THÊM MỚI

    // --- BẮT ĐẦU SỬA: Thêm logic cho hiệu ứng chọn đáp án ---
    optionsGrid.addEventListener('change', function(event) {
        if (event.target.type === 'radio') {
            // Xóa class 'selected' khỏi tất cả các card
            optionsGrid.querySelectorAll('.option-card').forEach(card => {
                card.classList.remove('selected');
            });
            // Thêm class 'selected' vào card được chọn
            const selectedCard = event.target.closest('.option-card');
            if (selectedCard) {
                selectedCard.classList.add('selected');
            }
        }
    });
    // --- KẾT THÚC SỬA ---

    /**
     * Mô tả: Xử lý sự kiện khi người dùng nộp form (nhấn nút "Kiểm tra").
     * @param {Event} event - Đối tượng sự kiện.
     */
    quizForm.addEventListener('submit', async function(event) {
        event.preventDefault(); 

        const selectedRadio = quizForm.querySelector('input[name="option"]:checked');
        if (!selectedRadio) {
            alert('Vui lòng chọn một đáp án.');
            return;
        }

        const selectedOption = selectedRadio.value;
        const checkUrl = quizForm.dataset.checkUrl;

        try {
            const response = await fetch(checkUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ option: selectedOption }),
            });

            if (!response.ok) {
                throw new Error('Lỗi từ server khi kiểm tra đáp án.');
            }

            const result = await response.json();

            if (result.status === 'success') {
                showResult(result.is_correct, result.correct_answer, selectedOption, result.guidance);
            } else {
                alert(result.message || 'Có lỗi xảy ra.');
            }

        } catch (error) {
            console.error('Lỗi khi gửi câu trả lời:', error);
            alert('Không thể kết nối đến máy chủ. Vui lòng thử lại.');
        }
    });

    /**
     * Mô tả: Hiển thị kết quả cho người dùng sau khi kiểm tra.
     * @param {boolean} isCorrect - Câu trả lời có đúng không.
     * @param {string} correctAnswer - Đáp án đúng ('A', 'B', 'C', 'D').
     * @param {string} selectedAnswer - Đáp án người dùng đã chọn.
     * @param {string} guidance - Nội dung giải thích.
     */
    function showResult(isCorrect, correctAnswer, selectedAnswer, guidance) {
        // Vô hiệu hóa tất cả các lựa chọn
        optionsGrid.querySelectorAll('input[type="radio"]').forEach(radio => {
            radio.disabled = true;
            radio.closest('.option-card').classList.remove('selected'); // Bỏ hiệu ứng selected
        });

        // Tìm và tô màu các lựa chọn
        optionsGrid.querySelectorAll('.option-card').forEach(card => {
            const optionValue = card.dataset.option;
            if (optionValue === correctAnswer) {
                card.classList.add('correct');
            } else if (optionValue === selectedAnswer) {
                card.classList.add('incorrect');
            }
        });

        // --- BẮT ĐẦU SỬA: Hiển thị khu vực kết quả ---
        resultSection.style.display = 'block';
        if (guidance) {
            guidanceText.innerText = guidance;
            guidancePanel.style.display = 'block';
        } else {
            guidancePanel.style.display = 'none';
        }
        // --- KẾT THÚC SỬA ---

        // Ẩn nút "Kiểm tra" và hiện nút "Tiếp theo"
        checkAnswerBtn.style.display = 'none';
        nextQuestionBtn.style.display = 'inline-flex';
    }
});

