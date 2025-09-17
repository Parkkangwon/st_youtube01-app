import streamlit as st
import yaml
import bcrypt
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from streamlit_extras.metric_cards import style_metric_cards

# Set page configuration first
st.set_page_config(
    page_title="YouTube 인기 동영상",
    page_icon="▶️",
    layout="wide"
)

# Now import other modules
import os
import json
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime

# Load environment variables
load_dotenv()

# Display Streamlit version for debugging
st.sidebar.write(f"Streamlit 버전: {st.__version__}")

# Custom CSS for better styling
st.markdown("""
    <style>
    .video-card {
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s, box-shadow 0.2s;
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        overflow: hidden;
        position: relative;
        cursor: pointer;
    }
    .video-card a {
        text-decoration: none;
        color: inherit;
    }
    .video-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
    }
    .video-card img {
        width: 100%;
        border-radius: 8px;
        margin-bottom: 10px;
        aspect-ratio: 16/9;
        object-fit: cover;
    }
    .video-title {
        font-weight: bold;
        font-size: 16px;
        margin: 5px 0;
        color: #0f1111;
    }
    .video-card h3 {
        font-size: 16px;
        margin: 8px 0;
        line-height: 1.4;
        height: 2.8em;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
    }
    
    .channel {
        color: #606060;
        font-size: 14px;
        margin: 3px 0;
    }
    .stats {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 10px;
        font-size: 11px;
        color: #606060;
    }
    .stats span {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        background: #f5f5f5;
        padding: 3px 8px;
        border-radius: 12px;
        white-space: nowrap;
        transition: background-color 0.2s;
    }
    .stats span:hover {
        background: #e0e0e0;
    }
    .stButton>button {
        width: 100%;
        border-radius: 20px;
        font-weight: bold;
        padding: 0.5rem 1rem;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize YouTube API
def get_youtube_service():
    try:
        # Streamlit secrets에서 YouTube API 키를 가져옵니다.
        if 'YOUTUBE_API_KEY' in st.secrets:
            api_key = st.secrets['YOUTUBE_API_KEY']
        else:
            # 하위 호환성을 위해 환경변수에서도 확인
            api_key = os.getenv('YOUTUBE_API_KEY')
            
        if not api_key:
            st.error("YouTube API 키를 찾을 수 없습니다. Streamlit secrets를 확인해주세요.")
            st.stop()
            
        return build('youtube', 'v3', developerKey=api_key)
    except Exception as e:
        st.error(f"YouTube API 초기화 중 오류가 발생했습니다: {str(e)}")
        st.stop()

# ISO 8601 기간을 읽기 쉬운 형식으로 변환
def format_duration(duration_str):
    import re
    
    # 정규식을 사용하여 시간, 분, 초 추출
    time_match = re.match(r'PT(?:H(\d+)H)?(?:M(\d+)M)?(?:S(\d+)S)?', duration_str)
    if not time_match:
        return "0:00"
    
    hours = int(time_match.group(1)) if time_match.group(1) else 0
    minutes = int(time_match.group(2)) if time_match.group(2) else 0
    seconds = int(time_match.group(3)) if time_match.group(3) else 0
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

# 게시 시간을 상대 시간으로 변환 (예: 3일 전)
def time_ago(published_at):
    from datetime import datetime, timezone
    import math
    
    # UTC 시간을 datetime 객체로 변환
    pub_time = datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = now - pub_time
    
    # 초, 분, 시간, 일, 주, 개월, 년 단위로 계산
    seconds = diff.total_seconds()
    minutes = seconds / 60
    hours = minutes / 60
    days = hours / 24
    weeks = days / 7
    months = days / 30.44  # 평균 월 길이
    years = days / 365.25  # 윤년 고려
    
    if years >= 1:
        return f"{math.floor(years)}년 전"
    elif months >= 1:
        return f"{math.floor(months)}개월 전"
    elif weeks >= 1:
        return f"{math.floor(weeks)}주 전"
    elif days >= 1:
        return f"{math.floor(days)}일 전"
    elif hours >= 1:
        return f"{math.floor(hours)}시간 전"
    elif minutes >= 1:
        return f"{math.floor(minutes)}분 전"
    else:
        return "방금 전"

# 숫자를 단위가 있는 문자열로 변환 (예: 1.2만)
def format_number(number):
    if number >= 10000:
        return f"{number/10000:.1f}만"
    elif number >= 1000:
        return f"{number/1000:.1f}천"
    else:
        return str(number)

# 인기 동영상 가져오기
def fetch_popular_videos():
    try:
        youtube = get_youtube_service()
        
        # 1. 인기 동영상 검색 시도
        st.sidebar.info("YouTube에서 인기 동영상을 검색 중입니다...")
        search_response = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            chart="mostPopular",
            maxResults=30,  # 30개 동영상 가져오기
            regionCode="KR"
        ).execute()
        
        if not search_response.get('items'):
            st.sidebar.warning("검색 결과가 없습니다. 다른 검색어를 시도해주세요.")
            return []
            
        videos = []
        
        # 2. 각 동영상의 상세 정보 처리
        for item in search_response.get('items', []):
            try:
                video_data = item
                video_id = video_data['id']
                
                # 필수 필드가 있는지 확인
                if not all(key in video_data['snippet'] for key in ['title', 'channelTitle', 'thumbnails']):
                    continue
                
                stats = video_data.get('statistics', {})
                details = video_data.get('contentDetails', {})
                
                video = {
                    'id': video_id,
                    'title': video_data['snippet']['title'],
                    'channel': video_data['snippet']['channelTitle'],
                    'thumbnail': video_data['snippet']['thumbnails']['high']['url'],
                    'view_count': int(stats.get('viewCount', 0)),
                    'like_count': int(stats.get('likeCount', 0)),
                    'comment_count': int(stats.get('commentCount', 0)),
                    'duration': format_duration(details.get('duration', 'PT0S')),
                    'published_at': video_data['snippet'].get('publishedAt', ''),
                    'url': f"https://www.youtube.com/watch?v={video_id}",
                    'category_id': video_data['snippet'].get('categoryId', '')
                }
                videos.append(video)
                
            except Exception as video_error:
                st.sidebar.warning(f"동영상 정보를 가져오는 중 오류 발생: {str(video_error)[:100]}...")
                continue
                
        if not videos:
            st.sidebar.error("동영상을 불러오는 데 실패했습니다. 나중에 다시 시도해주세요.")
            return []
            
        return videos
        
    except HttpError as e:
        error_details = json.loads(e.content).get('error', {})
        error_msg = error_details.get('message', str(e))
        st.sidebar.error(f"YouTube API 오류: {error_msg}")
        if 'quota' in str(e).lower():
            st.sidebar.error("API 할당량을 초과했습니다. 내일 다시 시도해주세요.")
        return []
        
    except Exception as e:
        st.sidebar.error(f"예상치 못한 오류가 발생했습니다: {str(e)[:200]}")
        return []

# 메인 앱
# YouTube 카테고리 가져오기
def get_video_categories():
    try:
        youtube = get_youtube_service()
        categories_response = youtube.videoCategories().list(
            part="snippet",
            regionCode="KR"
        ).execute()
        
        categories = {}
        for item in categories_response.get('items', []):
            categories[item['id']] = item['snippet']['title']
            
        return categories
    except Exception as e:
        st.sidebar.error(f"카테고리를 불러오는 중 오류가 발생했습니다: {str(e)}")
        return {}

# 동영상 필터링 함수
def filter_videos(videos, search_query, selected_categories, view_count_range):
    filtered = videos
    
    # 제목 또는 채널명으로 필터링
    if search_query:
        search_query = search_query.lower()
        filtered = [v for v in filtered 
                   if search_query in v['title'].lower() 
                   or search_query in v['channel'].lower()]
    
    # 카테고리로 필터링
    if selected_categories:
        filtered = [v for v in filtered 
                   if v.get('category_id') in selected_categories]
    
    # 조회수 범위로 필터링
    if view_count_range:
        min_views, max_views = view_count_range
        filtered = [v for v in filtered 
                   if min_views <= v['view_count'] <= max_views]
    
    return filtered

def main():
    st.title("🎬 한국 인기 YouTube 동영상")
    st.markdown("---")
    
    # 사이드바 필터
    st.sidebar.markdown("### 🔍 검색 및 필터")
    
    # 검색어 입력
    search_query = st.sidebar.text_input("채널명 또는 제목으로 검색")
    
    # 카테고리 필터
    st.sidebar.markdown("### 🗂️ 카테고리")
    categories = get_video_categories()
    selected_categories = st.sidebar.multiselect(
        "카테고리 선택 (여러 개 선택 가능)",
        options=list(categories.values()),
        default=[]
    )
    
    # 카테고리 이름을 ID로 변환
    selected_category_ids = [
        cid for cid, name in categories.items() 
        if name in selected_categories
    ]
    
    # 조회수 범위 필터
    st.sidebar.markdown("### 🔢 조회수 범위")
    view_count_range = st.sidebar.slider(
        "조회수 범위 선택 (만 회)",
        0, 10000,  # 최소 0회 ~ 최대 1억 회 (1만 단위)
        (0, 1000),  # 기본값: 0~1000만 회
        step=10,    # 10만 단위로 조정
        format="%d만"
    )
    # 실제 값으로 변환 (만 회 단위 -> 회 단위)
    view_count_range = (view_count_range[0] * 10000, view_count_range[1] * 10000)
    
    # 새로고침 버튼
    if st.sidebar.button("🔄 새로고침"):
        st.rerun()
    
    st.markdown("### 🎥 현재 인기 동영상")
    
    # 로딩 인디케이터
    with st.spinner('인기 동영상을 불러오는 중...'):
        videos = fetch_popular_videos()
    
    if not videos:
        st.warning("동영상을 불러오는 데 실패했습니다. 나중에 다시 시도해주세요.")
        return
    
    # 동영상 필터링 적용
    filtered_videos = filter_videos(
        videos, 
        search_query, 
        selected_category_ids,
        view_count_range
    )
    
    # 필터링된 동영상이 없는 경우 메시지 표시
    if not filtered_videos and (search_query or selected_categories or view_count_range[0] > 0 or view_count_range[1] < 100000000):
        st.warning("조건에 맞는 동영상이 없습니다. 필터를 조정해보세요.")
        return
    
    # 동영상 그리드 레이아웃
    cols = st.columns(3)
    
    for i, video in enumerate(filtered_videos):
        with cols[i % 3]:
            st.markdown(
                f"""
                <div class="video-card" onclick="window.open('{video['url']}', '_blank')">
                    <a href="{video['url']}" target="_blank">
                        <img src="{video['thumbnail']}" alt="{video['title']}">
                        <h3>{video['title']}</h3>
                    </a>
                    <p class="channel">{video['channel']}</p>
                    <div class="stats">
                        <span>👁️ {format_number(video['view_count'])}</span>
                        <span>👍 {format_number(video['like_count'])}</span>
                        <span>💬 {format_number(video['comment_count'])}</span>
                        <span>⏱️ {video['duration']}</span>
                        <span>📅 {time_ago(video['published_at'])}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
    
    # 하단 여백 추가
    st.markdown("<br><br>", unsafe_allow_html=True)

# 인증 설정 로드
def load_auth_config():
    with open('.streamlit/config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
    return config

# 인증자 생성
def get_authenticator():
    config = load_auth_config()
    authenticator = stauth.Authenticate(
        config['credentials'],
        'youtube_app',
        'auth',
        cookie_expiry_days=30,
        preauthorized=config.get('preauthorized', [])
    )
    return authenticator

# 관리자 페이지
def admin_page():
    st.title("관리자 페이지")
    st.write("관리자만 접근할 수 있는 페이지입니다.")
    
    # 사용자 관리 섹션
    with st.expander("사용자 관리"):
        st.subheader("사용자 목록")
        config = load_auth_config()
        users = config['credentials']['usernames']
        
        # 사용자 목록 표시
        for username, user_info in users.items():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                st.write(f"**{user_info['name']}**")
            with col2:
                st.write(f"이메일: {user_info['email']}")
            with col3:
                if st.button(f"삭제 {username}", key=f"del_{username}"):
                    if username != 'admin':  # 관리자 계정은 삭제 불가
                        del users[username]
                        with open('.streamlit/config.yaml', 'w') as file:
                            yaml.dump(config, file, default_flow_style=False)
                        st.success(f"{username} 사용자가 삭제되었습니다.")
                        st.rerun()
                    else:
                        st.error("관리자 계정은 삭제할 수 없습니다.")
        
        # 새 사용자 추가
        st.subheader("새 사용자 추가")
        with st.form("add_user"):
            new_username = st.text_input("사용자명")
            new_name = st.text_input("이름")
            new_email = st.text_input("이메일")
            new_password = st.text_input("비밀번호", type="password")
            new_role = st.selectbox("역할", ["user", "admin"])
            
            if st.form_submit_button("사용자 추가"):
                if new_username and new_name and new_email and new_password:
                    if new_username not in users:
                        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        users[new_username] = {
                            'email': new_email,
                            'name': new_name,
                            'password': hashed_password,
                            'role': new_role
                        }
                        with open('.streamlit/config.yaml', 'w') as file:
                            yaml.dump(config, file, default_flow_style=False)
                        st.success(f"{new_username} 사용자가 추가되었습니다.")
                        st.rerun()
                    else:
                        st.error("이미 존재하는 사용자명입니다.")
                else:
                    st.error("모든 필드를 입력해주세요.")

# 메인 앱
if __name__ == "__main__":
    # 인증자 초기화
    authenticator = get_authenticator()
    
    # 로그인 상태 확인
    if 'authentication_status' not in st.session_state:
        st.session_state['authentication_status'] = None
    
    # 로그인 페이지
    if not st.session_state.get('authentication_status'):
        st.title("YouTube 인기 동영상 - 로그인")
        
        # 로그인 폼
        name, authentication_status, username = authenticator.login('Login', 'main')
        
        if authentication_status == False:
            st.error('아이디/비밀번호가 올바르지 않습니다.')
        elif authentication_status == None:
            st.warning('아이디와 비밀번호를 입력해주세요.')
    
    # 로그인 성공 시 메인 페이지 또는 관리자 페이지 표시
    elif st.session_state['authentication_status']:
        # 사이드바에 로그아웃 버튼 추가
        authenticator.logout('로그아웃', 'sidebar')
        
        # 관리자 계정인 경우 관리자 페이지 링크 표시
        config = load_auth_config()
        user_role = config['credentials']['usernames'][st.session_state['username']]['role']
        
        if user_role == 'admin':
            if st.sidebar.button("관리자 페이지"):
                st.session_state['show_admin'] = not st.session_state.get('show_admin', False)
            
            if st.session_state.get('show_admin'):
                admin_page()
            else:
                main()
        else:
            main()
