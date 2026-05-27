import contextlib
import http.server
import json
import socketserver

from .utils.auth_parser import AuthParser
from .utils.logger import logger

PORT = 8080
parser = AuthParser()

HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>认证数据可视化抓取工具</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f4f6f8; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1 { color: #333; }
        label { font-weight: bold; margin-top: 10px; display: block; }
        textarea, select, input { width: 100%; padding: 10px; margin-top: 5px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin-top: 15px; font-size: 16px; }
        button:hover { background: #0056b3; }
        .result { margin-top: 20px; padding: 15px; background: #eef; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; }
        .error { background: #fee; color: #c00; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 认证数据解析器</h1>
        <p>将捕获到的网页 Cookie、JSON 响应或请求文本粘贴在下方，一键提取并验证核心认证字段。</p>

        <label>数据类型</label>
        <select id="dataType">
            <option value="cookie">Cookie 字符串</option>
            <option value="json">JSON 响应</option>
            <option value="text">纯文本 / Headers</option>
        </select>

        <label>解析规则配置名</label>
        <input type="text" id="ruleName" value="douyin" placeholder="对应 auth_rules.yaml 中的键名">

        <label>待解析的原始数据</label>
        <textarea id="rawData" rows="8" placeholder="在此粘贴..."></textarea>

        <button onclick="parseData()">开始解析</button>

        <div id="resultBox" class="result" style="display: none;"></div>
    </div>

    <script>
        async function parseData() {
            const rawData = document.getElementById('rawData').value;
            const dataType = document.getElementById('dataType').value;
            const ruleName = document.getElementById('ruleName').value;
            const resultBox = document.getElementById('resultBox');

            if (!rawData) {
                alert('请先输入原始数据！');
                return;
            }

            resultBox.style.display = 'block';
            resultBox.className = 'result';
            resultBox.innerText = '解析中...';

            try {
                const response = await fetch('/api/parse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ raw_data: rawData, data_type: dataType, rule_name: ruleName })
                });
                const res = await response.json();

                if (res.success) {
                    resultBox.innerText = '✅ 解析成功！\\n\\n提取结果：\\n' + JSON.stringify(res.data, null, 2);
                } else {
                    resultBox.className = 'result error';
                    resultBox.innerText = '❌ 解析失败：' + res.message;
                }
            } catch (err) {
                resultBox.className = 'result error';
                resultBox.innerText = '网络请求失败：' + err.message;
            }
        }
    </script>
</body>
</html>
"""


class AuthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/parse":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 10 * 1024 * 1024:  # 10MB limit
                self.send_error(413, "Request body too large")
                return
            post_data = self.rfile.read(content_length)

            try:
                req = json.loads(post_data.decode("utf-8"))
                raw_data = req.get("raw_data", "")
                data_type = req.get("data_type", "cookie")
                rule_name = req.get("rule_name", "douyin")

                success, msg, data = parser.validate_data(raw_data, data_type, rule_name)

                res = {"success": success, "message": msg, "data": data}
                self.send_response(200)
            except (RuntimeError, OSError, ValueError) as e:
                res = {"success": False, "message": str(e), "data": {}}
                self.send_response(500)

            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
        else:
            self.send_error(404)


if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", PORT), AuthHandler) as httpd:
        logger.info(f"认证可视化服务器已启动: http://localhost:{PORT}")
        logger.info("按 Ctrl+C 停止服务")
        with contextlib.suppress(KeyboardInterrupt):
            httpd.serve_forever()
