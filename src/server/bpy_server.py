from bottle import request, response

import bottle
import os
import queue
import threading
import traceback

from .spec import bytes_to_object, object_to_bytes, BPY_PORT

from ..rig_package.parser.bpy import BpyParser, transfer_rigging


def _resolve_payload(data):
    if isinstance(data, dict) and "payload_path" in data:
        payload_path = data["payload_path"]
        try:
            with open(payload_path, "rb") as f:
                return bytes_to_object(f.read())
        finally:
            try:
                os.remove(payload_path)
            except OSError:
                pass
    return data

def run():
    path_queue = queue.Queue()
    result_queue = queue.Queue()
    
    app = bottle.Bottle()
    
    @app.route('/load', method='GET') # type: ignore
    def load():
        data = request.body.read() # type: ignore
        path_queue.put(('load', data))
        res = result_queue.get()
        payload = object_to_bytes(res)
        response.content_type = 'application/octet-stream'  # type: ignore
        return payload
    
    @app.route('/ping', method='GET') # type: ignore
    def ping():
        return 'pong'
    
    @app.route('/export', method='post') # type: ignore
    def export():
        data = request.body.read() # type: ignore
        path_queue.put(('export', data))
        res = result_queue.get()
        payload = object_to_bytes(res)
        response.content_type = 'application/octet-stream'  # type: ignore
        return payload
    
    @app.route('/transfer', method='post') # type: ignore
    def transfer():
        data = request.body.read() # type: ignore
        path_queue.put(('transfer', data))
        res = result_queue.get()
        payload = object_to_bytes(res)
        response.content_type = 'application/octet-stream'  # type: ignore
        return payload
    
    # [FabricatorStudio patch 2026-07-13] host 0.0.0.0 -> 127.0.0.1.
    #
    # This endpoint is an UNAUTHENTICATED REMOTE CODE EXECUTION when bound to
    # 0.0.0.0. Its request bodies are deserialised with bytes_to_object(), which
    # is torch.load(..., weights_only=False) — i.e. pickle, which executes
    # arbitrary code while unpickling. There is no auth, no token, and no origin
    # check. Bound to all interfaces, any host that can reach port 59876 while a
    # rig job is running can POST a crafted payload and run code as the user.
    #
    # Loopback costs nothing: the client already talks to
    # http://localhost:59876 (BPY_SERVER, src/server/spec.py), so it was never
    # reaching this server from off-box in the first place. 0.0.0.0 bought
    # exposure and no capability.
    #
    # Upstream is a research demo, where this is unremarkable. AutoSkin ships it
    # to artists' workstations, where it is not.
    def run_server(): bottle.run(app, host='127.0.0.1', port=BPY_PORT, server='tornado')
    threading.Thread(target=run_server, daemon=False).start()
    
    while True:
        d = path_queue.get()
        op = d[0]
        try:
            data = _resolve_payload(bytes_to_object(d[1]))
            if op == 'load':
                print("[SERVER] received load path:", data)
                asset = BpyParser.load(data)
                result_queue.put(asset)
            elif op == 'export':
                print("[SERVER] received export path:", data['filepath'])
                BpyParser.export(**data)
                result_queue.put('ok')
            elif op == 'transfer':
                print("[SERVER] received transfer path:", data['target_path'])
                transfer_rigging(**data)
                result_queue.put('ok')
            else:
                result_queue.put(f"unsupported op: {str(op)}")
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)
            result_queue.put({
                "error": f"{type(e).__name__}: {e}",
                "traceback": tb,
            })
