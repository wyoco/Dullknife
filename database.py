import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = {
    "host": "localhost",
    "user": "dullknife",
    "password": "Dullkn1fe!",
    "database": "dullknife_rev1",
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
}

def get_db():
    connection = pymysql.connect(**DB_CONFIG)
    try:
        yield connection
    finally:
        connection.close()

