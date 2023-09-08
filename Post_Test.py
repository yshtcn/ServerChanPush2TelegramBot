import requests

def send_post_request():
    url = "http://localhost:5000"  # 请替换为实际API端点

    # 构建表单数据
    payload = {
        "bot_id": "",
        "chat_id": "",
        "title": "Test Title",
        "desp": "Test Description---Test Description",
        "url": "https://example.com"
    }

    # 发送POST请求
    response = requests.post(url, data=payload)

    # 输出状态码
    print(f"Status Code: {response.status_code}")

    # 输出响应文本
    print(f"Response Text: {response.text}")

    # 在尝试解析JSON之前先检查响应是否包含JSON
    try:
        print(f"Response Data: {response.json()}")
    except:
        print("Failed to parse JSON from response.")

if __name__ == "__main__":
    send_post_request()
