'''

{
  "name": "fetch_tickets",
  "arguments": {
    "departure": "诺里奇",
    "destination": "伦敦",
    "departure_date": "2025-04-19",
    "departure_time": "09:00",
    "return_date": "2025-04-20",
    "return_time": "09:00",
    "trip_type": "single"/return / open return
    "bike_space":yes/no
  }
}

return:{
  "arguments": {
    "departure": "诺里奇",
    "destination": "伦敦",
    "departure_date": "2025-04-19",
    "departure_time": "09:00",
    "return_date": "2025-04-19",
    "return_time": "09:00",
    "trip_type": "single"/return / open return
    "dep_std_price":n GBP
    "dep_first_price":n GBP
    "ret_std_price":n GBP
    "ret_first_price":n GBP
  }
}

'''
import os
import urllib.request, urllib.error
from datetime import datetime
from difflib import SequenceMatcher

import xlrd
from selenium import webdriver
from selenium.common import ElementClickInterceptedException
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re
import xlwt
import urllib.parse
import csv
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from rapidfuzz import fuzz, process

def askURL(url):
    """
    获取指定URL的HTML内容，模拟浏览器请求。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        print(f"请求失败：{e.reason}")
        return None


def getPage(params):
    """
    https://www.nationalrail.co.uk/journey-planner/?
    type=return&
    origin=NRW&
    destination=182&
    leavingType=departing&
    leavingDate=200425&
    leavingHour=08&
    leavingMin=45&
    returnType=departing&
    returnDate=230425&
    returnHour=08&
    returnMin=45&
    adults=1&
    children=2&
    extraTime=0#I
    根据参数构造URL并解析出发与返程票价。
    返回一个列表，每项包含一次查询的数据。
    字段顺序：出发站、到达站、出发日期、出发时间、标准舱价、头等舱价、返程日期、返程时间、返程标准舱价、返程头等舱价
    via=LBG&
    viaType=change-at
    """
    chrome_opts = Options()  # remove window
    chrome_opts.add_argument("--headless")
    chrome_opts.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=chrome_opts)
    base = "https://www.nationalrail.co.uk/journey-planner/"
    query = urllib.parse.urlencode(params)
    url = base + "?" + query + "&extraTime=0"
    print("-- Opening url: ", url)
    driver.get(url)
    time.sleep(3)
    html = driver.page_source
    driver.quit()
    return html

def load_and_select(params, headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless")
        opts.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=opts) #options=opts

#https://www.nationalrail.co.uk/journey-planner/?type=return&origin=NRW&destination=BFR&leavingType=departing&leavingDate=210425&leavingHour=09&leavingMin=00&returnType=departing&returnDate=230425&returnHour=09&returnMin=00&adults=1&children=0&extraTime=0#O
    # 1. 打开 outward 页面
    base = "https://www.nationalrail.co.uk/journey-planner/"
    url = base + "?" + urllib.parse.urlencode(params) + "&extraTime=0#O"
    print(url)
    driver.get(url)


    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[id^='result-card-price-outward-1']"))
    )


    driver.execute_script("""

                  document.querySelectorAll('p.ot-dpd-desc, div.ot-sdk-container, span[data-testid="jp-summary-buy-primary-label"]')
                    .forEach(el=>el.style.display='none');

                  document.querySelectorAll('[class*="sc-"][style*="position: fixed"]')
                    .forEach(el=>el.style.zIndex=0);
                """)
    time.sleep(0.5)

    if params["type"] in ("return", "open return"):



        btns = driver.find_elements(
            By.CSS_SELECTOR,
            "input[data-testid^='button-jp-results-ticket-input-group-outward-']"
        )
        if not btns:
            driver.quit()
            raise RuntimeError("没有outward按钮")

        first_btn = btns[0]
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", first_btn)
        time.sleep(0.3)


        try:
            first_btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", first_btn)


        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[id^='result-card-price-inward-']"))
        )
        time.sleep(1)

    html = driver.page_source
    driver.quit()
    return html,url

def parse_journeys(html, params):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    #标准化日期
    dep_date = datetime.strptime(params["leavingDate"], "%d%m%y").date().isoformat()
    ret_date = ""
    if params.get("type") in ("return", "open return"):
        ret_date = datetime.strptime(params["returnDate"], "%d%m%y").date().isoformat()

    #抓所有Journey span
    journey_spans = soup.find_all("span", string=re.compile(r"- Journey \d+, Departs"))
    total = len(journey_spans)
    half = total // 2 if params.get("type") != "single" else total

    for idx, span in enumerate(journey_spans):
        text = span.get_text()
        origin   = re.search(r"from ([^,]+)", text).group(1)
        destination = re.search(r"at ([^,]+)", text).group(1)
        dep_time = re.search(r"Departs, ([0-9:]+)", text).group(1)
        duration = re.search(r"duration (.*), with", text).group(1)
        chm = re.search(r"with (\d+) change", text)
        changes = chm.group(1) if chm else "0"

        if idx < half:
            # outward price
            div_out = soup.find("div", id=f"result-card-price-outward-{idx}")
            span_p = div_out and div_out.find("span", string=re.compile(r"£"))
            out_price = span_p.get_text(strip=True) if span_p else ""
            # no return yet
            ret_time, in_price = "", ""
        else:
            # inward price
            j = idx - half
            ret_time = re.search(r"Departs, ([0-9:]+)", text).group(1)
            div_in = soup.find("div", id=f"result-card-price-inward-{j}")
            span_p = div_in and div_in.find("span", string=re.compile(r"£"))
            in_price = span_p.get_text(strip=True) if span_p else ""
            # no outward here
            out_price = ""

        # label
        label = ""
        for tag in ("fastest","cheapest","lowest"):
            attr = f"{'outward' if idx<half else 'inward'}-{idx if idx<half else j}-result-card-{tag}-label"
            lbl = soup.find("span", attrs={"data-testid": attr})
            if lbl:
                label = lbl.get_text(strip=True).split()[0]
                break

        results.append([
            origin, destination,
            dep_date, dep_time,
            out_price,
            ret_date, ret_time,
            in_price,
            duration, changes, label
        ])

    return results

def saveData(data, filename="rail_prices.xls"):
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("Journeys", cell_overwrite_ok=True)
    headers = [
        "Departure","Destination","Dep Date","Dep Time",
        "Out Price","Ret Date","Ret Time","Ret Price",
        "Duration","Changes","Label"
    ]
    for c,h in enumerate(headers):
        sheet.write(0,c,h)
    for r,row in enumerate(data,1):
        for c,val in enumerate(row):
            sheet.write(r,c,val)
    book.save(filename)
    print("已保存到", filename)




def load_crs_list(csv_path):
    crs_dict = {}
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            name = row['stationName']
            re.sub(r'\(.*?\)', '', name)
            name = name.strip().lower()
            code = row['crsCode'].strip().lower()
            crs_dict[name] = code
    return crs_dict


def normalize(text):
    text = re.sub(r"\(.*?\)", "", text)  # 去括号内容
    text = re.sub(r"[^\w\s]", "", text)  # 去除标点
    return text.lower().strip()


def find_crs(user_input, crs_dict):
    user_input = user_input.strip().lower()

    #精确匹配CRS code
    if user_input.upper() in crs_dict.values():
        return user_input.upper()

    #精确匹配标准化站名
    norm_input = normalize(user_input)
    norm_name_to_code = {normalize(name): code for name, code in crs_dict.items()}

    if norm_input in norm_name_to_code:
        return norm_name_to_code[norm_input].upper()

    #模糊匹配
    candidates = list(norm_name_to_code.keys())

    try:
        from rapidfuzz import process, fuzz
        USE_RAPIDFUZZ = True
    except ImportError:
        USE_RAPIDFUZZ = False

    if USE_RAPIDFUZZ:
        best_match, score, _ = process.extractOne(norm_input, candidates, scorer=fuzz.token_sort_ratio)
        if score >= 75:
            return norm_name_to_code[best_match].upper()
    else:
        def ratio(a, b): return SequenceMatcher(None, a, b).ratio()
        best_match = max(candidates, key=lambda c: ratio(norm_input, c))
        if ratio(norm_input, best_match) >= 0.75:
            return norm_name_to_code[best_match].upper()

    print(f"Unable to match CRS code for input: {user_input}")
    return None


def check_crs(params, crs_dict):
    origin_input = params.get("origin", "")
    dest_input = params.get("destination", "")

    origin_code = find_crs(origin_input, crs_dict)
    if not origin_code:
        print(f"\nOrigin not found: {origin_input}")
        return None

    dest_code = find_crs(dest_input, crs_dict)
    if not dest_code:
        print(f"\nDestination not found: {dest_input}")
        return None

    # 替换站名为 code
    params["origin"] = origin_code
    params["destination"] = dest_code
    return params


def call_scraping(params, outfile="rail_prices.xls"):
    print("当前查询参数:", params)
    html,url = load_and_select(params, headless=True)

    data = parse_journeys(html, params)
    if not data:
        raise RuntimeError("没有抓到任何行程信息")
    saveData(data, filename=outfile)

    return os.path.abspath(outfile),url


def find_cheapest_ticket(xls_path: str, ticket_type: str = "single") -> dict:
    """
    return ：
    {
        "dep_time": "09:30",
        "ret_time": "18:00",
        "total_price": 42.5,
        "label": "cheapest"
    }
    """
    book = xlrd.open_workbook(xls_path)
    sheet = book.sheet_by_index(0)

    COL_OUT_PRICE = 4
    COL_RET_PRICE = 7
    COL_DEP_TIME  = 3
    COL_RET_TIME  = 6
    COL_LABEL     = 10

    cheapest = None
    for row in range(1, sheet.nrows):
        out_price_cell = sheet.cell_value(row, COL_OUT_PRICE)
        ret_price_cell = sheet.cell_value(row, COL_RET_PRICE)

        out_price = float(out_price_cell.replace("£", "")) if out_price_cell else 0.0
        ret_price = float(ret_price_cell.replace("£", "")) if ret_price_cell else 0.0

        total = out_price + (ret_price if ticket_type != "single" else 0.0)

        if cheapest is None or total < cheapest["total_price"]:
            cheapest = {
                "dep_time": sheet.cell_value(row, COL_DEP_TIME),
                "ret_time": sheet.cell_value(row, COL_RET_TIME) if ticket_type != "single" else "",
                "total_price": total,
                "label": sheet.cell_value(row, COL_LABEL)
            }

    if cheapest is None:
        raise RuntimeError("解析票价失败")
    return cheapest

def parse_time_string(time_str):
    if not time_str or not isinstance(time_str, str):
        return "09", "00"

    keyword_map = {
        "morning": ("09", "00"),
        "afternoon": ("13", "00"),
        "evening": ("18", "00"),
        "night": ("20", "00")
    }
    for keyword, (h, m) in keyword_map.items():
        if keyword in time_str.lower():
            return h, m

    # 尝试 split
    if ":" in time_str:
        parts = time_str.strip().split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return parts[0].zfill(2), parts[1].zfill(2)

    # fallback
    return "09", "00"


def main():
    '''
    returns:
        params = {
        'type': 'return',           # 'single'/'return'/'open return'
        'origin': 'Norwich',            # 车站代码或名称
        'destination': 'BFR',       # 车站代码或名称
        'leavingType': 'departing',
        'leavingDate': '250425',  # ddmmyy
        'leavingHour': '09',
        'leavingMin': '00',
        'returnType': 'departing',
        'returnDate': '280425',
        'returnHour': '09',
        'returnMin': '00',
        'adults': 2,
        'children': 1,
        'via':None,
        'viaType': None,  # via / change-at / avoid / do-not-change-at
        #'via':'LBG',
        #'viaType': 'change-at',  # via / change-at / avoid / do-not-change-at
    }

    single:
        params = {
        'type': 'single',           # 'single'/'return'/'open return'
        'origin': 'Norwich',            # 车站代码或名称
        'destination': 'BFR',       # 车站代码或名称
        'leavingType': 'departing',
        'leavingDate': '250425',  # ddmmyy
        'leavingHour': '09',
        'leavingMin': '00',
        'returnType': None,
        'returnDate': None,
        'returnHour': None,
        'returnMin': None,
        'adults': 2,
        'children': 0,
        'via':None,
        'viaType': None,  # via / change-at / avoid / do-not-change-at
        #'via':'LBG',
        #'viaType': 'change-at',  # via / change-at / avoid / do-not-change-at
    }
    :return:
    '''
    # 示例输入参数
    params = {
        'type': 'single',  # 'single'/'return'/'open return'
        'origin': 'Norwich',  # 车站代码或名称
        'destination': 'BFR',  # 车站代码或名称
        'leavingType': 'departing',
        'leavingDate': '300525',  # ddmmyy
        'leavingHour': '09',
        'leavingMin': '00',
        'returnType': None,
        'returnDate': None,
        'returnHour': None,
        'returnMin': None,
        'adults': 2,
        'children': 0,
        'via': None,
        'viaType': None,  # via / change-at / avoid / do-not-change-at
        # 'via':'LBG',
        # 'viaType': 'change-at',  # via / change-at / avoid / do-not-change-at
    }

    #param preprocess (remove None)
    params = {k: v for k, v in params.items() if v is not None}

    crs_dict = load_crs_list("stations.csv")
    if check_crs(params,crs_dict)==False:
        return(print("\nStation crs code not found, please check spelling of your orgin or destination. "))
    html = load_and_select(params, headless=True)
    data = parse_journeys(html, params)
    if data:
        saveData(data)
    else:
        print("没有抓到任何行程信息")


if __name__ == '__main__':
    main()

