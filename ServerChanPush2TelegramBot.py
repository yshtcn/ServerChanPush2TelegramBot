from flask import Flask, request, jsonify
import requests
import logging
import json
import re
from urllib.parse import unquote
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import shutil

# 获取当前日期
current_date = datetime.now().strftime("%Y-%m-%d")

# 获取当前工作目录
base_dir = os.path.dirname(os.path.abspath(__file__))

# 定义数据和日志目录
data_dir = os.path.join(base_dir, "data")
log_dir = os.path.join(data_dir, "log")

# 创建必要的目录
os.makedirs(data_dir, exist_ok=True)
os.makedirs(log_dir, exist_ok=True)

# 检查配置文件是否存在，如果不存在则复制示例配置文件并退出程序
config_path = os.path.join(data_dir, 'bot_config.json')
example_config_path = os.path.join(base_dir, 'bot_config_example.json')
if not os.path.exists(config_path):
    if os.path.exists(example_config_path):
        shutil.copyfile(example_config_path, config_path)
        logging.error(f"Configuration file not found. {example_config_path} copied to {config_path}. Exiting.")
        sys.exit(1)
    else:
        logging.error(f"Configuration file not found and example config file {example_config_path} does not exist. Exiting.")
        sys.exit(1)

# 创建一个处理器，该处理器每天午夜都会创建一个新的日志文件
handler = TimedRotatingFileHandler(os.path.join(log_dir, f"received_requests_StartAt{current_date}.log"), when="midnight", interval=1, backupCount=10, encoding='utf-8')
handler.suffix = "To%Y-%m-%d.log"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 初始化 Flask 应用
app = Flask(__name__)

# 读取配置文件
def load_config():
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
        for bot_config in config:
            api_url_template = bot_config.get('api_url', '')
            main_bot_id = bot_config.get('main_bot_id', '')
            if '[AUTO_REPLACE_MAIN_BOT_ID]' in api_url_template:
                bot_config['api_url'] = api_url_template.replace('[AUTO_REPLACE_MAIN_BOT_ID]', main_bot_id)
        return config

# 保存接收到的请求数据
def save_received_data(received_url, received_data):
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(log_dir, f"received_data_{current_date}.json"), "a", encoding='utf-8') as f:
            json.dump({"received_url": received_url, "received_data": received_data}, f, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        logging.error(f"Failed to save received data: {e}")

# 保存发送的请求数据
def save_sent_data(api_url, payload):
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(log_dir, f"sent_data_{current_date}.json"), "a", encoding='utf-8') as f:
            json.dump({"sent_url": api_url, "sent_data": payload}, f, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        logging.error(f"Failed to save sent data: {e}")

def unescape_url(escaped_url: str) -> str:
    return escaped_url.replace("\\/", "/")

def convert_str_gbk_to_utf8(text_str):
    try:
        return text_str
    except:
        return text_str  # 如果转换失败，则返回原始字符串

# 读取待发送的消息
def read_pending_messages():
    try:
        with open(os.path.join(data_dir, "pending_messages.json"), "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

# 写入待发送的消息
def write_pending_messages(messages):
    with open(os.path.join(data_dir, "pending_messages.json"), "w") as f:
        json.dump(messages, f, ensure_ascii=False)

# 发送 Telegram 消息
def send_telegram_message(bot_id, chat_id, title, desp=None, url=None):
    # 重新读取配置文件
    all_bots_config = load_config()
    # 用于标记是否找到匹配的关键词
    found = False
    delimiter = None
    api_url = None
    proxies = None
    # 遍历所有主 bot_id 的配置
    for config in all_bots_config:
        main_bot_id = config['main_bot_id']
        main_chat_id = config.get('main_chat_id', '')  # 如果没有main_chat_id，默认为空字符串
        sub_bots = config['sub_bots']
        api_url = config.get('api_url', None)
        proxies = config.get('proxies', None)
        # 如果传入的 bot_id 和 chat_id 匹配某个主 bot_id 和主 chat_id
        if bot_id == main_bot_id and chat_id == main_chat_id:
            # 检查关键词，如果匹配则替换 bot_id 和 chat_id
            for sub_bot in sub_bots:
                for keyword in sub_bot['keywords']:
                    keyword_decode = keyword.decode('utf-8') if isinstance(keyword, bytes) else keyword
                    title_decode = title.decode('utf-8') if isinstance(title, bytes) else title
                    if keyword_decode.lower() in title_decode.lower():
                        bot_id = sub_bot['bot_id']
                        chat_id = sub_bot['chat_id']  # 替换 chat_id
                        delimiter = sub_bot.get('delimiter')  # 获取隔断符配置
                        found = True
                        break
            if found:
                break

        # 一旦找到匹配的主 bot_id 和主 chat_id，就跳出循环
        if found:
            break

    api_url = api_url or f"https://api.telegram.org/bot{bot_id}/sendMessage"
    text = title  # 初始化 text 为 title
    text += f"\n\n{(desp.split(delimiter)[0] if delimiter and desp else desp) if desp else ''}"
    text = text.rstrip()

    # 使用正则表达式来识别受影响的链接
    affected_urls = re.findall(r'(https|http|ftp)\\\\\\/\\\\\\/[\\w\\\\:\\\\/\\.\\-]+', text)
    
    # 对受影响的链接进行处理
    for affected_url in affected_urls:
        corrected_url = affected_url.replace('\\/', '/')
        text = text.replace(affected_url, corrected_url)

    if url:  # 如果有 url，添加到 text
        text += f"\n\n<a href=\"{url}\">详情：</a>"
        text += f"{url}"  # 直接添加 URL，Telegram 会自动处理预览
        text = unescape_url(text)

    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False  # 启用网页预览
    }

    try:
        response = requests.post(api_url, data=payload, proxies=proxies, timeout=2)
        logging.info(f"response: {response.text}")
        if response.status_code == 200 and response.json().get("ok"):
            # 保存发送的请求数据
            converted_sent_data = convert_str_gbk_to_utf8(str(payload))
            save_sent_data(api_url, converted_sent_data)
            return True, response.json()
        else:
            return False, response.json()
    except requests.RequestException as e:
        logging.error(f"Failed to send message: {e}")
        return False, None

@app.route('/', methods=['GET', 'POST'])
def index():
    received_url = request.url
    received_url = unquote(received_url)
    received_data = request.form.to_dict() if request.form else None

    # 保存接收到的请求数据
    converted_received_data = convert_str_gbk_to_utf8(str(received_data))
    save_received_data(received_url, converted_received_data)

    logging.info(f"Received URL: {received_url}")
    logging.info(f"Received POST Data: {received_data}")

    bot_id = request.args.get('bot_id') or (received_data.get('bot_id') if received_data else None)
    chat_id = request.args.get('chat_id') or (received_data.get('chat_id') if received_data else None)
    title = request.args.get('title') or (received_data.get('title') if received_data else None)
    desp = request.args.get('desp') or (received_data.get('desp') if received_data else None)
    url = request.args.get('url') or (received_data.get('url') if received_data else None)

    # 初始化一个空列表来保存错误信息
    error_list = []

    # 分别检查 bot_id, chat_id, 和 title 是否为空
    if bot_id is None:
        error_list.append("bot_id is a required field.")
    if chat_id is None:
        error_list.append("chat_id is a required field.")
    if title is None:
        error_list.append("title is a required field.")

    # 如果 error_list 不为空，返回错误信息和 400 状态码
    if error_list:
        TestStatus = request.args.get('TestStatus') or (received_data.get('TestStatus') if received_data else None)
        if TestStatus is None:
            return jsonify({"error": error_list}), 400
        else:
            return jsonify({"ok": "the test passed"}), 200

    pending_messages = read_pending_messages()

    success, response = send_telegram_message(bot_id, chat_id, title, desp, url)

    if success:
        new_pending_messages = []
        for msg in pending_messages:
            success, _ = send_telegram_message(msg['bot_id'], msg['chat_id'], msg['title'], msg['desp'], msg.get('url'))
            if not success:
                new_pending_messages.append(msg)
        write_pending_messages(new_pending_messages)
        return jsonify(response), 200
    else:
        if "【This is a delayed message】" not in desp:
            if desp is None:
                desp = f"【This is a delayed message】"
            else:
                desp = desp + f"\n\n【This is a delayed message】"

        pending_messages.append({
            'bot_id': bot_id,
            'chat_id': chat_id,
            'title': title,
            'desp': desp,
            'url': url
        })
        write_pending_messages(pending_messages)
        return jsonify({"error": "Failed to send message, added to pending list"}), 200

if __name__ == "__main__":
    config = load_config()
    port = config[0].get("port", 5000)
    app.run(host='0.0.0.0', port=port)