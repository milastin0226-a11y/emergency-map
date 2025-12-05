import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, LocateControl
from streamlit_folium import st_folium
import re
from math import radians, sin, cos, sqrt, atan2

# 1. 페이지 설정 (무조건 맨 윗줄에 있어야 함)
st.set_page_config(
    page_title="수원시 안전 지도", 
    layout="wide", 
    page_icon="🏥",
    initial_sidebar_state="expanded"
)

# 2. API 키 설정 (없으면 에러 출력 후 중단)
if "GG_API_KEY" not in st.secrets or "KAKAO_API_KEY" not in st.secrets:
    st.error("🚨 Secrets 설정이 없습니다. Streamlit 대시보드에서 API 키를 설정해주세요.")
    st.stop()

GG_API_KEY = st.secrets["GG_API_KEY"]
KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]

# 3. 데이터 설정
CATEGORY_CONFIG = {
    "🏥 의료/건강": {"services": {
        "AED(제세동기)": {"url": "https://openapi.gg.go.kr/Aedstus", "icon": "heart", "color": "red", "radius": 0.5},
        "소아야간진료": {"url": "https://openapi.gg.go.kr/ChildNightTreatHosptl", "icon": "plus", "color": "green", "radius": 3.0}
    }},
    "🚨 안전/비상": {"services": {
        "안전비상벨": {"url": "https://openapi.gg.go.kr/Safeemrgncbell", "icon": "bell", "color": "orange", "radius": 0.2},
        "옥내소화전": {"url": "https://openapi.gg.go.kr/FirefgtFacltDevice", "icon": "fire-extinguisher", "color": "darkred", "radius": 0.1}
    }},
    "🚽 편의시설": {"services": {
        "공중화장실": {"url": "https://openapi.gg.go.kr/Publtolt", "icon": "info-sign", "color": "purple", "radius": 1.0}
    }}
}

# 4. 함수 정의
def clean_name(name):
    return re.sub(r'\[.*?\]\s*', '', str(name))

def get_coords_from_address(address):
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    try:
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        res = requests.get(url, headers=headers, params={"query": address}).json()
        if res.get('documents'):
            item = res['documents'][0]
            return float(item['y']), float(item['x']), item['place_name']
    except Exception as e:
        st.error(f"주소 검색 중 오류: {e}")
    return None, None, None

def get_straight_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2*atan2(sqrt(a), sqrt(1-a))
    return R*c

@st.cache_data(ttl=3600)
def get_gg_data_all_pages(url):
    all_rows = []
    # 데이터 로딩 속도를 위해 페이지 수 제한 (필요시 20으로 증가)
    for page in range(1, 10):
        params = {"KEY": GG_API_KEY, "Type": "json", "pIndex": page, "pSize": 1000}
        try:
            res = requests.get(url, params=params).json()
            found = False
            for key in res.keys():
                if isinstance(res[key], list):
                    for item in res[key]:
                        if isinstance(item, dict) and "row" in item:
                            rows = item["row"]
                            if rows:
                                all_rows.extend(rows)
                                found = True
            if not found:
                break
        except:
            break
    return all_rows

# 5. 메인 앱
def main():
    st.title("🚽 수원시 통합 안전/편의 지도")
    
    # 세션 상태 초기화
    if 'search_data' not in st.session_state:
        st.session_state['search_data'] = None

    # 사이드바 UI
    st.sidebar.header("🔍 검색 설정")
    main_cat = st.sidebar.selectbox("대분류 선택", list(CATEGORY_CONFIG.keys()))
    sub_services = CATEGORY_CONFIG[main_cat]['services']
    selected_svc_name = st.sidebar.selectbox("소분류 선택", list(sub_services.keys()))
    conf = sub_services[selected_svc_name]
    
    st.sidebar.markdown("---")
    st.sidebar.info("💡 **사용 팁**: 모바일에서는 '현재 위치' 대신 '장소 이름'으로 검색하는 것이 더 정확할 수 있습니다.")
    
    search_query = st.text_input("검색할 장소 입력", value="수원시청", placeholder="예: 수원역, 아주대, 매탄동")

    # 검색 버튼
    if st.button("시설 찾기 시작", type="primary", use_container_width=True):
        full_query = search_query if "수원" in search_query else f"수원 {search_query}"
        
        with st.spinner(f"'{full_query}' 위치를 찾는 중..."):
            lat, lon, name = get_coords_from_address(full_query)
            
        if lat:
            st.session_state['search_data'] = {
                'lat': lat, 'lon': lon, 'name': name, 'label': clean_name(name)
            }
        else:
            st.error("❌ 장소를 찾을 수 없습니다. 정확한 이름을 입력해주세요.")

    # 지도 렌더링
    if st.session_state['search_data']:
        data = st.session_state['search_data']
        my_lat, my_lon = data['lat'], data['lon']
        
        st.markdown(f"### 📍 기준: **{data['name']}**")
        
        with st.spinner("주변 시설 데이터를 불러오는 중..."):
            # 지도 생성
            m = folium.Map(location=[my_lat, my_lon], zoom_start=15)
            
            # 내 위치 마커
            folium.Marker(
                [my_lat, my_lon], 
                popup="검색 위치", 
                icon=folium.Icon(color='black', icon='home', prefix='fa')
            ).add_to(m)
            
            # 반경 표시
            folium.Circle(
                [my_lat, my_lon], 
                radius=conf['radius']*1000, 
                color=conf['color'], 
                fill=True, 
                fill_opacity=0.1
            ).add_to(m)
            
            # 시설 데이터 마커
            rows = get_gg_data_all_pages(conf['url'])
            marker_cluster = MarkerCluster().add_to(m)
            count = 0
            
            coordinate_cols = [
                ("REFINE_WGS84_LAT","REFINE_WGS84_LOGT"), 
                ("LAT","LON"), 
                ("WGS84_LAT","WGS84_LOGT")
            ]

            for row in rows:
                # 수원시 필터
                addr = str(row.get("REFINE_ROADNM_ADDR", "") or row.get("REFINE_LOTNO_ADDR", "") or "")
                if "수원" not in addr and "영통" not in addr and "팔달" not in addr and "장안" not in addr and "권선" not in addr:
                    continue
                
                # 좌표 추출
                lat, lon = None, None
                for lat_c, lon_c in coordinate_cols:
                    try:
                        t_lat, t_lon = float(row.get(lat_c,0)), float(row.get(lon_c,0))
                        if 33 < t_lat < 39 and 124 < t_lon < 132: # 한국 좌표 범위 체크
                            lat, lon = t_lat, t_lon
                            break
                    except: continue
                
                if lat and lon:
                    dist = get_straight_distance(my_lat, my_lon, lat, lon)
                    if dist <= conf['radius'] * 1.5: # 반경 1.5배까지 표시
                        count += 1
                        p_name = clean_name(row.get("PBCTLT_PLC_NM") or row.get("FACLT_NM") or row.get("REFINE_ROADNM_ADDR") or "시설")
                        
                        # 카카오맵 링크
                        link = f"https://map.kakao.com/link/to/{p_name},{lat},{lon}"
                        
                        popup_html = f"""
                        <div style="width:150px; font-family:sans-serif;">
                            <b>{p_name}</b><br>
                            <span style="color:gray; font-size:12px;">직선거리 {int(dist*1000)}m</span><br>
                            <a href="{link}" target="_blank" style="
                                display:block; margin-top:5px; background:#FEE500; 
                                color:#000; text-align:center; padding:5px; 
                                text-decoration:none; border-radius:4px; font-weight:bold;">
                                카카오맵 길찾기
                            </a>
                        </div>
                        """
                        
                        folium.Marker(
                            [lat, lon],
                            popup=folium.Popup(popup_html, max_width=200),
                            icon=folium.Icon(color=conf['color'], icon=conf['icon'], prefix='fa')
                        ).add_to(marker_cluster)

            st.success(f"반경 {conf['radius']}km 내에서 **{count}개**의 시설을 찾았습니다.")
            st_folium(m, width="100%", height=500)

if __name__ == "__main__":
    main()
