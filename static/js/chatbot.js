// Chatbot JavaScript

let chatHistory = [];

// Gửi tin nhắn
function sendMessage() {
    const input = document.getElementById('user-input');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Hiển thị tin nhắn user
    displayMessage(message, 'user');
    input.value = '';
    
    // Hiển thị loading
    displayLoading();
    
    // Gửi đến server
    fetch('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            message: message,
            history: chatHistory
        })
    })
    .then(response => response.json())
    .then(data => {
        removeLoading();
        displayMessage(data.response, 'bot');
        
        // Lưu vào history
        chatHistory.push({
            role: 'user',
            content: message
        });
        chatHistory.push({
            role: 'assistant',
            content: data.response
        });
    })
    .catch(error => {
        removeLoading();
        displayMessage('Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại!', 'bot');
        console.error('Error:', error);
    });
}

// Hiển thị tin nhắn
function displayMessage(text, sender) {
    const chatbox = document.getElementById('chatbox');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    messageDiv.textContent = text;
    chatbox.appendChild(messageDiv);
    
    // Scroll to bottom
    chatbox.scrollTop = chatbox.scrollHeight;
}

// Hiển thị loading
function displayLoading() {
    const chatbox = document.getElementById('chatbox');
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot loading';
    loadingDiv.id = 'loading-message';
    loadingDiv.textContent = 'Đang suy nghĩ...';
    chatbox.appendChild(loadingDiv);
    chatbox.scrollTop = chatbox.scrollHeight;
}

// Xóa loading
function removeLoading() {
    const loading = document.getElementById('loading-message');
    if (loading) {
        loading.remove();
    }
}

// Xóa lịch sử chat
function clearChat() {
    if (confirm('Bạn có chắc muốn xóa toàn bộ lịch sử chat?')) {
        chatHistory = [];
        document.getElementById('chatbox').innerHTML = '';
        displayMessage('Xin chào! Tôi là trợ lý AI. Tôi có thể giúp gì cho bạn?', 'bot');
    }
}

// Gợi ý câu hỏi
function suggestQuestion(question) {
    document.getElementById('user-input').value = question;
    sendMessage();
}

// Enter để gửi
document.addEventListener('DOMContentLoaded', function() {
    const input = document.getElementById('user-input');
    if (input) {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    }
    
    // Tin nhắn chào mừng
    displayMessage('Xin chào! Tôi là trợ lý AI hỗ trợ học Tin học THPT. Bạn có thể hỏi tôi về lập trình, thuật toán, hoặc các khái niệm trong môn Tin học.', 'bot');
});