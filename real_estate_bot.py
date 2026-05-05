import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import time
import concurrent.futures

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from dotenv import load_dotenv
import google.generativeai as genai

# 로컬 .env 파일 로드 (환경 변수 설정)
load_dotenv()

# docx 관련 임포트 삭제됨

# ==========================================
# 1. 설정 (Settings)
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_DEFAULT_OR_TEST_KEY")
SAVE_DIR = os.getenv("SAVE_DIR", "reports")
MAX_NEWS_COUNT = 10

# 이메일 설정
EMAIL_SENDER = os.getenv("EMAIL_USER")       # 보내는 사람 (본인 지메일)
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD") # 구글 앱 비밀번호
EMAIL_RECEIVER = "bamnamoo@gmail.com"        # 받는 사람

# 키워드 설정 (부동산 핵심 키워드)
INCLUDE_KEYWORDS = [
    '부동산', '아파트', '집값', '분양', '재건축', '재개발', '전세', '월세', 
    '매매', '주택', 'LH', 'SH', '청약', '임대', '건설', '공급', '규제', 
    '대출', '금리', '국토부', '빌라', '오피스텔', '단지', 'GTX', '공공주택',
    '주거', '경매', '공시지가', '매수', '매도', '수도권', '시장동향'
]
# 제외 키워드 (부동산과 무관한 노이즈 제거)
EXCLUDE_KEYWORDS = [
    '사고', '화재', '경찰', '살인', '폭행', '충돌', '추락', '폭발', '사망', 
    '부상', '피해', '혐의', '구속', '검거', '사기', '횡령', '음주', '마약',
    '정전', '구조', '급락', '증시', '삼성전자', '코스피', '코스닥', '공모주',
    '나스닥', '뉴욕증시', '환율', '반도체', '배터리', '자동차', '전기차',
    '아이폰', '갤럭시', '물가', '금통위', '한은', '가계부채', '자영업', 
    '소상공인', '편의점', '식당', '카페', '프랜차이즈', '최저임금', '노동계', 
    '알바', '영업이익', '매출', '소비자', '물가상승', '인건비', '삼전', '주식', '주가'
]

# ==========================================
# 2. 뉴스 수집 로봇 (Crawler)
# ==========================================
def get_ranking_news(date_str):
    # 변경: 경제 내 '부동산' 섹션 랭킹 (이게 가장 확실합니다)
    url = f"https://news.naver.com/main/ranking/popularDay.naver?sectionId=101&subSectionId=261&date={date_str}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        news_list = []
        
        for office_list in soup.select('.rankingnews_box'):
            for item in office_list.select('.rankingnews_list > li'):
                title_tag = item.select_one('a')
                if not title_tag: continue
                
                title = title_tag.get_text(strip=True)
                link = title_tag['href']
                
                if link.startswith('/'):
                    link = "https://news.naver.com" + link
                
                is_real_estate = any(k in title for k in INCLUDE_KEYWORDS)
                is_excluded = any(k in title for k in EXCLUDE_KEYWORDS)
                
                if is_real_estate and not is_excluded:
                    news_list.append({"title": title, "link": link})
        
        return news_list
    except Exception as e:
        print(f"[{date_str}] 뉴스 목록 수집 중 오류: {e}")
        return []

def get_article_content(url):
    """뉴스 원문 내용을 추출"""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        content_tag = soup.select_one('#dic_area') or soup.select_one('#articleBodyContents')
        if content_tag:
            for s in content_tag.select('script, style, .article_footer, .img_desc'):
                s.decompose()
            return content_tag.get_text(separator="\n", strip=True)
        return "본문을 불러올 수 없습니다."
    except Exception as e:
        return f"원문 추출 오류: {e}"

# ==========================================
# 3. AI 분석 로봇 (Gemini 3)
# ==========================================
def analyze_with_gemini(news_data):
    """Gemini SDK를 사용하여 블로그 원고와 요약 리스트를 생성"""
    print("AI가 블로그 포스팅 원고와 요약을 작성 중입니다...")
    
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_DEFAULT_OR_TEST_KEY":
        return "AI 분석 오류: API 키가 설정되지 않았습니다."

    try:
        # API 설정
        genai.configure(api_key=GEMINI_API_KEY)
        # 안정적인 모델명 사용
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        context_text = ""
        for i, item in enumerate(news_data):
            content_snippet = item['content'][:2000] 
            context_text += f"\n[뉴스 {i+1}]\n제목: {item['title']}\n링크: {item['link']}\n내용: {content_snippet}\n"
        
        prompt = f"""
당신은 부동산 전문 분석가입니다. 아래 제공된 뉴스 목록 중 **부동산 시장 흐름, 정책, 투자, 분양**과 직접적인 관련이 있는 뉴스만 선별하여 분석하세요.

[필터링 규칙]
- 단순 화재, 정전, 고독사, 살인사건 등 '사회적 사건/사고'는 부동산 가치 분석에 불필요하므로 절대 포함하지 마세요.
- 연예인 집 공개, 단순 가십성 뉴스도 제외하세요.
- 오직 시장 전망, 정책 변화, 신도시 소식, 재개발 현황 등 '경제적 가치'가 있는 뉴스만 최대 10개 선택하세요.

    [작성 항목]
    1. 오늘의 주요 뉴스 및 요약 링크: 
       각 뉴스(1~10)에 대해 아래 형식을 엄격히 지켜 작성하세요.
       형식:
       [번호]. [뉴스 제목]
       🔗 [뉴스 링크]
       📝 요약: [해당 뉴스의 핵심 내용을 정확히 2줄로 요약]

    2. 블로그 포스팅 원고: 독자들이 흥미를 가질만한 제목, 서론, 본문(흐름 분석 및 전략), 결론, 해시태그를 포함한 완성된 블로그 원고.

    구분선인 '---BLOG_START---' 를 사용하여 1번 항목과 2번 항목을 구분해 주세요.

    [입력 데이터]
    {context_text}
        """
        response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        # SSL 에러나 일시적인 통신 오류 시 재시도 로직 추가 고려 가능
        # 여기서는 단순 에러 메시지 반환 대신 재시도를 1회 시도해봅니다.
        print(f"AI 호출 중 오류 발생 ({e}), 5초 후 재시도합니다...")
        time.sleep(5)
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as retry_e:
            return f"AI 분석 오류 (재시도 실패): {retry_e}"

def save_as_html(full_path, report_content):
    """보고서 내용을 미려한 스타일의 HTML 파일로 저장"""
    try:
        import re
        
        # 더 세련된 스타일을 위해 섹션별로 구분
        sections = report_content.split('============================================================')
        
        formatted_content = ""
        for i, section in enumerate(sections):
            if not section.strip(): continue
            
            section_clean = section.strip()
            
            # URL을 클릭 가능한 링크로 변환하는 함수
            def make_clickable(text):
                # 마크다운 링크 [제목](링크) 처리
                text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
                # 일반 URL 처리 (이미 <a> 태그 내부에 있는 것은 제외)
                text = re.sub(r'(?<!href=")(https?://[^\s<]+)', r'<a href="\1" target="_blank">\1</a>', text)
                return text

            if "1단계" in section_clean:
                title = "1단계: 오늘의 주요 뉴스 및 요약 링크"
                content = section_clean.split(']')[1] if ']' in section_clean else section_clean
                content_html = make_clickable(content.strip().replace("\n", "<br>"))
                formatted_content += f'<div class="section"><h2>{title}</h2><div class="content">{content_html}</div></div>'
            elif "2단계" in section_clean:
                title = "2단계: 블로그 포스팅 원고"
                content = section_clean.split(']')[1] if ']' in section_clean else section_clean
                
                content_html = content.strip()
                content_html = re.sub(r'### (.*)', r'<h3>\1</h3>', content_html)
                content_html = re.sub(r'## (.*)', r'<h2>\1</h2>', content_html)
                content_html = re.sub(r'# (.*)', r'<h1>\1</h1>', content_html)
                content_html = make_clickable(content_html.replace('\n', '<br>'))
                
                formatted_content += f'<div class="section blog-post"><h2>{title}</h2><div class="content">{content_html}</div></div>'
            else:
                formatted_content += f'<div class="header-info">{make_clickable(section_clean.replace("\n", "<br>"))}</div>'

        html_template = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>오늘의 부동산 포스트</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap" rel="stylesheet">
    <style>
        body {{
            font-family: 'Noto Sans KR', sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            background-color: #f8f9fa;
        }}
        .container {{
            background-color: #fff;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }}
        h1 {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; }}
        h2 {{ color: #202124; margin-top: 30px; border-left: 5px solid #1a73e8; padding-left: 15px; }}
        h3 {{ color: #444; margin-top: 20px; }}
        .section {{ margin-bottom: 40px; }}
        .content {{ background: #fff; padding: 10px 0; }}
        .header-info {{ font-size: 0.9em; color: #666; margin-bottom: 20px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
        .footer {{ margin-top: 50px; text-align: center; font-size: 0.8em; color: #999; border-top: 1px solid #eee; padding-top: 20px; }}
        a {{ color: #1a73e8; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .blog-post {{ background-color: #fff; }}
    </style>
</head>
<body>
    <div class="container">
        {formatted_content}
        <div class="footer">
            제작: 니크의 부동산 정보 | 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(html_template)
        return True
    except Exception as e:
        print(f"HTML 저장 중 오류: {e}")
        return False

def send_email(subject, body, attachment_path=None):
    """분석 리포트를 이메일로 발송 (첨부파일 지원)"""
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("공지: 이메일 설정(EMAIL_USER, EMAIL_PASSWORD)이 되어있지 않아 메일 발송을 건너뜁니다.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        msg['Subject'] = Header(subject, 'utf-8')
        
        # 메일 본문 추가
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # 첨부파일 추가 (HTML 문서 등)
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                
                encoders.encode_base64(part)
                
                # 파일명 설정
                filename = os.path.basename(attachment_path)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={Header(filename, 'utf-8').encode()}",
                )
                msg.attach(part)
                print(f"첨부파일 추가 성공: {filename}")
            except Exception as attachment_e:
                print(f"첨부파일 추가 중 오류: {attachment_e}")

        # SMTP 서버 연결 (Gmail 기준) - 타임아웃 15초 추가
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        
        print(f"성공! 이메일이 발송되었습니다: {EMAIL_RECEIVER}")
        return True
    except Exception as e:
        print(f"이메일 발송 중 오류: {e}")
        return False

# ==========================================
# 4. 메인 실행 (Main)
# ==========================================
def main():
    print("부동산 뉴스 자동 분석 프로그램을 시작합니다.")
    
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    dates = [today.strftime('%Y%m%d'), yesterday.strftime('%Y%m%d')]
    
    collected_news = []
    seen_links = set()
    
    for date_str in dates:
        print(f"날짜 {date_str} 경제 랭킹 뉴스를 수집 중...")
        news_items = get_ranking_news(date_str)
        
        for item in news_items:
            if item['link'] not in seen_links:
                seen_links.add(item['link'])
                collected_news.append(item)
            
            if len(collected_news) >= MAX_NEWS_COUNT:
                break
        if len(collected_news) >= MAX_NEWS_COUNT:
            break

    if not collected_news:
        print("분석할 부동산 뉴스를 찾지 못했습니다.")
        return

    print(f"총 {len(collected_news)}개의 뉴스 원문을 병렬로 추출합니다...", flush=True)
    
    def fetch_and_update(news_item, index, total):
        try:
            print(f"[{index+1}/{total}] 본문 추출 중: {news_item['title'][:30]}...", flush=True)
        except UnicodeEncodeError:
            print(f"[{index+1}/{total}] 본문 추출 중: [제목 인코딩 오류]...", flush=True)
        news_item['content'] = get_article_content(news_item['link'])
        return news_item

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # 인덱스와 함께 작업 제출
        future_to_news = {executor.submit(fetch_and_update, item, i, len(collected_news)): i for i, item in enumerate(collected_news)}
        for future in concurrent.futures.as_completed(future_to_news):
            # 작업 완료 대기 (결과는 이미 item['content']에 반영됨)
            try:
                future.result()
            except Exception as e:
                print(f"추출 중 에러 발생: {e}")

    # AI 분석 (요약 + 블로그 스타일)
    ai_output = analyze_with_gemini(collected_news)
    
    # 요약과 블로그 본문 분리
    if "---BLOG_START---" in ai_output:
        summaries_part, blog_post = ai_output.split("---BLOG_START---")
    else:
        summaries_part = "요약을 생성하지 못했습니다."
        blog_post = ai_output

    # 최종 리포트 조립
    print("블로그 스타일로 최종 보고서를 생성 중입니다...")
    report = f"📅 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    report += "🚀 본 파일은 블로그 포스팅에 바로 사용할 수 있도록 구성되었습니다.\n\n"
    
    report += "="*60 + "\n"
    report += "          [ 1단계: 오늘의 주요 뉴스 및 요약 링크 ]\n"
    report += "="*60 + "\n\n"
    
    # AI가 생성한 뉴스별 [제목/링크/요약] 리스트 배치
    report += summaries_part.strip() + "\n"
    
    report += "\n" + "="*60 + "\n"
    report += "          [ 2단계: 블로그 포스팅 원고 ]\n"
    report += "="*60 + "\n\n"
    report += blog_post.strip()
    
    report += "\n\n" + "-"*60 + "\n"
    report += "제작: 니크의 부동산 정보\n"

    # 저장
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
    
    base_name = f"오늘의부동산포스트_{today.strftime('%Y%m%d_%H%M%S')}"
    
    # 1. TXT 저장
    txt_path = os.path.join(SAVE_DIR, base_name + ".txt")
    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n성공! TXT 보고서가 저장되었습니다: {txt_path}")
    except Exception as e:
        print(f"TXT 저장 중 오류: {e}")
        
    # 2. HTML 저장
    html_path = os.path.join(SAVE_DIR, base_name + ".html")
    if save_as_html(html_path, report):
        print(f"성공! HTML 보고서가 저장되었습니다: {html_path}")

    # 3. 이메일 발송
    email_subject = f"[오늘의 부동산 포스트] {today.strftime('%Y-%m-%d')} 분석 리포트"
    send_email(email_subject, report, attachment_path=html_path)

if __name__ == "__main__":
    main()
