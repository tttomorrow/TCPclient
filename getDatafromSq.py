import sqlite3


# 查询数据库内容

DB_FILE = 'sensor_data_20240923_113138.db'

def query_db():
    # 连接到数据库
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 查询所有数据
    cursor.execute("SELECT * FROM DataPacket")

    # 获取所有行
    rows = cursor.fetchall()

    # 打印查询结果
    if rows:
        for row in rows:
            print(row)
    else:
        print("数据库中没有数据。")

    conn.close()


# 调用查询函数
query_db()
