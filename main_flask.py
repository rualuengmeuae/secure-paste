import os
import json
import time
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS

app = Flask(__name__, static_folder='static')
app.config['JSON_AS_ASCII'] = False  # 保证返回 JSON 时中文不乱码

# 启用 CORS
CORS(app)

# 配置
DATA_DIR = Path("data/pastes")
DATA_DIR.mkdir(parents=True, exist_ok=True)


# --- API Endpoints ---

@app.route("/api/paste", methods=["POST"])
def create_paste():
    # 获取 JSON 数据
    payload = request.get_json()

    if not payload:
        return jsonify({"detail": "Invalid JSON"}), 400

    # 简单的数据校验
    content = payload.get("content")
    is_encrypted = payload.get("is_encrypted")
    remark = payload.get("remark", "")

    if content is None or is_encrypted is None:
        return jsonify({"detail": "Missing required fields: content or is_encrypted"}), 422

    paste_id = uuid.uuid4().hex
    timestamp = int(time.time())

    filename = f"{timestamp}_{paste_id}.json"
    file_path = DATA_DIR / filename

    # 构造存储数据
    data = {
        "id": paste_id,
        "timestamp": timestamp,
        "is_encrypted": bool(is_encrypted),
        "remark": str(remark)[:50],  # 简单截断，防止备注过长
        "content": content
    }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # 返回 500 错误
        return jsonify({"detail": str(e)}), 500

    return jsonify({"status": "success", "id": paste_id})


@app.route("/api/pastes", methods=["GET"])
def list_pastes():
    pastes = []
    # 获取文件列表并按文件名(时间戳)倒序排序
    files = sorted(DATA_DIR.glob("*.json"), reverse=True)

    # 限制读取前 200 个
    for f in files[:200]:
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                # 兼容旧数据（如果旧json没有remark字段）
                if "remark" not in data:
                    data["remark"] = ""
                pastes.append(data)
        except Exception:
            continue

    return jsonify(pastes)


@app.route("/api/paste/<string:paste_id>", methods=["DELETE"])
def delete_paste(paste_id):
    """
    删除指定 ID 的 Paste。
    由于文件名包含时间戳前缀，我们需要根据 paste_id 查找文件。
    """
    # 安全检查：简单的防止路径遍历（uuid通常是hex字符串）
    if ".." in paste_id or "/" in paste_id or "\\" in paste_id:
        return jsonify({"detail": "Invalid ID format"}), 400

    # 查找匹配该 ID 的文件
    # 文件名格式: {timestamp}_{uuid}.json
    found_files = list(DATA_DIR.glob(f"*_{paste_id}.json"))

    if not found_files:
        return jsonify({"detail": "Paste not found"}), 404

    deleted_count = 0
    try:
        for file_path in found_files:
            os.remove(file_path)
            deleted_count += 1
    except Exception as e:
        return jsonify({"detail": f"Failed to delete file: {str(e)}"}), 500

    return jsonify({"status": "success", "deleted_count": deleted_count})


# --- 静态文件托管 ---

@app.route('/')
def serve_index():
    """服务根路径的 index.html"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """服务其他静态资源"""
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return abort(404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8071, debug=False)