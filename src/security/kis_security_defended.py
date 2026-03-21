from __future__ import annotations

import os
import ssl
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

import pandas as pd

MASTER_BASE = "https://new.real.download.dws.co.kr/common/master"
KIND_CORP_LIST_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
OUT_DIR = Path("krx_outputs")
OUTPUT_FILENAME = "stock_classification.csv"
USER_AGENT = "Mozilla/5.0"

# -----------------------------
# KOSPI / KOSDAQ 공식 정제코드 기준 widths
# -----------------------------
KOSPI_WIDTHS = [
    2, 1, 4, 4, 4, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 9, 5, 5, 1, 1, 1, 2, 1, 1,
    1, 2, 2, 2, 3, 1, 3, 12, 12, 8,
    15, 21, 2, 7, 1, 1, 1, 1, 1, 9,
    9, 9, 5, 9, 8, 9, 3, 1, 1, 1,
]

KOSPI_FIELDS = [
    "증권그룹코드", "시가총액규모구분코드", "지수업종대분류코드", "지수업종중분류코드", "지수업종소분류코드",
    "제조업여부", "저유동성여부", "지배구조지수종목여부", "KOSPI200섹터업종코드", "KOSPI100여부",
    "KOSPI50여부", "KRX종목여부", "ETP상품구분코드", "ELW발행여부", "KRX100여부",
    "KRX자동차여부", "KRX반도체여부", "KRX바이오여부", "KRX은행여부", "SPAC여부",
    "KRX에너지화학여부", "KRX철강여부", "단기과열코드", "KRX미디어통신여부", "KRX건설여부",
    "삭제필드1", "KRX증권여부", "KRX선박여부", "KRX보험여부", "KRX운송여부",
    "SRI여부", "기준가", "정규시장매매수량단위", "시간외시장매매수량단위", "거래정지여부",
    "정리매매여부", "관리종목여부", "시장경고구분코드", "시장경고위험예고여부", "불성실공시여부",
    "우회상장여부", "락구분코드", "액면가변경구분코드", "증자구분코드", "증거금비율",
    "신용가능여부", "신용기간", "전일거래량", "액면가", "상장일자",
    "상장주수천주", "자본금", "결산월", "공모가", "우선주구분코드",
    "공매도과열여부", "이상급등여부", "KRX300여부", "KOSPI여부", "매출액",
    "영업이익", "경상이익", "당기순이익", "ROE", "기준년월",
    "시가총액억", "그룹사코드", "회사신용한도초과여부", "담보대출가능여부", "대주가능여부",
]

KOSDAQ_WIDTHS = [
    2, 1, 4, 4, 4, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 9, 5, 5, 1,
    1, 1, 2, 1, 1, 1, 2, 2, 2, 3,
    1, 3, 12, 12, 8, 15, 21, 2, 7, 1,
    1, 1, 1, 9, 9, 9, 5, 9, 8, 9,
    3, 1, 1, 1,
]

KOSDAQ_FIELDS = [
    "증권그룹코드", "시가총액규모구분코드", "지수업종대분류코드", "지수업종중분류코드", "지수업종소분류코드",
    "벤처기업여부", "저유동성여부", "KRX종목여부", "ETP상품구분코드", "KRX100여부",
    "KRX자동차여부", "KRX반도체여부", "KRX바이오여부", "KRX은행여부", "SPAC여부",
    "KRX에너지화학여부", "KRX철강여부", "단기과열코드", "KRX미디어통신여부", "KRX건설여부",
    "투자주의환기여부", "KRX증권여부", "KRX선박여부", "KRX보험여부", "KRX운송여부",
    "KOSDAQ150여부", "기준가", "정규시장매매수량단위", "시간외시장매매수량단위", "거래정지여부",
    "정리매매여부", "관리종목여부", "시장경고구분코드", "시장경고위험예고여부", "불성실공시여부",
    "우회상장여부", "락구분코드", "액면가변경구분코드", "증자구분코드", "증거금비율",
    "신용가능여부", "신용기간", "전일거래량", "액면가", "상장일자",
    "상장주수천주", "자본금", "결산월", "공모가", "우선주구분코드",
    "공매도과열여부", "이상급등여부", "KRX300여부", "매출액", "영업이익",
    "경상이익", "당기순이익", "ROE", "기준년월", "시가총액억",
    "그룹사코드", "회사신용한도초과여부", "담보대출가능여부", "대주가능여부",
]

assert len(KOSPI_WIDTHS) == len(KOSPI_FIELDS)
assert len(KOSDAQ_WIDTHS) == len(KOSDAQ_FIELDS)

KIND_COLUMNS = ["종목코드", "회사명", "시장구분", "업종", "주요제품"]

KRX_FLAG_LABELS = [
    ("KRX반도체여부", "반도체"),
    ("KRX바이오여부", "바이오"),
    ("KRX은행여부", "은행"),
    ("KRX증권여부", "증권"),
    ("KRX보험여부", "보험"),
    ("KRX운송여부", "운송"),
    ("KRX자동차여부", "자동차"),
    ("KRX에너지화학여부", "에너지/화학"),
    ("KRX철강여부", "철강"),
    ("KRX미디어통신여부", "미디어/통신"),
    ("KRX건설여부", "건설"),
    ("KRX선박여부", "조선"),
]

KIND_INDUSTRY_RULES = [
    (("전자부품",), "전자부품"),
    (("반도체",), "반도체"),
    (("일차전지", "이차전지", "축전지"), "이차전지"),
    (("디스플레이",), "디스플레이"),
    (("통신 및 방송 장비",), "통신장비"),
    (("영상 및 음향기기",), "가전/전자제품"),
    (("컴퓨터 프로그래밍", "소프트웨어 개발"), "소프트웨어"),
    (("게임 소프트웨어",), "게임"),
    (("인터넷 정보매개", "포털 및 기타 인터넷 정보매개"), "인터넷서비스"),
    (("은행", "저축기관"), "은행"),
    (("증권",), "증권"),
    (("보험",), "보험"),
    (("자동차용 엔진", "자동차 제조"), "자동차"),
    (("자동차 신품 부품",), "자동차부품"),
    (("선박 및 보트 건조",), "조선"),
    (("항공 운송",), "항공"),
    (("해상 운송",), "해운"),
    (("창고 및 운송관련 서비스",), "물류"),
    (("의약품",), "제약"),
    (("자연과학 및 공학 연구개발",), "바이오"),
    (("의료용 기기",), "의료기기"),
    (("기초 화학물질", "합성고무", "합성수지"), "화학"),
    (("석유 정제품", "코크스"), "정유"),
    (("1차 철강",), "철강"),
    (("1차 비철금속",), "비철금속"),
    (("금속 가공",), "금속가공"),
    (("건물 건설", "토목"), "건설"),
    (("전기업",), "전력"),
    (("가스",), "가스"),
    (("도매 및 상품 중개", "종합 소매"), "유통"),
    (("음·식료품", "음료", "담배"), "음식료"),
    (("섬유제품", "의복", "봉제"), "섬유/의류"),
    (("종이 및 판지", "펄프"), "종이/포장"),
    (("여행사",), "여행"),
    (("숙박",), "호텔/레저"),
    (("오락", "스포츠 및 여가"), "레저"),
    (("방송업", "영화, 비디오물", "영상·오디오"), "미디어/콘텐츠"),
    (("광고업",), "광고/마케팅"),
]

PRODUCT_OVERRIDE_RULES = [
    (("2차전지", "이차전지", "BATTERY", "배터리", "ESS"), "이차전지"),
    (("반도체 제조", "메모리", "HBM", "DRAM", "NAND", "파운드리", "웨이퍼", "시스템반도체"), "반도체"),
    (("MLCC", "INDUCTOR", "CHIP RESISTOR", "카메라모듈", "통신모듈", "전자부품", "패키지 기판", "FC-BGA", "PCB"), "전자부품"),
    (("OLED", "LCD", "디스플레이"), "디스플레이"),
    (("반도체",), "반도체"),
    (("기지국", "안테나", "라우터", "통신장비", "네트워크 장비"), "통신장비"),
    (("TV", "냉장고", "세탁기", "영상기기", "음향기기", "가전"), "가전/전자제품"),
    (("바이오시밀러", "항체", "세포치료", "유전자치료"), "바이오"),
    (("신약", "원료의약품", "의약품"), "제약"),
    (("의료기기", "진단키트", "임플란트"), "의료기기"),
    (("화장품", "COSMETIC"), "화장품"),
]

FORCE_BASE_SMALL_LABELS = {
    "반도체",
    "전자부품",
    "이차전지",
    "디스플레이",
    "소프트웨어",
    "게임",
    "인터넷서비스",
    "은행",
    "증권",
    "보험",
    "자동차",
    "자동차부품",
    "조선",
    "항공",
    "해운",
    "물류",
    "제약",
    "바이오",
    "의료기기",
    "화학",
    "정유",
    "철강",
    "비철금속",
    "금속가공",
    "건설",
    "전력",
    "가스",
    "유통",
    "음식료",
    "섬유/의류",
    "종이/포장",
    "여행",
    "호텔/레저",
    "레저",
    "미디어/콘텐츠",
    "광고/마케팅",
    "화장품",
}

SMALL_TO_MIDDLE_MAP = {
    "반도체": "전기·전자",
    "전자부품": "전기·전자",
    "디스플레이": "전기·전자",
    "이차전지": "전기·전자",
    "통신장비": "전기·전자",
    "가전/전자제품": "전기·전자",
    "소프트웨어": "IT서비스",
    "게임": "IT서비스",
    "인터넷서비스": "IT서비스",
    "미디어/콘텐츠": "미디어/엔터",
    "광고/마케팅": "미디어/엔터",
    "은행": "금융",
    "증권": "금융",
    "보험": "금융",
    "자동차": "운송장비·부품",
    "자동차부품": "운송장비·부품",
    "조선": "운송장비·부품",
    "항공": "운송·창고",
    "해운": "운송·창고",
    "물류": "운송·창고",
    "제약": "건강관리",
    "바이오": "건강관리",
    "의료기기": "건강관리",
    "화장품": "생활소비재",
    "화학": "화학",
    "정유": "에너지/화학",
    "철강": "철강·소재",
    "비철금속": "철강·소재",
    "금속가공": "철강·소재",
    "건설": "건설",
    "전력": "전기·가스",
    "가스": "전기·가스",
    "유통": "유통",
    "음식료": "음식료·담배",
    "섬유/의류": "섬유·의류",
    "종이/포장": "종이·목재",
    "여행": "서비스",
    "호텔/레저": "서비스",
    "레저": "서비스",
}

SMALL_TO_LARGE_MAP = {
    "반도체": "제조",
    "전자부품": "제조",
    "디스플레이": "제조",
    "이차전지": "제조",
    "통신장비": "제조",
    "가전/전자제품": "제조",
    "자동차": "제조",
    "자동차부품": "제조",
    "조선": "제조",
    "제약": "제조",
    "바이오": "제조",
    "의료기기": "제조",
    "화장품": "제조",
    "화학": "제조",
    "정유": "제조",
    "철강": "제조",
    "비철금속": "제조",
    "금속가공": "제조",
    "음식료": "제조",
    "섬유/의류": "제조",
    "종이/포장": "제조",
    "은행": "금융",
    "증권": "금융",
    "보험": "금융",
    "소프트웨어": "서비스",
    "게임": "서비스",
    "인터넷서비스": "서비스",
    "미디어/콘텐츠": "서비스",
    "광고/마케팅": "서비스",
    "여행": "서비스",
    "호텔/레저": "서비스",
    "레저": "서비스",
    "항공": "서비스",
    "해운": "서비스",
    "물류": "서비스",
    "유통": "서비스",
    "건설": "제조",
    "전력": "유틸리티",
    "가스": "유틸리티",
}


class KindCorpListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_td = False
        self.in_th = False
        self.current: list[str] = []
        self.row: list[str] = []
        self.headers: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "td":
            self.in_td = True
            self.current = []
        elif tag == "th":
            self.in_th = True
            self.current = []
        elif tag == "tr":
            self.row = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.in_td:
            self.row.append(" ".join("".join(self.current).split()))
            self.in_td = False
        elif tag == "th" and self.in_th:
            self.headers.append(" ".join("".join(self.current).split()))
            self.in_th = False
        elif tag == "tr":
            if self.row:
                self.rows.append(self.row)
                self.row = []

    def handle_data(self, data: str) -> None:
        if self.in_td or self.in_th:
            self.current.append(data)


def _clean_scalar(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _clean_columns(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    out = df.copy()
    target_cols = columns or list(out.columns)
    for col in target_cols:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str).str.strip()
    return out


def _is_valid_idx_code(code: object) -> bool:
    value = _clean_scalar(code)
    return value not in {"", "0000"}


def _normalize_stock_code(code: object) -> str:
    value = _clean_scalar(code).upper()
    if value.isdigit():
        return value.zfill(6)
    return value


def _normalize_text(text: object) -> str:
    return " ".join(_clean_scalar(text).upper().split())


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword.upper() in text for keyword in keywords)


def _fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, context=ssl._create_unverified_context()) as response:
        return response.read()


def download_and_extract(zip_filename: str, extracted_filename: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / zip_filename
    zip_path.write_bytes(_fetch_bytes(f"{MASTER_BASE}/{zip_filename}"))

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)

    zip_path.unlink(missing_ok=True)
    return out_dir / extracted_filename


def split_fixed_width(text: str, widths: Iterable[int], field_names: Iterable[str]) -> dict[str, str]:
    position = 0
    out: dict[str, str] = {}
    for width, name in zip(widths, field_names):
        out[name] = text[position:position + width].strip()
        position += width
    return out


def _score_sector_name(code: str, name: str) -> tuple[int, int, int]:
    text = (name or "").strip()
    if not text:
        return (10_000, 0, 0)

    penalty = 0
    if text[0].isdigit():
        penalty += 100
    if code and text.startswith(code[-2:]):
        penalty += 30

    readable = sum(character.isalpha() or ("가" <= character <= "힣") for character in text)
    return (penalty, -readable, len(text))


def choose_sector_name(code: str, raw_line: str) -> tuple[str, str]:
    candidate_fixed = raw_line[5:45].rstrip()
    candidate_official = raw_line[3:43].rstrip()

    if _score_sector_name(code, candidate_fixed) <= _score_sector_name(code, candidate_official):
        return candidate_fixed.strip(), "5:45"
    return candidate_official.strip(), "3:43"


def load_sector_master(workdir: Path) -> pd.DataFrame:
    path = download_and_extract("idxcode.mst.zip", "idxcode.mst", workdir)

    rows = []
    with open(path, "r", encoding="cp949") as file:
        for raw_line in file:
            if not raw_line.strip():
                continue

            market_div = raw_line[0:1]
            sector_code = raw_line[1:5].strip()
            sector_name, parse_mode = choose_sector_name(sector_code, raw_line)

            rows.append(
                {
                    "업종시장구분": market_div,
                    "업종코드": sector_code.zfill(4) if sector_code else "",
                    "업종명": sector_name,
                    "업종명파싱방식": parse_mode,
                }
            )

    df = pd.DataFrame(rows)
    df = _clean_columns(df)
    df = df[(df["업종코드"] != "") & (df["업종명"] != "")]
    return df.drop_duplicates(subset=["업종코드", "업종명"], keep="first").reset_index(drop=True)


def parse_stock_master(path: Path, market: str, tail_width: int, widths: list[int], field_names: list[str]) -> pd.DataFrame:
    rows = []
    with open(path, "r", encoding="cp949") as file:
        for raw_line in file:
            if not raw_line.strip():
                continue

            front = raw_line[0 : len(raw_line) - tail_width]
            tail = raw_line[-tail_width:]

            record = {
                "시장": market,
                "종목코드": _normalize_stock_code(front[0:9].rstrip()),
                "표준코드": front[9:21].rstrip(),
                "종목명": front[21:].strip(),
            }
            record.update(split_fixed_width(tail, widths, field_names))
            rows.append(record)

    df = pd.DataFrame(rows)
    df = _clean_columns(df)

    for column in ["지수업종대분류코드", "지수업종중분류코드", "지수업종소분류코드"]:
        mask = df[column] != ""
        df.loc[mask, column] = df.loc[mask, column].str.zfill(4)

    return df


def load_kospi_master(workdir: Path) -> pd.DataFrame:
    path = download_and_extract("kospi_code.mst.zip", "kospi_code.mst", workdir)
    return parse_stock_master(path, "KOSPI", 228, KOSPI_WIDTHS, KOSPI_FIELDS)


def load_kosdaq_master(workdir: Path) -> pd.DataFrame:
    path = download_and_extract("kosdaq_code.mst.zip", "kosdaq_code.mst", workdir)
    return parse_stock_master(path, "KOSDAQ", 222, KOSDAQ_WIDTHS, KOSDAQ_FIELDS)


def attach_sector_names(stock_df: pd.DataFrame, sector_df: pd.DataFrame) -> pd.DataFrame:
    lookup = sector_df[["업종코드", "업종명"]].drop_duplicates().copy()
    out = stock_df.copy()

    for code_column, name_column in [
        ("지수업종대분류코드", "지수업종대분류명"),
        ("지수업종중분류코드", "지수업종중분류명"),
        ("지수업종소분류코드", "지수업종소분류명"),
    ]:
        out = out.merge(
            lookup.rename(columns={"업종코드": code_column, "업종명": name_column}),
            on=code_column,
            how="left",
        )
        out[name_column] = out[name_column].fillna("")

    return _clean_columns(out)


def classify_security(row: pd.Series) -> tuple[str, str]:
    group_code = row.get("증권그룹코드", "")
    etp_code = row.get("ETP상품구분코드", "")
    preferred_code = row.get("우선주구분코드", "")
    is_spac = row.get("SPAC여부", "")

    if is_spac == "Y":
        return "SPAC", "SPAC"

    if preferred_code == "1":
        return "우선주", "구형우선주"
    if preferred_code == "2":
        return "우선주", "신형우선주"

    if etp_code in {"1", "2"} or group_code in {"EF", "FE"}:
        return "ETF", "ETF"
    if etp_code == "3":
        return "ETN", "ETN"
    if etp_code == "4":
        return "ETN", "손실제한ETN"
    if etp_code == "5":
        return "상장형수익증권", "상장형수익증권"

    if group_code == "ST":
        return "보통주", "보통주"
    if group_code == "RT":
        return "리츠", "부동산투자회사"
    if group_code == "MF":
        return "투자회사", "증권투자회사"
    if group_code == "SC":
        return "투자회사", "선박투자회사"
    if group_code == "IF":
        return "투자회사", "사회간접자본투융자회사"
    if group_code == "DR":
        return "예탁증서", "DR"
    if group_code == "EW":
        return "ELW", "ELW"
    if group_code == "SW":
        return "신주인수권", "신주인수권증권"
    if group_code == "SR":
        return "신주인수권", "신주인수권증서"
    if group_code == "BC":
        return "수익증권", "수익증권"
    if group_code == "FS":
        return "외국주권", "외국주권"

    return "기타", _clean_scalar(group_code) or "미분류"


def load_kind_company_profiles() -> pd.DataFrame:
    html = _fetch_bytes(KIND_CORP_LIST_URL).decode("euc-kr", "replace")
    return parse_kind_company_list_html(html)


def parse_kind_company_list_html(html: str) -> pd.DataFrame:
    parser = KindCorpListParser()
    parser.feed(html)
    rows = [row for row in parser.rows if len(row) == len(parser.headers)]
    df = pd.DataFrame(rows, columns=parser.headers)
    df = _clean_columns(df)
    df["종목코드"] = df["종목코드"].map(_normalize_stock_code)
    return df[KIND_COLUMNS].drop_duplicates(subset=["종목코드"], keep="first").reset_index(drop=True)


def _first_active_flag_label(row: pd.Series) -> str:
    for flag_column, label in KRX_FLAG_LABELS:
        if row.get(flag_column, "") == "Y":
            return label
    return ""


def _official_classification_name(row: pd.Series, code_column: str, name_column: str) -> str:
    if _is_valid_idx_code(row.get(code_column, "")):
        return _clean_scalar(row.get(name_column, ""))
    return ""


def normalize_kind_industry(industry: object) -> str:
    text = _clean_scalar(industry)
    normalized = _normalize_text(industry)

    for keywords, label in KIND_INDUSTRY_RULES:
        if _contains_any(normalized, keywords):
            return label

    return text.replace(" 제조업", "").replace("업", "").strip()


def detect_product_override(row: pd.Series) -> str:
    combined_text = _normalize_text(f"{row.get('업종', '')} {row.get('주요제품', '')}")
    for keywords, label in PRODUCT_OVERRIDE_RULES:
        if _contains_any(combined_text, keywords):
            return label
    return ""


def determine_small_classification(row: pd.Series) -> str:
    official_small = _official_classification_name(row, "지수업종소분류코드", "지수업종소분류명")
    if official_small:
        return official_small

    kind_base = normalize_kind_industry(row.get("업종", ""))
    if kind_base in FORCE_BASE_SMALL_LABELS:
        return kind_base

    product_override = detect_product_override(row)
    if product_override:
        return product_override

    flag_label = _first_active_flag_label(row)
    if flag_label:
        return flag_label

    if kind_base:
        return kind_base

    official_middle = _official_classification_name(row, "지수업종중분류코드", "지수업종중분류명")
    if official_middle:
        return official_middle

    official_large = _official_classification_name(row, "지수업종대분류코드", "지수업종대분류명")
    if official_large:
        return official_large

    return "미분류"


def determine_middle_classification(row: pd.Series, small_classification: str) -> str:
    official_middle = _official_classification_name(row, "지수업종중분류코드", "지수업종중분류명")
    if official_middle:
        return official_middle

    inferred_middle = SMALL_TO_MIDDLE_MAP.get(small_classification, "")
    if inferred_middle:
        return inferred_middle

    official_large = _official_classification_name(row, "지수업종대분류코드", "지수업종대분류명")
    if official_large:
        return official_large

    return SMALL_TO_LARGE_MAP.get(small_classification, "기타")


def determine_large_classification(row: pd.Series, small_classification: str, middle_classification: str) -> str:
    official_large = _official_classification_name(row, "지수업종대분류코드", "지수업종대분류명")
    if official_large:
        return official_large

    inferred_large = SMALL_TO_LARGE_MAP.get(small_classification, "")
    if inferred_large:
        return inferred_large

    if middle_classification:
        return middle_classification

    return "기타"


def build_classification_frame(stock_df: pd.DataFrame, kind_df: pd.DataFrame) -> pd.DataFrame:
    stocks = _clean_columns(stock_df)
    stocks["종목코드"] = stocks["종목코드"].map(_normalize_stock_code)

    kind_profiles = _clean_columns(kind_df, KIND_COLUMNS)
    kind_profiles["종목코드"] = kind_profiles["종목코드"].map(_normalize_stock_code)
    kind_profiles = kind_profiles[KIND_COLUMNS].drop_duplicates(subset=["종목코드"], keep="first")

    common_stocks = stocks[stocks.apply(lambda row: classify_security(row)[0] == "보통주", axis=1)].copy()
    common_stocks = common_stocks.merge(kind_profiles[["종목코드", "업종", "주요제품"]], on="종목코드", how="left")
    common_stocks = _clean_columns(common_stocks)

    common_stocks["소분류"] = common_stocks.apply(determine_small_classification, axis=1)
    common_stocks["중분류"] = common_stocks.apply(
        lambda row: determine_middle_classification(row, row["소분류"]),
        axis=1,
    )
    common_stocks["대분류"] = common_stocks.apply(
        lambda row: determine_large_classification(row, row["소분류"], row["중분류"]),
        axis=1,
    )

    result = common_stocks[["종목코드", "종목명", "대분류", "중분류", "소분류"]].copy()
    result = _clean_columns(result)
    return result.sort_values(["종목코드", "종목명"]).reset_index(drop=True)


def save_classification_csv(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / OUTPUT_FILENAME
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    workdir = Path(os.getcwd())
    out_dir = workdir / OUT_DIR

    print("1) 업종 마스터 다운로드 및 파싱")
    sector_df = load_sector_master(workdir)

    print("2) KOSPI/KOSDAQ 마스터 다운로드 및 파싱")
    kospi_df = load_kospi_master(workdir)
    kosdaq_df = load_kosdaq_master(workdir)

    print("3) KIND 상장법인 목록 다운로드")
    kind_df = load_kind_company_profiles()

    print("4) 보통주 분류 테이블 생성")
    all_stocks = pd.concat([kospi_df, kosdaq_df], ignore_index=True)
    all_stocks = attach_sector_names(all_stocks, sector_df)
    classification_df = build_classification_frame(all_stocks, kind_df)

    print("5) 단순 CSV 저장")
    output_path = save_classification_csv(classification_df, out_dir)

    print()
    print(f"완료: {output_path}")
    print(f"보통주 분류 수: {len(classification_df):,}")
    print("컬럼: 종목코드, 종목명, 대분류, 중분류, 소분류")


if __name__ == "__main__":
    main()
