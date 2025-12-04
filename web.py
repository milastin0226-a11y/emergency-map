import streamlit as st
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
import folium
import requests
import re
from math import radians, sin, cos, sqrt, atan2

# ==========================================
# 1. 설정 및 API 키
# ==========================================
st.set_page_config(page_title="수원시 안전 지도", page_icon="🚑", layout="wide")

try:
    GG_API_KEY = st.secrets["GG_API_KEY"]
    KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
except:
    GG_API_KEY = "42334a0cf97944c9b1ad81d6dd2dc17a"
    KAKAO_API_KEY = "72968d96a40f21a36d5d01d647daf602"

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
# 2. 핵심 함수 (계산 로직)
# ==========================================
def clean_name(name):
    # [장소] 같은 태그 제거하고 깔끔하게 만듦
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
            return float(item['y']), float(item['x']), item['place_name']
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
# 3. 화면 구성 및 상태 관리
# ==========================================

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

with st.sidebar:
    st.header("🔍 검색 설정")
    cat_name = st.selectbox("카테고리 선택", list(CATEGORY_CONFIG.keys()))
    selected_category = CATEGORY_CONFIG[cat_name]

    st.markdown("---")
    st.subheader("1. 📡 내 위치로 찾기 (GPS)")
    gps_loc = get_geolocation()
    
    if gps_loc:
        btn_gps = st.button("📍 내 위치(GPS)로 검색 실행")
        if btn_gps:
            st.session_state['my_lat'] = gps_loc['coords']['latitude']
            st.session_state['my_lon'] = gps_loc['coords']['longitude']
            # GPS로 찾았을 때의 이름은 "내위치"로 고정
            st.session_state['my_name'] = "내위치" 
            st.session_state['search_done'] = False 

    st.markdown("---")
    st.subheader("2. ⌨️ 직접 입력해서 찾기")
    user_input = st.text_input("위치 입력", placeholder="예: 수원역, 광교중앙역")
    btn_manual = st.button("🔍 주소로 검색 실행")

    if btn_manual and user_input:
        lat, lon, name = get_location_smart(user_input)
        if lat:
            st.session_state['my_lat'] = lat
            st.session_state['my_lon'] = lon
            # 직접 입력했을 때는 검색된 장소 이름(예: 아주대학교)을 저장
            st.session_state['my_name'] = clean_name(name) 
            st.session_state['search_done'] = False 
        else:
            st.error("위치를 찾을 수 없습니다.")

# ==========================================
# 4. 검색 로직 (상태 기반 실행)
# ==========================================

if st.session_state['my_lat'] and not st.session_state['search_done']:
    my_lat = st.session_state['my_lat']
    my_lon = st.session_state['my_lon']
    
    with st.spinner(f"📡 '{st.session_state['my_name']}' 주변 탐색 중..."):
        candidates = []
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
        
        st.session_state['candidates'] = sorted(candidates, key=lambda x: x['dist'])
        st.session_state['search_done'] = True

# ==========================================
# 5. 지도 그리기
# ==========================================

if st.session_state['search_done']:
    my_lat = st.session_state['my_lat']
    my_lon = st.session_state['my_lon']
    my_name = st.session_state['my_name'] # 설정된 출발지 이름
    candidates = st.session_state['candidates']

    st.success(f"📍 출발: {my_name} | 주변 {len(candidates)}개 발견")

    m = folium.Map(location=[my_lat, my_lon], zoom_start=15)
    folium.Marker(
        [my_lat, my_lon], 
        popup=f"출발: {my_name}", 
        icon=folium.Icon(color='black', icon='home')
    ).add_to(m)

    LIMIT_NAVI = 10 
    
    for i, item in enumerate(candidates):
        drive_str = "거리순 제외"
        if i < LIMIT_NAVI:
            if 'drive_time' not in item:
                time = get_navigation_time(my_lon, my_lat, item['lon'], item['lat'])
                item['drive_time'] = f"{int(time)}분" if time else "정보 없음"
            drive_str = item['drive_time']

        # [핵심 수정] sName에 저장해둔 출발지 이름(my_name)을 넣습니다.
        # GPS일 경우 "내위치", 직접 입력일 경우 "수원역" 등이 들어갑니다.
        map_link = f"https://map.kakao.com/?sName={my_name}&eName={item['name']}"
        
        conf = item['config']
        icon_prefix = 'fa' if conf['icon'] in ['fire-extinguisher', 'bell', 'snowflake-o', 'shield', 'user'] else 'glyphicon'

        popup_html = f"""
        <div style="width:200px">
            <b>{item['name']}</b><br>
            <span style="color:gray">{item['type']}</span><br>
            📏 {item['dist']*1000:.0f}m | 🚗 {drive_str}<br>
            <a href="{map_link}" target="_blank" 
                style="background-color:#FEE500; color:black; padding:5px; display:block; text-align:center; text-decoration:none; border-radius:5px; margin-top:5px;">
                길찾기 (From: {my_name})
            </a>
        </div>
        """
        folium.Marker(
            [item['lat'], item['lon']],
            popup=folium.Popup(popup_html, max_width=250),
            icon=folium.Icon(color=conf['color'], icon=conf['icon'], prefix=icon_prefix)
        ).add_to(m)

    st_folium(m, width=800, height=500)
