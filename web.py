import socket
from datetime import datetime
import sqlite3
import re
from threading import Lock
import requests
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
# 定义服务器地址和端口
HOST = '192.168.31.121'
PORT = 60000
TIMEOUT = 1000  # 设定超时时间

# 动态生成数据库文件名，使用启动时的时间戳
DB_FILE = f'sensor_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'


# 初始化数据库并创建表
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 创建 DataPacket 表，存储基本信息（温度、湿度） #zj
    cursor.execute('''CREATE TABLE IF NOT EXISTS DataPacket (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sourceMacH INTEGER,
                        sourceMacL INTEGER,
                        sourceID INTEGER,
                        forwardID INTEGER,
                        forwardtoID INTEGER,
                        destID INTEGER,
                        protocol INTEGER,
                        packetID INTEGER,
                        temperature REAL,
                        humidity REAL
                    )''')

    # 创建 SnifferTable 表，存储监听表信息
    cursor.execute('''CREATE TABLE IF NOT EXISTS SnifferTable (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        data_packet_id INTEGER,
                        lastSniffTime INTEGER,
                        sourceID INTEGER,
                        snifferID INTEGER,
                        forwardCount INTEGER,
                        sourceCount INTEGER,
                        ackCount INTEGER,
                        routeReqCount INTEGER,
                        routeRepCount INTEGER,
                        lastRSSI INTEGER,
                        FOREIGN KEY (data_packet_id) REFERENCES DataPacket (id)
                    )''')

    conn.commit()
    conn.close()


# 将解析后的数据保存到数据库中
def save_data_to_db(packet_data):
    # 过滤掉非十六进制字符，只保留有效的十六进制字符
    packet_data = re.sub(r'[^0-9A-Fa-f]', '', packet_data)

    # 将数据包字符串转换为字节列表，每2个字符作为一个字节
    try:
        processed_data = []
        data_bytes = [int(packet_data[i:i+2], 16) for i in range(0, len(packet_data), 2)]
        for i in range(len(data_bytes)):
            if i >= 8 and data_bytes[i] == 0xFF:  # 从data[8]开始，替换0xFF为0x00
                processed_data.append(0x00)
            else:
                processed_data.append(data_bytes[i])
        data_bytes = processed_data
    except ValueError as e:
        print(f"数据解析错误: {e}")
        return
    print(data_bytes)
    # 提取温度和湿度
    if len(data_bytes) < 4:
        print(f"数据长度不足，无法解析温度和湿度: {data_bytes}")
        return

    temperature = data_bytes[8] + data_bytes[9] / 100.0
    humidity = data_bytes[10] + data_bytes[11] / 100.0

    # 创建数据包结构
    data_packet = {
        "sourceMacH": data_bytes[0],
        "sourceMacL": data_bytes[1],
        "sourceID": data_bytes[2],
        "forwardID": data_bytes[3],
        "forwardtoID": data_bytes[4],
        "destID": data_bytes[5],
        "protocol":  data_bytes[6],
        "packetID": data_bytes[2] << 8 | data_bytes[7],
        "temperature": temperature,
        "humidity": humidity
    }

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 插入 DataPacket 表数据
    cursor.execute('''INSERT INTO DataPacket (sourceMacH, sourceMacL, sourceID, forwardID, forwardtoID, destID, protocol, packetID, temperature, humidity)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (data_packet['sourceMacH'], data_packet['sourceMacL'], data_packet['sourceID'],
                    data_packet['forwardID'], data_packet['forwardtoID'], data_packet['destID'],
                    data_packet['protocol'], data_packet['packetID'], data_packet['temperature'], data_packet['humidity']))

    # 获取插入后的 DataPacket ID
    data_packet_id = cursor.lastrowid

    # 解析 SnifferTable 信息
    sniffer_tables = []
    sniffer_start = 12  # 监听表从第 12 字节开始
    for i in range(2):  # 两个监听表
        if len(data_bytes) < sniffer_start + 12:
            print(f"监听表数据长度不足: {data_bytes[sniffer_start:]}")
            continue

        sniffer_data = {
            "lastSniffTime": int.from_bytes(data_bytes[sniffer_start:sniffer_start + 4], 'big'),
            "sourceID": data_bytes[sniffer_start + 4],
            "snifferID": data_bytes[sniffer_start + 5],
            "forwardCount": data_bytes[sniffer_start + 6],
            "sourceCount": data_bytes[sniffer_start + 7],
            "ackCount": data_bytes[sniffer_start + 8],
            "routeReqCount": data_bytes[sniffer_start + 9],
            "routeRepCount": data_bytes[sniffer_start + 10],
            "lastRSSI": data_bytes[sniffer_start + 11]
        }
        sniffer_tables.append(sniffer_data)
        sniffer_start += 12  # 每个监听表 12 字节

    # 插入 SnifferTable 数据
    for sniffer_table in sniffer_tables:
        cursor.execute('''INSERT INTO SnifferTable (data_packet_id, lastSniffTime, sourceID, snifferID, forwardCount, sourceCount, ackCount, routeReqCount, routeRepCount, lastRSSI)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (data_packet_id, sniffer_table['lastSniffTime'], sniffer_table['sourceID'], sniffer_table['snifferID'],
                        sniffer_table['forwardCount'], sniffer_table['sourceCount'], sniffer_table['ackCount'],
                        sniffer_table['routeReqCount'], sniffer_table['routeRepCount'], sniffer_table['lastRSSI']))

    conn.commit()
    conn.close()



# 过滤掉无用的数据，只保留以"FF FF"开头并以换行结束的数据
def filter_data(data):
    match = re.search(r'FF FF.*?\n', data)
    if match:
        return match.group(0)  # 返回匹配到的数据
    return None  # 未匹配到返回None


def start_server():
    # 初始化数据库
    init_db()

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

                    while True:
                        try:
                            # 从客户端接收数据
                            data = conn.recv(1024)
                            if not data:
                                break  # 客户端断开连接

                            decoded_data = data.decode('utf-8', errors='ignore')
                            print(f"接收到的数据: {decoded_data}")

                            # 过滤数据
                            filtered_data = filter_data(decoded_data)
                            if filtered_data:
                                print(f"过滤后的数据: {filtered_data}")
                                # 保存过滤后的数据到数据库
                                save_data_to_db(filtered_data)
                                #发送filtered_data
                                requests.request('POST',"http://localhost:8000/hasReceivedData",json=filtered_data)#zjj,filtered_data为传到前端的数据，json格式,需要修改
                        except socket.timeout:
                            print(f"超过 {TIMEOUT} 秒未收到数据，断开连接并等待新连接...")
                            break  # 超时，断开连接并等待下一个连接
            except Exception as e:
                print(f"发生错误: {e}")
                continue  # 处理异常，继续监听下一个连接

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
def start_webServer():

    thread = None
    thread_lock = Lock()

    @app.route("/")
    def index():
        return render_template("test.html")

    @app.route("/hasReceivedData",methods=['POST'])
    def index1():
        # socketio.emit('my event', {'data': 'foo'}, namespace='/test')
        data=request.get_json()
        socketio.emit("serverSay", {"data": str(data)}, namespace="/webServer")
        return '0'

    # 当websocket连接成功时,自动触发connect默认方法
    @socketio.on("connect", namespace="/webServer")
    def connect():
        print("链接建立成功..")
    # 当websocket连接失败时,自动触发disconnect默认方法
    @socketio.on("disconnect", namespace="/webServer")
    def disconnect():
        print("链接断开..")

    @socketio.on("message", namespace="/webServer")#接收到消息
    def socket(message):
        print(f"接收到消息: {message['data']}")
        n=3
        while n!=0:
            socketio.sleep(1)
            n-=1
            socketio.emit("serverSay", {"data": 'zjj'+str(n)}, namespace="/webServer")

    socketio.run(app, host="0.0.0.0", port=8000)




# 启动服务器
# start_server()
start_webServer()
