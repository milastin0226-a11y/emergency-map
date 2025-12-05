import streamlit as st
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
import folium
import requests
import re
from math import radians, sin, cos, sqrt, atan2

# ==========================================
# 1. 페이지 설정 및 API 키
# ==========================================
st.set_page_config(page_title="수원시 안전 지도", page_icon="🚑", layout="wide")

# API 키 설정 (Secrets가 없으면 코드 내 키 사용)
try:
    GG_API_KEY = st.secrets["GG_API_KEY"]
    KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
except:
    GG_API_KEY = "42334a0cf97944c9b1ad81d6dd2dc17a"
    KAKAO_API_KEY = "72968d96a40f21a36d5d01d647daf602"

# ==========================================
# 2. 카테고리 설정 (새로 주신 코드 반영)
# ==========================================
CATEGORY_CONFIG = {
    "1": {
        "name": "🏥 의료/건강",
        "services": {
            "AED(제세동기)": {"url": "https://openapi.gg.go.kr/Aedstus", "icon": "heart", "color": "red", "radius": 1.0},
            "소아야간진료": {"url": "https://openapi.gg.go.kr/ChildNightTreatHosptl", "icon": "plus", "color": "green", "radius": 5.0}
        }
    },
    "2": {
        "name": "🚨 안전/비상",
        "services": {
            "안전비상벨": {"url": "https://openapi.gg.go.kr/Safeemrgncbell", "icon": "bell", "color": "orange", "radius": 0.5},
            "옥내소화전": {"url": "https://openapi.gg.go.kr/FirefgtFacltDevice", "icon": "fire-extinguisher", "color": "darkred", "radius": 0.5},
            "제설함": {"url": "https://openapi.gg.go.kr/ClsnowbxInstlStus", "icon": "snowflake-o", "color": "cadetblue", "radius": 1.0}
        }
    },
    "3": {
        "name": "🏃 대피시설",
        "services": {
            "민방위대피소": {"url": "https://openapi.gg.go.kr/CivilDefenseEvacuation", "icon": "shield", "color": "black", "radius": 2.0}
        }
    },
    "4": {
        "name": "🚽 편의시설",
        "services": {
            "공중화장실": {"url": "https://openapi.gg.go.kr/Publtolt", "icon": "info-sign", "color": "purple", "radius": 1.5}
        }
    }
}

# ==========================================
# 3. 핵심 함수들 (새 코드 로직 적용)
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
    if "수원" not in user_input:
        search_query = f"수원시 {user_input}"
    else:
        search_query = user_input
        
    try:
        url_key = "https://dapi.kakao.com/v2/local/search/keyword.json"
        res = requests.get(url_key, headers=headers, params={"query": search_query}).json()
        if res.get('documents'):
            item = res['documents'][0]
            # 장소명도 함께 반환
            return float(item['y']), float(item['x']), f"{item['place_name']}"
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

def get_walking_time(dist_km):
    return dist_km * 15 # 시속 4km 기준

def get_gg_data(url):
    params = {"KEY": GG_API_KEY, "Type": "json", "pIndex": 1, "pSize": 1000, "SIGUN_NM": "수원시"}
    try:
        res = requests.get(url, params=params).json()
        key = list(res.keys())[0]
        if "row" in res[key][1]: return res[key][1]["row"]
    except: pass
    return []

# ==========================================
# 4. 화면 구성 및 상태 관리 (세션 스테이트)
# ==========================================

# 상태값 초기화 (새로고침 되어도 데이터 유지)
if 'search_done' not in st.session_state:
    st.session_state['search_done'] = False
if 'my_lat' not in st.session_state:
    st.session_state['my_lat'] = None
if 'my_lon' not in st.session_state:
    st.session_state['my_lon'] = None
if 'my_name' not in st.session_state:
    st.session_state['my_name'] = ""
if 'candidates' not in st.session_state:
    st.session_state['candidates'] = []

st.title("🚑 수원시 통합 안전 지도")
st.write("GPS로 내 위치를 찾거나, 직접 입력해서 주변 시설을 검색하세요.")

# 사이드바 구성
with st.sidebar:
    st.header("🔍 검색 설정")
    
    # 1. 카테고리 선택 (이름으로 선택하게 변경)
    # 딕셔너리를 보기 좋게 이름:키 형태로 매핑
    category_options = {val['name']: key for key, val in CATEGORY_CONFIG.items()}
    selected_name = st.selectbox("카테고리 선택", list(category_options.keys()))
    
    # 선택된 카테고리 정보 가져오기
    selected_key = category_options[selected_name]
    selected_category = CATEGORY_CONFIG[selected_key]
    
    st.markdown("---")
    st.subheader("1. 📡 내 위치로 찾기 (GPS)")
    
    # GPS 정보 가져오기 (히든 처리됨)
    gps_loc = get_geolocation()
    
    if gps_loc:
        btn_gps = st.button("📍 내 위치(GPS)로 검색 실행")
        if btn_gps:
            st.session_state['my_lat'] = gps_loc['coords']['latitude']
            st.session_state['my_lon'] = gps_loc['coords']['longitude']
            # [중요] GPS 사용 시 출발지 이름을 '내위치'로 설정
            st.session_state['my_name'] = "내위치"
            st.session_state['search_done'] = False # 새 좌표이므로 검색 다시 해야 함

    st.markdown("---")
    st.subheader("2. ⌨️ 직접 입력해서 찾기")
    user_input = st.text_input("위치 입력", placeholder="예: 수원역, 매탄동")
    btn_manual = st.button("🔍 주소로 검색 실행")

    if btn_manual and user_input:
        lat, lon, name = get_location_smart(user_input)
        if lat:
            st.session_state['my_lat'] = lat
            st.session_state['my_lon'] = lon
            # [중요] 직접 입력 시 출발지 이름을 '검색된 장소명'으로 설정
            st.session_state['my_name'] = clean_name(name)
            st.session_state['search_done'] = False
        else:
            st.error("위치를 찾을 수 없습니다.")

# ==========================================
# 5. 검색 로직 (조건 만족 시 실행)
# ==========================================

# 좌표는 있는데 아직 검색 결과가 없다면 -> 데이터 수집 시작
if st.session_state['my_lat'] and not st.session_state['search_done']:
    my_lat = st.session_state['my_lat']
    my_lon = st.session_state['my_lon']
    
    with st.spinner(f"📡 '{st.session_state['my_name']}' 기준으로 주변 시설 탐색 중..."):
        candidates = []
        for svc_name, config in selected_category['services'].items():
            rows = get_gg_data(config['url'])
            
            for row in rows:
                try:
                    name = row.get("INSTL_PLACE") or row.get("FACLT_NM") or row.get("EQUP_NM") or row.get("REFINE_ROADNM_ADDR")
                    if not name: name = "이름 미상"
                    
                    lat, lon = None, None
                    # 좌표 우선 확인
                    if row.get("REFINE_WGS84_LAT"):
                        try:
                            lat = float(row["REFINE_WGS84_LAT"])
                            lon = float(row["REFINE_WGS84_LOGT"])
                        except: pass
                    
                    # 좌표 없으면 주소로 찾기
                    if lat is None:
                        addr = row.get("REFINE_ROADNM_ADDR") or row.get("REFINE_LOTNO_ADDR")
                        if addr:
                            lat, lon = get_coords_from_address(addr)

                    if lat and lon:
                        dist = get_straight_distance(my_lat, my_lon, lat, lon)
                        if dist <= config['radius']:
                            candidates.append({
                                "name": name, "lat": lat, "lon": lon, "dist": dist,
                                "type": svc_name, "config": config
                            })
                except: continue
        
        # 결과 저장
        st.session_state['candidates'] = sorted(candidates, key=lambda x: x['dist'])
        st.session_state['search_done'] = True

# ==========================================
# 6. 결과 출력 및 지도 생성
# ==========================================

if st.session_state['search_done']:
    my_lat = st.session_state['my_lat']
    my_lon = st.session_state['my_lon']
    my_name = st.session_state['my_name'] # 설정된 출발지 이름
    candidates = st.session_state['candidates']

    st.success(f"📍 출발: {my_name} | 주변 {len(candidates)}개 발견")

    # 지도 생성
    m = folium.Map(location=[my_lat, my_lon], zoom_start=15)
    folium.Marker(
        [my_lat, my_lon], 
        popup=f"<b>출발: {my_name}</b>", 
        icon=folium.Icon(color='black', icon='home')
    ).add_to(m)

    LIMIT_NAVI = 15 # 요청하신 대로 15개
    
    for i, item in enumerate(candidates):
        # 도보 시간
        walk_time = get_walking_time(item['dist'])
        walk_str = f"{int(walk_time)}분" if walk_time < 60 else f"{walk_time/60:.1f}시간"

        # 운전 시간 (API 호출)
        drive_str = "정보 없음"
        if i < LIMIT_NAVI:
            if 'drive_time' not in item:
                time = get_navigation_time(my_lon, my_lat, item['lon'], item['lat'])
                item['drive_time'] = f"{int(time)}분" if time else "정보 없음"
            drive_str = item['drive_time']
        else:
            drive_str = "거리순 제외"

        # [핵심] Kakao Map 링크 생성 (동적 출발지 반영)
        start_name = clean_name(my_name)
        end_name = item['name']
        map_link = f"https://map.kakao.com/?sName={start_name}&eName={end_name}"
        
        conf = item['config']
        icon_prefix = 'fa' if conf['icon'] in ['fire-extinguisher', 'bell', 'snowflake-o', 'shield', 'user'] else 'glyphicon'

        popup_html = f"""
        <div style="width:200px">
            <b>{item['name']}</b><br>
            <span style="color:gray">{item['type']}</span><br>
            <hr style="margin:5px 0">
            📏 {item['dist']*1000:.0f}m<br>
            🏃 도보: {walk_str}<br>
            🚗 운전: {drive_str}<br>
            <hr style="margin:5px 0">
            <a href="{map_link}" target="_blank" 
                style="background-color:#FEE500; color:black; padding:5px 10px; text-decoration:none; border-radius:5px; font-weight:bold; font-size:0.9em; display:block; text-align:center;">
                카카오맵 길찾기 (From: {start_name})
            </a>
        </div>
        """
        folium.Marker(
            [item['lat'], item['lon']],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{item['name']} (도보 {walk_str})",
            icon=folium.Icon(color=conf['color'], icon=conf['icon'], prefix=icon_prefix)
        ).add_to(m)

    if not candidates:
        st.warning("⚠️ 선택하신 반경 내에 해당 시설이 없습니다.")

    st_folium(m, width=800, height=600)
