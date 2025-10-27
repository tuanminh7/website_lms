import json
import os
import uuid
from datetime import datetime, timedelta
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.utils import secure_filename

load_dotenv()

from utils.auth import register_user, login_user, get_user_by_id
from utils.database import Database
from utils.exam_parser import ExamParseError, parse_docx_exam
from utils.gemini_api import chat_with_gemini

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-me')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')

FORUM_UPLOAD_FOLDER = os.getenv('FORUM_UPLOAD_FOLDER', 'static/uploads/forum')
EXAM_UPLOAD_FOLDER = os.getenv('EXAM_UPLOAD_FOLDER', 'static/uploads/exams')
ALLOWED_EXAM_EXTENSIONS = {'docx'}


db = Database()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để tiếp tục', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập', 'warning')
            return redirect(url_for('login'))
        
        user = get_user_by_id(session['user_id'])
        if not user or user['role'] != 'teacher':
            flash('Chỉ giáo viên mới có quyền truy cập trang này', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

#################33
def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập', 'warning')
            return redirect(url_for('login'))
        
        user = get_user_by_id(session['user_id'])
        if not user or user['role'] != 'student':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    
    total_courses = len(db.get_all_courses())
    total_documents = len(db.get_all_documents())
    
    return render_template('index.html', 
                         total_courses=total_courses,
                         total_documents=total_documents)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        
        if not username or not password or not email:
            flash('Vui lòng điền đầy đủ thông tin', 'danger')
            return render_template('register.html')
        
        result = register_user(username, password, email, role='student')
        
        if result['success']:
            flash('Đăng ký thành công! Vui lòng đăng nhập', 'success')
            return redirect(url_for('login'))
        else:
            flash(result['message'], 'danger')
            return render_template('register.html')
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Vui lòng nhập tên đăng nhập và mật khẩu', 'danger')
            return render_template('login.html')
        
        result = login_user(username, password)
        
        if result['success']:
            session['user_id'] = result['user_id']
            session['username'] = result['username']
            session['role'] = result['role']
            
            flash(f'Chào mừng {result["username"]}!', 'success')
            
            if result['role'] == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash(result['message'], 'danger')
            return render_template('login.html')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    username = session.get('username', 'Người dùng')
    session.clear()
    flash(f'Tạm biệt {username}!', 'info')
    return redirect(url_for('index'))


@app.route('/student/dashboard')
@login_required
@student_required
def student_dashboard():
    courses = db.get_all_courses()
    my_progress = db.get_student_progress(session['user_id'])
    
    enrolled_courses = []
    for progress in my_progress:
        course = db.get_course_by_id(progress['course_id'])
        if course:
            total_lessons = len(course.get('lessons', []))
            completed_lessons = len(progress.get('completed_lessons', []))
            percentage = (completed_lessons / total_lessons * 100) if total_lessons > 0 else 0
            
            enrolled_courses.append({
                'course': course,
                'progress': progress,
                'percentage': round(percentage, 1)
            })
    
    return render_template('student_dashboard.html', 
                         courses=courses,
                         enrolled_courses=enrolled_courses,
                         username=session.get('username'))


@app.route('/teacher/dashboard')
@login_required
@teacher_required
def teacher_dashboard():
    my_courses = db.get_courses_by_teacher(session['user_id'])
    
    course_stats = []
    for course in my_courses:
        all_progress = db._load_json(db.progress_file)
        students_enrolled = len([p for p in all_progress if p['course_id'] == course['id']])
        
        course_stats.append({
            'course': course,
            'students_enrolled': students_enrolled,
            'total_lessons': len(course.get('lessons', []))
        })
    
    return render_template('teacher_dashboard.html',
                         courses=course_stats,
                         username=session.get('username'))


@app.route('/courses')
@login_required
def courses():
    all_courses = db.get_all_courses()
    
    courses_with_teacher = []
    for course in all_courses:
        teacher = get_user_by_id(course['teacher_id'])
        course['teacher_name'] = teacher['username'] if teacher else 'Unknown'
        courses_with_teacher.append(course)
    
    return render_template('courses.html', courses=courses_with_teacher)


@app.route('/course/<course_id>')
@login_required
def course_detail(course_id):
    course = db.get_course_by_id(course_id)
    
    if not course:
        flash('Khóa học không tồn tại', 'danger')
        return redirect(url_for('courses'))
    
    teacher = get_user_by_id(course['teacher_id'])
    course['teacher_name'] = teacher['username'] if teacher else 'Unknown'
    
    progress = db.get_course_progress(session['user_id'], course_id)
    completed_lessons = progress['completed_lessons'] if progress else []
    
    is_teacher = session.get('role') == 'teacher' and course['teacher_id'] == session['user_id']
    
    return render_template('course_detail.html', 
                         course=course,
                         completed_lessons=completed_lessons,
                         is_teacher=is_teacher)


@app.route('/teacher/create_course', methods=['GET', 'POST'])
@teacher_required
def create_course():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            if not data.get('title'):
                return jsonify({'success': False, 'message': 'Vui lòng nhập tên khóa học'})
            
            all_courses = db.get_all_courses()
            if any(c['title'].lower() == data['title'].lower() and c['teacher_id'] == session['user_id'] for c in all_courses):
                return jsonify({'success': False, 'message': 'Bạn đã có khóa học trùng tên này'})
            
            course_id = db.create_course(data, session['user_id'])
            
            return jsonify({'success': True, 'course_id': course_id, 'message': 'Tạo khóa học thành công'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('create_course.html')


@app.route('/teacher/edit_course/<course_id>', methods=['GET', 'POST'])
@teacher_required
def edit_course(course_id):
    course = db.get_course_by_id(course_id)
    
    if not course:
        flash('Khóa học không tồn tại', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    if course['teacher_id'] != session['user_id']:
        flash('Bạn không có quyền chỉnh sửa khóa học này', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            success = db.update_course(course_id, data)
            
            if success:
                return jsonify({'success': True, 'message': 'Cập nhật khóa học thành công'})
            else:
                return jsonify({'success': False, 'message': 'Cập nhật thất bại'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('create_course.html', course=course, edit_mode=True)


@app.route('/teacher/delete_course/<course_id>', methods=['POST'])
@teacher_required
def delete_course(course_id):
    course = db.get_course_by_id(course_id)
    
    if not course:
        return jsonify({'success': False, 'message': 'Khóa học không tồn tại'})
    
    if course['teacher_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Bạn không có quyền xóa khóa học này'})
    
    courses = db.get_all_courses()
    courses = [c for c in courses if c['id'] != course_id]
    db._save_json(db.courses_file, courses)
    
    return jsonify({'success': True, 'message': 'Xóa khóa học thành công'})


@app.route('/exercises')
@login_required
def exercises():
    all_courses = db.get_all_courses()
    
    exercises_list = []
    for course in all_courses:
        for lesson in course.get('lessons', []):
            questions = lesson.get('questions', [])
            if questions:
                exercises_list.append({
                    'course_id': course['id'],
                    'course_title': course['title'],
                    'lesson_id': lesson['id'],
                    'lesson_title': lesson['title'],
                    'questions': questions
                })
    
    try:
        all_submissions = db._load_json(db.submissions_file) if hasattr(db, 'submissions_file') else []
    except:
        all_submissions = []
    
    my_submissions = [s for s in all_submissions if s.get('user_id') == session['user_id']]
    
    return render_template('exercises.html', 
                         exercises=exercises_list,
                         submissions=my_submissions)


@app.route('/submit_exercise', methods=['POST'])
@login_required
def submit_exercise():
    try:
        data = request.get_json()
        
        if not data.get('course_id') or not data.get('lesson_id') or not data.get('answers'):
            return jsonify({'success': False, 'message': 'Dữ liệu không đầy đủ'})
        
        submission_data = {
            'course_id': data['course_id'],
            'exercise_id': data['lesson_id'],
            'answers': data['answers'],
            'submitted_at': datetime.now().isoformat()
        }
        
        submission_id = db.save_exercise_submission(session['user_id'], submission_data)
        
        course = db.get_course_by_id(data['course_id'])
        if course:
            lesson = next((l for l in course.get('lessons', []) if l['id'] == data['lesson_id']), None)
            if lesson:
                questions = lesson.get('questions', [])
                correct = 0
                total = len(questions)
                
                for i, q in enumerate(questions):
                    user_answer_raw = data['answers'].get(str(i), '')
                    user_choice = normalize_answer_token(user_answer_raw)
                    correct_answers = normalize_correct_answers(q.get('correct_answer'))
                    
                    if user_choice and user_choice in correct_answers:
                        correct += 1
                
                score = round((correct / total * 100) if total > 0 else 0, 1)
                
                return jsonify({
                    'success': True,
                    'submission_id': submission_id,
                    'score': score,
                    'correct': correct,
                    'total': total,
                    'message': 'Nộp bài thành công'
                })
        
        return jsonify({'success': True, 'submission_id': submission_id, 'message': 'Nộp bài thành công'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/documents')
@login_required
def documents():
    # Lấy các tham số lọc từ query string
    grade_filter = request.args.get('grade', 'all')  # 10, 11, 12, hoặc all
    type_filter = request.args.get('type', 'all')    # document, lecture, exam, hoặc all
    
    docs = db.get_all_documents()
    
    if grade_filter != 'all':
        docs = [d for d in docs if d.get('grade') == grade_filter]
    if type_filter != 'all':
        docs = [d for d in docs if d.get('doc_type') == type_filter]
    
    docs_by_grade = {
        '10': [d for d in docs if d.get('grade') == '10'],
        '11': [d for d in docs if d.get('grade') == '11'],
        '12': [d for d in docs if d.get('grade') == '12']
    }
    
    return render_template('documents.html',
                         docs_by_grade=docs_by_grade,
                         current_grade=grade_filter,
                         current_type=type_filter)



@app.route('/teacher/add_document', methods=['GET', 'POST'])
@teacher_required
def add_document():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            if not data.get('title') or not data.get('url'):
                return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ thông tin'})
            
            # Thêm trường grade và doc_type vào dữ liệu
            if not data.get('grade'):
                return jsonify({'success': False, 'message': 'Vui lòng chọn lớp học'})
            
            if not data.get('doc_type'):
                return jsonify({'success': False, 'message': 'Vui lòng chọn loại tài liệu'})
            
            if 'youtube.com' in data['url'] or 'youtu.be' in data['url']:
                data['link_type'] = 'youtube'
            elif 'drive.google.com' in data['url']:
                data['link_type'] = 'drive'
            else:
                data['link_type'] = data.get('link_type', 'other')
            
            doc_id = db.add_document(data)
            
            return jsonify({'success': True, 'doc_id': doc_id, 'message': 'Thêm tài liệu thành công'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('add_document.html')


@app.route('/teacher/import_exam', methods=['GET', 'POST'])
@teacher_required
def import_exam():
    form_data = {
        'title': request.form.get('title', '').strip(),
        'description': request.form.get('description', '').strip(),
        'time_limit': request.form.get('time_limit', '').strip() or '15',
        'grade': request.form.get('grade', '').strip(),
        'allow_multiple': 'on' if request.form.get('allow_multiple') else 'off'
    } if request.method == 'POST' else {
        'title': '',
        'description': '',
        'time_limit': '15',
        'grade': '12',
        'allow_multiple': 'off'
    }

    if request.method == 'POST':
        grade = form_data['grade']
        title = form_data['title']
        description = form_data['description']
        time_limit_raw = form_data['time_limit']
        exam_file = request.files.get('exam_file')
        allow_multiple = form_data['allow_multiple'] == 'on'

        errors = []
        if grade not in {'10', '11', '12'}:
            errors.append('Vui lòng chọn khối lớp hợp lệ (10, 11 hoặc 12).')

        try:
            time_limit = int(time_limit_raw)
            if time_limit <= 0:
                raise ValueError
        except ValueError:
            errors.append('Thời gian làm bài phải là số nguyên dương (phút).')
            time_limit = 15

        if not title:
            errors.append('Vui lòng nhập tên đề thi.')

        if not exam_file or not exam_file.filename:
            errors.append('Vui lòng chọn file .docx cần import.')
        elif not allowed_exam_file(exam_file.filename):
            errors.append('Chỉ hỗ trợ file định dạng .docx.')

        if errors:
            for message in errors:
                flash(message, 'danger')
            return render_template('import_exam.html', form_data=form_data)

        secure_name = secure_filename(exam_file.filename)
        ensure_directory(EXAM_UPLOAD_FOLDER)
        temp_filename = f"{uuid.uuid4().hex}_{secure_name}"
        temp_path = os.path.join(EXAM_UPLOAD_FOLDER, temp_filename)
        exam_file.save(temp_path)

        parsed_questions = []

        try:
            parsed_questions = parse_docx_exam(temp_path, allow_multiple_answers=False)
        except ExamParseError as exc:
            error_message = str(exc)
            if 'nhiều đáp án đúng' in error_message.lower():
                try:
                    parsed_questions = parse_docx_exam(temp_path, allow_multiple_answers=True)
                except ExamParseError as re_exc:
                    flash(f'Lỗi khi đọc file đề: {re_exc}', 'danger')
                    os.remove(temp_path)
                    return render_template('import_exam.html', form_data=form_data)
                except Exception as re_exc:
                    flash(f'Lỗi không xác định khi xử lý file: {re_exc}', 'danger')
                    os.remove(temp_path)
                    return render_template('import_exam.html', form_data=form_data)
            else:
                flash(f'Lỗi khi đọc file đề: {exc}', 'danger')
                os.remove(temp_path)
                return render_template('import_exam.html', form_data=form_data)
        except Exception as exc:
            flash(f'Lỗi không xác định khi xử lý file: {exc}', 'danger')
            os.remove(temp_path)
            return render_template('import_exam.html', form_data=form_data)
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

        if not parsed_questions:
            flash('Không tìm thấy câu hỏi trắc nghiệm nào trong file.', 'danger')
            return render_template('import_exam.html', form_data=form_data)

        questions_with_multiple = [
            item.get('number')
            for item in parsed_questions
            if len(normalize_correct_answers(item.get('correct_answer'))) > 1
        ]

        if questions_with_multiple and not allow_multiple:
            question_list = ', '.join(str(num) for num in questions_with_multiple[:5])
            more_suffix = '...' if len(questions_with_multiple) > 5 else ''
            flash(
                f'Đề thi có các câu {question_list}{more_suffix} được đánh dấu nhiều đáp án đúng. '
                'Vui lòng bật tùy chọn "Cho phép nhiều đáp án đúng" trước khi import.',
                'warning'
            )
            form_data['allow_multiple'] = 'on'
            return render_template('import_exam.html', form_data=form_data)

        questions = []
        has_tl2_question = False
        for idx, item in enumerate(parsed_questions, start=1):
            options = item.get('options', {})
            correct_answer = item.get('correct_answer')
            question_type = item.get('type', 'tl1')

            if not options or len(options) < 2:
                flash(f'Câu {item.get("number", idx)} không có đủ lựa chọn.', 'danger')
                return render_template('import_exam.html', form_data=form_data)

            if question_type == 'tl2':
                has_tl2_question = True
                if len(options) != 4:
                    flash(f'Câu {item.get("number", idx)} (TL2) cần đúng 4 ý để đánh giá Đúng/Sai.', 'danger')
                    return render_template('import_exam.html', form_data=form_data)

            option_keys = {key.upper(): key for key in options.keys()}
            correct_tokens = normalize_correct_answers(correct_answer)
            if not correct_tokens:
                flash(f'Không xác định được đáp án đúng cho câu {item.get("number", idx)}.', 'danger')
                return render_template('import_exam.html', form_data=form_data)

            invalid_tokens = [token for token in correct_tokens if token not in option_keys]
            if invalid_tokens:
                flash(
                    f'Đáp án {", ".join(invalid_tokens)} của câu {item.get("number", idx)} không trùng với lựa chọn A/B/C/D.',
                    'danger'
                )
                return render_template('import_exam.html', form_data=form_data)

            def convert_token(token):
                # Map back to original key casing (A vs a) if needed
                return option_keys.get(token, token)

            if question_type == 'tl2':
                normalized_correct = [convert_token(token) for token in sorted(correct_tokens)]
            else:
                if len(correct_tokens) > 1:
                    normalized_correct = [convert_token(token) for token in sorted(correct_tokens)]
                    if len(normalized_correct) == 1:
                        normalized_correct = normalized_correct[0]
                else:
                    normalized_correct = convert_token(next(iter(correct_tokens)))

            questions.append({
                'id': item.get('number', idx),
                'number': item.get('number', idx),
                'question': item.get('question', '').strip(),
                'options': options,
                'correct_answer': normalized_correct,
                'explanation': item.get('explanation', '').strip(),
                'type': question_type
            })

        exam_id = f"exam_{grade}_{uuid.uuid4().hex[:6]}"
        exam_record = {
            'id': exam_id,
            'title': title,
            'description': description,
            'time_limit': time_limit,
            'questions': questions,
            'allow_multiple_answers': bool(questions_with_multiple or has_tl2_question),
            'created_by': session.get('user_id'),
            'created_by_name': session.get('username'),
            'created_at': datetime.now().isoformat()
        }

        try:
            db.add_exam(grade, exam_record)
        except Exception as exc:
            flash(f'Không thể lưu đề thi: {exc}', 'danger')
            return render_template('import_exam.html', form_data=form_data)

        flash(f'Đã tạo đề thi "{title}" với {len(questions)} câu hỏi cho khối {grade}.', 'success')
        return redirect(url_for('tracnghiem'))

    return render_template('import_exam.html', form_data=form_data)


@app.route('/chatbot')
@login_required
def chatbot():
    return render_template('chatbot.html', username=session.get('username'))


@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'response': 'Vui lòng nhập tin nhắn'})
        
        response = chat_with_gemini(message)
        
        return jsonify({'success': True, 'response': response})
    
    except Exception as e:
        return jsonify({'success': False, 'response': f'Xin lỗi, có lỗi xảy ra: {str(e)}'})


@app.route('/update_progress', methods=['POST'])
@login_required
def update_progress():
    try:
        data = request.get_json()
        
        if not data.get('course_id') or not data.get('lesson_id'):
            return jsonify({'success': False, 'message': 'Dữ liệu không đầy đủ'})
        
        db.update_progress(
            session['user_id'],
            data['course_id'],
            data['lesson_id'],
            data.get('completed', True),
            timestamp=datetime.now().isoformat()
        )
        
        return jsonify({'success': True, 'message': 'Cập nhật tiến độ thành công'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/teacher/students_progress')
@teacher_required
def students_progress():
    teacher_courses = db.get_courses_by_teacher(session['user_id'])
    teacher_course_ids = [c['id'] for c in teacher_courses]
    
    all_progress = db._load_json(db.progress_file)
    filtered_progress = [p for p in all_progress if p['course_id'] in teacher_course_ids]
    
    progress_with_details = []
    for prog in filtered_progress:
        student = get_user_by_id(prog['user_id'])
        course = db.get_course_by_id(prog['course_id'])
        
        if student and course:
            total_lessons = len(course.get('lessons', []))
            completed = len(prog.get('completed_lessons', []))
            percentage = round((completed / total_lessons * 100) if total_lessons > 0 else 0, 1)
            
            progress_with_details.append({
                'student_name': student['username'],
                'student_email': student.get('email', ''),
                'course_title': course['title'],
                'completed': completed,
                'total': total_lessons,
                'percentage': percentage,
                'last_updated': prog.get('last_updated', 'Chưa cập nhật')
            })

    return render_template('student_progress.html', progress=progress_with_details)

@app.route('/teacher/exams')
@login_required
@teacher_required
def teacher_exams():
    teacher_id = session.get('user_id')
    exams_by_grade = {}

    for grade in ['10', '11', '12']:
        bank = db.load_exam_bank(grade)
        grade_exams = []

        for exam in bank.get('exams', []):
            exam_copy = {
                'id': exam.get('id'),
                'title': exam.get('title', 'Không có tiêu đề'),
                'description': exam.get('description', ''),
                'time_limit': exam.get('time_limit', 15),
                'question_count': len(exam.get('questions', [])),
                'created_at': exam.get('created_at'),
                'allow_multiple_answers': exam.get('allow_multiple_answers', False),
                'created_by': exam.get('created_by'),
                'created_by_name': exam.get('created_by_name', 'Không rõ'),
                'grade': grade,
            }
            exam_copy['is_owner'] = exam_copy['created_by'] == teacher_id or exam_copy['created_by'] is None
            grade_exams.append(exam_copy)

        exams_by_grade[grade] = grade_exams

    return render_template('teacher_exams.html',
                           exams_by_grade=exams_by_grade,
                           username=session.get('username'))

@app.route('/teacher/delete_exam', methods=['POST'])
@login_required
@teacher_required
def delete_exam():
    try:
        data = request.get_json() or {}
        grade = str(data.get('grade', '')).strip()
        exam_id = data.get('exam_id')

        if grade not in {'10', '11', '12'} or not exam_id:
            return jsonify({'success': False, 'message': 'Thiếu thông tin đề thi'}), 400

        bank = db.load_exam_bank(grade)
        exam = next((e for e in bank.get('exams', []) if e.get('id') == exam_id), None)

        if not exam:
            return jsonify({'success': False, 'message': 'Không tìm thấy đề thi'}), 404

        owner_id = exam.get('created_by')
        if owner_id and owner_id != session.get('user_id'):
            return jsonify({'success': False, 'message': 'Bạn chỉ có thể xoá đề thi do mình tạo'}), 403

        if not db.delete_exam(grade, exam_id):
            return jsonify({'success': False, 'message': 'Không thể xoá đề thi'}), 500

        removed_results = db.delete_exam_results(exam_id, grade)

        return jsonify({
            'success': True,
            'message': 'Đã xoá đề thi và xoá kết quả liên quan.' if removed_results else 'Đã xoá đề thi.',
            'removed_results': removed_results
        })
    except Exception as exc:
        return jsonify({'success': False, 'message': f'Lỗi: {exc}'}), 500


@app.route('/teacher/view_submissions')
@teacher_required
def view_submissions():
    teacher_courses = db.get_courses_by_teacher(session['user_id'])
    teacher_course_ids = [c['id'] for c in teacher_courses]
    
    try:
        all_submissions = db._load_json(db.submissions_file) if hasattr(db, 'submissions_file') else []
    except:
        all_submissions = []
    
    filtered_submissions = [s for s in all_submissions if s.get('course_id') in teacher_course_ids]
    
    submissions_with_details = []
    for sub in filtered_submissions:
        student = get_user_by_id(sub['user_id'])
        course = db.get_course_by_id(sub.get('course_id'))
        
        if student and course:
            submissions_with_details.append({
                'student_name': student['username'],
                'course_title': course['title'],
                'exercise_id': sub.get('exercise_id'),
                'answers': sub.get('answers', {}),
                'submitted_at': sub.get('submitted_at', 'Không rõ')
            })
    
    return render_template('view_submissions.html', submissions=submissions_with_details)


@app.route('/api/course/<course_id>')
@login_required
def api_get_course(course_id):
    course = db.get_course_by_id(course_id)
    if course:
        return jsonify({'success': True, 'course': course})
    return jsonify({'success': False, 'error': 'Course not found'}), 404


@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500



########################
###############33
@app.route('/tracnghiem/lam-bai/<grade>/<exam_id>')
@login_required
def lam_bai_tracnghiem(grade, exam_id):
    """
    Hiển thị đề trắc nghiệm để học sinh làm bài
     Fix: Logic thời gian chặt chẽ, xử lý session an toàn
    """
    if grade not in ['10', '11', '12']:
        flash('Lớp không hợp lệ', 'danger')
        return redirect(url_for('tracnghiem'))
    
    json_file = f'data/lop{grade}.json'
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            exams_data = json.load(f)
            exams = exams_data.get('exams', [])
            
            exam = next((e for e in exams if e['id'] == exam_id), None)
            
            if not exam:
                flash('Đề thi không tồn tại', 'danger')
                return redirect(url_for('tracnghiem'))
            
            time_limit = exam.get('time_limit', 15)
            
            if not isinstance(time_limit, (int, float)) or time_limit <= 0:
                time_limit = 15
                print(f"Warning: Invalid time_limit in exam {exam_id}, using default 15 minutes")
            
            session_key = f'exam_start_{grade}_{exam_id}'
            reset_param = request.args.get('reset', 'no')
            
            if not session.permanent:
                session.permanent = True
                session.modified = True
            

            should_create_new_session = False
            remaining_time = time_limit * 60  # Mặc định
            
            if reset_param == 'yes':
                should_create_new_session = True
                print(f"Reset session for exam {exam_id}")
            
            elif session_key not in session:
                should_create_new_session = True
                print(f"New session for exam {exam_id}")
            else:
                try:
                    start_time_str = session.get(session_key)
                    if not start_time_str or not isinstance(start_time_str, str):
                        raise ValueError("Invalid start_time format")
                    
                    start_time = datetime.fromisoformat(start_time_str)
                    current_time = datetime.now()
                    
                    elapsed_seconds = (current_time - start_time).total_seconds()
                    
                    if elapsed_seconds < 0:
                        print(f"ERROR: Negative elapsed time for exam {exam_id}")
                        should_create_new_session = True
                    elif elapsed_seconds > (time_limit * 60 * 2):
                        print(f"WARNING: Session too old for exam {exam_id}")
                        should_create_new_session = True
                    else:
                        remaining_time = (time_limit * 60) - elapsed_seconds
                        

                        if remaining_time <= 0:
                            flash('⏰ Đã hết thời gian làm bài! Vui lòng làm lại từ đầu.', 'warning')
                            # Xóa session cũ
                            session.pop(session_key, None)
                            session.modified = True
                            return redirect(url_for('tracnghiem'))
                        
                        print(f"Exam {exam_id}: {int(remaining_time)}s remaining")
                
                except (ValueError, KeyError, TypeError, AttributeError) as e:
                    print(f"Session error for exam {exam_id}: {e}")
                    should_create_new_session = True
            
            if should_create_new_session:
                current_time = datetime.now()
                session[session_key] = current_time.isoformat()
                session.permanent = True
                session.modified = True
                remaining_time = time_limit * 60
                print(f"Created new session for exam {exam_id}, expires in {time_limit} minutes")
            

            remaining_time = max(1, min(remaining_time, time_limit * 60))
            remaining_time = int(remaining_time)  # Convert to integer
            
            # . LOG (cho debug)
            print(f"""
            ===== EXAM SESSION INFO =====
            Exam: {exam_id} | Grade: {grade}
            Time Limit: {time_limit} minutes
            Remaining: {remaining_time} seconds ({remaining_time//60}m {remaining_time%60}s)
            Session Key: {session_key}
            Session Permanent: {session.permanent}
            ============================
            """)
            

            for question in exam.get('questions', []):
                if isinstance(question, dict):
                    question.setdefault('type', 'tl1')
                    if question.get('type') == 'tl2' and isinstance(question.get('correct_answer'), str):
                        question['correct_answer'] = [question['correct_answer']]
            has_tl2 = any(q.get('type') == 'tl2' for q in exam.get('questions', []))

            return render_template('baitap.html',
                                 exam=exam,
                                 grade=grade,
                                 time_limit=time_limit,
                                 remaining_time=remaining_time,
                                 username=session.get('username'),
                                 has_tl2=has_tl2)
    
    except FileNotFoundError:
        flash(' Không tìm thấy dữ liệu đề thi', 'danger')
        return redirect(url_for('tracnghiem'))
    
    except json.JSONDecodeError as e:
        flash(' Dữ liệu đề thi bị lỗi định dạng', 'danger')
        print(f"JSON decode error: {e}")
        return redirect(url_for('tracnghiem'))
    
    except Exception as e:
        flash(f' Lỗi không xác định: {str(e)}', 'danger')
        print(f"Unexpected error in lam_bai_tracnghiem: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('tracnghiem'))



@app.route('/api/tracnghiem/check-time/<grade>/<exam_id>')
@login_required
def api_check_exam_time(grade, exam_id):
    """
    API kiểm tra thời gian còn lại - GỌI TỪ JAVASCRIPT
    Trả về: remaining_time (seconds) hoặc is_expired=True
    """
    session_key = f'exam_start_{grade}_{exam_id}'
    
    if session_key not in session:
        return jsonify({
            'success': False,
            'message': 'Session không tồn tại',
            'is_expired': True,
            'remaining_time': 0
        })
    
    try:
        json_file = f'data/lop{grade}.json'
        with open(json_file, 'r', encoding='utf-8') as f:
            exams_data = json.load(f)
            exams = exams_data.get('exams', [])
            exam = next((e for e in exams if e['id'] == exam_id), None)
            
            if not exam:
                return jsonify({
                    'success': False,
                    'message': 'Đề thi không tồn tại',
                    'is_expired': True,
                    'remaining_time': 0
                })
            
            time_limit = exam.get('time_limit', 15)
        

        start_time = datetime.fromisoformat(session[session_key])
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        remaining_seconds = (time_limit * 60) - elapsed_seconds
        
        # Validate
        if remaining_seconds <= 0:
            # Hết giờ - xóa session
            session.pop(session_key, None)
            session.modified = True
            
            return jsonify({
                'success': True,
                'remaining_time': 0,
                'is_expired': True,
                'message': 'Hết thời gian'
            })
        
        return jsonify({
            'success': True,
            'remaining_time': int(remaining_seconds),
            'is_expired': False,
            'time_limit_minutes': time_limit
        })
    
    except (ValueError, KeyError, TypeError) as e:
        print(f"Error in api_check_exam_time: {e}")
        return jsonify({
            'success': False,
            'message': f'Lỗi session: {str(e)}',
            'is_expired': True,
            'remaining_time': 0
        })
    
    except Exception as e:
        print(f"Unexpected error in api_check_exam_time: {e}")
        return jsonify({
            'success': False,
            'message': f'Lỗi: {str(e)}',
            'is_expired': True,
            'remaining_time': 0
        })



@app.route('/tracnghiem')
@login_required
def tracnghiem():
    """
    Trang chọn đề thi trắc nghiệm
    """
    print("========= DEBUG TRACNGHIEM =========")
    print(f"User ID: {session.get('user_id')}")
    print(f"Role: {session.get('role')}")
    print(f"Username: {session.get('username')}")
    print("====================================")
    
    try:
        all_exams = []
        
        # Đọc đề thi từ 3 khối lớp
        for grade in ['10', '11', '12']:
            json_file = f'data/lop{grade}.json'
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    exams_data = json.load(f)
                    exams = exams_data.get('exams', [])
                    
                    for exam in exams:
                        exam['grade'] = grade
                    
                    all_exams.extend(exams)
                    print(f"✓ Loaded {len(exams)} exams from grade {grade}")
            
            except FileNotFoundError:
                print(f"✗ File {json_file} không tồn tại")
                continue
            except json.JSONDecodeError:
                print(f"✗ File {json_file} bị lỗi định dạng")
                continue
        

        exams_by_grade = {
            '10': [e for e in all_exams if e['grade'] == '10'],
            '11': [e for e in all_exams if e['grade'] == '11'],
            '12': [e for e in all_exams if e['grade'] == '12']
        }
        
        print(f"Total exams: {len(all_exams)}")
        print(f"Grade 10: {len(exams_by_grade['10'])}")
        print(f"Grade 11: {len(exams_by_grade['11'])}")
        print(f"Grade 12: {len(exams_by_grade['12'])}")
        
        return render_template('tracnghiem.html', 
                             exams_by_grade=exams_by_grade,
                             username=session.get('username'))
    
    except Exception as e:
        print(f"ERROR in tracnghiem route: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Lỗi khi tải danh sách đề thi: {str(e)}', 'danger')
        return redirect(url_for('student_dashboard'))

@app.route('/tracnghiem/nop-bai', methods=['POST'])
@login_required
def nop_bai_tracnghiem():
    """
    Nộp bài -  Thêm validate thời gian
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'Không nhận được dữ liệu'
            }), 400
        
        grade = data.get('grade')
        exam_id = data.get('exam_id')
        answers = data.get('answers', {})
        
        if not grade or not exam_id:
            return jsonify({
                'success': False,
                'message': 'Thiếu thông tin đề thi'
            }), 400
        
        if grade not in ['10', '11', '12']:
            return jsonify({
                'success': False,
                'message': 'Lớp không hợp lệ'
            }), 400
        
        session_key = f'exam_start_{grade}_{exam_id}'
        
        if session_key not in session:
            return jsonify({
                'success': False,
                'message': ' Session đã hết hạn. Vui lòng làm lại.'
            }), 403
        
        json_file = f'data/lop{grade}.json'
        with open(json_file, 'r', encoding='utf-8') as f:
            exams_data = json.load(f)
            exams = exams_data.get('exams', [])
            exam = next((e for e in exams if e['id'] == exam_id), None)
            
            if not exam:
                return jsonify({
                    'success': False,
                    'message': 'Không tìm thấy đề thi'
                }), 404
            
            time_limit = exam.get('time_limit', 15)
            
            try:
                start_time = datetime.fromisoformat(session[session_key])
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                
                if elapsed_seconds > (time_limit * 60):
                    # Nộp muộn - không chấp nhận
                    session.pop(session_key, None)
                    session.modified = True
                    
                    return jsonify({
                        'success': False,
                        'message': '⏰ Đã hết thời gian làm bài! Không thể nộp.'
                    }), 403
            
            except (ValueError, KeyError):
                return jsonify({
                    'success': False,
                    'message': 'Session không hợp lệ'
                }), 403
            questions = exam.get('questions', [])
            total_questions = len(questions)
            total_points = 0.0
            full_correct_count = 0
            wrong_answers = []
            question_breakdown = []

            for question in questions:
                q_id = str(question.get('id'))
                question_type = question.get('type', 'tl1')
                options = question.get('options', {}) or {}
                correct_answer_value = question.get('correct_answer')
                correct_choices = normalize_correct_answers(correct_answer_value)

                option_token_map = {normalize_answer_token(key): key for key in options.keys()}

                if question_type == 'tl2':
                    response_payload = answers.get(q_id, {})
                    if isinstance(response_payload, dict):
                        selected_true_raw = response_payload.get('selected_true', [])
                        option_states_raw = response_payload.get('option_states', {})
                    elif isinstance(response_payload, list):
                        selected_true_raw = response_payload
                        option_states_raw = {}
                    else:
                        selected_true_raw = response_payload if response_payload else []
                        option_states_raw = {}

                    if isinstance(selected_true_raw, str):
                        selected_true_raw = [selected_true_raw]

                    student_true = {
                        normalize_answer_token(choice)
                        for choice in selected_true_raw
                        if normalize_answer_token(choice) in option_token_map
                    }
                    expected_true = {token for token in correct_choices if token in option_token_map}
                    answered_tokens = {
                        normalize_answer_token(key)
                        for key in (option_states_raw.keys() if isinstance(option_states_raw, dict) else [])
                    }
                    all_tokens = {normalize_answer_token(key) for key in options.keys()}
                    missing_tokens = all_tokens - answered_tokens

                    mistakes = len(expected_true.symmetric_difference(student_true))
                    extra_mistakes = len(missing_tokens - expected_true)
                    mistakes = min(len(all_tokens), mistakes + extra_mistakes)

                    question_point = calculate_tl2_score(mistakes)

                    if question_point >= 0.999:
                        full_correct_count += 1
                    else:
                        wrong_answers.append({
                            'question_number': question.get('number'),
                            'question_text': question.get('question'),
                            'question_type': 'tl2',
                            'student_true': [option_token_map.get(token, token) for token in sorted(student_true)],
                            'expected_true': [option_token_map.get(token, token) for token in sorted(expected_true)],
                            'options': options,
                            'mistakes': mistakes,
                            'option_states': option_states_raw,
                            'missing_choices': [option_token_map.get(token, token) for token in sorted(missing_tokens)],
                            'explanation': question.get('explanation', '')
                        })

                    question_breakdown.append({
                        'question_number': question.get('number'),
                        'type': 'tl2',
                        'score': question_point,
                        'mistakes': mistakes
                    })
                else:
                    response_payload = answers.get(q_id, '')
                    if isinstance(response_payload, dict):
                        user_choice = normalize_answer_token(response_payload.get('selected'))
                    else:
                        user_choice = normalize_answer_token(response_payload)

                    if user_choice and user_choice in correct_choices:
                        question_point = 1.0
                        full_correct_count += 1
                    else:
                        question_point = 0.0
                        wrong_answers.append({
                            'question_number': question.get('number'),
                            'question_text': question.get('question'),
                            'question_type': 'standard',
                            'user_answer': user_choice if user_choice else 'Không trả lời',
                            'correct_answer': format_correct_answer(correct_answer_value),
                            'explanation': question.get('explanation', '')
                        })

                    question_breakdown.append({
                        'question_number': question.get('number'),
                        'type': 'standard',
                        'score': question_point,
                        'selected': user_choice
                    })

                total_points += question_point

            score = round((total_points / total_questions) * 10, 2) if total_questions > 0 else 0


            session.pop(session_key, None)
            session.modified = True
            
            # Lưu kết quả
            result_data = {
                'user_id': session['user_id'],
                'username': session.get('username', 'Unknown'),
                'grade': grade,
                'exam_id': exam_id,
                'exam_title': exam.get('title', ''),
                'score': score,
                'correct_count': full_correct_count,
                'total_questions': total_questions,
                'total_points': round(total_points, 2),
                'question_breakdown': question_breakdown,
                'submitted_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                'time_spent_seconds': int(elapsed_seconds)  # 
            }
            
            try:
                results_file = 'data/exam_results.json'
                os.makedirs('data', exist_ok=True)
                
                try:
                    with open(results_file, 'r', encoding='utf-8') as f:
                        all_results = json.load(f)
                except FileNotFoundError:
                    all_results = []
                
                all_results.append(result_data)
                
                with open(results_file, 'w', encoding='utf-8') as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)
                
                print(f"✅ Saved result: User {session['user_id']}, Score: {score}")
            
            except Exception as e:
                print(f"❌ Error saving result: {e}")
            
            return jsonify({
                'success': True,
                'score': score,
                'correct_count': full_correct_count,
                'total_questions': total_questions,
                'total_points': round(total_points, 2),
                'wrong_answers': wrong_answers,
                'message': 'Nộp bài thành công'
            })
    
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'message': 'Không tìm thấy file dữ liệu đề thi'
        }), 404
    
    except json.JSONDecodeError:
        return jsonify({
            'success': False,
            'message': 'Dữ liệu đề thi bị lỗi'
        }), 500
    
    except Exception as e:
        print(f"ERROR in nop_bai_tracnghiem: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Lỗi server: {str(e)}'
        }), 500

@app.route('/tracnghiem/lich-su')
@login_required
def lich_su_tracnghiem():
    """
    Hiển thị lịch sử làm bài trắc nghiệm của học sinh
    """
    try:
        user_id = session.get('user_id')
        results_file = 'data/exam_results.json'
        
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                all_results = json.load(f)
        except FileNotFoundError:
            all_results = []
        except json.JSONDecodeError:
            print("ERROR: exam_results.json bị lỗi định dạng")
            all_results = []
        

        user_results = [r for r in all_results if r.get('user_id') == user_id]
        user_results.sort(key=lambda x: x.get('submitted_at', ''), reverse=True)
        
        print(f"User {user_id} có {len(user_results)} bài đã làm")
        
        return render_template('lichsu_tracnghiem.html', 
                             results=user_results,
                             username=session.get('username'))
    
    except Exception as e:
        print(f"ERROR in lich_su_tracnghiem: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Lỗi khi tải lịch sử: {str(e)}', 'danger')
        return redirect(url_for('tracnghiem'))


@app.route('/tracnghiem/reset/<grade>/<exam_id>')
@login_required

def reset_exam_session(grade, exam_id):
    """
    Reset session để làm lại bài thi
    """
    session_key = f'exam_start_{grade}_{exam_id}'
    
    if session_key in session:
        session.pop(session_key)
        session.modified = True
        flash('Đã reset bài thi. Bạn có thể làm lại từ đầu!', 'success')
    
    return redirect(url_for('lam_bai_tracnghiem', grade=grade, exam_id=exam_id, reset='yes'))


@app.route('/tracnghiem/ket-qua/<grade>/<exam_id>')
@login_required
def ket_qua_tracnghiem(grade, exam_id):
    """
    Hiển thị kết quả bài làm (lấy từ sessionStorage JavaScript)
    """
    try:
        user_id = session.get('user_id')
        

        results_file = 'data/exam_results.json'
        
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                all_results = json.load(f)
        except FileNotFoundError:
            flash('Không tìm thấy kết quả bài làm', 'warning')
            return redirect(url_for('tracnghiem'))
        

        matching_results = [
            r for r in all_results 
            if r.get('user_id') == user_id 
            and r.get('grade') == grade 
            and r.get('exam_id') == exam_id
        ]
        
        if not matching_results:
            flash('Không tìm thấy kết quả bài làm', 'warning')
            return redirect(url_for('tracnghiem'))
        
        result = matching_results[-1]
        
        return render_template('ketqua.html', 
                             result=result,
                             username=session.get('username'))
    
    except Exception as e:
        print(f"ERROR in ket_qua_tracnghiem: {str(e)}")
        flash(f'Lỗi khi hiển thị kết quả: {str(e)}', 'danger')
        return redirect(url_for('tracnghiem'))
        ####################

##############


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'zip', 'rar'}
MAX_FILE_SIZE = 10 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_exam_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXAM_EXTENSIONS

def ensure_directory(path):
    os.makedirs(path, exist_ok=True)

def normalize_answer_token(value):
    if value is None:
        return ''
    token = str(value).strip()
    if not token:
        return ''
    token = token.split('.')[0]
    return token.strip().upper()

def normalize_correct_answers(value):
    if isinstance(value, list):
        tokens = {normalize_answer_token(v) for v in value}
        return {t for t in tokens if t}
    token = normalize_answer_token(value)
    return {token} if token else set()

def format_correct_answer(value):
    if isinstance(value, list):
        return ', '.join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()

def calculate_tl2_score(mistakes_count):
    if mistakes_count <= 0:
        return 1.0
    if mistakes_count == 1:
        return 0.5
    if mistakes_count == 2:
        return 0.25
    if mistakes_count == 3:
        return 0.1
    return 0.0

@app.route('/forum')
@login_required
def forum():
    search_query = request.args.get('search', '').strip()
    filter_type = request.args.get('filter', 'all')
    
    if search_query:
        posts = db.search_forum_posts(search_query)
    elif filter_type == 'my_posts':
        posts = db.get_forum_posts_by_user(session['user_id'])
    else:
        posts = db.get_all_forum_posts()
    
    for post in posts:
        post['created_at_formatted'] = format_datetime(post['created_at'])
        if post.get('updated_at'):
            post['updated_at_formatted'] = format_datetime(post['updated_at'])
    
    return render_template('forum.html', 
                         posts=posts,
                         search_query=search_query,
                         filter_type=filter_type,
                         username=session.get('username'))


@app.route('/forum/post/<post_id>')
@login_required
def forum_post_detail(post_id):
    post = db.get_forum_post_by_id(post_id)
    
    if not post:
        flash('Bài viết không tồn tại', 'danger')
        return redirect(url_for('forum'))
    
    db.increment_post_views(post_id)
    
    comments = db.get_comments_by_post(post_id)
    
    post['created_at_formatted'] = format_datetime(post['created_at'])
    if post.get('updated_at'):
        post['updated_at_formatted'] = format_datetime(post['updated_at'])
    
    for comment in comments:
        comment['created_at_formatted'] = format_datetime(comment['created_at'])
    
    is_author = post['author_id'] == session['user_id']
    
    return render_template('forum_post_detail.html',
                         post=post,
                         comments=comments,
                         is_author=is_author,
                         username=session.get('username'))


@app.route('/forum/create', methods=['GET', 'POST'])
@login_required
def forum_create_post():
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            tags_str = request.form.get('tags', '').strip()
            
            if not title or not content:
                return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ tiêu đề và nội dung'})
            
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()] if tags_str else []
            
            attachments = []
            if 'files' in request.files:
                files = request.files.getlist('files')
                for file in files:
                    if file and file.filename and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                        
                        os.makedirs(FORUM_UPLOAD_FOLDER, exist_ok=True)
                        file_path = os.path.join(FORUM_UPLOAD_FOLDER, unique_filename)
                        file.save(file_path)
                        
                        file_size = os.path.getsize(file_path)
                        
                        file_ext = filename.rsplit('.', 1)[1].lower()
                        file_type = 'image' if file_ext in {'png', 'jpg', 'jpeg', 'gif'} else 'file'
                        
                        attachments.append({
                            'type': file_type,
                            'filename': filename,
                            'path': file_path.replace('\\', '/'),
                            'size': file_size
                        })
            
            user = get_user_by_id(session['user_id'])
            
            post_data = {
                'title': title,
                'content': content,
                'author_id': session['user_id'],
                'author_name': session.get('username', 'Unknown'),
                'author_role': user.get('role', 'student') if user else 'student',
                'attachments': attachments,
                'tags': tags
            }
            
            post_id = db.create_forum_post(post_data)
            
            return jsonify({'success': True, 'post_id': post_id, 'message': 'Tạo bài viết thành công'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('forum_create_post.html', username=session.get('username'))


@app.route('/forum/edit/<post_id>', methods=['GET', 'POST'])
@login_required
def forum_edit_post(post_id):
    post = db.get_forum_post_by_id(post_id)
    
    if not post:
        flash('Bài viết không tồn tại', 'danger')
        return redirect(url_for('forum'))
    
    if post['author_id'] != session['user_id']:
        flash('Bạn không có quyền chỉnh sửa bài viết này', 'danger')
        return redirect(url_for('forum'))
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            tags_str = request.form.get('tags', '').strip()
            
            if not title or not content:
                return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ tiêu đề và nội dung'})
            
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()] if tags_str else []
            
            attachments = post.get('attachments', [])
            
            if 'files' in request.files:
                files = request.files.getlist('files')
                for file in files:
                    if file and file.filename and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                        
                        os.makedirs(FORUM_UPLOAD_FOLDER, exist_ok=True)
                        file_path = os.path.join(FORUM_UPLOAD_FOLDER, unique_filename)
                        file.save(file_path)
                        
                        file_size = os.path.getsize(file_path)
                        file_ext = filename.rsplit('.', 1)[1].lower()
                        file_type = 'image' if file_ext in {'png', 'jpg', 'jpeg', 'gif'} else 'file'
                        
                        attachments.append({
                            'type': file_type,
                            'filename': filename,
                            'path': file_path.replace('\\', '/'),
                            'size': file_size
                        })
            
            post_data = {
                'title': title,
                'content': content,
                'attachments': attachments,
                'tags': tags
            }
            
            success = db.update_forum_post(post_id, post_data)
            
            if success:
                return jsonify({'success': True, 'message': 'Cập nhật bài viết thành công'})
            else:
                return jsonify({'success': False, 'message': 'Cập nhật thất bại'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})
    
    return render_template('forum_create_post.html', 
                         post=post, 
                         edit_mode=True,
                         username=session.get('username'))


@app.route('/forum/delete/<post_id>', methods=['POST'])
@login_required
def forum_delete_post(post_id):
    post = db.get_forum_post_by_id(post_id)
    
    if not post:
        return jsonify({'success': False, 'message': 'Bài viết không tồn tại'})
    
    if post['author_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Bạn không có quyền xóa bài viết này'})
    
    for attachment in post.get('attachments', []):
        try:
            if os.path.exists(attachment['path']):
                os.remove(attachment['path'])
        except:
            pass
    
    db.delete_forum_post(post_id)
    
    return jsonify({'success': True, 'message': 'Xóa bài viết thành công'})


@app.route('/forum/comment/<post_id>', methods=['POST'])
@login_required
def forum_add_comment(post_id):
    try:
        post = db.get_forum_post_by_id(post_id)
        
        if not post:
            return jsonify({'success': False, 'message': 'Bài viết không tồn tại'})
        
        content = request.form.get('content', '').strip()
        
        if not content:
            return jsonify({'success': False, 'message': 'Vui lòng nhập nội dung bình luận'})
        
        attachments = []
        if 'files' in request.files:
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                    
                    os.makedirs(FORUM_UPLOAD_FOLDER, exist_ok=True)
                    file_path = os.path.join(FORUM_UPLOAD_FOLDER, unique_filename)
                    file.save(file_path)
                    
                    file_size = os.path.getsize(file_path)
                    file_ext = filename.rsplit('.', 1)[1].lower()
                    file_type = 'image' if file_ext in {'png', 'jpg', 'jpeg', 'gif'} else 'file'
                    
                    attachments.append({
                        'type': file_type,
                        'filename': filename,
                        'path': file_path.replace('\\', '/'),
                        'size': file_size
                    })
        
        user = get_user_by_id(session['user_id'])
        
        comment_data = {
            'post_id': post_id,
            'author_id': session['user_id'],
            'author_name': session.get('username', 'Unknown'),
            'author_role': user.get('role', 'student') if user else 'student',
            'content': content,
            'attachments': attachments
        }
        
        comment_id = db.add_comment(comment_data)
        
        return jsonify({'success': True, 'comment_id': comment_id, 'message': 'Thêm bình luận thành công'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/forum/delete-comment/<comment_id>', methods=['POST'])
@login_required
def forum_delete_comment(comment_id):
    comments = db._load_json(db.forum_comments_file)
    comment = next((c for c in comments if c['id'] == comment_id), None)
    
    if not comment:
        return jsonify({'success': False, 'message': 'Bình luận không tồn tại'})
    
    if comment['author_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Bạn không có quyền xóa bình luận này'})
    
    for attachment in comment.get('attachments', []):
        try:
            if os.path.exists(attachment['path']):
                os.remove(attachment['path'])
        except:
            pass
    
    db.delete_comment(comment_id)
    
    return jsonify({'success': True, 'message': 'Xóa bình luận thành công'})


def format_datetime(iso_string):
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime('%d/%m/%Y %H:%M')
    except:
        return iso_string
#######
@app.route('/chat')
@login_required
def chat_room():
    messages = db.get_all_chat_messages()
    
    for msg in messages:
        msg['created_at_formatted'] = format_datetime(msg['created_at'])
    
    return render_template('chat_room.html',
                         messages=messages,
                         username=session.get('username'))


@app.route('/api/chat/send', methods=['POST'])
@login_required
def send_chat_message():
    try:
        data = request.get_json()
        content = data.get('content', '').strip()
        reply_to = data.get('reply_to')
        
        if not content:
            return jsonify({'success': False, 'message': 'Nội dung không được để trống'})
        
        user = get_user_by_id(session['user_id'])
        
        message_data = {
            'content': content,
            'author_id': session['user_id'],
            'author_name': session.get('username', 'Unknown'),
            'author_role': user.get('role', 'student') if user else 'student',
            'reply_to': reply_to
        }
        
        message_id = db.add_chat_message(message_data)
        message = db.get_chat_message_by_id(message_id)
        message['created_at_formatted'] = format_datetime(message['created_at'])
        
        return jsonify({
            'success': True,
            'message': message
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/api/chat/messages')
@login_required
def get_chat_messages():
    try:
        last_id = request.args.get('last_id', '')
        messages = db.get_chat_messages_after(last_id)
        
        for msg in messages:
            msg['created_at_formatted'] = format_datetime(msg['created_at'])
        
        return jsonify({
            'success': True,
            'messages': messages
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/api/chat/delete/<message_id>', methods=['POST'])
@login_required
def delete_chat_message(message_id):
    try:
        message = db.get_chat_message_by_id(message_id)
        
        if not message:
            return jsonify({'success': False, 'message': 'Tin nhắn không tồn tại'})
        
        if message['author_id'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Bạn không có quyền xóa tin nhắn này'})
        
        db.delete_chat_message(message_id)
        
        return jsonify({'success': True, 'message': 'Đã xóa tin nhắn'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})

#################
@app.route('/lop10')
@login_required
def lop10():
    return render_template('lop10.html', username=session.get('username'))


@app.route('/lop11')
@login_required
def lop11():
    return render_template('lop11.html', username=session.get('username'))


@app.route('/lop12')
@login_required
def lop12():
    return render_template('lop12.html', username=session.get('username'))


@app.route('/onthi')
@login_required
def onthi():
    return render_template('onthi/onthi_main.html', username=session.get('username'))


@app.route('/onthi/de-tham-khao')
@login_required
def onthi_de_tham_khao():
    return render_template('onthi/de_tham_khao.html', username=session.get('username'))


@app.route('/onthi/tai-lieu-on-luyen')
@login_required
def onthi_tai_lieu():
    return render_template('onthi/tai_lieu_on_luyen.html', username=session.get('username'))


@app.route('/onthi/de-chinh-thuc')
@login_required
def onthi_de_chinh_thuc():
    return render_template('onthi/de_chinh_thuc.html', username=session.get('username'))
################
if __name__ == '__main__':
    ensure_directory('data')
    ensure_directory('static/css')
    ensure_directory('static/js')
    ensure_directory('templates')
    ensure_directory(FORUM_UPLOAD_FOLDER)
    ensure_directory(EXAM_UPLOAD_FOLDER)

    port = int(os.getenv('PORT', os.getenv('FLASK_RUN_PORT', 5001)))
    debug_mode = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'

    app.run(debug=debug_mode, host='0.0.0.0', port=port)
