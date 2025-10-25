from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
from datetime import datetime

USERS_FILE = 'data/users.json'

def load_users():
    """Load users từ file JSON"""
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_users(users):
    """Lưu users vào file JSON"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def register_user(username, password, email, role='student'):
    """
    Đăng ký user mới
    role: 'student' hoặc 'teacher' (teacher được admin tạo riêng)
    """
    users = load_users()
    
    # Kiểm tra username đã tồn tại
    if any(u['username'] == username for u in users):
        return {'success': False, 'message': 'Tên đăng nhập đã tồn tại'}
    
    # Kiểm tra email đã tồn tại
    if any(u['email'] == email for u in users):
        return {'success': False, 'message': 'Email đã được sử dụng'}
    
    # Tạo user mới
    user_id = str(len(users) + 1)
    new_user = {
        'id': user_id,
        'username': username,
        'password': generate_password_hash(password),
        'email': email,
        'role': role,  # student hoặc teacher
        'created_at': datetime.now().isoformat()
    }
    
    users.append(new_user)
    save_users(users)
    
    return {'success': True, 'message': 'Đăng ký thành công'}

def login_user(username, password):
    """Đăng nhập user (hỗ trợ cả hash và plaintext cho bản demo)"""
    users = load_users()
    user = next((u for u in users if u['username'] == username), None)

    if not user:
        return {'success': False, 'message': 'Tên đăng nhập không tồn tại'}

    stored_password = user['password']

    # Nếu mật khẩu là dạng hash (có dấu ':') thì kiểm tra hash,
    # còn nếu là mật khẩu thường (plaintext) thì so sánh trực tiếp.
    if ':' in stored_password:
        password_ok = check_password_hash(stored_password, password)
    else:
        password_ok = (stored_password == password)

    if not password_ok:
        return {'success': False, 'message': 'Mật khẩu không đúng'}

    return {
        'success': True,
        'user_id': user['id'],
        'username': user['username'],
        'role': user['role']
    }


def get_user_by_id(user_id):
    """Lấy thông tin user theo ID"""
    users = load_users()
    return next((u for u in users if u['id'] == user_id), None)

def create_teacher_account(username, password, email):
    """Tạo tài khoản giáo viên (admin dùng)"""
    return register_user(username, password, email, role='teacher')