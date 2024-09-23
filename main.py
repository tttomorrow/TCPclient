import socket
from datetime import datetime

# 定义服务器地址和端口
HOST = '192.168.31.121'  # 监听所有可用的网络接口
PORT = 60000  # 服务器将监听的端口
TIMEOUT = 1000  # 设定超时时间，如果时间内没有数据接收，自动断开


def start_server():
    # 获取当前时间戳
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 生成带时间戳的文件名
    filename = f"received_data_{timestamp}.txt"

    # 创建 TCP 套接字
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        # 绑定到地址和端口
        server_socket.bind((HOST, PORT))
        # 监听来自客户端的连接
        server_socket.listen()
        print(f"服务器已启动，正在监听 {HOST}:{PORT}")

        while True:
            try:
                # 等待客户端连接
                conn, addr = server_socket.accept()
                with conn:
                    print(f"已连接到 {addr}")
                    # 设置连接的超时时间
                    conn.settimeout(TIMEOUT)

                    # 打开带时间戳的文件保存接收到的数据
                    with open(filename, 'a') as file:
                        while True:
                            try:
                                # 从客户端接收数据
                                data = conn.recv(1024)
                                if not data:
                                    break  # 客户端断开连接

                                # 实时保存数据到文件
                                file.write(data.decode('utf-8', errors='ignore'))
                                file.flush()  # 确保数据实时写入文件
                                print(f"{data.decode('utf-8', errors='ignore')}")
                            except socket.timeout:
                                print(f"超过 {TIMEOUT} 秒未收到数据，断开连接并等待新连接...")
                                break  # 超时，断开连接并等待下一个连接
            except Exception as e:
                print(f"发生错误: {e}")
                continue  # 处理异常，继续监听下一个连接


# 启动服务器
start_server()
