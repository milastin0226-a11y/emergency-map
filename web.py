import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
# [추가됨] GPS 기능을 위한 라이브러리
from streamlit_js_eval import get_geolocation
import os
import re
from math import radians, sin, cos, sqrt, atan2
import pandas as pd
import datetime

# ==========================================
# 1. API 키 설정
# ==========================================
GG_API_KEY = "42334a0cf97944c9b1ad81d6dd2dc17a"
KAKAO_API_KEY = "72968d96a40f21a36d5d01d647daf602"

# ==========================================
# 2. 카테고리/아이콘/반경 설정 (데이터 유지)
# ==========================================
CATEGORY_CONFIG = {
    "1": {"name": "🏥 의료/건강", "services": {
        "AED(제세동기)": {"url": "https://openapi.gg.go.kr/Aedstus", "icon": "heart", "color": "red", "radius": 0.5},
        "소아야간진료": {"url": "https://openapi.gg.go.kr/ChildNightTreatHosptl", "icon": "plus", "color": "green", "radius": 3.0}
    }},
    "2": {"name": "🚨 안전/비상", "services": {
        "안전비상벨": {"url": "https://openapi.gg.go.kr/Safeemrgncbell", "icon": "bell", "color": "orange", "radius": 0.2},
        "옥내소화전": {"url": "https://openapi.gg.go.kr/FirefgtFacltDevice", "icon": "fire-extinguisher", "color": "darkred", "radius": 0.1}
    }},
    "3": {"name": "🚽 편의시설", "services": { 
        "공중화장실": {"url": "https://openapi.gg.go.kr/Publtolt", "icon": "info-sign", "color": "purple", "radius": 1.0}
    }}
}

# ==========================================
# 3. 함수 정의
# ==========================================
def clean_name(name):
    return re.sub(r'\[.*?\]\s*', '', name)

def get_coords_from_address(address):
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    url_address = "https://dapi.kakao.com/v2/local/search/address.json"
    try:
        res = requests.get(url_address, headers=headers, params={"query": address}).json()
        if res.get('documents'):
            item = res['documents'][0]
            return float(item['y']), float(item['x'])
    except: pass
    url_keyword = "https://dapi.kakao.com/v2/local/search/keyword.json"
    try:
        res = requests.get(url_keyword, headers=headers, params={"query": address}).json()
        if res.get('documents'):
            item = res['documents'][0]
            return float(item['y']), float(item['x'])
    except: pass
    return None, None

def get_location_smart(user_input):
    # [변경] IP 기반 로직 제거 -> GPS 버튼으로 대체됨
    # 오직 텍스트 검색만 수행
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    search_query = user_input if "수원" in user_input else f"수원시 {user_input}"
    try:
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        res = requests.get(url, headers=headers, params={"query": search_query}).json()
        if res.get('documents'):
            item = res['documents'][0]
            return float(item['y']), float(item['x']), f"[장소] {item['place_name']}"
    except: pass
    return None, None, None

def get_straight_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2*atan2(sqrt(a), sqrt(1-a))
    return R*c

def get_walking_time(dist_km):
    return dist_km / 4 * 60

@st.cache_data(ttl=600)
def get_gg_data_all_pages(url):
    all_rows = []
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
# 4. Streamlit 메인 UI 및 실행 로직
# ==========================================
def main():
    st.set_page_config(page_title="수원시 통합 안전 지도", layout="wide", page_icon="🗺️")
    
    st.title("🚽 수원시 통합 안전 지도")
    st.markdown("---")

    # 세션 상태 초기화 (지도 및 현재 위치 저장)
    if 'generated_map' not in st.session_state:
        st.session_state['generated_map'] = None
    if 'search_result_text' not in st.session_state:
        st.session_state['search_result_text'] = ""
    if 'active_lat' not in st.session_state:
        st.session_state['active_lat'] = None
    if 'active_lon' not in st.session_state:
        st.session_state['active_lon'] = None
    if 'active_name' not in st.session_state:
        st.session_state['active_name'] = None
    if 'last_gps_timestamp' not in st.session_state:
        st.session_state['last_gps_timestamp'] = 0

    # 사이드바에서 입력 받기
    with st.sidebar:
        st.header("🔍 검색 옵션")
        
        # 1. 대주제 & 소주제 선택
        cat_options = list(CATEGORY_CONFIG.keys())
        selected_cat_idx = st.selectbox("카테고리 선택", options=cat_options, format_func=lambda x: CATEGORY_CONFIG[x]['name'])
        category = CATEGORY_CONFIG[selected_cat_idx]

        services_list = list(category['services'].keys())
        selected_service_name = st.selectbox("세부 시설 선택", options=services_list)
        selected_services = [selected_service_name]

        st.markdown("---")
        st.subheader("📍 위치 설정")

        # [변경] 실제 GPS 좌표 요청 버튼 (streamlit-js-eval 사용)
        st.write("📡 GPS로 내 위치 찾기")
        gps_data = get_geolocation(component_key='get_gps', button_text="📍 내 현재 위치로 검색")

        st.markdown("---")
        st.write("🏙️ 장소 이름으로 검색")
        
        with st.form(key='search_form'):
            user_input_text = st.text_input("장소 입력", placeholder="예: 수원역, 아주대")
            submit_text = st.form_submit_button("🔍 검색")

    # ==========================================
    # 검색 우선순위 및 좌표 설정 로직
    # ==========================================
    
    should_run_analysis = False

    # 1. GPS 데이터가 새로 들어왔는지 확인
    if gps_data and 'coords' in gps_data:
        # 타임스탬프를 확인하여 새로운 클릭인지 확인 (혹은 최초 실행)
        current_timestamp = gps_data.get('timestamp', 0)
        if current_timestamp != st.session_state['last_gps_timestamp']:
            st.session_state['active_lat'] = gps_data['coords']['latitude']
            st.session_state['active_lon'] = gps_data['coords']['longitude']
            st.session_state['active_name'] = "📍 현위치 (GPS)"
            st.session_state['last_gps_timestamp'] = current_timestamp
            should_run_analysis = True
            st.sidebar.success("✅ GPS 위치 수신 성공!")

    # 2. 텍스트 검색 버튼을 눌렀는지 확인 (GPS보다 우선 실행하여 덮어씌움)
    if submit_text and user_input_text:
        my_lat, my_lon, my_name = get_location_smart(user_input_text)
        if my_lat:
            st.session_state['active_lat'] = my_lat
            st.session_state['active_lon'] = my_lon
            st.session_state['active_name'] = my_name
            should_run_analysis = True
        else:
            st.error(f"❌ '{user_input_text}' 위치를 찾을 수 없습니다.")

    # ==========================================
    # 지도 생성 및 분석 실행
    # ==========================================
    
    if should_run_analysis and st.session_state['active_lat']:
        with st.spinner(f"📍 {st.session_state['active_name']} 기준으로 분석 중..."):
            
            my_lat = st.session_state['active_lat']
            my_lon = st.session_state['active_lon']
            my_name = st.session_state['active_name']

            # 좌표 컬럼 정의
            coordinate_columns = [
                ("REFINE_WGS84_LAT","REFINE_WGS84_LOGT"), ("LAT","LON"),
                ("TPLT_WGS84_LAT","TPLT_WGS84_LOGT"), ("위도","경도"),
                ("Y","X"), ("X_COORD","Y_COORD"), ("X_WGS","Y_WGS")
            ]

            # 지도 객체 생성
            m = folium.Map(location=[my_lat, my_lon], zoom_start=15)
            folium.Marker([my_lat,my_lon], popup=f"<b>출발: {clean_name(my_name)}</b>", 
                          icon=folium.Icon(color='black', icon='home', prefix='fa')).add_to(m)
            
            # MarkerCluster 생성
            icon_create_function = """
                function(cluster) {
                    var count = cluster.getChildCount();
                    var size = count < 10 ? 20 + count * 1.2 : (count < 50 ? 30 + (count - 10) * 0.5 : 50 + (count - 50) * 0.1);
                    size = Math.min(size, 60);
                    var color = count < 10 ? 'green' : (count < 50 ? 'orange' : 'red');
                    return L.divIcon({
                        html: '<div style="background-color: ' + color + '; width: ' + size + 'px; height: ' + size + 'px; border-radius: 50%; text-align: center; line-height: ' + size + 'px; color: white; font-weight: bold; font-size: ' + (size/3.5) + 'px;">' + count + '</div>',
                        className: 'marker-cluster',
                        iconSize: [size, size]
                    });
                }
            """
            marker_cluster = MarkerCluster(icon_create_function=icon_create_function).add_to(m)
            
            total_count = 0

            for svc_name in selected_services:
                conf = category['services'][svc_name]
                radius_km = conf['radius']
                
                folium.Circle([my_lat, my_lon], radius=radius_km*1000, color=conf['color'], fill=False, dash_array='5,5').add_to(m)

                rows = get_gg_data_all_pages(conf['url'])
                df = pd.DataFrame(rows)
                
                coordinate_columns_flat = [col for pair in coordinate_columns for col in pair]
                for col in coordinate_columns_flat:
                    if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce') 

                suwon_mask = df.apply(lambda row: any("수원시" in str(row.get(col, "")) for col in ["REFINE_ROADNM_ADDR", "REFINE_LOTNO_ADDR", "SIGUN_NM"]), axis=1)
                df_suwon = df[suwon_mask].copy()
                total_count += len(df_suwon)

                for index, row in df_suwon.iterrows():
                    name = row.get("PBCTLT_PLC_NM") or row.get("INSTL_PLC_NM") or row.get("INSTL_PLACE") or \
                           row.get("FACLT_NM") or row.get("EQUP_NM") or row.get("TPLT_NM") or row.get("REFINE_ROADNM_ADDR") or "이름 미상"
                    
                    lat, lon = None, None
                    for lat_col, lon_col in coordinate_columns:
                        try:
                            val_lat, val_lon = row.get(lat_col, 0), row.get(lon_col, 0)
                            if 30 <= val_lat <= 45 and 120 <= val_lon <= 135:
                                lat, lon = val_lat, val_lon
                                break
                        except: continue
                    
                    if lat is None or lon is None:
                        addr_search = row.get("REFINE_ROADNM_ADDR") or row.get("PBCTLT_PLC_NM")
                        if addr_search: lat, lon = get_coords_from_address(f"수원 {addr_search}")
                        
                    if lat and lon:
                        dist = get_straight_distance(my_lat,my_lon,lat,lon)
                        walk_str = f"{int(get_walking_time(dist))}분" if get_walking_time(dist)<60 else f"{get_walking_time(dist)/60:.1f}시간"
                        display_color = conf['color'] if dist <= radius_km else 'lightgray'
                        
                        kakao_map_url = f"https://map.kakao.com/link/to/{clean_name(name)},{lat},{lon}/from/{clean_name(my_name)},{my_lat},{my_lon}"

                        popup_html = f"""
                        <div style="width:200px">
                            <b>{clean_name(name)}</b><br><span style="color:gray; font-size:0.9em">{svc_name}</span><hr style="margin:5px 0">
                            📏 <b>거리:</b> {dist*1000:.0f}m<br>🏃 <b>도보:</b> 약 {walk_str}<hr style="margin:5px 0">
                            <a href="{kakao_map_url}" target="_blank" style="background-color:#FEE500; color:black; padding:5px 10px; text-decoration:none; border-radius:5px; font-weight:bold; font-size:0.9em; display:block; text-align:center;">카카오맵 길찾기</a>
                        </div>
                        """
                        icon_prefix = 'fa' if conf['icon'] in ['fire-extinguisher','bell','snowflake-o','shield','user', 'home'] else 'glyphicon'
                        folium.Marker([lat,lon], popup=folium.Popup(popup_html, max_width=250), tooltip=f"{clean_name(name)}", icon=folium.Icon(color=display_color, icon=conf['icon'], prefix=icon_prefix)).add_to(marker_cluster)

            st.session_state['search_result_text'] = f"📍 기준점: **{my_name}** / 📊 검색 결과: **{total_count}건**"
            st.session_state['generated_map'] = m

    # ==========================================
    # 결과 화면 출력
    # ==========================================
    if st.session_state['generated_map'] is not None:
        st.success(st.session_state['search_result_text'])
        st_folium(st.session_state['generated_map'], width=700, height=500, returned_objects=[])
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"suwon_map_{timestamp}.html"
        m_html = st.session_state['generated_map'].get_root().render()
        st.download_button(label="📥 HTML 파일로 지도 다운로드", data=m_html, file_name=file_name, mime="text/html")

if __name__=="__main__":
    main()
