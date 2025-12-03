import sys

# 1. 设置项目路径
project_home = '/home/SecurePaste/secure-paste'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 2. 导入你的 FastAPI app
from main import app as fastapi_app

# 3. 关键修改：使用 a2wsgi 将 ASGI 转换为 WSGI
from a2wsgi import ASGIMiddleware

application = ASGIMiddleware(fastapi_app)








"""
import sys

# 1. 设置项目路径
project_home = '/home/SecurePaste/secure-paste'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 2. 导入你的 FastAPI app
from main_flask import app as application
"""