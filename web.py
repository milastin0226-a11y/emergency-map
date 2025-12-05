import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, LocateControl
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
from math import radians, sin, cos, sqrt, atan2
import re

# ==========================================
# 1. 설정 및 API 키
# ==========================================
st.set_page_config(page_title="수원시 안전 지도", layout="wide", page_icon="🏥")

# Streamlit Secrets에서 키를 가져옵니다.
# 로컬에서 실행할 때는 .streamlit/secrets.toml 파일이 필요하며,
# 클라우드 배포 시에는 대시보드에서 설정합니다.
try:
    GG_API_KEY = st.secrets["GG_API_KEY"]
    KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
except FileNotFoundError:
    st.error("API 키를 찾을 수 없습니다. secrets.toml 파일을 확인해주세요.")
    st.stop()

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

# ==========================================
# 2. 유틸리티 함수 (캐싱 적용)
# ==========================================
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
        print(e)
    return None, None, None

def get_straight_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2*atan2(sqrt(a), sqrt(1-a))
    return R*c

@st.cache_data(ttl=3600)  # 1시간 동안 데이터 캐싱
def get_gg_data_all_pages(url):
    all_rows = []
    # 속도를 위해 페이지 수 조정 (필요시 늘리세요)
    for page in range(1, 20):
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
    st.markdown("내 위치 또는 특정 장소 주변의 **의료, 안전, 편의시설**을 찾아보세요.")

    # 사이드바 설정
    st.sidebar.header("🔍 검색 설정")
    
    # 1. 카테고리 선택
    main_cat = st.sidebar.selectbox("대분류 선택", list(CATEGORY_CONFIG.keys()))
    sub_services = CATEGORY_CONFIG[main_cat]['services']
    selected_svc_name = st.sidebar.selectbox("소분류 선택", list(sub_services.keys()))
    
    conf = sub_services[selected_svc_name]
    
    # 2. 위치 설정 방식
    location_mode = st.radio("위치 설정", ["📍 주소/장소 검색", "📡 내 현재 위치(GPS)"], horizontal=True)

    my_lat, my_lon, my_name = None, None, None
    start_label_for_link = "" # 길찾기 링크용 출발지 이름

    if location_mode == "📡 내 현재 위치(GPS)":
        st.info("모바일에서 '위치 권한'을 허용해주세요.")
        # GPS 버튼 (streamlit-js-eval)
        loc = get_geolocation()
        
        if loc:
            my_lat = loc['coords']['latitude']
            my_lon = loc['coords']['longitude']
            my_name = "내 현재 위치"
            start_label_for_link = "현위치" # 카카오맵 URL용 매직 키워드
            st.success(f"GPS 수신 성공! (위도: {my_lat:.4f}, 경도: {my_lon:.4f})")
        else:
            st.warning("위치 정보를 가져오는 중입니다. 버튼을 다시 누르거나 기다려주세요.")

    else:
        search_query = st.text_input("검색할 장소 입력 (예: 수원역, 아주대)", value="수원시청")
        if search_query:
            if "수원" not in search_query:
                search_query = f"수원 {search_query}"
            
            lat, lon, name = get_coords_from_address(search_query)
            if lat:
                my_lat, my_lon = lat, lon
                my_name = name
                start_label_for_link = clean_name(my_name)
            else:
                st.error("장소를 찾을 수 없습니다.")

    # 지도 그리기 버튼
    if st.button("시설 찾기 시작", type="primary"):
        if my_lat is None or my_lon is None:
            st.error("위치 정보가 없습니다. GPS를 켜거나 장소를 입력해주세요.")
            return

        with st.spinner(f"수원시 {selected_svc_name} 데이터를 불러오는 중..."):
            # 지도 초기화
            m = folium.Map(location=[my_lat, my_lon], zoom_start=15)
            
            # 내 위치 마커
            folium.Marker(
                [my_lat, my_lon],
                popup=f"<b>출발: {my_name}</b>",
                icon=folium.Icon(color='black', icon='home', prefix='fa')
            ).add_to(m)
            
            # 내 위치 찾기 버튼 추가 (지도 상단)
            LocateControl(auto_start=False).add_to(m)

            # 반경 표시
            folium.Circle(
                location=[my_lat, my_lon],
                radius=conf['radius'] * 1000,
                color=conf['color'],
                fill=True,
                fill_opacity=0.05
            ).add_to(m)

            # 데이터 로드
            rows = get_gg_data_all_pages(conf['url'])
            marker_cluster = MarkerCluster().add_to(m)
            
            count = 0
            coordinate_columns = [
                ("REFINE_WGS84_LAT","REFINE_WGS84_LOGT"), ("LAT","LON"),
                ("TPLT_WGS84_LAT","TPLT_WGS84_LOGT"), ("위도","경도"), ("Y","X")
            ]

            for row in rows:
                # 수원시 데이터 필터링 (주소 기반)
                addr = str(row.get("REFINE_ROADNM_ADDR", "") or row.get("REFINE_LOTNO_ADDR", "") or row.get("SIGUN_NM", ""))
                if "수원" not in addr:
                    continue

                # 좌표 추출
                lat, lon = None, None
                for lat_col, lon_col in coordinate_columns:
                    try:
                        t_lat = float(row.get(lat_col, 0))
                        t_lon = float(row.get(lon_col, 0))
                        if 30 <= t_lat <= 45 and 120 <= t_lon <= 135:
                            lat, lon = t_lat, t_lon
                            break
                    except: continue
                
                # 좌표 없으면 주소로 검색 (너무 느려질 수 있어 생략하거나 필요시 활성화)
                if lat is None and row.get("REFINE_ROADNM_ADDR"):
                     # 실시간 지오코딩은 대량 데이터에서 느리므로 여기선 생략
                     pass

                if lat and lon:
                    dist = get_straight_distance(my_lat, my_lon, lat, lon)
                    
                    # 설정된 반경 + 여유분(2배) 내의 데이터만 표시하여 성능 확보
                    if dist <= conf['radius'] * 2.0:
                        count += 1
                        
                        # 이름 결정
                        name = row.get("PBCTLT_PLC_NM") or row.get("FACLT_NM") or row.get("REFINE_ROADNM_ADDR") or "이름 없음"
                        clean_dest_name = clean_name(name)
                        
                        walk_time = dist / 4 * 60
                        walk_str = f"{int(walk_time)}분" if walk_time < 60 else f"{walk_time/60:.1f}시간"
                        
                        # 반경 내/외 색상 구분
                        icon_color = conf['color'] if dist <= conf['radius'] else 'gray'
                        
                        # 카카오맵 링크 생성 로직 (요청하신 부분)
                        # sName=현위치 (GPS인 경우) 또는 입력한장소이름
                        # eName=도착지이름
                        kakao_link = f"https://map.kakao.com/?sName={start_label_for_link}&eName={clean_dest_name}"
                        
                        popup_html = f"""
                        <div style="width:200px; font-family:sans-serif;">
                            <b style="font-size:1.1em;">{clean_dest_name}</b><br>
                            <span style="color:gray; font-size:0.8em">{selected_svc_name}</span>
                            <hr style="margin:5px 0">
                            📏 거리: <b>{dist*1000:.0f}m</b><br>
                            🏃 도보: 약 {walk_str}<br>
                            <hr style="margin:5px 0">
                            <a href="{kakao_link}" target="_blank"
                            style="background-color:#FEE500; color:black; padding:8px; 
                            text-decoration:none; border-radius:5px; display:block; text-align:center; font-weight:bold;">
                            카카오맵 길찾기 🚀
                            </a>
                        </div>
                        """
                        
                        icon_prefix = 'fa' if conf['icon'] in ['heart', 'bell', 'fire-extinguisher', 'info-sign', 'plus'] else 'glyphicon'
                        
                        folium.Marker(
                            [lat, lon],
                            popup=folium.Popup(popup_html, max_width=250),
                            tooltip=f"{clean_dest_name} ({int(dist*1000)}m)",
                            icon=folium.Icon(color=icon_color, icon=conf['icon'], prefix=icon_prefix)
                        ).add_to(marker_cluster)

            st.write(f"📊 검색 결과: 반경 {conf['radius']}km 내외 **{count}개** 시설 발견")
            st_folium(m, width="100%", height=500)

if __name__ == "__main__":

    main()
