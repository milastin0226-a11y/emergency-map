import streamlit as st
from streamlit_folium import st_folium
import folium
import requests
import re
from math import radians, sin, cos, sqrt, atan2

# ==========================================
# 1. API 키 설정 (Streamlit Secrets 사용 권장)
# ==========================================
# 배포 시에는 Streamlit Cloud의 Secrets에 등록하는 것이 안전합니다.
try:
    GG_API_KEY = st.secrets["GG_API_KEY"]
    KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
except:
    # 로컬 테스트용 (제출해주신 키)
    GG_API_KEY = "42334a0cf97944c9b1ad81d6dd2dc17a"
    KAKAO_API_KEY = "72968d96a40f21a36d5d01d647daf602"

# ==========================================
# 2. 카테고리 설정
# ==========================================
CATEGORY_CONFIG = {
    "🏥 의료/건강": {
        "services": {
            "AED(제세동기)": {"url": "https://openapi.gg.go.kr/Aedstus", "icon": "heart", "color": "red", "radius": 1.0},
            "소아야간진료": {"url": "https://openapi.gg.go.kr/ChildNightTreatHosptl", "icon": "plus", "color": "green", "radius": 5.0}
        }
    },
    "🚨 안전/비상": {
        "services": {
            "안전비상벨": {"url": "https://openapi.gg.go.kr/Safeemrgncbell", "icon": "bell", "color": "orange", "radius": 0.5},
            "옥내소화전": {"url": "https://openapi.gg.go.kr/FirefgtFacltDevice", "icon": "fire-extinguisher", "color": "darkred", "radius": 0.5},
            "제설함": {"url": "https://openapi.gg.go.kr/ClsnowbxInstlStus", "icon": "snowflake-o", "color": "cadetblue", "radius": 1.0}
        }
    },
    "🏃 대피시설": {
        "services": {
            "민방위대피소": {"url": "https://openapi.gg.go.kr/CivilDefenseEvacuation", "icon": "shield", "color": "black", "radius": 2.0}
        }
    },
    "🚽 편의시설": {
        "services": {
            "공중화장실": {"url": "https://openapi.gg.go.kr/Publtolt", "icon": "info-sign", "color": "purple", "radius": 1.5}
        }
    }
}

# ==========================================
# 3. 핵심 함수들 (기존 로직 유지)
# ==========================================
def clean_name(name):
    return re.sub(r'\[.*?\]\s*', '', name)

def get_coords_from_address(address):
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    try:
        res = requests.get(url, headers=headers, params={"query": address}).json()
        if res.get('documents'):
            item = res['documents'][0]
            return float(item['y']), float(item['x'])
    except: pass
    return None, None

def get_location_smart(user_input):
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    search_query = user_input if "수원" in user_input else f"수원시 {user_input}"
    
    try:
        url_key = "https://dapi.kakao.com/v2/local/search/keyword.json"
        res = requests.get(url_key, headers=headers, params={"query": search_query}).json()
        if res.get('documents'):
            item = res['documents'][0]
            return float(item['y']), float(item['x']), f"[장소] {item['place_name']}"
    except: pass
    return None, None, None

def get_straight_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def get_navigation_time(origin_x, origin_y, dest_x, dest_y):
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}", "Content-Type": "application/json"}
    params = {"origin": f"{origin_x},{origin_y}", "destination": f"{dest_x},{dest_y}", "priority": "RECOMMEND"}
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get('routes'):
                return data['routes'][0]['summary']['duration'] / 60
    except: pass
    return None

def get_gg_data(url):
    params = {"KEY": GG_API_KEY, "Type": "json", "pIndex": 1, "pSize": 1000, "SIGUN_NM": "수원시"}
    try:
        res = requests.get(url, params=params).json()
        key = list(res.keys())[0]
        if "row" in res[key][1]: return res[key][1]["row"]
    except: pass
    return []

# ==========================================
# 4. Streamlit 웹 화면 구성
# ==========================================
st.set_page_config(page_title="수원시 통합 안전 지도", page_icon="🚑", layout="wide")

st.title("🚑 수원시 통합 안전 지도")
st.write("원하는 시설을 선택하고 현재 위치를 입력하면 가까운 곳을 찾아드립니다.")

# 사이드바 입력창
with st.sidebar:
    st.header("🔍 검색 설정")
    
    # 1. 카테고리 선택 (Selectbox)
    cat_name = st.selectbox("카테고리 선택", list(CATEGORY_CONFIG.keys()))
    selected_category = CATEGORY_CONFIG[cat_name]
    
    # 2. 위치 입력
    user_loc = st.text_input("현재 위치 입력", placeholder="예: 수원역, 아주대, 매탄동")
    
    search_btn = st.button("검색 시작", type="primary")

# 검색 버튼 클릭 시 실행
if search_btn and user_loc:
    with st.spinner(f"📡 '{user_loc}' 주변 분석 중..."):
        my_lat, my_lon, my_name = get_location_smart(user_loc)

        if not my_lat:
            st.error(f"❌ '{user_loc}' 위치를 찾을 수 없습니다. 정확한 지명이나 주소를 입력해주세요.")
        else:
            st.success(f"📍 기준 위치 확인: {my_name}")
            
            # 지도 생성
            m = folium.Map(location=[my_lat, my_lon], zoom_start=15)
            folium.Marker(
                [my_lat, my_lon], 
                popup=f"<b>출발: {clean_name(my_name)}</b>", 
                icon=folium.Icon(color='black', icon='home')
            ).add_to(m)

            candidates = []

            # 데이터 검색
            for svc_name, config in selected_category['services'].items():
                rows = get_gg_data(config['url'])
                
                for row in rows:
                    try:
                        name = row.get("INSTL_PLACE") or row.get("FACLT_NM") or row.get("EQUP_NM") or row.get("REFINE_ROADNM_ADDR")
                        if not name: name = "이름 미상"

                        lat, lon = None, None
                        if row.get("REFINE_WGS84_LAT"):
                            lat = float(row["REFINE_WGS84_LAT"])
                            lon = float(row["REFINE_WGS84_LOGT"])
                        elif row.get("REFINE_ROADNM_ADDR"):
                            lat, lon = get_coords_from_address(row["REFINE_ROADNM_ADDR"])

                        if lat and lon:
                            dist = get_straight_distance(my_lat, my_lon, lat, lon)
                            if dist <= config['radius']:
                                candidates.append({
                                    "name": name, "lat": lat, "lon": lon, "dist": dist,
                                    "type": svc_name, "config": config
                                })
                    except: continue

            # 결과 처리
            if candidates:
                candidates = sorted(candidates, key=lambda x: x['dist'])
                LIMIT_NAVI = 10  # 속도를 위해 10개만 내비 계산
                
                # 진행률 표시줄
                progress_bar = st.progress(0)
                
                for i, item in enumerate(candidates):
                    # 내비게이션 시간 계산 (상위 항목만)
                    drive_str = "거리순 제외"
                    if i < LIMIT_NAVI:
                        drive_time = get_navigation_time(my_lon, my_lat, item['lon'], item['lat'])
                        if drive_time:
                            drive_str = f"{int(drive_time)}분"
                    
                    # 진행률 업데이트
                    progress_bar.progress((i + 1) / len(candidates))

                    # 팝업 HTML 생성
                    start_name = clean_name(my_name)
                    map_link = f"https://map.kakao.com/?sName={start_name}&eName={item['name']}"
                    conf = item['config']
                    icon_prefix = 'fa' if conf['icon'] in ['fire-extinguisher', 'bell', 'snowflake-o', 'shield', 'user'] else 'glyphicon'

                    popup_html = f"""
                    <div style="width:180px">
                        <b>{item['name']}</b><br>
                        <span style="color:gray">{item['type']}</span><br>
                        📏 거리: {item['dist']*1000:.0f}m<br>
                        🚗 운전: {drive_str}<br>
                        <a href="{map_link}" target="_blank" 
                           style="background-color:#FEE500; color:black; padding:3px 8px; text-decoration:none; border-radius:5px; font-size:0.8em; display:block; margin-top:5px; text-align:center;">
                           카카오맵 길찾기
                        </a>
                    </div>
                    """

                    folium.Marker(
                        [item['lat'], item['lon']],
                        popup=folium.Popup(popup_html, max_width=250),
                        tooltip=f"{item['name']} ({drive_str})",
                        icon=folium.Icon(color=conf['color'], icon=conf['icon'], prefix=icon_prefix)
                    ).add_to(m)
                
                progress_bar.empty() # 진행바 삭제
                st_folium(m, width=800, height=500) # 지도 출력
                st.success(f"총 {len(candidates)}개의 시설을 찾았습니다.")
                
            else:
                st.warning("⚠️ 반경 내에 해당 시설이 없습니다.")
                st_folium(m, width=800, height=500)

elif search_btn and not user_loc:
    st.warning("위치를 입력해주세요!")
