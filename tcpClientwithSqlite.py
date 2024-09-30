import socket
from datetime import datetime
import sqlite3
import re

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

    # 创建 DataPacket 表，
    # （源mac地址高位，源mac地址地位，源节点ID，转发节点ID，转发到节点ID，目的节点ID，协议类型，温度，湿度）
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
    # （数据包ID， 最后监听时间，被监听者ID，监听者ID，被监听者转发数据包次数，发送温湿度数据次数，发送ack次数，路由查询次数，路由回复次数，最后的监听信道RSSI）
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

    # 创建 PathInfo 表，存储节点ID、RSSI和环境噪声
    # 路径经过的节点ID，当前节点到上个路径节点间的RSSI，当前节点到上个路径节点间的环境噪声RSSI
    # 每个data_packet_id对应一条路径
    cursor.execute('''CREATE TABLE IF NOT EXISTS PathInfo (
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           data_packet_id INTEGER,
                           node_id INTEGER,
                           rssi INTEGER,
                           noise INTEGER,
                           FOREIGN KEY (data_packet_id) REFERENCES DataPacket (id)
                       )''')

    conn.commit()
    conn.close()


# 将解析后的数据保存到数据库中
def save_data_to_db(packet_data, RSSI, envirRSSI):
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
        "packetID": data_bytes[7],
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
        lastsnifftime = int.from_bytes(data_bytes[sniffer_start:sniffer_start + 4], 'big', signed=False)
        if lastsnifftime == 0 or data_bytes[sniffer_start + 5] == 0:
            sniffer_start += 12  # 每个监听表 12 字节
            continue
        if len(data_bytes) < sniffer_start + 12:
            print(f"监听表数据长度不足: {data_bytes[sniffer_start:]}")
            continue

        sniffer_data = {
            "lastSniffTime": lastsnifftime,
            "sourceID": data_bytes[sniffer_start + 4],
            "snifferID": data_bytes[sniffer_start + 5],
            "forwardCount": data_bytes[sniffer_start + 6],
            "sourceCount": data_bytes[sniffer_start + 7],
            "ackCount": data_bytes[sniffer_start + 8],
            "routeReqCount": data_bytes[sniffer_start + 9],
            "routeRepCount": data_bytes[sniffer_start + 10],
            "lastRSSI": data_bytes[sniffer_start + 11] - 256
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

    # 解析从第37字节开始的节点信息
    parse_and_save_path_info(cursor, data_packet_id, data_bytes[36:], data_bytes, RSSI, envirRSSI)

    conn.commit()
    conn.close()

# 解析从第37字节开始的节点信息，每三个字节为一组
def parse_and_save_path_info(cursor, data_packet_id, node_data_bytes, data_bytes, RSSI, envirRSSI):
    if len(node_data_bytes) < 3:
        print("没有足够的数据解析节点信息")
        return

    cursor.execute('''INSERT INTO PathInfo (data_packet_id, node_id, rssi, noise)
                              VALUES (?, ?, ?, ?)''', (data_packet_id, data_bytes[2], 0, 0))

    for i in range(0, len(node_data_bytes), 3):
        if i + 2 >= len(node_data_bytes) or node_data_bytes[i] == 0:
            break  # 确保不会超出数据范围
        node_id = node_data_bytes[i]
        rssi = node_data_bytes[i + 1] -256
        noise = node_data_bytes[i + 2] - 256  # 环境噪声需要减去256

        cursor.execute('''INSERT INTO PathInfo (data_packet_id, node_id, rssi, noise)
                          VALUES (?, ?, ?, ?)''', (data_packet_id, node_id, rssi, noise))

    cursor.execute('''INSERT INTO PathInfo (data_packet_id, node_id, rssi, noise)
                                  VALUES (?, ?, ?, ?)''', (data_packet_id, data_bytes[5], RSSI, envirRSSI))


# 过滤掉无用的数据，只保留以"FF FF"开头并以换行结束的数据
def filter_data(data):
    match = re.search(r'FF FF.*?\n', data)
    if match:
        return match.group(0)  # 返回匹配到的数据
    return None  # 未匹配到返回None

def getRSSItoCH(data):
    match = re.search(r'receivedPacketWithRSSI: (-?\d+)dBm', data)
    if match:
        return match.group(1)  # 返回匹配到的数据
    return None  # 未匹配到返回None

def getEnvirRSSItoCH(data):
    match = re.search(r'currentChannelNoise: (-?\d+)dBm', data)
    if match:
        return match.group(1)  # 返回匹配到的数据
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
        # 创建一个缓冲区来存储数据
        data_buffer = b''

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

                            # 将接收到的数据存入缓冲区
                            data_buffer += data

                            # 检查缓冲区是否包含完整的数据包（数据包以 'dB\r\n' 结尾）
                            if b'dB\r\n' in data_buffer:
                                # 分割数据包
                                packets = data_buffer.split(b'dB\r\n')

                                # 处理所有完整的数据包
                                for packet in packets[:-1]:
                                    decoded_data = packet.decode('utf-8', errors='ignore')
                                    print(f"接收到的数据: {decoded_data}")

                                    # 过滤数据
                                    filtered_data = filter_data(decoded_data)
                                    RSSI = getRSSItoCH(decoded_data)
                                    envirRSSI = getEnvirRSSItoCH(decoded_data)

                                    if filtered_data and RSSI and envirRSSI:
                                        print(f"过滤后的数据: {filtered_data}")
                                        print(RSSI, envirRSSI)
                                        # 保存过滤后的数据到数据库
                                        save_data_to_db(filtered_data, RSSI, envirRSSI)
                        except socket.timeout:
                            print(f"超过 {TIMEOUT} 秒未收到数据，断开连接并等待新连接...")
                            break  # 超时，断开连接并等待下一个连接
            except Exception as e:
                print(f"发生错误: {e}")
                continue  # 处理异常，继续监听下一个连接


# 启动服务器
start_server()
