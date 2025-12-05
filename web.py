import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, LocateControl
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
import re
from math import radians, sin, cos, sqrt, atan2

# ==========================================
# 1. 페이지 및 API 설정
# ==========================================
st.set_page_config(
    page_title="수원시 안전 지도", 
    layout="wide", 
    page_icon="🏥",
    initial_sidebar_state="expanded"
)

# API 키 확인
if "GG_API_KEY" not in st.secrets or "KAKAO_API_KEY" not in st.secrets:
    st.error("🚨 Secrets 설정이 없습니다. Streamlit 대시보드에서 API 키를 설정해주세요.")
    st.stop()

GG_API_KEY = st.secrets["GG_API_KEY"]
KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]

# ==========================================
# 2. 데이터 및 함수 설정
# ==========================================
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
        st.error(f"주소 검색 오류: {e}")
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
    for page in range(1, 10): # 속도를 위해 10페이지까지만
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

# ==========================================
# 3. 메인 앱 로직
# ==========================================
def main():
    st.title("🚽 수원시 통합 안전/편의 지도")
    
    # 세션 상태 초기화
    if 'search_data' not in st.session_state:
        st.session_state['search_data'] = None

    # 사이드바
    st.sidebar.header("🔍 검색 설정")
    main_cat = st.sidebar.selectbox("대분류 선택", list(CATEGORY_CONFIG.keys()))
    sub_services = CATEGORY_CONFIG[main_cat]['services']
    selected_svc_name = st.sidebar.selectbox("소분류 선택", list(sub_services.keys()))
    conf = sub_services[selected_svc_name]
    
    st.sidebar.markdown("---")
    
    # 위치 설정 방식 선택 (GPS 기능 부활)
    location_mode = st.sidebar.radio("위치 설정", ["📍 주소/장소 검색", "📡 내 현재 위치(GPS)"])
    
    gps_lat, gps_lon = None, None

    if location_mode == "📡 내 현재 위치(GPS)":
        loc = get_geolocation()
        if loc:
            gps_lat = loc['coords']['latitude']
            gps_lon = loc['coords']['longitude']
            st.sidebar.success(f"GPS 수신 완료! ({gps_lat:.4f}, {gps_lon:.4f})")
        else:
            st.sidebar.warning("위치 권한을 허용하거나 잠시 기다려주세요.")
            
    else:
        search_query = st.sidebar.text_input("검색할 장소", value="수원시청")

    # 검색 버튼
    if st.sidebar.button("시설 찾기 시작", type="primary"):
        lat, lon, name, label = None, None, None, ""

        if location_mode == "📡 내 현재 위치(GPS)":
            if gps_lat and gps_lon:
                lat, lon = gps_lat, gps_lon
                name = "내 현재 위치"
                label = "현위치" # 카카오맵 길찾기용 매직 키워드
            else:
                st.error("GPS 정보를 아직 받아오지 못했습니다.")
        else:
            # 주소 검색
            full_query = search_query if "수원" in search_query else f"수원 {search_query}"
            lat, lon, name = get_coords_from_address(full_query)
            if lat:
                label = clean_name(name)
            else:
                st.error("장소를 찾을 수 없습니다.")

        # 좌표가 유효하면 세션에 저장
        if lat and lon:
            st.session_state['search_data'] = {
                'lat': lat, 'lon': lon, 'name': name, 'label': label
            }

    # 지도 그리기 (세션에 데이터가 있으면 항상 표시)
    if st.session_state['search_data']:
        data = st.session_state['search_data']
        my_lat, my_lon = data['lat'], data['lon']
        
        st.markdown(f"### 📍 기준: **{data['name']}** 주변 {selected_svc_name}")
        
        with st.spinner("시설 데이터를 분석 중입니다..."):
            m = folium.Map(location=[my_lat, my_lon], zoom_start=15)
            
            # 내 위치
            folium.Marker(
                [my_lat, my_lon],
                popup="<b>출발지</b>",
                icon=folium.Icon(color='black', icon='home', prefix='fa')
            ).add_to(m)
            
            folium.Circle(
                [my_lat, my_lon], radius=conf['radius']*1000, 
                color=conf['color'], fill=True, fill_opacity=0.1
            ).add_to(m)
            
            rows = get_gg_data_all_pages(conf['url'])
            marker_cluster = MarkerCluster().add_to(m)
            count = 0
            
            coord_cols = [("REFINE_WGS84_LAT","REFINE_WGS84_LOGT"), ("LAT","LON"), ("WGS84_LAT","WGS84_LOGT")]

            for row in rows:
                addr = str(row.get("REFINE_ROADNM_ADDR", "") or "")
                # 수원 근처 필터링 (너무 넓게 잡히는 것 방지)
                if not any(x in addr for x in ["수원", "영통", "권선", "팔달", "장안"]):
                    continue

                t_lat, t_lon = None, None
                for lat_c, lon_c in coord_cols:
                    try:
                        temp_lat, temp_lon = float(row.get(lat_c,0)), float(row.get(lon_c,0))
                        if 33 < temp_lat < 39: # 유효 좌표 체크
                            t_lat, t_lon = temp_lat, temp_lon
                            break
                    except: continue
                
                if t_lat and t_lon:
                    dist = get_straight_distance(my_lat, my_lon, t_lat, t_lon)
                    
                    if dist <= conf['radius'] * 1.5:
                        count += 1
                        place_name = clean_name(row.get("PBCTLT_PLC_NM") or row.get("FACLT_NM") or row.get("REFINE_ROADNM_ADDR") or "시설")
                        
                        # 카카오맵 링크 (출발지 -> 도착지)
                        # GPS일 경우: sName=현위치, 검색일 경우: sName=검색어
                        link = f"https://map.kakao.com/?sName={data['label']}&eName={place_name}"
                        
                        popup_html = f"""
                        <div style="width:160px; font-family:sans-serif;">
                            <b style="font-size:14px">{place_name}</b><br>
                            <span style="color:#666; font-size:12px">거리: {int(dist*1000)}m</span><br>
                            <a href="{link}" target="_blank" style="
                                display:block; margin-top:5px; background:#FEE500; 
                                color:#000; text-align:center; padding:6px; 
                                text-decoration:none; border-radius:4px; font-weight:bold; font-size:13px;">
                                카카오맵 길찾기 🚀
                            </a>
                        </div>
                        """
                        
                        folium.Marker(
                            [t_lat, t_lon],
                            popup=folium.Popup(popup_html, max_width=200),
                            icon=folium.Icon(color=conf['color'], icon=conf['icon'], prefix='fa')
                        ).add_to(marker_cluster)
            
            st.success(f"검색 결과: **{count}개**의 시설을 찾았습니다.")
            st_folium(m, width="100%", height=500)

if __name__ == "__main__":
    main()
