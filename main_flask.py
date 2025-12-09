import os
import json
import time
import uuid
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS

app = Flask(__name__, static_folder='static')
app.config['JSON_AS_ASCII'] = False

CORS(app)

# 目录配置
DATA_DIR = Path("data/store")  # 改名：pastes -> store
CACHE_DIR = Path("data/io_cache")  # 改名：temp_uploads -> io_cache
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# --- 辅助函数 ---

def clean_cache(sess_id):
    """清理临时会话文件夹"""
    target_dir = CACHE_DIR / sess_id
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)


# --- 数据传输相关 API (原 Upload) ---
# 混淆策略：模拟通用的系统 IO 接口，避免 upload 关键字

@app.route("/api/io/handshake", methods=["POST"])
def io_handshake():
    """原 upload/init：建立传输会话"""
    sess_id = uuid.uuid4().hex
    # 创建临时目录
    work_dir = CACHE_DIR / sess_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # 返回 sess_id 而非 upload_id
    return jsonify({"ret": 0, "sess_id": sess_id})


@app.route("/api/io/push_shard", methods=["POST"])
def io_push_shard():
    """原 upload/chunk：接收分片"""
    req = request.get_json()
    if not req:
        return jsonify({"err": "nodata"}), 400

    # 参数混淆
    sess_id = req.get("sess_id")
    seq_no = req.get("seq")  # 原 index
    blob = req.get("blob")  # 原 data

    if not sess_id or seq_no is None or blob is None:
        return jsonify({"err": "bad_args"}), 422

    if ".." in sess_id or "/" in sess_id:
        return jsonify({"err": "bad_id"}), 400

    save_dir = CACHE_DIR / sess_id
    if not save_dir.exists():
        return jsonify({"err": "timeout"}), 404

    try:
        # 保存分片
        chunk_path = save_dir / str(seq_no)
        with open(chunk_path, "w", encoding="utf-8") as f:
            f.write(blob)
    except Exception as e:
        return jsonify({"err": "io_err"}), 500

    return jsonify({"ret": 0})


@app.route("/api/io/commit", methods=["POST"])
def io_commit():
    """原 upload/finish：合并并提交"""
    req = request.get_json()
    sess_id = req.get("sess_id")
    count = req.get("cnt")  # 原 total_chunks

    if not sess_id or count is None:
        return jsonify({"err": "bad_args"}), 422

    chunk_dir = CACHE_DIR / sess_id
    if not chunk_dir.exists():
        return jsonify({"err": "missing"}), 404

    # 1. 验证完整性
    for i in range(count):
        if not (chunk_dir / str(i)).exists():
            clean_cache(sess_id)
            return jsonify({"err": f"missing_seq_{i}"}), 400

    # 2. 合并
    full_str = ""
    try:
        for i in range(count):
            with open(chunk_dir / str(i), "r", encoding="utf-8") as f:
                full_str += f.read()
    except Exception:
        clean_cache(sess_id)
        return jsonify({"err": "merge_err"}), 500

    # 3. 解析并落盘
    try:
        data_obj = json.loads(full_str)

        # 生成最终文件
        item_id = uuid.uuid4().hex
        ts = int(time.time())

        data_obj["srv_id"] = item_id  # server_id -> srv_id
        data_obj["ts"] = ts  # server_ts -> ts

        filename = f"{ts}_{item_id}.json"
        with open(DATA_DIR / filename, "w", encoding="utf-8") as f:
            json.dump(data_obj, f, ensure_ascii=False, indent=0)

    except json.JSONDecodeError:
        clean_cache(sess_id)
        return jsonify({"err": "fmt_err"}), 400
    except Exception as e:
        clean_cache(sess_id)
        return jsonify({"err": str(e)}), 500

    clean_cache(sess_id)
    return jsonify({"ret": 0, "ref": item_id})


# --- 列表与删除 API ---

@app.route("/api/list", methods=["GET"])
def get_list():
    items = []
    files = sorted(DATA_DIR.glob("*.json"), reverse=True)

    for f in files[:200]:
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                items.append(data)
        except Exception:
            continue

    return jsonify(items)


@app.route("/api/del/<string:tid>", methods=["DELETE"])
def del_item(tid):
    if ".." in tid or "/" in tid:
        return jsonify({"err": "bad_id"}), 400

    found_files = list(DATA_DIR.glob(f"*_{tid}.json"))
    if not found_files:
        return jsonify({"err": "404"}), 404

    try:
        for file_path in found_files:
            os.remove(file_path)
    except Exception as e:
        return jsonify({"err": "sys_err"}), 500

    return jsonify({"ret": 0})


# --- 静态资源 ---

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return abort(404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8071, debug=False)
