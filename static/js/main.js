// Main JavaScript

// Đánh dấu bài học đã hoàn thành
function markLessonComplete(courseId, lessonId) {
    fetch('/update_progress', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            course_id: courseId,
            lesson_id: lessonId,
            completed: true
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Cập nhật UI
            const lessonEl = document.getElementById(`lesson-${lessonId}`);
            if (lessonEl) {
                lessonEl.classList.add('completed');
            }
            alert('Đã đánh dấu hoàn thành!');
            location.reload();
        }
    })
    .catch(error => console.error('Error:', error));
}

// Tạo khóa học mới (giáo viên)
function createCourse() {
    const form = document.getElementById('course-form');
    const formData = new FormData(form);
    
    const courseData = {
        title: formData.get('title'),
        description: formData.get('description'),
        lessons: []
    };
    
    fetch('/teacher/create_course', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(courseData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Tạo khóa học thành công!');
            location.reload();
        }
    })
    .catch(error => console.error('Error:', error));
}

// Thêm bài học vào khóa học
function addLesson(courseId) {
    const title = document.getElementById('lesson-title').value;
    const videoUrl = document.getElementById('video-url').value;
    const docUrl = document.getElementById('doc-url').value;
    
    const lesson = {
        id: 'l' + Date.now(),
        title: title,
        video_url: videoUrl,
        document_url: docUrl,
        questions: []
    };
    
    // Gửi lên server để cập nhật course
    fetch(`/teacher/update_course/${courseId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            action: 'add_lesson',
            lesson: lesson
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Thêm bài học thành công!');
            location.reload();
        }
    })
    .catch(error => console.error('Error:', error));
}

// Nộp bài tập
function submitExercise(exerciseId) {
    const answers = [];
    const questions = document.querySelectorAll('.question');
    
    questions.forEach((q, index) => {
        const selected = q.querySelector('input[type="radio"]:checked');
        if (selected) {
            answers.push({
                question_id: q.dataset.questionId,
                answer: parseInt(selected.value)
            });
        }
    });
    
    fetch('/submit_exercise', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            exercise_id: exerciseId,
            answers: answers
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Đã nộp bài!');
            // Tính điểm (có thể mở rộng)
        }
    })
    .catch(error => console.error('Error:', error));
}

// Tính progress phần trăm
function calculateProgress(completed, total) {
    if (total === 0) return 0;
    return Math.round((completed / total) * 100);
}

// Cập nhật thanh progress
function updateProgressBar(elementId, percentage) {
    const progressBar = document.getElementById(elementId);
    if (progressBar) {
        progressBar.style.width = percentage + '%';
        progressBar.textContent = percentage + '%';
    }
}

// Toggle video player
function toggleVideo(videoUrl) {
    const videoContainer = document.getElementById('video-container');
    if (videoContainer) {
        videoContainer.innerHTML = `
            <iframe width="100%" height="400" 
                src="${videoUrl}" 
                frameborder="0" 
                allowfullscreen>
            </iframe>
        `;
    }
}

// Confirm action
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// Document ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Website học tập Tin học THPT đã sẵn sàng!');
    
    // Auto-hide alerts after 3s
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.display = 'none';
        }, 3000);
    });
});