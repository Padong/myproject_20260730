import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
import time

# -----------------------------------------------------------------------------
# 1. 스트림릿 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="전국 고령화 지도",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ 전국 시군구 고령화 지도 (2015~2026)")
st.markdown("시군구별 65세 이상 인구 비율을 단계구분도(Choropleth)로 시각화합니다.")

# -----------------------------------------------------------------------------
# 2. 데이터 불러오기 및 캐싱 (Streamlit Cloud 최적화)
# -----------------------------------------------------------------------------
DATA_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEOJSON_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

@st.cache_data
def load_geojson():
    """GeoJSON 지적도 경계 데이터를 불러옵니다."""
    response = requests.get(GEOJSON_URL)
    return response.json()

@st.cache_data
def load_data():
    """인구 CSV 데이터를 불러오고 시군구별 65세 이상 인구 비율을 계산합니다."""
    # 코드는 반드시 문자열(str)로 읽어야 앞자리 '0'이 유지되고 5자리 잘라내기가 가능합니다.
    df = pd.read_csv(DATA_URL, dtype={'코드': str})
    
    # '코드' 열에서 앞 5자리를 추출하여 시군구 코드로 사용
    df['sigungu_code'] = df['코드'].str[:5]
    
    # 65세 이상 인구 관련 열 찾기 ('계_65세' ~ '계_100세 이상')
    total_cols = [c for c in df.columns if c.startswith('계_')]
    
    age_65_cols = []
    for col in total_cols:
        age_str = col.replace('계_', '').replace('세', '').replace(' 이상', '')
        if age_str.isdigit():
            if int(age_str) >= 65:
                age_65_cols.append(col)
        elif age_str == '100': # '계_100세 이상' 처리
            age_65_cols.append(col)
            
    # 전체 인구 및 65세 이상 인구 합계
    df['총인구'] = df[total_cols].sum(axis=1)
    df['65세이상인구'] = df[age_65_cols].sum(axis=1)
    
    # 시군구 단위로 연도별 집계 (시도, 시군구 이름 보존)
    # 한 시군구 코드에 여러 읍면동이 포함되어 있으므로 sum 처리
    grouped = df.groupby(['연도', 'sigungu_code', '시도', '시군구'], as_index=False)[['총인구', '65세이상인구']].sum()
    
    # 고령화율(%) 계산
    grouped['고령화율'] = (grouped['65세이상인구'] / grouped['총인구']) * 100
    grouped['고령화율'] = grouped['고령화율'].round(2)
    
    # 5단계 구간 나누기 (19%, 23%, 28%, 38% 기준)
    # 0: ~19 미만, 1: 19~23, 2: 23~28, 3: 28~38, 4: 38 이상
    bins = [0, 19, 23, 28, 38, 100]
    labels = ['19% 미만', '19% ~ 23%', '23% ~ 28%', '28% ~ 38%', '38% 이상']
    grouped['고령화구간'] = pd.cut(grouped['고령화율'], bins=bins, labels=labels, right=False)
    
    # 연령대별 세부 분석용 원본 읍면동 데이터도 시군구 단위로 합산하여 반환
    df_age_grouped = df.groupby(['연도', 'sigungu_code'])[total_cols].sum().reset_index()
    
    return grouped, df_age_grouped

geojson_data = load_geojson()
pop_data, age_data = load_data()

# available years
years = sorted(pop_data['연도'].unique())
max_year = max(years)

# -----------------------------------------------------------------------------
# 3. 사이드바 및 시뮬레이션 제어
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ 지도 제어")

# 애니메이션 시뮬레이션 재생 기능
if 'selected_year' not in st.session_state:
    st.session_state['selected_year'] = max_year

def run_simulation():
    for y in years:
        st.session_state['selected_year'] = y
        time.sleep(0.6)
        st.rerun()

if st.sidebar.button("▶️ 2015~2026 연도별 변화 시뮬레이션"):
    run_simulation()

selected_year = st.sidebar.selectbox(
    "조회할 연도 선택",
    years,
    index=years.index(st.session_state['selected_year'])
)
st.session_state['selected_year'] = selected_year

# 해당 연도 데이터 필터링
current_df = pop_data[pop_data['연도'] == selected_year].copy()

# -----------------------------------------------------------------------------
# 4. plotly 단계구분도 (Choropleth) 생성
# -----------------------------------------------------------------------------
# 5단계 범례 색상 지정 (옅은 주황 -> 진한 Red-Purple)
color_discrete_map = {
    '19% 미만': '#fef0d9',
    '19% ~ 23%': '#fdcc8a',
    '23% ~ 28%': '#fc8d59',
    '28% ~ 38%': '#e34a33',
    '38% 이상': '#b30000'
}

category_orders = {'고령화구간': ['19% 미만', '19% ~ 23%', '23% ~ 28%', '28% ~ 38%', '38% 이상']}

fig = px.choropleth_mapbox(
    current_df,
    geojson=geojson_data,
    locations='sigungu_code',
    featureidkey="properties.코드", # GeoJSON의 5자리 '코드' 속성과 매칭
    color='고령화구간',
    color_discrete_map=color_discrete_map,
    category_orders=category_orders,
    mapbox_style="white-bg", # 배경 지도 타일 없이 경계선만 표시
    center={"lat": 35.9, "lon": 127.8}, # 대한민국 중심 좌표
    zoom=6.2,
    hover_name='시군구',
    hover_data={
        'sigungu_code': False,
        '시도': True,
        '고령화율': ':.2f',
        '총인구': ':,d',
        '65세이상인구': ':,d'
    },
    labels={'고령화율': '고령화율(%)', '고령화구간': '고령화 비율 구간'}
)

fig.update_traces(
    marker_line_width=0.5,
    marker_line_color="gray",
    hovertemplate="<b>%{hovertext}</b> (%{customdata[0]})<br>" +
                  "고령화율: <b>%{customdata[1]:.2f}%</b><br>" +
                  "총 인구: %{customdata[2]:,}명<br>" +
                  "65세 이상 인구: %{customdata[3]:,}명<extra></extra>"
)

fig.update_layout(
    margin={"r":0,"t":30,"l":0,"b":0},
    title=f"<b>[{selected_year}년] 전국 시군구 고령화율 지도</b>",
    legend_title_text="<b>고령화 비율 구간</b>",
    clickmode='event+select' # 지역 클릭 이벤트를 받아오기 위해 설정
)

# 지도 출력 및 클릭 이벤트 감지
map_event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points")

# -----------------------------------------------------------------------------
# 5. 고령화율 상위/하위 10개 지역 표
# -----------------------------------------------------------------------------
st.subheader(f"📊 {selected_year}년 고령화율 극단 지역 (상위/하위 10개)")

col1, col2 = st.columns(2)

top10 = current_df.sort_values(by='고령화율', ascending=False).head(10)[['시도', '시군구', '고령화율', '총인구', '65세이상인구']]
bottom10 = current_df.sort_values(by='고령화율', ascending=True).head(10)[['시도', '시군구', '고령화율', '총인구', '65세이상인구']]

with col1:
    st.markdown("🔴 **고령화율 가장 높은 10곳**")
    st.dataframe(top10.reset_index(drop=True), use_container_width=True)

with col2:
    st.markdown("🟢 **고령화율 가장 낮은 10곳**")
    st.dataframe(bottom10.reset_index(drop=True), use_container_width=True)

# -----------------------------------------------------------------------------
# 6. 지역 클릭 시 팝업(Modal) 분석창 및 원그래프 연동
# -----------------------------------------------------------------------------
# 지도에서 특정 시군구를 클릭했는지 확인
if map_event and "selection" in map_event and len(map_event["selection"]["points"]) > 0:
    clicked_point = map_event["selection"]["points"][0]
    clicked_code = clicked_point["location"]
    
    # 클릭한 지역 정보 가져오기
    target_info = pop_data[pop_data['sigungu_code'] == clicked_code].iloc[0]
    target_name = f"{target_info['시도']} {target_info['시군구']}"
    
    # Streamlit 팝업 창(Modal) 생성
    @st.dialog(f"🔍 {target_name} 세부 고령화 분석", width="large")
    def show_detail_modal(code, name):
        st.write(f"**행정구역 코드:** `{code}`")
        
        # 1) 시군구의 연도별 고령화율 추이 데이터
        region_history = pop_data[pop_data['sigungu_code'] == code].sort_values('연도')
        
        # 2) 꺾은선 그래프 (연도별 추이)
        fig_line = px.line(
            region_history,
            x='연도',
            y='고령화율',
            markers=True,
            title=f"📈 {name} 연도별 고령화율 추이 (2015~2026)",
            labels={'고령화율': '고령화율 (%)', '연도': '연도'}
        )
        fig_line.update_traces(line_color='#e34a33', line_width=3, marker_size=8)
        fig_line.update_layout(clickmode='event+select')
        
        st.markdown("👇 **그래프의 연도 포인트를 클릭**하면 해당 연도의 **연령별 인구 분포(원그래프)**를 확인할 수 있습니다.")
        line_event = st.plotly_chart(fig_line, use_container_width=True, on_select="rerun", selection_mode="points")
        
        # 선택된 연도 판별 (추이 그래프 클릭 시 선택된 연도, 클릭 없을 시 기본 2026년/최신연도)
        pie_year = selected_year
        if line_event and "selection" in line_event and len(line_event["selection"]["points"]) > 0:
            pie_year = line_event["selection"]["points"][0]["x"]
        
        st.divider()
        st.markdown(f"### 🍰 {pie_year}년 연령별 인구 비율")
        
        # 3) 선택 연도의 연령대별 원그래프(Pie Chart) 생성
        region_age = age_data[(age_data['sigungu_code'] == code) & (age_data['연도'] == pie_year)]
        
        if not region_age.empty:
            # 연령대를 10세 단위 및 65세 이상 구분그룹으로 묶기
            age_row = region_age.iloc[0]
            
            # 연령대 그룹 생성 (0~14세, 15~64세, 65세 이상)
            group_0_14 = 0
            group_15_64 = 0
            group_65_plus = 0
            
            for col in [c for c in age_data.columns if c.startswith('계_')]:
                age_num = col.replace('계_', '').replace('세', '').replace(' 이상', '')
                val = age_row[col]
                if age_num.isdigit():
                    n = int(age_num)
                    if n < 15:
                        group_0_14 += val
                    elif 15 <= n < 65:
                        group_15_64 += val
                    else:
                        group_65_plus += val
                elif age_num == '100':
                    group_65_plus += val
                    
            pie_df = pd.DataFrame({
                '연령구분': ['유소년인구 (0~14세)', '생산연령인구 (15~64세)', '고령인구 (65세 이상)'],
                '인구수': [group_0_14, group_15_64, group_65_plus]
            })
            
            fig_pie = px.pie(
                pie_df,
                names='연령구분',
                values='인구수',
                title=f"{pie_year}년 {name} 인구 구조 비율",
                color='연령구분',
                color_discrete_map={
                    '유소년인구 (0~14세)': '#2b83ba',
                    '생산연령인구 (15~64세)': '#abdda4',
                    '고령인구 (65세 이상)': '#d7191c'
                },
                hole=0.3
            )
            fig_pie.update_traces(textinfo='percent+label+value')
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.warning("해당 연도의 세부 연령 데이터가 존재하지 않습니다.")

    # Dialog 실행
    show_detail_modal(clicked_code, target_name)
