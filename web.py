import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, LocateControl
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
from math import radians, sin, cos, sqrt, atan2
import re

# ==========================================
# 1. 설정 및 API 키 (수정된 버전)
# ==========================================
st.set_page_config(page_title="수원시 안전 지도", layout="wide", page_icon="🏥")

try:
    # secrets가 아예 없는 경우(로컬)나 키가 없는 경우를 모두 대비
    if "GG_API_KEY" in st.secrets and "KAKAO_API_KEY" in st.secrets:
        GG_API_KEY = st.secrets["GG_API_KEY"]
        KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
    else:
        # 키가 없으면 로컬 테스트용 빈 값 혹은 경고
        # (배포 환경에서는 이 부분이 실행되면 안 됨)
        st.error("🚨 Secrets에 API 키가 설정되지 않았습니다! 대시보드 설정을 확인하세요.")
        st.stop()
except Exception as e:
    st.error(f"🚨 설정 오류 발생: {e}")
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
# 2. 유틸리티 함수
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
        pass
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

