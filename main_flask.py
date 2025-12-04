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
DATA_DIR = Path("data/pastes")
TEMP_DIR = Path("data/temp_uploads")  # 临时存放切片
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)


# --- 辅助函数 ---

def clean_temp_folder(upload_id):
    """清理临时文件夹"""
    target_dir = TEMP_DIR / upload_id
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)


# --- 上传相关 API (分片处理) ---

@app.route("/api/upload/init", methods=["POST"])
def upload_init():
    """初始化上传，返回一个 upload_id"""
    upload_id = uuid.uuid4().hex
    upload_dir = TEMP_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    return jsonify({"status": "ok", "upload_id": upload_id})


@app.route("/api/upload/chunk", methods=["POST"])
def upload_chunk():
    """接收单个数据切片"""
    payload = request.get_json()
    if not payload:
        return jsonify({"err": "no_data"}), 400

    upload_id = payload.get("upload_id")
    chunk_index = payload.get("index")
    chunk_data = payload.get("data")  # 这是一个字符串片段

    if not upload_id or chunk_index is None or chunk_data is None:
        return jsonify({"err": "bad_params"}), 422

    # 安全检查：防止路径遍历
    if ".." in upload_id or "/" in upload_id:
        return jsonify({"err": "bad_id"}), 400

    save_dir = TEMP_DIR / upload_id
    if not save_dir.exists():
        return jsonify({"err": "session_expired"}), 404

    # 保存切片，文件名为索引
    try:
        chunk_path = save_dir / str(chunk_index)
        with open(chunk_path, "w", encoding="utf-8") as f:
            f.write(chunk_data)
    except Exception as e:
        return jsonify({"err": str(e)}), 500

    return jsonify({"status": "ok"})


@app.route("/api/upload/finish", methods=["POST"])
def upload_finish():
    """合并切片并保存为最终 Paste"""
    payload = request.get_json()
    upload_id = payload.get("upload_id")
    total_chunks = payload.get("total_chunks")

    if not upload_id or total_chunks is None:
        return jsonify({"err": "bad_params"}), 422

    chunk_dir = TEMP_DIR / upload_id
    if not chunk_dir.exists():
        return jsonify({"err": "not_found"}), 404

    # 1. 验证切片完整性
    for i in range(total_chunks):
        if not (chunk_dir / str(i)).exists():
            clean_temp_folder(upload_id)
            return jsonify({"err": f"missing_chunk_{i}"}), 400

    # 2. 合并数据
    full_data_str = ""
    try:
        for i in range(total_chunks):
            with open(chunk_dir / str(i), "r", encoding="utf-8") as f:
                full_data_str += f.read()
    except Exception as e:
        clean_temp_folder(upload_id)
        return jsonify({"err": "merge_failed"}), 500

    # 3. 解析并保存
    try:
        # 尝试解析 JSON，确认数据格式正确（虽然服务器不关心内容，但需确保是 JSON）
        data_obj = json.loads(full_data_str)

        # 补充服务器端元数据
        paste_id = uuid.uuid4().hex
        timestamp = int(time.time())

        # 将 timestamp 和 ID 注入到 JSON 中，或者包裹它
        # 为了保持混淆性，我们尽量不改变 data_obj 的核心结构，
        # 但我们需要一些索引字段。这里我们选择包裹一层，
        # 或者直接利用文件名做索引，文件内容就是用户上传的混淆 JSON。
        # 为了列表接口能读取，我们需要确保 data_obj 里有我们需要的字段。
        # 前端上传时已经包含了混淆后的 'tag' (remark) 和 'mode' (is_encrypted)

        data_obj["server_id"] = paste_id
        data_obj["server_ts"] = timestamp

        filename = f"{timestamp}_{paste_id}.json"
        with open(DATA_DIR / filename, "w", encoding="utf-8") as f:
            json.dump(data_obj, f, ensure_ascii=False, indent=0)  # indent=0 减小体积

    except json.JSONDecodeError:
        clean_temp_folder(upload_id)
        return jsonify({"err": "invalid_json_reconstructed"}), 400
    except Exception as e:
        clean_temp_folder(upload_id)
        return jsonify({"err": str(e)}), 500

    # 4. 清理
    clean_temp_folder(upload_id)

    return jsonify({"status": "success", "id": paste_id})


# --- 列表与删除 API ---

@app.route("/api/pastes", methods=["GET"])
def list_pastes():
    """返回列表，内容已经是混淆过的键名"""
    pastes = []
    files = sorted(DATA_DIR.glob("*.json"), reverse=True)

    for f in files[:200]:
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                # 仅返回列表需要的精简字段，减少流量
                # 混淆键名映射:
                # note -> remark
                # mode -> is_encrypted
                # server_ts -> timestamp
                # server_id -> id
                # sys_blob -> content (如果加密) 或 raw_text (如果明文)

                # 为了列表显示，我们需要返回足够的信息
                pastes.append(data)
        except Exception:
            continue

    return jsonify(pastes)


@app.route("/api/paste/<string:paste_id>", methods=["DELETE"])
def delete_paste(paste_id):
    if ".." in paste_id or "/" in paste_id:
        return jsonify({"err": "invalid_id"}), 400

    found_files = list(DATA_DIR.glob(f"*_{paste_id}.json"))
    if not found_files:
        return jsonify({"err": "not_found"}), 404

    try:
        for file_path in found_files:
            os.remove(file_path)
    except Exception as e:
        return jsonify({"err": str(e)}), 500

    return jsonify({"status": "success"})


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
