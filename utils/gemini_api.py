import os
import re

import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def remove_markdown_formatting(text):
    """
    Loại bỏ các ký tự định dạng Markdown
    """

    text = re.sub(r'#+\s*', '', text)
    

    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)

    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    

    text = re.sub(r'```[\w]*\n?', '', text)
    text = re.sub(r'```', '', text)
    
   
    text = re.sub(r'`(.+?)`', r'\1', text)
    
    return text.strip()

def chat_with_gemini(user_message):
    """
    Gửi tin nhắn đến Gemini AI và nhận phản hồi
    """
    if not GEMINI_API_KEY:
        return "Xin lỗi, dịch vụ AI chưa được cấu hình. Vui lòng liên hệ quản trị viên để bổ sung GEMINI_API_KEY."
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        system_prompt = """
        Bạn là trợ lý AI cho học sinh THPT ôn thi môn Tin học.
        Nhiệm vụ của bạn là:
        - Giải đáp thắc mắc về lập trình, thuật toán, cấu trúc dữ liệu
        - Hướng dẫn học sinh giải bài tập tin học
        - Giải thích các khái niệm tin học một cách dễ hiểu
        - Trả lời bằng tiếng Việt, ngắn gọn và rõ ràng
        
        QUAN TRỌNG: Trả lời bằng văn bản thuần túy, KHÔNG sử dụng bất kỳ ký tự định dạng nào như:
        - Dấu # cho tiêu đề
        - Dấu ** hoặc * cho in đậm/nghiêng
        - Dấu ``` cho code block
        - Dấu ` cho inline code
        Chỉ viết văn bản bình thường, dễ đọc.
        """
        
        full_prompt = f"{system_prompt}\n\nCâu hỏi của học sinh: {user_message}"
        
        response = model.generate_content(full_prompt)
        
        clean_text = remove_markdown_formatting(response.text)
        
        return clean_text
    
    except Exception as e:
        return f"Xin lỗi, có lỗi xảy ra: {str(e)}"

def chat_with_context(user_message, chat_history=[]):
    """
    Chat với context (lịch sử hội thoại)
    chat_history: [{'role': 'user', 'content': '...'}, {'role': 'assistant', 'content': '...'}]
    """
    if not GEMINI_API_KEY:
        return "Xin lỗi, dịch vụ AI chưa được cấu hình. Vui lòng liên hệ quản trị viên để bổ sung GEMINI_API_KEY."
    try:
        model = genai.GenerativeModel(
            'gemini-2.0-flash-exp',
            generation_config={
                'temperature': 0.7,
            },
            system_instruction="""
            Bạn là trợ lý AI cho học sinh THPT ôn thi môn Tin học.
            Trả lời bằng văn bản thuần túy, KHÔNG sử dụng ký tự định dạng Markdown như #, **, *, ```.
            Chỉ viết văn bản bình thường, dễ đọc.
            """
        )
        

        chat = model.start_chat(history=[])
        

        for msg in chat_history:
            if msg['role'] == 'user':
                chat.send_message(msg['content'])
        

        response = chat.send_message(user_message)
        

        clean_text = remove_markdown_formatting(response.text)
        
        return clean_text
    
    except Exception as e:
        return f"Xin lỗi, có lỗi xảy ra: {str(e)}"

# Test
if __name__ == "__main__":
    print("=== Test chat_with_gemini ===")
    response1 = chat_with_gemini("Giải thích thuật toán sắp xếp nổi bọt")
    print(response1)
    
    print("\n=== Test chat_with_context ===")
    history = [
        {'role': 'user', 'content': 'Độ phức tạp của bubble sort là gì?'}
    ]
    response2 = chat_with_context("Còn quick sort thì sao?", history)
    print(response2)
