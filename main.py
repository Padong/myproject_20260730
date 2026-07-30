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
    page_title="전국 고령화 지도(심층 분석 ver)",
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
    grouped = df.groupby(['연도', 'sigungu_code', '시도', '시군구'], as_index=False)[['총인구', '65세이상인구']].sum()
    
    # 고령화율(%) 계산
    grouped['고령화율'] = (grouped['65세이상인구'] / grouped['총인구']) * 100
    grouped['고령화율'] = grouped['고령화율'].round(2)
    
    # 5단계 구간 나누기 (19%, 23%, 28%, 38% 기준)
    bins = [0, 19, 23, 28, 38, 100]
    labels = ['19% 미만', '19% ~ 23%', '23% ~ 28%', '28% ~ 38%', '38% 이상']
    grouped['고령화구간'] = pd.cut(grouped['고령화율'], bins=bins, labels=labels, right=False)
    
    # 시군구 식별용 풀네임 생성 (예: '서울특별시 강남구')
    grouped['지역풀네임'] = grouped['시도'] + " " + grouped['시군구']
    
    # 연령대별 세부 분석용 원본 읍면동 데이터도 시군구 단위로 합산하여 반환
    df_age_grouped = df.groupby(['연도', 'sigungu_code'])[total_cols].sum().reset_index()
    
    return grouped, df_age_grouped

geojson_data = load_geojson()
pop_data, age_data = load_data()

# 사용 가능한 연도 목록
years = sorted(pop_data['연도'].unique())
max_year = max(years)

# 시군구 풀네임 - 코드를 연결하는 매핑 사전 생성
region_info_df = pop_data[['지역풀네임', 'sigungu_code']].drop_duplicates().sort_values('지역풀네임')
region_options = ["전체 (전국 지도)"] + list(region_info_df['지역풀네임'])
code_to_name = dict(zip(region_info_df['sigungu_code'], region_info_df['지역풀네임']))
name_to_code = dict(zip(region_info_df['지역풀네임'], region_info_df['sigungu_code']))

# -----------------------------------------------------------------------------
# 3. 세션 상태(Session State) 초기화
# -----------------------------------------------------------------------------
if 'selected_year' not in st.session_state:
    st.session_state['selected_year'] = max_year

if 'selected_region' not in st.session_state:
    st.session_state['selected_region'] = "전체 (전국 지도)"

if 'pie_year' not in st.session_state:
    st.session_state['pie_year'] = max_year

# -----------------------------------------------------------------------------
# 4. 사이드바 제어
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ 지도 및 지역 제어")

# 1) 연도 선택
selected_year = st.sidebar.selectbox(
    "📅 조회할 연도",
    years,
    index=years.index(st.session_state['selected_year']),
    key='year_selectbox'
)
st.session_state['selected_year'] = selected_year

# 2) 지역 선택 (추가된 기능)
selected_region = st.sidebar.selectbox(
    "🏢 조회할 지역",
    region_options,
    index=region_options.index(st.session_state['selected_region']) if st.session_state['selected_region'] in region_options else 0,
    key='region_selectbox'
)
st.session_state['selected_region'] = selected_region

# 3) 애니메이션 시뮬레이션 버튼
def run_simulation():
    for y in years:
        st.session_state['selected_year'] = y
        time.sleep(0.5)
        st.rerun()

if st.sidebar.button("▶️ 2015~2026 연도별 변화 시뮬레이션"):
    run_simulation()

# 선택된 연도 데이터 필터링
current_df = pop_data[pop_data['연도'] == selected_year].copy()

# -----------------------------------------------------------------------------
# 5. Plotly 단계구분도 (Choropleth Map) 생성
# -----------------------------------------------------------------------------
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
    featureidkey="properties.코드",
    color='고령화구간',
    color_discrete_map=color_discrete_map,
    category_orders=category_orders,
    mapbox_style="white-bg",
    center={"lat": 35.9, "lon": 127.8},
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
    margin={"r":0, "t":30, "l":0, "b":0},
    title=f"<b>[{selected_year}년] 전국 시군구 고령화율 지도</b> (지도를 클릭하면 해당 지역 분석이 열립니다)",
    legend_title_text="<b>고령화 비율 구간</b>",
    clickmode='event+select'
)

# 지도 출력 및 클릭 이벤트 처리
map_event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="main_map")

# 지도를 클릭했을 때 클릭한 지역을 세션 상태에 반영
if map_event and "selection" in map_event and len(map_event["selection"]["points"]) > 0:
    clicked_code = map_event["selection"]["points"][0]["location"]
    if clicked_code in code_to_name:
        clicked_region_name = code_to_name[clicked_code]
        if st.session_state['selected_region'] != clicked_region_name:
            st.session_state['selected_region'] = clicked_region_name
            st.rerun()

# -----------------------------------------------------------------------------
# 6. 고령화율 상위/하위 10개 지역 표 (메인 화면)
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
# 7. 선택된 지역 팝업(Dialog) 창 - 추이 그래프 & 원그래프 연동 개선
# -----------------------------------------------------------------------------
if st.session_state['selected_region'] != "전체 (전국 지도)":
    region_full_name = st.session_state['selected_region']
    target_code = name_to_code.get(region_full_name)

    @st.dialog(f"🔍 {region_full_name} 고령화 상세 분석", width="large")
    def show_detail_dialog(code, name):
        st.write(f"**행정구역 코드:** `{code}`")
        
        # 1) 시군구 연도별 추이 데이터
        region_history = pop_data[pop_data['sigungu_code'] == code].sort_values('연도')
        
        # 2) 추이 꺾은선 그래프
        fig_line = px.line(
            region_history,
            x='연도',
            y='고령화율',
            markers=True,
            title=f"📈 {name} 연도별 고령화율 추이 (2015~2026)",
            labels={'고령화율': '고령화율 (%)', '연도': '연도'}
        )
        
        fig_line.update_traces(
            mode='lines+markers',
            marker=dict(size=10, color='#e34a33'),
            line=dict(color='#e34a33', width=3),
            hovertemplate="<b>%{x}년</b><br>고령화율: <b>%{y:.2f}%</b><extra></extra>"
        )
        
        fig_line.update_layout(clickmode='event+select')
        
        st.markdown("💡 **그래프 상의 연도 포인트를 클릭**하거나 아래 **슬라이더**를 조작하여 원그래프 연도를 변경하세요.")
        
        line_event = st.plotly_chart(fig_line, use_container_width=True, on_select="rerun", key="trend_line_chart")
        
        # 추이 그래프 포인트 클릭 감지 및 연도 업데이트
        if line_event and "selection" in line_event and len(line_event["selection"]["points"]) > 0:
            clicked_point_x = line_event["selection"]["points"][0]["x"]
            if clicked_point_x in years and clicked_point_x != st.session_state['pie_year']:
                st.session_state['pie_year'] = int(clicked_point_x)
                st.rerun()

        # 연도 선택 슬라이더 (그래프 클릭과 100% 연동)
        selected_pie_y = st.select_slider(
            "🍰 원그래프 연도 선택:",
            options=years,
            value=st.session_state['pie_year'],
            key="pie_year_slider"
        )
        if selected_pie_y != st.session_state['pie_year']:
            st.session_state['pie_year'] = selected_pie_y
            st.rerun()

        st.divider()
        st.markdown(f"### 🍰 {st.session_state['pie_year']}년 연령별 인구 구조 비율")
        
        # 3) 선택된 연도의 연령대별 원그래프(Pie Chart)
        region_age = age_data[(age_data['sigungu_code'] == code) & (age_data['연도'] == st.session_state['pie_year'])]
        
        if not region_age.empty:
            age_row = region_age.iloc[0]
            
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
                title=f"{st.session_state['pie_year']}년 {name} 인구 구성",
                color='연령구분',
                color_discrete_map={
                    '유소년인구 (0~14세)': '#2b83ba',
                    '생산연령인구 (15~64세)': '#abdda4',
                    '고령인구 (65세 이상)': '#d7191c'
                },
                hole=0.35
            )
            fig_pie.update_traces(textinfo='percent+label+value')
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.warning("해당 연도의 인구 데이터가 없습니다.")

        # 닫기 / 전체 지도로 복귀 버튼
        if st.button("❌ 닫기 (전체 지도로 돌아가기)", use_container_width=True):
            st.session_state['selected_region'] = "전체 (전국 지도)"
            st.rerun()

    show_detail_dialog(target_code, region_full_name)
