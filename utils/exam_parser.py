import os
import re
from typing import Dict, List

from docx import Document


class ExamParseError(Exception):
    """Ngoại lệ riêng cho lỗi đọc đề thi."""


QUESTION_PATTERN = re.compile(r'^câu\s*(\d+)\s*[:\.]?\s*(.+)', re.IGNORECASE)
OPTION_PATTERN = re.compile(r'^([A-D])[\.\)]\s*(.+)', re.IGNORECASE)
ANSWER_PATTERN = re.compile(r'^đáp\s*án\s*[:\-]\s*([A-D])', re.IGNORECASE)
EXPLANATION_PATTERN = re.compile(r'^(giải\s*thích)\s*[:\-]\s*(.+)', re.IGNORECASE)

CORRECT_MARKERS = [
    '(đúng)', '(đáp án đúng)', '(correct)', '(true)', '[đúng]'
]
CORRECT_MARKERS_LOWER = [marker.lower() for marker in CORRECT_MARKERS]


def _normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text.replace('\xa0', ' ').strip())


def _strip_correct_markers(text: str) -> str:
    cleaned = text
    for marker in CORRECT_MARKERS:
        cleaned = re.sub(re.escape(marker), '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _paragraph_has_underlined_letter(paragraph, letter: str) -> bool:
    target = letter.upper()
    for run in paragraph.runs:
        run_text = run.text.strip().upper()
        if not run_text:
            continue
        if run_text.startswith(target):
            if getattr(run, 'underline', False):
                return True
            font = getattr(run, 'font', None)
            if font and getattr(font, 'underline', False):
                return True
    return False


def parse_docx_exam(file_path: str, allow_multiple_answers: bool = False) -> List[Dict]:
    """
    Đọc file .docx và chuyển thành danh sách câu hỏi trắc nghiệm.
    Mỗi phần tử có dạng:
    {
        'number': int,
        'question': str,
        'options': {'A': '...', ...},
        'correct_answer': 'A',
        'explanation': str
    }
    """
    if not os.path.exists(file_path):
        raise ExamParseError('File đề thi không tồn tại.')

    try:
        document = Document(file_path)
    except Exception as exc:
        raise ExamParseError(f'Không thể mở file Word: {exc}') from exc

    questions: List[Dict] = []
    current_question: Dict = {}

    def finalize_current():
        if not current_question:
            return
        if not current_question.get('question'):
            raise ExamParseError(f"Câu hỏi số {current_question.get('number', len(questions) + 1)} không có nội dung.")
        options = current_question.get('options', {})
        if len(options) < 2:
            raise ExamParseError(f"Câu {current_question.get('number', len(questions) + 1)} cần ít nhất 2 lựa chọn.")
        answers = current_question.get('correct_answer')
        if not answers:
            raise ExamParseError(f"Không xác định được đáp án đúng cho câu {current_question.get('number', len(questions) + 1)}.")
        if not allow_multiple_answers and isinstance(answers, list) and len(answers) != 1:
            raise ExamParseError(
                f"Câu {current_question.get('number', len(questions) + 1)} được đánh dấu nhiều đáp án đúng nhưng hệ thống đang yêu cầu 1 đáp án."
            )
        if allow_multiple_answers:
            if isinstance(answers, str):
                answers = [answers]
            answers = [ans for ans in answers if ans]
            if not answers:
                raise ExamParseError(
                    f"Câu {current_question.get('number', len(questions) + 1)} không xác định được đáp án đúng."
                )
            current_question['correct_answer'] = answers
        else:
            if isinstance(answers, list):
                # Trường hợp parser lỡ thêm list nhưng chỉ cần 1 đáp án
                answers = answers[0]
            current_question['correct_answer'] = answers
        questions.append(current_question.copy())

    for paragraph in document.paragraphs:
        raw_text = paragraph.text
        normalized = _normalize_text(raw_text)
        if not normalized:
            continue

        answer_line = ANSWER_PATTERN.match(normalized)
        if answer_line and current_question:
            answer_letter = answer_line.group(1).upper()
            if answer_letter not in current_question.get('options', {}):
                raise ExamParseError(f"Đáp án '{answer_letter}' không khớp với lựa chọn của câu {current_question.get('number', len(questions) + 1)}.")
            current_answer = current_question.get('correct_answer')
            if allow_multiple_answers:
                answers_list = list(current_answer or [])
                if answer_letter not in answers_list:
                    answers_list.append(answer_letter)
                current_question['correct_answer'] = answers_list
            else:
                if current_answer and current_answer != answer_letter:
                    raise ExamParseError(f"Câu {current_question.get('number', len(questions) + 1)} bị đánh dấu nhiều đáp án đúng.")
                current_question['correct_answer'] = answer_letter
            continue

        explanation_match = EXPLANATION_PATTERN.match(normalized)
        if explanation_match and current_question:
            current_question['explanation'] = explanation_match.group(2).strip()
            continue

        question_match = QUESTION_PATTERN.match(normalized)
        if question_match:
            # Lưu câu trước nếu có
            finalize_current()
            number = int(question_match.group(1))
            content = question_match.group(2).strip()
            current_question = {
                'number': number,
                'question': content,
                'options': {},
                'correct_answer': None,
                'explanation': ''
            }
            continue

        option_match = OPTION_PATTERN.match(normalized)
        if option_match and current_question:
            letter = option_match.group(1).upper()
            option_text = option_match.group(2).strip()
            option_text_lower = option_text.lower()
            is_marked_correct = any(marker in option_text_lower for marker in CORRECT_MARKERS_LOWER)

            if _paragraph_has_underlined_letter(paragraph, letter):
                is_marked_correct = True

            cleaned_text = _strip_correct_markers(option_text)
            current_question.setdefault('options', {})[letter] = cleaned_text

            if is_marked_correct:
                existing_answer = current_question.get('correct_answer')
                if allow_multiple_answers:
                    answers_list = list(existing_answer or [])
                    if letter not in answers_list:
                        answers_list.append(letter)
                    current_question['correct_answer'] = answers_list
                else:
                    if existing_answer and existing_answer != letter:
                        raise ExamParseError(
                            f"Câu {current_question.get('number', len(questions) + 1)} bị đánh dấu nhiều đáp án đúng."
                        )
                    current_question['correct_answer'] = letter
            continue

        # Nếu đoạn văn không phải câu hỏi/lựa chọn nhưng đang ở trong câu -> nối vào nội dung câu
        if current_question:
            current_question['question'] = f"{current_question['question']} {normalized}".strip()

    finalize_current()

    if not questions:
        raise ExamParseError('Không tìm thấy câu hỏi trắc nghiệm hợp lệ trong file.')

    return questions
