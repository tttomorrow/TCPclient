import socket
from datetime import datetime
import sqlite3
import re
from threading import Lock
import requests
import sqlite3
import json
from threading import Thread
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
# 定义服务器地址和端口
HOST = '192.168.31.121'
PORT = 60000
TIMEOUT = 1000  # 设定超时时间



app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
def start_webServer():

    # thread = None
    # thread_lock = Lock()
    def process_data(database_name='sensor_data_20240924_105233.db'):
        s = requests.Session()
        path_dict = {}

        con = sqlite3.connect(database_name)
        cursor = con.cursor()

        cursor.execute("SELECT data_packet_id, node_id FROM PathInfo ORDER BY id")

        rows = cursor.fetchall()

        def take_first_elem(turple):
            return turple[0]

        rows.sort(key=take_first_elem)

        for row in rows:
            packet_id = row[0]
            node_id = row[1]
            if packet_id in path_dict.keys():
                path_dict[packet_id].append(node_id)
            else:
                path_dict[packet_id] = [node_id]

        # print(path_dict)
        for p_id, path in path_dict.items():
            time.sleep(1)
            json_data = {'packet_id': p_id, 'path': path}
            s.post("http://localhost:8000/hasReceivedData", json=json_data)


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
        socketio.emit("serverSay", {"data": '链接建立成功..'}, namespace="/webServer")
        p = Thread(target=process_data)
        p.start()

    socketio.run(app, host="0.0.0.0", port=8000)




# 启动服务器
# start_server()


start_webServer()
