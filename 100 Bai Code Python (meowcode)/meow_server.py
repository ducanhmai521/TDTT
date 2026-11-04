import io
import json
import os
import subprocess
import sys
from flask import Flask, jsonify, render_template_string, request, send_file
import PyPDF2
import re

app = Flask(__name__)

SOLUTIONS_FILE = "meow_solutions.json"
DATA_FILE = "meow_problems.json"
PDF_FILE = "100 Bai Code Python.pdf"

def extract_problems_from_pdf():
    """Trích xuất đề bài và test cases từ PDF"""
    pdf_path = os.path.join(os.path.dirname(__file__), PDF_FILE)
    if not os.path.exists(pdf_path):
        print(f"⚠️  Không tìm thấy file PDF: {PDF_FILE}")
        return []
    
    # Fallback descriptions cho các bài có công thức phức tạp
    FALLBACK_DESCRIPTIONS = {
        "0008": "Viết chương trình tính bán kính R của đường tròn ngoại tiếp tam giác có ba cạnh a, b, c theo công thức R = (a*b*c)/(4*S), với S là diện tích tam giác.",
        "0021": "Tính tiền taxi theo quy tắc: 0.8km đầu: 15000đ, từ 0.8km đến 20km: 12500đ/km, trên 20km: 10000đ/km.",
        # Thêm các bài khác nếu cần
    }
    
    try:
        problems = []
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            full_text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                # Fix các ký hiệu đặc biệt thường gặp (safe replacements)
                try:
                    page_text = page_text.replace('×', '*')  # Multiplication
                    page_text = page_text.replace('÷', '/')  # Division
                    page_text = page_text.replace('≤', '<=')  # Less than or equal
                    page_text = page_text.replace('≥', '>=')  # Greater than or equal
                    page_text = page_text.replace('≠', '!=')  # Not equal
                except:
                    pass  # Nếu có lỗi encoding thì bỏ qua
                full_text += page_text + "\n"
        
        # Pattern để tìm từng bài (ID - Title)
        # Format: 0001 - Tính chu vi và diện tích hình vuông
        problem_pattern = r'(\d{4})\s*-\s*([^\n]+)\n'
        matches = list(re.finditer(problem_pattern, full_text))
        
        for idx, match in enumerate(matches):
            prob_id = match.group(1)
            title = match.group(2).strip()
            
            # Lấy toàn bộ nội dung của bài này (từ match hiện tại đến match tiếp theo)
            start_pos = match.end()
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
            content = full_text[start_pos:end_pos]
            
            # Trích xuất phần "Đề bài"
            desc_match = re.search(r'Đề bài\s*\n(.*?)(?=Dữ liệu vào|$)', content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else title
            
            # Format description để dễ đọc hơn
            # Thêm line break trước các bullet points
            description = re.sub(r'([.!?])\s*(\d+\.|[-•])', r'\1\n\n\2', description)
            # Giữ line breaks cho list items
            description = re.sub(r'\n\s*\n\s*\n+', '\n\n', description)  # Normalize multiple newlines
            # Không làm sạch quá nhiều whitespace
            description = re.sub(r'[ \t]+', ' ', description)  # Chỉ normalize spaces/tabs trong dòng
            
            # Kiểm tra nếu description quá ngắn hoặc có dấu hiệu bị cắt công thức
            if (len(description) < 20 or 
                description.endswith('=') or 
                'R=' in description or
                'theo công thức' in description and '=' in description and len(description.split('=')[1].strip()) < 5):
                # Dùng fallback nếu có
                if prob_id in FALLBACK_DESCRIPTIONS:
                    description = FALLBACK_DESCRIPTIONS[prob_id]
                    print(f"📝 Bài {prob_id}: Dùng mô tả fallback (công thức phức tạp)")
            
            # Trích xuất Input/Output examples
            tests = []
            input_pattern = r'Input\s*#(\d+)\s*\n(.*?)(?=Output|$)'
            output_pattern = r'Output\s*#(\d+)\s*\n(.*?)(?=Input|(?:\d{4}\s*-)|$)'
            
            inputs = list(re.finditer(input_pattern, content, re.DOTALL))
            outputs = list(re.finditer(output_pattern, content, re.DOTALL))
            
            # Ghép Input và Output tương ứng
            for inp_match in inputs:
                inp_num = inp_match.group(1)
                inp_text = inp_match.group(2).strip()
                
                # Tìm output tương ứng
                for out_match in outputs:
                    out_num = out_match.group(1)
                    if inp_num == out_num:
                        out_text = out_match.group(2).strip()
                        tests.append({
                            "input": inp_text,
                            "output": out_text
                        })
                        break
            
            # Nếu không có test case thì skip bài này
            if not tests:
                print(f"⚠️  Bài {prob_id} không có test case")
                continue
            
            problems.append({
                "id": prob_id,
                "title": title,
                "desc": f"{description}",
                "template": f"# Bài {prob_id}: {title}\n",
                "tests": tests
            })
        
        print(f"✅ Đã trích xuất {len(problems)} bài từ PDF (có đề bài đầy đủ và test cases)")
        return problems
    
    except Exception as e:
        print(f"❌ Lỗi khi đọc PDF: {e}")
        import traceback
        traceback.print_exc()
        return []

def init_problems():
    """Khởi tạo danh sách bài tập từ PDF hoặc file JSON cache"""
    if os.path.exists(DATA_FILE):
        print(f"📚 Đang load từ cache: {DATA_FILE}")
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    
    print(f"📖 Đang đọc PDF: {PDF_FILE}")
    problems = extract_problems_from_pdf()
    
    if problems:
        # Lưu vào cache
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(problems, f, ensure_ascii=False, indent=2)
        print(f"💾 Đã lưu cache vào: {DATA_FILE}")
    else:
        print(f"⚠️  Không extract được bài tập từ PDF!")
    
    return problems

HTML = r"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MeowCode IDE 🐾 100 Bài Python Cho Sen</title>
    <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&family=Fira+Code:wght@400;500;600;700&display=swap" rel="stylesheet">
    
    <!-- CodeMirror Core & Themes -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/codemirror.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/theme/neo.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/theme/dracula.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/addon/dialog/dialog.min.css">

    <!-- CodeMirror Scripts & Addons -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/codemirror.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/mode/python/python.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/addon/edit/closebrackets.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/addon/edit/matchbrackets.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/addon/selection/active-line.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/addon/dialog/dialog.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/addon/search/searchcursor.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/addon/search/search.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.13/addon/comment/comment.min.js"></script>

    <style>
        :root {
            --pink-bg: #fff5f8;
            --pink-card: #ffffff;
            --pink-sidebar: #fff0f5;
            --pink-border: #ffccd9;
            --pink-hot: #ff5e97;
            --pink-hot-hover: #ff3b80;
            --pink-light: #ff8fb7;
            --pink-soft: #ffafcc;
            --pink-subtle: #fff0f6;
            --cat-fur: #ff9eb5;
            --cat-fur-dark: #ff7597;
            --text-dark: #3e3137;
            --text-muted: #7d6b75;
            --success: #10b981;
            --fail: #f43f5e;
            --spring: cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Nunito', sans-serif;
            background: linear-gradient(135deg, #fff5f8 0%, #ffedf3 50%, #fff0f6 100%);
            color: var(--text-dark);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            user-select: none;
        }

        /* HEADER */
        header {
            background: rgba(255, 255, 255, 0.94);
            backdrop-filter: blur(10px);
            padding: 6px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px dashed var(--pink-border);
            box-shadow: 0 2px 10px rgba(255, 94, 151, 0.08);
            z-index: 100;
            white-space: nowrap;
            overflow-x: auto;
            overflow-y: hidden;
            gap: 12px;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-shrink: 0;
        }
        .logo-box {
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: default;
        }
        /* ============ HOA ANH ĐÀO BAY ============ */
        .sakura-petal {
            position: fixed;
            width: 10px;
            height: 10px;
            background: radial-gradient(ellipse at center, #ffb7d5 0%, #ffc9e0 50%, transparent 80%);
            border-radius: 80% 0 55% 50% / 55% 0 80% 50%;
            pointer-events: none;
            z-index: 99;
            opacity: 0;
            animation: sakuraFall linear forwards;
        }
        @keyframes sakuraFall {
            0% {
                opacity: 0;
                transform: translateY(-20px) translateX(0) rotateZ(0deg);
            }
            10% {
                opacity: 0.8;
            }
            90% {
                opacity: 0.6;
            }
            100% {
                opacity: 0;
                transform: translateY(100vh) translateX(var(--drift, 100px)) rotateZ(var(--rotate, 720deg));
            }
        }

        /* Logo wrap có hiệu ứng hover sinh hoa */
        .logo-box {
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: default;
            position: relative;
        }
        .logo-box:hover {
            animation: logoGlow 0.8s ease-in-out;
        }
        @keyframes logoGlow {
            0%, 100% { filter: drop-shadow(0 0 0 transparent); }
            50% { filter: drop-shadow(0 0 8px rgba(255, 94, 151, 0.4)); }
        }

        .logo-title {
            font-size: 1.35rem;
            font-weight: 900;
            background: linear-gradient(135deg, var(--pink-hot), #ff8fb7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 6px;
            letter-spacing: -0.5px;
        }
        .logo-sub {
            font-size: 0.72rem;
            font-weight: 700;
            color: var(--text-muted);
            background: var(--pink-subtle);
            padding: 2px 8px;
            border-radius: 10px;
            border: 1px solid var(--pink-border);
        }

        /* MASCOT CAT IN HEADER */
        .mascot-cat {
            position: relative;
            width: 32px;
            height: 28px;
            cursor: pointer;
            transition: transform 0.2s var(--spring);
        }
        .mascot-cat:hover {
            transform: scale(1.15) rotate(5deg);
        }
        .mcat-head {
            width: 28px;
            height: 24px;
            background: linear-gradient(180deg, #ff9eb5, #ff7597);
            border-radius: 50%;
            position: absolute;
            bottom: 0;
            left: 2px;
        }
        .mcat-ear {
            position: absolute;
            width: 0;
            height: 0;
            border-left: 4.5px solid transparent;
            border-right: 4.5px solid transparent;
            border-bottom: 9px solid #ff7597;
            top: -6px;
            animation: mascotEarWiggle 5s infinite;
        }
        .mcat-ear.l { left: 1px; transform: rotate(-15deg); }
        .mcat-ear.r { right: 1px; transform: rotate(15deg); }
        @keyframes mascotEarWiggle {
            0%, 90%, 100% { transform: rotate(0); }
            92% { transform: rotate(-12deg); }
            94% { transform: rotate(12deg); }
        }
        .mcat-eye {
            position: absolute;
            width: 4px;
            height: 4px;
            background: #3e3137;
            border-radius: 50%;
            top: 9px;
            animation: mascotBlink 4s infinite;
        }
        .mcat-eye.l { left: 6px; }
        .mcat-eye.r { right: 6px; }
        @keyframes mascotBlink {
            0%, 96%, 100% { transform: scaleY(1); }
            98% { transform: scaleY(0.1); }
        }
        .mcat-nose {
            position: absolute;
            width: 3px;
            height: 2px;
            background: #ff3b80;
            border-radius: 50%;
            top: 14px;
            left: 50%;
            transform: translateX(-50%);
        }
        .mcat-blush {
            position: absolute;
            width: 4px;
            height: 2.5px;
            background: rgba(255, 94, 151, 0.5);
            border-radius: 50%;
            top: 13px;
        }
        .mcat-blush.l { left: 3px; }
        .mcat-blush.r { right: 3px; }

        /* HEADER ACTIONS */
        .header-actions {
            display: flex;
            gap: 8px;
            align-items: center;
            flex-shrink: 0;
        }
        .progress-box {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 800;
            font-size: 0.88rem;
            background: rgba(255, 255, 255, 0.9);
            padding: 4px 12px;
            border-radius: 20px;
            border: 1px solid var(--pink-border);
        }
        .progress-bar-bg {
            width: 140px;
            height: 12px;
            background: #ffe9f0;
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid var(--pink-border);
            position: relative;
        }
        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #ff9eb5, #ff5e97, #ff3b80);
            width: 0%;
            transition: width 0.4s var(--spring);
            position: relative;
        }
        .progress-bar-fill::after {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.55), transparent);
            animation: barShimmer 2s infinite linear;
            background-size: 200% 100%;
        }
        @keyframes barShimmer {
            0% { background-position: -150px 0; }
            100% { background-position: 150px 0; }
        }

        .btn {
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, var(--pink-light), var(--pink-hot));
            color: white;
            border: none;
            padding: 7px 15px;
            border-radius: 18px;
            cursor: pointer;
            font-family: 'Nunito', sans-serif;
            font-weight: 700;
            font-size: 0.85rem;
            box-shadow: 0 3px 10px rgba(255, 94, 151, 0.25);
            transition: transform 0.2s var(--spring), box-shadow 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .btn:hover {
            transform: translateY(-2px) scale(1.02);
            box-shadow: 0 6px 16px rgba(255, 94, 151, 0.35);
        }
        .btn:active {
            transform: translateY(1px) scale(0.97);
        }
        .btn-outline {
            background: white;
            color: var(--pink-hot);
            border: 2px solid var(--pink-hot);
            box-shadow: none;
        }
        .btn-outline:hover {
            background: #fff0f5;
        }

        /* MAIN LAYOUT */
        .main-container {
            display: flex;
            flex: 1;
            overflow: hidden;
            position: relative;
        }
        .sidebar {
            width: 320px;
            background: rgba(255, 240, 245, 0.88);
            backdrop-filter: blur(8px);
            border-right: 2px dashed var(--pink-border);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
            position: relative;
        }
        .sidebar-header {
            padding: 10px 12px;
            background: rgba(255, 255, 255, 0.95);
            border-bottom: 1px solid var(--pink-border);
            display: flex;
            flex-direction: column;
            gap: 8px;
            position: relative;
        }
        .search-row {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .search-wrapper {
            position: relative;
            flex: 1;
            display: flex;
            align-items: center;
        }
        .search-input {
            width: 100%;
            border: 2px solid var(--pink-border);
            padding: 7px 30px 7px 12px;
            border-radius: 16px;
            outline: none;
            font-family: 'Nunito', sans-serif;
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-dark);
            background: #fffcfd;
            transition: all 0.25s var(--spring);
        }
        .search-input:focus {
            border-color: var(--pink-hot);
            box-shadow: 0 0 0 3px rgba(255, 94, 151, 0.25), 0 4px 12px rgba(255, 94, 151, 0.15);
            background: #ffffff;
        }
        .search-paw-decor {
            position: absolute;
            right: 10px;
            pointer-events: none;
            opacity: 0.5;
            font-size: 0.85rem;
            transition: opacity 0.2s, transform 0.2s;
        }
        .search-input:focus + .search-paw-decor {
            opacity: 1;
            transform: scale(1.2) rotate(12deg);
        }

        /* SLEEPING CAT WIDGET IN SIDEBAR TOP */
        .sleeping-cat-widget {
            position: relative;
            width: 48px;
            height: 34px;
            display: flex;
            align-items: flex-end;
            justify-content: center;
            cursor: pointer;
            user-select: none;
            flex-shrink: 0;
        }
        .zzz-stream {
            position: absolute;
            top: -4px;
            right: 4px;
            display: flex;
            flex-direction: column;
            pointer-events: none;
        }
        .zzz {
            font-family: 'Nunito', sans-serif;
            font-weight: 800;
            color: var(--pink-hot);
            opacity: 0;
            position: absolute;
        }
        .z1 { font-size: 8px; animation: floatZ 2.4s infinite ease-out 0s; }
        .z2 { font-size: 10px; animation: floatZ 2.4s infinite ease-out 0.8s; }
        .z3 { font-size: 12px; animation: floatZ 2.4s infinite ease-out 1.6s; }
        @keyframes floatZ {
            0% { opacity: 0; transform: translate(0, 0) scale(0.6); }
            30% { opacity: 0.9; }
            80% { opacity: 0.8; }
            100% { opacity: 0; transform: translate(10px, -18px) scale(1.1); }
        }
        .sleeping-cat {
            position: relative;
            width: 42px;
            height: 28px;
            animation: scatBreathe 3s ease-in-out infinite;
            transform-origin: bottom center;
        }
        @keyframes scatBreathe {
            0%, 100% { transform: scale(1, 1); }
            50% { transform: scale(1.05, 0.95); }
        }
        .scat-body {
            position: absolute;
            width: 36px;
            height: 20px;
            background: linear-gradient(135deg, #ffafcc, #ff8fb7);
            border-radius: 50% 50% 45% 45%;
            bottom: 0;
            left: 2px;
        }
        .scat-fur-marking {
            position: absolute;
            width: 12px;
            height: 8px;
            background: rgba(255, 255, 255, 0.45);
            border-radius: 50%;
            bottom: 2px;
            left: 10px;
        }
        .scat-head {
            position: absolute;
            width: 20px;
            height: 18px;
            background: #ff8fb7;
            border-radius: 50%;
            bottom: 2px;
            right: 0;
            z-index: 2;
        }
        .scat-ear {
            position: absolute;
            width: 0;
            height: 0;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-bottom: 6px solid #ff7597;
            top: -4px;
        }
        .scat-ear-l { left: 1px; transform: rotate(-15deg); }
        .scat-ear-r { right: 1px; transform: rotate(15deg); }
        .scat-eye {
            position: absolute;
            width: 5px;
            height: 2.5px;
            border-bottom: 1.5px solid #4a3e44;
            border-radius: 0 0 50% 50%;
            top: 6px;
            transition: all 0.2s;
        }
        .scat-eye-l { left: 3px; }
        .scat-eye-r { right: 3px; }
        .sleeping-cat.awake .scat-eye {
            height: 4px;
            background: #4a3e44;
            border-radius: 50%;
            border-bottom: none;
        }
        .sleeping-cat.awake {
            animation: wakeJump 0.4s var(--spring);
        }
        @keyframes wakeJump {
            0% { transform: translateY(0) scale(1); }
            50% { transform: translateY(-7px) scale(1.1); }
            100% { transform: translateY(0) scale(1); }
        }
        .scat-nose {
            position: absolute;
            width: 2.5px;
            height: 1.5px;
            background: var(--pink-hot);
            border-radius: 50%;
            bottom: 4px;
            left: 50%;
            transform: translateX(-50%);
        }
        .scat-tail {
            position: absolute;
            width: 14px;
            height: 5px;
            background: #ff8fb7;
            border-radius: 8px;
            bottom: 2px;
            left: -3px;
            transform-origin: right center;
            transform: rotate(20deg);
        }

        /* FILTER PILLS */
        .filter-tabs {
            display: flex;
            gap: 4px;
        }
        .filter-pill {
            flex: 1;
            text-align: center;
            padding: 4px 0;
            font-size: 0.72rem;
            font-weight: 700;
            background: #fff0f5;
            color: var(--text-muted);
            border-radius: 10px;
            cursor: pointer;
            border: 1px solid transparent;
            transition: all 0.2s var(--spring);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
        }
        .filter-pill:hover {
            background: #ffe4ec;
            color: var(--pink-hot);
        }
        .filter-pill.active {
            background: var(--pink-hot);
            color: white;
            box-shadow: 0 2px 6px rgba(255, 94, 151, 0.3);
        }
        .filter-pill .icon-svg {
            display: inline-flex;
        }

        /* PROBLEM LIST */
        .problem-list {
            flex: 1;
            overflow-y: auto;
            list-style: none;
            padding: 8px;
            scroll-behavior: smooth;
        }
        .problem-item {
            padding: 8px 12px;
            border-radius: 12px;
            margin-bottom: 5px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.95);
            border: 1.5px solid transparent;
            transition: transform 0.2s var(--spring), box-shadow 0.2s, border-color 0.2s;
            user-select: none;
        }
        .problem-item:hover {
            border-color: var(--pink-hot);
            transform: translateX(4px) scale(1.01);
            box-shadow: 0 3px 10px rgba(255, 94, 151, 0.15);
        }
        .problem-item:active {
            transform: scale(0.97);
        }
        .problem-item.active {
            background: linear-gradient(135deg, var(--pink-light), var(--pink-hot));
            color: white;
            font-weight: 700;
            box-shadow: 0 4px 14px rgba(255, 94, 151, 0.35);
            border-color: transparent;
        }
        .problem-item-left {
            display: flex;
            align-items: center;
            gap: 8px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .p-num {
            font-weight: 800;
            font-size: 0.82rem;
            opacity: 0.85;
        }
        .p-name {
            font-size: 0.85rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 170px;
        }
        .problem-item-right {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-shrink: 0;
        }

        /* PURE CSS CAT FACE ICON FOR PROBLEMS */
        .cat-face-icon {
            display: inline-block;
            position: relative;
            width: 13px;
            height: 11px;
            border-radius: 50% 50% 45% 45%;
        }
        .cat-face-icon::before, .cat-face-icon::after {
            content: '';
            position: absolute;
            top: -4px;
            width: 0;
            height: 0;
            border-left: 2px solid transparent;
            border-right: 2px solid transparent;
        }
        .cat-face-icon::before { left: 0px; transform: rotate(-15deg); }
        .cat-face-icon::after { right: 0px; transform: rotate(15deg); }
        .cat-face-icon.pass { background: #10b981; }
        .cat-face-icon.pass::before, .cat-face-icon.pass::after { border-bottom: 4.5px solid #059669; }
        .cat-face-icon.fail { background: #f43f5e; }
        .cat-face-icon.fail::before, .cat-face-icon.fail::after { border-bottom: 4.5px solid #e11d48; }
        .cat-face-icon.unsolved { background: #cbd5e1; }
        .cat-face-icon.unsolved::before, .cat-face-icon.unsolved::after { border-bottom: 4.5px solid #94a3b8; }

        .badge {
            font-size: 0.72rem;
            padding: 2px 7px;
            border-radius: 10px;
            font-weight: 700;
        }
        .badge.passed { background: #d1fae5; color: #065f46; }
        .badge.failed { background: #ffe4e6; color: #9f1239; }
        .badge.unsolved { background: #f1f5f9; color: #64748b; }
        .problem-item.active .badge {
            background: rgba(255, 255, 255, 0.25);
            color: white;
        }

        /* WORKSPACE */
        .workspace {
            flex: 1;
            display: flex;
            flex-direction: column;
            padding: 10px 14px;
            gap: 10px;
            overflow: hidden;
        }
        .panel {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            border: 1px solid var(--pink-border);
            box-shadow: 0 4px 18px rgba(255, 182, 193, 0.16);
        }
        .problem-detail {
            padding: 12px 18px;
            transition: transform 0.35s var(--spring);
        }
        .panel-bounce {
            animation: slideBounceIn 0.4s var(--spring);
        }
        @keyframes slideBounceIn {
            0% { opacity: 0; transform: translateY(-8px) scale(0.98); }
            70% { transform: translateY(2px) scale(1.005); }
            100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        .problem-detail h2 {
            color: var(--pink-hot);
            font-size: 1.15rem;
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 800;
        }
        .problem-detail p {
            font-size: 0.9rem;
            margin-top: 8px;
            color: #555;
            line-height: 1.6;
            white-space: pre-wrap; /* Cho phép xuống dòng tự nhiên */
            word-wrap: break-word;
        }
        body.dark-mode .problem-detail p {
            color: #d4bec9;
        }

        /* EDITOR WRAPPER & COMPANION CAT */
        .editor-wrapper {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
            border: 2px solid var(--pink-border);
            border-radius: 16px;
            background: white;
            box-shadow: 0 6px 20px rgba(255, 94, 151, 0.1);
        }
        .editor-header {
            padding: 6px 14px;
            background: #fffafd;
            border-bottom: 1px solid var(--pink-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.82rem;
            color: var(--text-muted);
            position: relative;
            z-index: 5;
        }
        .editor-header-left {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 700;
            color: var(--text-dark);
        }
        .tab-file-pill {
            background: #ffeef4;
            border: 1px solid var(--pink-border);
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.78rem;
            color: var(--pink-hot);
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .tab-file-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #10b981;
        }
        .editor-controls {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .editor-btn {
            background: white;
            border: 1px solid var(--pink-border);
            color: var(--text-dark);
            padding: 3px 8px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.75rem;
            font-weight: 700;
            transition: all 0.2s var(--spring);
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .editor-btn:hover {
            border-color: var(--pink-hot);
            color: var(--pink-hot);
            transform: translateY(-1px);
        }
        .font-size-control {
            display: flex;
            align-items: center;
            border: 1px solid var(--pink-border);
            border-radius: 8px;
            background: white;
            overflow: hidden;
        }
        .font-btn {
            border: none;
            background: none;
            padding: 2px 7px;
            cursor: pointer;
            font-weight: 800;
            font-size: 0.75rem;
            color: var(--pink-hot);
        }
        .font-btn:hover {
            background: #ffeef4;
        }
        .font-val {
            padding: 0 4px;
            font-size: 0.72rem;
            font-weight: 700;
            color: var(--text-dark);
        }

        /* COMPANION CAT SITTING ON EDITOR */
        .editor-cat-companion {
            position: absolute;
            top: -22px;
            right: 48px;
            width: 44px;
            height: 26px;
            z-index: 10;
            pointer-events: auto;
            cursor: pointer;
            user-select: none;
        }
        .ecat-head {
            position: absolute;
            width: 30px;
            height: 22px;
            background: linear-gradient(180deg, #ff9eb5, #ff8fb7);
            border-radius: 50% 50% 45% 45%;
            top: 0;
            left: 7px;
            box-shadow: 0 2px 6px rgba(255, 94, 151, 0.25);
            transition: transform 0.2s;
        }
        .ecat-ear {
            position: absolute;
            width: 0;
            height: 0;
            border-left: 4.5px solid transparent;
            border-right: 4.5px solid transparent;
            border-bottom: 8px solid #ff7597;
            top: -6px;
        }
        .ecat-ear-l { left: 2px; transform: rotate(-15deg); }
        .ecat-ear-r { right: 2px; transform: rotate(15deg); }
        .ecat-ear-inner {
            position: absolute;
            width: 0;
            height: 0;
            border-left: 2px solid transparent;
            border-right: 2px solid transparent;
            border-bottom: 4px solid #ffeef4;
            top: 2px;
            left: -2px;
        }
        .ecat-eye {
            position: absolute;
            width: 4.5px;
            height: 5px;
            background: #3d3137;
            border-radius: 50%;
            top: 6px;
        }
        .ecat-eye-l { left: 6px; }
        .ecat-eye-r { right: 6px; }
        .ecat-pupil {
            position: absolute;
            width: 1.5px;
            height: 1.5px;
            background: white;
            border-radius: 50%;
            top: 1px;
            left: 1px;
        }
        .ecat-nose {
            position: absolute;
            width: 3px;
            height: 2px;
            background: var(--pink-hot);
            border-radius: 50%;
            top: 12px;
            left: 50%;
            transform: translateX(-50%);
        }
        .ecat-blush {
            position: absolute;
            width: 4px;
            height: 2.5px;
            background: rgba(255, 94, 151, 0.5);
            border-radius: 50%;
            top: 11px;
        }
        .ecat-blush-l { left: 3px; }
        .ecat-blush-r { right: 3px; }
        .ecat-paws {
            position: absolute;
            bottom: -3px;
            left: 9px;
            width: 26px;
            display: flex;
            justify-content: space-between;
            z-index: 12;
        }
        .ecat-paw {
            width: 7px;
            height: 6px;
            background: #ffffff;
            border: 1.5px solid var(--pink-border);
            border-radius: 50% 50% 40% 40%;
            transition: transform 0.15s;
        }
        .ecat-tail {
            position: absolute;
            width: 16px;
            height: 4.5px;
            background: var(--cat-fur);
            border-radius: 8px;
            top: 8px;
            right: -8px;
            transform-origin: left center;
            animation: ecatTailIdle 2s ease-in-out infinite;
            z-index: -1;
        }
        @keyframes ecatTailIdle {
            0%, 100% { transform: rotate(-15deg); }
            50% { transform: rotate(25deg); }
        }
        .editor-cat-companion.typing .ecat-head {
            transform: translateY(-2px);
        }
        .editor-cat-companion.typing .ecat-tail {
            animation: ecatTailFast 0.25s ease-in-out infinite;
        }
        @keyframes ecatTailFast {
            0%, 100% { transform: rotate(-35deg); }
            50% { transform: rotate(35deg); }
        }
        .editor-cat-companion.typing .ecat-paw-l {
            animation: pawTapL 0.25s infinite;
        }
        .editor-cat-companion.typing .ecat-paw-r {
            animation: pawTapR 0.25s infinite;
        }
        @keyframes pawTapL {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-4px); }
        }
        @keyframes pawTapR {
            0%, 100% { transform: translateY(-4px); }
            50% { transform: translateY(0); }
        }

        .CodeMirror {
            flex: 1;
            height: 100%;
            font-family: 'Fira Code', 'Courier New', monospace;
            font-size: 15px;
            line-height: 1.5;
        }
        .CodeMirror-gutters {
            background: #fffafc;
            border-right: 1px solid var(--pink-border);
        }
        .CodeMirror-activeline-background {
            background: rgba(255, 94, 151, 0.08) !important;
        }

        /* RESULTS PANEL */
        .results-panel {
            height: 140px;
            transition: height 0.35s var(--spring);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .results-panel.expanded { height: 350px; }
        .results-header {
            padding: 8px 16px;
            background: #fffafc;
            border-bottom: 1px solid var(--pink-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: 800;
            font-size: 0.9rem;
        }
        .results-body {
            flex: 1;
            overflow-y: auto;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .test-card {
            border-radius: 12px;
            padding: 10px 14px;
            background: #fffafc;
            border-left: 6px solid #ccc;
            border-top: 1px solid var(--pink-border);
            border-right: 1px solid var(--pink-border);
            border-bottom: 1px solid var(--pink-border);
            animation: testCardSlide 0.3s var(--spring);
            position: relative;
            transition: transform 0.2s var(--spring), box-shadow 0.2s;
        }
        .test-card:hover {
            transform: translateX(3px);
            box-shadow: 0 4px 12px rgba(255, 94, 151, 0.15);
        }
        /* Thêm nhiều biểu tượng mèo bay quanh test card */
        .test-card::after {
            content: '🐾 meow~';
            position: absolute;
            right: 8px;
            bottom: 8px;
            font-size: 0.7rem;
            opacity: 0;
            color: var(--pink-hot);
            font-weight: 700;
            transition: opacity 0.3s;
            pointer-events: none;
        }
        .test-card:hover::after {
            opacity: 0.6;
        }
        @keyframes testCardSlide {
            0% { opacity: 0; transform: translateY(6px); }
            100% { opacity: 1; transform: translateY(0); }
        }
        .test-card.pass { border-left-color: var(--success); }
        .test-card.fail { border-left-color: var(--fail); }
        .test-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1.2fr;
            gap: 10px;
            margin-top: 6px;
        }
        /* ===== Results Summary Bar ===== */
        .results-summary {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 14px;
            background: linear-gradient(135deg, #fff0f8, #f0f8ff);
            border-radius: 12px;
            border: 1.5px solid var(--pink-border);
            margin-bottom: 10px;
            animation: testCardSlide 0.3s var(--spring);
            position: relative;
            overflow: hidden;
        }
        body.dark-mode .results-summary {
            background: linear-gradient(135deg, #1e1030, #101e30);
            border-color: #3a2244;
        }
        /* Nhiều mèo mini bay qua lại trong summary bar */
        .results-summary::before {
            content: '🐱';
            position: absolute;
            left: -30px;
            animation: summaryMeowFloat 8s linear infinite;
            font-size: 1.2rem;
            opacity: 0.3;
            pointer-events: none;
        }
        @keyframes summaryMeowFloat {
            0% { left: -30px; transform: translateY(0); }
            50% { transform: translateY(-8px); }
            100% { left: calc(100% + 30px); transform: translateY(0); }
        }
        .results-summary-cat {
            display: inline-block;
            width: 32px; height: 28px;
            position: relative;
            flex-shrink: 0;
            animation: summaryMeowBounce 1.5s ease-in-out infinite;
        }
        @keyframes summaryMeowBounce {
            0%, 100% { transform: translateY(0) rotate(-3deg); }
            50% { transform: translateY(-5px) rotate(3deg); }
        }
        .results-summary-cat::before {
            content: '';
            position: absolute;
            bottom: 0; left: 50%;
            transform: translateX(-50%);
            width: 24px; height: 20px;
            border-radius: 50% 50% 45% 45%;
        }
        .results-summary-cat.pass::before { background: #06d6a0; }
        .results-summary-cat.fail::before { background: #ff5e97; }
        .results-summary-cat::after {
            content: '';
            position: absolute;
            top: 0; left: 50%;
            transform: translateX(-50%);
            width: 20px; height: 15px;
            border-radius: 40% 40% 50% 50%;
        }
        .results-summary-cat.pass::after { background: #05bf8e; }
        .results-summary-cat.fail::after { background: #e54585; }
        .results-summary-text { 
            font-size: 0.88rem; 
            color: var(--text-dark);
            font-weight: 700;
        }
        .results-summary-badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 700;
            margin-left: 6px;
        }
        .results-summary-badge.pass { background: #d1fae5; color: #065f46; }
        .results-summary-badge.fail { background: #ffe4e6; color: #9f1239; }
        body.dark-mode .results-summary-badge.pass { background: #064e3b; color: #6ee7b7; }
        body.dark-mode .results-summary-badge.fail { background: #4c0519; color: #fca5a5; }

        /* ===== Test Card Cat Face ===== */
        .tc-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
            position: relative;
        }
        /* Thêm mèo mini bay xung quanh card */
        .test-card:hover .tc-header::after {
            content: '🐾';
            position: absolute;
            right: -25px;
            animation: pawWiggle 0.6s ease-in-out infinite;
            font-size: 1rem;
        }
        @keyframes pawWiggle {
            0%, 100% { transform: rotate(-15deg) translateY(0); }
            50% { transform: rotate(15deg) translateY(-3px); }
        }
        .tc-label { 
            font-size: 0.88rem;
            font-weight: 700;
        }
        .tc-label.pass { color: var(--success); }
        .tc-label.fail { color: var(--fail); }
        .tc-cat-face {
            display: inline-block;
            width: 28px; height: 24px;
            position: relative;
            flex-shrink: 0;
            animation: tcCatBob 2s ease-in-out infinite;
        }
        @keyframes tcCatBob {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-2px); }
        }
        /* cat body */
        .tc-cat-face::before {
            content: '';
            position: absolute;
            bottom: 0; left: 50%;
            transform: translateX(-50%);
            width: 22px; height: 18px;
            border-radius: 40% 40% 48% 48%;
        }
        .tc-cat-face.pass::before { background: #06d6a0; }
        .tc-cat-face.fail::before { background: #ff5e97; }
        /* ears */
        .tc-ear {
            position: absolute;
            top: 0;
            width: 0; height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-bottom: 9px solid;
        }
        .tc-cat-face.pass .tc-ear { border-bottom-color: #05bf8e; }
        .tc-cat-face.fail .tc-ear { border-bottom-color: #e54585; }
        .tc-ear.l { left: 2px; transform: rotate(-10deg); }
        .tc-ear.r { right: 2px; transform: rotate(10deg); }
        /* eyes */
        .tc-eye {
            position: absolute;
            width: 4px; height: 4px;
            background: #222;
            border-radius: 50%;
            top: 10px;
        }
        .tc-eye.l { left: 5px; }
        .tc-eye.r { right: 5px; }
        .tc-eye.sad { 
            border-radius: 0;
            clip-path: polygon(0 100%, 50% 0, 100% 100%);
            background: #222;
        }
        /* nose */
        .tc-nose {
            position: absolute;
            bottom: 6px; left: 50%;
            transform: translateX(-50%);
            width: 4px; height: 3px;
            background: #ff88b8;
            border-radius: 50%;
        }
        /* mouth */
        .tc-mouth {
            position: absolute;
            bottom: 2px; left: 50%;
            transform: translateX(-50%);
            width: 10px; height: 5px;
            border: 2px solid #222;
            border-top: none;
        }
        .tc-mouth.pass { border-radius: 0 0 6px 6px; }
        .tc-mouth.fail { 
            border-radius: 6px 6px 0 0;
            border-top: 2px solid #222;
            border-bottom: none;
            bottom: 4px;
        }

        .test-col-title {
            font-size: 0.78rem;
            font-weight: 700;
            color: #888;
            margin-bottom: 3px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        /* Thêm hiệu ứng kawaii cho column title */
        .test-col-title::before {
            content: '✿';
            font-size: 0.7rem;
            color: var(--pink-hot);
            opacity: 0.6;
        }
        pre {
            background: white;
            border: 1px solid var(--pink-border);
            border-radius: 8px;
            padding: 6px 10px;
            font-family: 'Fira Code', monospace;
            font-size: 0.85rem;
            max-height: 85px;
            overflow-y: auto;
            white-space: pre-wrap;
        }
        .diff-error { color: var(--fail); font-weight: bold; }

        .btn-run.submitting {
            animation: excitedWiggle 0.35s infinite ease-in-out;
        }
        @keyframes excitedWiggle {
            0%, 100% { transform: rotate(0) scale(1); }
            25% { transform: rotate(-3deg) scale(1.03); }
            75% { transform: rotate(3deg) scale(1.03); }
        }

        /* STATUS BAR AT BOTTOM */
        .status-bar {
            height: 32px;
            background: rgba(255, 255, 255, 0.95);
            border-top: 1px solid var(--pink-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 16px;
            font-size: 0.78rem;
            color: var(--text-muted);
            font-weight: 600;
            z-index: 100;
        }
        .status-left, .status-right {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .status-center {
            font-weight: 700;
            color: var(--pink-hot);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 40%;
        }
        .autosave-status {
            display: flex;
            align-items: center;
            gap: 5px;
            padding: 2px 8px;
            border-radius: 10px;
            background: #f1f5f9;
            transition: all 0.3s;
        }
        .autosave-status.saving {
            background: #fef3c7;
            color: #b45309;
        }
        .autosave-status.saved {
            background: #d1fae5;
            color: #065f46;
        }
        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #94a3b8;
            transition: background 0.3s;
        }
        .autosave-status.saving .status-dot {
            background: #f59e0b;
            animation: dotPulse 0.8s infinite alternate;
        }
        .autosave-status.saved .status-dot {
            background: #10b981;
        }
        @keyframes dotPulse {
            0% { transform: scale(0.8); opacity: 0.6; }
            100% { transform: scale(1.2); opacity: 1; }
        }
        .status-lang-pill {
            background: #ffeef4;
            color: var(--pink-hot);
            border: 1px solid var(--pink-border);
            padding: 1px 6px;
            border-radius: 6px;
            font-weight: 700;
        }

        /* WALKING CAT IN STATUS BAR */
        .walking-cat-track {
            position: relative;
            width: 130px;
            height: 24px;
            overflow: hidden;
            background: rgba(255, 94, 151, 0.08);
            border-radius: 12px;
            border: 1px dashed var(--pink-border);
            flex-shrink: 0;
            cursor: pointer;
        }
        .walking-cat {
            position: absolute;
            width: 36px;
            height: 20px;
            bottom: 2px;
            animation: catWalkRun 10s linear infinite;
            cursor: pointer;
        }
        @keyframes catWalkRun {
            0% { left: -45px; }
            100% { left: 135px; }
        }
        .wcat-body {
            position: absolute;
            width: 20px;
            height: 11px;
            background: var(--cat-fur);
            border-radius: 50% 50% 40% 40%;
            bottom: 4px;
            left: 7px;
            animation: wcatBob 0.5s ease-in-out infinite;
        }
        .wcat-head {
            position: absolute;
            width: 12px;
            height: 12px;
            background: var(--cat-fur);
            border-radius: 50%;
            top: 1px;
            right: 2px;
            z-index: 2;
            animation: wcatBob 0.5s ease-in-out infinite;
        }
        .wcat-ear {
            position: absolute;
            width: 0;
            height: 0;
            border-left: 2.5px solid transparent;
            border-right: 2.5px solid transparent;
            border-bottom: 5px solid var(--cat-fur-dark);
            top: -4px;
        }
        .wcat-ear-l { left: 1px; transform: rotate(-15deg); }
        .wcat-ear-r { right: 1px; transform: rotate(15deg); }
        .wcat-eye {
            position: absolute;
            width: 2px;
            height: 2px;
            background: #3d3137;
            border-radius: 50%;
            top: 4px;
            right: 3px;
        }
        .wcat-tail {
            position: absolute;
            width: 10px;
            height: 2.5px;
            background: var(--cat-fur);
            border-radius: 3px;
            bottom: 8px;
            left: 0;
            transform-origin: right bottom;
            animation: wcatTail 0.5s ease-in-out infinite;
        }
        @keyframes wcatTail {
            0%, 100% { transform: rotate(-25deg); }
            50% { transform: rotate(15deg); }
        }
        @keyframes wcatBob {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-2px); }
        }
        .wcat-leg {
            position: absolute;
            width: 2.5px;
            height: 6px;
            background: var(--cat-fur-dark);
            border-radius: 1px;
            bottom: 0;
            transform-origin: top center;
        }
        .wcat-leg-fl { right: 7px; animation: wcatLegA 0.5s linear infinite; }
        .wcat-leg-fr { right: 11px; animation: wcatLegB 0.5s linear infinite; }
        .wcat-leg-bl { left: 8px; animation: wcatLegB 0.5s linear infinite; }
        .wcat-leg-br { left: 12px; animation: wcatLegA 0.5s linear infinite; }
        @keyframes wcatLegA {
            0%, 100% { transform: rotate(-28deg); }
            50% { transform: rotate(28deg); }
        }
        @keyframes wcatLegB {
            0%, 100% { transform: rotate(28deg); }
            50% { transform: rotate(-28deg); }
        }

        /* FLYING CAT (ZOOMS ACROSS SCREEN) */
        .flying-cat-container {
            position: fixed;
            z-index: 9998;
            pointer-events: none;
            transition: transform linear;
            filter: drop-shadow(0 6px 12px rgba(255, 94, 151, 0.35));
        }
        .flying-cat-inner {
            position: relative;
            width: 58px;
            height: 38px;
            animation: flyBob 0.8s ease-in-out infinite;
        }
        @keyframes flyBob {
            0%, 100% { transform: translateY(0) rotate(3deg); }
            50% { transform: translateY(-10px) rotate(-3deg); }
        }
        .fcat-body {
            position: absolute;
            width: 40px;
            height: 22px;
            background: linear-gradient(135deg, #ffafcc, #ff5e97);
            border-radius: 50% 50% 45% 45%;
            top: 10px;
            left: 4px;
        }
        .fcat-head {
            position: absolute;
            width: 20px;
            height: 18px;
            background: #ff8fb7;
            border-radius: 50%;
            top: 8px;
            right: 2px;
        }
        .fcat-ear {
            position: absolute;
            width: 0;
            height: 0;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-bottom: 6px solid #ff5e97;
            top: -4px;
        }
        .fcat-ear-l { left: 2px; transform: rotate(-15deg); }
        .fcat-ear-r { right: 2px; transform: rotate(15deg); }
        .fcat-eye {
            position: absolute;
            width: 3.5px;
            height: 3.5px;
            background: #3d3137;
            border-radius: 50%;
            top: 6px;
            right: 4px;
        }
        .fcat-wing {
            position: absolute;
            width: 16px;
            height: 11px;
            background: rgba(255, 255, 255, 0.9);
            border-radius: 50% 50% 10% 50%;
            top: 2px;
            left: 16px;
            transform-origin: bottom center;
            animation: wingFlap 0.2s ease-in-out infinite;
            border: 1px solid var(--pink-border);
        }
        @keyframes wingFlap {
            0%, 100% { transform: rotate(-25deg); }
            50% { transform: rotate(30deg); }
        }
        .fcat-tail {
            position: absolute;
            width: 16px;
            height: 4px;
            background: #ff8fb7;
            border-radius: 8px;
            top: 18px;
            left: -8px;
            transform-origin: right center;
            animation: fcatTail 0.4s ease-in-out infinite;
        }
        @keyframes fcatTail {
            0%, 100% { transform: rotate(-20deg); }
            50% { transform: rotate(20deg); }
        }
        .fcat-trail {
            position: absolute;
            left: -28px;
            top: 16px;
            display: flex;
            gap: 4px;
        }
        .fcat-star {
            width: 6px;
            height: 6px;
            background: #ffd166;
            clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%);
            animation: starTwinkle 0.4s infinite alternate;
        }
        @keyframes starTwinkle {
            0% { transform: scale(0.6); opacity: 0.5; }
            100% { transform: scale(1.2); opacity: 1; }
        }

        /* CELEBRATION MODAL OVERLAY (PASS & FAIL) */
        .cat-overlay {
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 9999;
            display: flex;
            justify-content: center;
            align-items: center;
            background: transparent;
            transition: background 0.3s ease;
        }
        .cat-overlay.active {
            pointer-events: auto;
            background: rgba(40, 20, 30, 0.4);
            backdrop-filter: blur(3px);
        }
        .cat-pop {
            background: white;
            padding: 24px 36px;
            border-radius: 28px;
            box-shadow: 0 12px 36px rgba(255, 94, 151, 0.4);
            border: 3.5px solid var(--pink-hot);
            text-align: center;
            transform: scale(0.6);
            opacity: 0;
            pointer-events: auto;
            transition: transform 0.35s var(--spring), opacity 0.3s;
            max-width: 400px;
            width: 90%;
            position: relative;
        }
        .cat-pop.show {
            transform: scale(1);
            opacity: 1;
        }

        /* PURE CSS CELEBRATION CAT (PASS) */
        .celeb-cat-box {
            position: relative;
            width: 110px;
            height: 100px;
            margin: 0 auto 12px auto;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .celeb-cat-figure {
            position: relative;
            width: 76px;
            height: 90px;
            animation: celebCatDance 0.7s var(--spring) infinite;
            transform-origin: bottom center;
        }
        @keyframes celebCatDance {
            0%, 100% { transform: translateY(0) rotate(-4deg) scale(1); }
            50% { transform: translateY(-16px) rotate(4deg) scale(1.05); }
        }
        .ccat-body {
            position: absolute;
            width: 56px;
            height: 46px;
            background: linear-gradient(180deg, #ff8fb7, #ff5e97);
            border-radius: 50% 50% 45% 45%;
            bottom: 8px;
            left: 10px;
            box-shadow: 0 6px 15px rgba(255, 94, 151, 0.35);
        }
        .ccat-belly {
            position: absolute;
            width: 30px;
            height: 26px;
            background: #ffffff;
            border-radius: 50%;
            bottom: 4px;
            left: 50%;
            transform: translateX(-50%);
        }
        .ccat-head {
            position: absolute;
            width: 50px;
            height: 42px;
            background: linear-gradient(180deg, #ff9eb5, #ff7597);
            border-radius: 50%;
            top: 4px;
            left: 13px;
            z-index: 5;
            box-shadow: 0 4px 10px rgba(255, 94, 151, 0.25);
        }
        .ccat-ear {
            position: absolute;
            width: 0;
            height: 0;
            border-left: 8px solid transparent;
            border-right: 8px solid transparent;
            border-bottom: 14px solid #ff5e97;
            top: -10px;
        }
        .ccat-ear-l { left: 4px; transform: rotate(-18deg); animation: earWiggleL 0.7s infinite; }
        .ccat-ear-r { right: 4px; transform: rotate(18deg); animation: earWiggleR 0.7s infinite; }
        @keyframes earWiggleL { 0%, 100% { transform: rotate(-18deg); } 50% { transform: rotate(-28deg); } }
        @keyframes earWiggleR { 0%, 100% { transform: rotate(18deg); } 50% { transform: rotate(28deg); } }
        .ccat-ear-in {
            position: absolute;
            width: 0;
            height: 0;
            border-left: 4.5px solid transparent;
            border-right: 4.5px solid transparent;
            border-bottom: 9px solid #ffeef4;
            top: 3px;
            left: -4.5px;
        }
        .ccat-eyes-happy {
            position: absolute;
            top: 14px;
            width: 100%;
            display: flex;
            justify-content: space-around;
            padding: 0 8px;
            box-sizing: border-box;
        }
        .ccat-eye-arc {
            width: 9px;
            height: 5px;
            border-bottom: 2.5px solid #3d3137;
            border-radius: 0 0 50% 50%;
        }
        .ccat-nose {
            position: absolute;
            width: 5px;
            height: 3.5px;
            background: #ff3b80;
            border-radius: 50%;
            top: 22px;
            left: 50%;
            transform: translateX(-50%);
        }
        .ccat-mouth {
            position: absolute;
            width: 8px;
            height: 5px;
            background: #e63946;
            border-radius: 0 0 10px 10px;
            top: 26px;
            left: 50%;
            transform: translateX(-50%);
            box-shadow: inset 0 2px 0 #ff8fb7;
        }
        .ccat-blush {
            position: absolute;
            width: 7px;
            height: 4px;
            background: rgba(255, 94, 151, 0.6);
            border-radius: 50%;
            top: 22px;
        }
        .ccat-blush.l { left: 5px; }
        .ccat-blush.r { right: 5px; }
        .ccat-paw {
            position: absolute;
            width: 13px;
            height: 15px;
            background: #ffffff;
            border: 2px solid var(--pink-border);
            border-radius: 50%;
            top: 24px;
            z-index: 6;
        }
        .ccat-paw-l {
            left: -2px;
            transform-origin: bottom center;
            animation: cheerWaveL 0.7s infinite;
        }
        .ccat-paw-r {
            right: -2px;
            transform-origin: bottom center;
            animation: cheerWaveR 0.7s infinite;
        }
        @keyframes cheerWaveL { 0%, 100% { transform: rotate(-30deg) translateY(0); } 50% { transform: rotate(-55deg) translateY(-8px); } }
        @keyframes cheerWaveR { 0%, 100% { transform: rotate(30deg) translateY(0); } 50% { transform: rotate(55deg) translateY(-8px); } }
        .ccat-tail {
            position: absolute;
            width: 28px;
            height: 7px;
            background: var(--cat-fur-dark);
            border-radius: 10px;
            bottom: 16px;
            right: -14px;
            transform-origin: left center;
            animation: ccatTailWag 0.5s ease-in-out infinite;
        }
        @keyframes ccatTailWag { 0%, 100% { transform: rotate(-30deg); } 50% { transform: rotate(35deg); } }
        .ccat-feet {
            position: absolute;
            bottom: 2px;
            left: 13px;
            width: 48px;
            display: flex;
            justify-content: space-between;
        }
        .ccat-foot {
            width: 14px;
            height: 9px;
            background: #ffffff;
            border: 2px solid var(--pink-border);
            border-radius: 50% 50% 40% 40%;
        }

        /* PURE CSS SAD CRYING CAT (FAIL) */
        .sad-cat-box {
            position: relative;
            width: 110px;
            height: 100px;
            margin: 0 auto 12px auto;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .sad-cat-figure {
            position: relative;
            width: 76px;
            height: 90px;
            animation: sadShiver 2s ease-in-out infinite;
        }
        @keyframes sadShiver {
            0%, 100% { transform: translateY(0); }
            15% { transform: translateY(1px) translateX(-1px); }
            30% { transform: translateY(-1px) translateX(1px); }
            45% { transform: translateY(1px) translateX(-0.5px); }
            60% { transform: translateY(0); }
        }
        .sad-body {
            position: absolute;
            width: 54px;
            height: 44px;
            background: #ffb3c6;
            border-radius: 50% 50% 45% 45%;
            bottom: 8px;
            left: 11px;
        }
        .sad-belly {
            position: absolute;
            width: 28px;
            height: 24px;
            background: #ffffff;
            border-radius: 50%;
            bottom: 4px;
            left: 50%;
            transform: translateX(-50%);
        }
        .sad-head {
            position: absolute;
            width: 48px;
            height: 40px;
            background: #ffa8bc;
            border-radius: 50%;
            top: 10px;
            left: 14px;
            z-index: 5;
        }
        .sad-ear {
            position: absolute;
            width: 0;
            height: 0;
            border-left: 7px solid transparent;
            border-right: 7px solid transparent;
            border-bottom: 13px solid #ff7597;
            top: -4px;
        }
        .sad-ear.l { left: -2px; transform: rotate(-45deg); }
        .sad-ear.r { right: -2px; transform: rotate(45deg); }
        .sad-eyes {
            position: absolute;
            top: 12px;
            width: 100%;
            display: flex;
            justify-content: space-around;
            padding: 0 8px;
            box-sizing: border-box;
        }
        .sad-eye {
            position: relative;
            width: 10px;
            height: 11px;
            background: #3d3137;
            border-radius: 50%;
            overflow: hidden;
        }
        .sad-pupil {
            position: absolute;
            width: 4px;
            height: 4px;
            background: #a0c4ff;
            border-radius: 50%;
            bottom: 1px;
            left: 2px;
        }
        .sad-tear-shine {
            position: absolute;
            width: 4.5px;
            height: 4.5px;
            background: #ffffff;
            border-radius: 50%;
            top: 1px;
            right: 1px;
        }
        .scat-tears-stream {
            position: absolute;
            top: 36px;
            width: 60px;
            height: 38px;
            pointer-events: none;
            z-index: 20;
        }
        .stear {
            position: absolute;
            width: 5px;
            height: 8px;
            background: #64b5f6;
            border-radius: 50% 50% 50% 50% / 60% 60% 40% 40%;
            opacity: 0;
        }
        .st-l1 { left: 14px; animation: tearDrop 1.2s infinite ease-in 0s; }
        .st-l2 { left: 16px; animation: tearDrop 1.2s infinite ease-in 0.6s; }
        .st-r1 { right: 14px; animation: tearDrop 1.2s infinite ease-in 0.3s; }
        .st-r2 { right: 16px; animation: tearDrop 1.2s infinite ease-in 0.9s; }
        @keyframes tearDrop {
            0% { opacity: 0; transform: translateY(0) scale(0.6); }
            30% { opacity: 0.9; }
            80% { opacity: 0.8; }
            100% { opacity: 0; transform: translateY(32px) scale(1.1); }
        }
        .sad-nose {
            position: absolute;
            width: 4.5px;
            height: 3px;
            background: var(--fail);
            border-radius: 50%;
            top: 23px;
            left: 50%;
            transform: translateX(-50%);
        }
        .sad-mouth {
            position: absolute;
            width: 7px;
            height: 3.5px;
            border-top: 2px solid #5a3d4a;
            border-radius: 50% 50% 0 0;
            top: 28px;
            left: 50%;
            transform: translateX(-50%);
        }
        .sad-paws {
            position: absolute;
            bottom: 6px;
            left: 23px;
            width: 30px;
            display: flex;
            justify-content: space-between;
            z-index: 6;
        }
        .sad-paw {
            width: 12px;
            height: 11px;
            background: #ffffff;
            border: 1.5px solid var(--pink-border);
            border-radius: 50%;
        }
        .sad-tail-droop {
            position: absolute;
            width: 22px;
            height: 5px;
            background: #ff8fb7;
            border-radius: 8px;
            bottom: 6px;
            left: -5px;
            transform: rotate(35deg);
        }

        /* PURE CSS CONFETTI */
        .css-confetti {
            position: fixed;
            top: -20px;
            pointer-events: none;
            z-index: 10000;
            animation: confettiFall linear forwards;
        }
        .css-confetti.circle { width: 9px; height: 9px; border-radius: 50%; }
        .css-confetti.square { width: 9px; height: 9px; border-radius: 2px; }
        .css-confetti.diamond { width: 9px; height: 9px; border-radius: 1px; transform: rotate(45deg); }
        .css-confetti.strip { width: 5px; height: 14px; border-radius: 3px; }
        @keyframes confettiFall {
            0% { top: -20px; opacity: 1; transform: translateY(0) rotate(0deg); }
            100% { top: 105vh; opacity: 0; transform: translateY(105vh) rotate(720deg) scale(0.6); }
        }

        /* MODAL OVERLAY (SHORTCUTS & MILESTONE) */
        .modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(61, 49, 55, 0.45);
            backdrop-filter: blur(4px);
            z-index: 9999;
            display: flex;
            justify-content: center;
            align-items: center;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.25s var(--spring);
        }
        .modal-overlay.active {
            opacity: 1;
            pointer-events: auto;
        }
        .modal-card {
            background: white;
            padding: 24px 28px;
            border-radius: 24px;
            border: 3px solid var(--pink-border);
            box-shadow: 0 16px 40px rgba(255, 94, 151, 0.3);
            max-width: 460px;
            width: 90%;
            transform: scale(0.85);
            transition: transform 0.3s var(--spring);
            position: relative;
        }
        .modal-overlay.active .modal-card {
            transform: scale(1);
        }
        .modal-close-btn {
            position: absolute;
            top: 14px;
            right: 16px;
            background: #ffeef4;
            border: 1px solid var(--pink-border);
            width: 28px;
            height: 28px;
            border-radius: 50%;
            cursor: pointer;
            font-weight: 800;
            color: var(--pink-hot);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .modal-close-btn:hover {
            background: var(--pink-hot);
            color: white;
        }
        .shortcuts-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            font-size: 0.85rem;
        }
        .shortcuts-table td {
            padding: 7px 6px;
            border-bottom: 1px solid #f8fafc;
        }
        .kbd {
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 2px 7px;
            font-family: 'Fira Code', monospace;
            font-size: 0.78rem;
            font-weight: 600;
            color: #1e293b;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }

        /* MILESTONE CROWN CAT */
        .milestone-crown-cat {
            position: relative;
            width: 80px;
            height: 75px;
            margin: 0 auto 10px auto;
        }
        .mcrown {
            position: absolute;
            top: -12px;
            left: 50%;
            transform: translateX(-50%);
            width: 28px;
            height: 16px;
            background: linear-gradient(135deg, #ffd700, #ffb703);
            clip-path: polygon(0% 100%, 0% 20%, 25% 60%, 50% 0%, 75% 60%, 100% 20%, 100% 100%);
            z-index: 10;
            filter: drop-shadow(0 2px 4px rgba(255, 183, 3, 0.5));
            animation: crownFloat 1.5s infinite ease-in-out;
        }
        @keyframes crownFloat {
            0%, 100% { transform: translateX(-50%) translateY(0); }
            50% { transform: translateX(-50%) translateY(-3px); }
        }


        /* ============ DARK MODE (global) ============ */
        body.dark-mode {
            --pink-bg: #1a1218;
            --pink-card: #221820;
            --pink-sidebar: #1e151b;
            --pink-border: #4a2d3a;
            --pink-hot: #ff5e97;
            --pink-hot-hover: #ff3b80;
            --pink-light: #cc4a7a;
            --pink-soft: #9e3860;
            --pink-subtle: #2d1a24;
            --cat-fur: #d4607e;
            --cat-fur-dark: #b34d68;
            --text-dark: #f0dce6;
            --text-muted: #a08090;
            --success: #10b981;
            --fail: #f43f5e;
            background: linear-gradient(135deg, #1a1218 0%, #1e1420 50%, #1c1118 100%);
            color: var(--text-dark);
        }
        body.dark-mode header {
            background: rgba(30,20,28,0.97);
            border-bottom-color: var(--pink-border);
        }
        body.dark-mode .sidebar {
            background: rgba(28,16,22,0.97);
            border-right-color: var(--pink-border);
        }
        body.dark-mode .sidebar-header {
            background: rgba(34,24,32,0.98);
            border-bottom-color: var(--pink-border);
        }
        body.dark-mode .panel {
            background: rgba(32,22,30,0.97);
            border-color: var(--pink-border);
        }
        body.dark-mode .editor-wrapper {
            background: #1e1520;
            border-color: var(--pink-border);
        }
        body.dark-mode .editor-header {
            background: #261b22;
            border-bottom-color: var(--pink-border);
        }
        body.dark-mode .results-header {
            background: #1e1520;
            border-bottom-color: var(--pink-border);
        }
        body.dark-mode .status-bar {
            background: rgba(28,16,24,0.98);
            border-top-color: var(--pink-border);
        }
        body.dark-mode .problem-item {
            background: rgba(40,25,35,0.95);
            color: var(--text-dark);
        }
        body.dark-mode .progress-box {
            background: rgba(40,20,32,0.9);
            border-color: var(--pink-border);
        }
        body.dark-mode .progress-bar-bg { background: #2d1a24; }
        body.dark-mode .filter-pill { background: #2a1820; color: #a08090; }
        body.dark-mode .filter-pill:hover { background: #3a2030; color: var(--pink-hot); }
        body.dark-mode .search-input { background: #261b22; color: var(--text-dark); border-color: var(--pink-border); }
        body.dark-mode .search-input:focus { background: #2d2029; }
        body.dark-mode .modal-card { background: #221820; color: var(--text-dark); border-color: var(--pink-border); }
        body.dark-mode .cat-pop { background: #221820; }
        body.dark-mode .tab-file-pill { background: #2d1a24; border-color: var(--pink-border); }
        body.dark-mode pre { background: #1a1018; border-color: var(--pink-border); color: #d4bec9; }
        body.dark-mode .test-card { background: #1e1520; }
        body.dark-mode pre { background: #12101a; border-color: #3a2244; color: #e0d0f0; }
        body.dark-mode .test-col-title { color: #9980aa; }
        body.dark-mode .btn-outline { background: #2d1a24; color: var(--pink-hot); border-color: var(--pink-hot); }
        body.dark-mode .btn-outline:hover { background: #3d2030; }
        body.dark-mode .editor-btn { background: #2a1a24; border-color: var(--pink-border); color: var(--text-dark); }
        body.dark-mode .editor-btn:hover { border-color: var(--pink-hot); color: var(--pink-hot); }
        body.dark-mode .font-size-control { background: #2a1a24; border-color: var(--pink-border); }
        body.dark-mode .font-btn { color: var(--pink-hot); }
        body.dark-mode .font-btn:hover { background: #3a2030; }
        body.dark-mode .autosave-status { background: #2a1a24; }
        body.dark-mode .walking-cat-track { background: rgba(255,94,151,0.06); border-color: var(--pink-border); }
        body.dark-mode ::-webkit-scrollbar-thumb { background: var(--pink-border); }
        body.dark-mode .modal-overlay { background: rgba(10,5,8,0.7); }
        body.dark-mode .shortcuts-table td { border-bottom-color: #3a2030; }
        body.dark-mode .kbd { background: #2a1a24; border-color: #4a2d3a; color: #d4bec9; }
        body.dark-mode .logo-sub { background: #2d1a24; color: var(--text-muted); }
        body.dark-mode .CodeMirror-gutters { background: #1a1018; border-right-color: var(--pink-border); }

        /* ============ TYPING SPARKLE EFFECT ============ */
        .type-spark {
            position: fixed;
            pointer-events: none;
            z-index: 99999;
            animation: sparkFloat 0.7s ease-out forwards;
        }
        .type-spark-dot {
            width: 5px; height: 5px; border-radius: 50%;
            background: var(--pink-hot);
        }
        .type-spark-line {
            width: 2px; height: 8px; border-radius: 2px;
            background: #ffd166;
            transform: rotate(var(--rot, 0deg));
        }
        @keyframes sparkFloat {
            0%   { opacity: 1; transform: translate(0,0) scale(1); }
            100% { opacity: 0; transform: translate(var(--tx,0), var(--ty,-20px)) scale(0.3); }
        }

        /* ============ SVG ICON helpers ============ */
        .icon-svg { display:inline-flex; align-items:center; justify-content:center; }

        /* ============ CORNER STRETCH CATS (fixed position decorative) ============ */
        /* Cat #3 - top-right corner peeker */
        .corner-cat-tr {
            position: fixed; top: 48px; right: 0; z-index: 200;
            width: 42px; height: 48px;
            cursor: pointer;
            animation: cornerPeek 8s ease-in-out infinite;
            transform-origin: right center;
        }
        @keyframes cornerPeek {
            0%,100% { transform: translateX(28px); }
            25%,75% { transform: translateX(28px); }
            40%,60% { transform: translateX(0px); }
        }
        /* Cat #4 - bottom-left corner lounger */
        .corner-cat-bl {
            position: fixed; bottom: 34px; left: 322px; z-index: 200;
            width: 38px; height: 28px;
            cursor: pointer; pointer-events: auto;
            animation: blLoungeWag 3s ease-in-out infinite;
        }
        @keyframes blLoungeWag {
            0%,100% { transform: translateY(0) rotate(0deg); }
            50% { transform: translateY(-3px) rotate(2deg); }
        }
        /* Cat #5 - sidebar footer sitter */
        .sidebar-footer-cat {
            position: absolute; bottom: 36px; left: 50%; transform: translateX(-50%);
            width: 50px; height: 44px; z-index: 5;
            cursor: pointer; pointer-events: auto;
        }
        /* Cat #6 - header right watcher */
        .header-watcher-cat {
            position: relative; width: 28px; height: 24px;
            display: inline-flex; align-items: flex-end;
            cursor: pointer; flex-shrink: 0;
            animation: hwcBob 4s ease-in-out infinite;
        }
        @keyframes hwcBob { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-3px); } }

        /* ============ AMBIENT CATS (roam the edges) ============ */
        /* Cat #7 - window climber (right side, slides up slowly) */
        .edge-climber {
            position: fixed; right: 4px; bottom: 40px;
            width: 28px; height: 32px; z-index: 150;
            animation: edgeClimb 20s linear infinite;
            pointer-events: none;
        }
        @keyframes edgeClimb {
            0%   { bottom: 40px; transform: rotate(0deg); }
            45%  { bottom: calc(100vh - 100px); transform: rotate(0deg); }
            50%  { bottom: calc(100vh - 100px); transform: rotate(180deg); }
            95%  { bottom: 40px; transform: rotate(180deg); }
            100% { bottom: 40px; transform: rotate(0deg); }
        }
        /* Cat #8 - top bar lurker slides left-to-right slowly */
        .topbar-lurker {
            position: fixed; top: 56px; left: -40px; z-index: 150;
            width: 36px; height: 24px; pointer-events: none;
            animation: topLurk 35s linear infinite;
        }
        @keyframes topLurk {
            0%   { left: -40px; }
            45%  { left: calc(100vw + 40px); }
            45.1%{ left: -40px; opacity:0; }
            46%  { opacity: 1; }
            100% { left: -40px; }
        }
        /* Cat #9 - results panel cat that peeks from bottom of editor */
        .editor-bottom-peeker {
            position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%);
            width: 32px; height: 20px; z-index: 20;
            pointer-events: none;
            animation: peekUpDown 5s ease-in-out infinite;
        }
        @keyframes peekUpDown {
            0%,100%  { transform: translateX(-50%) translateY(12px); }
            30%,70%  { transform: translateX(-50%) translateY(0); }
        }
        /* Cat #10 - sidebar scroll follower (always at mid-sidebar) */
        .sidebar-scroll-cat {
            position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
            width: 20px; height: 18px; z-index: 10;
            pointer-events: none;
            animation: sscPeek 6s ease-in-out infinite;
        }
        @keyframes sscPeek {
            0%,100% { transform: translateY(-50%) scaleX(1); opacity: 0.6; }
            50%      { transform: translateY(calc(-50% - 6px)) scaleX(1); opacity: 1; }
        }
        /* Cat #11 - mini cat on progress bar */
        .progress-riding-cat {
            position: relative; display: inline-flex; align-items: center;
            width: 18px; height: 14px; margin-left: 4px; vertical-align: middle;
            animation: progRide 2s ease-in-out infinite;
        }
        @keyframes progRide {
            0%,100% { transform: translateY(0); }
            50%      { transform: translateY(-2px); }
        }

        /* Cat #12 - results area cat greeting */
        .results-greeting-cat {
            display: inline-block; width: 44px; height: 38px;
            margin: 0 auto 8px auto;
            animation: greetBounce 2s ease-in-out infinite;
        }
        @keyframes greetBounce {
            0%,100% { transform: translateY(0) rotate(-3deg); }
            50%      { transform: translateY(-6px) rotate(3deg); }
        }

        /* ============ SHARED MINI-CAT TEMPLATE CSS ============ */
        /* generic micro cat parts */
        .mc { position: relative; display: inline-block; }
        .mc .h  { /* head  */
            position: absolute; border-radius: 50%;
            background: var(--cat-fur);
        }
        .mc .b  { /* body  */
            position: absolute; border-radius: 50% 50% 45% 45%;
            background: var(--cat-fur);
        }
        .mc .el, .mc .er { /* ears */
            position: absolute; width:0; height:0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-bottom: 7px solid var(--cat-fur-dark);
        }
        .mc .tl { /* tail */
            position: absolute; border-radius: 6px;
            background: var(--cat-fur);
            transform-origin: right center;
            animation: mcTail 1.5s ease-in-out infinite;
        }
        @keyframes mcTail {
            0%,100% { transform: rotate(-20deg); }
            50%      { transform: rotate(20deg); }
        }
        .mc .ey { /* eye dot */
            position: absolute; border-radius: 50%;
            background: #3e3137; width:3px; height:3px;
        }
        .mc .ns { /* nose */
            position: absolute; border-radius: 50%;
            background: var(--pink-hot);
            width: 3px; height: 2px;
        }
        /* Sleeping stripe on eye = closed */
        .mc .ec {
            position: absolute; border-radius: 0 0 50% 50%;
            border-bottom: 1.5px solid #3e3137; width: 5px; height: 3px;
        }

        /* ============ BIG CENTER WATCHING CAT ============ */
        .editor-center-cat {
            position: absolute;
            top: 52%;
            left: 55%;
            transform: translate(-50%, -50%);
            z-index: 1;
            pointer-events: none;
            opacity: 0.22;
            transition: opacity 0.3s ease, transform 0.2s ease;
            user-select: none;
        }
        body.dark-mode .editor-center-cat {
            opacity: 0.28;
        }
        .editor-center-cat.typing-active {
            opacity: 0.38;
            transform: translate(-50%, -50%) scale(1.03);
        }
        body.dark-mode .editor-center-cat.typing-active {
            opacity: 0.45;
        }
        .editor-center-cat.has-code {
            opacity: 0.18;
        }
        body.dark-mode .editor-center-cat.has-code {
            opacity: 0.22;
        }
        .editor-center-cat svg {
            width: 280px;
            height: 280px;
            filter: drop-shadow(0 8px 30px rgba(255,94,151,0.4));
            overflow: visible;
        }
        /* Pupils move via JS transform */
        #bigCatPupilL, #bigCatPupilR {
            transition: transform 0.08s ease-out;
        }
        /* Tail wag */
        #bigCatTail {
            transform-origin: 95px 155px;
            animation: bigTailWag 2s ease-in-out infinite;
        }
        @keyframes bigTailWag {
            0%,100% { transform: rotate(-15deg); }
            50%      { transform: rotate(15deg); }
        }
        /* Ear wiggle */
        #bigCatEarL { transform-origin: 60px 48px; animation: bigEarL 6s ease-in-out infinite; }
        #bigCatEarR { transform-origin: 120px 48px; animation: bigEarR 6s ease-in-out infinite; }
        @keyframes bigEarL {
            0%,88%,100% { transform: rotate(0deg); }
            92% { transform: rotate(-8deg); }
            96% { transform: rotate(5deg); }
        }
        @keyframes bigEarR {
            0%,88%,100% { transform: rotate(0deg); }
            92% { transform: rotate(8deg); }
            96% { transform: rotate(-5deg); }
        }
        /* Blink */
        #bigCatEyeLid {
            animation: bigBlink 5s ease-in-out infinite;
            transform-origin: center;
        }
        @keyframes bigBlink {
            0%,94%,100% { transform: scaleY(0); }
            97% { transform: scaleY(1); }
        }
        /* Breathing body */
        #bigCatBody {
            transform-origin: 90px 160px;
            animation: bigBreath 4s ease-in-out infinite;
        }
        @keyframes bigBreath {
            0%,100% { transform: scaleY(1) scaleX(1); }
            50%      { transform: scaleY(1.025) scaleX(0.985); }
        }
        /* Tail wag FAST when typing */
        .editor-center-cat.typing-active #bigCatTail {
            animation: bigTailFast 0.3s ease-in-out infinite;
        }
        @keyframes bigTailFast {
            0%,100% { transform: rotate(-28deg); }
            50%      { transform: rotate(28deg); }
        }
        /* UET logo */
        .uet-logo-img {
            height: 28px;
            width: auto;
            object-fit: contain;
            border-radius: 4px;
            opacity: 0.95;
            transition: opacity 0.2s, transform 0.2s var(--spring);
        }
        .uet-logo-img:hover {
            opacity: 1;
            transform: scale(1.05);
        }
        .uet-logo-wrap {
            display: flex;
            align-items: center;
            gap: 6px;
            text-decoration: none;
            border-right: 1.5px solid var(--pink-border);
            padding-right: 10px;
            margin-right: 2px;
            flex-shrink: 0;
        }
        .uet-logo-label {
            font-size: 0.68rem;
            font-weight: 800;
            color: var(--text-muted);
            line-height: 1.1;
            white-space: nowrap;
        }
        body.dark-mode .uet-logo-img {
            filter: brightness(0) invert(1);
            opacity: 0.95;
        }
        body.dark-mode .uet-logo-label {
            color: var(--text-dark);
        }
        ::-webkit-scrollbar { width: 7px; height: 7px; }
        ::-webkit-scrollbar-thumb { background: var(--pink-border); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--pink-hot); }
    </style>
</head>
<body>
    <!-- HEADER -->
    <header>
        <div class="header-left">
            <a class="uet-logo-wrap" href="https://uet.vnu.edu.vn" target="_blank" title="Truong Dai hoc Cong nghe - DHQGHN">
                <img class="uet-logo-img" src="https://upload.wikimedia.org/wikipedia/vi/b/bf/Logo_HUET.svg"
                     onerror="this.style.display='none'" alt="UET Logo">
                <div class="uet-logo-label">ĐHQGHN<br>Trường ĐH Công nghệ</div>
            </a>
            <div class="logo-box">
                <div class="mascot-cat" title="Meow! Chúc Sen code vui vẻ!">
                    <div class="mcat-head">
                        <div class="mcat-ear l"></div>
                        <div class="mcat-ear r"></div>
                        <div class="mcat-eye l"></div>
                        <div class="mcat-eye r"></div>
                        <div class="mcat-nose"></div>
                        <div class="mcat-blush l"></div>
                        <div class="mcat-blush r"></div>
                    </div>
                </div>
                <div>
                    <div class="logo-title">MeowCode</div>
                </div>
            </div>
        </div>
        
        <div class="header-actions">
            <div class="progress-box">
                <span id="progressLabel">0/100</span><span class="progress-riding-cat"><div class="mc " style="width:18px;height:14px;display:inline-block;position:relative;"><div class="mc h" style="width:12px;height:10px;top:0;left:3px;"><div class="mc el" style="border-left-width:3px;border-right-width:3px;border-bottom-width:5px;top:-4px;left:1px;transform:rotate(-15deg);"></div><div class="mc er" style="border-left-width:3px;border-right-width:3px;border-bottom-width:5px;top:-4px;right:1px;transform:rotate(15deg);"></div><div class="mc ey" style="top:4px;left:3px;"></div><div class="mc ey" style="top:4px;right:3px;"></div><div class="mc ns" style="top:8px;left:50%;transform:translateX(-50%);"></div></div></div></span>
                <div class="progress-bar-bg"><div class="progress-bar-fill" id="progressFill"></div></div>
            </div>
            <!-- Cat #6: Header watcher cat -->
            <div class="header-watcher-cat" onclick="spawnPawConfetti()" title="Bấm mèo để tung confetti!"><div class="mc " style="width:28px;height:24px;display:inline-block;position:relative;"><div class="mc tl" style="width:12px;height:3px;top:10px;left:-8px;"></div><div class="mc h" style="width:18px;height:18px;top:0;left:5px;"><div class="mc el" style="border-left-width:5px;border-right-width:5px;border-bottom-width:8px;top:-6px;left:1px;transform:rotate(-15deg);"></div><div class="mc er" style="border-left-width:5px;border-right-width:5px;border-bottom-width:8px;top:-6px;right:1px;transform:rotate(15deg);"></div><div class="mc ey" style="top:8px;left:4px;"></div><div class="mc ey" style="top:8px;right:4px;"></div><div class="mc ns" style="top:12px;left:50%;transform:translateX(-50%);"></div><div style="position:absolute;width:5px;height:3px;background:rgba(255,94,151,0.5);border-radius:50%;top:11px;left:1px;"></div><div style="position:absolute;width:5px;height:3px;background:rgba(255,94,151,0.5);border-radius:50%;top:11px;right:1px;"></div></div></div>            </div>
            <button class="btn btn-outline" id="darkModeBtn" onclick="toggleDarkMode()" title="Chuyển giao diện sáng/tối" style="padding:6px 10px;">
                <span class="icon-svg" id="darkModeIcon"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></span>
            </button>
            <input type="file" id="ipynbFile" accept=".ipynb" style="display:none;" onchange="handleImportIpynb(event)">
            <button class="btn btn-outline" onclick="document.getElementById('ipynbFile').click()"><span class="icon-svg"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg></span> Nhập .ipynb</button>
            <button class="btn" onclick="exportIpynb()"><span class="icon-svg"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></span> Xuất Notebook</button>
        </div>
    </header>

    <!-- MAIN CONTAINER -->
    <div class="main-container">
        <!-- SIDEBAR -->
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="search-row">
                    <div class="search-wrapper">
                        <input type="text" id="searchInput" class="search-input" placeholder="Tìm bài tập (mã hoặc tên) meow~" oninput="filterProblems()">
                        <span class="search-paw-decor icon-svg"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg></span>
                    </div>
                    <!-- Sleeping Cat Widget -->
                    <div class="sleeping-cat-widget" onclick="wakeSleepingCat()" title="Mèo ngủ nè Sen~ Zzz (Bấm để gọi dậy!)">
                        <div class="zzz-stream">
                            <span class="zzz z1">z</span>
                            <span class="zzz z2">Z</span>
                            <span class="zzz z3">Z</span>
                        </div>
                        <div class="sleeping-cat" id="sleepingCat">
                            <div class="scat-tail"></div>
                            <div class="scat-body">
                                <div class="scat-fur-marking"></div>
                            </div>
                            <div class="scat-head">
                                <div class="scat-ear scat-ear-l"></div>
                                <div class="scat-ear scat-ear-r"></div>
                                <div class="scat-eye scat-eye-l"></div>
                                <div class="scat-eye scat-eye-r"></div>
                                <div class="scat-nose"></div>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- Filter Pills -->
                <div class="filter-tabs">
                    <div class="filter-pill active" data-filter="all" onclick="setFilter('all')"><span class="icon-svg"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg></span> Tất cả (100)</div>
                    <div class="filter-pill" data-filter="passed" onclick="setFilter('passed')"><span class="icon-svg"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg></span> Đã xong</div>
                    <div class="filter-pill" data-filter="unsolved" onclick="setFilter('unsolved')"><span class="icon-svg"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></span> Chưa làm</div>
                    <div class="filter-pill" data-filter="failed" onclick="setFilter('failed')"><span class="icon-svg"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg></span> Cần sửa</div>
                </div>
            </div>
            <ul class="problem-list" id="problemList"></ul>
            <!-- Cat #10: sidebar scroll cat -->
            <div class="sidebar-scroll-cat"><div class="mc " style="width:20px;height:18px;display:inline-block;position:relative;"><div class="mc h" style="width:13px;height:14px;top:0;left:4px;"><div class="mc el" style="border-left-width:3px;border-right-width:3px;border-bottom-width:5px;top:-4px;left:1px;transform:rotate(-15deg);"></div><div class="mc er" style="border-left-width:3px;border-right-width:3px;border-bottom-width:5px;top:-4px;right:1px;transform:rotate(15deg);"></div><div class="mc ey" style="top:6px;left:3px;"></div><div class="mc ey" style="top:6px;right:3px;"></div><div class="mc ns" style="top:10px;left:50%;transform:translateX(-50%);"></div></div></div>            </div>
            <!-- Cat #5: Sidebar footer sitter -->
            <div class="sidebar-footer-cat" onclick="wakeSleepingCat()" title="Meo~ bấm tôi nào!"><div class="mc " style="width:50px;height:44px;display:inline-block;position:relative;"><div class="mc tl" style="width:12px;height:3px;top:18px;left:-8px;"></div><div class="mc h" style="width:32px;height:33px;top:0;left:9px;"><div class="mc el" style="border-left-width:7px;border-right-width:7px;border-bottom-width:11px;top:-9px;left:3px;transform:rotate(-15deg);"></div><div class="mc er" style="border-left-width:7px;border-right-width:7px;border-bottom-width:11px;top:-9px;right:3px;transform:rotate(15deg);"></div><div class="mc ey" style="top:14px;left:7px;"></div><div class="mc ey" style="top:14px;right:7px;"></div><div class="mc ns" style="top:22px;left:50%;transform:translateX(-50%);"></div><div style="position:absolute;width:5px;height:3px;background:rgba(255,94,151,0.5);border-radius:50%;top:21px;left:3px;"></div><div style="position:absolute;width:5px;height:3px;background:rgba(255,94,151,0.5);border-radius:50%;top:21px;right:3px;"></div></div></div>            </div>
        </div>

        <!-- MAIN WORKSPACE -->
        <div class="workspace">
            <div class="panel problem-detail" id="problemDetailPanel">
                <h2 id="curTitle"><span class="icon-svg" style="vertical-align: middle;"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg></span> Chọn bài tập để bắt đầu meow~</h2>
                <p id="curDesc"></p>
            </div>

            <!-- CODE EDITOR BOX -->
            <div class="editor-wrapper">
                <!-- Companion Cat Sitting on Editor Header -->
                <div class="editor-cat-companion" id="editorCat" title="Mèo đồng hành đang chăm chú xem Sen code!">
                    <div class="ecat-tail"></div>
                    <div class="ecat-head">
                        <div class="ecat-ear ecat-ear-l"><div class="ecat-ear-inner"></div></div>
                        <div class="ecat-ear ecat-ear-r"><div class="ecat-ear-inner"></div></div>
                        <div class="ecat-eye ecat-eye-l"><div class="ecat-pupil"></div></div>
                        <div class="ecat-eye ecat-eye-r"><div class="ecat-pupil"></div></div>
                        <div class="ecat-nose"></div>
                        <div class="ecat-blush ecat-blush-l"></div>
                        <div class="ecat-blush ecat-blush-r"></div>
                    </div>
                    <div class="ecat-paws">
                        <div class="ecat-paw ecat-paw-l"></div>
                        <div class="ecat-paw ecat-paw-r"></div>
                    </div>
                </div>

                <div class="editor-header">
                    <div class="editor-header-left">
                        <span class="tab-file-pill"><span class="tab-file-dot"></span> solution.py</span>
                        <span style="font-size: 0.78rem; color: #888;">Phím tắt: <b>Ctrl+Enter</b> chấm bài</span>
                    </div>
                    <div class="editor-controls">
                        <div class="font-size-control" title="Chỉnh cỡ chữ (Ctrl + = / Ctrl + -)">
                            <button class="font-btn" onclick="changeFontSize(-1)">A-</button>
                            <span class="font-val" id="fontSizeVal">15px</span>
                            <button class="font-btn" onclick="changeFontSize(1)">A+</button>
                        </div>
                        <button class="editor-btn" onclick="toggleTheme()" id="themeBtn" title="Đổi giao diện">
                            <span class="icon-svg" id="themeIcon"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg></span><span id="themeLabel">Neo</span>
                        </button>
                        <button class="editor-btn" onclick="toggleCommentAction()" title="Bật/Tắt chú thích dòng (Ctrl+/)">
                            <span class="icon-svg"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></span><span>Ghi chú</span>
                        </button>
                        <button class="editor-btn" onclick="resetCurrentTemplate()" title="Đặt lại code ban đầu">
                            <span class="icon-svg"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.39"/></svg></span><span>Đặt lại</span>
                        </button>
                        <button class="editor-btn" onclick="toggleShortcutsModal(true)" title="Xem danh sach phim tat"><span class="icon-svg"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8"/></svg></span></button>
                    </div>
                </div>
                <textarea id="codeEditor"></textarea>
                <!-- BÉ MÈO SIÊU TO KHỔNG LỒ GIỮA EDITOR NHÌN THEO CODE -->
                <div class="editor-center-cat" id="editorBigCat">
                  <svg viewBox="0 0 200 220" xmlns="http://www.w3.org/2000/svg">
                    <!-- Glow circle behind cat -->
                    <circle cx="100" cy="110" r="95" fill="rgba(255, 158, 181, 0.08)"/>
                    
                    <!-- TAIL -->
                    <g id="bigCatTail">
                      <path d="M120 170 Q160 175 175 145 Q185 125 170 120 Q155 125 152 145 Q145 165 120 172"
                            fill="var(--cat-fur)" stroke="var(--cat-fur-dark)" stroke-width="2.5"/>
                    </g>
                    
                    <!-- HIND PAWS -->
                    <ellipse cx="45" cy="185" rx="20" ry="12" fill="var(--cat-fur)" stroke="var(--cat-fur-dark)" stroke-width="2"/>
                    <ellipse cx="155" cy="185" rx="20" ry="12" fill="var(--cat-fur)" stroke="var(--cat-fur-dark)" stroke-width="2"/>
                    <ellipse cx="45" cy="184" rx="13" ry="7" fill="#ffffff" opacity="0.6"/>
                    <ellipse cx="155" cy="184" rx="13" ry="7" fill="#ffffff" opacity="0.6"/>

                    <!-- BODY -->
                    <g id="bigCatBody">
                      <ellipse cx="100" cy="155" rx="60" ry="48" fill="var(--cat-fur)" stroke="var(--cat-fur-dark)" stroke-width="2.5"/>
                      <!-- belly patch -->
                      <ellipse cx="100" cy="160" rx="34" ry="28" fill="#ffffff" opacity="0.75"/>
                      <!-- little collar & bell -->
                      <path d="M72 120 Q100 134 128 120" stroke="#ff3b80" stroke-width="4.5" fill="none" stroke-linecap="round"/>
                      <circle cx="100" cy="130" r="6" fill="#ffd166" stroke="#e09f3e" stroke-width="1.5"/>
                      <circle cx="100" cy="131" r="1.5" fill="#e09f3e"/>
                    </g>

                    <!-- FRONT PAWS (tucked cute) -->
                    <g>
                      <ellipse cx="78" cy="188" rx="14" ry="10" fill="#ffffff" stroke="var(--cat-fur-dark)" stroke-width="2"/>
                      <ellipse cx="122" cy="188" rx="14" ry="10" fill="#ffffff" stroke="var(--cat-fur-dark)" stroke-width="2"/>
                      <!-- Toe lines -->
                      <path d="M74 184 L74 191 M82 184 L82 191" stroke="var(--pink-border)" stroke-width="1.5" stroke-linecap="round"/>
                      <path d="M118 184 L118 191 M126 184 L126 191" stroke="var(--pink-border)" stroke-width="1.5" stroke-linecap="round"/>
                    </g>

                    <!-- HEAD -->
                    <g id="bigCatHead">
                      <ellipse cx="100" cy="85" rx="58" ry="50" fill="var(--cat-fur)" stroke="var(--cat-fur-dark)" stroke-width="2.5"/>
                      
                      <!-- EARS -->
                      <g id="bigCatEarL">
                        <polygon points="45,50 62,10 82,48" fill="var(--cat-fur)" stroke="var(--cat-fur-dark)" stroke-width="2.5"/>
                        <polygon points="52,48 64,20 76,46" fill="#ff7597" opacity="0.65"/>
                      </g>
                      <g id="bigCatEarR">
                        <polygon points="118,48 138,10 155,50" fill="var(--cat-fur)" stroke="var(--cat-fur-dark)" stroke-width="2.5"/>
                        <polygon points="124,46 136,20 148,48" fill="#ff7597" opacity="0.65"/>
                      </g>
                      
                      <!-- FOREHEAD TABBY STRIPES -->
                      <path d="M100 45 L100 56" stroke="var(--cat-fur-dark)" stroke-width="3" stroke-linecap="round" opacity="0.5"/>
                      <path d="M90 48 L93 57" stroke="var(--cat-fur-dark)" stroke-width="2.5" stroke-linecap="round" opacity="0.5"/>
                      <path d="M110 48 L107 57" stroke="var(--cat-fur-dark)" stroke-width="2.5" stroke-linecap="round" opacity="0.5"/>
                      
                      <!-- EYES SCLERA (Big expressive white) -->
                      <ellipse cx="76" cy="86" rx="19" ry="18" fill="#ffffff" stroke="var(--cat-fur-dark)" stroke-width="2.5"/>
                      <ellipse cx="124" cy="86" rx="19" ry="18" fill="#ffffff" stroke="var(--cat-fur-dark)" stroke-width="2.5"/>
                      
                      <!-- IRIS (Emerald green gradient) -->
                      <ellipse cx="76" cy="86" rx="14" ry="14" fill="#10b981"/>
                      <ellipse cx="124" cy="86" rx="14" ry="14" fill="#10b981"/>
                      <circle cx="76" cy="86" r="12" fill="#059669" opacity="0.5"/>
                      <circle cx="124" cy="86" r="12" fill="#059669" opacity="0.5"/>

                      <!-- PUPILS (DILATED & MOVE TO TRACK CODE CURSOR) -->
                      <g id="bigCatPupilL">
                        <ellipse cx="76" cy="86" rx="7" ry="11" fill="#1e1520"/>
                        <!-- Big cute shine -->
                        <circle cx="72" cy="81" r="4.5" fill="#ffffff"/>
                        <circle cx="79" cy="91" r="2" fill="#ffffff"/>
                      </g>
                      <g id="bigCatPupilR">
                        <ellipse cx="124" cy="86" rx="7" ry="11" fill="#1e1520"/>
                        <!-- Big cute shine -->
                        <circle cx="120" cy="81" r="4.5" fill="#ffffff"/>
                        <circle cx="127" cy="91" r="2" fill="#ffffff"/>
                      </g>
                      
                      <!-- BLINK EYELID OVERLAY -->
                      <g id="bigCatEyeLid">
                        <path d="M57 86 Q76 68 95 86 Q76 76 57 86 Z" fill="var(--cat-fur)"/>
                        <path d="M105 86 Q124 68 143 86 Q124 76 105 86 Z" fill="var(--cat-fur)"/>
                      </g>

                      <!-- NOSE (Heart shape) -->
                      <path d="M96 104 C96 102 98 100 100 102 C102 100 104 102 104 104 C104 107 100 110 100 110 C100 110 96 107 96 104 Z" fill="#ff3b80"/>
                      
                      <!-- MOUTH (Cute :3 cat mouth) -->
                      <path d="M94 110 Q100 114 100 111 Q100 114 106 110" stroke="#4a2d3a" stroke-width="2.5" fill="none" stroke-linecap="round"/>
                      
                      <!-- ROSY BLUSH CHEEKS -->
                      <ellipse cx="56" cy="103" rx="10" ry="6" fill="#ff5e97" opacity="0.45"/>
                      <ellipse cx="144" cy="103" rx="10" ry="6" fill="#ff5e97" opacity="0.45"/>
                      
                      <!-- WHISKERS -->
                      <g stroke="#4a2d3a" stroke-width="1.8" stroke-linecap="round" opacity="0.45">
                        <line x1="30" y1="98" x2="62" y2="103"/>
                        <line x1="26" y1="106" x2="60" y2="107"/>
                        <line x1="32" y1="114" x2="62" y2="111"/>
                        <line x1="170" y1="98" x2="138" y2="103"/>
                        <line x1="174" y1="106" x2="140" y2="107"/>
                        <line x1="168" y1="114" x2="138" y2="111"/>
                      </g>
                    </g>
                  </svg>
                </div>

            <!-- Cat #9: Editor bottom peeker -->
            <div class="editor-bottom-peeker"><div class="mc " style="width:32px;height:20px;display:inline-block;position:relative;"><div class="mc h" style="width:21px;height:15px;top:0;left:6px;"><div class="mc el" style="border-left-width:4px;border-right-width:4px;border-bottom-width:6px;top:-5px;left:2px;transform:rotate(-15deg);"></div><div class="mc er" style="border-left-width:4px;border-right-width:4px;border-bottom-width:6px;top:-5px;right:2px;transform:rotate(15deg);"></div><div class="mc ey" style="top:6px;left:5px;"></div><div class="mc ey" style="top:6px;right:5px;"></div><div class="mc ns" style="top:11px;left:50%;transform:translateX(-50%);"></div></div></div>            </div>
            </div>

            <!-- TEST RESULTS BOX -->
            <div class="panel results-panel" id="resultsPanel">
                <div class="results-header">
                    <span id="resultsTitle" style="display:flex;align-items:center;gap:6px;"><span class="icon-svg"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg></span> <span class="icon-svg"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg></span> Kết quả Test Cases của Sen</span>
                    <div style="display: flex; gap: 10px;">
                        <button class="btn" id="btnToggleHeight" style="padding: 4px 12px; font-size: 0.8rem;" onclick="toggleExpand()"><span class="icon-svg" id="expandIcon"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg></span> <span id="expandLabel">Phóng to</span></button>
                        <button class="btn btn-run" id="btnRun" onclick="submitCode()"><span class="icon-svg"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg></span> Chấm Bài (Ctrl+Enter)</button>
                    </div>
                </div>
                <div class="results-body" id="resultsArea">
                    <div style="text-align: center; margin-top: 35px; color: #999;">Bấm "Chấm Bài" để kiểm tra code tự động với các test cases meow~</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Cat #7: Edge climber -->
    <div class="edge-climber"><div class="mc " style="width:28px;height:32px;display:inline-block;position:relative;"><div class="mc tl" style="width:12px;height:3px;top:13px;left:-8px;"></div><div class="mc h" style="width:18px;height:24px;top:0;left:5px;"><div class="mc el" style="border-left-width:5px;border-right-width:5px;border-bottom-width:8px;top:-6px;left:1px;transform:rotate(-15deg);"></div><div class="mc er" style="border-left-width:5px;border-right-width:5px;border-bottom-width:8px;top:-6px;right:1px;transform:rotate(15deg);"></div><div class="mc ey" style="top:9px;left:4px;"></div><div class="mc ey" style="top:9px;right:4px;"></div><div class="mc ns" style="top:15px;left:50%;transform:translateX(-50%);"></div></div></div>    </div>
    <!-- Cat #8: Topbar lurker -->
    <div class="topbar-lurker"><div class="mc " style="width:36px;height:24px;display:inline-block;position:relative;"><div class="mc tl" style="width:12px;height:3px;top:10px;left:-8px;"></div><div class="mc h" style="width:23px;height:18px;top:0;left:6px;"><div class="mc el" style="border-left-width:5px;border-right-width:5px;border-bottom-width:8px;top:-6px;left:2px;transform:rotate(-15deg);"></div><div class="mc er" style="border-left-width:5px;border-right-width:5px;border-bottom-width:8px;top:-6px;right:2px;transform:rotate(15deg);"></div><div class="mc ec" style="top:8px;left:5px;"></div><div class="mc ec" style="top:8px;right:5px;"></div><div class="mc ns" style="top:13px;left:50%;transform:translateX(-50%);"></div></div></div>    </div>
    <!-- Cat #3: Corner peeker TR -->
    <div class="corner-cat-tr" onclick="spawnPawConfetti()" title="Mèo nhìn trộm! Bấm để ăn mừng!"><div class="mc " style="width:42px;height:48px;display:inline-block;position:relative;"><div class="mc tl" style="width:12px;height:3px;top:19px;left:-8px;"></div><div class="mc h" style="width:27px;height:36px;top:0;left:8px;"><div class="mc el" style="border-left-width:7px;border-right-width:7px;border-bottom-width:11px;top:-9px;left:2px;transform:rotate(-15deg);"></div><div class="mc er" style="border-left-width:7px;border-right-width:7px;border-bottom-width:11px;top:-9px;right:2px;transform:rotate(15deg);"></div><div class="mc ey" style="top:14px;left:6px;"></div><div class="mc ey" style="top:14px;right:6px;"></div><div class="mc ns" style="top:22px;left:50%;transform:translateX(-50%);"></div></div></div>    </div>
    <!-- Cat #4: Corner lounger BL -->
    <div class="corner-cat-bl" title="Mèo lười biếng"><div class="mc " style="width:38px;height:28px;display:inline-block;position:relative;"><div class="mc tl" style="width:12px;height:3px;top:11px;left:-8px;"></div><div class="mc h" style="width:25px;height:21px;top:0;left:6px;"><div class="mc el" style="border-left-width:5px;border-right-width:5px;border-bottom-width:8px;top:-6px;left:2px;transform:rotate(-15deg);"></div><div class="mc er" style="border-left-width:5px;border-right-width:5px;border-bottom-width:8px;top:-6px;right:2px;transform:rotate(15deg);"></div><div class="mc ec" style="top:9px;left:5px;"></div><div class="mc ec" style="top:9px;right:5px;"></div><div class="mc ns" style="top:15px;left:50%;transform:translateX(-50%);"></div></div></div>    </div>

    <!-- STATUS BAR AT VERY BOTTOM -->
    <div class="status-bar">
        <div class="status-left">
            <!-- Walking Cat Track -->
            <div class="walking-cat-track" onclick="patWalkingCat(event)" title="Mèo dạo mát trong status bar meow~ (Bấm nhẹ để xoa đầu)">
                <div class="walking-cat">
                    <div class="wcat-tail"></div>
                    <div class="wcat-body"></div>
                    <div class="wcat-head">
                        <div class="wcat-ear wcat-ear-l"></div>
                        <div class="wcat-ear wcat-ear-r"></div>
                        <div class="wcat-eye"></div>
                    </div>
                    <div class="wcat-leg wcat-leg-fl"></div>
                    <div class="wcat-leg wcat-leg-fr"></div>
                    <div class="wcat-leg wcat-leg-bl"></div>
                    <div class="wcat-leg wcat-leg-br"></div>
                </div>
            </div>
            <!-- Auto-save Status Badge -->
            <div class="autosave-status saved" id="autosaveStatus">
                <span class="status-dot"></span>
                <span id="autosaveText">Đã sẵn sàng meow~</span>
            </div>
        </div>

        <div class="status-center">
            <span id="statusCurrentProblem">Chưa chọn bài tập</span>
        </div>

        <div class="status-right">
            <span id="cursorPos">Ln 1, Col 1</span>
            <span class="status-lang-pill">Python 3</span>
            <span>UTF-8</span>
            <span>Spaces: 4</span>
        </div>
    </div>

    <!-- CELEBRATION MODAL OVERLAY (NO EMOJI CATS - PURE CSS ANIMATED ART) -->
    <div class="cat-overlay" id="catOverlay" onclick="if(event.target === this) closeCatCelebration()">
        <div class="cat-pop" id="catPop">
            <button class="modal-close-btn" onclick="closeCatCelebration()" style="position:absolute;top:12px;right:14px;z-index:20;" title="Đóng">✕</button>
            <!-- Success Dancing Cat Art -->
            <div class="celeb-cat-box" id="passCatArt" style="display: none;">
                <div class="celeb-cat-figure">
                    <div class="ccat-tail"></div>
                    <div class="ccat-body"><div class="ccat-belly"></div></div>
                    <div class="ccat-paw ccat-paw-l"></div>
                    <div class="ccat-paw ccat-paw-r"></div>
                    <div class="ccat-head">
                        <div class="ccat-ear ccat-ear-l"><div class="ccat-ear-in"></div></div>
                        <div class="ccat-ear ccat-ear-r"><div class="ccat-ear-in"></div></div>
                        <div class="ccat-eyes-happy">
                            <div class="ccat-eye-arc"></div>
                            <div class="ccat-eye-arc"></div>
                        </div>
                        <div class="ccat-nose"></div>
                        <div class="ccat-mouth"></div>
                        <div class="ccat-blush l"></div>
                        <div class="ccat-blush r"></div>
                    </div>
                    <div class="ccat-feet"><div class="ccat-foot"></div><div class="ccat-foot"></div></div>
                </div>
            </div>

            <!-- Fail Crying Cat Art -->
            <div class="sad-cat-box" id="failCatArt" style="display: none;">
                <div class="scat-tears-stream">
                    <div class="stear st-l1"></div>
                    <div class="stear st-l2"></div>
                    <div class="stear st-r1"></div>
                    <div class="stear st-r2"></div>
                </div>
                <div class="sad-cat-figure">
                    <div class="sad-tail-droop"></div>
                    <div class="sad-body"><div class="sad-belly"></div></div>
                    <div class="sad-paws"><div class="sad-paw"></div><div class="sad-paw"></div></div>
                    <div class="sad-head">
                        <div class="sad-ear l"></div>
                        <div class="sad-ear r"></div>
                        <div class="sad-eyes">
                            <div class="sad-eye"><div class="sad-pupil"></div><div class="sad-tear-shine"></div></div>
                            <div class="sad-eye"><div class="sad-pupil"></div><div class="sad-tear-shine"></div></div>
                        </div>
                        <div class="sad-nose"></div>
                        <div class="sad-mouth"></div>
                    </div>
                </div>
            </div>

            <h2 id="catStatusTitle" style="color: var(--pink-hot); margin-bottom: 5px; font-weight: 800;">Tuyệt vời Sen ơi!</h2>
            <p id="catStatusMsg" style="color: #666; font-weight: 600;">Code chuẩn không cần chỉnh meow meow! 🐾🎉</p>
        </div>
    </div>

    <!-- KEYBOARD SHORTCUTS MODAL -->
    <div class="modal-overlay" id="shortcutsModal" onclick="if(event.target === this) toggleShortcutsModal(false)">
        <div class="modal-card">
            <button class="modal-close-btn" onclick="toggleShortcutsModal(false)">✕</button>
            <h3 style="color: var(--pink-hot); display: flex; align-items: center; gap: 8px;">
                <span class="icon-svg"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8"/></svg></span> Bang Phim Tat MeowCode IDE
            </h3>
            <table class="shortcuts-table">
                <tr>
                    <td><b>Chấm bài (Run test)</b></td>
                    <td style="text-align: right;"><span class="kbd">Ctrl</span> + <span class="kbd">Enter</span></td>
                </tr>
                <tr>
                    <td><b>Tăng cỡ chữ</b></td>
                    <td style="text-align: right;"><span class="kbd">Ctrl</span> + <span class="kbd">+</span></td>
                </tr>
                <tr>
                    <td><b>Giảm cỡ chữ</b></td>
                    <td style="text-align: right;"><span class="kbd">Ctrl</span> + <span class="kbd">-</span></td>
                </tr>
                <tr>
                    <td><b>Bật / Tắt chú thích dòng</b></td>
                    <td style="text-align: right;"><span class="kbd">Ctrl</span> + <span class="kbd">/</span></td>
                </tr>
                <tr>
                    <td><b>Tìm kiếm trong code</b></td>
                    <td style="text-align: right;"><span class="kbd">Ctrl</span> + <span class="kbd">F</span></td>
                </tr>
                <tr>
                    <td><b>Tìm từ tiếp theo</b></td>
                    <td style="text-align: right;"><span class="kbd">Ctrl</span> + <span class="kbd">G</span></td>
                </tr>
                <tr>
                    <td><b>Thụt lề / Lùi lề 4 space</b></td>
                    <td style="text-align: right;"><span class="kbd">Tab</span> / <span class="kbd">Shift+Tab</span></td>
                </tr>
                <tr>
                    <td><b>Tự động lưu (Auto-Save)</b></td>
                    <td style="text-align: right;"><span style="color: #10b981; font-weight: 700;">Tự lưu sau 1.5s</span></td>
                </tr>
            </table>
        </div>
    </div>

    <!-- MILESTONE CELEBRATION MODAL -->
    <div class="modal-overlay" id="milestoneModal" onclick="if(event.target === this) this.classList.remove('active')">
        <div class="modal-card" style="text-align: center;">
            <button class="modal-close-btn" onclick="document.getElementById('milestoneModal').classList.remove('active')">✕</button>
            <div class="milestone-crown-cat">
                <div class="mcrown"></div>
                <div class="celeb-cat-figure" style="transform: scale(0.85); margin: 0 auto;">
                    <div class="ccat-tail"></div>
                    <div class="ccat-body"><div class="ccat-belly"></div></div>
                    <div class="ccat-head">
                        <div class="ccat-ear ccat-ear-l"><div class="ccat-ear-in"></div></div>
                        <div class="ccat-ear ccat-ear-r"><div class="ccat-ear-in"></div></div>
                        <div class="ccat-eyes-happy"><div class="ccat-eye-arc"></div><div class="ccat-eye-arc"></div></div>
                        <div class="ccat-nose"></div>
                        <div class="ccat-mouth"></div>
                    </div>
                </div>
            </div>
            <h2 id="milestoneTitle" style="color: var(--pink-hot); margin-bottom: 8px;">COT MOC VINH QUANG!</h2>
            <p id="milestoneMsg" style="color: #555; font-weight: 600; line-height: 1.5; margin-bottom: 16px;"></p>
            <button class="btn" style="margin: 0 auto;" onclick="document.getElementById('milestoneModal').classList.remove('active')"><span class="icon-svg"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg></span> Tiep tuc chinh phuc meow!</button>
        </div>
    </div>

    <script>
        let problems = [], userSolutions = {}, currentProblem = null;
        let currentFilter = 'all';
        let currentFontSize = parseInt(localStorage.getItem('meow_fontsize') || '15', 10);
        let currentTheme = localStorage.getItem('meow_theme') || 'neo';
        let autosaveTimer = null;
        let typingCatTimer = null;

        // Khởi tạo CodeMirror với đầy đủ Addons & Cấu hình IDE chuyên nghiệp
        const cm = CodeMirror.fromTextArea(document.getElementById('codeEditor'), {
            mode: 'python',
            theme: currentTheme,
            lineNumbers: true,
            lineWrapping: false,
            scrollbarStyle: "native",
            styleActiveLine: true,
            matchBrackets: true,
            autoCloseBrackets: true,
            indentUnit: 4,
            tabSize: 4,
            indentWithTabs: false,
            extraKeys: {
                "Tab": function(cm) {
                    if (cm.somethingSelected()) {
                        cm.indentSelection("add");
                    } else {
                        cm.replaceSelection("    ", "end");
                    }
                },
                "Shift-Tab": function(cm) { cm.indentSelection("subtract"); },
                "Ctrl-Enter": function() { submitCode(); },
                "Cmd-Enter": function() { submitCode(); },
                "Ctrl-/": function(cm) { toggleCommentAction(); },
                "Cmd-/": function(cm) { toggleCommentAction(); },
                "Ctrl-=": function() { changeFontSize(1); },
                "Cmd-=": function() { changeFontSize(1); },
                "Ctrl--": function() { changeFontSize(-1); },
                "Cmd--": function() { changeFontSize(-1); }
            }
        });

        // Áp dụng font size đã lưu
        cm.getWrapperElement().style.fontSize = currentFontSize + 'px';
        document.getElementById('fontSizeVal').innerText = currentFontSize + 'px';
        updateThemeUI();

        // Lắng nghe di chuyển con trỏ để cập nhật status bar
        cm.on('cursorActivity', () => {
            const pos = cm.getCursor();
            const el = document.getElementById('cursorPos');
            if (el) el.innerText = `Ln ${pos.line + 1}, Col ${pos.ch + 1}`;
        });

        // Lắng nghe gõ phím: kích hoạt phản ứng Mèo đồng hành & Auto-save
        cm.on('change', (cmInstance, changeObj) => {
            if (changeObj.origin === 'setValue') return;
            triggerTypingCat();
            triggerAutoSave();
        });

        // Phản ứng của Mèo trên Editor khi user gõ phím
        function triggerTypingCat() {
            const cat = document.getElementById('editorCat');
            if (!cat) return;
            cat.classList.add('typing');
            if (typingCatTimer) clearTimeout(typingCatTimer);
            typingCatTimer = setTimeout(() => {
                cat.classList.remove('typing');
            }, 800);
        }

        // Tự động lưu bài sau 1.5s ngừng gõ
        function triggerAutoSave() {
            const statusBox = document.getElementById('autosaveStatus');
            const statusText = document.getElementById('autosaveText');
            if (statusBox) {
                statusBox.className = 'autosave-status saving';
                if (statusText) statusText.innerText = 'Đang lưu meow...';
            }

            if (autosaveTimer) clearTimeout(autosaveTimer);
            autosaveTimer = setTimeout(async () => {
                if (!currentProblem) return;
                const code = cm.getValue();
                try {
                    const res = await fetch('/api/autosave', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ id: currentProblem.id, code: code })
                    });
                    const data = await res.json();
                    if (data.status === 'saved') {
                        if (!userSolutions[currentProblem.id]) {
                            userSolutions[currentProblem.id] = { code: code, status: 'unsolved' };
                        } else {
                            userSolutions[currentProblem.id].code = code;
                        }
                        if (statusBox) {
                            statusBox.className = 'autosave-status saved';
                            if (statusText) statusText.innerText = 'Đã lưu meow~';
                        }
                    }
                } catch(err) {
                    if (statusBox) {
                        statusBox.className = 'autosave-status';
                        if (statusText) statusText.innerText = 'Lỗi lưu tự động';
                    }
                }
            }, 1500);
        }

        // Tăng giảm cỡ chữ editor
        function changeFontSize(delta) {
            currentFontSize = Math.max(10, Math.min(24, currentFontSize + delta));
            cm.getWrapperElement().style.fontSize = currentFontSize + 'px';
            const label = document.getElementById('fontSizeVal');
            if (label) label.innerText = currentFontSize + 'px';
            cm.refresh();
            localStorage.setItem('meow_fontsize', currentFontSize);
        }

        // Đổi giao diện Neo / Dracula
        function toggleTheme() {
            currentTheme = currentTheme === 'neo' ? 'dracula' : 'neo';
            cm.setOption('theme', currentTheme);
            localStorage.setItem('meow_theme', currentTheme);
            updateThemeUI();
        }

        function updateThemeUI() {
            const label = document.getElementById('themeLabel');
            const icon  = document.getElementById('themeIcon');
            if (label) label.innerText = currentTheme === 'neo' ? 'Neo' : 'Dracula';
            if (icon) icon.innerHTML = currentTheme === 'neo'
                ? '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
                : '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
        }

        // Bật/tắt chú thích dòng
        function toggleCommentAction() {
            if (typeof cm.toggleComment === 'function') {
                cm.toggleComment();
            } else {
                const from = cm.getCursor("from"), to = cm.getCursor("to");
                for (let i = from.line; i <= to.line; i++) {
                    let line = cm.getLine(i);
                    if (line.trim().startsWith("#")) {
                        cm.replaceRange(line.replace(/^\s*# ?/, ""), {line: i, ch: 0}, {line: i, ch: line.length});
                    } else {
                        cm.replaceRange("# " + line, {line: i, ch: 0}, {line: i, ch: line.length});
                    }
                }
            }
        }

        // Đặt lại template ban đầu
        function resetCurrentTemplate() {
            if (!currentProblem) return;
            if (confirm("Sen có chắc muốn đặt lại code ban đầu cho bài này không meow?")) {
                cm.setValue(currentProblem.template || `# Bài ${currentProblem.id}: ${currentProblem.title}\n`);
                triggerAutoSave();
            }
        }

        // Modal phím tắt
        function toggleShortcutsModal(show) {
            const modal = document.getElementById('shortcutsModal');
            if (!modal) return;
            if (show !== undefined) modal.classList.toggle('active', show);
            else modal.classList.toggle('active');
        }

        // Đánh thức Mèo ngủ khi click
        function wakeSleepingCat() {
            const scat = document.getElementById('sleepingCat');
            if (!scat) return;
            scat.classList.add('awake');
            setTimeout(() => scat.classList.remove('awake'), 2800);
        }

        // Xoa đầu Mèo đi bộ trong status bar
        function patWalkingCat(e) {
            e.stopPropagation();
            const heart = document.createElement('div');
            heart.innerText = '💖 Purr~';
            heart.style.position = 'fixed';
            heart.style.left = e.clientX + 'px';
            heart.style.top = (e.clientY - 25) + 'px';
            heart.style.fontWeight = '800';
            heart.style.fontSize = '0.85rem';
            heart.style.color = '#ff5e97';
            heart.style.pointerEvents = 'none';
            heart.style.zIndex = '99999';
            heart.style.transition = 'all 0.8s var(--spring)';
            document.body.appendChild(heart);
            setTimeout(() => {
                heart.style.transform = 'translateY(-25px) scale(1.2)';
                heart.style.opacity = '0';
            }, 20);
            setTimeout(() => heart.remove(), 850);
        }

        // Mèo bay ngang màn hình định kỳ (25-35s)
        function setupFlyingCatTimer() {
            function launchFlyingCat() {
                const cat = document.createElement('div');
                cat.className = 'flying-cat-container';
                const yPercent = Math.floor(Math.random() * 55 + 15);
                cat.style.top = yPercent + 'vh';
                cat.style.left = '-80px';
                cat.innerHTML = `
                    <div class="flying-cat-inner">
                        <div class="fcat-trail"><div class="fcat-star"></div><div class="fcat-star"></div><div class="fcat-star"></div></div>
                        <div class="fcat-tail"></div>
                        <div class="fcat-body"></div>
                        <div class="fcat-wing"></div>
                        <div class="fcat-head">
                            <div class="fcat-ear fcat-ear-l"></div>
                            <div class="fcat-ear fcat-ear-r"></div>
                            <div class="fcat-eye"></div>
                        </div>
                    </div>
                `;
                document.body.appendChild(cat);
                const startTime = performance.now();
                const duration = 5200;
                const totalDist = window.innerWidth + 160;
                function step(now) {
                    const elapsed = now - startTime;
                    const progress = Math.min(elapsed / duration, 1);
                    cat.style.transform = `translateX(${progress * totalDist}px)`;
                    if (progress < 1) requestAnimationFrame(step);
                    else cat.remove();
                }
                requestAnimationFrame(step);

                const nextInterval = Math.floor(Math.random() * 10000 + 25000);
                setTimeout(launchFlyingCat, nextInterval);
            }
            setTimeout(launchFlyingCat, 18000);
        }

        // Kiểm tra cột mốc đã giải xong
        const CELEBRATED_KEY = 'meow_celebrated_milestones';
        function checkMilestone(newPassedCount) {
            const milestones = [10, 25, 50, 75, 100];
            let celebrated = [];
            try {
                celebrated = JSON.parse(localStorage.getItem(CELEBRATED_KEY) || '[]');
            } catch(e) { celebrated = []; }

            for (let m of milestones) {
                if (newPassedCount >= m && !celebrated.includes(m)) {
                    celebrated.push(m);
                    localStorage.setItem(CELEBRATED_KEY, JSON.stringify(celebrated));
                    showMilestoneModal(m);
                    break;
                }
            }
        }

        function showMilestoneModal(milestone) {
            const modal = document.getElementById('milestoneModal');
            const msg = document.getElementById('milestoneMsg');
            if (!modal) return;
            if (msg) msg.innerText = `Sen đã xuất sắc vượt qua ${milestone} bài tập Python! Vua Mèo xin trao tặng danh hiệu Sen Bất Bại! 🐟👑`;
            modal.classList.add('active');
            spawnPawConfetti();
        }

        // Reload đề bài từ PDF
        async function reloadFromPDF() {
            if (!confirm('Reload tất cả đề bài từ PDF? Thao tác này sẽ mất vài giây meow~')) return;
            
            try {
                const res = await fetch('/api/reload_pdf', { method: 'POST' });
                const data = await res.json();
                
                if (data.status === 'success') {
                    alert(`✅ ${data.message}`);
                    // Reload lại data
                    await loadData();
                } else {
                    alert(`❌ Lỗi: ${data.message}`);
                }
            } catch(err) {
                alert(`❌ Lỗi kết nối: ${err.message}`);
            }
        }

        // Nạp dữ liệu ban đầu
        async function loadData() {
            const res = await fetch('/api/problems');
            const data = await res.json();
            problems = data.problems;
            userSolutions = data.solutions;
            renderList();
            updateProgress();
            if (problems.length > 0) selectProblem(problems[0].id);
            setupFlyingCatTimer();
        }

        // Lọc danh sách bài tập
        function setFilter(filter) {
            currentFilter = filter;
            document.querySelectorAll('.filter-pill').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.filter === filter);
            });
            renderList();
        }

        function filterProblems() { renderList(); }

        function renderList() {
            const list = document.getElementById('problemList');
            const kw = document.getElementById('searchInput').value.toLowerCase();
            list.innerHTML = '';
            problems.forEach(p => {
                const status = userSolutions[p.id]?.status || 'unsolved';
                if (currentFilter !== 'all' && status !== currentFilter) return;

                if (p.id.toLowerCase().includes(kw) || p.title.toLowerCase().includes(kw)) {
                    const li = document.createElement('li');
                    li.className = `problem-item ${currentProblem?.id === p.id ? 'active' : ''}`;
                    
                    let catIconClass = status === 'passed' ? 'pass' : (status === 'failed' ? 'fail' : 'unsolved');
                    let badgeText = status === 'passed' ? 'Xong' : (status === 'failed' ? 'Sai' : 'Chưa làm');

                    li.innerHTML = `
                        <div class="problem-item-left">
                            <span class="p-num">${p.id}</span>
                            <span class="p-name">${p.title}</span>
                        </div>
                        <div class="problem-item-right">
                            <span class="cat-face-icon ${catIconClass}"></span>
                            <span class="badge ${status}">${badgeText}</span>
                        </div>`;
                    li.onclick = () => selectProblem(p.id);
                    list.appendChild(li);
                }
            });
        }

        function selectProblem(id) {
            currentProblem = problems.find(p => p.id === id);
            if (!currentProblem) return;

            document.title = `Bai ${currentProblem.id} - ${currentProblem.title} | MeowCode`;
            const statusProb = document.getElementById('statusCurrentProblem');
            if (statusProb) statusProb.innerText = `[${currentProblem.id}] ${currentProblem.title}`;

            const detailPanel = document.getElementById('problemDetailPanel');
            if (detailPanel) {
                detailPanel.classList.remove('panel-bounce');
                void detailPanel.offsetWidth;
                detailPanel.classList.add('panel-bounce');
            }

            document.getElementById('curTitle').innerText = `Bai ${currentProblem.id}: ${currentProblem.title}`;
            document.getElementById('curDesc').innerText = currentProblem.desc;
            
            const savedCode = userSolutions[id]?.code || currentProblem.template || '';
            cm.setValue(savedCode);
            setTimeout(() => cm.refresh(), 50);

            document.getElementById('resultsArea').innerHTML = '<div style="text-align: center; margin-top: 35px; color: #aaa;">Viết code và bấm Chấm bài (Ctrl+Enter) để bé mèo check nha, meow~~~</div>';
            renderList();
        }

        function toggleExpand(forceState = null) {
            const panel = document.getElementById('resultsPanel');
            const isExpanded = forceState !== null ? forceState : !panel.classList.contains('expanded');
            if (isExpanded) {
                panel.classList.add('expanded');
                const lbl = document.getElementById('expandLabel');
                const ico = document.getElementById('expandIcon');
                if (lbl) lbl.innerText = 'Thu nhỏ';
                if (ico) ico.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="10" y1="14" x2="3" y2="21"/><line x1="21" y1="3" x2="14" y2="10"/></svg>';
            } else {
                panel.classList.remove('expanded');
                const lbl = document.getElementById('expandLabel');
                const ico = document.getElementById('expandIcon');
                if (lbl) lbl.innerText = 'Phóng to';
                if (ico) ico.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>';
            }
        }

        // Chấm bài kiểm tra tự động
        async function submitCode() {
            if (!currentProblem) return;
            const code = cm.getValue();
            const btn = document.getElementById('btnRun');
            if (btn) {
                btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="animation:spin 0.6s linear infinite"><path d="M12 2a10 10 0 1 0 10 10"/></svg> Meo dang cham...';
                btn.classList.add('submitting');
                btn.disabled = true;
            }

            let data;
            try {
                const res = await fetch('/api/run', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ id: currentProblem.id, code: code })
                });
                if (!res.ok) {
                    throw new Error(`Server returned HTTP ${res.status}`);
                }
                data = await res.json();
            } catch(netErr) {
                console.error("Submit network error:", netErr);
                if (btn) {
                    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Chấm Bài (Ctrl+Enter)';
                    btn.classList.remove('submitting');
                    btn.disabled = false;
                }
                alert('Loi ket noi toi may chu meow! Hay thu lai nhe Sen.');
                return;
            }

            if (btn) {
                btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Chấm Bài (Ctrl+Enter)';
                btn.classList.remove('submitting');
                btn.disabled = false;
            }

            try {
                userSolutions[currentProblem.id] = { code: code, status: data.all_passed ? 'passed' : 'failed' };
                toggleExpand(true);
                renderResults(data);
                renderList();
                updateProgress();
                showCatCelebration(data.all_passed);

                let passedCount = Object.values(userSolutions).filter(x => x.status === 'passed').length;
                checkMilestone(passedCount);
            } catch(uiErr) {
                console.error("UI error during post-submit rendering:", uiErr);
            }
        }

        function renderResults(data) {
            const area = document.getElementById('resultsArea');
            area.innerHTML = '';

            // Summary bar với icons và tiếng Việt cute
            const totalTests = data.results.length;
            const passedTests = data.results.filter(r => r.passed).length;
            const summaryDiv = document.createElement('div');
            summaryDiv.className = 'results-summary';
            
            const passIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
            const failIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
            
            summaryDiv.innerHTML = `
                <span class="results-summary-cat ${data.all_passed ? 'pass' : 'fail'}"></span>
                <span class="results-summary-text">
                    <strong>${passedTests}/${totalTests}</strong> test ${passedTests !== 1 ? '' : ''} đã qua 
                    ${data.all_passed
                        ? '<span class="results-summary-badge pass">' + passIcon + ' Hoàn hảo meow!</span>'
                        : '<span class="results-summary-badge fail">' + failIcon + ' Cố lên nào Sen!</span>'}
                </span>
            `;
            area.appendChild(summaryDiv);

            // SVG icon helpers
            const iconInput = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="8 17 12 21 16 17"/><line x1="12" y1="3" x2="12" y2="21"/></svg>`;
            const iconExpected = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
            const iconActual = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`;

            data.results.forEach((r, idx) => {
                const div = document.createElement('div');
                div.className = `test-card ${r.passed ? 'pass' : 'fail'}`;
                div.style.animationDelay = `${idx * 60}ms`;

                const catFaceHtml = r.passed
                    ? `<span class="tc-cat-face pass">
                            <span class="tc-ear l"></span><span class="tc-ear r"></span>
                            <span class="tc-eye l"></span><span class="tc-eye r"></span>
                            <span class="tc-nose"></span><span class="tc-mouth pass"></span>
                        </span>`
                    : `<span class="tc-cat-face fail">
                            <span class="tc-ear l"></span><span class="tc-ear r"></span>
                            <span class="tc-eye l sad"></span><span class="tc-eye r sad"></span>
                            <span class="tc-nose"></span><span class="tc-mouth fail"></span>
                        </span>`;
                
                const testIcon = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;"><path d="M10 2v7.31M14 9.3V1.99M8.5 2h3M13.5 2h3M9 16.5h6M9 12h6M16.53 8.92l.96-1.73M10.2 10.48l-1.45-1.81M20 11l-1.5 1.5M4 11l1.5 1.5M3 6h2M19 6h2"/><rect x="5" y="11" width="14" height="11" rx="1"/></svg>`;

                div.innerHTML = `
                    <div class="tc-header">
                        ${catFaceHtml}
                        <span class="tc-label ${r.passed ? 'pass' : 'fail'}">
                            ${testIcon} Test #${idx + 1}:
                            <strong>${r.passed ? 'ĐÃ PASS' : 'CHƯA PASS'}</strong>
                        </span>
                    </div>
                    <div class="test-grid">
                        <div>
                            <div class="test-col-title">${iconInput} Dữ liệu vào</div>
                            <pre>${r.input !== undefined && r.input !== null && r.input !== '' ? r.input : '(Không có input)'}</pre>
                        </div>
                        <div>
                            <div class="test-col-title">${iconExpected} Kết quả mong đợi</div>
                            <pre>${r.expected}</pre>
                        </div>
                        <div>
                            <div class="test-col-title">${iconActual} Kết quả của Sen</div>
                            <pre class="${r.passed ? '' : 'diff-error'}">${r.actual}</pre>
                        </div>
                    </div>
                `;
                area.appendChild(div);
            });
        }

        // ============ HOA ANH ĐÀO BAY ============
        function spawnSakuraPetal(x, y) {
            const petal = document.createElement('div');
            petal.className = 'sakura-petal';
            petal.style.left = x + 'px';
            petal.style.top = y + 'px';
            
            // Random drift và rotation
            const drift = (Math.random() - 0.5) * 200;
            const rotate = Math.random() * 1440 - 720;
            const duration = 3 + Math.random() * 2;
            
            petal.style.setProperty('--drift', drift + 'px');
            petal.style.setProperty('--rotate', rotate + 'deg');
            petal.style.animationDuration = duration + 's';
            
            document.body.appendChild(petal);
            setTimeout(() => petal.remove(), duration * 1000);
        }
        
        // Spawn hoa khi hover logo
        let sakuraInterval = null;
        document.addEventListener('DOMContentLoaded', () => {
            const logoBox = document.querySelector('.logo-box');
            const mascotCat = document.querySelector('.mascot-cat');
            
            if (logoBox) {
                logoBox.addEventListener('mouseenter', () => {
                    const rect = logoBox.getBoundingClientRect();
                    // Spawn nhiều hoa
                    for (let i = 0; i < 5; i++) {
                        setTimeout(() => {
                            const x = rect.left + Math.random() * rect.width;
                            const y = rect.top + Math.random() * rect.height;
                            spawnSakuraPetal(x, y);
                        }, i * 100);
                    }
                    
                    // Spawn liên tục khi hover
                    sakuraInterval = setInterval(() => {
                        const rect = logoBox.getBoundingClientRect();
                        const x = rect.left + Math.random() * rect.width;
                        const y = rect.top + Math.random() * rect.height;
                        spawnSakuraPetal(x, y);
                    }, 300);
                });
                
                logoBox.addEventListener('mouseleave', () => {
                    if (sakuraInterval) {
                        clearInterval(sakuraInterval);
                        sakuraInterval = null;
                    }
                });
            }
            
            // Spawn hoa khi click mascot cat
            if (mascotCat) {
                mascotCat.addEventListener('click', () => {
                    const rect = mascotCat.getBoundingClientRect();
                    for (let i = 0; i < 15; i++) {
                        setTimeout(() => {
                            const x = rect.left + rect.width / 2 + (Math.random() - 0.5) * 100;
                            const y = rect.top + rect.height / 2 + (Math.random() - 0.5) * 50;
                            spawnSakuraPetal(x, y);
                        }, i * 50);
                    }
                });
            }
        });

        // ============ ÂM THANH PASS/FAIL ============
        // Tạo âm thanh bằng Web Audio API
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        
        function playSuccessSound() {
            // Âm thanh vui vẻ (C-E-G chord - major triad)
            const notes = [523.25, 659.25, 783.99]; // C5, E5, G5
            notes.forEach((freq, i) => {
                const osc = audioContext.createOscillator();
                const gain = audioContext.createGain();
                
                osc.connect(gain);
                gain.connect(audioContext.destination);
                
                osc.frequency.value = freq;
                osc.type = 'sine';
                
                const now = audioContext.currentTime;
                gain.gain.setValueAtTime(0.15, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
                
                osc.start(now + i * 0.1);
                osc.stop(now + 0.4 + i * 0.1);
            });
        }
        
        function playFailSound() {
            // Âm thanh buồn (E-C chord - minor descending)
            const notes = [659.25, 523.25]; // E5, C5
            notes.forEach((freq, i) => {
                const osc = audioContext.createOscillator();
                const gain = audioContext.createGain();
                
                osc.connect(gain);
                gain.connect(audioContext.destination);
                
                osc.frequency.value = freq;
                osc.type = 'triangle';
                
                const now = audioContext.currentTime;
                gain.gain.setValueAtTime(0.2, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
                
                osc.start(now + i * 0.15);
                osc.stop(now + 0.5 + i * 0.15);
            });
        }

        // Popup Mèo Hoạt Hình Pure CSS
        let catCelebrationTimer = null;
        function closeCatCelebration() {
            if (catCelebrationTimer) {
                clearTimeout(catCelebrationTimer);
                catCelebrationTimer = null;
            }
            const pop = document.getElementById('catPop');
            const overlay = document.getElementById('catOverlay');
            if (pop) pop.classList.remove('show');
            if (overlay) overlay.classList.remove('active');
        }

        function showCatCelebration(isPassed) {
            const pop = document.getElementById('catPop');
            const overlay = document.getElementById('catOverlay');
            const title = document.getElementById('catStatusTitle');
            const msg = document.getElementById('catStatusMsg');
            const passCat = document.getElementById('passCatArt');
            const failCat = document.getElementById('failCatArt');

            if (catCelebrationTimer) clearTimeout(catCelebrationTimer);

            if (overlay) overlay.classList.add('active');

            if (isPassed) {
                if (pop) pop.className = 'cat-pop pass show';
                if (passCat) passCat.style.display = 'block';
                if (failCat) failCat.style.display = 'none';
                if (title) title.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> Meowtastic! Quá Đỉnh Sen Ơi!';
                if (msg) msg.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="vertical-align: middle;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg> Sen đã vượt qua toàn bộ Test Case của bài này! Code chuẩn không cần chỉnh meow meow!';
                spawnPawConfetti();
                playSuccessSound(); // 🔊 Âm thanh thành công
            } else {
                if (pop) pop.className = 'cat-pop fail show';
                if (passCat) passCat.style.display = 'none';
                if (failCat) failCat.style.display = 'block';
                if (title) title.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> Huhu, Sai Một Xíu Kìa Sen!';
                if (msg) msg.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg> Kiểm tra lại ký tự dấu cách hoặc kiểu dữ liệu nhé Sen ơi! Mèo tin Sen sẽ làm được!';
                playFailSound(); // 🔊 Âm thanh thất bại
            }

            // Tự động đóng sau 3.5s
            catCelebrationTimer = setTimeout(() => {
                closeCatCelebration();
            }, 3500);
        }

        // Confetti Pure CSS Shapes & Flying Mini-Cats (Cat #14)
        function spawnPawConfetti() {
            const colors = ['#ff5e97', '#ffafcc', '#ffd166', '#06d6a0', '#118ab2', '#8338ec', '#ff7597'];
            const shapes = ['circle', 'square', 'diamond', 'strip'];
            const container = document.body;
            for (let i = 0; i < 40; i++) {
                const conf = document.createElement('div');
                const shape = shapes[Math.floor(Math.random() * shapes.length)];
                const color = colors[Math.floor(Math.random() * colors.length)];
                conf.className = `css-confetti ${shape}`;
                conf.style.backgroundColor = color;
                conf.style.left = Math.random() * 96 + 'vw';
                conf.style.animationDuration = (Math.random() * 1.6 + 1.2) + 's';
                conf.style.animationDelay = (Math.random() * 0.3) + 's';
                container.appendChild(conf);
                setTimeout(() => conf.remove(), 2800);
            }

            // Spawn 3 flying mini-cats on confetti celebration
            const catColors = ['#ff5e97','#ff9eb5','#ffd166'];
            for (let i = 0; i < 3; i++) {
                const mc = document.createElement('div');
                mc.style.cssText = `position:fixed;top:-30px;left:${10+Math.random()*80}vw;z-index:10001;pointer-events:none;animation:confettiFall ${1.5+Math.random()}s linear forwards;`;
                mc.style.animationDelay = (i * 0.2) + 's';
                mc.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="${catColors[i%catColors.length]}">
                    <ellipse cx="12" cy="14" rx="8" ry="6"/>
                    <ellipse cx="12" cy="10" rx="6" ry="6"/>
                    <polygon points="6,6 8,0 10,5" fill="${catColors[i%catColors.length]}"/>
                    <polygon points="18,6 16,0 14,5" fill="${catColors[i%catColors.length]}"/>
                    <circle cx="10" cy="10" r="1.2" fill="#3e3137"/>
                    <circle cx="14" cy="10" r="1.2" fill="#3e3137"/>
                    <ellipse cx="12" cy="12.5" rx="1.2" ry="0.8" fill="#ff3b80"/>
                </svg>`;
                container.appendChild(mc);
                setTimeout(() => mc.remove(), 2500);
            }
        }

        function updateProgress() {
            let count = Object.values(userSolutions).filter(x => x.status === 'passed').length;
            document.getElementById('progressLabel').innerText = `${count}/${problems.length}`;
            document.getElementById('progressFill').style.width = (count / problems.length * 100) + '%';
        }

        function exportIpynb() { window.location.href = '/api/export'; }

        // Nhập file .ipynb để khôi phục code
        function handleImportIpynb(event) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = async function(e) {
                try {
                    const nb = JSON.parse(e.target.result);
                    const importedSolutions = {};
                    let currentId = null;
                    for (let cell of nb.cells) {
                        if (cell.cell_type === 'markdown') {
                            const text = Array.isArray(cell.source) ? cell.source.join('') : cell.source;
                            const match = text.match(/Bài\s*(0\d{3})/i) || text.match(/\b(0\d{3})\b/);
                            if (match) currentId = match[1];
                        } else if (cell.cell_type === 'code' && currentId) {
                            const code = Array.isArray(cell.source) ? cell.source.join('') : cell.source;
                            if (code.trim()) {
                                importedSolutions[currentId] = { code: code, status: 'unsolved' };
                            }
                            currentId = null;
                        }
                    }
                    await fetch('/api/import', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(importedSolutions)
                    });
                    alert(`🐾 Meow! Đã nạp thành công code của ${Object.keys(importedSolutions).length} bài từ notebook!`);
                    loadData();
                } catch(err) {
                    alert('😿 File notebook không đúng định dạng!');
                }
            };
            reader.readAsText(file);
        }

        // Global hotkeys
        window.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && (e.key === '=' || e.key === '+')) {
                e.preventDefault();
                changeFontSize(1);
            }
            if ((e.ctrlKey || e.metaKey) && (e.key === '-' || e.key === '_')) {
                e.preventDefault();
                changeFontSize(-1);
            }
            if (e.key === 'Escape') {
                toggleShortcutsModal(false);
                const milestoneModal = document.getElementById('milestoneModal');
                if (milestoneModal) milestoneModal.classList.remove('active');
                const catPop = document.getElementById('catPop');
                if (catPop) catPop.classList.remove('show');
            }
        });


        // ============ DARK MODE ============
        let isDarkMode = localStorage.getItem('meow_dark') === '1';
        function applyDarkMode() {
            document.body.classList.toggle('dark-mode', isDarkMode);
            const icon = document.getElementById('darkModeIcon');
            if (icon) icon.innerHTML = isDarkMode
                ? '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
                : '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
        }
        function toggleDarkMode() {
            isDarkMode = !isDarkMode;
            localStorage.setItem('meow_dark', isDarkMode ? '1' : '0');
            applyDarkMode();
            // Also switch CodeMirror theme
            if (isDarkMode) {
                currentTheme = 'dracula';
                cm.setOption('theme', 'dracula');
            } else {
                currentTheme = 'neo';
                cm.setOption('theme', 'neo');
            }
            localStorage.setItem('meow_theme', currentTheme);
            updateThemeUI();
        }
        applyDarkMode();

        // ============ TYPING SPARKLE ============
        let sparkEnabled = true;
        let lastSparkTime = 0;
        function spawnTypeSpark(x, y) {
            if (!sparkEnabled) return;
            const now = Date.now();
            if (now - lastSparkTime < 60) return; // throttle
            lastSparkTime = now;
            const count = 3 + Math.floor(Math.random() * 3);
            const colors = ['#ff5e97','#ffd166','#06d6a0','#ff9eb5','#a29bfe'];
            for (let i = 0; i < count; i++) {
                const el = document.createElement('div');
                el.className = 'type-spark';
                const isLine = Math.random() > 0.5;
                const inner = document.createElement('div');
                inner.className = isLine ? 'type-spark-line' : 'type-spark-dot';
                inner.style.background = colors[Math.floor(Math.random() * colors.length)];
                const angle = (Math.random() * 360);
                const dist = 12 + Math.random() * 20;
                const tx = Math.cos(angle * Math.PI/180) * dist;
                const ty = Math.sin(angle * Math.PI/180) * dist - 10;
                inner.style.setProperty('--rot', angle + 'deg');
                inner.style.setProperty('--tx', tx + 'px');
                inner.style.setProperty('--ty', ty + 'px');
                el.style.left = (x + (Math.random()-0.5)*20) + 'px';
                el.style.top  = (y + (Math.random()-0.5)*10) + 'px';
                el.appendChild(inner);
                document.body.appendChild(el);
                setTimeout(() => el.remove(), 750);
            }
        }
        // Hook into CodeMirror cursor to get pixel position
        cm.on('change', (cmInst, chg) => {
            if (chg.origin === 'setValue') return;
            try {
                const cur = cmInst.getCursor();
                const coords = cmInst.cursorCoords(cur, 'page');
                spawnTypeSpark(coords.left, coords.top);
            } catch(e) {}
        });

        // Spin keyframe for loading
        const spinStyle = document.createElement('style');
        spinStyle.textContent = '@keyframes spin { 0%{transform:rotate(0)} 100%{transform:rotate(360deg)} }';
        document.head.appendChild(spinStyle);

        // ============ EXTRA CATS 13-15 (dynamic spawners) ============
        // Cat #13: Random corner napper (appears in results panel occasionally)
        function spawnNapperCat() {
            const area = document.getElementById('resultsArea');
            if (!area) return;
            // only spawn if results area shows the greeting (empty)
            if (area.children.length > 1) return;
            const napper = document.createElement('div');
            napper.style.cssText = 'position:absolute;bottom:8px;right:12px;opacity:0.5;pointer-events:none;animation:greetBounce 3s ease-in-out infinite;z-index:5;';
            napper.innerHTML = document.querySelector('.results-greeting-cat') ? '' : '';
            // just a small cat div
            napper.style.display = 'inline-block';
            area.style.position = 'relative';
        }

        // Cat #15: Idle roaming cat that appears on the workspace background periodically
        function startRoamingWorkspaceCat() {
            const workspace = document.querySelector('.workspace');
            if (!workspace) return;
            workspace.style.position = 'relative';

            function roam() {
                const roamer = document.createElement('div');
                const startY = 60 + Math.random() * 60; // % from top of workspace
                roamer.style.cssText = `position:absolute;top:${startY}%;left:-50px;z-index:1;pointer-events:none;opacity:0.18;transition:left 12s linear;`;
                roamer.innerHTML = `<svg width="30" height="22" viewBox="0 0 30 22" fill="var(--cat-fur)">
                    <ellipse cx="20" cy="14" rx="9" ry="6"/>
                    <ellipse cx="22" cy="9" rx="6" ry="6"/>
                    <polygon points="17,5 19,0 21,4" fill="var(--cat-fur-dark)"/>
                    <polygon points="25,5 27,0 29,4" fill="var(--cat-fur-dark)"/>
                    <circle cx="20" cy="9" r="1" fill="#3e3137"/>
                    <circle cx="24" cy="9" r="1" fill="#3e3137"/>
                    <ellipse cx="22" cy="11" rx="1" ry="0.7" fill="#ff5e97"/>
                    <path d="M11 14 Q6 12 2 16" stroke="var(--cat-fur)" stroke-width="3" fill="none" stroke-linecap="round"/>
                </svg>`;
                workspace.appendChild(roamer);
                requestAnimationFrame(() => {
                    roamer.style.left = (workspace.offsetWidth + 60) + 'px';
                });
                setTimeout(() => roamer.remove(), 13000);
                setTimeout(roam, 20000 + Math.random() * 15000);
            }
            setTimeout(roam, 8000);
        }
        startRoamingWorkspaceCat();

        // ============ BIG CAT EYE TRACKING ============
        const bigCat = document.getElementById('editorBigCat');
        const pupilL = document.getElementById('bigCatPupilL');
        const pupilR = document.getElementById('bigCatPupilR');

        function moveBigCatEyes(targetX, targetY) {
            if (!bigCat || !pupilL || !pupilR) return;
            const svgEl = bigCat.querySelector('svg');
            if (!svgEl) return;
            const svgRect = svgEl.getBoundingClientRect();

            // Sclera centers in screen coords (viewBox is 200x220)
            const scaleX = svgRect.width / 200;
            const scaleY = svgRect.height / 220;

            const eyeLScreen = {
                x: svgRect.left + 76 * scaleX,
                y: svgRect.top  + 86 * scaleY
            };
            const eyeRScreen = {
                x: svgRect.left + 124 * scaleX,
                y: svgRect.top  + 86 * scaleY
            };

            const maxDistance = 7; // max offset in px

            function calcOffset(eyeScreen) {
                const dx = targetX - eyeScreen.x;
                const dy = targetY - eyeScreen.y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 1) return { x: 0, y: 0 };
                const angle = Math.atan2(dy, dx);
                // Travel smoothly with distance
                const travel = Math.min(dist / 90, 1) * maxDistance;
                return {
                    x: Math.cos(angle) * travel,
                    y: Math.sin(angle) * travel
                };
            }

            const offL = calcOffset(eyeLScreen);
            const offR = calcOffset(eyeRScreen);

            pupilL.style.transform = `translate(${offL.x}px, ${offL.y}px)`;
            pupilR.style.transform = `translate(${offR.x}px, ${offR.y}px)`;
        }

        // Track CodeMirror cursor position
        cm.on('cursorActivity', () => {
            try {
                const cur = cm.getCursor();
                const coords = cm.cursorCoords(cur, 'page');
                moveBigCatEyes(coords.left, coords.top);
            } catch(e) {}
        });

        // Also track mouse movement anywhere over the workspace
        document.addEventListener('mousemove', (e) => {
            moveBigCatEyes(e.clientX, e.clientY);
        });

        // Dynamic reaction on typing
        cm.on('change', (cmInst, chg) => {
            if (chg.origin === 'setValue') return;
            if (bigCat) {
                bigCat.classList.add('typing-active');
                clearTimeout(window._bigCatTypingTimer);
                window._bigCatTypingTimer = setTimeout(() => {
                    if (bigCat) bigCat.classList.remove('typing-active');
                }, 800);
            }
            try {
                const cur = cmInst.getCursor();
                const coords = cmInst.cursorCoords(cur, 'page');
                moveBigCatEyes(coords.left, coords.top);
            } catch(e) {}
        });

        loadData();
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/reload_pdf", methods=["POST"])
def reload_from_pdf():
    """API để reload lại đề bài từ PDF (xóa cache và đọc lại)"""
    try:
        # Xóa cache
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)
        
        # Extract lại từ PDF
        problems = extract_problems_from_pdf()
        
        if problems:
            # Lưu cache mới
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(problems, f, ensure_ascii=False, indent=2)
            return jsonify({"status": "success", "message": f"Đã reload {len(problems)} bài từ PDF", "count": len(problems)})
        else:
            return jsonify({"status": "error", "message": "Không thể extract từ PDF"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/problems", methods=["GET"])
def get_problems():
    problems = init_problems()
    solutions = {}
    if os.path.exists(SOLUTIONS_FILE):
        with open(SOLUTIONS_FILE, "r", encoding="utf-8") as f:
            solutions = json.load(f)
    return jsonify({"problems": problems, "solutions": solutions})

@app.route("/api/run", methods=["POST"])
def run_test():
    req = request.json
    pid, code = req.get("id"), req.get("code")
    prob = next((p for p in init_problems() if p["id"] == pid), None)
    
    results = []
    all_passed = True
    for test in prob["tests"]:
        inp, expected = test["input"].strip(), test["output"].strip()
        try:
            p = subprocess.run([sys.executable, "-c", code], input=inp + "\n", capture_output=True, text=True, timeout=2)
            actual = p.stdout.strip()
            passed = (actual == expected) if p.returncode == 0 else False
            if p.returncode != 0:
                actual = f"Lỗi thực thi (Runtime Error):\n{p.stderr.strip()}"
        except subprocess.TimeoutExpired:
            actual = "Lỗi: Quá thời gian quy định (Timeout 2s - Có thể bị lặp vô tận)"
            passed = False
        except Exception as e:
            actual = f"Lỗi hệ thống: {str(e)}"
            passed = False

        if not passed: all_passed = False
        results.append({"input": inp, "expected": expected, "actual": actual, "passed": passed})

    solutions = {}
    if os.path.exists(SOLUTIONS_FILE):
        with open(SOLUTIONS_FILE, "r", encoding="utf-8") as f: solutions = json.load(f)
    solutions[pid] = {"code": code, "status": "passed" if all_passed else "failed"}
    with open(SOLUTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(solutions, f, ensure_ascii=False, indent=2)

    return jsonify({"all_passed": all_passed, "results": results})

@app.route("/api/import", methods=["POST"])
def import_solutions():
    imported = request.json
    solutions = {}
    if os.path.exists(SOLUTIONS_FILE):
        with open(SOLUTIONS_FILE, "r", encoding="utf-8") as f:
            solutions = json.load(f)
    solutions.update(imported)
    with open(SOLUTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(solutions, f, ensure_ascii=False, indent=2)
    return jsonify({"status": "ok"})

@app.route("/api/export", methods=["GET"])
def export_ipynb():
    problems = init_problems()
    solutions = {}
    if os.path.exists(SOLUTIONS_FILE):
        with open(SOLUTIONS_FILE, "r", encoding="utf-8") as f:
            solutions = json.load(f)

    # Xuất file Jupyter Notebook với định dạng học thuật, nghiêm túc
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# BÀI TẬP LẬP TRÌNH PYTHON CĂN BẢN (100 BÀI)\n", "---\n"]
            }
        ],
        "metadata": {
            "language_info": {"name": "python", "version": "3.8"},
            "kernelspec": {"name": "python3", "display_name": "Python 3"}
        },
        "nbformat": 4, "nbformat_minor": 2
    }

    for p in problems:
        # Markdown cell miêu tả đề bài nghiêm túc
        notebook["cells"].append({
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                f"### {p['id']} - {p['title']}\n",
                f"**Yêu cầu:** {p['desc'].replace('Đề bài: ', '')}\n"
            ]
        })
        user_code = solutions.get(p["id"], {}).get("code", p.get("template", ""))
        notebook["cells"].append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [user_code]
        })

    out_file = "BaiTap_Python_100_Bai.ipynb"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(notebook, f, ensure_ascii=False, indent=2)
    return send_file(out_file, as_attachment=True)

@app.route("/api/autosave", methods=["POST"])
def autosave():
    req = request.json or {}
    pid = req.get("id")
    code = req.get("code")
    if not pid:
        return jsonify({"status": "error", "message": "Missing problem id"}), 400

    solutions = {}
    if os.path.exists(SOLUTIONS_FILE):
        try:
            with open(SOLUTIONS_FILE, "r", encoding="utf-8") as f:
                solutions = json.load(f)
        except Exception:
            solutions = {}

    current_status = solutions.get(pid, {}).get("status", "unsolved")
    solutions[pid] = {"code": code, "status": current_status}
    with open(SOLUTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(solutions, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "saved", "id": pid})

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("\n" + "=" * 50)
    print("  MeowCode IDE 2.0 đang khởi động...")
    print("=" * 50)
    
    # Khởi tạo problems từ PDF hoặc cache
    init_problems()
    
    print("\n" + "=" * 50)
    print("  ✅ MeowCode IDE chạy tại: http://127.0.0.1:5000")
    print("  🐱 Mở browser để tận hưởng code cùng mèo nha!")
    print("=" * 50 + "\n")
    app.run(port=5000, debug=False)
