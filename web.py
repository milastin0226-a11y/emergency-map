import streamlit as st
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
import folium
import requests
from math import radians, sin, cos, sqrt, atan2

# [변경 전]
# GG_API_KEY = "4233... (원래 키)"
# KAKAO_API_KEY = "7296... (원래 키)"

# [변경 후] 이렇게 바꿔주세요!
import streamlit as st 

# Streamlit의 비밀 보관함(Secrets)에서 키를 가져옴
try:
    GG_API_KEY = st.secrets["GG_API_KEY"]
    KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
except:
    # (내 컴퓨터에서 테스트할 때를 위해 예비용으로 남겨둠)
    GG_API_KEY = "42334a0cf97944c9b1ad81d6dd2dc17a"
    KAKAO_API_KEY = "72968d96a40f21a36d5d01d647daf602"

# ==========================================
# 2. 계산 함수들 (기존 로직 유지)
# ==========================================
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
    except:
        pass
    return None

def get_gg_data(url):
    params = {"KEY": GG_API_KEY, "Type": "json", "pIndex": 1, "pSize": 1000, "SIGUN_NM": "수원시"}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        key = list(data.keys())[0]
        if "row" in data[key][1]: return data[key][1]["row"]
    except:
        pass
    return []

# ==========================================
# 3. 화면 구성 (Streamlit)
# ==========================================
st.set_page_config(page_title="수원시 응급 의료 지도", page_icon="🚑")

st.title("🚑 수원시 응급 의료 지도")
st.write("현재 위치 주변의 **제세동기**와 **소아 야간 진료소**를 찾습니다.")

# GPS 버튼
loc = get_geolocation()

# 지도 초기화용 변수
my_lat = None
my_lon = None

# GPS 정보가 있으면 좌표 설정
if loc:
    my_lat = loc['coords']['latitude']
    my_lon = loc['coords']['longitude']
    st.success(f"📍 현재 위치를 찾았습니다! ({my_lat:.4f}, {my_lon:.4f})")
else:
    st.info("👆 위 버튼을 눌러 위치 권한을 허용해주세요. (PC에서는 다소 부정확할 수 있습니다)")
    # 테스트용 기본 좌표 (수원시청)
    # my_lat, my_lon = 37.2636, 127.0286 

if my_lat and my_lon:
    # 지도 생성
    m = folium.Map(location=[my_lat, my_lon], zoom_start=14)
    folium.Marker([my_lat, my_lon], popup="내 위치", icon=folium.Icon(color='red', icon='home')).add_to(m)

    # 데이터 검색 설정
    urls_config = {
        "🚑 제세동기": {"url": "https://openapi.gg.go.kr/Aedstus", "radius_km": 0.5, "color": "blue", "icon": "heart"},
        "🏥 소아야간진료": {"url": "https://openapi.gg.go.kr/ChildNightTreatHosptl", "radius_km": 5.0, "color": "green", "icon": "plus"}
    }

    # 데이터 처리
    with st.spinner("주변 의료 시설을 검색하고 내비게이션 시간을 계산 중입니다..."):
        for title, config in urls_config.items():
            rows = get_gg_data(config['url'])
            candidates = []

            # 1차 필터링 (직선 거리)
            for row in rows:
                try:
                    lat = float(row.get("REFINE_WGS84_LAT"))
                    lon = float(row.get("REFINE_WGS84_LOGT"))
                    name = row.get("INSTL_PLACE") or row.get("FACLT_NM")
                    if not name: name = row.get("REFINE_ROADNM_ADDR") or "이름없음"

                    dist = get_straight_distance(my_lat, my_lon, lat, lon)
                    if dist <= config['radius_km']:
                        candidates.append({"name": name, "lat": lat, "lon": lon, "dist": dist})
                except:
                    continue
            
            # 내비게이션 계산 (상위 10개만)
            candidates = sorted(candidates, key=lambda x: x['dist'])[:10]

            for item in candidates:
                time = get_navigation_time(my_lon, my_lat, item['lon'], item['lat'])
                if time is not None:
                    popup_html = f"""
                    <div style="width:150px">
                        <b>{item['name']}</b><br>
                        [{title}]<br>
                        직선거리: {item['dist']:.2f}km<br>
                        🚗 차량: 약 {int(time)}분
                    </div>
                    """
                    folium.Marker(
                        [item['lat'], item['lon']],
                        popup=popup_html,
                        tooltip=f"{item['name']} ({int(time)}분)",
                        icon=folium.Icon(color=config['color'], icon=config['icon'], prefix='fa')
                    ).add_to(m)

    # 지도 출력
    st_folium(m, width=725, height=500)