# media_tools package

# 抢先 mount NullHandler，让 F2 的 log_setup 在 `if logger.hasHandlers(): return`
# 处短路，阻止 F2 创建 ./logs/ 目录和 f2-trace-*.log 空文件。
# 必须先于任何 `from f2.* import ...` 执行（f2.log.logger 在 import 时即调用 log_setup）。
import logging as _logging

for _name in ("f2", "f2-trace"):
    _l = _logging.getLogger(_name)
    if not _l.hasHandlers():
        _l.addHandler(_logging.NullHandler())

del _logging
