import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import json

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=2)  # 最大并发请求数
history_file = 'ip_history.txt'  # 存储查询过的 IP 地址和数据


def read_history():
    """读取历史记录文件中的 IP 地址及其数据"""
    history = {}
    try:
        with open(history_file, 'r') as f:
            for line in f:
                line = line.strip()
                if '-' in line:
                    try:
                        ip, source, data = line.split('-', 2)
                        if ip not in history:
                            history[ip] = {}
                        history[ip][source] = json.loads(data)
                    except ValueError:
                        print(f"无法解析的行: {line}")
    except FileNotFoundError:
        print("历史记录文件未找到")
    return history


def write_history(ip, source, data):
    """将查询过的 IP 地址及其来源的数据写入历史记录文件"""
    with open(history_file, 'a') as f:
        f.write(f"{ip}-{source}-{json.dumps(data)}\n")


def fetch_data_from_url(url, name, parse_func):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    start_time = time.time()
    response = requests.get(url, headers=headers)
    elapsed_time = time.time() - start_time

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        data = parse_func(soup)
        return name, elapsed_time, data

    return name, elapsed_time, {'error': '未能获取数据'}


def parse_ipshudi_data(soup):
    table = soup.find('div', class_='ft').find('table')
    data = {}
    if table:
        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) == 2:
                key = cols[0].text.strip()
                value = cols[1]
                if key == '归属地':
                    span = value.find('span')
                    if span:
                        data[key] = span.get_text(strip=True)
                else:
                    data[key] = value.get_text(strip=True)
    return data


def parse_ip138_data(soup):
    table = soup.find('div', class_='table-box').find('table')
    data = {}
    if table:
        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) == 2:
                key = cols[0].text.strip()
                value = cols[1]
                if key == 'ASN归属地':
                    span = value.find('span')
                    if span:
                        data[key] = span.get_text(strip=True)
                else:
                    data[key] = value.get_text(strip=True)
    return data


@app.route('/api/ipshudi/<ip>', methods=['GET'])
def get_ipshudi_info(ip):
    history = read_history()
    if ip in history and 'ipshudi' in history[ip]:
        return jsonify(history[ip]['ipshudi']), 200

    url = f'https://www.ipshudi.com/{ip}.htm'
    name, elapsed_time, data = fetch_data_from_url(url, 'ipshudi', parse_ipshudi_data)
    if 'error' in data:
        return jsonify(data), 500

    write_history(ip, 'ipshudi', data)
    return jsonify(data)


@app.route('/api/ip138/<ip>', methods=['GET'])
def get_ip138_info(ip):
    history = read_history()
    if ip in history and 'ip138' in history[ip]:
        return jsonify(history[ip]['ip138']), 200

    url = f'https://www.ip138.com/iplookup.php?ip={ip}'
    name, elapsed_time, data = fetch_data_from_url(url, 'ip138', parse_ip138_data)
    if 'error' in data:
        return jsonify(data), 500

    write_history(ip, 'ip138', data)
    return jsonify(data)


@app.route('/api/ip/<ip>', methods=['GET'])
def get_fastest_ip_info(ip):
    history = read_history()
    if ip in history:
        # 如果 IP 存在，优先返回上次最快的结果
        if 'fastest' in history[ip]:
            return jsonify(history[ip]['fastest']), 200

    urls = {
        'ipshudi': f'https://www.ipshudi.com/{ip}.htm',
        'ip138': f'https://www.ip138.com/iplookup.php?ip={ip}'
    }

    futures = [executor.submit(fetch_data_from_url, url, name, parse_func) for name, url, parse_func in
               zip(urls.keys(), urls.values(), [parse_ipshudi_data, parse_ip138_data])]

    results = {}
    fastest_name = None
    fastest_time = float('inf')

    for future in as_completed(futures):
        name, elapsed_time, data = future.result()
        print(f"{name} 的数据: {data}")  # 调试输出
        if 'error' not in data:
            results[name] = data
            if elapsed_time < fastest_time:
                fastest_time = elapsed_time
                fastest_name = name

    if fastest_name:
        write_history(ip, 'fastest', results[fastest_name])
        return jsonify(results[fastest_name])
    else:
        return jsonify({'error': '所有数据源均未返回有效数据'}), 500


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)
