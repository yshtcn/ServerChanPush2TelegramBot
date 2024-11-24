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
import base64
from html import escape

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
    

def send_messages_in_batches(batch_size=10):
    """
    批量发送待发送的消息，每次最多发送 batch_size 条。
    :param batch_size: 每批次发送的最大消息数量
    :return: 成功发送的数量和剩余待发送消息数量
    """
    pending_messages = read_pending_messages()
    if not pending_messages:
        return {"message": "No pending messages to send", "pending_messages_count": 0}

    to_send = pending_messages[:batch_size]  # 取出前 batch_size 条消息
    remaining_messages = pending_messages[batch_size:]  # 保留剩余的消息
    failed_messages = []

    for msg in to_send:
        success, _ = send_telegram_message(
            msg['bot_id'],
            msg['chat_id'],
            msg['title'],
            msg.get('desp'),
            msg.get('url')
        )
        if not success:
            failed_messages.append(msg)

    # 将失败的消息与剩余未尝试发送的消息合并，并写回文件
    remaining_messages.extend(failed_messages)
    write_pending_messages(remaining_messages)

    return {
        "message": "Batch processing completed",
        "successfully_sent_count": len(to_send) - len(failed_messages),
        "remaining_pending_messages_count": len(remaining_messages)
    }

# 读取待发送的消息
def read_pending_messages():
    try:
        with open(os.path.join(data_dir, "pending_messages.json"), "r") as f:
            encoded_messages = json.load(f)
            decoded_messages = []
            for msg in encoded_messages:
                decoded_msg = {
                    key: base64.b64decode(value).decode('utf-8') if value is not None and key in ['bot_id', 'chat_id', 'title', 'desp', 'url'] else value 
                    for key, value in msg.items()
                }
                decoded_messages.append(decoded_msg)
            return decoded_messages
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []


# 写入待发送的消息
def write_pending_messages(messages):
    encoded_messages = []
    for msg in messages:
        encoded_msg = {
            key: base64.b64encode(value.encode('utf-8')).decode('utf-8') if value is not None and key in ['bot_id', 'chat_id', 'title', 'desp', 'url'] else value 
            for key, value in msg.items()
        }
        encoded_messages.append(encoded_msg)
    with open(os.path.join(data_dir, "pending_messages.json"), "w") as f:
        json.dump(encoded_messages, f, ensure_ascii=False)


# 发送 Telegram 消息
def send_telegram_message(bot_id, chat_id, title, desp=None, url=None):
    all_bots_config = load_config()
    found = False
    delimiter = None
    api_url = None
    proxies = None

    for config in all_bots_config:
        main_bot_id = config['main_bot_id']
        main_chat_id = config.get('main_chat_id', '')
        sub_bots = config['sub_bots']
        api_url = config.get('api_url', None)
        proxies = config.get('proxies', None)
        if bot_id == main_bot_id and chat_id == main_chat_id:
            for sub_bot in sub_bots:
                for keyword in sub_bot['keywords']:
                    keyword_decode = keyword.decode('utf-8') if isinstance(keyword, bytes) else keyword
                    title_decode = title.decode('utf-8') if isinstance(title, bytes) else title
                    if keyword_decode.lower() in title_decode.lower():
                        bot_id = sub_bot['bot_id']
                        chat_id = sub_bot['chat_id']
                        delimiter = sub_bot.get('delimiter')
                        found = True
                        break
            if found:
                break
        if found:
            break

    api_url = api_url or f"https://api.telegram.org/bot{bot_id}/sendMessage"
    text = title
    text += f"\n\n{(desp.split(delimiter)[0] if delimiter and desp else desp) if desp else ''}"
    text = text.rstrip()

    text = escape(text)  # 处理 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)  # 移除所有 HTML 标签

    # 添加对消息长度的检查和拆分
    max_length = 4096  # Telegram 允许的最大消息长度
    messages = []
    while len(text) > max_length:
        part = text[:max_length]
        last_space = part.rfind(' ')
        if last_space != -1:
            part = part[:last_space]
        messages.append(part)
        text = text[len(part):].strip()
    messages.append(text)

    if url:
        for i in range(len(messages)):
            if i == len(messages) - 1:
                messages[i] += f"\n\n<a href=\"{url}\">详情：</a>{url}"
            messages[i] = unescape_url(messages[i])

    success = True
    for msg in messages:
        payload = {
            'chat_id': chat_id,
            'text': msg,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }

        try:
            response = requests.post(api_url, data=payload, proxies=proxies, timeout=2)
            logging.info(f"response: {response.text}")
            if response.status_code == 200 and response.json().get("ok"):
                converted_sent_data = convert_str_gbk_to_utf8(str(payload))
                save_sent_data(api_url, converted_sent_data)
            else:
                success = False
        except requests.RequestException as e:
            logging.error(f"Failed to send message: {e}")
            success = False

    return success, None if success else {"error": "Failed to send all parts of the message"}


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
            pending_messages = read_pending_messages()
            pending_count = len(pending_messages)
            if TestStatus == '1':
                return jsonify({"ok": "the test passed"}), 200
            elif TestStatus == '2':
                if pending_count == 0:
                    return jsonify({"ok": "the test passed", "pending_messages_count": pending_count}), 200
                else:
                    return jsonify({"ok": "the test passed", "pending_messages_count": pending_count}), 202
            elif TestStatus == '3':
                pending_messages = read_pending_messages()
                pending_count = len(pending_messages)
                if pending_messages:
                    new_pending_messages = []
                    for msg in pending_messages:
                        success, _ = send_telegram_message(msg['bot_id'], msg['chat_id'], msg['title'], msg['desp'], msg.get('url'))
                        if not success:
                            new_pending_messages.append(msg)
                    # 更新待发送消息列表，只包含失败的消息
                    write_pending_messages(new_pending_messages)
                    return jsonify({"ok": "re-sent pending messages", "pending_messages_count": pending_count, "remaining_pending_messages_count": len(new_pending_messages)}), 200
                else:
                    return jsonify({"ok": "no pending messages to re-send", "pending_messages_count": pending_count}), 200
            elif TestStatus == '4':
                # 读取当前待发送消息数量
                pending_messages = read_pending_messages()
                pending_count = len(pending_messages)

                if pending_count == 0:
                    # 如果没有待发送消息，直接返回与 TestStatus == '3' 一致的结构
                    return jsonify({
                        "ok": "no pending messages to re-send",
                        "pending_messages_count": pending_count,
                        "remaining_pending_messages_count": 0,
                        "successfully_sent_count": 0
                    }), 200

                # 调用批量发送逻辑，每次最多发送10条
                result = send_messages_in_batches(batch_size=3)

                # 读取剩余待发送消息数量
                remaining_messages = read_pending_messages()
                remaining_count = len(remaining_messages)

                # 返回结果与 TestStatus == '3' 保持一致，并增加成功发送条数
                return jsonify({
                    "ok": "batch processed",
                    "pending_messages_count": pending_count,
                    "remaining_pending_messages_count": remaining_count,
                    "successfully_sent_count": result["successfully_sent_count"]
                }), 200


    # 原始的消息发送逻辑
    pending_messages = read_pending_messages()

    success, response = send_telegram_message(bot_id, chat_id, title, desp, url)

    if success:
        # new_pending_messages = []
        # for msg in pending_messages:
        #     success, _ = send_telegram_message(msg['bot_id'], msg['chat_id'], msg['title'], msg['desp'], msg.get('url'))
        #     if not success:
        #         new_pending_messages.append(msg)
        # # 更新待发送消息列表，只包含失败的消息
        # write_pending_messages(new_pending_messages)
        pending_messages = read_pending_messages()
        pending_count = len(pending_messages)

        if pending_count == 0:
            # 如果没有待发送消息，直接返回与 TestStatus == '3' 一致的结构
            return jsonify({
            "ok": "send message success",
            "response": response,
        }), 200

        # 调用批量发送逻辑，每次最多发送10条
        result = send_messages_in_batches(batch_size=2)

        # 读取剩余待发送消息数量
        remaining_messages = read_pending_messages()
        remaining_count = len(remaining_messages)

        # 返回结果与 TestStatus == '3' 保持一致，并增加成功发送条数
        return jsonify({
            "ok": "send message success and batch processed",
            "pending_messages_count": pending_count,
            "remaining_pending_messages_count": remaining_count,
            "successfully_sent_count": result["successfully_sent_count"]
        }), 200
    else:
        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if "【This is a delayed message】" not in desp:
            if desp is None:
                desp = f"【This is a delayed message】\n\nTimestamp: {current_timestamp}"
            else:
                desp = desp + f"\n\n【This is a delayed message】\n\nTimestamp: {current_timestamp}"

        pending_messages.append({
            'bot_id': bot_id,
            'chat_id': chat_id,
            'title': title,
            'desp': desp,
            'url': url
        })
        write_pending_messages(pending_messages)
        return jsonify({"error": "Failed to send message, added to pending list"}), 202




if __name__ == "__main__":
    config = load_config()
    port = config[0].get("port", 5000)
    app.run(host='0.0.0.0', port=port)

