import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px

# 1. 페이지 기본 설정 (넓은 화면 레이아웃)
st.set_page_config(
    page_title="전국 시군구 고령화 지도",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ 전국 시군구 고령화율 지도")
st.write("2015~2026년 인구 데이터를 바탕으로 가장 최신 연도의 시군구별 고령화율(65세 이상 인구 비율)을 보여줍니다.")

# 2. 데이터 불러오기 함수 (캐싱을 적용하여 새로고침 시 빠른 로딩)
@st.cache_data
def load_data():
    # 인구 데이터 URL
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    # GeoJSON 지도 경계 데이터 URL
    geojson_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

    # [인구 데이터 읽기] '코드' 열은 5자리 잘라내기 위해 반드시 문자열(str)로 읽기
    df_pop = pd.read_csv(pop_url, dtype={'코드': str})

    # [GeoJSON 데이터 읽기] GeoPandas로 경계 데이터 불러오기
    gdf_sigungu = gpd.read_file(geojson_url)
    gdf_sigungu['코드'] = gdf_sigungu['코드'].astype(str)

    return df_pop, gdf_sigungu

# 데이터 로딩 상태 표시
with st.spinner("인구 데이터 및 지도 경계 데이터를 불러오는 중입니다..."):
    df_pop, gdf_sigungu = load_data()

# 3. 데이터 가공 (최신 연도 추출 및 고령화율 계산)
# (1) 가장 최신 연도 확인
latest_year = df_pop['연도'].max()

# (2) 최신 연도 데이터만 필터링
df_latest = df_pop[df_pop['연도'] == latest_year].copy()

# (3) 행정동 10자리 코드에서 앞 5자리를 추출하여 시군구 코드 생성
df_latest['시군구코드'] = df_latest['코드'].str.slice(0, 5)

# (4) 65세 이상 인구 열 찾기 ('계_65세'부터 '계_100세 이상'까지)
# '계_'로 시작하면서 숫자(65 이상) 또는 '100세 이상'인 컬럼 필터링
total_pop_col = '계_0세'  # 전체 인구 계산용 (모든 나이 열 합)
# 나이 관련 전체 컬럼 목록 (계_로 시작하는 컬럼)
all_age_cols = [col for col in df_latest.columns if col.startswith('계_')]

# 65세 이상 컬럼 선별
over_65_cols = []
for col in all_age_cols:
    age_str = col.replace('계_', '').replace('세', '').replace(' 이상', '')
    try:
        age_num = int(age_str)
        if age_num >= 65:
            over_65_cols.append(col)
    except ValueError:
        pass

# (5) 시군구 단위로 전체 인구수 및 65세 이상 인구수 합산
df_latest['총인구'] = df_latest[all_age_cols].sum(axis=1)
df_latest['고령인구'] = df_latest[over_65_cols].sum(axis=1)

# 시군구 코드로 그룹화하여 합계 계산
df_sigungu_pop = df_latest.groupby('시군구코드')[['총인구', '고령인구']].sum().reset_index()

# (6) 고령화율(%) 계산 (소수점 2자리 반올림)
df_sigungu_pop['고령화율'] = (df_sigungu_pop['고령인구'] / df_sigungu_pop['총인구'] * 100).round(2)

# (7) GeoJSON 경계 데이터와 인구 데이터 결합
# GeoJSON의 '코드' 속성과 인구 데이터의 '시군구코드'를 기준으로 병합
gdf_merged = gdf_sigungu.merge(df_sigungu_pop, left_on='코드', right_on='시군구코드', how='left')

# (8) 지정된 경계값(19%, 23%, 28%, 38%) 기준으로 5단계 구분을 위한 구간 생성
# 구간 라벨 정의
bins = [-1, 19, 23, 28, 38, 100]
labels = ['19% 미만', '19% 이상 ~ 23% 미만', '23% 이상 ~ 28% 미만', '28% 이상 ~ 38% 미만', '38% 이상']

gdf_merged['고령화율_구간'] = pd.cut(
    gdf_merged['고령화율'],
    bins=bins,
    labels=labels,
    right=False
)

# 4. 지도 시각화 (Plotly Choropleth)
st.subheader(f"📊 {latest_year}년 전국 시군구 고령화율 지도")

# Color Map 설정 (낮은 쪽은 옅고, 높은 쪽은 진하게)
color_sequence = ["#edf8fb", "#b2e2e2", "#66c2a4", "#2ca25f", "#006d2c"]

# Plotly 단계구분도 생성
fig = px.choropleth_mapbox(
    gdf_merged,
    geojson=gdf_merged.geometry,
    locations=gdf_merged.index,
    color='고령화율_구간',
    color_discrete_sequence=color_sequence,
    category_orders={'고령화율_구간': labels},
    mapbox_style="white-bg",  # 배경 지도 타일 없이 경계선만 표시
    center={"lat": 35.8, "lon": 127.8},  # 대한민국 중심 좌표
    zoom=6,
    hover_name='시군구',
    hover_data={
        '시도': True,
        '고령화율': ':.2f',
        '고령화율_구간': False
    },
    labels={
        '고령화율_구간': '고령화율 구간',
        '시도': '시도명',
        '고령화율': '고령화율(%)'
    }
)

# 지도 스타일 및 외곽선 투명도/색상 조정
fig.update_traces(
    marker_line_width=0.5,
    marker_line_color="#666666"
)

fig.update_layout(
    margin={"r": 0, "t": 10, "l": 0, "b": 10},
    height=650,
    legend_title_text="고령화율 구간",
    legend=dict(
        yanchor="top",
        y=0.98,
        xanchor="left",
        x=0.01,
        bgcolor="rgba(255, 255, 255, 0.8)"
    )
)

# 스트림릿에 지도 출력
st.plotly_chart(fig, use_container_width=True)

st.write("---")

# 5. 고령화율 상위 / 하위 10개 시군구 표 표시
st.subheader("📌 고령화율 상위 & 하위 TOP 10 지역")

# 상위 10개, 하위 10개 추출 및 표 양식 정돈
df_sorted = gdf_merged[['시도', '시군구', '고령화율', '총인구', '고령인구']].dropna().copy()

top_10 = df_sorted.sort_values(by='고령화율', ascending=False).head(10).reset_index(drop=True)
top_10.index = top_10.index + 1  # 순위를 1부터 시작

bottom_10 = df_sorted.sort_values(by='고령화율', ascending=True).head(10).reset_index(drop=True)
bottom_10.index = bottom_10.index + 1

# 나란히 배치하기 위해 컬럼 분할
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🔴 고령화율 가장 높은 곳 TOP 10")
    st.dataframe(
        top_10.style.format({'고령화율': '{:.2f}%', '총인구': '{:,}명', '고령인구': '{:,}명'}),
        use_container_width=True
    )

with col2:
    st.markdown("### 🔵 고령화율 가장 낮은 곳 TOP 10")
    st.dataframe(
        bottom_10.style.format({'고령화율': '{:.2f}%', '총인구': '{:,}명', '고령인구': '{:,}명'}),
        use_container_width=True
    )
